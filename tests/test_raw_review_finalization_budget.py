from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from run_cwh_inline_review import raw_review_budget
from cwh_model_contract import execution_profile, resolved_stage_budgets


@pytest.mark.parametrize('profile', ['bounded_40m', 'bounded_60m'])
@pytest.mark.parametrize('remaining', [600, 340.5, 180, 60, 0])
def test_native_review_cannot_consume_workbook_finalization_reserve(profile, remaining):
    task = {'execution_profile': profile, 'remaining_budget_seconds': remaining,
            'time_budget_seconds': 900}
    result = raw_review_budget(task, True)
    assert result['semantic_seconds'] == max(0, remaining - 180)
    assert result['finalization_reserve_seconds'] == 180
    assert result['semantic_seconds'] + min(remaining, 180) == remaining
    assert task['remaining_budget_seconds'] == remaining
    _, settings = execution_profile(profile)
    assert sum(resolved_stage_budgets(settings, 'raw_workbook').values()) + settings['reserved_delivery_buffer_seconds'] <= settings['wall_clock_budget_seconds']


def test_explicit_zero_is_not_replaced_by_nominal_stage_budget():
    assert raw_review_budget({'remaining_budget_seconds': 0, 'time_budget_seconds': 600}, True)['semantic_seconds'] == 0


def test_legacy_strict_path_keeps_its_existing_reserve():
    result = raw_review_budget({'time_budget_seconds': 200}, False)
    assert result['semantic_seconds'] == 195
    assert result['finalization_reserve_seconds'] == 5
