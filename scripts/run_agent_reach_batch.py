from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def matches(task: dict[str, Any], platforms: set[str]) -> bool:
    if not platforms:
        return True
    return str(task.get("platform") or "").lower() in platforms


def round_robin_select(tasks: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if not limit or len(tasks) <= limit:
        return tasks
    buckets: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for task in tasks:
        platform = str(task.get("platform") or "unknown")
        if platform not in buckets:
            buckets[platform] = []
            order.append(platform)
        buckets[platform].append(task)
    selected: list[dict[str, Any]] = []
    while len(selected) < limit and any(buckets.values()):
        for platform in order:
            if buckets[platform]:
                selected.append(buckets[platform].pop(0))
                if len(selected) >= limit:
                    break
    return selected


def run_task(task: dict[str, Any], opencli_profile: str = "") -> subprocess.CompletedProcess[str]:
    argv = task.get("argv")
    if isinstance(argv, list) and argv:
        final_argv = [str(x) for x in argv]
        if opencli_profile and final_argv and final_argv[0].lower() == "opencli" and "--profile" not in final_argv:
            final_argv.extend(["--profile", opencli_profile])
        return subprocess.run(
            final_argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    command = str(task.get("command") or "")
    shell = os.name == "nt"
    return subprocess.run(
        command if shell else command.split(),
        shell=shell,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run agent-reach lead-discovery tasks and save raw outputs.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--platforms", default="", help="Optional comma list.")
    parser.add_argument("--limit", type=int, default=1, help="Maximum tasks to run; 0 means all matched tasks.")
    parser.add_argument("--run", action="store_true", help="Actually run commands. Default writes dry-run plan only.")
    parser.add_argument("--opencli-profile", default="", help="Optional OpenCLI Browser Bridge profile name.")
    parser.add_argument("--out-dir", default="", help="Raw output directory. Defaults beside manifest.")
    parser.add_argument("--out", default="", help="Batch result JSON path.")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    manifest = load_manifest(manifest_path)
    platforms = {x.strip().lower() for x in args.platforms.split(",") if x.strip()}
    raw_dir = Path(args.out_dir).resolve() if args.out_dir else manifest_path.parent / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    candidates = []
    for task in manifest.get("tasks", []):
        if not matches(task, platforms):
            continue
        candidates.append(task)
    selected = round_robin_select(candidates, args.limit)

    results = []
    for idx, task in enumerate(selected, 1):
        command = str(task.get("command") or "")
        started_at = datetime.now().isoformat(timespec="seconds")
        output_file = raw_dir / f"{idx:03d}_{task.get('platform', 'agent_reach')}.txt"
        if args.run and command:
            proc = run_task(task, args.opencli_profile)
            output_file.write_text(proc.stdout, encoding="utf-8")
            stderr_file = output_file.with_suffix(".stderr.txt")
            stderr_file.write_text(proc.stderr, encoding="utf-8")
            code = proc.returncode
        else:
            output_file.write_text(command, encoding="utf-8")
            stderr_file = output_file.with_suffix(".stderr.txt")
            code = 0
        results.append(
            {
                "task": task,
                "dry_run": not args.run,
                "command": command,
                "started_at": started_at,
                "finished_at": datetime.now().isoformat(timespec="seconds"),
                "exit_code": code,
                "stdout_file": str(output_file),
                "stderr_file": str(stderr_file),
            }
        )

    payload = {
        "manifest": str(manifest_path),
        "dry_run": not args.run,
        "selected_count": len(selected),
        "raw_dir": str(raw_dir),
        "results": results,
    }
    out = Path(args.out).resolve() if args.out else manifest_path.parent / ("batch_run.json" if args.run else "batch_dry_run.json")
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    failed = [x for x in results if x["exit_code"] != 0]
    print(json.dumps({"status": "ok" if not failed else "failed", "selected": len(selected), "failed": len(failed), "out": str(out)}, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
