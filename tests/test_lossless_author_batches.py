import copy
import json
from pathlib import Path
import sys
import time
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_author_batches import partition_author_packet, synthesis_packet, apply_synthesis, synthesis_prompt, native_topic_synthesis
import run_cwh_compiled_worker as worker
from cwh_host_research import HostModelError
import cwh_author_batches as author_batches
from cwh_claim_synthesis import flat_packet


def flat_response():
    return {'heading': '认可动态判断', 'selected': [
        {'key': 'k1', 'heading': '认可判断甲', 'claim_ids': ['c1']},
        {'key': 'k2', 'heading': '建议判断乙', 'claim_ids': ['c2'],
         'thin_reason': '当前只有一个独立主体'}], 'excluded': []}


def fixture():
    packet = {'topic': '动态议题', 'period': {'start': '2026-01-01', 'end': '2026-01-02'},
        'items': [{'id': 'r1', 'content': '原文甲。原文乙。', 'url': 'https://example.test/a'},
                  {'id': 'r2', 'content': '事实通知。', 'url': 'https://example.test/b'}]}
    decisions = [{'id': 'r1', 'decision': 'eligible', 'reason': '有独立判断', 'source': '测试来源',
        'claims': [{'speaker': '主体甲', 'role': '职务甲', 'speaker_type': 'expert',
                    'claim': '判断甲', 'quote_range': [1, 1], 'cluster': 'temporary'},
                   {'speaker': '主体乙', 'role': '', 'speaker_type': 'expert',
                    'claim': '判断乙', 'quote_range': [2, 2], 'cluster': 'temporary'}]},
                 {'id': 'r2', 'decision': 'excluded', 'reason': '只有事实', 'claims': []}]
    response = {'heading': '认可动态判断', 'clusters': [{'key': 'k1', 'heading': '认可判断甲'},
                  {'key': 'k2', 'heading': '建议判断乙', 'thin_reason': '当前只有一个独立主体'}],
        'items': [{'id': 'r1', 'decision': 'eligible', 'reason': '保留不同实质判断',
                   'claim_clusters': [{'index': 0, 'cluster': 'k1'}, {'index': 1, 'cluster': 'k2'}]}]}
    return packet, decisions, response


def test_partition_preserves_all_original_segments_and_order():
    packet = {'topic': '通用题', 'items': [{'id': f'r{i}', 'segments': [{'id': f'p{i}/1', 'text': '原文。'*30}]}
                                         for i in range(9)]}
    original = copy.deepcopy(packet)
    groups = partition_author_packet(packet, max_characters=600, max_items=3)
    assert len(groups) > 1
    assert [item for group in groups for item in group['items']] == original['items']
    assert all(len(json.dumps(group, ensure_ascii=False, separators=(',', ':'))) <= 600 for group in groups)
    assert packet == original


def test_default_batches_bound_work_for_all_models_without_truncating():
    packet = {'topic': '通用题', 'items': [{'id': f'r{i}', 'content': '完整原文' * 900} for i in range(8)]}
    groups = partition_author_packet(packet)
    assert max(len(group['items']) for group in groups) <= 3
    assert [item for group in groups for item in group['items']] == packet['items']
    assert all(len(json.dumps(group, ensure_ascii=False, separators=(',', ':'))) <= 20000 for group in groups)


def test_synthesis_feedback_is_routed_without_dropping_article_errors():
    from cwh_author_batches import is_synthesis_feedback
    assert is_synthesis_feedback('[议题] Formal selection has 13 independent voices')
    assert is_synthesis_feedback('[议题] Flat synthesis repeated claim ID: c1')
    assert not is_synthesis_feedback('[议题] speaker missing from original quote')
    assert not is_synthesis_feedback('[议题] contradictory interpretation without source support')


def test_literal_claim_feedback_only_invalidates_the_affected_batch():
    from cwh_author_batches import article_feedback_for_ids
    error = '[动态议题] w11 claim[0] role missing from selected quote'
    assert article_feedback_for_ids([error], ['r1', 'r2']) == []
    assert article_feedback_for_ids([error], ['w10', 'w11']) == [error]
    unscoped = 'Unknown article coverage problem'
    assert article_feedback_for_ids([unscoped], ['r1']) == [unscoped]
    assert article_feedback_for_ids(['Formal selection has 13 independent voices'], ['r1']) == []


