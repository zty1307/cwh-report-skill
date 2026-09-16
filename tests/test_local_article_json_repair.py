import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import cwh_author_batches as batches
from cwh_host_research import HostModelError, SemanticResponseError


def test_local_json_repair_preserves_full_packet_and_both_actual_runs(tmp_path):
    packet = {'topic': '动态议题', 'items': [{'id': 'r1', 'content': '完整原文' * 20000}]}
    original = copy.deepcopy(packet)
    calls = []
    def model(request, prompt, command, workspace, label, timeout, reuse_cache):
        calls.append((copy.deepcopy(request), label, timeout, reuse_cache))
        if len(calls) == 1:
            raise SemanticResponseError('JSON syntax error', {'session_id': 'first', 'seconds': 10})
        return {'items': [{'id': 'r1', 'decision': 'excluded', 'reason': '原生判断', 'claims': []}]}, {
            'session_id': 'repair', 'seconds': 11}
    result, run = batches.native_article_batch(packet, '原规则', [], tmp_path, 'author', 90, model, reuse_cache=True)
    assert calls[0][0] == calls[1][0] == original == packet
    assert calls[1][1:] == ('author-json-repair', 45, False)
    assert run['seconds'] == 21 and run['original_rejected_run']['session_id'] == 'first'
    assert result['items'][0]['decision'] == 'excluded'
    assert Path(result['transport_repairs'][0]['failure_checkpoint']['path']).is_file()


def test_transport_timeout_does_not_trigger_json_retry(tmp_path):
    calls = []
    def model(*args, **kwargs):
        calls.append(1)
        raise HostModelError('timeout', 124)
    with pytest.raises(HostModelError):
        batches.native_article_batch({}, '', [], tmp_path, 'author', 90, model, reuse_cache=False)
    assert len(calls) == 1


def test_no_extra_budget_after_completed_malformed_answer(tmp_path, monkeypatch):
    clock = iter([100, 180])
    monkeypatch.setattr(batches.time, 'monotonic', lambda: next(clock))
    calls = []
    def model(*args, **kwargs):
        calls.append(1)
        raise SemanticResponseError('invalid JSON', {'session_id': 'first'})
    with pytest.raises(SemanticResponseError, match='without local repair time'):
        batches.native_article_batch({}, '', [], tmp_path, 'author', 90, model, reuse_cache=False)
    assert len(calls) == 1


def test_second_invalid_reply_propagates_without_third_call(tmp_path):
    calls = []
    def model(*args, **kwargs):
        calls.append(1)
        raise SemanticResponseError('invalid JSON', {'session_id': str(len(calls))})
    with pytest.raises(SemanticResponseError):
        batches.native_article_batch({}, '', [], tmp_path, 'author', 90, model, reuse_cache=False)
    assert len(calls) == 2


def test_name_and_role_anchor_errors_repair_locally_without_host_changing_quote(tmp_path):
    packet = {'items': [{'id': 'r1', 'segments': [
        {'id': 'p1/1', 'text': '研究院研究员张某说，'},
        {'id': 'p1/2', 'text': '完善设施有助于降低成本。'}]}]}
    first = {'items': [{'id': 'r1', 'decision': 'eligible', 'claims': [
        {'speaker': '张某', 'role': '研究院研究员', 'speaker_type': 'named_person',
         'quote_range': ['p1/2', 'p1/2'], 'claim': '完善设施有助于降低成本'}]}]}
    original = copy.deepcopy(first)
    calls = []
    def model(request, prompt, *args, **kwargs):
        calls.append(prompt)
        response = copy.deepcopy(first)
        if len(calls) == 2:
            assert 'p1/1' in str(request['validation_problems'])
            response = {'repairs': [{'id': 'r1', 'index': 0, 'speaker': '张某', 'role': '研究院研究员',
                                    'quote_range': ['p1/1', 'p1/2']}]}
        return response, {'session_id': str(len(calls)), 'seconds': 1}
    result, run = batches.native_article_batch(packet, '', [], tmp_path, 'author', 90, model, reuse_cache=False)
    assert len(calls) == 2 and run['seconds'] == 2
    assert result['items'][0]['claims'][0]['quote_range'] == ['p1/1', 'p1/2']
    assert first == original
    assert 'semantic_review' not in result['items'][0]['claims'][0]


def test_second_bad_span_does_not_trigger_a_third_model_call(tmp_path):
    packet = {'items': [{'id': 'r1', 'segments': [{'id': 'p1/1', 'text': '原文'}]}]}
    bad = {'items': [{'id': 'r1', 'decision': 'eligible', 'claims': [
        {'quote_range': ['other/1', 'other/2']}]}]}
    calls = []
    def model(*args, **kwargs):
        calls.append(1)
        return bad, {'session_id': str(len(calls))}
    with pytest.raises(SemanticResponseError):
        batches.native_article_batch(packet, '', [], tmp_path, 'author', 90, model, reuse_cache=False)
    assert len(calls) == 2


def test_targeted_span_patch_cannot_rewrite_claims_or_unrequested_items():
    original = {'items': [{'id': 'r1', 'claims': [{'claim': '完整原判断', 'speaker': '甲'}, {'claim': '另一完整判断'}]},
                          {'id': 'r2', 'claims': [{'claim': '其他文章不动'}]}]}
    targets = [{'id': 'r1', 'index': 0}]
    row = {'id': 'r1', 'index': 0, 'speaker': '甲', 'role': '真实职务', 'quote_range': ['p/1', 'p/3']}
    result = batches.apply_article_span_repairs(original, targets, {'repairs': [row]})
    assert result['items'][0]['claims'][0]['claim'] == '完整原判断'
    assert result['items'][0]['claims'][1] == original['items'][0]['claims'][1]
    assert result['items'][1] == original['items'][1]
    assert 'role' not in original['items'][0]['claims'][0]
    for invalid in ({**row, 'claim': '不许改写'}, {**row, 'id': 'r2'}, {**row, 'index': True}):
        with pytest.raises(ValueError):
            batches.apply_article_span_repairs(original, targets, {'repairs': [invalid]})
