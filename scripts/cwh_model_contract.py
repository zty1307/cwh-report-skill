from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from cwh_writing_rules import writing_rules, writing_rules_sha256


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
    profile_name = name or str(policy.get("default_profile") or "bounded_40m")
    profiles = policy.get("profiles") or {}
    if profile_name not in profiles:
        raise ValueError(f"Unknown CWH execution profile: {profile_name}")
    return profile_name, dict(profiles[profile_name])


def is_bounded_profile(profile: str | dict[str, Any] = "") -> bool:
    settings = profile if isinstance(profile, dict) else execution_profile(profile)[1]
    return int(settings.get("wall_clock_budget_seconds") or 0) > 0


def resolved_stage_budgets(profile: dict[str, Any], input_mode: str) -> dict[str, int]:
    """Reallocate unnecessary raw normalization time, not the delivery reserve."""
    stages = dict(profile.get("stage_budgets_seconds") or {})
    overrides = (profile.get("input_mode_budget_overrides") or {}).get(input_mode) or {}
    if not set(overrides).issubset(stages):
        raise ValueError("Input-mode override references an unknown stage")
    resolved = {**stages, **overrides}
    if resolved and any(not isinstance(v, int) or isinstance(v, bool) or v <= 0 for v in resolved.values()):
        raise ValueError("Stage budgets must be positive integers")
    if sum(resolved.values()) > sum(stages.values()):
        raise ValueError("Input-mode allocation cannot increase the total stage budget")
    for stage in ("domestic_evidence_verification", "render", "delivery_gate"):
        if resolved.get(stage, 0) < stages.get(stage, 0):
            raise ValueError("Input-mode allocation cannot borrow from review or delivery")
    return resolved


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
    stage_workspace: Path | None = None,
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
    workspace = stage_workspace or (expected_output.parent / "_worker" / stage_id)
    return {
        "schema_version": "2.0",
        "task_id": f"{stage_id}:v2",
        "task_type": task_type,
        "stage_id": stage_id,
        "execution_profile": resolved_profile,
        "time_budget_seconds": budget,
        "semantic_request_limits": {
            "single_topic_max_seconds": int(model_contract.get("single_topic_request_timeout_seconds") or 0),
            "future_topic_reserve_seconds": int(model_contract.get("minimum_future_topic_request_seconds") or 0),
        },
        "expected_output": str(expected_output),
        "declared_outputs": declared_outputs,
        "stage_workspace": str(workspace),
        "allowed_write_directories": [str(workspace)],
        "inputs": inputs,
        "output_schema": output_schema or TASK_OUTPUT_SCHEMAS.get(task_type, {"type": "object"}),
        "rules": rules,
        "fixed_writing_rules": str(WRITING_RULES_PATH),
        "writing_rules_sha256": writing_rules_sha256(),
        "writing_handoff": {
            "model_fields": ["heading", "summary", "speaker_name", "source_excerpt", "formal_claim", "semantic_review", "translation"],
            "script_fields": ["source_order", "details", "opening", "propagation_prose", "numbering", "comment_lead", "hotword_prose", "overseas_frames", "Word/Markdown layout"],
            "instruction": "Submit only the semantic fields required by this stage. Do not draft whole report sections or polish script-generated paragraphs. Preserve the source meaning and all qualifications.",
            "claim_cjk_range": writing_rules()["viewpoint"]["claim_cjk_range"],
            "interpretation_eligibility_rule": writing_rules()["viewpoint"]["interpretation_eligibility_rule"],
            "meeting_reference_rule": writing_rules()["viewpoint"]["meeting_reference_rule"],
            "selection_rule": writing_rules()["viewpoint"]["selection_rule"],
            "claim_composition_rule": writing_rules()["viewpoint"]["claim_composition_rule"],
            "claim_unit_rule": writing_rules()["viewpoint"]["claim_unit_rule"],
            "composition_frames": writing_rules()["viewpoint"]["composition_frames"],
            "paragraph_pairing_rule": writing_rules()["viewpoint"]["paragraph_pairing_rule"],
            "cluster_structure_rule": writing_rules()["viewpoint"]["cluster_structure_rule"],
            "heading_support_rule": writing_rules()["viewpoint"]["heading_support_rule"],
            "comment_heading_summary_rule": writing_rules()["comments"]["heading_summary_rule"],
            "comment_selection_quality_rule": writing_rules()["comments"]["selection_quality_rule"],
            "prohibited_padding": writing_rules()["viewpoint"]["prohibited_padding"],
        },
        "mechanical_completion": {
            "stage": "domestic_viewpoints",
            "missing_fields_only": ["candidate_id", "snapshot_id", "source_text_sha256", "source_snapshot_id", "source_excerpt_start", "source_excerpt_end", "evidence_id"],
            "instruction": "The controller fills these draft fields only where exact source inputs determine them uniquely. Preserve existing IDs and consistent query/candidate references. Supply real full text and semantic fields; never invent missing source facts. Frozen reviewed bundles must not be completed again.",
        },
        "delivery_boundary": "The controller renders Word, Excel, Markdown and HTML from shared data using shipped templates. Do not generate report files, HTML/CSS/JavaScript, layouts or charts; do not read the large dashboard template during normal stage execution.",
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
            "Write final JSON/CSV artifacts only to declared_outputs; store collection seeds, raw responses, temporary batches and helper outputs only under stage_workspace. Do not edit code, pipeline state, validators, hashes or prior accepted artifacts. "
            "The deterministic validator checks source integrity. If evidence is insufficient, return the available "
            "content plus structured gaps so the controller can continue delivery; never fabricate or pad."
        ),
    }