def test_synthesis_feedback_changes_selection_packet_only():
    packet, decisions, _ = fixture()
    request = synthesis_packet(packet, decisions)
    before, mapping = flat_packet(request)
    request['synthesis_validation_feedback'] = ['Formal selection has 13 independent voices']
    after, after_mapping = flat_packet(request)
    assert mapping == after_mapping
    assert after.pop('synthesis_validation_feedback') == request['synthesis_validation_feedback']
    assert after == before


def test_many_cached_batches_can_resume_without_impossible_fixed_reservations(monkeypatch, tmp_path):
    packet = {'topic': '动态议题', 'items': [{'id': f'r{i}', 'content': '原文'} for i in range(20)]}
    groups = [{'items': [row]} for row in packet['items']]
    deadlines = []
    def cached(packets, prompt, command, workspace, deadline, **kwargs):
        remaining = deadline - time.monotonic()
        deadlines.append(remaining)
        assert 15 < remaining < 90
        return [{'items': [{'id': packets[0]['items'][0]['id'], 'decision': 'excluded',
                            'reason': '原生缓存判断', 'claims': []}]}], {'seconds': 0, 'cache_reused': True}
    monkeypatch.setattr(worker, 'author_topic_decisions', cached)
    result, run = worker.review_author_article_batches(packet, groups, '', [], tmp_path,
        time.monotonic() + 90, reuse_cache=True, feedback=[], maximum_request_seconds=90)
    assert len(deadlines) == len(result['items']) == 20
    assert run['synthesis_run']['model_invoked'] is False


def test_single_oversized_article_is_not_truncated():
    packet = {'items': [{'id': 'a', 'segments': [{'id': 1, 'text': '完整。'*1000}]}]}
    assert partition_author_packet(packet, max_characters=100) == [packet]
    with pytest.raises(ValueError, match='positive'):
        partition_author_packet(packet, max_characters=0)


def test_synthesis_receives_every_existing_claim_and_exact_quotes():
    packet, decisions, _ = fixture()
    request = synthesis_packet(packet, decisions)
    assert [claim['original_excerpt'] for claim in request['eligible_items'][0]['claims']] == ['原文甲。', '原文乙。']
    assert request['previously_excluded_items'][0]['id'] == 'r2'
    assert 'content' not in json.dumps(request, ensure_ascii=False)
    assert '不是独立审核' in synthesis_prompt()
    assert '"quote_range"' not in synthesis_prompt()
    decisions[0]['claims'][0]['quote_range'] = [4, 5]
    with pytest.raises(ValueError, match='ordered pair'):
        synthesis_packet(packet, decisions)


def test_synthesis_changes_only_native_assignments_and_keeps_audit():
    _, decisions, response = fixture()
    original = copy.deepcopy(decisions)
    result = apply_synthesis(decisions, response)
    for index, claim in enumerate(result['items'][0]['claims']):
        assert {key: value for key, value in claim.items() if key != 'cluster'} == {
            key: value for key, value in original[0]['claims'][index].items() if key != 'cluster'}
    assert result['items'][1] == original[1]
    assert decisions == original
    assert result['transport_repairs'][-1]['original_batch_decisions'] == original


def test_synthesis_uses_shared_heading_targets_and_style_not_an_author_schema(monkeypatch):
    rules = copy.deepcopy(author_batches.writing_rules())
    rules['viewpoint']['topic_heading_cjk_range'] = [13, 27]
    rules['viewpoint']['cluster_heading_cjk_range'] = [11, 25]
    monkeypatch.setattr(author_batches, 'writing_rules', lambda: rules)
    prompt = synthesis_prompt()
    assert '一级heading目标13—27个汉字' in prompt
    assert '簇heading目标11—25个汉字' in prompt
    assert all(rule in prompt for rule in rules['viewpoint']['heading_rules'])
    assert '不能为压短丢掉关键对象或限定' in prompt
    assert '"quote_range"' not in prompt


@pytest.mark.parametrize('fault', ['missing_id', 'new_claim', 'missing_claim', 'duplicate_claim', 'empty_cluster', 'wrong_cluster'])
def test_synthesis_rejects_loss_or_unauthorized_semantic_changes(fault):
    _, decisions, response = fixture()
    if fault == 'missing_id':
        response['items'] = []
    elif fault == 'new_claim':
        response['items'][0]['claims'] = [{'claim': '凭空新增'}]
    elif fault == 'missing_claim':
        response['items'][0]['claim_clusters'].pop()
    elif fault == 'duplicate_claim':
        response['items'][0]['claim_clusters'][1]['index'] = 0
    elif fault == 'empty_cluster':
        response['clusters'].append({'key': 'empty', 'heading': '没有支持'})
    else:
        response['items'][0]['claim_clusters'][0]['cluster'] = 'unknown'
    with pytest.raises(ValueError):
        apply_synthesis(decisions, response)


