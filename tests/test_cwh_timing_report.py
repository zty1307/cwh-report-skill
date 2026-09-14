from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from cwh_timing_report import build_timing_report


def test_timing_separates_recorded_commands_from_uninstrumented_wait(tmp_path):
    state = {"pipeline_id": "test", "status": "waiting_ai", "wall_clock_elapsed_seconds": 120, "updated_at": "2026-01-01T00:02:00+00:00", "stages": [{"stage_id": "research", "kind": "ai", "status": "waiting_ai"}]}
    (tmp_path / "pipeline_state.json").write_text(json.dumps(state), encoding="utf-8")
    events = [
        {"timestamp": "2026-01-01T00:00:00+00:00", "event": "stage_started"},
        {"timestamp": "2026-01-01T00:00:10+00:00", "event": "command_finished", "details": {"duration_seconds": 10, "exit_code": 124}},
        {"timestamp": "2026-01-01T00:02:00+00:00", "event": "stage_waiting"},
    ]
    (tmp_path / "pipeline_events.jsonl").write_text("\n".join(json.dumps({"pipeline_id": "test", "stage_id": "research", **event}) for event in events), encoding="utf-8")
    report = build_timing_report(tmp_path)
    assert report["instrumented_command_seconds"] == 10
    assert report["wait_and_other_uninstrumented_seconds"] == 110
    assert report["stages"][0]["observed_span_seconds"] == 120
    assert report["stages"][0]["command_timeouts"] == 1
    assert report["status"] == "waiting_ai"


def test_old_job_without_timing_does_not_invent_durations(tmp_path):
    (tmp_path / "pipeline_state.json").write_text(json.dumps({"pipeline_id": "old", "status": "failed", "stages": [{"stage_id": "render"}]}), encoding="utf-8")
    report = build_timing_report(tmp_path)
    assert report["wall_clock_seconds"] is None
    assert report["wait_and_other_uninstrumented_seconds"] is None
    assert report["stages"][0]["observed_span_seconds"] is None


def test_live_elapsed_is_separate_from_last_saved_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr('cwh_timing_report.time.time', lambda: 200)
    state = {'status': 'running', 'budget_started_epoch': 100, 'wall_clock_elapsed_seconds': 5,
             'input_contract': {'analysis_bundle': 'supplied.json', 'stage_timeouts_seconds': {'review': 90}},
             'stages': [{'stage_id': 'review', 'status': 'running', 'budget_started_epoch': 120}]}
    (tmp_path / 'pipeline_state.json').write_text(json.dumps(state), encoding='utf-8')
    result = build_timing_report(tmp_path)
    assert result['wall_clock_seconds'] == 5
    assert result['live_wall_clock_seconds'] == 100
    assert result['stages'][0]['live_elapsed_seconds'] == 80
    assert result['stages'][0]['observed_span_seconds'] is None
    assert result['supplied_analysis_bundle'] is True
