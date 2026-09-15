import copy
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_semantic_repairs import repair_missing_reasons
from cwh_semantic_compiler import labeled_publication_date, exclude_certain_period_misses


def fixture():
    packet = {'topic': '政策甲', 'agenda_topics': ['政策甲', '政策乙'], 'items': [
        {'id': 'r1', 'source': '原始机构', 'content': '政策甲的实施条件与机制。', 'segment_scheme': 'sentence_v2'},
        {'id': 'r2', 'content': '会议事实。', 'segment_scheme': 'sentence_v2'}]}
    decision = {'heading': '原始标题', 'clusters': [], 'items': [
        {'id': 'r1', 'decision': 'eligible', 'claims': [{'claim': '原始观点', 'speaker': '原始主体'}]},
        {'id': 'r2', 'decision': 'excluded', 'reason': '仅事实', 'claims': []}]}
    return packet, decision


def test_reason_completion_changes_only_missing_reason_and_keeps_actual_run(monkeypatch, tmp_path):
    packet, decision = fixture()
    original = copy.deepcopy(decision)
    def model(request, prompt, command, workspace, label, timeout, **kwargs):
        assert [r['id'] for r in request['items']] == ['r1']
        assert request['agenda_topics'] == packet['agenda_topics']
        assert timeout <= 45 and kwargs['reuse_cache'] is True
        return {'items': [{'id': 'r1', 'reason': '原文阐述实施条件'}]}, {'session_id': 'actual-test-stub'}
    monkeypatch.setattr('cwh_host_research.semantic_json', model)
    result, run = repair_missing_reasons(packet, decision, [], tmp_path, 90)
    assert result['items'][1] == original['items'][1]
    assert {k: v for k, v in result['items'][0].items() if k != 'reason'} == original['items'][0]
    assert result['transport_repairs'][0]['original_items'] == [original['items'][0]]
    assert result['transport_repairs'][0]['run'] == run
    assert result['heading'] == original['heading'] and decision == original


@pytest.mark.parametrize('patch', [
    {'items': [{'id': 'r2', 'reason': '错ID'}]},
    {'items': [{'id': 'r1', 'reason': '理由', 'decision': 'excluded'}]},
    {'items': [{'id': 'r1', 'reason': ''}]},
    {'items': [{'id': 'r1', 'reason': '理由'}, {'id': 'r1', 'reason': '重复'}]},
])
def test_reason_completion_rejects_identity_decision_or_coverage_changes(monkeypatch, tmp_path, patch):
    packet, decision = fixture()
    monkeypatch.setattr('cwh_host_research.semantic_json', lambda *a, **k: (patch, {'session_id': 'stub'}))
    with pytest.raises(ValueError, match='only requested IDs'):
        repair_missing_reasons(packet, decision, [], tmp_path, 30)


def test_no_call_for_complete_reasons_or_insufficient_budget(monkeypatch, tmp_path):
    packet, decision = fixture()
    def fail(*args, **kwargs):
        raise AssertionError('No model call authorized by this component')
    monkeypatch.setattr('cwh_host_research.semantic_json', fail)
    assert repair_missing_reasons(packet, decision, [], tmp_path, 14) == (decision, None)
    decision['items'][0]['reason'] = '原始具体理由'
    assert repair_missing_reasons(packet, decision, [], tmp_path, 90) == (decision, None)


def test_partial_native_reasons_complete_only_remaining_ids_in_original_budget(monkeypatch, tmp_path):
    packet, decision = fixture()
    decision['items'][1].pop('reason')
    calls = []
    def model(request, prompt, command, workspace, label, timeout, **kwargs):
        calls.append((request, label, timeout))
        rows = [{'id': 'r1', 'reason': '原文机制'}] if len(calls) == 1 else [{'id': 'r2', 'reason': '原文仅事实'}]
        return {'items': rows}, {'session_id': str(len(calls)), 'seconds': 1}
    monkeypatch.setattr('cwh_host_research.semantic_json', model)
    result, run = repair_missing_reasons(packet, decision, [], tmp_path, 90)
    assert [row['id'] for row in calls[1][0]['items']] == ['r2']
    assert calls[1][2] <= calls[0][2] <= 45
    assert calls[0][1] != calls[1][1]
    assert [row['reason'] for row in result['items']] == ['原文机制', '原文仅事实']
    assert run['seconds'] == 2 and len(run['reason_completion_runs']) == 2
    assert 'reason' not in decision['items'][0]


def test_reason_cache_namespace_is_topic_specific(monkeypatch, tmp_path):
    packet, decision = fixture()
    labels = []
    def model(request, prompt, command, workspace, label, timeout, **kwargs):
        labels.append(label)
        return {'items': [{'id': 'r1', 'reason': '原文机制'}]}, {'session_id': 'test'}
    monkeypatch.setattr('cwh_host_research.semantic_json', model)
    repair_missing_reasons(packet, decision, [], tmp_path, 90)
    packet['topic'] = '另一议题'
    repair_missing_reasons(packet, decision, [], tmp_path, 90)
    assert labels[0] != labels[1]


def test_exact_minimum_budget_allows_first_call_without_extending_deadline(monkeypatch, tmp_path):
    packet, decision = fixture()
    calls = []
    def model(request, prompt, command, workspace, label, timeout, **kwargs):
        calls.append(timeout)
        return {'items': [{'id': 'r1', 'reason': '原文机制'}]}, {'session_id': 'native'}
    monkeypatch.setattr('cwh_host_research.semantic_json', model)
    result, run = repair_missing_reasons(packet, decision, [], tmp_path, 15)
    assert 0 < calls[0] <= 15
    assert result['items'][0]['reason'] == '原文机制'


def test_plain_timestamp_source_header_excludes_outside_period_without_editing_source():
    content = '文章标题\n2026-08-13 17:07\n来源：\n真实媒体\n正文含2026年8月15日施行。'
    evidence = labeled_publication_date(content)
    assert evidence['date'] == '2026-08-13'
    assert content[evidence['start']:evidence['end']].strip() == '2026-08-13 17:07'
    packet = {'period': {'start': '2026-07-31', 'end': '2026-08-03'},
              'items': [{'id': 'w1', 'origin': 'web', 'content': content}]}
    decision = {'items': [{'id': 'w1', 'decision': 'eligible', 'claims': [{'claim': '期外观点'}]}]}
    result = exclude_certain_period_misses(packet, decision)
    assert result['items'][0]['decision'] == 'excluded'
    assert decision['items'][0]['decision'] == 'eligible'
    assert packet['items'][0]['content'] == content


@pytest.mark.parametrize('content', [
    '文章正文于2026-08-13 17:07讨论决定。\n来源：真实媒体',
    'https://example.org/2026-08-13\n来源：真实媒体',
    '2026-08-13 17:07\n将于近期实施',
    '2026-08-13 25:07\n来源：真实媒体',
    '2026-08-13 17:07\n来源：真实媒体\n发布时间：2026-08-14',
])
def test_header_date_does_not_infer_narrative_url_invalid_or_conflicting_dates(content):
    assert labeled_publication_date(content) is None