def test_native_global_exclusion_is_preserved_not_host_semantic_choice():
    _, decisions, response = fixture()
    response['items'][0].update(decision='duplicate', reason='全池有同主体同一判断', claim_clusters=[])
    response['clusters'] = []
    result = apply_synthesis(decisions, response)
    assert result['items'][0]['decision'] == 'duplicate'
    assert result['items'][0]['claims'] == []
    assert result['transport_repairs'][-1]['original_batch_decisions'][0]['decision'] == 'eligible'


def test_explicit_native_claim_exclusion_has_reason_and_preserves_original_audit():
    _, decisions, response = fixture()
    response['items'][0]['claim_clusters'][1] = {'index': 1, 'decision': 'exclude',
                                               'cluster': None, 'reason': '与另一个已选主体同一实质判断'}
    response['clusters'].pop()
    value = apply_synthesis(decisions, response)
    assert len(value['items'][0]['claims']) == 1
    assert value['items'][0]['claims'][0]['claim'] == decisions[0]['claims'][0]['claim']
    assert len(value['transport_repairs'][-1]['original_batch_decisions'][0]['claims']) == 2
    response['items'][0]['claim_clusters'][1]['reason'] = ''
    with pytest.raises(ValueError, match='exclusion reason'):
        apply_synthesis(decisions, response)


def test_oversized_author_runs_sequential_full_batches_then_native_synthesis(monkeypatch, tmp_path):
    text = '完整原文。'*3000
    packet = {'topic': '动态议题', 'items': [{'id': f'r{i}', 'content': text, 'origin': 'raw_monitoring'} for i in range(8)]}
    calls = []
    def model(request, prompt, command, workspace, label, timeout, reuse_cache):
        assert 0 < timeout <= (90 if label == 'topic-synthesis' else 180)
        calls.append((copy.deepcopy(request), label))
        if label == 'topic-synthesis':
            assert 'candidates' in request
            return {'heading': '建议优化配置', 'selected': [{'key': 'all', 'heading': '建议协调实际需求',
                'claim_ids': [row['id'] for row in request['candidates']]}], 'excluded': []}, {'session_id': label, 'seconds': 1}
        assert all(''.join(seg['text'] for seg in row['segments']) == text for row in request['items'])
        assert all(row['id'] in prompt for row in request['items'])
        assert '“items”' not in prompt  # no host answers embedded
        return {'heading': '临时标题', 'clusters': [{'key': 'temporary', 'heading': '临时判断'}],
            'items': [{'id': row['id'], 'decision': 'eligible', 'reason': '独立建议',
                'claims': [{'speaker': row['id'], 'speaker_type': 'media_voice',
                            'claim': '建议优化实际配置', 'quote_range': [1, 1], 'cluster': 'temporary'}]}
                for row in request['items']]}, {'session_id': label, 'seconds': 1}
    monkeypatch.setattr(worker, 'semantic_json', model)
    values, run = worker.author_topic_decisions([packet], '规则', [], tmp_path, time.monotonic()+500, reuse_cache=False)
    assert [item['id'] for item in values[0]['items']] == [row['id'] for row in packet['items']]
    batches = calls[:-1]
    assert len(batches) > 1 and calls[-1][1] == 'topic-synthesis'
    assert [row['id'] for request, _ in batches for row in request['items']] == [row['id'] for row in packet['items']]
    assert run['topic_runs'][0]['transport'] == 'lossless_article_batches_native_topic_synthesis'


def test_native_timeout_is_not_reclassified_as_exclusion_or_success(monkeypatch, tmp_path):
    packet = {'topic': '动态议题', 'items': [{'id': 'r1', 'origin': 'raw_monitoring', 'content': '全文。'*30000}]}
    def fail(*args, **kwargs):
        raise HostModelError('实际原生超时', 124)
    monkeypatch.setattr(worker, 'semantic_json', fail)
    with pytest.raises(HostModelError) as caught:
        worker.author_topic_decisions([packet], '规则', [], tmp_path, time.monotonic()+500, reuse_cache=False)
    assert caught.value.exit_code == 124


