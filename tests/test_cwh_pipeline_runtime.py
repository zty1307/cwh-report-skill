from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "cwh_pipeline_runtime.py"
SPEC = importlib.util.spec_from_file_location("cwh_pipeline_runtime", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class PipelineRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def runner(self, executors, *, maximum=2):
        specs = [
            MODULE.StageSpec(
                "prepare",
                "准备数据",
                artifacts=(MODULE.ArtifactSpec("prepared", "prepared.json"),),
                max_attempts=maximum,
            ),
            MODULE.StageSpec(
                "review",
                "AI审核",
                dependencies=("prepare",),
                artifacts=(MODULE.ArtifactSpec("review", "review.json"),),
                max_attempts=maximum,
                kind="ai",
            ),
            MODULE.StageSpec(
                "render",
                "生成报告",
                dependencies=("review",),
                artifacts=(MODULE.ArtifactSpec("report", "report.docx"),),
                max_attempts=maximum,
            ),
        ]
        return MODULE.PipelineRunner(
            self.root,
            specs,
            executors,
            pipeline_name="test",
            input_contract={"agenda": "test", "files": ["a.xlsx"]},
        )

    def test_waiting_ai_blocks_downstream_and_resume_keeps_checkpoint(self) -> None:
        calls = {"prepare": 0, "review": 0, "render": 0}

        def prepare(runner, spec):
            calls["prepare"] += 1
            (self.root / "prepared.json").write_text("{}", encoding="utf-8")
            return MODULE.StageOutcome.succeeded("prepared")

        def review(runner, spec):
            calls["review"] += 1
            target = self.root / "review.json"
            if not target.exists():
                return MODULE.StageOutcome.waiting(
                    "waiting_ai",
                    "需要AI审核",
                    details={"expected_output": str(target)},
                )
            return MODULE.StageOutcome.succeeded("reviewed")

        def render(runner, spec):
            calls["render"] += 1
            (self.root / "report.docx").write_bytes(b"docx")
            return MODULE.StageOutcome.succeeded("rendered")

        runner = self.runner({"prepare": prepare, "review": review, "render": render})
        first = runner.run()
        self.assertEqual("waiting_ai", first["status"])
        self.assertEqual("review", first["current_stage"])
        self.assertEqual(0, calls["render"])

        (self.root / "review.json").write_text('{"approved": true}', encoding="utf-8")
        resumed = runner.run()
        self.assertEqual("succeeded", resumed["status"])
        self.assertEqual(1, calls["prepare"])
        self.assertEqual(2, calls["review"])
        self.assertEqual(1, calls["render"])
        self.assertTrue((self.root / "pipeline_events.jsonl").exists())

    def test_transient_failure_retries_only_current_stage(self) -> None:
        attempts = {"prepare": 0, "review": 0, "render": 0}

        def prepare(runner, spec):
            attempts["prepare"] += 1
            (self.root / "prepared.json").write_text("{}", encoding="utf-8")
            return MODULE.StageOutcome.succeeded()

        def review(runner, spec):
            attempts["review"] += 1
            if attempts["review"] == 1:
                return MODULE.StageOutcome.failed("temporary", retryable=True, error_code="timeout")
            (self.root / "review.json").write_text("{}", encoding="utf-8")
            return MODULE.StageOutcome.succeeded()

        def render(runner, spec):
            attempts["render"] += 1
            (self.root / "report.docx").write_bytes(b"docx")
            return MODULE.StageOutcome.succeeded()

        state = self.runner({"prepare": prepare, "review": review, "render": render}).run()
        self.assertEqual("succeeded", state["status"])
        self.assertEqual({"prepare": 1, "review": 2, "render": 1}, attempts)

    def test_missing_required_artifact_fails_gate(self) -> None:
        def prepare(runner, spec):
            return MODULE.StageOutcome.succeeded("claimed success")

        runner = self.runner(
            {
                "prepare": prepare,
                "review": lambda *_: MODULE.StageOutcome.succeeded(),
                "render": lambda *_: MODULE.StageOutcome.succeeded(),
            },
            maximum=1,
        )
        state = runner.run()
        self.assertEqual("failed", state["status"])
        stage = state["stages"][0]
        self.assertEqual("artifact_validation_failed", stage["last_error"]["code"])
        self.assertEqual("prepare", state["next_action"]["stage_id"])

    def test_interrupted_running_stage_is_recovered(self) -> None:
        def prepare(runner, spec):
            (self.root / "prepared.json").write_text("{}", encoding="utf-8")
            return MODULE.StageOutcome.succeeded()

        executors = {
            "prepare": prepare,
            "review": lambda *_: MODULE.StageOutcome.waiting("waiting_ai", "wait"),
            "render": lambda *_: MODULE.StageOutcome.succeeded(),
        }
        runner = self.runner(executors)
        state = json.loads(runner.state_path.read_text(encoding="utf-8"))
        state["stages"][0]["status"] = "running"
        MODULE.atomic_write_json(runner.state_path, state)

        recovered = self.runner(executors)
        self.assertEqual("interrupted", recovered.stage_state("prepare")["status"])
        resumed = recovered.run()
        self.assertEqual("waiting_ai", resumed["status"])
        self.assertEqual("succeeded", recovered.stage_state("prepare")["status"])

    def test_changed_artifact_invalidates_cached_stage(self) -> None:
        calls = {"prepare": 0, "review": 0, "render": 0}

        def prepare(runner, spec):
            calls["prepare"] += 1
            (self.root / "prepared.json").write_text(json.dumps(calls["prepare"]), encoding="utf-8")
            return MODULE.StageOutcome.succeeded()

        def review(runner, spec):
            calls["review"] += 1
            (self.root / "review.json").write_text(json.dumps(calls["review"]), encoding="utf-8")
            return MODULE.StageOutcome.succeeded()

        def render(runner, spec):
            calls["render"] += 1
            (self.root / "report.docx").write_bytes(str(calls["render"]).encode())
            return MODULE.StageOutcome.succeeded()

        runner = self.runner({"prepare": prepare, "review": review, "render": render})
        self.assertEqual("succeeded", runner.run()["status"])
        (self.root / "prepared.json").write_text("tampered", encoding="utf-8")
        self.assertEqual("succeeded", runner.run()["status"])
        self.assertEqual({"prepare": 2, "review": 2, "render": 2}, calls)


if __name__ == "__main__":
    unittest.main()
