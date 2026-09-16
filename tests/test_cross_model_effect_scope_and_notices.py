import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_writing_rules import writing_rules
from cwh_semantic_compiler import AUTHOR_PROMPT
from cwh_semantic_repairs import REPAIR_PROMPT
from run_cwh_compiled_worker import REVIEW_PROMPT
from cwh_comment_semantics import QUOTE_PROMPT, QUOTE_REVIEW_PROMPT, PROMPT, COMPACT_PROMPT
from formalize_cwh_report import empty_comment_notice, formal_overseas_summary


def test_same_literal_attribution_rule_reaches_author_repair_and_independent_review():
    rule = writing_rules()['viewpoint']['attribution_identity_rule']
    assert all(rule in prompt for prompt in (AUTHOR_PROMPT, REPAIR_PROMPT, REVIEW_PROMPT))
    assert '联名报告' in rule and '第一位作者' in rule and '后缀' in rule


def test_shared_effect_object_rule_reaches_writer_repair_and_independent_review():
    rule = writing_rules()['viewpoint']['effect_object_scope_rule']
    assert all(rule in prompt for prompt in (AUTHOR_PROMPT, REPAIR_PROMPT, REVIEW_PROMPT))


def test_parent_policy_is_not_synonymous_with_quote_state_in_all_quote_routes():
    marker = '政策甲与状态乙含义相关或近似'
    assert all(marker in prompt for prompt in (QUOTE_PROMPT, QUOTE_REVIEW_PROMPT, PROMPT, COMPACT_PROMPT))


def test_no_quote_does_not_deny_genuine_captured_comments():
    row = {'content': '原始评论', 'quote_verified': True, 'comment_id': '1',
           'evidence_mode': 'verbatim_public_comment', 'url': 'https://example.test/comment',
           'ai_formal_include': False}
    assert empty_comment_notice({'comments': {'selected': [row]}}) == writing_rules()['comments']['no_ready_quotes_verified_samples']
    assert row['ai_formal_include'] is False


def test_unverified_or_out_of_window_rows_are_not_claimed_as_verifiable_current_samples():
    assert empty_comment_notice({'comments': {'selected': [{'content': '线索'}]}}) == writing_rules()['comments']['no_ready_quotes_unverified_candidates']
    row = {'quote_verified': True, 'comment_id': '1', 'evidence_mode': 'verbatim_public_comment',
           'url': 'https://example.test/comment', 'in_monitoring_window': False}
    assert empty_comment_notice({'comments': {'selected': [row]}}) == writing_rules()['comments']['no_ready_quotes_unverified_candidates']
    assert empty_comment_notice({}) == writing_rules()['comments']['no_comment_samples']


def test_only_redundant_narrating_prefix_is_removed_not_actual_actor_or_conditions():
    claim = '政策效果取决于需求恢复，短期仍有不确定性'
    assert formal_overseas_summary({'summary_cn_simplified': '原文认为，' + claim}) == claim
    actual = '某研究员认为，' + claim
    assert formal_overseas_summary({'summary_cn_simplified': actual}) == actual
