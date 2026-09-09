from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_SUPERVISOR = Path("D:/Codex/2026-06-15/ai-1-1-https-drive-weixin/work/mediaspider-supervisor")
DEFAULT_MEDIA_HOME_CANDIDATES = [
    Path("D:/Codex/2026-07-07/mediacrawler-global/MediaSpider"),
    Path.home() / ".data_assistant" / "engines" / "MediaSpider",
]


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_task_path(value: str, base: Path) -> Path:
    raw = Path(value)
    if raw.is_absolute():
        return raw
    candidate = Path.cwd() / raw
    if candidate.exists():
        return candidate.resolve()
    return (base / raw).resolve()


def task_matches(task: dict[str, Any], platforms: set[str], topic_contains: str) -> bool:
    if platforms and str(task.get("platform") or "").lower() not in platforms:
        return False
    if topic_contains and topic_contains not in str(task.get("topic") or ""):
        return False
    return True


def clean_proxy_env() -> dict[str, str]:
    env = os.environ.copy()
    blocked = {"http_proxy", "https_proxy", "all_proxy", "git_http_proxy", "git_https_proxy"}
    for key in list(env):
        if key.lower() in blocked:
            env.pop(key, None)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def child_env(keep_proxy: bool) -> dict[str, str]:
    env = os.environ.copy() if keep_proxy else clean_proxy_env()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def parse_run_dir(stdout: str) -> str:
    match = re.search(r"Run directory:\s*(.+)", stdout or "")
    return match.group(1).strip() if match else ""


def should_circuit_break_platform(result: dict[str, Any]) -> bool:
    """Stop repeating a platform after a clear login/risk/timeout blocker with no data."""
    inspection = result.get("inspection") or {}
    metrics = inspection.get("metrics") or {}
    produced_rows = int(metrics.get("posts") or 0) + int(metrics.get("comments") or 0)
    if produced_rows:
        return False
    combined = f"{result.get('stdout') or ''}\n{result.get('stderr') or ''}".lower()
    blocker_markers = (
        "login required",
        "no raw output",
        "captcha",
        "risk control",
        "account risk",
        "验证码",
        "风控",
    )
    return bool(result.get("timed_out") or any(marker in combined for marker in blocker_markers))


def default_media_home() -> str:
    for candidate in DEFAULT_MEDIA_HOME_CANDIDATES:
        if (candidate / "main.py").exists():
            return str(candidate)
    return ""


