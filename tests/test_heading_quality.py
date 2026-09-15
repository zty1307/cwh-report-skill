import copy
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_heading_quality import heading_manifest, build_heading_audit, reviewed_display_headings
from report_rules import enrich_viewpoint_titles
from cwh_heading_quality import repair_overlong_headings
from unittest.mock import patch


def sample():
    return {'viewpoints': {'by_topic': [{'topic': '公共服务布局', 'heading': '肯定资源调整已经改善服务效率',
        'clusters': [{'summary': '肯定资源调整已经改善服务效率', 'evidence': [
            {'evidence_id': 'real-1', 'speaker_name': '测试日报', 'formal_claim': '建议按需求调整布局，同时保留服务覆盖。',
             'source_excerpt': '建议按需求调整布局，同时保留服务覆盖。', 'semantic_review': {'verdict': 'fully_supported'}}]}]}]}}


def packet():
    return {'reviewer_run_id': 'actual-run', 'reviews': [{'evidence_id': 'real-1', 'verdict': 'fully_supported'}],
            'heading_reviews': [{'id': identity, 'verdict': 'needs_revision',
                'rationale': '原文为建议，未说效果已实现。', 'supporting_claim_ids': ['e1'],
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
