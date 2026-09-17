import copy
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from test_host_compiler import compiled
from run_cwh_compiled_worker import compile_review
from cwh_review_retention import retain_reviewed_content, retention_packet
from cwh_review_repair import validate_combined, evidence_rows


def fixture():
    source = compiled()
    ev = evidence_rows(source)[0][1]
    other = copy.deepcopy(ev)
    other['evidence_id'] += '-uncertain'
    source['viewpoints']['by_topic'][0]['clusters'][0]['evidence'].append(other)
    raw = {'reviews': [
        {'id': 'e1', 'verdict': 'fully_supported', 'rationale': '真实原文支持。', 'revision': None},
        {'id': 'e2', 'verdict': 'uncertain', 'rationale': '实际讨论对象无法确定。', 'revision': None}]}
    run = {'session_id': 'actual-independent-run', 'completed_at': 'time'}
    initial = compile_review(source, raw, run, 'original-hash')
    return source, initial, run


def test_uncertain_claim_is_excluded_not_guessed_and_original_is_unchanged():
    source, initial, run = fixture()
    frozen = copy.deepcopy(source)
    repaired, actions = retain_reviewed_content(source, initial)
    assert len(evidence_rows(repaired)) == 1
    assert source == frozen
    assert actions[0]['action'] == 'excluded'
    assert actions[0]['excluded_evidence'] == evidence_rows(source)[1][1]
    final = retention_packet(repaired, initial, actions, run, 'new-hash')
    validate_combined(source, repaired, initial, final)
    assert final['reviews'][0]['reviewer_run_id'] == run['session_id']
    assert final['repair_provenance']['excluded_evidence_ids'] == [evidence_rows(source)[1][1]['evidence_id']]
    assert repaired['research_audit']['domestic_media_research'] == source['research_audit']['domestic_media_research']


@pytest.mark.parametrize('narrow', [False, True])
def test_local_recheck_keeps_each_actual_reviewer_through_retention(narrow):
    from domestic_evidence_mapping import validate_semantic_review_packet
    source, initial, original_run = fixture()
    raw = {'reviews': [{'id': 'e1', 'verdict': 'fully_supported', 'rationale': '原审核未变化。'},
                       {'id': 'e2', 'verdict': 'uncertain', 'rationale': '本条局部补核。', 'revision': None}],
           'review_field_retry': {'original_run': original_run,
               'retry_run': {'session_id': 'local-recheck', 'completed_at': 'later-time'},
               'retried_claim_ids': ['e2']}}
    if narrow:
        raw['reviews'][1]['revision'] = {'formal_claim': evidence_rows(source)[0][1]['formal_claim'],
                                         'verdict': 'fully_supported', 'rationale': '局部收窄有依据。'}
    later = raw['review_field_retry']['retry_run']
    initial = compile_review(source, raw, later, 'original-hash')
    assert initial['reviews'][0]['reviewed_at'] == original_run['completed_at']
    assert initial['reviews'][0]['reviewer_run_id'] == original_run['session_id']
    assert initial['reviews'][1]['reviewer_run_id'] == later['session_id']
    repaired, actions = retain_reviewed_content(source, initial)
    final = retention_packet(repaired, initial, actions, later, 'new-hash')
    validate_combined(source, repaired, initial, final)
    assert final['reviews'][0] == initial['reviews'][0]
    if narrow:
        assert final['reviews'][1]['reviewer_run_id'] == later['session_id']
        assert final['reviews'][1]['reviewed_at'] == later['completed_at']
    assert not validate_semantic_review_packet(repaired, final, source_bundle_sha256='new-hash')


def test_retention_refuses_frozen_source_or_accepted_claim_edits():
    source, initial, run = fixture()
    repaired, actions = retain_reviewed_content(source, initial)
    final = retention_packet(repaired, initial, actions, run, 'new-hash')
    tampered = copy.deepcopy(repaired)
    evidence_rows(tampered)[0][1]['speaker_name'] = '假人'
    with pytest.raises(ValueError, match='frozen sources'):
        validate_combined(source, tampered, initial, final)
    final['reviews'][0]['rationale'] = '篡改'
    with pytest.raises(ValueError, match='accepted verdict'):
        validate_combined(source, repaired, initial, final)


