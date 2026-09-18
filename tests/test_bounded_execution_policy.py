from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_research_plan import build_plan  # noqa: E402
from cwh_model_contract import execution_profile, resolved_stage_budgets  # noqa: E402
from cwh_preflight import execution_policy_checks  # noqa: E402


def policy():
    return json.loads((ROOT / "config" / "execution_policy.v1.json").read_text(encoding="utf-8"))


def test_40m_remains_available_and_retains_independent_review_and_quality_minimums():
    name, current = execution_profile("bounded_40m")
    assert name == "bounded_40m"
    assert sum(current["stage_budgets_seconds"].values()) == 2040
    assert current["reserved_delivery_buffer_seconds"] == 360
    assert current["wall_clock_budget_seconds"] == 2400
    assert current["research"]["parallel_lanes"] is False
    assert current["comments"]["parallel_with_domestic_research"] is False
    assert current["overseas"]["parallel_with_domestic_research"] is False
    assert current["stage_budgets_seconds"]["domestic_evidence_verification"] >= 300
    _, legacy = execution_profile("bounded_60m")
    for field in ("minimum_independent_voices_per_topic", "target_formal_excerpts_per_topic", "max_formal_voices_per_topic"):
        assert current["research"][field] == legacy["research"][field]
    assert current["model_contract"] == legacy["model_contract"]


@pytest.mark.parametrize("name", ["bounded_40m", "bounded_60m"])
@pytest.mark.parametrize("defect", ["over_budget", "missing_review", "negative_stage", "wrong_wall"])
def test_preflight_rejects_corrupt_budget_even_for_nondefault_profile(name, defect):
    damaged = copy.deepcopy(policy())
    selected = damaged["profiles"][name]
    if defect == "over_budget":
        selected["reserved_delivery_buffer_seconds"] = selected["wall_clock_budget_seconds"]
    elif defect == "missing_review":
        del selected["stage_budgets_seconds"]["domestic_evidence_verification"]
    elif defect == "negative_stage":
        selected["stage_budgets_seconds"]["domestic_viewpoints"] = -1
    else:
        selected["wall_clock_budget_seconds"] += 1
    checks = {row["id"]: row for row in execution_policy_checks(damaged)}
    assert checks[f"policy:{name}_budget"]["status"] == "failed"


def test_preflight_checks_all_shipped_profiles():
    checks = execution_policy_checks(policy())
    assert all(row["status"] == "passed" for row in checks), checks
    assert {row["id"] for row in checks} >= {
        "policy:bounded_40m_budget", "policy:bounded_60m_budget", "policy:exhaustive_budget",
    }


def test_input_budgets_prioritize_body_within_the_one_hour_limit():
    _, selected = execution_profile("bounded_60m")
    raw = resolved_stage_budgets(selected, "raw_workbook")
    standard = resolved_stage_budgets(selected, "standard_workbook")
    assert raw["workbook"] == 600 and standard["workbook"] == 30
    assert raw["domestic_viewpoints"] == 1080 and standard["domestic_viewpoints"] == 1290
    assert raw["domestic_evidence_verification"] == 780 and standard["domestic_evidence_verification"] == 600
    assert standard["overseas_evidence"] - raw["overseas_evidence"] == 180
    assert standard["hotwords"] - raw["hotwords"] == 60
    assert sum(raw.values()) == 3225 and sum(standard.values()) == 2925
    assert selected["wall_clock_budget_seconds"] == 3600 and selected["research_deadline_seconds"] == 3000
    for allocation in (raw, standard):
        assert sum(allocation.values()) + selected['reserved_delivery_buffer_seconds'] <= 3600
        assert allocation['render'] == 180 and allocation['delivery_gate'] == 120


def test_raw_appendices_cannot_consume_the_primary_body_allocation():
    _, selected = execution_profile("bounded_60m")
    raw = resolved_stage_budgets(selected, "raw_workbook")
    assert raw["overseas_evidence"] == 60 and raw["hotwords"] == 30
    assert raw["domestic_viewpoints"] == 1080 and raw["domestic_evidence_verification"] == 780
    assert raw['domestic_viewpoints'] + raw['domestic_evidence_verification'] > 3 * raw['workbook']
    assert raw["domestic_comments_sentiment"] == 300
    assert raw["render"] == 180 and raw["delivery_gate"] == 120
    assert sum(raw.values()) + selected["reserved_delivery_buffer_seconds"] == 3600
    assert sum(v for k, v in raw.items() if k not in {"render", "delivery_gate"}) <= selected["research_deadline_seconds"]


@pytest.mark.parametrize("override", [{"workbook": -1}, {"domestic_viewpoints": 10000}, {"render": 1}, {"unknown": 1}])
def test_input_allocations_cannot_inflate_budget_or_steal_delivery(override):
    _, selected = execution_profile("bounded_60m")
    selected["input_mode_budget_overrides"] = {"standard_workbook": override}
    with pytest.raises(ValueError):
        resolved_stage_budgets(selected, "standard_workbook")


def research_plan(name):
    # Synthetic workbook metadata isolates policy routing; this is not an evidence run.
    metadata = {
        "monitoring_period": {"start": "2026-01-01", "end": "2026-01-03"},
        "topics": [{"title": "议题甲"}, {"title": "议题乙"}],
    }
    with patch("build_research_plan.ingest_workbook", return_value=metadata):
        return build_plan("policy-routing-test.xlsx", execution_profile_name=name)


@pytest.mark.parametrize("name", ["bounded_40m", "bounded_60m"])
def test_both_bounded_profiles_apply_caps_grouped_lanes_and_one_zero_round(name):
    plan = research_plan(name)
    _, selected = execution_profile(name)
    assert plan["execution_profile"] == name
    assert plan["execution_budget"]["wall_clock_budget_seconds"] == selected["wall_clock_budget_seconds"]
    assert plan["execution_budget"]["max_named_entity_expansions_per_topic"] == selected["research"]["max_named_entity_expansions_per_topic"]
    assert not plan["global_tasks"]["overseas"]["mediaspider_foreign"]["deep_crawl"]
    assert plan["global_tasks"]["public_comments"]["target_quotes"] == [2, 3]
    assert plan["research_audit_contract"]["required_zero_new_rounds"] == 1
    assert "two consecutive" not in " ".join(plan["authority_rules"])
    for topic in plan["topics"]:
        assert topic["minimum_evidence"]["formal_sources_per_mature_cluster"] == "bounded_selected_eligible_with_audited_reserve"
        assert topic["candidate_pool_contract"]["max_formal_voices_per_topic"] == 12
        assert all(task["bounded"] for task in topic["stable_source_tasks"])
        assert topic["candidate_pool_contract"]["saturation_rule"]["required_zero_new_rounds"] == 1


def test_exhaustive_keeps_unbounded_source_tasks_and_two_zero_rounds():
    plan = research_plan("exhaustive")
    assert plan["execution_budget"]["wall_clock_budget_seconds"] == 0
    assert plan["global_tasks"]["overseas"]["mediaspider_foreign"]["deep_crawl"]
    assert plan["global_tasks"]["public_comments"]["target_quotes"] is None
    assert plan["research_audit_contract"]["required_zero_new_rounds"] == 2
    assert "two consecutive" in " ".join(plan["authority_rules"])
    for topic in plan["topics"]:
        assert not any(task.get("bounded") for task in topic["stable_source_tasks"])
        assert topic["candidate_pool_contract"]["max_formal_voices_per_topic"] == 0


def test_unknown_profile_is_not_silently_treated_as_bounded():
    with pytest.raises(ValueError, match="Unknown CWH execution profile"):
        research_plan("unknown_profile")
