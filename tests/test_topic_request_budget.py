import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_cwh_compiled_worker as worker
from cwh_model_contract import build_task_payload
import run_cwh_resumable_pipeline as pipeline


@pytest.mark.parametrize('remaining,future,expected', [(1000, 2, 180), (240, 2, 150),
                         (90, 2, 30), (60, 0, 60), (500, 0, 180)])
def test_one_topic_never_takes_all_future_time(remaining, future, expected):
    assert worker.single_topic_request_budget(remaining, future) == expected


@pytest.mark.parametrize('remaining', [0, -1])
def test_exhausted_budget_is_not_reset(remaining):
    with pytest.raises(TimeoutError):
        worker.single_topic_request_budget(remaining, 3)


def test_uncapped_profile_retains_existing_remaining_allocation():
    assert worker.single_topic_request_budget(1000, 5, maximum=0) == 1000


@pytest.mark.parametrize('profile,cap', [('bounded_40m', 180), ('bounded_60m', 180), ('exhaustive', 0)])
def test_model_contract_exposes_same_limits_without_provider_names(tmp_path, profile, cap):
    task = build_task_payload(stage_id='domestic_viewpoints', task_type='domestic_viewpoint_research_and_review',
              expected_output=tmp_path / 'analysis.json', inputs={}, rules=[], profile_name=profile)
    assert task['semantic_request_limits']['single_topic_max_seconds'] == cap


def test_actual_sequential_host_passes_cap_and_preserves_coverage_and_sources(tmp_path, monkeypatch):
    calls = []
    packets = [{'topic': f'议题{i}', 'items': [{'id': f'r{i}', 'content': '真实原文。'}]} for i in range(3)]
    def fake_semantic(packet, prompt, command, workspace, label, timeout, **kwargs):
        calls.append((packet, timeout))
        return {'items': [{'id': r['id'], 'decision': 'excluded', 'reason': '本例无实质解读', 'claims': []}
                          for r in packet['items']], 'clusters': [], 'heading': '本例证据不足'}, {
                          'session_id': label, 'completed_at': '本次时间', 'seconds': 1}
    monkeypatch.setattr(worker, 'semantic_json', fake_semantic)
    decisions, _ = worker.author_topic_decisions(packets, '规则', [], tmp_path, time.monotonic() + 1000,
                 reuse_cache=True, maximum_request_seconds=180, future_topic_reserve_seconds=45)
    assert len(calls) == len(decisions) == 3
    assert all(0 < timeout <= 180 for _, timeout in calls)
    assert [{r['id'] for r in p['items']} for p in packets] == [{r['id'] for r in d['items']} for d in decisions]
    assert all(packet['items'][0]['segments'][0]['text'] == '真实原文。' for packet, _ in calls)


@pytest.mark.parametrize('remaining,expected', [(150, 150), (20, 20), (None, 60)])
def test_outer_worker_and_inner_task_share_effective_budget(tmp_path, remaining, expected):
    from types import SimpleNamespace
    task_path = tmp_path / 'task.json'
    pipeline.atomic_write_json(task_path, {'time_budget_seconds': 60})
    seen = []
    def command(stage, command, **kwargs):
        seen.append(kwargs['timeout_seconds'])
        return 0, tmp_path / 'unit.log'
    runner = SimpleNamespace(root=tmp_path,
        input_contract={'ai_worker_command': ['worker', '{task}'], 'stage_timeouts_seconds': {'author': 60}},
        remaining_budget_seconds=lambda stage: remaining, run_command=command)
    outcome = pipeline.maybe_run_ai_worker(runner, SimpleNamespace(stage_id='author'), task_path,
                                           tmp_path / 'unused-output.json', allow_missing_output=True)
    assert outcome is None and seen == [expected]
    task = pipeline.read_json(task_path)
    assert task['time_budget_seconds'] == 60
    if remaining is not None:
        assert task['remaining_budget_seconds'] == int(expected)
    else:
        assert 'remaining_budget_seconds' not in task
