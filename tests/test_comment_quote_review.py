"""Formal selection must not mutate source text, topics or sentiment decisions."""
import copy
from pathlib import Path
import sys
from unittest.mock import patch
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_comment_semantics import apply_quote_review, review_formal_selection


def decisions():
    return {'rows': [{'id': 1, 'topic': 1, 'label': 'positive', 'reason': 'classified',
        'formal': True, 'heading': '认为应改善服务覆盖', 'text': '原话甲'},
        {'id': 2, 'topic': 1, 'label': 'neutral', 'reason': 'classified',
         'formal': True, 'heading': '询问基层服务如何落实', 'text': '原话乙'}],
        'topic_headings': {'1': '旧的共同标题'}}


def answer():
    return {'reviews': [{'id': 1, 'verdict': 'reject', 'reason': 'abstract'},
        {'id': 2, 'verdict': 'keep', 'reason': 'specific inquiry'}],
        'topic_headings': {'1': '询问基层服务如何落实'}}


def test_review_subsets_only_formal_quotes_and_replaces_stale_group_title():
    original = decisions()
    frozen = copy.deepcopy(original)
    result = apply_quote_review(original, answer())
    assert original == frozen
    for old, new in zip(original['rows'], result['rows']):
        assert {k: new[k] for k in ('id', 'topic', 'label', 'reason', 'text')} == {
            k: old[k] for k in ('id', 'topic', 'label', 'reason', 'text')}
    assert [row['id'] for row in result['rows'] if row['formal']] == [2]
    assert result['topic_headings'] == answer()['topic_headings']


@pytest.mark.parametrize('change', ['duplicate', 'extra', 'relabel', 'stale_heading'])
def test_invalid_review_cannot_create_a_formal_handoff(change):
    reviewed = answer()
    if change == 'duplicate':
        reviewed['reviews'][1]['id'] = 1
    elif change == 'extra':
        reviewed['reviews'][1]['id'] = 99
    elif change == 'relabel':
        reviewed['reviews'][1]['label'] = 'negative'
    else:
        reviewed['topic_headings']['2'] = '没有保留评论的议题'
    with pytest.raises(ValueError):
        apply_quote_review(decisions(), reviewed)


def test_failed_review_preserves_denominator_but_never_claims_formal_approval(tmp_path):
    original = decisions()
    with patch('cwh_comment_semantics.semantic_json', side_effect=TimeoutError('test timeout')):
        result, audit = review_formal_selection({'rows': [{'id': 1}, {'id': 2}]},
                                               original, ['configured-host'], tmp_path, 10)
    assert audit['status'] == 'review_incomplete'
    assert len(result['rows']) == 2 and all(not row['formal'] for row in result['rows'])
    assert [row['label'] for row in result['rows']] == ['positive', 'neutral']


def test_empty_selection_does_not_spend_another_model_call(tmp_path):
    original = decisions()
    for row in original['rows']:
        row['formal'] = False
    with patch('cwh_comment_semantics.semantic_json') as call:
        result, audit = review_formal_selection({'rows': []}, original, [], tmp_path, 45)
    call.assert_not_called()
    assert result == original and audit['status'] == 'not_needed'
