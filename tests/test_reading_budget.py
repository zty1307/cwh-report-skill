import copy
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_reading_budget import allocate_reading, frozen_reading_allocation, preparation_policy, optional_priority_budget

POLICY = {'base_monitoring_articles': 12, 'base_public_pages': 4,
          'baseline_topic_seconds': 360, 'expanded_topic_seconds': 660}


def test_preparation_reserves_most_author_time_for_intact_reading():
    from cwh_model_contract import execution_profile
    fraction, minimum = preparation_policy(execution_profile('bounded_60m')[1])
    assert fraction == .25 and minimum == 30
    assert preparation_policy(execution_profile('bounded_40m')[1]) == (.45, 10)
    assert optional_priority_budget(60, .2, 45, minimum) == 0
    assert optional_priority_budget(200, .2, 45, minimum) == 40
    assert optional_priority_budget(900, .2, 45, minimum) == 45
    assert optional_priority_budget(-1, .2, 45, minimum) == 0


@pytest.mark.parametrize('field,value', [('preparation_fraction', 1), ('preparation_fraction', True),
    ('preparation_fraction', float('nan')), ('minimum_optional_priority_seconds', 0)])
def test_invalid_preparation_policy_is_not_silently_used(field, value):
    with pytest.raises(ValueError, match='preparation budget'):
        preparation_policy({'research': {field: value}})


def test_ceilings_are_not_mandatory_quotas_and_minimum_review_is_preserved():
    assert allocate_reading(POLICY, (20, 10), 6, 1667) == [12, 4]
    assert allocate_reading(POLICY, (20, 10), 1, 660) == [20, 10]
    assert allocate_reading(POLICY, (20, 10), 2, 1020) == [16, 7]
    assert allocate_reading(POLICY, (16, 3), 6, 10) == [12, 3]
    assert allocate_reading(POLICY, (12, 4), 1, 900) == [12, 4]


def test_resume_keeps_same_source_scope_despite_less_time(tmp_path):
    plan = {'execution_profile': 'bounded_60m', 'execution_budget': {'reading_budget_policy': POLICY}}
    before = copy.deepcopy(plan)
    path = tmp_path / 'allocation.json'
    first = frozen_reading_allocation(path, plan, (20, 10), 2, 1020)
    saved = path.read_bytes()
    assert frozen_reading_allocation(path, plan, (20, 10), 2, 50) == first == (16, 7)
    assert path.read_bytes() == saved and plan == before
    with pytest.raises(ValueError, match='immutable inputs'):
        frozen_reading_allocation(path, plan, (20, 10), 3, 900)
    record = json.loads(saved)
    record['payload']['limits'] = [20, 10]
    path.write_text(json.dumps(record), encoding='utf-8')
    with pytest.raises(ValueError, match='immutable inputs'):
        frozen_reading_allocation(path, plan, (20, 10), 2, 900)


def test_old_plans_and_exhaustive_keep_existing_reading_contract(tmp_path):
    path = tmp_path / 'allocation.json'
    assert frozen_reading_allocation(path, {}, (20, 10), 6, 100) == (20, 10)
    assert frozen_reading_allocation(path, {'execution_profile': 'exhaustive',
        'execution_budget': {'reading_budget_policy': POLICY}}, (20, 10), 6, 100) == (20, 10)
    assert not path.exists()