def test_invalid_reviewer_number_is_excluded_instead_of_waiving_draft_gate():
    source, initial, run = fixture()
    initial['reviews'][1]['revision'] = {'formal_claim': '公共服务建设将在三年内完成。',
        'verdict': 'fully_supported', 'rationale': '审核建议但数字不在原文。'}
    repaired, actions = retain_reviewed_content(source, initial)
    assert actions[0]['action'] == 'excluded'
    assert any(i['code'] == 'claim_adds_numbers' for i in actions[0]['draft_gate_issues'])
    final = retention_packet(repaired, initial, actions, run, 'new-hash')
    validate_combined(source, repaired, initial, final)


def test_independently_supported_narrowing_is_retained_with_real_certification():
    source, initial, run = fixture()
    initial['reviews'][1]['verdict'] = 'partially_supported'
    initial['reviews'][1]['revision'] = {'formal_claim': evidence_rows(source)[0][1]['formal_claim'],
        'verdict': 'fully_supported', 'rationale': '删除越界内容后原文完整支持。'}
    repaired, actions = retain_reviewed_content(source, initial)
    assert actions[0]['action'] == 'narrowed'
    final = retention_packet(repaired, initial, actions, run, 'new-hash')
    validate_combined(source, repaired, initial, final)
    assert len(final['reviews']) == 2
    assert final['reviews'][1]['rationale'] == initial['reviews'][1]['revision']['rationale']


def test_retention_cannot_hide_incomplete_review_or_forge_exclusion_audit():
    source, initial, run = fixture()
    bad = copy.deepcopy(initial)
    bad['reviews'].pop()
    with pytest.raises(ValueError, match='coverage'):
        retain_reviewed_content(source, bad)
    repaired, actions = retain_reviewed_content(source, initial)
    final = retention_packet(repaired, initial, actions, run, 'new-hash')
    final['repair_provenance']['excluded_evidence_ids'] = []
    with pytest.raises(ValueError, match='exclusion audit'):
        validate_combined(source, repaired, initial, final)


def test_month_only_revision_is_not_a_real_meeting_identity():
    source, initial, run = fixture()
    initial['reviews'][1]['revision'] = {'formal_claim': '7月会议指出，' + evidence_rows(source)[0][1]['formal_claim'],
        'verdict': 'fully_supported', 'rationale': '只恢复月份，没有确认实际会议。'}
    repaired, actions = retain_reviewed_content(source, initial)
    assert actions[0]['action'] == 'excluded'
    assert any(i['code'] == 'ambiguous_meeting_reference' for i in actions[0]['draft_gate_issues'])


def test_all_rejected_voices_keep_original_candidate_snapshot_and_explicit_empty_topic():
    source = compiled()
    frozen = copy.deepcopy(source)
    run = {'session_id': 'actual-reviewer', 'completed_at': 'time'}
    initial = compile_review(source, {'reviews': [{'id': 'e1', 'verdict': 'uncertain',
        'rationale': '原文不足以确认对象。', 'revision': None}]}, run, 'original-hash')
    repaired, actions = retain_reviewed_content(source, initial)
    assert source == frozen
    original_candidate = source['research_audit']['domestic_media_research']['candidate_pool_by_topic'][0]['candidates'][0]
    retained_candidate = repaired['research_audit']['domestic_media_research']['candidate_pool_by_topic'][0]['candidates'][0]
    assert retained_candidate['decision'] == 'excluded'
    assert retained_candidate['source_snapshot'] == original_candidate['source_snapshot']
    assert repaired['research_audit']['independent_review_retention']['candidate_actions'][0]['original_candidate'] == original_candidate
    assert repaired['viewpoints']['by_topic'][0]['clusters'] == []
    assert repaired['viewpoints']['by_topic'][0]['evidence_gap']['status'] == 'no_usable_interpretation_in_reviewed_material'
    final = retention_packet(repaired, initial, actions, run, 'new-hash')
    validate_combined(source, repaired, initial, final)
