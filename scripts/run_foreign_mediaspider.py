from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_SUPERVISOR_CANDIDATES = [
    Path.home() / ".codex/skills/mediaspider-supervisor",
    Path("D:/Codex/2026-06-15/ai-1-1-https-drive-weixin/work/mediaspider-supervisor"),
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def resolve_supervisor(value: str) -> Path:
    candidates = [Path(value)] if value else DEFAULT_SUPERVISOR_CANDIDATES
    for candidate in candidates:
        script = candidate.expanduser().resolve() / "scripts/run_task.py"
        if script.exists():
            return script.parent.parent
    raise FileNotFoundError("mediaspider-supervisor was not found")


def build_task(plan: dict[str, Any], platforms: list[str], mode: str, limit: int = 8) -> dict[str, Any]:
    period = plan.get("monitoring_period") or {}
    queries: list[str] = []
    topic_map: dict[str, str] = {}
    for item in plan.get("topics") or []:
        exact_topic = str(item.get("topic") or "").strip()
        overseas_queries = ((item.get("queries") or {}).get("overseas") or [])
        for query in overseas_queries:
            value = str(query or "").strip()
            if not value or value in topic_map:
                continue
            queries.append(value)
            topic_map[value] = exact_topic
    if not queries:
        raise ValueError("research plan has no overseas queries")
    return {
        "collector": "foreign",
        "topic": "CWH overseas media and public discussion",
        "platforms": platforms,
        "topics": queries,
        "start_date": str(period.get("start") or ""),
        "end_date": str(period.get("end") or ""),
        "match_mode": "any",
        "foreign_mode": mode,
        "fallback_limit": max(1, int(limit)),
        "deep_crawl": True,
        "no_browser_cookies": True,
        "drop_undated": False,
        "cwh_topic_map": topic_map,
        "cwh_evidence_only": True,
        "cwh_authority_note": "Social rows are qualitative only. News rows affect the overseas count only after complete pre-workbook AI review, time-window validation and deduplication.",
    }


def parse_run_dir(stdout: str) -> Path | None:
    match = re.search(r"Run directory:\s*(.+)", stdout or "")
    return Path(match.group(1).strip()).resolve() if match else None


def collector_exit_code(run_dir: Path | None) -> int | None:
    if not run_dir:
        return None
    log_path = run_dir / "run.log"
    if not log_path.exists():
        return None
    matches = re.findall(r"(?m)^exit_code=(\d+)\s*$", log_path.read_text(encoding="utf-8", errors="replace"))
    return int(matches[-1]) if matches else None


def classify_collection_completion(
    *,
    executed: bool,
    supervisor_exit_code: int,
    run_dir: Path | None,
    stdout: str,
) -> dict[str, Any]:
    inner_exit_code = collector_exit_code(run_dir)
    completed_no_rows = bool(
        executed
        and run_dir
        and supervisor_exit_code == 4
        and inner_exit_code == 0
        and "finished without data rows" in (stdout or "").lower()
    )
    completed = bool(executed and (supervisor_exit_code == 0 or completed_no_rows))
    return {
        "collection_completed": completed,
        "collection_status": (
            "completed_no_rows" if completed_no_rows else "completed" if completed else "failed"
        ),
        "zero_result": completed_no_rows,
        "collector_exit_code": inner_exit_code,
    }


def run_command(command: list[str], timeout_sec: int) -> dict[str, Any]:
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
        start_new_session=os.name != "nt",
    )
    try:
        stdout, stderr = process.communicate(timeout=max(1, timeout_sec))
        return {"exit_code": process.returncode, "stdout": stdout, "stderr": stderr, "timed_out": False}
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
            )
        else:
            try:
                os.killpg(process.pid, 9)
            except ProcessLookupError:
                pass
        stdout, stderr = process.communicate()
        return {"exit_code": 124, "stdout": stdout, "stderr": stderr, "timed_out": True}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run MediaSpider Supervisor's foreign collector for a CWH research plan.")
    parser.add_argument("research_plan")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--supervisor", default="")
    parser.add_argument("--media-home", default="")
    parser.add_argument("--platforms", default="grounding,x,youtube,reddit")
    parser.add_argument("--foreign-mode", choices=["fallback-only", "hybrid", "last30days"], default="fallback-only")
    parser.add_argument("--limit", type=int, default=8, help="Maximum rows per foreign source and topic.")
    parser.add_argument("--task-timeout-sec", type=int, default=120, help="Per-platform collector timeout; one slow platform must not block the others.")
    parser.add_argument("--run", action="store_true", help="Execute collection. Default only validates command generation.")
    args = parser.parse_args()

    plan_path = Path(args.research_plan).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    supervisor = resolve_supervisor(args.supervisor)
    plan = load_json(plan_path)
    platforms = [item.strip().lower() for item in args.platforms.split(",") if item.strip()]
    task = build_task(plan, platforms, args.foreign_mode, args.limit)
    task_path = output_dir / "foreign_mediaspider_task.json"
    task_path.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")

    platform_runs: list[dict[str, Any]] = []
    run_dirs: list[Path] = []
    if not args.run:
        command = [sys.executable, str(supervisor / "scripts/run_task.py"), str(task_path)]
        if args.media_home:
            command.extend(["--media-home", args.media_home])
        command.append("--dry-run")
        run = run_command(command, args.task_timeout_sec)
        run_dir = parse_run_dir(run["stdout"])
        completion = classify_collection_completion(
            executed=False,
            supervisor_exit_code=run["exit_code"],
            run_dir=run_dir,
            stdout=run["stdout"],
        )
        platform_runs.append({"platforms": platforms, **run, "run_dir": str(run_dir) if run_dir else ""})
    else:
        for platform in platforms:
            platform_task = build_task(plan, [platform], args.foreign_mode, args.limit)
            platform_task_path = output_dir / f"foreign_mediaspider_task_{platform}.json"
            platform_task_path.write_text(json.dumps(platform_task, ensure_ascii=False, indent=2), encoding="utf-8")
            command = [sys.executable, str(supervisor / "scripts/run_task.py"), str(platform_task_path)]
            if args.media_home:
                command.extend(["--media-home", args.media_home])
            run = run_command(command, args.task_timeout_sec)
            run_dir = parse_run_dir(run["stdout"])
            one_completion = classify_collection_completion(
                executed=True,
                supervisor_exit_code=run["exit_code"],
                run_dir=run_dir,
                stdout=run["stdout"],
            )
            if run_dir and one_completion["collection_completed"]:
                run_dirs.append(run_dir)
            platform_runs.append({
                "platform": platform,
                "task": str(platform_task_path),
                **run,
                **one_completion,
                "run_dir": str(run_dir) if run_dir else "",
            })
        completed_count = sum(1 for item in platform_runs if item.get("collection_completed"))
        timed_out_count = sum(1 for item in platform_runs if item.get("timed_out"))
        all_completed = bool(platform_runs) and completed_count == len(platform_runs)
        completion = {
            "collection_completed": all_completed,
            "collection_status": "completed" if all_completed else "partial_completed" if completed_count else "failed",
            "zero_result": bool(all_completed and all(item.get("zero_result") for item in platform_runs)),
            "collector_exit_code": 0 if all_completed else 124 if timed_out_count else 1,
            "completed_platform_count": completed_count,
            "timed_out_platform_count": timed_out_count,
        }
        run_dir = run_dirs[0] if len(run_dirs) == 1 else None
    samples_path = output_dir / "foreign_mediaspider_samples.json"
    ingest_result: dict[str, Any] = {}
    if args.run and run_dirs:
        ingest = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("ingest_mediacrawler_outputs.py")), *[str(item) for item in run_dirs], "--output", str(samples_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        ingest_result = {
            "exit_code": ingest.returncode,
            "stdout": ingest.stdout[-4000:],
            "stderr": ingest.stderr[-4000:],
            "samples": str(samples_path) if samples_path.exists() else "",
        }

    result = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "research_plan": str(plan_path),
        "task": str(task_path),
        "supervisor": str(supervisor),
        "dry_run": not args.run,
        "command_exit_code": 0 if completion["collection_completed"] else completion.get("collector_exit_code", 1),
        **completion,
        "run_dir": str(run_dir) if run_dir else "",
        "run_dirs": [str(item) for item in run_dirs],
        "platform_runs": platform_runs,
        "stdout": "\n".join(str(item.get("stdout") or "")[-2000:] for item in platform_runs)[-6000:],
        "stderr": "\n".join(str(item.get("stderr") or "")[-2000:] for item in platform_runs)[-6000:],
        "ingest": ingest_result,
    }
    result_path = output_dir / ("foreign_mediaspider_run.json" if args.run else "foreign_mediaspider_dry_run.json")
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": completion["collection_status"] if args.run else "ok" if platform_runs[0]["exit_code"] == 0 else "failed",
        "dry_run": not args.run,
        "task": str(task_path),
        "run_dir": str(run_dir) if run_dir else "",
        "samples": ingest_result.get("samples", ""),
        "result": str(result_path),
    }, ensure_ascii=False, indent=2))
    if not args.run:
        return int(platform_runs[0]["exit_code"])
    return 0 if completion["collection_completed"] else int(completion.get("collector_exit_code") or 1)


if __name__ == "__main__":
    raise SystemExit(main())
