"""No native model calls: verify flat protocol conversion retains original claims."""
import copy
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from cwh_claim_synthesis import flat_packet, restore_synthesis, duplicate_assignment_request, apply_duplicate_assignments


def fixture():
    claims = [{'index': i, 'speaker': '专家甲', 'role': '研究员', 'speaker_type': 'named_person',
        'claim': '完整判断' + str(i), 'original_excerpt': '完整原文'+str(i)} for i in range(2)]
    request = {'topic': '动态议题', 'eligible_items': [{'id': 'r1', 'source': '媒体', 'claims': claims}]}
    decisions = [{'id': 'r1', 'decision': 'eligible', 'reason': '原生审核',
        'claims': [{k: v for k, v in claim.items() if k not in ('index', 'original_excerpt')} for claim in claims]}]
    response = {'heading': '中心判断', 'selected': [{'key': 'k1', 'heading': '共同判断',
        'claim_ids': ['c1'], 'thin_reason': '仅一个真实主体'}],
        'excluded': [{'id': 'c2', 'reason': '与另一保留判断实质重复'}]}
    return request, decisions, response


def test_flat_protocol_preserves_all_existing_claims_and_ids():
    request, decisions, response = fixture()
    originals = copy.deepcopy((request, decisions, response))
    flat, mapping = flat_packet(request)
    assert [row['claim'] for row in flat['candidates']] == [row['claim'] for row in decisions[0]['claims']]
    assert mapping == {'c1': ('r1', 0), 'c2': ('r1', 1)}
    result = restore_synthesis(decisions, mapping, response)
    assert result['items'][0]['claims'] == [{**decisions[0]['claims'][0], 'cluster': 'k1'}]
    assert result['transport_repairs'][-1]['native_response'] == response
    assert (request, decisions, response) == originals


def test_selection_retains_declared_meeting_context_without_copying_source_excerpts():
    request, _, _ = fixture()
    request.update(period={'start': '2026-01-01'}, agenda_topics=['议题甲', '议题乙'],
                   report_agenda='本期会议的原始议程')
    transport, _ = flat_packet(request)
    for key in ('period', 'agenda_topics', 'report_agenda'):
        assert transport[key] == request[key]
    assert all('original_excerpt' not in row for row in transport['candidates'])
    transport['agenda_topics'].append('不得改变原始输入')
    assert request['agenda_topics'] == ['议题甲', '议题乙']


def test_duplicate_feedback_names_the_exact_id_and_both_assignments():
    request, decisions, response = fixture()
    _, mapping = flat_packet(request)
    response['excluded'][0]['id'] = 'c1'
    with pytest.raises(ValueError) as caught:
        restore_synthesis(decisions, mapping, response)
    assert 'repeated claim ID: c1' in str(caught.value)
    assert 'first_assignment=' in str(caught.value)
    assert 'repeated_assignment=' in str(caught.value)


@pytest.mark.parametrize('fault', ['missing', 'duplicate', 'unknown', 'no_reason', 'empty_group', 'extra_field'])
def test_flat_protocol_rejects_ambiguous_or_incomplete_native_choices(fault):
    request, decisions, response = fixture()
    _, mapping = flat_packet(request)
    if fault == 'missing':
        response['excluded'] = []
    elif fault == 'duplicate':
        response['excluded'][0]['id'] = 'c1'
    elif fault == 'unknown':
        response['selected'][0]['claim_ids'] = ['new']
    elif fault == 'no_reason':
        response['excluded'][0]['reason'] = ''
    elif fault == 'empty_group':
        response['selected'][0]['claim_ids'] = []
    else:
        response['invented_claims'] = ['新观点']
    with pytest.raises(ValueError):
        restore_synthesis(decisions, mapping, response)


def test_distinct_claims_by_same_person_remain_separately_traceable():
    request, decisions, response = fixture()
    _, mapping = flat_packet(request)
    response['selected'][0]['claim_ids'].append('c2')
    response['excluded'] = []
    result = restore_synthesis(decisions, mapping, response)
    assert len(result['items'][0]['claims']) == 2
    assert [r['claim'] for r in result['items'][0]['claims']] == [r['claim'] for r in decisions[0]['claims']]


def test_native_reserve_retains_valid_original_claim_outside_formal_prose():
    request, decisions, response = fixture()
    _, mapping = flat_packet(request)
    response['reserved'] = response.pop('excluded')
    response['excluded'] = []
    original = copy.deepcopy(decisions)
    result = restore_synthesis(decisions, mapping, response,
                               {'allow_reserve': True, 'max_independent_voices': 1})
    claims = result['items'][0]['claims']
    assert result['items'][0]['decision'] == 'eligible'
    assert claims[1]['formal_use'] == 'reserve'
    assert claims[1]['claim'] == original[0]['claims'][1]['claim']
    assert claims[1]['reserve_reason']
    assert decisions == original


