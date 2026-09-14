from __future__ import annotations

import argparse
import importlib
import json
import platform
import sys
from pathlib import Path
from typing import Any


REQUIRED_MODULES = {
    "numpy": "numpy==2.2.6",
    "openpyxl": "openpyxl==3.1.5",
    "PIL": "Pillow==12.1.0",
    "docx": "python-docx==1.2.0",
    "opencc": "opencc-python-reimplemented==0.1.7",
}


REQUIRED_STAGES = {
    "preflight", "intake", "workbook", "research_plan", "domestic_viewpoints",
    "domestic_evidence_verification", "domestic_comments_sentiment",
    "overseas_evidence", "hotwords", "render", "delivery_gate",
}


def execution_policy_checks(policy: dict[str, Any]) -> list[dict[str, Any]]:
    """Check every shipped profile, including the explicitly selected legacy one."""
    from cwh_model_contract import resolved_stage_budgets
    profiles = policy.get("profiles") or {}
    default_name = str(policy.get("default_profile") or "")
    checks = [{
        "id": "policy:default_profile",
        "status": "passed" if default_name in {"bounded_40m", "bounded_60m"} and default_name in profiles else "failed",
        "profile": default_name,
    }]
    for name, expected_wall in (("bounded_40m", 2400), ("bounded_60m", 3600), ("exhaustive", 0)):
        try:
            profile = profiles[name]
            wall_clock = int(profile.get("wall_clock_budget_seconds") or 0)
            reserve = int(profile.get("reserved_delivery_buffer_seconds") or 0)
            stages = profile.get("stage_budgets_seconds") or {}
            stage_total = sum(int(value) for value in stages.values())
            valid = wall_clock == expected_wall and reserve >= 0
            if expected_wall:
                valid = (
                    valid and set(stages) == REQUIRED_STAGES
                    and all(isinstance(value, int) and not isinstance(value, bool) and value > 0 for value in stages.values())
                    and stage_total + reserve <= wall_clock
                )
                deadline = profile.get("research_deadline_seconds", 0)
                valid = valid and isinstance(deadline, int) and not isinstance(deadline, bool) and 0 <= deadline < wall_clock
            else:
                valid = valid and reserve == 0 and not stages
            checks.append({
                "id": f"policy:{name}_budget",
                "status": "passed" if valid else "failed",
                "wall_clock_seconds": wall_clock,
                "stage_total_seconds": stage_total,
                "reserve_seconds": reserve,
            })
            for input_mode in profile.get("input_mode_budget_overrides") or {}:
                allocation = resolved_stage_budgets(profile, input_mode)
                checks.append({"id": f"policy:{name}:{input_mode}_allocation", "status": "passed" if sum(allocation.values()) + reserve <= wall_clock else "failed",
                               "stage_total_seconds": sum(allocation.values()), "reserve_seconds": reserve})
        except Exception as exc:
            checks.append({"id": f"policy:{name}_budget", "status": "failed", "message": f"{type(exc).__name__}: {exc}"})
    return checks


