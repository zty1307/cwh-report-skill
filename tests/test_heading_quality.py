import copy
import sys
import pytest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_heading_quality import heading_manifest, build_heading_audit, reviewed_display_headings
from report_rules import enrich_viewpoint_titles
from cwh_heading_quality import repair_overlong_headings
from cwh_heading_quality import review_retained_headings
from unittest.mock import patch


def sample():
    return {'viewpoints': {'by_topic': [{'topic': '公共服务布局', 'heading': '肯定资源调整已经改善服务效率',
        'clusters': [{'summary': '肯定资源调整已经改善服务效率', 'evidence': [
            {'evidence_id': 'real-1', 'speaker_name': '测试日报', 'formal_claim': '建议按需求调整布局，同时保留服务覆盖。',
             'source_excerpt': '建议按需求调整布局，同时保留服务覆盖。', 'semantic_review': {'verdict': 'fully_supported'}}]}]}]}}


def packet():
    return {'reviewer_run_id': 'actual-run', 'reviews': [{'evidence_id': 'real-1', 'verdict': 'fully_supported'}],
            'heading_reviews': [{'id': identity, 'verdict': 'needs_revision',
                'rationale': '原文为建议，未说效果已实现。', 'supporting_claim_ids': ['e1'], 'scope_preserved': True,
                'replacement': {'text': '建议按需求优化布局并保留服务覆盖', 'verdict': 'supported',
                                'rationale': '原文明确支持调整建议与覆盖条件。'}} for identity in ('h1', 'h2')]}


def audited():
    data = sample()
    data['research_audit'] = {'heading_quality': build_heading_audit(data, packet())}
    return data


def test_heading_manifest_connects_each_heading_to_its_own_claims():
    data = sample()
    data['viewpoints']['by_topic'][0]['clusters'].append({'summary': '担忧覆盖不均', 'evidence': [
        {'evidence_id': 'real-2', 'formal_claim': '另一观点'}]})
    rows = heading_manifest(data)
    assert [r['claim_ids'] for r in rows] == [['e1', 'e2'], ['e1'], ['e2']]


def test_cluster_title_cannot_cover_only_one_of_two_retained_members():
    data = sample()
    data['viewpoints']['by_topic'][0]['clusters'][0]['evidence'].append({
        'evidence_id': 'real-2', 'formal_claim': '另一实质判断',
        'semantic_review': {'verdict': 'fully_supported'}})
    review = packet()
    review['reviews'].append({'evidence_id': 'real-2', 'verdict': 'fully_supported'})
    frozen = copy.deepcopy(data)
    audit = build_heading_audit(data, review)
    assert [r['id'] for r in audit['approved']] == ['h1']
    assert any('未覆盖全部保留成员' in warning for warning in audit['warnings'])
    assert data == frozen
    review['heading_reviews'][1]['supporting_claim_ids'] = ['e1', 'e2']
    assert len(build_heading_audit(data, review)['approved']) == 2


def test_missing_policy_scope_confirmation_uses_original_topic_not_first_cluster():
    data, review = sample(), packet()
    review['heading_reviews'][0].pop('scope_preserved')
    audit = build_heading_audit(data, review)
    assert [r['id'] for r in audit['approved']] == ['h2']
    assert audit['fallbacks'][0]['display_text'] == data['viewpoints']['by_topic'][0]['topic']
    review['heading_reviews'][0]['scope_preserved'] = 1
    assert [r['id'] for r in build_heading_audit(data, review)['approved']] == ['h2']


def test_body_field_retry_cannot_restamp_original_heading_reviewer():
    data, review = sample(), packet()
    review['reviewer_run_id'] = 'new-body-review-run'
    review['heading_original_run'] = {'session_id': 'original-heading-run'}
    for row in review['heading_reviews']:
        row['reviewer_run_id'] = 'original-heading-run'
    data['research_audit'] = {'heading_quality': build_heading_audit(data, review)}
    assert {row['reviewer_run_id'] for row in data['research_audit']['heading_quality']['approved']} == {'original-heading-run'}
    assert len(reviewed_display_headings(data)) == 2