def test_voice_cap_counts_people_not_claims_and_does_not_silently_truncate():
    request, decisions, response = fixture()
    _, mapping = flat_packet(request)
    response['selected'][0]['claim_ids'].append('c2')
    response['excluded'] = []
    assert len(restore_synthesis(decisions, mapping, response,
        {'max_independent_voices': 1})['items'][0]['claims']) == 2
    decisions[0]['claims'][1]['speaker'] = '另一专家'
    with pytest.raises(ValueError, match='2 independent voices'):
        restore_synthesis(decisions, mapping, response, {'max_independent_voices': 1})


@pytest.mark.parametrize('policy', [None, {'allow_reserve': False}])
def test_reserve_requires_explicit_contract(policy):
    request, decisions, response = fixture()
    _, mapping = flat_packet(request)
    response['reserved'] = response.pop('excluded')
    response['excluded'] = []
    with pytest.raises(ValueError, match='explicit bounded'):
        restore_synthesis(decisions, mapping, response, policy)


def test_duplicate_ownership_repair_changes_only_native_selected_destination():
    request, decisions, response = fixture()
    transport, mapping = flat_packet(request)
    response['reserved'] = [{'id': 'c1', 'reason': '正文之外的有效备选'}]
    before = copy.deepcopy(response)
    ownership = duplicate_assignment_request(transport, response)
    assert len(ownership['conflicts']) == 1
    fixed = apply_duplicate_assignments(response, ownership, {'choices': [{'id': 'c1', 'option': 0}]})
    result = restore_synthesis(decisions, mapping, fixed, {'allow_reserve': True})
    assert len(result['items'][0]['claims']) == 1
    assert fixed['selected'] == before['selected'] and fixed['excluded'] == before['excluded']
    assert fixed['reserved'] == [] and response == before


@pytest.mark.parametrize('choices', [[], [{'id': 'c1', 'option': True}],
    [{'id': 'c1', 'option': 2}], [{'id': 'other', 'option': 0}]])
def test_duplicate_ownership_repair_rejects_missing_or_invented_choices(choices):
    request, _, response = fixture()
    transport, _ = flat_packet(request)
    response['reserved'] = [{'id': 'c1', 'reason': '备选'}]
    ownership = duplicate_assignment_request(transport, response)
    with pytest.raises(ValueError):
        apply_duplicate_assignments(response, ownership, {'choices': choices})


def test_duplicate_only_repair_does_not_hide_missing_or_foreign_ids():
    request, _, response = fixture()
    transport, _ = flat_packet(request)
    response['selected'][0]['claim_ids'].append('c1')
    response['excluded'] = []
    assert duplicate_assignment_request(transport, response) is None


def test_native_ownership_reply_is_recognized_by_real_transport_parser():
    import json
    from run_cwh_inline_review import response_object
    answer = {'choices': [{'id': 'c31', 'option': 0}, {'id': 'c33', 'option': 0}]}
    assert response_object(json.dumps({'type': 'result', 'result': json.dumps(answer)})) == answer


@pytest.mark.parametrize('fault', ['missing_pair', 'duplicate_pair', 'foreign_pair', 'boolean_index'])
def test_host_mapping_cannot_silently_lose_even_excluded_claims(fault):
    request, decisions, response = fixture()
    _, mapping = flat_packet(request)
    if fault == 'missing_pair':
        del mapping['c2']
    elif fault == 'duplicate_pair':
        mapping['c2'] = mapping['c1']
    elif fault == 'foreign_pair':
        mapping['c2'] = ('other', 1)
    else:
        mapping['c1'] = ('r1', False)
    with pytest.raises(ValueError, match='every original claim'):
        restore_synthesis(decisions, mapping, response)


def test_all_excluded_is_explicit_and_preserves_every_original_judgment():
    request, decisions, response = fixture()
    _, mapping = flat_packet(request)
    response['selected'] = []
    response['excluded'].append({'id': 'c1', 'reason': '仅转述会议事实'})
    result = restore_synthesis(decisions, mapping, response)
    assert result['items'][0]['decision'] == 'excluded'
    assert result['items'][0]['claims'] == []
    assert result['transport_repairs'][0]['original_batch_decisions'] == decisions


@pytest.mark.parametrize('fault', ['duplicate_article', 'empty_claims', 'unordered_index', 'empty_text'])
def test_invalid_original_packet_fails_before_model_call(fault):
    request, _, _ = fixture()
    if fault == 'duplicate_article':
        request['eligible_items'].append(copy.deepcopy(request['eligible_items'][0]))
    elif fault == 'empty_claims':
        request['eligible_items'][0]['claims'] = []
    elif fault == 'unordered_index':
        request['eligible_items'][0]['claims'][1]['index'] = 0
    else:
        request['eligible_items'][0]['claims'][0]['claim'] = ''
    with pytest.raises(ValueError):
        flat_packet(request)