def run_preflight(skill_root: Path) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    for module_name, package in REQUIRED_MODULES.items():
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            checks.append(
                {
                    "id": f"python_module:{module_name}",
                    "status": "failed",
                    "package": package,
                    "message": f"{type(exc).__name__}: {exc}",
                }
            )
        else:
            checks.append({"id": f"python_module:{module_name}", "status": "passed", "package": package})

    try:
        from zoneinfo import ZoneInfo
        ZoneInfo("Asia/Shanghai")
        checks.append({"id": "python_module:timezone_data", "status": "passed"})
    except Exception as exc:
        checks.append({"id": "python_module:timezone_data", "status": "failed",
                       "package": "tzdata", "message": f"{type(exc).__name__}: {exc}"})

    required_files = [
        "SKILL.md",
        "config/execution_policy.v1.json",
        "config/formal_writing_rules.v1.json",
        "config/source_registry.v1.json",
        "scripts/run_cwh_resumable_pipeline.py",
        "scripts/cwh_model_contract.py",
        "scripts/cwh_viewpoint_gate.py",
        "scripts/cwh_writing_rules.py",
        "scripts/complete_cwh_evidence_structure.py",
        "scripts/cwh_timing_report.py",
        "scripts/cwh_scoped_process.py",
        "scripts/run_cwh_model_worker.py",
        "scripts/run_cwh_inline_review.py",
        "scripts/run_cwh_batched_viewpoints.py",
        "scripts/cwh_worker_observations.py",
        "scripts/cwh_authoring_packet.py",
        "scripts/cwh_json_transport.py",
        "scripts/cwh_host_research.py",
        "scripts/cwh_public_reader.py",
        "scripts/cwh_semantic_compiler.py",
        "scripts/cwh_source_spans.py",
        "scripts/cwh_semantic_repairs.py",
        "scripts/cwh_review_repair.py",
        "scripts/cwh_weibo_capture.py",
        "scripts/cwh_toutiao_capture.py",
        "scripts/cwh_comment_semantics.py",
        "scripts/run_cwh_compiled_worker.py",
        "scripts/build_cwh_review_delivery.py",
        "scripts/prepare_cwh_corpus_index.py",
        "scripts/cwh_pipeline_runtime.py",
        "scripts/normalize_cwh_analysis.py",
        "scripts/cwh_orchestrator.py",
        "scripts/generate_dashboard.py",
        "assets/cwh_dashboard_template.html",
        "templates/formal_report_template_complete_20260714.docx",
    ]
    for relative in required_files:
        path = skill_root / relative
        checks.append(
            {
                "id": f"file:{relative}",
                "status": "passed" if path.is_file() and path.stat().st_size > 0 else "failed",
                "path": str(path),
            }
        )

    template = skill_root / "assets" / "cwh_dashboard_template.html"
    try:
        placeholder_count = template.read_text(encoding="utf-8").count("__DASHBOARD_DATA__")
        checks.append({"id": "template:dashboard_data_slot", "status": "passed" if placeholder_count == 1 else "failed", "placeholder_count": placeholder_count})
    except (OSError, UnicodeError) as exc:
        checks.append({"id": "template:dashboard_data_slot", "status": "failed", "message": type(exc).__name__})

    try:
        policy = json.loads((skill_root / "config" / "execution_policy.v1.json").read_text(encoding="utf-8"))
        checks.extend(execution_policy_checks(policy))
    except Exception as exc:
        checks.append({"id": "policy:execution_policy", "status": "failed", "message": f"{type(exc).__name__}: {exc}"})

    try:
        writing = json.loads((skill_root / "config" / "formal_writing_rules.v1.json").read_text(encoding="utf-8"))
        required_sections = {"document", "propagation", "viewpoint", "comments", "hotwords", "overseas", "style"}
        missing_sections = sorted(required_sections - set(writing))
        density = writing.get("viewpoint", {}).get("density_gate", {})
        valid_density = (
            density.get("minimum_independent_voices") == 2
            and density.get("minimum_details_cjk") == 120
            and density.get("exception_required_fields") == ["reason", "search_evidence", "reviewed_by"]
        )
        checks.append({
            "id": "policy:formal_writing_rules",
            "status": "failed" if missing_sections or not valid_density else "passed",
            "missing_sections": missing_sections,
            "density_gate_valid": valid_density,
        })
    except Exception as exc:
        checks.append({"id": "policy:formal_writing_rules", "status": "failed", "message": f"{type(exc).__name__}: {exc}"})

    failed = [row for row in checks if row["status"] != "passed"]
    module_failed = any(str(row.get("id") or "").startswith("python_module:") for row in failed)
    return {
        "schema_version": "1.0",
        "status": "passed" if not failed else "blocked",
        "python": sys.version,
        "platform": platform.platform(),
        "checks": checks,
        "problems": [row["id"] for row in failed],
        "repair_command": (
            f'"{sys.executable}" -m pip install -r "{skill_root / "deploy" / "with" / "requirements.txt"}"'
            if module_failed
            else ""
        ),
        "operator_action": (
            "Restore or repair the failed Skill files or policies; dependency installation cannot fix them."
            if failed and not module_failed
            else ""
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the CWH runtime before starting an expensive model workflow.")
    parser.add_argument("--skill-root", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    payload = run_preflight(Path(args.skill_root).resolve())
    if args.output:
        target = Path(args.output).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
