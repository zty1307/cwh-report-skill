import copy
import time
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_author_batches import native_topic_synthesis, synthesis_packet
from cwh_editorial_selection import author_layout_shortfalls, repair_author_layout_once
from cwh_host_research import HostModelError


def inputs():
    packet = {'topic': '公共服务', 'items': [
        {'id': f'r{i}', 'content': f'完整原文{i}。', 'source': f'媒体{i}'} for i in range(3)],
        'formal_selection': {'allow_reserve': True, 'max_independent_voices': 12,
                             'selection_mode': 'ranked_positive_v1'}}
    decisions = [{'id': f'r{i}', 'decision': 'eligible', 'reason': '独立判断',
                  'source': f'媒体{i}', 'claims': [
                      {'speaker': f'主体{i}', 'speaker_type': 'media', 'role': '',
                       'claim': f'观点{i}的条件与机制不可改写。', 'quote': f'完整原文{i}。',
                       'cluster': 'temporary'}]} for i in range(3)]
    response = {'heading': '认可服务建设', 'selected': [
        {'key': f'k{i}', 'heading': f'认可条件{i}', 'claim_ids': [f'c{i+1}']}
        for i in range(3)], 'shortfall_reason': '', 'single_cluster_reason': ''}
    return synthesis_packet(packet, decisions), decisions, response


def test_native_regroup_preserves_every_selected_claim_and_original_input(tmp_path):
    request, decisions, response = inputs()
    original = copy.deepcopy(decisions)
    patch = {**response, 'selected': [{'key': 'k1', 'heading': '认可共同条件',
                                      'claim_ids': ['c1', 'c2', 'c3']}],
             'single_cluster_reason': '三个主体确有共同判断'}
    calls = []
    def model(packet, prompt, command, workspace, label, timeout, reuse_cache):
        calls.append((label, timeout, reuse_cache, copy.deepcopy(packet)))
        return (response if len(calls) == 1 else patch), {'session_id': label, 'seconds': 1}
    result, run = native_topic_synthesis(request, decisions, [], tmp_path, 90, model, reuse_cache=False)
    assert [row[0] for row in calls] == ['topic-synthesis', 'synthesis-layout-repair']
    assert calls[1][1] <= 45 and calls[1][2] is False
    assert decisions == original
    assert author_layout_shortfalls(result) == []
    assert [c['claim'] for x in result['items'] for c in x.get('claims', [])] == [
        c['claim'] for x in original for c in x['claims']]
    assert run['synthesis_initial_run']['session_id'] == 'topic-synthesis'
    assert run['seconds'] == 2


@pytest.mark.parametrize('failure', ['unchanged', 'bad_id', 'timeout'])
def test_unsuccessful_regroup_keeps_all_original_selected_claims(tmp_path, failure):
    request, decisions, response = inputs()
    calls = []
    def model(packet, prompt, command, workspace, label, timeout, reuse_cache):
        calls.append(label)
        if len(calls) == 2:
            if failure == 'timeout':
                raise HostModelError('timeout', 124, run={'session_id': label, 'seconds': 3})
            if failure == 'bad_id':
                return {**response, 'selected': [{'key': 'k1', 'heading': '认可条件',
                                                 'claim_ids': ['missing']}]}, {'seconds': 1}
        return response, {'session_id': label, 'seconds': 1}
    result, run = native_topic_synthesis(request, decisions, [], tmp_path, 90, model, reuse_cache=False)
    assert len(calls) == 2
    assert len(result['clusters']) == 3
    assert len(author_layout_shortfalls(result)) == 3
    assert len([c for x in result['items'] for c in x.get('claims', [])
                if c.get('formal_use') != 'reserve']) == 3
    assert run['editorial_layout_repair']['status'] == 'pending_original_selection_retained'


def test_no_remaining_budget_does_not_start_optional_model_call(tmp_path):
    result = {'clusters': [{'key': 'a'}, {'key': 'b'}], 'items': [
        {'decision': 'eligible', 'claims': [{'speaker': key, 'cluster': key}]}
        for key in ['a', 'b']]}
    def forbidden(*args, **kwargs):
        pytest.fail('No budget for optional model call')
    retained, run = repair_author_layout_once(result, {}, {}, forbidden, '', [], tmp_path,
        time.monotonic() + 1, forbidden, {'seconds': 0})
    assert retained['items'] == result['items']
    assert run['editorial_layout_repair']['status'] == 'pending_no_budget'


def test_permission_failure_is_not_disguised_as_success(tmp_path):
    request, decisions, response = inputs()
    calls = []
    def model(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise HostModelError('permission denied', 1, category='permission')
        return response, {'session_id': 'first', 'seconds': 1}
    with pytest.raises(HostModelError):
        native_topic_synthesis(request, decisions, [], tmp_path, 90, model, reuse_cache=False)
    assert len(calls) == 2
