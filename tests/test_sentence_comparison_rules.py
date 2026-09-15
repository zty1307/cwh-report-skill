"""Config routing and frozen-evidence invariants, not semantic model certification."""
import copy
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_model_contract import build_task_payload
from cwh_writing_rules import writing_rules
from cwh_comment_semantics import merge_quote_decisions
from cwh_heading_quality import build_heading_audit, reviewed_display_headings
from report_rules import enrich_viewpoint_titles
from report_rules import domestic_viewpoint_quality_issues
from cwh_authoring_packet import compact_authoring_references
import json


def test_task_handoff_uses_configured_rules_instead_of_a_second_rule_copy(tmp_path):
    rules = copy.deepcopy(writing_rules())
    rules['viewpoint'].update(selection_rule='configured-selection', heading_support_rule='configured-heading',
        claim_composition_rule='configured-claim', cluster_structure_rule='configured-structure')
    rules['comments']['heading_summary_rule'] = 'configured-comment'
    rules['comments']['selection_quality_rule'] = 'configured-quote-selection'
    with patch('cwh_model_contract.writing_rules', return_value=rules):
        task = build_task_payload(stage_id='domestic_viewpoints', task_type='analysis_bundle',
            expected_output=tmp_path / 'author.json', inputs={}, rules=[], profile_name='bounded_60m')
    assert task['writing_handoff']['selection_rule'] == 'configured-selection'
    assert task['writing_handoff']['heading_support_rule'] == 'configured-heading'
    assert task['writing_handoff']['comment_heading_summary_rule'] == 'configured-comment'
    assert task['writing_handoff']['comment_selection_quality_rule'] == 'configured-quote-selection'
    assert task['writing_handoff']['claim_composition_rule'] == 'configured-claim'
    assert task['writing_handoff']['cluster_structure_rule'] == 'configured-structure'
    assert task['declared_outputs'] == [str(tmp_path / 'author.json')]


def test_not_selecting_a_quote_does_not_reclassify_the_comment_or_empty_the_denominator():
    labels = {'rows': [{'id': 1, 'topic': 1, 'label': 'positive', 'formal': False,
                       'reason': '表达支持', 'sample_id': 'genuine-comment'}]}
    frozen = copy.deepcopy(labels)
    result = merge_quote_decisions(labels, {'topic_headings': {}, 'selected': []})
    assert result['rows'][0]['label'] == 'positive'
    assert result['rows'][0]['formal'] is False
    assert len([r for r in result['rows'] if r['label'] != 'exclude']) == 1
    assert labels == frozen


def test_overseas_summary_handoff_reads_shared_config_not_a_separate_prompt_copy():
    from raw_system_workbook_pipeline import build_overseas_review_packet
    rules = copy.deepcopy(writing_rules())
    rules['overseas']['interpretive_summary_rule'] = 'configured-summary-judgment-and-conditions'
    with patch('raw_system_workbook_pipeline.writing_rules', return_value=rules):
        packet = build_overseas_review_packet([], {}, {'topic_titles': ['公共政策']}, [])
    assert 'configured-summary-judgment-and-conditions' in packet['instructions']


def test_reviewed_effect_strength_changes_only_display_and_stales_after_claim_change():
    evidence = {'evidence_id': 'actual-evidence', 'speaker_name': '机构甲',
                'formal_claim': '完善基础设施有助于降低流通成本。',
                'source_excerpt': '完善基础设施有助于降低流通成本。',
                'semantic_review': {'verdict': 'fully_supported'}}
    data = {'viewpoints': {'by_topic': [{'topic': '流通布局', 'heading': '认为设施改善是降本关键',
        'clusters': [{'summary': '认为设施改善是降本关键', 'evidence': [evidence]}]}]}}
    frozen = copy.deepcopy(evidence)
    packet = {'reviewer_run_id': 'actual-independent-review',
        'reviews': [{'evidence_id': evidence['evidence_id'], 'verdict': 'fully_supported'}],
        'heading_reviews': [{'id': identity, 'verdict': 'needs_revision', 'rationale': '原文只说有助于，未称关键。',
            'supporting_claim_ids': ['e1'], 'scope_preserved': True, 'replacement': {'text': '认为完善设施有助于降低流通成本',
            'verdict': 'supported', 'rationale': '原文直接支持作用及有限强度。'}} for identity in ('h1', 'h2')]}
    data['research_audit'] = {'heading_quality': build_heading_audit(data, packet)}
    enrich_viewpoint_titles(data)
    assert data['viewpoints']['by_topic'][0]['heading'] == '认为完善设施有助于降低流通成本'
    assert evidence == frozen
    assert len(reviewed_display_headings(data)) == 2
    evidence['formal_claim'] = '新的不同论断'
    assert reviewed_display_headings(data) == {}


