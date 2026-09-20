import copy
import json
from pathlib import Path
import sys
from unittest.mock import patch
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_heading_transport import recover_heading_rows
from cwh_heading_quality import review_retained_headings, build_heading_audit, reviewed_display_headings
from cwh_host_research import SemanticResponseError
from test_heading_quality import sample, packet


def terminal(text):
    return json.dumps({'type': 'result', 'subtype': 'success', 'result': text}, ensure_ascii=False)


def malformed_last():
    valid = packet()['heading_reviews'][0]
    bad = json.dumps(packet()['heading_reviews'][1], ensure_ascii=False).replace('"h2"', 'h2请见下', 1)
    return '{"heading_reviews":[' + json.dumps(valid, ensure_ascii=False) + ',' + bad + ']}', valid


def test_recover_only_intact_rows_with_exact_native_values():
    text, valid = malformed_last()
    recovered = recover_heading_rows(terminal(text), {'h1', 'h2'})
    assert recovered['heading_reviews'] == [valid]
    assert recovered['heading_transport_recovery']['invalid_row_indices'] == [1]
    assert recovered['heading_transport_recovery']['quarantined_possible_ids'] == ['h2']


@pytest.mark.parametrize('change', ['truncated', 'error_terminal', 'two_terminals', 'extra_root', 'thought_only'])
def test_ambiguous_framing_and_unfinished_streams_are_not_reviews(change):
    text, _ = malformed_last()
    log = terminal(text)
    if change == 'truncated': log = terminal(text[:-2])
    elif change == 'error_terminal': log = log.replace('"success"', '"error"')
    elif change == 'two_terminals': log += '\n' + log
    elif change == 'extra_root': log = terminal(text[:-1] + ',"other":true}')
    elif change == 'thought_only': log = json.dumps({'type': 'assistant', 'text': text})
    assert recover_heading_rows(log, {'h1', 'h2'}) is None


def test_malformed_possible_duplicate_quarantines_earlier_row_too():
    text, _ = malformed_last()
    assert recover_heading_rows(terminal(text.replace('h2请见下', 'h1请见下')), {'h1', 'h2'}) is None


def test_nested_quoted_delimiters_are_not_array_boundaries():
    text, valid = malformed_last()
    valid['rationale'] = '原文包含“甲,乙”，以及符号 ] } 和英文引号 "，不是JSON边界。'
    bad = text[text.index(',{"id": h2'):]
    result = recover_heading_rows(terminal('{"heading_reviews":[' + json.dumps(valid, ensure_ascii=False) + bad), {'h1', 'h2'})
    assert result['heading_reviews'] == [valid]


def test_production_quarantines_one_heading_without_recalling_or_approving_it(tmp_path):
    text, valid = malformed_last()
    log = tmp_path / 'native.jsonl'
    log.write_text(terminal(text), encoding='utf-8')
    run = {'exit_code': 0, 'session_id': 'actual-heading-run', 'log': str(log)}
    analysis, prior = sample(), packet()
    original = copy.deepcopy((analysis, prior))
    with patch('cwh_host_research.semantic_json', side_effect=SemanticResponseError('bad JSON', run)) as call:
        result = review_retained_headings(analysis, prior, [], tmp_path, 90)
    assert call.call_count == 1
    assert result['heading_recheck']['status'] == 'partial'
    assert result['heading_recheck']['missing_heading_ids'] == ['h2']
    assert result['heading_reviews'] == [{**valid, 'reviewer_run_id': 'actual-heading-run'}]
    audit = build_heading_audit(analysis, result)
    assert [r['id'] for r in audit['approved']] == ['h1']
    assert [r['id'] for r in audit['fallbacks']] == ['h2']
    analysis['research_audit'] = {'heading_quality': audit}
    assert reviewed_display_headings(analysis) == {
        (0, None): '建议按需求优化布局并保留服务覆盖', (0, 0): '相关报道'}
    analysis.pop('research_audit')
    assert (analysis, prior) == original


def test_partial_review_still_requires_scope_and_independent_claim_support():
    analysis, prior = sample(), packet()
    prior['heading_reviews'] = prior['heading_reviews'][:1]
    prior['reviews'][0]['verdict'] = 'unsupported'
    audit = build_heading_audit(analysis, prior)
    assert not audit['approved']
    assert {r['id'] for r in audit['fallbacks']} == {'h1', 'h2'}
