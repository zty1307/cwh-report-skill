from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from cwh_scoped_process import run_scoped_command


TERMINAL_STAGE_STATUSES = {"succeeded", "skipped"}
WAITING_STAGE_STATUSES = {"waiting_ai", "waiting_login", "waiting_review", "blocked"}
ACTIVE_STAGE_STATUSES = {"queued", "running", "retrying"}
PIPELINE_TERMINAL_STATUSES = {"succeeded", "failed", "blocked"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        # Windows readers/indexers can briefly deny replacement. Never truncate
        # or delete the accepted checkpoint to work around an occupied file.
        delays = (0.05, 0.1, 0.2, 0.4, 0.8, 1.0)
        for attempt in range(len(delays) + 1):
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                if attempt == len(delays):
                    raise
                time.sleep(delays[attempt])
    finally:
        # This path belongs exclusively to this write. Cleanup must not hide
        # the original error when a scanner also holds the temporary file.
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


@dataclass(frozen=True)
class ArtifactSpec:
    name: str
    path: str
    required: bool = True
    minimum_bytes: int = 1


@dataclass(frozen=True)
class StageSpec:
    stage_id: str
    label: str
    dependencies: tuple[str, ...] = ()
    artifacts: tuple[ArtifactSpec, ...] = ()
    max_attempts: int = 2
    retry_delay_seconds: float = 1.0
    transient_exit_codes: tuple[int, ...] = (75, 124)
    kind: str = "script"


@dataclass
class StageOutcome:
    status: str
    message: str = ""
    artifacts: dict[str, str] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)
    retryable: bool = False
    error_code: str = ""

    @classmethod
    def succeeded(cls, message: str = "", **kwargs: Any) -> "StageOutcome":
        return cls("succeeded", message=message, **kwargs)

    @classmethod
    def waiting(cls, status: str, message: str, **kwargs: Any) -> "StageOutcome":
        if status not in WAITING_STAGE_STATUSES:
            raise ValueError(f"Unsupported waiting status: {status}")
        return cls(status, message=message, **kwargs)

    @classmethod
    def failed(
        cls,
        message: str,
        *,
        retryable: bool = False,
        error_code: str = "stage_failed",
        **kwargs: Any,
    ) -> "StageOutcome":
        return cls(
            "failed",
            message=message,
            retryable=retryable,
            error_code=error_code,
            **kwargs,
        )


StageExecutor = Callable[["PipelineRunner", StageSpec], StageOutcome]


class PipelineBusyError(RuntimeError):
    pass


class PipelineLock:
    def __init__(self, path: Path, *, stale_after_seconds: int = 6 * 60 * 60):
        self.path = path
        self.stale_after_seconds = stale_after_seconds
        self.acquired = False

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        if os.name == "nt":
            # os.kill(pid, 0) is not a non-mutating process probe on Windows.
            import ctypes
            from ctypes import wintypes

            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            kernel.GetExitCodeProcess.restype = wintypes.BOOL
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel.CloseHandle.restype = wintypes.BOOL
            handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not handle:
                # Access denied/unknown errors must not authorize lock stealing.
                return ctypes.get_last_error() != 87  # ERROR_INVALID_PARAMETER: absent PID
            try:
                code = wintypes.DWORD()
                return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
            finally:
                kernel.CloseHandle(handle)
        try:
            os.kill(pid, 0)
        except PermissionError:
            return True
        except OSError:
            return False
        return True

    def __enter__(self) -> "PipelineLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                payload = {
                    "pid": os.getpid(),
                    "host": socket.gethostname(),
                    "created_at": utc_now(),
                    "created_epoch": time.time(),
                }
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False)
                self.acquired = True
                return self
            except FileExistsError:
                try:
                    current = json.loads(self.path.read_text(encoding="utf-8"))
                except (OSError, ValueError, json.JSONDecodeError):
                    current = {}
                age = time.time() - float(current.get("created_epoch") or self.path.stat().st_mtime)
                same_host = str(current.get("host") or "") == socket.gethostname()
                alive = same_host and self._pid_alive(int(current.get("pid") or 0))
                if (same_host and not alive and current.get("pid")) or (not same_host and age > self.stale_after_seconds):
                    self.path.unlink(missing_ok=True)
                    continue
                raise PipelineBusyError(
                    f"Pipeline is already running under PID {current.get('pid')} on {current.get('host')}."
                )
        raise PipelineBusyError("Unable to acquire pipeline lock.")

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.acquired:
            self.path.unlink(missing_ok=True)


