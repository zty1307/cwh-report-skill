from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from cwh_model_contract import build_task_payload, execution_profile  # noqa: E402
from cwh_preflight import run_preflight  # noqa: E402


class ModelContractTests(unittest.TestCase):
    def test_default_profile_fits_one_hour_with_delivery_buffer(self) -> None:
        name, profile = execution_profile()
        self.assertEqual("bounded_60m", name)
        stage_total = sum(profile["stage_budgets_seconds"].values())
        self.assertLessEqual(
            stage_total + profile["reserved_delivery_buffer_seconds"],
            profile["wall_clock_budget_seconds"],
        )

    def test_task_contract_is_model_neutral_and_write_scoped(self) -> None:
        output = ROOT / "outputs" / "analysis_bundle.json"
        payload = build_task_payload(
            stage_id="domestic_viewpoints",
            task_type="domestic_viewpoint_research_and_review",
            expected_output=output,
            inputs={"research_plan": "plan.json"},
            rules=["obey plan"],
        )
        self.assertEqual([str(output)], payload["declared_outputs"])
        self.assertIn("viewpoints", payload["output_schema"]["required"])
        forbidden = " ".join(payload["forbidden_operations"])
        self.assertIn("pipeline_state.json", forbidden)
        self.assertIn("validators", forbidden)
        self.assertNotIn("Codex", payload["completion_contract"])

    def test_preflight_validates_runtime_and_policy(self) -> None:
        result = run_preflight(ROOT)
        self.assertEqual("passed", result["status"], result["problems"])
        ids = {row["id"] for row in result["checks"] if row["status"] == "passed"}
        self.assertIn("policy:bounded_60m_budget", ids)
        self.assertIn("policy:formal_writing_rules", ids)

    def test_semantic_reviewer_cannot_write_controller_verified_artifacts(self) -> None:
        payload = build_task_payload(
            stage_id="domestic_evidence_verification",
            task_type="independent_domestic_evidence_verification",
            expected_output=Path("review.json"),
            inputs={"expected_verified_bundle": "verified.json", "expected_mapping_audit": "mapping.json"},
            rules=[],
        )
        self.assertEqual(["review.json"], payload["declared_outputs"])


if __name__ == "__main__":
    unittest.main()
