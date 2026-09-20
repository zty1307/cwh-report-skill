import copy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_claim_length import refine_long_claims


def fixture():
    text = '只有配套措施到位才可能改善服务。' + '与判断无关的背景材料。' * 20
    claim = {'speaker': '研究机构', 'role': '', 'speaker_type': 'media_voice',
             'claim': text, 'quote': text, 'cluster': 'k1'}
    packet = {'topic': '公共服务', 'items': [{'id': 'r1', 'content': text}]}
    decision = {'items': [{'id': 'r1', 'decision': 'eligible', 'claims': [claim]}],
                'heading': '建议改善公共服务', 'clusters': [{'key': 'k1', 'heading': '建议完善配套'}]}
    return packet, decision


def test_only_native_selected_claim_string_changes_before_independent_review(tmp_path):
    packet, decision = fixture()
    original = copy.deepcopy((packet, decision))
    def model(request, prompt, command, workspace, label, timeout, **kwargs):
        assert request['items'][0]['source_excerpt'] == packet['items'][0]['content']
        assert timeout == 90 and '保留必要条件' in prompt
        return {'items': [{'id': 'c1', 'claim': '只有配套措施到位才可能改善服务。',
                           'reason': '移除无关背景，保留条件与可能性'}]}, {'session_id': 'native-editor'}
    result, audit = refine_long_claims(packet, decision, [], tmp_path, 200, model)
    assert (packet, decision) == original
    assert result['heading'] == decision['heading'] and result['clusters'] == decision['clusters']
    after, before = result['items'][0]['claims'][0], decision['items'][0]['claims'][0]
    assert {k:v for k,v in after.items() if k != 'claim'} == {k:v for k,v in before.items() if k != 'claim'}
    assert after['claim'] == '只有配套措施到位才可能改善服务。'
    assert audit['status'] == 'authored_pending_independent_review'
    assert audit['original_decision'] == decision
    assert 'semantic_review' not in after


@pytest.mark.parametrize('case', ['timeout', 'missing', 'duplicate', 'unknown', 'extra_field', 'longer'])
def test_optional_edit_failure_preserves_every_original_claim(tmp_path, case):
    packet, decision = fixture()
    def model(*args, **kwargs):
        if case == 'timeout': raise TimeoutError('native task deadline')
        row = {'id': 'c1', 'claim': '只有配套措施到位才可能改善服务。', 'reason': '原文支持'}
        if case == 'unknown': row['id'] = 'c9'
        if case == 'extra_field': row['speaker'] = '另一个人'
        if case == 'longer': row['claim'] = decision['items'][0]['claims'][0]['claim'] + '新增'
        return {'items': [] if case == 'missing' else [row, row] if case == 'duplicate' else [row]}, {'session_id': 'test'}
    result, audit = refine_long_claims(packet, decision, [], tmp_path, 45, model)
    assert result == decision and audit['status'] == 'deferred'


def test_no_extra_call_for_normal_claim_or_insufficient_budget(tmp_path):
    packet, decision = fixture()
    def forbidden(*args, **kwargs): raise AssertionError('No unnecessary model call')
    result, audit = refine_long_claims(packet, decision, [], tmp_path, 24, forbidden)
    assert result == decision and audit['status'] == 'deferred'
    decision['items'][0]['claims'][0]['claim'] = '必要条件下才可能改善服务。'
    result, audit = refine_long_claims(packet, decision, [], tmp_path, 45, forbidden)
    assert result == decision and audit['status'] == 'not_needed'


def test_reserve_pool_is_not_rewritten_or_charged_to_editorial_budget(tmp_path):
    packet, decision = fixture()
    decision['items'][0]['claims'][0]['formal_use'] = 'reserve'
    def forbidden(*args, **kwargs): raise AssertionError('Reserve is outside this editing task')
    result, audit = refine_long_claims(packet, decision, [], tmp_path, 45, forbidden)
    assert result == decision and audit['status'] == 'not_needed'


@pytest.mark.parametrize('case', ['missing_id', 'quote_mismatch', 'invalid_range'])
def test_unresolved_evidence_mapping_defers_to_regular_review_without_stopping_flow(tmp_path, case):
    packet, decision = fixture()
    claim = decision['items'][0]['claims'][0]
    if case == 'missing_id':
        decision['items'][0]['id'] = 'unknown'
    elif case == 'quote_mismatch':
        claim['quote'] = '并未出现在原文的文字'
    else:
        claim['quote_range'] = {'start': 9999, 'end': 10000}
    before = copy.deepcopy((packet, decision))
    def forbidden(*args, **kwargs):
        raise AssertionError('Unmapped evidence must not be sent to the optional editor')
    result, audit = refine_long_claims(packet, decision, [], tmp_path, 45, forbidden)
    assert (packet, decision) == before and result == decision
    assert audit['status'] == 'deferred'
    assert audit['reason'] == 'evidence_mapping_requires_regular_review'
    assert 'semantic_review' not in claim


def test_invalid_native_edit_keeps_actual_run_provenance(tmp_path):
    packet, decision = fixture()
    def model(*args, **kwargs):
        return {'items': []}, {'session_id': 'actual-invalid-response'}
    result, audit = refine_long_claims(packet, decision, [], tmp_path, 45, model)
    assert result == decision and audit['status'] == 'deferred'
    assert audit['run']['session_id'] == 'actual-invalid-response'


def test_new_151_character_limit_gets_source_bound_edit(tmp_path):
    packet, decision = fixture()
    text = '甲' * 151
    packet['items'][0]['content'] = text
    decision['items'][0]['claims'][0].update(claim=text, quote=text)
    def model(request, *args, **kwargs):
        assert request['items'][0]['source_excerpt'] == text
        return {'items': [{'id': 'c1', 'claim': '甲' * 150, 'reason': '测试返回；仍须独立原文审核'}]}, {'session_id': 'test-boundary'}
    result, audit = refine_long_claims(packet, decision, [], tmp_path, 30, model)
    assert len(result['items'][0]['claims'][0]['claim']) == 150
    assert audit['status'] == 'authored_pending_independent_review'