class PipelineRunner:
    """Durable stage runner with atomic checkpoints and deterministic resume behavior."""

    STATE_VERSION = 1

    def __init__(
        self,
        root: Path,
        specs: Iterable[StageSpec],
        executors: dict[str, StageExecutor],
        *,
        pipeline_name: str,
        input_contract: dict[str, Any],
    ):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.root / "pipeline_state.json"
        self.events_path = self.root / "pipeline_events.jsonl"
        self.lock_path = self.root / ".pipeline.lock"
        self.logs_dir = self.root / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.specs = list(specs)
        self.spec_by_id = {spec.stage_id: spec for spec in self.specs}
        if len(self.spec_by_id) != len(self.specs):
            raise ValueError("Duplicate pipeline stage id.")
        self.executors = executors
        self.pipeline_name = pipeline_name
        self.input_contract = input_contract
        self._validate_graph()
        # Loading can recover an interrupted checkpoint; protect that write
        # from a second controller while the real worker is still running.
        with PipelineLock(self.lock_path):
            self.state = self._load_or_initialize()

    def _validate_graph(self) -> None:
        seen: set[str] = set()
        for spec in self.specs:
            missing = [item for item in spec.dependencies if item not in seen]
            if missing:
                raise ValueError(f"Stage {spec.stage_id} has missing or forward dependencies: {missing}")
            seen.add(spec.stage_id)
            if spec.stage_id not in self.executors:
                raise ValueError(f"No executor registered for stage {spec.stage_id}")

    def _new_state(self) -> dict[str, Any]:
        created = utc_now()
        input_fingerprint = stable_hash(self.input_contract)
        return {
            "schema_version": self.STATE_VERSION,
            "pipeline_id": uuid.uuid4().hex,
            "pipeline_name": self.pipeline_name,
            "status": "pending",
            "created_at": created,
            "updated_at": created,
            "input_contract": self.input_contract,
            "input_fingerprint": input_fingerprint,
            "current_stage": "",
            "next_action": {},
            "stages": [
                {
                    "stage_id": spec.stage_id,
                    "label": spec.label,
                    "kind": spec.kind,
                    "dependencies": list(spec.dependencies),
                    "status": "pending",
                    "attempts": 0,
                    "total_attempts": 0,
                    "retry_cycles": 0,
                    "command_count": 0,
                    "wait_count": 0,
                    "max_attempts": spec.max_attempts,
                    "message": "",
                    "artifacts": {},
                    "artifact_hashes": {},
                    "input_fingerprint": "",
                    "output_fingerprint": "",
                    "started_at": "",
                    "finished_at": "",
                    "last_error": {},
                }
                for spec in self.specs
            ],
            "run_count": 0,
        }

    def _load_or_initialize(self) -> dict[str, Any]:
        if not self.state_path.exists():
            state = self._new_state()
            atomic_write_json(self.state_path, state)
            self._event("pipeline_created", details={"input_fingerprint": state["input_fingerprint"]})
            return state
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        if int(state.get("schema_version") or 0) != self.STATE_VERSION:
            raise ValueError("Unsupported pipeline state schema version.")
        if state.get("input_fingerprint") != stable_hash(self.input_contract):
            raise ValueError(
                "Pipeline input contract changed. Start a new job or explicitly invalidate the existing pipeline."
            )
        known = {row.get("stage_id") for row in state.get("stages") or []}
        expected = {spec.stage_id for spec in self.specs}
        if known != expected:
            raise ValueError("Pipeline stage definition changed for an existing job; migration is required.")
        self._recover_interrupted_state(state)
        self._validate_event_history(state)
        return state

    def _validate_event_history(self, state: dict[str, Any]) -> None:
        """Reject a state file that was rolled back behind its append-only event log."""
        if not self.events_path.exists():
            if state.get("status") == "succeeded" or any(
                row.get("status") in TERMINAL_STAGE_STATUSES for row in state.get("stages") or []
            ):
                raise ValueError("Completed pipeline state has no event history; restore the event log or start a new job.")
            return
        max_run_count = 0
        last_terminal_event = ""
        last_stage_terminal: dict[str, dict[str, Any]] = {}
        for raw_line in self.events_path.read_text(encoding="utf-8").splitlines():
            if not raw_line.strip():
                continue
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if event.get("pipeline_id") not in {"", state.get("pipeline_id")}:
                continue
            if event.get("event") == "pipeline_run_started":
                max_run_count = max(max_run_count, int((event.get("details") or {}).get("run_count") or 0))
            if event.get("event") in {"pipeline_succeeded", "stage_failed", "stage_waiting"}:
                last_terminal_event = str(event.get("event") or "")
            if event.get("stage_id") and event.get("event") in {"stage_succeeded", "stage_failed", "stage_waiting"}:
                last_stage_terminal[str(event["stage_id"])] = event
        if int(state.get("run_count") or 0) < max_run_count:
            raise ValueError("Pipeline state is older than its append-only event history; restore the latest state or start a new job.")
        if state.get("status") == "succeeded" and last_terminal_event and last_terminal_event != "pipeline_succeeded":
            raise ValueError("Pipeline state claims success but the latest event history does not; restore the latest state or start a new job.")
        for row in state.get("stages") or []:
            if row.get("status") not in TERMINAL_STAGE_STATUSES:
                continue
            event = last_stage_terminal.get(str(row.get("stage_id") or ""))
            if not event or event.get("event") != "stage_succeeded":
                raise ValueError(
                    f"Stage {row.get('stage_id')} claims success without a matching latest success event; "
                    "restore the latest state or start a new job."
                )
            event_fingerprint = str((event.get("details") or {}).get("output_fingerprint") or "")
            if event_fingerprint and event_fingerprint != str(row.get("output_fingerprint") or ""):
                raise ValueError(f"Stage {row.get('stage_id')} output fingerprint conflicts with the append-only event history.")

    def _recover_interrupted_state(self, state: dict[str, Any]) -> None:
        changed = False
        for row in state.get("stages") or []:
            if row.get("status") in ACTIVE_STAGE_STATUSES:
                row["status"] = "interrupted"
                row["finished_at"] = utc_now()
                row["message"] = "上次执行在该节点中断，可从本节点继续。"
                row["last_error"] = {
                    "code": "process_interrupted",
                    "message": "The previous pipeline process ended before the stage reached a terminal state.",
                }
                changed = True
        if changed:
            state["status"] = "interrupted"
            state["updated_at"] = utc_now()
            atomic_write_json(self.state_path, state)

    def _save(self) -> None:
        self.state["updated_at"] = utc_now()
        if self.state.get("budget_started_epoch"):
            self.state["wall_clock_elapsed_seconds"] = round(max(
                0.0, time.time() - self.state["budget_started_epoch"]
            ), 3)
        atomic_write_json(self.state_path, self.state)

    def remaining_budget_seconds(self, stage_id: str = "") -> float | None:
        limits: list[float] = []
        now = time.time()
        budget = float(self.input_contract.get("wall_clock_budget_seconds") or 0)
        started = self.state.get("budget_started_epoch")
        if budget and started is not None:
            limits.append(budget - max(0.0, now - float(started)))
        if stage_id:
            research_deadline = float(self.input_contract.get("research_deadline_seconds") or 0)
            if research_deadline and started is not None and stage_id not in {"render", "delivery_gate"}:
                limits.append(research_deadline - max(0.0, now - float(started)))
            row = self.stage_state(stage_id)
            stage_budget = float((self.input_contract.get("stage_timeouts_seconds") or {}).get(stage_id) or 0)
            stage_started = row.get("budget_started_epoch")
            if stage_budget and stage_started is not None:
                limits.append(stage_budget - max(0.0, now - float(stage_started)))
        return min(limits) if limits else None

    def _stop_if_budget_exhausted(self, stage_id: str) -> bool:
        remaining = self.remaining_budget_seconds(stage_id)
        if remaining is None or remaining > 0:
            return False
        message = "任务或节点累计时间预算已耗尽（含等待与重试）；保留断点和审计，记录本次超时。新一轮测试须使用新任务目录，run/invalidate不会重置预算。"
        self.stage_state(stage_id).update(status="blocked", message=message)
        self.state.update(status="blocked", current_stage=stage_id, next_action={
            "type": "time_budget_exhausted", "stage_id": stage_id, "message": message,
        })
        self._save()
        self._event("pipeline_time_budget_exhausted", stage_id=stage_id, details=self.state["next_action"])
        return True

    def _event(self, event: str, *, stage_id: str = "", details: dict[str, Any] | None = None) -> None:
        row = {
            "timestamp": utc_now(),
            "pipeline_id": self.state.get("pipeline_id") if hasattr(self, "state") else "",
            "event": event,
            "stage_id": stage_id,
            "details": details or {},
        }
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def stage_state(self, stage_id: str) -> dict[str, Any]:
        for row in self.state.get("stages") or []:
            if row.get("stage_id") == stage_id:
                return row
        raise KeyError(stage_id)

    def artifact_path(self, value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else (self.root / path).resolve()

    def _artifact_snapshot(self, spec: StageSpec, outcome: StageOutcome) -> tuple[dict[str, str], dict[str, str]]:
        declared = {item.name: item for item in spec.artifacts}
        values = {item.name: item.path for item in spec.artifacts}
        values.update({key: str(value) for key, value in outcome.artifacts.items() if value})
        hashes: dict[str, str] = {}
        for name, artifact in declared.items():
            value = values.get(name, artifact.path)
            path = self.artifact_path(value)
            if artifact.required and not path.exists():
                raise FileNotFoundError(f"Required artifact {name} is missing: {path}")
            if path.exists():
                if path.is_file() and path.stat().st_size < artifact.minimum_bytes:
                    raise ValueError(f"Artifact {name} is unexpectedly small: {path}")
                if path.is_file():
                    hashes[name] = sha256_file(path)
                elif path.is_dir():
                    children = sorted(
                        (str(child.relative_to(path)), child.stat().st_size)
                        for child in path.rglob("*")
                        if child.is_file()
                    )
                    hashes[name] = stable_hash(children)
        return values, hashes

    def _stage_input_fingerprint(self, spec: StageSpec) -> str:
        upstream = {
            dependency: self.stage_state(dependency).get("output_fingerprint")
            for dependency in spec.dependencies
        }
        return stable_hash(
            {
                "pipeline_input": self.state.get("input_fingerprint"),
                "stage": spec.stage_id,
                "kind": spec.kind,
                "stage_definition": {
                    "dependencies": list(spec.dependencies),
                    "artifacts": [
                        {
                            "name": item.name,
                            "path": item.path,
                            "required": item.required,
                            "minimum_bytes": item.minimum_bytes,
                        }
                        for item in spec.artifacts
                    ],
                    "max_attempts": spec.max_attempts,
                },
                "upstream": upstream,
            }
        )

    def _cached_stage_is_valid(self, spec: StageSpec, row: dict[str, Any], fingerprint: str) -> bool:
        if row.get("status") not in TERMINAL_STAGE_STATUSES:
            return False
        if row.get("input_fingerprint") != fingerprint:
            return False
        expected = row.get("artifact_hashes") or {}
        for name, expected_hash in expected.items():
            value = (row.get("artifacts") or {}).get(name)
            if not value:
                return False
            path = self.artifact_path(value)
            if not path.exists() or not path.is_file() or sha256_file(path) != expected_hash:
                return False
        for artifact in spec.artifacts:
            if artifact.required and not self.artifact_path((row.get("artifacts") or {}).get(artifact.name, artifact.path)).exists():
                return False
        return True

    def run_command(
        self,
        stage_id: str,
        command: list[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> tuple[int, Path]:
        row = self.stage_state(stage_id)
        if timeout_seconds is None:
            configured = (self.input_contract.get("stage_timeouts_seconds") or {}).get(stage_id)
            timeout_seconds = int(configured) if configured not in (None, "", 0) else None
        attempt = int(row.get("total_attempts") or row.get("attempts") or 1)
        row["command_count"] = int(row.get("command_count") or 0) + 1
        command_count = row["command_count"]
        self._save()
        log_path = self.logs_dir / f"{stage_id}.attempt-{attempt}.command-{command_count}.log"
        with log_path.open("w", encoding="utf-8", errors="replace") as log:
            log.write("COMMAND: " + json.dumps(command, ensure_ascii=False) + "\n")
            log.flush()
            remaining = self.remaining_budget_seconds(stage_id)
            if remaining is not None:
                if remaining <= 0:
                    log.write("TIMEOUT: cumulative task/stage budget exhausted before command launch\n")
                    return 124, log_path
                timeout_seconds = min(timeout_seconds, remaining) if timeout_seconds is not None else remaining
            command_started = time.monotonic()
            exit_code: int | None = None
            try:
                exit_code = run_scoped_command(
                    command,
                    cwd=str(cwd or self.root),
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=timeout_seconds,
                )
                return exit_code, log_path
            except subprocess.TimeoutExpired:
                log.write(f"\nTIMEOUT after {timeout_seconds} seconds\n")
                exit_code = 124
                return 124, log_path
            finally:
                self._event("command_finished", stage_id=stage_id, details={
                    "total_attempt": attempt,
                    "command_index": command_count,
                    "duration_seconds": round(time.monotonic() - command_started, 3),
                    "exit_code": exit_code,
                    "log_path": str(log_path),
                })

    def invalidate_from(self, stage_id: str, *, reason: str) -> None:
        found = False
        for row in self.state.get("stages") or []:
            if row.get("stage_id") == stage_id:
                found = True
            if not found:
                continue
            row.update(
                {
                    "status": "pending",
                    "attempts": 0,
                    "wait_count": 0,
                    "message": "",
                    "input_fingerprint": "",
                    "output_fingerprint": "",
                    "started_at": "",
                    "finished_at": "",
                    "last_error": {},
                    "artifacts": {},
                    "artifact_hashes": {},
                }
            )
        if not found:
            raise KeyError(stage_id)
        self.state["status"] = "pending"
        self.state["current_stage"] = ""
        self.state["next_action"] = {}
        self.state.pop("completed_elapsed_seconds", None)
        self._save()
        self._event("pipeline_invalidated", stage_id=stage_id, details={"reason": reason})

    def _dependencies_ready(self, spec: StageSpec) -> bool:
        return all(self.stage_state(item).get("status") in TERMINAL_STAGE_STATUSES for item in spec.dependencies)

    def run(self, *, until_stage: str = "") -> dict[str, Any]:
        with PipelineLock(self.lock_path):
            self.state = json.loads(self.state_path.read_text(encoding="utf-8"))
            self._recover_interrupted_state(self.state)
            self._validate_event_history(self.state)
            self.state.setdefault("budget_started_epoch", time.time())
            self.state["run_count"] = int(self.state.get("run_count") or 0) + 1
            self.state["status"] = "running"
            self.state["next_action"] = {}
            self._save()
            self._event("pipeline_run_started", details={"run_count": self.state["run_count"]})

            for spec in self.specs:
                row = self.stage_state(spec.stage_id)
                if not self._dependencies_ready(spec):
                    self.state["status"] = "blocked"
                    self.state["current_stage"] = spec.stage_id
                    self.state["next_action"] = {
                        "type": "repair_dependency",
                        "stage_id": spec.stage_id,
                        "message": "上游节点尚未完成，不能执行本节点。",
                    }
                    self._save()
                    return self.state

                fingerprint = self._stage_input_fingerprint(spec)
                if self._cached_stage_is_valid(spec, row, fingerprint):
                    self._event("stage_cache_hit", stage_id=spec.stage_id)
                    if until_stage == spec.stage_id:
                        break
                    continue

                if row.get("status") in TERMINAL_STAGE_STATUSES:
                    self.invalidate_from(spec.stage_id, reason="输入或上游产物发生变化")
                    row = self.stage_state(spec.stage_id)

                if row.get("status") == "failed":
                    row["attempts"] = 0
                    row["retry_cycles"] = int(row.get("retry_cycles") or 0) + 1
                    row["status"] = "pending"
                    row["message"] = "已为本次显式续跑重新开放重试预算。"
                    self._save()
                    self._event(
                        "stage_rearmed",
                        stage_id=spec.stage_id,
                        details={"retry_cycle": row["retry_cycles"]},
                    )

                last_outcome: StageOutcome | None = None
                row.setdefault("budget_started_epoch", time.time())
                if self._stop_if_budget_exhausted(spec.stage_id):
                    return self.state
                while int(row.get("attempts") or 0) < spec.max_attempts:
                    if self._stop_if_budget_exhausted(spec.stage_id):
                        return self.state
                    row["status"] = "running"
                    row["attempts"] = int(row.get("attempts") or 0) + 1
                    row["total_attempts"] = int(row.get("total_attempts") or 0) + 1
                    row["command_count"] = 0
                    row["started_at"] = utc_now()
                    row["finished_at"] = ""
                    row["message"] = ""
                    row["input_fingerprint"] = fingerprint
                    row["last_error"] = {}
                    self.state["current_stage"] = spec.stage_id
                    self._save()
                    self._event(
                        "stage_started",
                        stage_id=spec.stage_id,
                        details={"attempt": row["attempts"], "total_attempt": row["total_attempts"]},
                    )
                    try:
                        outcome = self.executors[spec.stage_id](self, spec)
                    except Exception as exc:
                        outcome = StageOutcome.failed(
                            f"{type(exc).__name__}: {exc}",
                            retryable=False,
                            error_code="uncaught_exception",
                        )
                    last_outcome = outcome
                    if self._stop_if_budget_exhausted(spec.stage_id):
                        return self.state

                    if outcome.status == "succeeded":
                        try:
                            artifacts, hashes = self._artifact_snapshot(spec, outcome)
                        except Exception as exc:
                            outcome = StageOutcome.failed(
                                f"产物校验失败：{type(exc).__name__}: {exc}",
                                retryable=False,
                                error_code="artifact_validation_failed",
                            )
                            last_outcome = outcome
                        else:
                            if self._stop_if_budget_exhausted(spec.stage_id):
                                return self.state
                            row.update(
                                {
                                    "status": "succeeded",
                                    "message": outcome.message,
                                    "finished_at": utc_now(),
                                    "artifacts": artifacts,
                                    "artifact_hashes": hashes,
                                    "output_fingerprint": stable_hash(hashes),
                                    "details": outcome.details,
                                }
                            )
                            # Journal first: a crash before the checkpoint save
                            # leaves a resumable running stage, never a success
                            # snapshot without its required success event.
                            self._event(
                                "stage_succeeded",
                                stage_id=spec.stage_id,
                                details={
                                    "artifacts": artifacts,
                                    "artifact_hashes": hashes,
                                    "output_fingerprint": row["output_fingerprint"],
                                },
                            )
                            self._save()
                            break

                    if outcome.status in WAITING_STAGE_STATUSES:
                        # Waiting for an external model, login or review is not
                        # a failed execution attempt. A job may be inspected or
                        # resumed repeatedly without exhausting its retry budget.
                        row["attempts"] = max(0, int(row.get("attempts") or 0) - 1)
                        row["wait_count"] = int(row.get("wait_count") or 0) + 1
                        row.update(
                            {
                                "status": outcome.status,
                                "message": outcome.message,
                                "finished_at": utc_now(),
                                "details": outcome.details,
                            }
                        )
                        self.state["status"] = outcome.status
                        self.state["next_action"] = {
                            "type": outcome.status,
                            "stage_id": spec.stage_id,
                            "message": outcome.message,
                            **outcome.details,
                        }
                        self._save()
                        self._event("stage_waiting", stage_id=spec.stage_id, details=self.state["next_action"])
                        return self.state

                    row["last_error"] = {
                        "code": outcome.error_code or "stage_failed",
                        "message": outcome.message,
                        "retryable": bool(outcome.retryable),
                    }
                    row["message"] = outcome.message
                    row["finished_at"] = utc_now()
                    if outcome.retryable and int(row["attempts"]) < spec.max_attempts:
                        row["status"] = "retrying"
                        self._save()
                        self._event("stage_retrying", stage_id=spec.stage_id, details=row["last_error"])
                        time.sleep(spec.retry_delay_seconds * int(row["attempts"]))
                        continue
                    row["status"] = "failed"
                    self.state["status"] = "failed"
                    self.state["next_action"] = {
                        "type": "retry_stage",
                        "stage_id": spec.stage_id,
                        "message": outcome.message,
                    }
                    self._save()
                    self._event("stage_failed", stage_id=spec.stage_id, details=row["last_error"])
                    return self.state

                if row.get("status") != "succeeded":
                    message = last_outcome.message if last_outcome else "Stage did not complete."
                    row["status"] = "failed"
                    row["message"] = message
                    row["finished_at"] = utc_now()
                    self.state["status"] = "failed"
                    self.state["next_action"] = {
                        "type": "retry_stage",
                        "stage_id": spec.stage_id,
                        "message": message,
                    }
                    self._save()
                    return self.state

                if until_stage == spec.stage_id:
                    self.state["status"] = "paused"
                    self.state["next_action"] = {
                        "type": "resume",
                        "stage_id": "",
                        "message": f"已按要求执行至 {spec.label}。",
                    }
                    self._save()
                    return self.state

            self.state["status"] = "succeeded"
            self.state["current_stage"] = ""
            self.state["next_action"] = {}
            self.state["finished_at"] = utc_now()
            self.state.setdefault("completed_elapsed_seconds", round(max(
                0.0, time.time() - self.state["budget_started_epoch"]
            ), 3))
            self._event("pipeline_succeeded")
            self._save()
            return self.state


def command_outcome(
    runner: PipelineRunner,
    spec: StageSpec,
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout_seconds: int | None = None,
    success_message: str = "",
) -> StageOutcome:
    code, log_path = runner.run_command(
        spec.stage_id,
        command,
        cwd=cwd,
        env=env,
        timeout_seconds=timeout_seconds,
    )
    if code == 0:
        return StageOutcome.succeeded(success_message, details={"log_path": str(log_path), "exit_code": code})
    return StageOutcome.failed(
        f"命令退出码为 {code}，详见 {log_path}",
        retryable=code in spec.transient_exit_codes,
        error_code=f"exit_{code}",
        details={"log_path": str(log_path), "exit_code": code},
    )
