"""No native model calls: verify flat protocol conversion retains original claims."""
import copy
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from cwh_claim_synthesis import flat_packet, restore_synthesis


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
