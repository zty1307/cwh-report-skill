"""Summarize observed pipeline/worker time without inventing API usage metrics."""
from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from cwh_pipeline_runtime import atomic_write_json


def timestamp(value: Any) -> float | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None


def build_timing_report(job_dir: Path) -> dict[str, Any]:
    state = json.loads((job_dir / "pipeline_state.json").read_text(encoding="utf-8-sig"))
    now = time.time()
    events_path = job_dir / "pipeline_events.jsonl"
    by_stage: dict[str, list[dict[str, Any]]] = defaultdict(list)
    invalid_lines = 0
    if events_path.exists():
        for line in events_path.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                invalid_lines += 1
                continue
            if event.get("pipeline_id") not in {"", state.get("pipeline_id")}:
                continue
            by_stage[str(event.get("stage_id") or "")].append(event)
    stages = []
    for row in state.get("stages") or []:
        events = by_stage[str(row["stage_id"])]
        commands = [event.get("details") or {} for event in events if event.get("event") == "command_finished"]
        starts = [stamp for event in events if event.get("event") == "stage_started" and (stamp := timestamp(event.get("timestamp"))) is not None]
        ends = [stamp for event in events if event.get("event") in {"stage_succeeded", "stage_failed", "stage_waiting", "pipeline_time_budget_exhausted"} and (stamp := timestamp(event.get("timestamp"))) is not None]
        stages.append({
            "stage_id": row["stage_id"], "label": row.get('label', row['stage_id']), "kind": row.get("kind"), "status": row.get("status"),
            "budget_seconds": (state.get('input_contract', {}).get('stage_timeouts_seconds') or {}).get(row['stage_id']),
            "live_elapsed_seconds": round(max(0.0, now-row['budget_started_epoch']), 3) if row.get('status') in {'running', 'retrying'} and row.get('budget_started_epoch') else None,
            "observed_span_seconds": round(max(0.0, max(ends) - min(starts)), 3) if starts and ends else None,
            "instrumented_command_seconds": round(sum(float(item.get("duration_seconds") or 0) for item in commands), 3),
            "instrumented_command_count": len(commands),
            "command_timeouts": sum(item.get("exit_code") == 124 for item in commands),
            "stage_attempts": sum(event.get("event") == "stage_started" for event in events),
            "wait_returns": sum(event.get("event") == "stage_waiting" for event in events),
            "cache_hits": sum(event.get("event") == "stage_cache_hit" for event in events),
        })
    total = state.get("completed_elapsed_seconds", state.get("wall_clock_elapsed_seconds"))
    command_seconds = sum(item["instrumented_command_seconds"] for item in stages)
    return {
        "schema_version": "1.0", "pipeline_id": state.get("pipeline_id"), "status": state.get("status"),
        "observed_through": state.get("updated_at"), "wall_clock_seconds": total,
        "live_wall_clock_seconds": round(max(0.0, now-state['budget_started_epoch']), 3) if state.get('status') == 'running' and state.get('budget_started_epoch') else None,
        "supplied_analysis_bundle": bool(state.get('input_contract', {}).get('analysis_bundle')),
        'supplied_domestic_evidence_review': bool(state.get('input_contract', {}).get('domestic_evidence_review')),
        "supplied_comment_capture": bool(state['input_contract']['comment_capture']) if 'comment_capture' in state.get('input_contract', {}) else None,
        "instrumented_command_seconds": round(command_seconds, 3),
        "wait_and_other_uninstrumented_seconds": round(max(0.0, float(total) - command_seconds), 3) if total is not None else None,
        "invalid_event_lines": invalid_lines,
        "stages": stages,
        "limitations": [
            "Only observed through the latest saved state; an ongoing external wait is not a completed duration.",
            "External manual model/tool calls have no per-call timing unless the host records them. API tokens and cost are unknown.",
            "Old jobs without command_finished events have incomplete command timings. This report does not certify successful delivery.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-dir", required=True)
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    report = build_timing_report(Path(args.job_dir).resolve())
    if args.output:
        atomic_write_json(Path(args.output).resolve(), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
