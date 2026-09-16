import copy
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_claim_synthesis import voice_reserve_request, apply_voice_reserves


def fixture():
    packet = {'topic': '动态议题', 'formal_selection': {'allow_reserve': True, 'max_independent_voices': 2},
              'candidates': [{'id': f'c{i}', 'speaker': name, 'claim': f'原观点{i}'}
                             for i, name in enumerate(['主体甲', '主体乙', '主体丙', '主体丙'], 1)]}
    response = {'heading': '原标题', 'selected': [
        {'key': 'k1', 'heading': '原分组一', 'claim_ids': ['c1', 'c3']},
        {'key': 'k2', 'heading': '原分组二', 'claim_ids': ['c2', 'c4']}], 'excluded': [], 'reserved': []}
    return packet, response


def test_moves_all_selected_claims_of_explicit_native_subject_only():
    packet, response = fixture()
    before = copy.deepcopy(response)
    request = voice_reserve_request(packet, response)
    assert request['minimum_reserve_voices'] == 1
    result = apply_voice_reserves(response, request, {'choices': [{'id': 'v3', 'reason': '同类论点已覆盖'}]})
    assert [g['claim_ids'] for g in result['selected']] == [['c1'], ['c2']]
    assert {row['id'] for row in result['reserved']} == {'c3', 'c4'}
    assert result['heading'] == before['heading'] and response == before
    assert result['excluded'] == before['excluded']


@pytest.mark.parametrize('choices', [[], [{'id': 'unknown', 'reason': '理由'}],
    [{'id': 'v3', 'reason': ''}], [{'id': 'v3', 'reason': '理由', 'claim': '改写'}],
    [{'id': 'v3', 'reason': '理由'}, {'id': 'v3', 'reason': '重复'}],
    [{'id': f'v{i}', 'reason': '全删'} for i in range(1, 4)]])
def test_rejects_invalid_or_emptying_choices(choices):
    packet, response = fixture()
    with pytest.raises(ValueError):
        apply_voice_reserves(response, voice_reserve_request(packet, response), {'choices': choices})


def test_no_host_selection_under_cap_or_when_reserves_not_allowed():
    packet, response = fixture()
    packet['formal_selection']['max_independent_voices'] = 3
    assert voice_reserve_request(packet, response) is None
    packet['formal_selection'] = {'allow_reserve': False, 'max_independent_voices': 1}
    assert voice_reserve_request(packet, response) is None


def test_native_repair_uses_one_compact_choice_and_preserves_actual_runs(tmp_path):
    from cwh_author_batches import native_topic_synthesis
    packet, response = fixture()
    decisions = [{'id': 'r1', 'decision': 'eligible', 'reason': '原生判断',
                  'claims': [{'speaker': row['speaker'], 'claim': row['claim']} for row in packet['candidates']]}]
    request = {'topic': packet['topic'], 'formal_selection': packet['formal_selection'],
               'eligible_items': [{'id': 'r1', 'claims': [dict(row, index=i)
                   for i, row in enumerate(decisions[0]['claims'])]}]}
    calls = []
    def model(payload, prompt, command, workspace, label, timeout, **kwargs):
        calls.append((payload, label, timeout))
        return (response if len(calls) == 1 else {'choices': [{'id': 'v3', 'reason': '已覆盖同类分析'}]}), {
            'session_id': str(len(calls)), 'seconds': 2}
    result, run = native_topic_synthesis(request, decisions, [], tmp_path, 90, model, reuse_cache=False)
    assert len(calls) == 2 and calls[1][1] == 'synthesis-voice-reserve'
    assert calls[1][2] <= 45 and run['seconds'] == 4
    assert sum(c.get('formal_use') == 'reserve' for c in result['items'][0]['claims']) == 2
    assert result['transport_repairs'][-1]['kind'] == 'native_voice_reserve_repair'