def inspect_run(python: str, supervisor_dir: Path, run_dir: str) -> dict[str, Any]:
    if not run_dir:
        return {}
    inspect_script = supervisor_dir / "scripts" / "inspect_outputs.py"
    if not inspect_script.exists():
        return {"error": f"inspect_outputs.py not found: {inspect_script}"}
    output = Path(run_dir) / "inspection.json"
    proc = subprocess.run(
        [python, str(inspect_script), run_dir, "--output", str(output)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    metrics: dict[str, Any] = {
        "exit_code": proc.returncode,
        "output": str(output),
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
    }
    if output.exists():
        try:
            metrics["metrics"] = json.loads(output.read_text(encoding="utf-8"))
        except Exception as exc:
            metrics["metrics_error"] = str(exc)
    return metrics


def terminate_process_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True, check=False)
        return
    try:
        os.kill(pid, 9)
    except OSError:
        pass


def run_supervisor_command(command: list[str], keep_proxy: bool, timeout_sec: int) -> tuple[int, str, str, bool]:
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=child_env(keep_proxy),
        bufsize=1,
    )
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    def pump(pipe, sink: list[str], *, to_stderr: bool = False) -> None:
        if pipe is None:
            return
        output = sys.stderr if to_stderr else sys.stdout
        for line in iter(pipe.readline, ""):
            sink.append(line)
            print(line, end="", file=output, flush=True)
        pipe.close()

    stdout_thread = threading.Thread(target=pump, args=(proc.stdout, stdout_lines), daemon=True)
    stderr_thread = threading.Thread(
        target=pump,
        args=(proc.stderr, stderr_lines),
        kwargs={"to_stderr": True},
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()
    timed_out = False
    try:
        proc.wait(timeout=timeout_sec if timeout_sec > 0 else None)
    except subprocess.TimeoutExpired:
        timed_out = True
        terminate_process_tree(proc.pid)
        proc.wait()
    stdout_thread.join(timeout=5)
    stderr_thread.join(timeout=5)
    return (
        proc.returncode if proc.returncode is not None else -9,
        "".join(stdout_lines),
        "".join(stderr_lines),
        timed_out,
    )


def resolve_runtime_adapter() -> str:
    configured = str(os.environ.get("CWH_MEDIASPIDER_RUNTIME_ADAPTER") or "").strip()
    if configured and Path(configured).exists():
        return configured
    bundled = Path(__file__).resolve().with_name("run_mediaspider_task.py")
    return str(bundled) if bundled.exists() else ""


def resolve_adapter_python(default_python: str, media_home: str | None) -> str:
    if media_home:
        home = Path(media_home)
        candidates = [
            home / ".venv" / "Scripts" / "python.exe",
            home / ".venv" / "bin" / "python",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
    return default_python


def task_login_artifacts(task_path: Path) -> tuple[Path, Path]:
    return (
        task_path.with_suffix(".qrcode.png"),
        task_path.with_suffix(".login_state.json"),
    )


def default_profile_template(task_path: Path) -> str:
    return str((task_path.parent.parent / "browser_profiles" / "%s_user_data_dir").resolve())


def run_one(
    python: str,
    supervisor_dir: Path,
    supervisor_script: Path,
    task_path: Path,
    dry_run: bool,
    media_home: str | None,
    keep_proxy: bool,
    task_timeout_sec: int,
) -> dict[str, Any]:
    runtime_adapter = resolve_runtime_adapter()
    qr_path: Path | None = None
    state_path: Path | None = None
    if runtime_adapter and media_home and Path(runtime_adapter).exists():
        command = [resolve_adapter_python(python, media_home), runtime_adapter, str(task_path), "--media-home", media_home]
        qr_path, state_path = task_login_artifacts(task_path)
        command.extend(["--qr-path", str(qr_path), "--state-path", str(state_path)])
        profile_template = str(os.environ.get("CWH_BROWSER_PROFILE_TEMPLATE") or "").strip()
        if not profile_template:
            profile_template = default_profile_template(task_path)
        command.extend(["--profile-template", profile_template])
    else:
        command = [python, str(supervisor_script), str(task_path)]
        if media_home:
            command.extend(["--media-home", media_home])
    if dry_run:
        command.append("--dry-run")
    started_at = datetime.now().isoformat(timespec="seconds")
    returncode, stdout, stderr, timed_out = run_supervisor_command(command, keep_proxy, task_timeout_sec)
    run_dir = parse_run_dir(stdout)
    result = {
        "task": str(task_path),
        "dry_run": dry_run,
        "media_home": media_home or "",
        "run_dir": run_dir,
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "exit_code": returncode,
        "timed_out": timed_out,
        "task_timeout_sec": task_timeout_sec,
        "stdout": stdout[-4000:],
        "stderr": stderr[-4000:],
        "qrcode": str(qr_path) if qr_path else "",
        "login_state": str(state_path) if state_path else "",
        "browser_profile_template": profile_template if runtime_adapter else "",
    }
    if not dry_run:
        result["inspection"] = inspect_run(python, supervisor_dir, run_dir)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch-run CWH collection tasks through mediaspider-supervisor.")
    parser.add_argument("--manifest", required=True, help="Path to orchestrator MediaSpider-compatible manifest.json.")
    parser.add_argument("--supervisor", default=str(DEFAULT_SUPERVISOR), help="mediaspider-supervisor directory.")
    parser.add_argument("--python", default=sys.executable, help="Python executable for supervisor run_task.py.")
    parser.add_argument("--media-home", default="", help="Optional MediaSpider home override.")
    parser.add_argument("--platforms", default="", help="Optional comma list, e.g. xhs,wb,bili.")
    parser.add_argument("--topic-contains", default="", help="Optional substring filter for topic.")
    parser.add_argument("--limit", type=int, default=1, help="Maximum tasks to run in this batch. Keep small first.")
    parser.add_argument("--run", action="store_true", help="Actually run MediaSpider. Default is dry-run.")
    parser.add_argument("--keep-proxy", action="store_true", help="Keep inherited HTTP/HTTPS proxy environment variables.")
    parser.add_argument("--task-timeout-sec", type=int, default=0, help="Per-task timeout in seconds; 0 means no timeout.")
    parser.add_argument("--out", default="", help="Batch result JSON path. Defaults beside manifest.")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    manifest = load_manifest(manifest_path)
    base = manifest_path.parent
    supervisor_dir = Path(args.supervisor).resolve()
    supervisor_script = supervisor_dir / "scripts" / "run_task.py"
    if not supervisor_script.exists():
        raise SystemExit(f"supervisor run_task.py not found: {supervisor_script}")
    resolved_media_home = args.media_home or default_media_home()

    platforms = {x.strip().lower() for x in args.platforms.split(",") if x.strip()}
    selected = []
    for task in manifest.get("tasks", []):
        if not task_matches(task, platforms, args.topic_contains):
            continue
        task_value = task.get("path") or task.get("task")
        if not task_value:
            continue
        selected.append({"meta": task, "path": resolve_task_path(str(task_value), base)})
        if args.limit and len(selected) >= args.limit:
            break

    dry_run = not args.run
    results = []
    platform_blockers: dict[str, str] = {}
    for item in selected:
        platform = str(item["meta"].get("platform") or "").lower()
        if platform in platform_blockers:
            results.append({
                "task": str(item["path"]),
                "platform": platform,
                "dry_run": dry_run,
                "run_dir": "",
                "started_at": datetime.now().isoformat(timespec="seconds"),
                "finished_at": datetime.now().isoformat(timespec="seconds"),
                "exit_code": 0,
                "timed_out": False,
                "skipped": True,
                "skipped_reason": platform_blockers[platform],
                "stdout": "",
                "stderr": "",
            })
            continue
        print(
            f"[CWH comments] 开始平台={platform or 'unknown'}，任务={item['path'].stem}，"
            f"超时={args.task_timeout_sec or '不限'}秒",
            flush=True,
        )
        result = run_one(
            args.python,
            supervisor_dir,
            supervisor_script,
            item["path"],
            dry_run,
            resolved_media_home or None,
            args.keep_proxy,
            args.task_timeout_sec,
        )
        result["platform"] = platform
        results.append(result)
        print(
            f"[CWH comments] 完成平台={platform or 'unknown'}，exit={result['exit_code']}，"
            f"timed_out={result['timed_out']}，run_dir={result.get('run_dir') or '未取得'}",
            flush=True,
        )
        if not dry_run and should_circuit_break_platform(result):
            platform_blockers[platform] = "该平台首个正式任务出现登录、风控或超时阻塞，后续议题未重复触发。"

    out_path = Path(args.out) if args.out else base / ("batch_dry_run.json" if dry_run else "batch_run.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "manifest": str(manifest_path),
        "supervisor": str(supervisor_dir),
        "media_home": resolved_media_home,
        "dry_run": dry_run,
        "selected_count": len(selected),
        "platform_blockers": platform_blockers,
        "results": results,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    failed = [x for x in results if x["exit_code"] != 0]
    timed_out = [x for x in results if x.get("timed_out")]
    skipped = [x for x in results if x.get("skipped")]
    print(json.dumps({
        "status": "ok" if not failed else "failed",
        "dry_run": dry_run,
        "selected": len(selected),
        "failed": len(failed),
        "timed_out": len(timed_out),
        "skipped": len(skipped),
        "out": str(out_path),
    }, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
