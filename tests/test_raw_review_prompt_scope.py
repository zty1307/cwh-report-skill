"""Contract routing checks, not claims of semantic model success."""
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from run_cwh_inline_review import raw_review_prompt_rules


def test_available_term_count_policy_cannot_leak_into_article_review_contracts():
    for kind in ('public_top', 'overseas'):
        assert raw_review_prompt_rules(kind, True) == raw_review_prompt_rules(kind, False)
        assert 'minimum_term_count' not in raw_review_prompt_rules(kind)
    assert raw_review_prompt_rules('hotword', True) != raw_review_prompt_rules('hotword', False)


def test_interpretive_span_fields_are_requested_only_in_the_overseas_contract():
    assert 'interpretive_range:' in raw_review_prompt_rules('overseas')
    assert 'interpretive_range:' not in raw_review_prompt_rules('public_top')
    assert 'interpretive_range:' not in raw_review_prompt_rules('hotword')


def test_unknown_task_kind_cannot_silently_use_another_stage_contract():
    with pytest.raises(ValueError):
        raw_review_prompt_rules('unrecognized')
