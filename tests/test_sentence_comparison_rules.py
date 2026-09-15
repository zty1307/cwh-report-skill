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


def test_task_handoff_uses_configured_rules_instead_of_a_second_rule_copy(tmp_path):
    rules = copy.deepcopy(writing_rules())
    rules['viewpoint'].update(selection_rule='configured-selection', heading_support_rule='configured-heading')
    rules['comments']['heading_summary_rule'] = 'configured-comment'
    with patch('cwh_model_contract.writing_rules', return_value=rules):
        task = build_task_payload(stage_id='domestic_viewpoints', task_type='analysis_bundle',
            expected_output=tmp_path / 'author.json', inputs={}, rules=[], profile_name='bounded_60m')
    assert task['writing_handoff']['selection_rule'] == 'configured-selection'
    assert task['writing_handoff']['heading_support_rule'] == 'configured-heading'
    assert task['writing_handoff']['comment_heading_summary_rule'] == 'configured-comment'
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
            'supporting_claim_ids': ['e1'], 'replacement': {'text': '认为完善设施有助于降低流通成本',
            'verdict': 'supported', 'rationale': '原文直接支持作用及有限强度。'}} for identity in ('h1', 'h2')]}
    data['research_audit'] = {'heading_quality': build_heading_audit(data, packet)}
    enrich_viewpoint_titles(data)
    assert data['viewpoints']['by_topic'][0]['heading'] == '认为完善设施有助于降低流通成本'
    assert evidence == frozen
    assert len(reviewed_display_headings(data)) == 2
    evidence['formal_claim'] = '新的不同论断'
    assert reviewed_display_headings(data) == {}
