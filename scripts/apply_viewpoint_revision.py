from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from report_rules import domestic_viewpoint_quality_issues


def rebase_artifact_paths(value: Any, source_root: Path, target_root: Path) -> Any:
    if isinstance(value, dict):
        return {
            key: rebase_artifact_paths(item, source_root, target_root)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [rebase_artifact_paths(item, source_root, target_root) for item in value]
    if not isinstance(value, str):
        return value
    try:
        path = Path(value)
        relative = path.resolve().relative_to(source_root)
    except (OSError, ValueError):
        return value
    return str(target_root / relative)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply a reviewed domestic-viewpoint revision to an existing CWH report data file."
    )
    parser.add_argument("base_report_data")
    parser.add_argument("revision")
    parser.add_argument("output_report_data")
    args = parser.parse_args()

    base_path = Path(args.base_report_data).resolve()
    revision_path = Path(args.revision).resolve()
    output_path = Path(args.output_report_data).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = json.loads(base_path.read_text(encoding="utf-8"))
    revision = json.loads(revision_path.read_text(encoding="utf-8"))
    viewpoints = revision.get("viewpoints") or {}
    if not viewpoints.get("by_topic"):
        raise ValueError("Revision must contain viewpoints.by_topic.")

    data["viewpoints"] = viewpoints
    data["artifacts"] = rebase_artifact_paths(
        data.get("artifacts") or {}, base_path.parent, output_path.parent
    )
    quality_issues = domestic_viewpoint_quality_issues(data)
    data.setdefault("audit", {})["domestic_viewpoint_revision"] = {
        "method": revision.get("method") or "ai_semantic_source_review",
        "reviewed_at": revision.get("reviewed_at") or "",
        "source_count": len(revision.get("sources") or []),
        "notes": list(revision.get("notes") or []),
        "quality_issue_count": len(quality_issues),
        "quality_issues": quality_issues,
    }
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    for name in ("charts", "appendices", "TencentFont.otf", "hotword_audit.json"):
        source = base_path.parent / name
        target = output_path.parent / name
        if not source.exists() or target.exists():
            continue
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)

    print(
        json.dumps(
            {
                "status": "ok",
                "output": str(output_path),
                "topic_count": len(viewpoints["by_topic"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