def test_exact_cross_topic_duplicate_detection_never_guesses_routes_or_merges_homonyms():
    from cwh_heading_quality import cross_topic_exact_duplicate_groups
    ev = {'evidence_id': 'a', 'speaker_name': '某专家', 'speaker_role': '原文职务',
          'url': 'https://example.com/article', 'formal_claim': '完全相同的实际判断。'}
    other = {**ev, 'evidence_id': 'b', 'formal_claim': '完全相同的实际判断'}
    data = {'viewpoints': {'by_topic': [
        {'topic': '议题甲', 'clusters': [{'evidence': [ev]}]},
        {'topic': '议题乙', 'clusters': [{'evidence': [other]}]}]}}
    frozen = copy.deepcopy(data)
    groups = cross_topic_exact_duplicate_groups(data)
    assert groups == [{'claim_ids': ['e1', 'e2'], 'topics': ['议题甲', '议题乙'],
                       'evidence_ids': ['a', 'b']}]
    assert data == frozen
    other['speaker_role'] = '不同职务，不据同名合并'
    assert cross_topic_exact_duplicate_groups(data) == []


def test_retained_heading_recheck_uses_current_claims_and_real_separate_run():
    analysis = sample()
    frozen = copy.deepcopy(analysis)
    result = {'heading_reviews': packet()['heading_reviews']}
    with patch('cwh_host_research.semantic_json', return_value=(result, {'session_id': 'actual-heading-run'})) as call:
        revised = review_retained_headings(analysis, packet(), [], Path('.'), 90)
    request = call.call_args.args[0]
    assert request['claims'][0]['formal_claim'] == analysis['viewpoints']['by_topic'][0]['clusters'][0]['evidence'][0]['formal_claim']
    assert 'source_excerpt' not in request['claims'][0]
    assert '不从旧标题推回已经删除的论据' in call.call_args.args[1]
    assert call.call_args.args[-1] == 90
    assert call.call_args.kwargs['reuse_cache'] is False
    assert revised['heading_reviews'][0]['reviewer_run_id'] == 'actual-heading-run'
    assert analysis == frozen


def test_retained_heading_recheck_skips_short_budget_and_rejects_partial_coverage():
    analysis, earlier = sample(), packet()
    with patch('cwh_host_research.semantic_json') as call:
        result = review_retained_headings(analysis, earlier, [], Path('.'), 20)
        assert 'heading_reviews' not in result
        assert result['heading_recheck']['reason'] == 'insufficient_remaining_budget'
        call.assert_not_called()
    with patch('cwh_host_research.semantic_json', return_value=({'heading_reviews': []}, {'session_id': 'run'})):
        result = review_retained_headings(analysis, earlier, [], Path('.'), 40)
        assert result['heading_recheck']['status'] == 'unavailable'
        assert result['unusable_prior_heading_reviews'] == earlier['heading_reviews']
        assert 'heading_reviews' not in result


@pytest.mark.parametrize('supplied', [None, [], [{'id': 'h1'}]])
def test_unavailable_heading_review_uses_neutral_display_without_mutating_claims(supplied):
    data, review = sample(), packet()
    frozen = copy.deepcopy(data)
    review['heading_reviews'] = supplied
    audit = build_heading_audit(data, review)
    assert audit['approved'] == []
    assert [r['display_text'] for r in audit['fallbacks']] == ['公共服务布局', '相关报道']
    assert data == frozen
    data['research_audit'] = {'heading_quality': audit}
    assert reviewed_display_headings(data) == {(0, None): '公共服务布局', (0, 0): '相关报道'}


def test_supported_replacement_is_display_only_and_preserves_source_audit():
    data = audited()
    original = copy.deepcopy(data)
    assert len(reviewed_display_headings(data)) == 2
    enrich_viewpoint_titles(data)
    topic = data['viewpoints']['by_topic'][0]
    assert topic['heading'] == '建议按需求优化布局并保留服务覆盖'
    assert topic['clusters'][0]['evidence'] == original['viewpoints']['by_topic'][0]['clusters'][0]['evidence']
    assert data['research_audit'] == original['research_audit']