def test_aggregate_uuids_do_not_become_native_authoring_ids():
    run = {'session_id': 'aggregate-top', 'transport': 'sequential_single_topic_semantic', 'topic_runs': [
        {'session_id': 'aggregate-topic', 'transport': 'lossless_article_batches_native_topic_synthesis',
         'batch_runs': [{'session_id': 'aggregate-batch', 'transport': 'sequential_single_topic_semantic',
                         'topic_runs': [{'session_id': 'native-1', 'web_metadata_repair_run': {'session_id': 'native-repair'}}]}],
         'synthesis_run': {'session_id': 'native-synthesis'}},
        {'session_id': 'fixed-unread', 'model_invoked': False}]}
    assert worker.actual_author_run_ids(run) == ['native-1', 'native-repair', 'native-synthesis']


def test_completed_invalid_json_feedback_is_recoverable_but_transport_failure_is_not():
    assert worker.recoverable_author_blocker_feedback({'error_type': 'SemanticResponseError',
        'blocker': '已完成回复的JSON多一个闭合符'}) == ['已完成回复的JSON多一个闭合符']
    assert worker.recoverable_author_blocker_feedback({'error_type': 'HostModelError', 'blocker': '124'}) == []
    assert worker.recoverable_author_blocker_feedback({'error_type': 'TimeoutError', 'blocker': '无剩余预算'}) == []


def test_invalid_synthesis_repairs_only_summary_preserving_native_claims(tmp_path):
    packet, decisions, _ = fixture()
    valid = flat_response()
    request = synthesis_packet(packet, decisions)
    invalid = copy.deepcopy(valid)
    invalid['claims'] = [{'claim': '模型改写不允许进入原判断'}]
    calls = []
    def model(packet, prompt, command, workspace, label, timeout, reuse_cache):
        calls.append((copy.deepcopy(packet), label, timeout, reuse_cache))
        return (invalid if len(calls) == 1 else valid), {'session_id': label, 'seconds': 2}
    result, run = native_topic_synthesis(request, decisions, [], tmp_path, 90, model, reuse_cache=True)
    assert [row[1] for row in calls] == ['topic-synthesis', 'synthesis-shape-repair']
    assert calls[0][0] == flat_packet(request)[0]
    assert calls[1][0] == {**calls[0][0], 'previous_synthesis': invalid}
    assert calls[1][2] <= 45 and calls[1][3] is False
    assert result['items'][0]['claims'][0]['claim'] == decisions[0]['claims'][0]['claim']
    assert result['transport_repairs'][-1]['original_response'] == invalid
    assert run['synthesis_initial_run']['session_id'] == 'topic-synthesis'
    assert (tmp_path / 'synthesis_shape_failure.json').is_file()


def test_synthesis_transport_failure_does_not_trigger_fresh_call(tmp_path):
    packet, decisions, _ = fixture()
    calls = []
    def model(*args, **kwargs):
        calls.append(1)
        raise HostModelError('native timeout', 124)
    with pytest.raises(HostModelError):
        native_topic_synthesis(synthesis_packet(packet, decisions), decisions, [], tmp_path, 90, model, reuse_cache=False)
    assert calls == [1]


def test_synthesis_index_feedback_names_exact_item_and_missing_claim():
    _, decisions, valid = fixture()
    valid['items'][0]['claim_clusters'] = [{'index': 0, 'cluster': 'k1'}]
    with pytest.raises(ValueError) as caught:
        apply_synthesis(decisions, valid)
    assert 'item=r1' in str(caught.value)
    assert 'required_indices=[0, 1]' in str(caught.value)
    assert 'missing_indices=[1]' in str(caught.value)


def test_synthesis_retry_workspace_retains_hash_bound_original_inputs(tmp_path):
    packet, decisions, _ = fixture()
    valid = flat_response()
    request = synthesis_packet(packet, decisions)
    def model(*args, **kwargs):
        return valid, {'session_id': 'native', 'seconds': 1}
    _, first = native_topic_synthesis(request, decisions, [], tmp_path, 90, model, reuse_cache=False)
    original_path = Path(first['synthesis_input']['path'])
    original_bytes = original_path.read_bytes()
    changed = copy.deepcopy(request)
    changed['scope'] = 'Different later authoring input'
    _, second = native_topic_synthesis(changed, decisions, [], tmp_path, 90, model, reuse_cache=False)
    assert first['synthesis_input'] != second['synthesis_input']
    assert original_path.read_bytes() == original_bytes
    assert json.loads(original_path.read_text('utf-8')) == request
    assert Path(second['synthesis_original_decisions']['path']).is_file()
