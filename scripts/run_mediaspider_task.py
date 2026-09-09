"""Run one MediaSpider domestic task with CWH runtime hooks.

The adapter preserves the Supervisor task contract while keeping QR capture,
headless browser settings, and per-user profile isolation outside MediaSpider.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import runpy
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


VALUE_FLAGS = {
    "platform": "--platform",
    "login_type": "--lt",
    "crawler_type": "--type",
    "start_page": "--start",
    "save_data_option": "--save_data_option",
    "cookies": "--cookies",
    "specified_id": "--specified_id",
    "creator_id": "--creator_id",
    "max_comments_per_post": "--max_comments_count_singlenotes",
    "max_posts": "--crawler_max_notes_count",
    "max_concurrency": "--max_concurrency_num",
    "save_data_path": "--save_data_path",
}
BOOL_FLAGS = {
    "get_comment": "--get_comment",
    "get_sub_comment": "--get_sub_comment",
    "headless": "--headless",
    "enable_ip_proxy": "--enable_ip_proxy",
}


def _as_csv(value: Any) -> str:
    if isinstance(value, list):
        return ",".join(str(item).strip() for item in value if str(item).strip())
    return str(value)


def _write_state(path: Path | None, **changes) -> None:
    if not path:
        return
    current = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    current.update(changes, updated_at=datetime.now().isoformat(timespec="seconds"))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _capture_qrcode(qr_path: Path | None, state_path: Path | None):
    def capture(encoded: str) -> None:
        if not qr_path:
            return
        value = str(encoded or "")
        if "," in value:
            value = value.split(",", 1)[1]
        qr_path.parent.mkdir(parents=True, exist_ok=True)
        qr_path.write_bytes(base64.b64decode(value))
        _write_state(state_path, status="awaiting_scan", qr_ready=True, message="二维码已生成，请扫码登录。")

    return capture


def build_media_argv(task: dict[str, Any]) -> list[str]:
    argv = ["main.py"]
    for key, flag in VALUE_FLAGS.items():
        value = task.get(key)
        if value is not None and value != "":
            argv.extend([flag, _as_csv(value)])
    if task.get("keywords"):
        argv.extend(["--keywords", _as_csv(task["keywords"])])
    for key, flag in BOOL_FLAGS.items():
        if key in task:
            argv.extend([flag, "true" if bool(task[key]) else "false"])
    return argv


def bind_task_output(task: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    """Force every collection task to keep its raw evidence inside its audit run."""
    resolved = dict(task)
    resolved["save_data_path"] = str((run_dir / "raw").resolve())
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a MediaSpider task with CWH runtime isolation")
    parser.add_argument("task_json", type=Path)
    parser.add_argument("--media-home", type=Path, required=True)
    parser.add_argument("--profile-template", default="")
    parser.add_argument("--qr-path", default="")
    parser.add_argument("--state-path", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    task_path = args.task_json.resolve()
    task = json.loads(task_path.read_text(encoding="utf-8-sig"))
    media_home = args.media_home.resolve()
    if not (media_home / "main.py").exists():
        raise FileNotFoundError(f"MediaSpider main.py not found: {media_home}")
    run_dir = Path(task.get("run_dir") or (task_path.parent / f"{datetime.now():%Y%m%d_%H%M%S}_{task_path.stem}")).resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    task = bind_task_output(task, run_dir)
    Path(task["save_data_path"]).mkdir(parents=True, exist_ok=True)
    (run_dir / "task.resolved.json").write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
    media_argv = build_media_argv(task)
    (run_dir / "command.txt").write_text(" ".join(media_argv), encoding="utf-8")
    print(f"Run directory: {run_dir}", flush=True)
    print(f"MediaSpider: {media_home}", flush=True)
    print("Command:", " ".join(media_argv), flush=True)
    if args.dry_run:
        return 0

    sys.path.insert(0, str(media_home))
    os.chdir(media_home)
    import config  # type: ignore
    from tools import utils  # type: ignore

    if args.profile_template:
        config.USER_DATA_DIR = str(Path(args.profile_template).resolve())
    config.SAVE_LOGIN_STATE = True
    config.ENABLE_CDP_MODE = False
    config.CDP_HEADLESS = True
    config.HEADLESS = True
    qr_path = Path(args.qr_path).resolve() if args.qr_path else None
    state_path = Path(args.state_path).resolve() if args.state_path else None
    if qr_path:
        utils.show_qrcode = _capture_qrcode(qr_path, state_path)
    sys.argv = media_argv
    try:
        runpy.run_path(str(media_home / "main.py"), run_name="__main__")
    except SystemExit as exc:
        code = int(exc.code or 0)
        _write_state(
            state_path,
            status="completed" if code == 0 else "failed",
            qr_ready=bool(qr_path and qr_path.exists()),
            exit_code=code,
            message="采集任务已完成。" if code == 0 else f"采集任务失败，退出码 {code}。",
        )
        return code
    except BaseException as exc:
        _write_state(
            state_path,
            status="failed",
            qr_ready=bool(qr_path and qr_path.exists()),
            message=f"采集任务异常：{type(exc).__name__}",
        )
        raise
    _write_state(
        state_path,
        status="completed",
        qr_ready=bool(qr_path and qr_path.exists()),
        exit_code=0,
        message="采集任务已完成。",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