def test_missing_or_duplicate_heading_reviews_never_block_claim_delivery_or_edit_titles():
    data = sample()
    assert build_heading_audit(data, {})['warnings']
    review = packet()
    review['heading_reviews'][1]['id'] = 'h1'
    assert build_heading_audit(data, review)['approved'] == []


def test_rejected_claim_cannot_support_a_replacement_title():
    review = packet()
    review['reviews'][0]['verdict'] = 'unsupported'
    assert build_heading_audit(sample(), review)['approved'] == []


def test_foreign_claim_id_and_malformed_ids_are_not_accepted():
    review = packet()
    review['heading_reviews'][0]['supporting_claim_ids'] = ['e99']
    assert len(build_heading_audit(sample(), review)['approved']) == 1
    review['heading_reviews'][0]['supporting_claim_ids'] = [{}]
    assert len(build_heading_audit(sample(), review)['approved']) == 1
    review['heading_reviews'][0]['id'] = {}
    assert build_heading_audit(sample(), review)['approved'] == []


def test_stale_claim_or_modified_approved_text_disables_display_patch():
    data = audited()
    data['viewpoints']['by_topic'][0]['clusters'][0]['evidence'][0]['formal_claim'] = '改过的观点'
    assert reviewed_display_headings(data) == {}
    data = audited()
    data['research_audit']['heading_quality']['approved'][0]['display_text'] = '肯定没有原文支持的效果'
    assert reviewed_display_headings(data) == {}


def test_uncertain_heading_is_warning_not_fabricated_conclusion():
    review = packet()
    for row in review['heading_reviews']:
        row.update(verdict='uncertain', replacement=None)
    audit = build_heading_audit(sample(), review)
    assert audit['approved'] == [] and len(audit['warnings']) == 2


def test_render_data_nested_bundle_retains_heading_audit():
    bundle = audited()
    report = {'viewpoints': copy.deepcopy(bundle['viewpoints']), 'analysis_bundle': bundle}
    assert len(reviewed_display_headings(report)) == 2
    enrich_viewpoint_titles(report)
    assert report['viewpoints']['by_topic'][0]['heading'].startswith('建议')


def test_heading_length_repair_is_small_optional_and_preserves_other_reviews():
    data, review = sample(), packet()
    review['heading_reviews'][0]['replacement']['text'] = '建议' + '按实际需求优化公共服务布局' * 4
    manifest = heading_manifest(data)
    request = {'headings': manifest, 'claims': [{'id': 'e1', 'formal_claim': '原观点'}], 'sources': []}
    answer = {'heading_reviews': [copy.deepcopy(packet()['heading_reviews'][0])]}
    with patch('cwh_host_research.semantic_json', return_value=(answer, {'session_id': 'repair-real'})) as model:
        result = repair_overlong_headings(request, review, ['model'], Path('.'), 30)
    assert len(model.call_args.args[0]['headings']) == 1
    assert result['heading_reviews'][1] == review['heading_reviews'][1]
    assert result['heading_reviews'][0]['reviewer_run_id'] == 'repair-real'
    assert result['reviews'] == review['reviews']
    with patch('cwh_host_research.semantic_json') as model:
        assert repair_overlong_headings(request, review, ['model'], Path('.'), 10) == review
        model.assert_not_called()


def test_rejected_heading_without_certified_replacement_is_neutralized_not_reused():
    data, review = sample(), packet()
    review['heading_reviews'][0].update(verdict='uncertain', replacement=None)
    audit = build_heading_audit(data, review)
    data['research_audit'] = {'heading_quality': audit}
    assert reviewed_display_headings(data)[(0, None)] == '公共服务布局'


def test_clear_repetition_and_multi_center_style_faults_share_one_small_repair():
    data, review = sample(), packet()
    review['heading_reviews'][0]['replacement']['text'] = '公共服务转向系统性转变与协同'
    review['heading_reviews'][1]['replacement']['text'] = '服务供给扩大，政策定位提升且投资拉动显著'
    request = {'headings': heading_manifest(data), 'claims': [{'id': 'e1', 'formal_claim': '原观点'}], 'sources': []}
    with patch('cwh_host_research.semantic_json', return_value=({'heading_reviews': []}, {'session_id': 'r'})) as model:
        assert repair_overlong_headings(request, review, [], Path('.'), 30) == review
    assert len(model.call_args.args[0]['headings']) == 2
    assert model.call_count == 1


