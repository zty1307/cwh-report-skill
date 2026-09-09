from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parent.parent
BAIJIAHAO_ADAPTER = Path(__file__).resolve().parent / "baijiahao_browser_adapter.mjs"


def cwh_browser_profile() -> Path:
    explicit = str(os.environ.get("CWH_PLATFORM_PROFILE_DIR") or "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
    marker = local / "cwh-report-skill" / "platform_profile.json"
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
        value = str(payload.get("profile_dir") or "").strip()
        if value:
            return Path(value).expanduser().resolve()
    except (OSError, ValueError):
        pass
    return (Path.home() / ".cwh" / "browser_profile").resolve()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def find_node() -> str:
    configured = os.environ.get("CWH_NODE") or os.environ.get("WSW_NODE")
    if configured and Path(configured).exists():
        return configured
    found = shutil.which("node")
    if found:
        return found
    bundled = Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node" / "bin" / "node.exe"
    if bundled.exists():
        return str(bundled)
    raise FileNotFoundError("未找到 Node.js；请设置 CWH_NODE")


def find_wechat_skill(explicit: str = "") -> Path | None:
    candidates = [
        Path(explicit) if explicit else None,
        Path.home() / ".codex" / "skills" / "wechat-search-weread",
        Path.home() / ".agents" / "skills" / "wechat-search-weread",
        Path.home() / ".claude" / "skills" / "wechat-search-weread",
    ]
    for candidate in candidates:
        if candidate and (candidate / "scripts" / "weread_search.mjs").exists():
            return candidate.resolve()
    return None


def platform_queries(plan: dict[str, Any], platform: str) -> list[dict[str, str]]:
    source_id = {"wechat": "wechat_public", "baijiahao": "baijiahao"}[platform]
    tasks: list[dict[str, str]] = []
    for topic_index, topic in enumerate(plan.get("topics") or [], 1):
        topic_name = str(topic.get("topic") or "").strip()
        stable = next(
            (row for row in topic.get("stable_source_tasks") or [] if row.get("source_id") == source_id),
            {},
        )
        families = [str(value).strip() for value in stable.get("query_families") or [] if str(value).strip()]
        if not families:
            families = [topic_name]
        for family_index, query in enumerate(families, 1):
            query = re.sub(r"^\((?:site:[^\s)]+(?:\s+OR\s+)?)+\)\s*", "", query, flags=re.IGNORECASE)
            query = re.sub(r"^site:[^\s]+\s+", "", query, flags=re.IGNORECASE)
            tasks.append(
                {
                    "topic": topic_name,
                    "query_id": f"{platform}-t{topic_index}-q{family_index}",
                    "query": query,
                }
            )
    return tasks


def read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def run_command(command: list[str], cwd: Path, timeout: int) -> dict[str, Any]:
    started = utc_now()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return {
            "started_at": started,
            "finished_at": utc_now(),
            "exit_code": completed.returncode,
            "stdout": completed.stdout[-12000:],
            "stderr": completed.stderr[-12000:],
        }
    except subprocess.TimeoutExpired as error:
        return {
            "started_at": started,
            "finished_at": utc_now(),
            "exit_code": None,
            "timeout": True,
            "stdout": (error.stdout or "")[-12000:] if isinstance(error.stdout, str) else "",
            "stderr": (error.stderr or "")[-12000:] if isinstance(error.stderr, str) else "",
        }


def baijiahao_command(node: str, tasks: list[dict[str, str]], output_dir: Path, args: argparse.Namespace) -> list[str]:
    command = [node, str(BAIJIAHAO_ADAPTER), "--out-dir", str(output_dir), "--profile-dir", str(cwh_browser_profile()), "--max-results", str(args.max_results)]
    for task in tasks:
        command.extend(["--query", task["query"]])
    if args.headless:
        command.append("--headless")
    if args.wait_for_human_seconds:
        command.extend(["--wait-for-human-seconds", str(args.wait_for_human_seconds)])
    return command


def wechat_command(node: str, skill_dir: Path, tasks: list[dict[str, str]], output_dir: Path, args: argparse.Namespace) -> list[str]:
    script = skill_dir / "scripts" / "weread_search.mjs"
    command = [node, str(script), "--out-dir", str(output_dir), "--profile-dir", str(cwh_browser_profile()), "--max-results", str(args.max_results), "--verify-original"]
    for task in tasks:
        command.extend(["--query", task["query"]])
    if args.headless:
        command.append("--headless")
    if args.wait_for_human_seconds:
        command.extend(["--wait-for-login-seconds", str(args.wait_for_human_seconds)])
    return command


def adapter_status(platform: str, result: dict[str, Any], audit_payload: dict[str, Any]) -> str:
    if result.get("timeout"):
        return "access_failed"
    status = str(audit_payload.get("status") or "")
    if status:
        return status
    if result.get("exit_code") == 2:
        return "partial_waiting_login"
    return "completed" if result.get("exit_code") == 0 else "access_failed"


def main() -> None:
    parser = argparse.ArgumentParser(description="执行 CWH 微信公众号/百家号平台专项检索，并保留可恢复审计。")
    parser.add_argument("research_plan")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--platforms", default="baijiahao,wechat")
    parser.add_argument("--wechat-skill-dir", default="")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--max-results", type=int, default=10)
    parser.add_argument("--wait-for-human-seconds", type=int, default=0)
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()

    plan_path = Path(args.research_plan).resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    platforms = [value.strip().lower() for value in args.platforms.split(",") if value.strip()]
    unsupported = [value for value in platforms if value not in {"baijiahao", "wechat"}]
    if unsupported:
        raise SystemExit(f"不支持的平台: {', '.join(unsupported)}")

    node = find_node()
    wechat_skill = find_wechat_skill(args.wechat_skill_dir)
    manifest: dict[str, Any] = {
        "schema_version": "1.0",
        "created_at": utc_now(),
        "research_plan": str(plan_path),
        "run_requested": args.run,
        "waiting_login_terminal": False,
        "platforms": [],
    }
    for platform in platforms:
        tasks = platform_queries(plan, platform)
        platform_dir = output_dir / platform
        platform_dir.mkdir(parents=True, exist_ok=True)
        row: dict[str, Any] = {"platform": platform, "tasks": tasks, "status": "planned", "terminal": False}
        if platform == "wechat" and not wechat_skill:
            row.update(
                {
                    "status": "access_failed",
                    "failure_reason": "wechat-search-weread 未安装或缺少 scripts/weread_search.mjs",
                    "next_action": "安装增强版 wechat-search-weread 后以同一 output-dir 重跑；继续其他平台。",
                }
            )
            manifest["platforms"].append(row)
            continue
        command = (
            baijiahao_command(node, tasks, platform_dir, args)
            if platform == "baijiahao"
            else wechat_command(node, wechat_skill, tasks, platform_dir, args)
        )
        row["command"] = command
        if args.run:
            result = run_command(command, output_dir, args.timeout)
            audit_path = platform_dir / ("baijiahao_browser_audit.json" if platform == "baijiahao" else "weread_search_audit.json")
            payload = read_json_if_exists(audit_path)
            row.update(
                {
                    "status": adapter_status(platform, result, payload),
                    "terminal": False,
                    "resume_required": "waiting_login" in adapter_status(platform, result, payload),
                    "execution": result,
                    "audit": str(audit_path) if audit_path.exists() else "",
                }
            )
        manifest["platforms"].append(row)

    waiting = [row["platform"] for row in manifest["platforms"] if "waiting_login" in str(row.get("status"))]
    failed = [row["platform"] for row in manifest["platforms"] if row.get("status") == "access_failed"]
    manifest["status"] = "partial_waiting_login" if waiting else ("partial_access_failed" if failed else ("completed" if args.run else "planned"))
    manifest["terminal"] = False
    manifest["resume_required"] = bool(waiting)
    manifest["waiting_platforms"] = waiting
    manifest["failed_platforms"] = failed
    manifest["finished_at"] = utc_now()
    manifest_path = output_dir / "public_platform_research_audit.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": manifest["status"], "audit": str(manifest_path)}, ensure_ascii=False))
    if waiting:
        raise SystemExit(2)
    if args.run and failed and len(failed) == len(platforms):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
