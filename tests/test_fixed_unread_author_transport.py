import copy
from pathlib import Path
import sys
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_cwh_compiled_worker as worker


def packet():
    return {'topic': '公共服务', 'period': {'start': '2026-01-01', 'end': '2026-01-04'},
            'items': [{'id': 'r1', 'origin': 'raw_monitoring', 'content': '完整原文，包含真实政策对象。'},
                      {'id': 'w1', 'origin': 'web', 'content': '', 'full_text_status': 'access_failed'},
                      {'id': 'w2', 'origin': 'web', 'content': ' \n', 'full_text_status': 'not_fetched_bounded_budget'}]}


def test_only_readable_body_ids_are_requested_then_all_original_ids_are_audited(monkeypatch, tmp_path):
    source = packet()
    frozen = copy.deepcopy(source)
    calls = []
    def model(request, prompt, *args, **kwargs):
        calls.append(request)
        assert [r['id'] for r in request['items']] == ['r1']
        assert 'w1' not in prompt and 'w2' not in prompt
        return {'items': [{'id': 'r1', 'decision': 'excluded', 'reason': '仅会议动作事实', 'claims': []}],
                'heading': '', 'clusters': []}, {'session_id': 'native-test-double', 'seconds': 1}
    monkeypatch.setattr(worker, 'semantic_json', model)
    decisions, runs = worker.author_topic_decisions([source], '规则', [], tmp_path,
                                                   time.monotonic() + 60, reuse_cache=False)
    assert len(calls) == 1
    assert [r['id'] for r in decisions[0]['items']] == ['r1', 'w1', 'w2']
    assert runs['topic_runs'][0]['fixed_unread_web_ids'] == ['w1', 'w2']
    for choice in decisions[0]['items'][1:]:
        assert choice['classification_origin'] == 'deterministic_body_availability_gate'
        assert '未做全文语义审核' in choice['reason'] and choice['claims'] == []
    assert source == frozen


def test_unread_web_only_uses_no_model_and_reports_explicit_shortfall(monkeypatch, tmp_path):
    source = packet()
    source['items'] = source['items'][1:]
    monkeypatch.setattr(worker, 'semantic_json', lambda *args, **kwargs: pytest.fail('No body to review'))
    decisions, runs = worker.author_topic_decisions([source], '规则', [], tmp_path,
                                                   time.monotonic() + 60, reuse_cache=False)
    assert len(decisions[0]['items']) == 2 and decisions[0]['clusters'] == []
    assert '未取得正文' in decisions[0]['shortfall_reason']
    assert runs['topic_runs'][0]['model_invoked'] is False


def test_model_cannot_invent_reviews_for_ids_not_supplied(monkeypatch, tmp_path):
    source = packet()
    monkeypatch.setattr(worker, 'semantic_json', lambda *args, **kwargs: (
        {'items': [{'id': 'r1'}, {'id': 'w1'}, {'id': 'w2'}]}, {'session_id': 'invalid'}))
    with pytest.raises(ValueError, match='every item exactly once'):
        worker.author_topic_decisions([source], '规则', [], tmp_path,
                                     time.monotonic() + 60, reuse_cache=False)


def test_full_text_transport_is_unchanged_for_every_actual_readable_row():
    source = packet()
    old = worker.semantic_packet(source)
    new, fixed = worker.author_transport_with_fixed_unread_web(source)
    assert new['items'] == old['items'][:1]
    assert set(fixed) == {'w1', 'w2'}