def test_semantic_editorial_categories_cannot_become_a_keyword_veto():
    rules = copy.deepcopy(writing_rules())
    for rule in rules['viewpoint']['editorial_exclusions']:
        if rule.get('review_mode') == 'semantic_only':
            rule['patterns'] = ['产业链', '金融']  # Even an erroneous future pattern is advisory.
    claim = '政策利好产业链发展，长期金融支持可覆盖研发阶段资金缺口，但效果取决于项目筛选和持续投入，不能只依靠短期市场热度。'
    evidence = {'attribution_status': 'self_media', 'formal_claim': claim, 'source_excerpt': claim}
    data = {'viewpoints': {'by_topic': [{'topic': '产业培育', 'heading': '认为长期资金支持须匹配研发周期',
        'clusters': [{'summary': '认为长期资金支持须匹配研发周期', 'details': claim, 'evidence': [evidence]}]}]}}
    frozen = copy.deepcopy(data)
    with patch('report_rules.writing_rules', return_value=rules):
        codes = {r['code'] for r in domestic_viewpoint_quality_issues(data)}
    assert not codes.intersection({'beneficiary_market_pitch', 'tangential_promotion', 'slogan_or_wordplay_only'})
    assert data == frozen


def test_legacy_author_transport_routes_the_same_cross_period_claim_and_cluster_rules():
    root = Path(__file__).resolve().parents[1]
    rules = copy.deepcopy(writing_rules())
    keys = ('interpretation_eligibility_rule', 'meeting_reference_rule', 'selection_rule',
            'claim_composition_rule', 'cluster_structure_rule', 'heading_support_rule')
    for key in keys:
        rules['viewpoint'][key] = 'configured-' + key
    registry = (root / 'config/source_registry.v1.json').read_text('utf-8')
    schema = (root / 'references/analysis_bundle_schema.md').read_text('utf-8')
    with patch('cwh_authoring_packet.writing_rules', return_value=rules):
        result = compact_authoring_references(schema, registry, {'topic': '公共服务', 'stable_source_tasks': []})
    assert all('configured-' + key in result['semantic_requirements'] for key in keys)
    assert not any('只谈消费金融板块受益' in text for text in result['semantic_requirements'])
    assert result['output_shape']['metadata']['meeting_date'].startswith('Only a verified')


def test_single_topic_contract_enumerates_real_ids_without_changing_source_material():
    from run_cwh_compiled_worker import single_topic_author_contract
    packet = {'topic': '公共服务供给', 'items': [{'id': 'original-7', 'content': '真实原文'}, {'id': 'original-9'}]}
    frozen = copy.deepcopy(packet)
    contract = single_topic_author_contract(packet)
    assert contract.endswith(json.dumps(['original-7', 'original-9'], ensure_ascii=False))
    assert '真实原文' not in contract
    assert packet == frozen


def test_checkpoint_identity_changes_with_model_rules_and_output_shape():
    from run_cwh_compiled_worker import author_contract_sha256
    first = author_contract_sha256('original-rules', ['host', '--model', 'first-model'])
    assert first == author_contract_sha256('original-rules', ['host', '--model', 'first-model'])
    assert first != author_contract_sha256('changed-rules', ['host', '--model', 'first-model'])
    assert first != author_contract_sha256('original-rules', ['host', '--model', 'second-model'])
    with patch('run_cwh_compiled_worker.single_topic_author_contract', return_value='changed-output-shape'):
        assert first != author_contract_sha256('original-rules', ['host', '--model', 'first-model'])
