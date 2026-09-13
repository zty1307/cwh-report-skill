from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


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

    def test_atomic_checkpoint_retries_transient_lock_without_losing_old_state(self) -> None:
        target = self.root / "checkpoint.json"
        target.write_text('{"version": 1}', encoding="utf-8")
        replace = MODULE.os.replace
        calls = []

        def temporarily_locked(source, destination):
            calls.append(source)
            self.assertEqual({"version": 1}, json.loads(target.read_text(encoding="utf-8")))
            if len(calls) < 3:
                raise PermissionError("transient scanner lock")
            return replace(source, destination)

        with mock.patch.object(MODULE.os, "replace", side_effect=temporarily_locked), mock.patch.object(MODULE.time, "sleep"):
            MODULE.atomic_write_json(target, {"version": 2})
        self.assertEqual({"version": 2}, json.loads(target.read_text(encoding="utf-8")))
        self.assertEqual(3, len(calls))
        self.assertFalse(list(self.root.glob("*.tmp")))

    def test_live_pipeline_lock_blocks_second_controller_without_signalling_owner(self) -> None:
        lock = self.root / ".pipeline.lock"
        with MODULE.PipelineLock(lock), mock.patch.object(MODULE.os, "kill", side_effect=AssertionError("must not signal a Windows process")) if MODULE.os.name == "nt" else mock.patch.object(MODULE.os, "kill", return_value=None):
            with self.assertRaises(MODULE.PipelineBusyError):
                MODULE.PipelineRunner(self.root, [], {}, pipeline_name="locked", input_contract={})
            self.assertTrue(lock.exists())
            self.assertFalse((self.root / "pipeline_state.json").exists())

    def test_atomic_checkpoint_permanent_denial_is_bounded_and_preserves_old_state(self) -> None:
        target = self.root / "checkpoint.json"
        target.write_text('{"version": 1}', encoding="utf-8")
        with mock.patch.object(MODULE.os, "replace", side_effect=PermissionError("denied")) as replace, mock.patch.object(MODULE.time, "sleep") as sleep:
            with self.assertRaises(PermissionError):
                MODULE.atomic_write_json(target, {"version": 2})
        self.assertEqual(7, replace.call_count)
        self.assertLess(sum(call.args[0] for call in sleep.call_args_list), 3)
        self.assertEqual({"version": 1}, json.loads(target.read_text(encoding="utf-8")))
        self.assertFalse(list(self.root.glob("*.tmp")))

    def test_atomic_checkpoint_other_io_errors_are_not_retried(self) -> None:
        target = self.root / "checkpoint.json"
        with mock.patch.object(MODULE.os, "replace", side_effect=OSError("disk full")), mock.patch.object(MODULE.time, "sleep") as sleep:
            with self.assertRaisesRegex(OSError, "disk full"):
                MODULE.atomic_write_json(target, {})
        sleep.assert_not_called()
        self.assertFalse(target.exists())
        self.assertFalse(list(self.root.glob("*.tmp")))

    def test_checkpoint_failure_after_success_event_can_resume(self) -> None:
        spec = MODULE.StageSpec("prepare", "Prepare", artifacts=(MODULE.ArtifactSpec("result", "result.json"),))

        def prepare(*_):
            (self.root / "result.json").write_text("{}", encoding="utf-8")
            return MODULE.StageOutcome.succeeded()

        def runner():
            return MODULE.PipelineRunner(self.root, [spec], {"prepare": prepare}, pipeline_name="crash", input_contract={})

        interrupted = runner()
        save = interrupted._save

        def fail_checkpoint():
            if interrupted.stage_state("prepare")["status"] == "succeeded":
                raise PermissionError("persistent checkpoint denial")
            save()

        with mock.patch.object(interrupted, "_save", side_effect=fail_checkpoint):
            with self.assertRaises(PermissionError):
                interrupted.run()
        resumed = runner()
        self.assertEqual("interrupted", resumed.stage_state("prepare")["status"])
        self.assertEqual("succeeded", resumed.run()["status"])

    def test_completed_state_without_event_log_is_rejected(self) -> None:
        runner = MODULE.PipelineRunner(self.root, [], {}, pipeline_name="empty", input_contract={})
        self.assertEqual("succeeded", runner.run()["status"])
        runner.events_path.unlink()
        with self.assertRaisesRegex(ValueError, "no event history"):
            MODULE.PipelineRunner(self.root, [], {}, pipeline_name="empty", input_contract={})

    def test_wall_budget_survives_wait_resume_and_invalidate(self) -> None:
        calls = []
        spec = MODULE.StageSpec("review", "Review")

        def review(*_):
            calls.append(1)
            return MODULE.StageOutcome.waiting("waiting_ai", "wait")

        def runner():
            return MODULE.PipelineRunner(self.root, [spec], {"review": review}, pipeline_name="budget", input_contract={"wall_clock_budget_seconds": 60})

        with mock.patch.object(MODULE.time, "time", return_value=1000):
            first = runner()
            self.assertEqual("waiting_ai", first.run()["status"])
        with mock.patch.object(MODULE.time, "time", return_value=1061):
            resumed = runner()
            self.assertEqual("blocked", resumed.run()["status"])
            self.assertEqual("time_budget_exhausted", resumed.state["next_action"]["type"])
            resumed.invalidate_from("review", reason="explicit retry")
            self.assertEqual("blocked", resumed.run()["status"])
        self.assertEqual([1], calls)

    def test_commands_share_remaining_stage_budget_and_stop_after_expiry(self) -> None:
        spec = MODULE.StageSpec("review", "Review")
        runner = MODULE.PipelineRunner(self.root, [spec], {"review": lambda *_: None}, pipeline_name="budget", input_contract={"wall_clock_budget_seconds": 60, "stage_timeouts_seconds": {"review": 10}})
        runner.state["budget_started_epoch"] = 1000
        runner.stage_state("review")["budget_started_epoch"] = 1002
        with mock.patch.object(MODULE.time, "time", return_value=1008), mock.patch.object(MODULE.subprocess, "run", return_value=mock.Mock(returncode=0)) as run:
            self.assertEqual(0, runner.run_command("review", ["unused"], timeout_seconds=100)[0])
            self.assertEqual(4, run.call_args.kwargs["timeout"])
        with mock.patch.object(MODULE.time, "time", return_value=1013), mock.patch.object(MODULE.subprocess, "run") as run:
            self.assertEqual(124, runner.run_command("review", ["unused"])[0])
            run.assert_not_called()

    def test_stage_exceeding_budget_cannot_report_success(self) -> None:
        clock = [1000]
        spec = MODULE.StageSpec("review", "Review")

        def review(*_):
            clock[0] += 11
            return MODULE.StageOutcome.succeeded()

        with mock.patch.object(MODULE.time, "time", side_effect=lambda: clock[0]):
            runner = MODULE.PipelineRunner(self.root, [spec], {"review": review}, pipeline_name="budget", input_contract={"wall_clock_budget_seconds": 60, "stage_timeouts_seconds": {"review": 10}})
            self.assertEqual("blocked", runner.run()["status"])
            self.assertEqual("time_budget_exhausted", runner.state["next_action"]["type"])

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

    def test_explicit_resume_rearms_a_failed_stage(self) -> None:
        calls = {"prepare": 0, "review": 0, "render": 0}

        def prepare(runner, spec):
            calls["prepare"] += 1
            if calls["prepare"] == 1:
                return MODULE.StageOutcome.failed("first run failed", retryable=False)
            (self.root / "prepared.json").write_text("{}", encoding="utf-8")
            return MODULE.StageOutcome.succeeded()

        def review(runner, spec):
            calls["review"] += 1
            (self.root / "review.json").write_text("{}", encoding="utf-8")
            return MODULE.StageOutcome.succeeded()

        def render(runner, spec):
            calls["render"] += 1
            (self.root / "report.docx").write_bytes(b"docx")
            return MODULE.StageOutcome.succeeded()

        runner = self.runner({"prepare": prepare, "review": review, "render": render}, maximum=1)
        self.assertEqual("failed", runner.run()["status"])
        self.assertEqual("succeeded", runner.run()["status"])
        self.assertEqual(2, runner.stage_state("prepare")["total_attempts"])
        self.assertEqual(1, runner.stage_state("prepare")["retry_cycles"])
        self.assertEqual({"prepare": 2, "review": 1, "render": 1}, calls)

    def test_rolled_back_state_cannot_override_later_failure_event(self) -> None:
        def write(name, value=b"{}"):
            path = self.root / name
            path.write_bytes(value)
            return MODULE.StageOutcome.succeeded()

        executors = {
            "prepare": lambda *_: write("prepared.json"),
            "review": lambda *_: write("review.json"),
            "render": lambda *_: write("report.docx", b"docx"),
        }
        runner = self.runner(executors)
        self.assertEqual("succeeded", runner.run()["status"])
        with runner.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "timestamp": MODULE.utc_now(),
                "pipeline_id": runner.state["pipeline_id"],
                "event": "pipeline_run_started",
                "stage_id": "",
                "details": {"run_count": 2},
            }) + "\n")
            handle.write(json.dumps({
                "timestamp": MODULE.utc_now(),
                "pipeline_id": runner.state["pipeline_id"],
                "event": "stage_failed",
                "stage_id": "render",
                "details": {"message": "later failure"},
            }) + "\n")
        with self.assertRaisesRegex(ValueError, "older than"):
            self.runner(executors)

    def test_forged_stage_success_without_event_is_rejected(self) -> None:
        def prepare(runner, spec):
            (self.root / "prepared.json").write_text("{}", encoding="utf-8")
            return MODULE.StageOutcome.succeeded()

        executors = {
            "prepare": prepare,
            "review": lambda *_: MODULE.StageOutcome.waiting("waiting_ai", "wait"),
            "render": lambda *_: MODULE.StageOutcome.succeeded(),
        }
        runner = self.runner(executors)
        self.assertEqual("waiting_ai", runner.run()["status"])
        state = json.loads(runner.state_path.read_text(encoding="utf-8"))
        review = next(row for row in state["stages"] if row["stage_id"] == "review")
        review["status"] = "succeeded"
        review["output_fingerprint"] = "fabricated"
        MODULE.atomic_write_json(runner.state_path, state)
        with self.assertRaisesRegex(ValueError, "matching latest success event"):
            self.runner(executors)


if __name__ == "__main__":
    unittest.main()
