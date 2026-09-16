"""Preserve distinct judgments; a person's name is not a one-claim quota."""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_author_batches import apply_synthesis, native_topic_synthesis


def fixture():
    claims = [{'speaker': '专家甲', 'role': '研究员', 'speaker_type': 'named_person',
               'claim': '原文不同判断' + str(i), 'quote_range': [i+1, i+1]} for i in range(2)]
    decisions = [{'id': 'r1', 'decision': 'eligible', 'reason': '原生判断', 'claims': claims}]
    response = {'heading': '中心判断', 'clusters': [{'key': 'k1', 'heading': '判断一'},
        {'key': 'k2', 'heading': '判断二'}], 'items': [{'id': 'r1', 'decision': 'eligible',
        'reason': '保留', 'claim_clusters': [{'index': 0, 'cluster': 'k1'}, {'index': 1, 'cluster': 'k2'}]}]}
    return decisions, response


def test_distinct_claims_by_same_person_preserved_without_mutating_original():
    decisions, response = fixture()
    original = copy.deepcopy(decisions)
    result = apply_synthesis(decisions, response)
    assert [r['claim'] for r in result['items'][0]['claims']] == [r['claim'] for r in decisions[0]['claims']]
    assert decisions == original


@pytest.mark.parametrize('field,value', [('speaker', '专家乙'), ('role', '另一机构教授')])
def test_different_named_identities_not_mechanically_merged(field, value):
    decisions, response = fixture()
    decisions[0]['claims'][1][field] = value
    assert len(apply_synthesis(decisions, response)['items'][0]['claims']) == 2


def test_distinct_judgments_do_not_trigger_needless_native_repair(tmp_path):
    decisions, response = fixture()
    calls = []
    def model(request, prompt, command, workspace, label, timeout, reuse_cache):
        calls.append(label)
        return response, {'session_id': label, 'seconds': 1}
    result, run = native_topic_synthesis({'eligible_items': []}, decisions, [], tmp_path, 90, model, reuse_cache=False)
    assert calls == ['topic-synthesis']
    assert result['items'][0]['claims'][0]['claim'] == decisions[0]['claims'][0]['claim']
    assert len(result['items'][0]['claims']) == 2


def test_mirrored_claims_preserved_for_deterministic_compiler_dedup():
    decisions, response = fixture()
    mirror = copy.deepcopy(decisions[0])
    mirror['id'] = 'w1'
    decisions.append(mirror)
    patch = copy.deepcopy(response['items'][0])
    patch['id'] = 'w1'
    response['items'].append(patch)
    original = copy.deepcopy(decisions)
    result = apply_synthesis(decisions, response)
    assert len(result['items']) == 2
    assert decisions == original


def test_different_people_can_share_exactly_the_same_wording():
    decisions, response = fixture()
    decisions[0]['claims'][1]['speaker'] = '专家乙'
    decisions[0]['claims'][1]['claim'] = decisions[0]['claims'][0]['claim']
    assert len(apply_synthesis(decisions, response)['items'][0]['claims']) == 2