def test_source_label_heading_requests_semantic_repair_not_mechanical_deletion():
    data, review = sample(), packet()
    review['heading_reviews'][0]['replacement']['text'] = '认为机构解读公共服务改善机制'
    request = {'headings': heading_manifest(data), 'claims': [{'id': 'e1', 'formal_claim': '原观点'}], 'sources': []}
    frozen = copy.deepcopy(review)
    with patch('cwh_host_research.semantic_json', return_value=({'heading_reviews': []}, {'session_id': 'actual'})) as model:
        assert repair_overlong_headings(request, review, [], Path('.'), 30) == frozen
    assert len(model.call_args.args[0]['headings']) == 1
    assert '来源标签或审核动作代替具体判断' in model.call_args.args[0]['headings'][0]['style_faults']


@pytest.mark.parametrize('text', ['认为公共服务被解读为协同保障', '认为保护与发展双赢的空间配置判断'])
def test_introduction_style_heading_uses_existing_single_optional_repair(text):
    data, review = sample(), packet()
    review['heading_reviews'][0]['replacement']['text'] = text
    request = {'headings': heading_manifest(data), 'claims': [{'id': 'e1', 'formal_claim': '原观点'}], 'sources': []}
    frozen = copy.deepcopy(review)
    with patch('cwh_host_research.semantic_json', return_value=({'heading_reviews': []}, {'session_id': 'actual'})) as model:
        assert repair_overlong_headings(request, review, [], Path('.'), 30) == frozen
    assert model.call_count == 1 and len(model.call_args.args[0]['headings']) == 1
    assert any('介绍解读过程' in fault for fault in model.call_args.args[0]['headings'][0]['style_faults'])


def test_heading_replay_preserves_real_prior_repair_provenance():
    data, review = sample(), packet()
    review['heading_repair_run'] = {'session_id': 'earlier-real'}
    review['heading_repair_runs'] = [{'session_id': 'earlier-real'}, {'session_id': 'later-real'}]
    review['heading_reviews'][0]['reviewer_run_id'] = 'earlier-real'
    review['heading_reviews'][1]['reviewer_run_id'] = 'later-real'
    data['research_audit'] = {'heading_quality': build_heading_audit(data, review)}
    assert [r['reviewer_run_id'] for r in data['research_audit']['heading_quality']['approved']] == ['earlier-real', 'later-real']
    assert len(reviewed_display_headings(data)) == 2


def test_malformed_repair_metadata_does_not_crash_or_certify_a_fake_run():
    data, review = sample(), packet()
    review['heading_repair_run'] = 'not-a-host-run'
    review['heading_repair_runs'] = [None, 'invented', {}, {'session_id': 3}]
    review['heading_reviews'][0]['reviewer_run_id'] = 'invented'
    audit = build_heading_audit(data, review)
    assert audit['approved'][0]['reviewer_run_id'] == review['reviewer_run_id']
    data['research_audit'] = {'heading_quality': audit}
    assert len(reviewed_display_headings(data)) == 2


def test_factual_certified_heading_is_not_given_an_invented_stance():
    data, review = sample(), packet()
    review['heading_reviews'][0]['replacement']['text'] = '公共服务部门公布布局调整规则'
    data['research_audit'] = {'heading_quality': build_heading_audit(data, review)}
    enrich_viewpoint_titles(data)
    assert data['viewpoints']['by_topic'][0]['heading'] == '公共服务部门公布布局调整规则'
    from formalize_cwh_report import topic_heading
    assert topic_heading(data['viewpoints']['by_topic'][0]) == '公共服务部门公布布局调整规则'
    enrich_viewpoint_titles(data)
    assert data['viewpoints']['by_topic'][0]['heading'] == '公共服务部门公布布局调整规则'
