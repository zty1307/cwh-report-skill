from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from cwh_hotword_pipeline import render_wordcloud_png


def write_job(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a dashboard hotword preview outside the web process")
    parser.add_argument("job", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    job_path = args.job.resolve()
    preview = json.loads(job_path.read_text(encoding="utf-8"))
    try:
        preview["status"] = "running"
        write_job(job_path, preview)
        render_wordcloud_png(dict(preview.get("audit") or {}), args.output.resolve(), seed=20260710)
        preview["status"] = "complete"
        preview["completed_at"] = datetime.now().isoformat(timespec="seconds")
        write_job(job_path, preview)
        return 0
    except Exception as exc:
        preview["status"] = "failed"
        preview["error"] = f"{type(exc).__name__}: {exc}"
        write_job(job_path, preview)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
