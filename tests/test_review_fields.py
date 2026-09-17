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


def test_local_retry_preserves_unrelated_verdict_and_complete_excerpt():
    request, result, run = fixtures()
    request['claims'][0]['source_id'] = 's1'
    request['claims'].append({'id': 'e2', 'source_id': 's2',
                             'excerpt_segments': [{'id': 'e2/1', 'text': '另一篇有价值的判断。'}]})
    request['sources'].append({'id': 's2', 'reference_context': '无关文章'})
    accepted = {'id': 'e2', 'verdict': 'fully_supported', 'rationale': '另一篇全文确有依据。', 'revision': None}
    result['reviews'].append(copy.deepcopy(accepted))
    corrected = {'reviews': [{'id': 'e1', 'verdict': 'uncertain', 'rationale': '不能确认对象。', 'revision': None}]}
    newer = {'session_id': 'local-real-run', 'completed_at': 'local-time'}
    with patch('cwh_host_research.semantic_json', return_value=(corrected, newer)) as call:
        combined, _ = retry_invalid_review_fields(request, result, run, '', [], Path('.'), 45)
    sent = call.call_args.args[0]
    assert sent['claims'] == request['claims'][:1]
    assert sent['sources'] == request['sources'][:1]
    assert combined['reviews'][1] == accepted
    assert combined['review_field_retry']['retried_claim_ids'] == ['e1']
    assert combined['review_field_retry']['original_run'] == run
    assert combined['review_field_retry']['retry_run'] == newer


def test_local_retry_cannot_return_or_replace_an_unrequested_claim():
    request, result, run = fixtures()
    request['claims'].append({'id': 'e2'})
    result['reviews'].append({'id': 'e2', 'verdict': 'fully_supported', 'rationale': '保持原审核'})
    corrected = {'reviews': [{'id': 'e1', 'verdict': 'uncertain', 'rationale': '对象不明'},
                             {'id': 'e2', 'verdict': 'unsupported', 'rationale': '误读其他材料'}]}
    with patch('cwh_host_research.semantic_json', return_value=(corrected, run)), pytest.raises(ValueError, match='exactly once'):
        retry_invalid_review_fields(request, result, run, '', [], Path('.'), 45)


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


@pytest.mark.parametrize('claim', ['会议未给出具体安排。', '会议围绕市场环境作出部署。',
    '会议明确“完善相关政策”，这需要落实实际执行条件。', '会议表示政策需要与实施条件相适应。',
    '会议认为当前环境仍需完善。', '会议确定后续工作方向。'])
def test_bare_meeting_action_also_requires_explicit_source_reference(claim):
    from domestic_evidence_mapping import has_ambiguous_meeting_reference
    assert has_ambiguous_meeting_reference(claim)
    assert not has_ambiguous_meeting_reference('中央政治局' + claim)


def test_bare_meeting_before_quote_cannot_pass_on_literal_fidelity_alone():
    request, result, run = fixtures()
    request['claims'][0]['formal_claim'] = '会议明确“完善相关政策”，具体实施仍需要配套条件。'
    request['claims'][0]['reference_expansion_required'] = False  # older saved packet
    result['reviews'][0]['rationale'] = '原文有这句，且作者给出具体实施条件。'
    errors = review_field_errors(result, ['e1'], request['claims'])
    assert errors[0]['invalid_fields'] == ['unexpanded_meeting_reference_requires_native_revision']


def test_available_delivery_quarantines_only_unresolved_reference_not_other_fields():
    request, result, run = fixtures()
    request['delivery_policy'] = 'deliver_available_with_gaps'
    request['claims'][0]['reference_expansion_required'] = True
    result['reviews'][0]['rationale'] = '原文有依据，但尚未在正文写明会议'
    original = copy.deepcopy(result)
    retry_run = {'session_id': 'actual-retry'}
    with patch('cwh_host_research.semantic_json', return_value=(result, retry_run)) as call:
        checked, _ = retry_invalid_review_fields(request, result, run, '', [], Path('.'), 45)
    row = checked['reviews'][0]
    assert call.call_count == 1 and row['verdict'] == 'uncertain' and row['revision'] is None
    assert row['host_reference_gate']['native_review'] == original['reviews'][0]
    assert checked['review_field_retry']['host_reference_quarantines'] == ['e1']
    assert result == original
    result['reviews'][0]['rationale'] = None
    with patch('cwh_host_research.semantic_json', return_value=(result, retry_run)), pytest.raises(ValueError, match='still invalid'):
        retry_invalid_review_fields(request, result, run, '', [], Path('.'), 45)
