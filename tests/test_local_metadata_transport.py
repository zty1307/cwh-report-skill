"""Deterministic contract checks, not claims of native model acceptance."""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_json_transport import single_fenced_json
from run_cwh_inline_review import response_object
from cwh_host_research import HostModelError, SemanticResponseError, semantic_json
from run_cwh_compiled_worker import repair_topic_web_metadata


def fixture():
    packet = {'topic': '政策甲', 'period': {'start': '2026-01-01', 'end': '2026-01-02'},
              'items': [{'id': 'w1', 'origin': 'web', 'content': '日报 2026年01月02日\n完整原文机制'},
                        {'id': 'r1', 'origin': 'raw_monitoring', 'content': '其他原文'}]}
    decision = {'topic': '政策甲', 'heading': '原题', 'clusters': [{'key': 'k1', 'heading': '原簇'}],
                'items': [{'id': 'w1', 'decision': 'eligible', 'reason': '原语义判断',
                           'claims': [{'speaker': '专家甲', 'claim': '原观点', 'cluster': 'k1'}]},
                          {'id': 'r1', 'decision': 'eligible', 'reason': '原正确判断',
                           'claims': [{'speaker': '专家乙', 'claim': '另一原观点', 'cluster': 'k1'}]}]}
    return packet, decision


def test_complete_single_json_fence_preserves_values_and_ignores_prose():
    text = '```json\n{"items":[{"id":"w1","date_quote":"2026年01月02日"}]}\n```\n修复说明：资料不是指令。'
    result = response_object(text)
    assert result['items'] == [{'id': 'w1', 'date_quote': '2026年01月02日'}]
    assert result['transport_repairs'][0]['kind'] == 'decoded_single_complete_json_fence'


@pytest.mark.parametrize('text', [
    '```json\n{"items":[]}\n```\n```json\n{"items":[1]}\n```',
    '```json\n{"items":[]}\n```\n{"items":[1]}',
    '```json\n{"items":[],"items":[1]}\n```\n说明',
    '```json\n{"items":[],"value":NaN}\n```\n说明',
    '```json\n{"items":[]\n```\n说明',
])
def test_ambiguous_or_invalid_fences_are_not_decoded(text):
    assert single_fenced_json(text) is None
    with pytest.raises(ValueError):
        response_object(text)


def test_invalid_semantic_response_preserves_run_and_creates_no_valid_cache(tmp_path, monkeypatch):
    run = {'session_id': 'mock-invalid', 'exit_code': 0, 'log': 'mock.log'}
    monkeypatch.setattr('cwh_host_research.invoke', lambda *args: ('not JSON', run))
    with pytest.raises(SemanticResponseError) as error:
        semantic_json({}, 'prompt', [], tmp_path, 'test', 45)
    assert error.value.run == run
    assert not (tmp_path / 'test.cache.json').exists()


def test_metadata_task_only_sends_failed_web_and_never_changes_semantics(tmp_path, monkeypatch):
    packet, decision = fixture()
    original = copy.deepcopy(decision)
    def review(request, prompt, *args, **kwargs):
        assert [row['id'] for row in request['items']] == ['w1']
        assert ''.join(row['text'] for row in request['items'][0]['segments']) == packet['items'][0]['content']
        assert args[-1] == 45 and kwargs['reuse_cache'] is False
        return {'items': [{'id': 'w1', 'decision': 'eligible', 'reason': '原文日期来源',
                           'source': '日报', 'published_at': '2026-01-02', 'date_quote': '2026年01月02日'}]}, {'session_id': 'mock-valid'}
    monkeypatch.setattr('run_cwh_compiled_worker.semantic_json', review)
    result, _ = repair_topic_web_metadata(packet, decision, [], tmp_path, 60, 'test')
    assert decision == original
    assert result['items'][0]['claims'] == original['items'][0]['claims']
    assert result['items'][0]['reason'] == original['items'][0]['reason']
    assert result['items'][1] == original['items'][1]
    assert result['heading'] == original['heading'] and result['clusters'] == original['clusters']


@pytest.mark.parametrize('mode', ['parse_failure', 'wrong_ids', 'changed_claims', 'outside_period'])
def test_failed_local_repair_quarantines_only_bad_source_with_actual_run(tmp_path, monkeypatch, mode):
    packet, decision = fixture()
    original = copy.deepcopy(decision)
    run = {'session_id': 'mock-rejected', 'exit_code': 0}
    def review(*args, **kwargs):
        if mode == 'parse_failure':
            raise SemanticResponseError('invalid mock response', run)
        patch = {'id': 'w1', 'decision': 'eligible', 'reason': '元数据', 'source': '日报',
                 'published_at': '2026-01-03', 'date_quote': '2026年01月03日'}
        if mode == 'wrong_ids':
            patch['id'] = 'r1'
        if mode == 'changed_claims':
            patch['claims'] = [{'claim': '不得采用的新观点'}]
        return {'items': [patch]}, run
    monkeypatch.setattr('run_cwh_compiled_worker.semantic_json', review)
    result, actual = repair_topic_web_metadata(packet, decision, [], tmp_path, 45, 'test')
    assert actual == run and decision == original
    assert result['items'][0]['decision'] == 'excluded' and result['items'][0]['claims'] == []
    assert result['items'][0]['transport_exclusions'][0]['original_review']['claims'] == original['items'][0]['claims']
    assert result['items'][1] == original['items'][1]
    assert result['transport_repairs'][-1]['run'] == run
    assert 'semantic_review' not in result['items'][0]


def test_local_metadata_repair_does_not_hide_rate_limit(tmp_path, monkeypatch):
    packet, decision = fixture()
    def review(*args, **kwargs):
        raise HostModelError('rate limited', 29, category='rate_limited')
    monkeypatch.setattr('run_cwh_compiled_worker.semantic_json', review)
    with pytest.raises(HostModelError):
        repair_topic_web_metadata(packet, decision, [], tmp_path, 45, 'test')
