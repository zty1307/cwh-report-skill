"""Regression checks for automatic-worker completion and repair handoffs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_cwh_resumable_pipeline as pipeline_module


def hotword_packet(*, reviewed: bool = True) -> dict:
    return {
        "review_method": "ai_semantic_review",
        "second_pass_completed": reviewed,
        "settings": {"minimum_term_count": 36},
        "selected": [{"term": f"测试短语{index}"} for index in range(36)],
    }


def test_research_plan_uses_resolved_input_mode_budgets_without_resetting_clock(tmp_path, monkeypatch):
    name, profile = pipeline_module.execution_profile('bounded_60m')
    allocation = pipeline_module.resolved_stage_budgets(profile, 'standard_workbook')
    contract = {'execution_profile': name, 'stage_timeouts_seconds': allocation}
    pipeline = pipeline_module.CwhPipeline(tmp_path, contract)
    target = pipeline.artifacts / 'research_plan.json'
    def command(*args, **kwargs):
        pipeline_module.atomic_write_json(target, {'topics': [{'topic': '当前议题'}],
            'execution_budget': {'stage_budgets_seconds': profile['stage_budgets_seconds'], 'wall_clock_budget_seconds': 3600}})
        return 0, tmp_path / 'unit.log'
    monkeypatch.setattr(pipeline.runner, 'run_command', command)
    before = json.dumps(pipeline.runner.input_contract, sort_keys=True)
    result = pipeline.research_plan(pipeline.runner, pipeline.runner.spec_by_id['research_plan'])
    data = json.loads(target.read_text('utf-8'))
    assert result.status == 'succeeded'
    assert data['execution_budget']['stage_budgets_seconds'] == allocation
    assert data['execution_budget']['stage_budgets_seconds']['workbook'] == 30
    assert data['execution_budget']['wall_clock_budget_seconds'] == 3600
    assert json.dumps(pipeline.runner.input_contract, sort_keys=True) == before


def test_compact_cli_preserves_current_action_and_errors_without_full_history(tmp_path):
    state = {"pipeline_id": "test", "status": "waiting_ai", "current_stage": "hotwords",
             "next_action": {"task": "tasks/hotwords.json", "problems": ["needs review"]},
             "wall_clock_elapsed_seconds": 40, "input_contract": {"large": "x" * 10000},
             "stages": [{"stage_id": "hotwords", "status": "waiting_ai", "last_error": {"code": "review_required"}, "artifact_hashes": {"large": "x" * 10000}}]}
    before = json.dumps(state)
    result = pipeline_module.cli_state_summary(state, tmp_path)
    assert json.dumps(state) == before
    assert result["next_action"] == state["next_action"]
    assert result["current_error"] == {"code": "review_required"}
    assert result["stage_statuses"] == {"hotwords": "waiting_ai"}
    assert result["wall_clock_elapsed_seconds"] == 40
    assert result["state_path"] == str((tmp_path / "pipeline_state.json").resolve())
    assert "input_contract" not in result and "stages" not in result
    assert len(json.dumps(result)) < len(before) / 10


def test_cli_defaults_to_compact_and_allows_full_compatibility(tmp_path):
    args = ["status", "--job-dir", str(tmp_path)]
    assert pipeline_module.parser().parse_args(args).output_format == "compact"
    assert pipeline_module.parser().parse_args(args + ["--output-format", "full"]).output_format == "full"


@pytest.mark.parametrize("reviewed", [True, False])
def test_hotword_worker_output_is_validated_in_same_invocation(tmp_path, monkeypatch, reviewed):
    pipeline = pipeline_module.CwhPipeline(tmp_path, {"execution_profile": "bounded_60m"})
    monkeypatch.setattr(pipeline_module, "topic_titles", lambda _: ["测试议题"])
    observed_tasks = []

    def worker(runner, spec, task, output):
        observed_tasks.append(json.loads(task.read_text(encoding="utf-8")))
        pipeline_module.atomic_write_json(output, hotword_packet(reviewed=reviewed))

    monkeypatch.setattr(pipeline_module, "maybe_run_ai_worker", worker)
    result = pipeline.hotwords(pipeline.runner, pipeline.runner.spec_by_id["hotwords"])

    assert len(observed_tasks) == 1
    if reviewed:
        assert result.status == "succeeded"
    else:
        assert result.status == "failed"
        assert result.retryable
        assert result.error_code == "hotword_audit_invalid"
        assert "二次复核" in result.details["problems"][0]


def test_hotword_manual_handoff_still_waits_without_output(tmp_path, monkeypatch):
    pipeline = pipeline_module.CwhPipeline(tmp_path, {"execution_profile": "bounded_60m"})
    monkeypatch.setattr(pipeline_module, "topic_titles", lambda _: ["测试议题"])

    result = pipeline.hotwords(pipeline.runner, pipeline.runner.spec_by_id["hotwords"])

    assert result.status == "waiting_ai"
    assert Path(result.details["task"]).exists()


def test_hotword_repair_task_receives_current_validation_problem(tmp_path, monkeypatch):
    pipeline = pipeline_module.CwhPipeline(tmp_path, {"execution_profile": "bounded_60m"})
    monkeypatch.setattr(pipeline_module, "topic_titles", lambda _: ["测试议题"])
    pipeline_module.atomic_write_json(pipeline.artifacts / "hotword_audit.json", hotword_packet(reviewed=False))
    observed_tasks = []

    def worker(runner, spec, task, output):
        observed_tasks.append(json.loads(task.read_text(encoding="utf-8")))
        pipeline_module.atomic_write_json(output, hotword_packet())

    monkeypatch.setattr(pipeline_module, "maybe_run_ai_worker", worker)
    result = pipeline.hotwords(pipeline.runner, pipeline.runner.spec_by_id["hotwords"])

    assert result.status == "succeeded"
    assert "二次复核" in observed_tasks[0]["inputs"]["validation_problems"][0]


def test_malformed_existing_draft_reaches_worker_with_parse_feedback(tmp_path, monkeypatch):
    pipeline = pipeline_module.CwhPipeline(tmp_path, {"execution_profile": "bounded_60m"})
    monkeypatch.setattr(pipeline_module, "topic_titles", lambda _: ["测试议题"])
    draft_path = pipeline.artifacts / "analysis_bundle.json"
    draft_path.write_text('{"metadata": ', encoding="utf-8")
    observed_tasks = []

    def worker(runner, spec, task, output):
        observed_tasks.append(json.loads(task.read_text(encoding="utf-8")))
        # Syntactic repair alone must still fail the real evidence validator.
        pipeline_module.atomic_write_json(output, {})

    monkeypatch.setattr(pipeline_module, "maybe_run_ai_worker", worker)
    result = pipeline.domestic_viewpoints(pipeline.runner, pipeline.runner.spec_by_id["domestic_viewpoints"])

    assert "JSONDecodeError" in observed_tasks[0]["inputs"]["validation_problems"][0]
    assert result.status == "failed"
    assert result.retryable
    assert result.error_code == "analysis_bundle_invalid"
    assert result.details["problems"]
    assert all("JSONDecodeError" not in problem for problem in result.details["problems"])


@pytest.mark.parametrize("worker_text", ['{"metadata": ', "[]", '{"viewpoints": []}'])
def test_malformed_worker_draft_returns_repairable_validation_failure(tmp_path, monkeypatch, worker_text):
    pipeline = pipeline_module.CwhPipeline(tmp_path, {"execution_profile": "bounded_60m"})
    monkeypatch.setattr(pipeline_module, "topic_titles", lambda _: ["测试议题"])

    def worker(runner, spec, task, output):
        output.write_text(worker_text, encoding="utf-8")

    monkeypatch.setattr(pipeline_module, "maybe_run_ai_worker", worker)
    result = pipeline.domestic_viewpoints(pipeline.runner, pipeline.runner.spec_by_id["domestic_viewpoints"])

    assert result.status == "failed"
    assert result.retryable
    assert result.error_code == "analysis_bundle_invalid"
    assert result.details["problems"]
