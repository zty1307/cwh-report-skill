import copy
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import raw_system_workbook_pipeline as raw
from test_raw_system_workbook_pipeline import PublicTopRankingTests as Fixture


def expanded_case():
    rows = [Fixture.public_row(i, f'account{i}', 10000 - i) for i in range(1, 61)]
    config, metadata = Fixture.public_config(), Fixture.public_metadata()
    first = raw.filter_public_top(rows, config, metadata)['review_packet']
    reviewed = [{'record_id': r['record_id'], 'decision': 'exclude', 'review_reason': 'Unrelated roundup',
                 'classification_confidence': .9, 'topic_hits': []} for r in first['items']]
    expanded = raw.filter_public_top(rows, config, metadata,
        {'review_method': 'ai_semantic_review', 'items': reviewed})['review_packet']
    assert len(first['items']) == 30 and len(expanded['items']) == 60
    deferred = [{'record_id': r['record_id'], 'kind': 'budget_exhausted_before_call',
                 'reason': 'No remaining batch allocation', 'actual_run': {'model_invoked': False}}
                for r in expanded['items'][30:]]
    review = {'review_method': 'ai_semantic_review', 'items': reviewed,
              'delivery_policy': 'deliver_available_with_gaps', 'deferred_records': deferred}
    return rows, config, metadata, review, expanded


def test_expanded_window_keeps_native_decisions_and_unread_rows():
    rows, config, metadata, review, _ = expanded_case()
    frozen = copy.deepcopy(review)
    result = raw.filter_public_top(rows, config, metadata, review)
    assert result['status'] == 'ai_review_partial'
    assert len(result['review_packet']['items']) == 60
    assert len([r for r in result['decisions'] if r['decision'] == 'deferred']) == 30
    assert result['selected'] == []
    assert review == frozen


def test_all_deferred_expanded_window_is_not_approval():
    rows, config, metadata, review, expanded = expanded_case()
    review['items'] = []
    review['review_method'] = 'host_partial_review'
    review['deferred_records'] = [{**review['deferred_records'][0], 'record_id': r['record_id']}
                                  for r in expanded['items']]
    result = raw.filter_public_top(rows, config, metadata, review)
    assert result['status'] == 'ai_review_partial'
    assert result['selected'] == []
    assert len(result['decisions']) == 60


@pytest.mark.parametrize('damage', ['unknown', 'hole', 'no_interruption'])
def test_expansion_never_accepts_invalid_deferrals(damage):
    rows, config, metadata, review, _ = expanded_case()
    if damage == 'unknown':
        review['deferred_records'][-1]['record_id'] = 'invented'
    elif damage == 'hole':
        review['deferred_records'].pop(1)
    elif damage == 'no_interruption':
        review['deferred_records'][0]['actual_run'] = {}
    with pytest.raises(raw.PipelineError):
        raw.filter_public_top(rows, config, metadata, review)


def test_strict_delivery_still_requests_expanded_native_review():
    rows, config, metadata, review, _ = expanded_case()
    review['delivery_policy'] = 'strict'
    result = raw.filter_public_top(rows, config, metadata, review)
    assert result['status'] == 'ai_review_expand_required'
    assert len(result['review_packet']['items']) == 60
    assert not result['selected']
