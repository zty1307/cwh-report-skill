import copy
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_verified_grouping import apply_topic_grouping, apply_grouping_audit, digest, weak_group_topics


def fixture():
    evidence = [{'evidence_id': f'e{i}', 'speaker_name': f'主体{i}', 'formal_claim': f'完整判断{i}',
                 'source_excerpt': f'连续原文{i}', 'semantic_review': {'verdict': 'fully_supported', 'reviewer_run_id': 'old-real'}}
                for i in range(1, 4)]
    topic = {'topic': '通用政策', 'heading': '建议完善政策执行', 'clusters': [
        {'summary': '原分组一', 'evidence': evidence[:2]}, {'summary': '原分组二', 'evidence': evidence[2:]}]}
    response = {'decision': 'regroup', 'topic_heading': '建议完善政策执行',
                'groups': [{'heading': '建议完善具体执行', 'ids': ['q3', 'q1', 'q2']}], 'reason': '三个互补论据支持一个共同判断'}
    return topic, response, {'session_id': 'real-native-grouping', 'exit_code': 0}


def test_grouping_changes_no_claim_source_or_existing_review():
    topic, response, run = fixture()
    before = copy.deepcopy(topic)
    result = apply_topic_grouping(topic, response, run)
    assert topic == before
    assert len(result['clusters']) == 1
    assert result['clusters'][0]['evidence'] == [topic['clusters'][1]['evidence'][0], *topic['clusters'][0]['evidence']]
    assert result['single_cluster_exception']['reviewed_by'] == run['session_id']


def test_shared_native_decoder_recognizes_only_the_declared_grouping_envelope():
    import json
    from run_cwh_inline_review import response_object
    _, response, _ = fixture()
    assert response_object(json.dumps({'type': 'result', 'result': json.dumps(response)})) == response
    keep = {'decision': 'keep_original', 'reason': '没有足够共同判断'}
    assert response_object(json.dumps(keep)) == keep
    with pytest.raises(ValueError):
        response_object('{"groups":[]}')


@pytest.mark.parametrize('ids', [['q1', 'q2'], ['q1', 'q1', 'q3'], ['q1', 'q2', 'q4']])
def test_omission_duplication_and_invention_are_rejected(ids):
    topic, response, run = fixture()
    response['groups'][0]['ids'] = ids
    with pytest.raises(ValueError):
        apply_topic_grouping(topic, response, run)


def test_one_source_per_numbered_group_remains_invalid():
    topic, response, run = fixture()
    response['groups'] = [{'heading': '一', 'ids': ['q1', 'q2']}, {'heading': '二', 'ids': ['q3']}]
    with pytest.raises(ValueError, match='single-source'):
        apply_topic_grouping(topic, response, run)


def test_grouping_audit_cannot_rebind_to_changed_original_evidence():
    topic, response, run = fixture()
    original = {'viewpoints': {'by_topic': [topic]}, 'research_audit': {}}
    assert weak_group_topics(original) == [0]
    audit = {'input_sha256': digest(original), 'changes': [{'topic_index': 0, 'topic_before_sha256': digest(topic),
             'response': response, 'response_sha256': digest(response), 'run': run}]}
    result = apply_grouping_audit(original, audit)
    assert len(result['viewpoints']['by_topic'][0]['clusters']) == 1
    tampered = copy.deepcopy(original)
    tampered['viewpoints']['by_topic'][0]['clusters'][0]['evidence'][0]['formal_claim'] = '篡改'
    with pytest.raises(ValueError, match='retained input'):
        apply_grouping_audit(tampered, audit)


def test_candidate_family_index_follows_native_regroup_without_touching_source_fields():
    topic, response, run = fixture()
    candidates = []
    for group_index, cluster in enumerate(topic['clusters']):
        for evidence in cluster['evidence']:
            cid = evidence['evidence_id'] + '-candidate'
            evidence['candidate_id'] = cid
            candidates.append({'candidate_id': cid, 'decision': 'eligible', 'formal_use': 'selected',
                'viewpoint_cluster_key': f'old-{group_index}', 'source_snapshot': {'source_text': '完整原文不动'}})
    candidates.append({'candidate_id': 'reserve', 'formal_use': 'reserve', 'viewpoint_cluster_key': 'old-reserve'})
    original = {'viewpoints': {'by_topic': [topic]}, 'research_audit': {'domestic_media_research': {
        'candidate_pool_by_topic': [{'topic': topic['topic'], 'candidates': candidates}]}}}
    frozen = copy.deepcopy(original)
    audit = {'input_sha256': digest(original), 'changes': [{'topic_index': 0,
        'topic_before_sha256': digest(topic), 'response': response, 'response_sha256': digest(response), 'run': run}]}
    result = apply_grouping_audit(original, audit)
    after = result['research_audit']['domestic_media_research']['candidate_pool_by_topic'][0]['candidates']
    assert {r['viewpoint_cluster_key'] for r in after if r['formal_use'] == 'selected'} == {'editorial-regroup-1'}
    assert after[-1] == candidates[-1]
    for a, b in zip(after[:-1], candidates[:-1]):
        assert {k:v for k,v in a.items() if k != 'viewpoint_cluster_key'} == {k:v for k,v in b.items() if k != 'viewpoint_cluster_key'}
    assert original == frozen
    assert apply_grouping_audit(original, result['research_audit']['post_review_grouping']) == result
