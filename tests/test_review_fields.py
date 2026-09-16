"""Schema and provenance tests; mocked transport is not a real model success."""
import copy
from pathlib import Path
import sys
from unittest.mock import patch
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_review_fields import review_field_errors, retry_invalid_review_fields


def fixtures():
    request = {'claims': [{'id': 'e1', 'excerpt_segments': [{'id': 'e1/1', 'text': '条件明确。'}]}],
               'sources': [{'id': 's1', 'reference_context': '原始对象'}], 'headings': [{'id': 'h1'}]}
    result = {'reviews': [{'id': 'e1', 'verdict': 'fully_supported', 'rationale': None}],
              'heading_reviews': [{'id': 'h1', 'verdict': 'supported', 'rationale': '原文对象明确'}]}
    return request, result, {'session_id': 'original-real-run', 'completed_at': 'original-time'}


@pytest.mark.parametrize('value', [None, '', '   ', False, []])
def test_null_empty_or_wrong_typed_rationale_is_never_a_supported_certification(value):
    _, result, _ = fixtures()
    result['reviews'][0]['rationale'] = value
    assert review_field_errors(result, ['e1']) == [{'id': 'e1', 'invalid_fields': ['rationale']}]


def test_valid_review_uses_no_new_model_call_or_budget():
    request, result, run = fixtures()
    result['reviews'][0]['rationale'] = '原文明示条件，原句没有增加效果。'
    with patch('cwh_host_research.semantic_json') as call:
        assert retry_invalid_review_fields(request, result, run, '', [], Path('.'), 0) == (result, run)
    call.assert_not_called()


def test_actual_retry_may_reject_claim_and_keeps_original_heading_provenance():
    request, result, run = fixtures()
    frozen = copy.deepcopy((request, result, run))
    corrected = {'reviews': [{'id': 'e1', 'verdict': 'unsupported', 'rationale': '原文仅有条件，未支持新增效果。', 'revision': None}]}
    retry_run = {'session_id': 'new-real-run', 'completed_at': 'new-time'}
    with patch('cwh_host_research.semantic_json', return_value=(corrected, retry_run)) as call:
        combined, actual = retry_invalid_review_fields(request, result, run, 'frozen-source-only', [], Path('.'), 200)
    assert call.call_args.args[-1] == 45
    assert 'headings' not in call.call_args.args[0]
    assert call.call_args.args[0]['claims'] == request['claims']
    assert combined['reviews'] == corrected['reviews']
    assert actual == retry_run
    assert combined['heading_reviews'][0]['reviewer_run_id'] == run['session_id']
    assert combined['heading_original_run'] == run
    assert (request, result, run) == frozen


def test_no_remaining_retry_time_does_not_fill_fields_or_call_model():
    request, result, run = fixtures()
    with patch('cwh_host_research.semantic_json') as call, pytest.raises(ValueError, match='no retry budget'):
        retry_invalid_review_fields(request, result, run, '', [], Path('.'), 14)
    call.assert_not_called()
    assert result['reviews'][0]['rationale'] is None


def test_invalid_retry_is_rejected_after_one_call():
    request, result, run = fixtures()
    with patch('cwh_host_research.semantic_json', return_value=(result, run)) as call, pytest.raises(ValueError, match='still invalid'):
        retry_invalid_review_fields(request, result, run, '', [], Path('.'), 40)
    assert call.call_count == 1
    assert call.call_args.args[-1] == 40


@pytest.mark.parametrize('rows', [[], [{'id': 'e2'}], [{'id': 'e1'}, {'id': 'e1'}]])
def test_wrong_or_missing_ids_cannot_be_guessed(rows):
    with pytest.raises(ValueError, match='exactly once'):
        review_field_errors({'reviews': rows}, ['e1'])


def test_ambiguous_meeting_reference_needs_native_revision_not_host_replacement():
    request, result, run = fixtures()
    request['claims'][0].update(formal_claim='会议首次提出该措施，可针对已有问题完善政策机制。', reference_expansion_required=True)
    result['reviews'][0]['rationale'] = '文字原样出现'
    assert review_field_errors(result, ['e1'], request['claims'])[0]['invalid_fields'] == ['unexpanded_meeting_reference_requires_native_revision']
    corrected = {'reviews': [{'id': 'e1', 'verdict': 'uncertain', 'rationale': '无法确认实际会议，不猜测', 'revision': None}]}
    with patch('cwh_host_research.semantic_json', return_value=(corrected, {'session_id': 'native-recheck'})):
        reviewed, _ = retry_invalid_review_fields(request, result, run, '', [], Path('.'), 45)
    assert reviewed['reviews'] == corrected['reviews']
    assert request['claims'][0]['formal_claim'].startswith('会议首次')
