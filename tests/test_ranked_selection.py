"""Mechanical native-priority selection retains every original claim in audit."""
import copy
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_ranked_selection import ranked_selection
from cwh_claim_synthesis import flat_packet, restore_synthesis, remove_exact_input_echoes
from test_flat_claim_synthesis import fixture


def sample():
    return {'formal_selection': {'allow_reserve': True, 'max_independent_voices': 2},
        'candidates': [{'id': f'c{i}', 'speaker': name, 'source': '原媒体'}
                       for i, name in enumerate(['甲', '乙', '丙', '甲'], 1)]}, {
        'heading': '本题判断', 'selected': [{'key': 'k1', 'heading': '共同判断',
            'claim_ids': ['c2', 'c1', 'c3', 'c4']}]}


def test_priority_cap_retains_multiple_claims_of_same_subject_and_all_reserves():
    packet, response = sample()
    original = copy.deepcopy((packet, response))
    result = ranked_selection(packet, response)
    assert result['selected'][0]['claim_ids'] == ['c2', 'c1']
    assert result['reserved'][0]['id'] == 'c3'
    assert result['reserved'][0]['reason'].startswith('ranked_subject_cap:')
    assert result['transport_repairs'][0]['native_response'] == response
    assert (packet, response) == original


def test_same_subject_distinct_groups_remain_traceable():
    packet, response = sample()
    response['selected'] = [dict(key='k1', heading='一', claim_ids=['c1']),
                            dict(key='k2', heading='二', claim_ids=['c4'])]
    result = ranked_selection(packet, response)
    assert [row['claim_ids'] for row in result['selected']] == [['c1'], ['c4']]


def test_repeated_groups_do_not_consume_formal_group_slots():
    packet, response = sample()
    response['selected'] *= 7
    result = ranked_selection(packet, response)
    assert len(result['selected']) == 1
    assert result['transport_repairs'][0]['native_response'] == response


def test_excess_native_priority_groups_are_reserved_without_semantic_merge():
    packet = {'formal_selection': {'allow_reserve': True, 'max_independent_voices': 12},
              'candidates': [{'id': f'c{i}', 'speaker': f'主体{i}', 'source': '原媒体'} for i in range(8)]}
    response = {'selected': [{'key': f'k{i}', 'heading': f'原判断{i}', 'claim_ids': [f'c{i}']}
                             for i in range(8)]}
    original = copy.deepcopy((packet, response))
    result = ranked_selection(packet, response)
    assert result['selected'] == response['selected'][:6]
    assert [row['id'] for row in result['reserved']] == ['c6', 'c7']
    assert all(row['reason'].startswith('ranked_cluster_cap:') for row in result['reserved'])
    assert result['excluded'] == []
    assert (packet, response) == original
    response['selected'][-1]['claim_ids'] = ['unknown']
    with pytest.raises(ValueError, match='unknown claim ID'):
        ranked_selection(packet, response)


def test_unlisted_is_reserve_not_invalid_evidence():
    packet, response = sample()
    response['selected'][0]['claim_ids'] = ['c4']
    result = ranked_selection(packet, response)
    assert result['excluded'] == []
    assert [row['id'] for row in result['reserved']] == ['c1', 'c2', 'c3']
    assert all('未判定证据无效' in row['reason'] for row in result['reserved'])


def test_duplicate_uses_explicit_first_group_priority_with_audit():
    packet, response = sample()
    response['selected'] = [dict(key='k1', heading='一', claim_ids=['c1']),
                            dict(key='k2', heading='二', claim_ids=['c1', 'c2'])]
    result = ranked_selection(packet, response)
    assert result['selected'][1]['claim_ids'] == ['c2']
    assert result['transport_repairs'][0]['duplicate_ids'] == ['c1']


def test_conflicting_native_dispositions_never_enter_formal_prose():
    packet, response = sample()
    response['excluded'] = [{'id': 'c1', 'reason': '仅会议原文'}]
    result = ranked_selection(packet, response)
    assert 'c1' not in result['selected'][0]['claim_ids']
    assert result['reserved'][0]['id'] == 'c1'
    assert 'conflict' in result['reserved'][0]['reason']


@pytest.mark.parametrize('fault', ['unknown', 'no_policy', 'bad_cap', 'no_identity', 'bad_reason'])
def test_invalid_selection_not_silently_accepted(fault):
    packet, response = sample()
    if fault == 'unknown':
        response['selected'][0]['claim_ids'] = ['c999']
    elif fault == 'no_policy':
        packet['formal_selection']['allow_reserve'] = False
    elif fault == 'bad_cap':
        packet['formal_selection']['max_independent_voices'] = True
    elif fault == 'no_identity':
        packet['candidates'][1].update(speaker=None, source=None)
    else:
        response['reserved'] = [{'id': 'c1', 'reason': ''}]
    with pytest.raises(ValueError):
        ranked_selection(packet, response)


def test_restore_preserves_exact_original_claims_and_ranked_audit():
    request, decisions, response = fixture()
    request['formal_selection'] = {'allow_reserve': True, 'max_independent_voices': 1}
    response.pop('excluded')
    transport, mapping = flat_packet(request)
    original = copy.deepcopy(decisions)
    result = restore_synthesis(decisions, mapping, ranked_selection(transport, response), request['formal_selection'])
    assert result['items'][0]['claims'][1]['formal_use'] == 'reserve'
    assert [row['claim'] for row in result['items'][0]['claims']] == [row['claim'] for row in decisions[0]['claims']]
    assert result['transport_repairs'][-1]['native_response']['transport_repairs'][0]['native_response'] == response
    assert decisions == original


def test_equal_input_metadata_does_not_discard_completed_native_grouping():
    request, decisions, response = fixture()
    request.update(topic='本期议题', period={'start': '2030-01-01', 'end': '2030-01-03'},
                   agenda_topics=['本期议题'], report_agenda='本期报告会议')
    request['formal_selection'] = {'allow_reserve': True, 'max_independent_voices': 12}
    transport, mapping = flat_packet(request)
    response.pop('excluded')
    response.update({key: copy.deepcopy(transport[key]) for key in
                     ('topic', 'period', 'agenda_topics', 'report_agenda', 'formal_selection')})
    before = copy.deepcopy(response)
    ranked = ranked_selection(transport, response)
    result = restore_synthesis(decisions, mapping, ranked, request['formal_selection'], transport=transport)
    assert result['clusters'][0]['heading'] == response['selected'][0]['heading']
    assert response == before
    audit = result['transport_repairs'][-1]['native_response']['transport_repairs']
    assert audit[-1]['kind'] == 'removed_exact_input_metadata_echoes'
    assert set(audit[-1]['removed_fields']) == {'period', 'topic', 'agenda_topics', 'report_agenda', 'formal_selection'}


@pytest.mark.parametrize('key', ['period', 'topic', 'agenda_topics', 'report_agenda', 'formal_selection'])
def test_changed_metadata_echo_cannot_be_silently_ignored(key):
    with pytest.raises(ValueError, match='differs from input'):
        remove_exact_input_echoes({key: '真实输入'}, {key: '被模型改写的输入'})
    with pytest.raises(ValueError, match='differs from input'):
        remove_exact_input_echoes({}, {key: '额外生成的输入'})


def test_unknown_fields_and_native_decisions_are_never_removed_as_echoes():
    response = {'selected': [{'key': 'k1', 'claim_ids': ['c1']}], 'unknown': 'not an allowed echo'}
    assert remove_exact_input_echoes({}, response) == response
