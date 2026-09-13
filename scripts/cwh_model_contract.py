from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = SKILL_ROOT / "config" / "execution_policy.v1.json"
WRITING_RULES_PATH = SKILL_ROOT / "config" / "formal_writing_rules.v1.json"

TASK_OUTPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "raw_workbook_semantic_reviews": {
        "type": "multi_artifact",
        "required_artifacts": ["hotword_ai_review", "overseas_ai_review", "public_top_ai_review"],
    },
    "domestic_viewpoint_research_and_review": {
        "type": "object",
        "required": ["metadata", "research_audit", "viewpoints"],
    },
    "independent_domestic_evidence_verification": {
        "type": "object",
        "required": ["review_version", "review_pass", "reviewer_run_id", "source_bundle_sha256", "reviews"],
    },
    "domestic_comment_collection_and_sentiment": {
        "type": "multi_artifact",
        "required_artifacts": ["comment_handoff", "sentiment_results", "sentiment_summary"],
        "sentiment_summary_required": ["collection_audit", "topics"],
    },
    "overseas_media_and_comment_collection_review": {
        "type": "multi_artifact",
        "required_artifacts": ["supplements", "foreign_collection_audit"],
    },
    "hotword_evidence_review": {
        "type": "object",
        "required": ["review_method", "second_pass_completed", "settings", "selected"],
    },
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def execution_profile(name: str = "") -> tuple[str, dict[str, Any]]:
    policy = read_json(POLICY_PATH)
    profile_name = name or str(policy.get("default_profile") or "bounded_60m")
    profiles = policy.get("profiles") or {}
    if profile_name not in profiles:
        raise ValueError(f"Unknown CWH execution profile: {profile_name}")
    return profile_name, dict(profiles[profile_name])


def stage_budget_seconds(stage_id: str, profile_name: str = "") -> int | None:
    _, profile = execution_profile(profile_name)
    value = (profile.get("stage_budgets_seconds") or {}).get(stage_id)
    if value in (None, "", 0):
        return None
    return max(1, int(value))


def build_task_payload(
    *,
    stage_id: str,
    task_type: str,
    expected_output: Path,
    inputs: dict[str, Any],
    rules: list[str],
    profile_name: str = "",
    output_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_profile, profile = execution_profile(profile_name)
    model_contract = profile.get("model_contract") or {}
    budget = stage_budget_seconds(stage_id, resolved_profile)
    declared_outputs = [str(expected_output)]
    additional = inputs.get("expected_outputs")
    if isinstance(additional, dict):
        declared_outputs.extend(str(value) for value in additional.values() if value)
    elif isinstance(additional, list):
        declared_outputs.extend(str(value) for value in additional if value)
    # Verified bundles and mapping audits are controller-generated artifacts,
    # not worker outputs, even when their paths are supplied as task context.
    for key in ("expected_audit",):
        if inputs.get(key):
            declared_outputs.append(str(inputs[key]))
    declared_outputs = list(dict.fromkeys(declared_outputs))
    return {
        "schema_version": "2.0",
        "task_id": f"{stage_id}:v2",
        "task_type": task_type,
        "stage_id": stage_id,
        "execution_profile": resolved_profile,
        "time_budget_seconds": budget,
        "expected_output": str(expected_output),
        "declared_outputs": declared_outputs,
        "inputs": inputs,
        "output_schema": output_schema or TASK_OUTPUT_SCHEMAS.get(task_type, {"type": "object"}),
        "rules": rules,
        "fixed_writing_rules": str(WRITING_RULES_PATH),
        "forbidden_operations": [
            "modify any file under skill_root",
            "modify pipeline_state.json, pipeline_events.jsonl, hashes, validators or task contracts",
            "invent a URL, candidate_id, evidence_id, quotation, comment or source snapshot",
            "write directly into report/ or mark any stage complete",
            "weaken a gate or pad prose solely to satisfy a length threshold",
        ],
        "repair_contract": {
            "maximum_rounds": int(model_contract.get("max_repair_rounds_per_stage") or 2),
            "scope": "repair only fields named by validation_problems; preserve accepted evidence and identifiers",
            "missing_evidence": str(model_contract.get("on_missing_evidence") or "return_structured_blocker"),
        },
        "completion_contract": (
            "Write only the declared JSON/CSV artifacts to declared_outputs. Do not edit code, pipeline state, validators, hashes or prior accepted artifacts. "
            "The deterministic validator is the sole authority for completion. If evidence is insufficient, return a structured "
            "blocker instead of fabricating or padding."
        ),
    }
