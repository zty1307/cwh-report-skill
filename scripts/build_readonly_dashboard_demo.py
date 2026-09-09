from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path


DATA_PATTERN = re.compile(
    r'(<script id="dashboard-data" type="application/json">)(.*?)(</script>)',
    re.DOTALL,
)
DEMO_FLAG = "const DEMO_MODE=new URLSearchParams(location.search).get('demo')==='1';"


def sanitize_local_paths(value):
    if isinstance(value, dict):
        return {key: sanitize_local_paths(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_local_paths(item) for item in value]
    if isinstance(value, str) and re.match(r"^[A-Za-z]:[\\/]", value):
        return Path(value).name or "本机文件"
    return value


def build_demo(source: Path, output_dir: Path) -> tuple[Path, Path]:
    html = source.read_text(encoding="utf-8")
    match = DATA_PATTERN.search(html)
    if not match:
        raise ValueError("dashboard-data not found")
    data = sanitize_local_paths(json.loads(match.group(2)))
    data.setdefault("artifacts", {})
    for artifact in data["artifacts"].values():
        if isinstance(artifact, dict):
            artifact["path"] = "只读演示不提供本机文件"
            artifact["href"] = "#"
            artifact["protocol"] = ""
    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = DATA_PATTERN.sub(lambda current: current.group(1) + encoded + current.group(3), html, count=1)
    if DEMO_FLAG not in html:
        raise ValueError("dashboard template does not support readonly demo mode")
    html = html.replace("fetch(", "readonlyFetch(")
    html = html.replace(
        DEMO_FLAG,
        "const DEMO_MODE=true;\n"
        "const readonlyFetch=()=>Promise.reject(new Error('只读演示不连接后台'));",
        1,
    )
    html = html.replace("<title>CWH舆情报告工作台</title>", "<title>CWH舆情报告工作台（只读演示）</title>", 1)

    output_dir.mkdir(parents=True, exist_ok=True)
    index_path = output_dir / "index.html"
    index_path.write_text(html, encoding="utf-8")
    archive_base = output_dir.parent / output_dir.name
    archive_path = Path(shutil.make_archive(str(archive_base), "zip", root_dir=output_dir))
    return index_path, archive_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a sanitized, read-only CWH dashboard demo")
    parser.add_argument("dashboard", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    index_path, archive_path = build_demo(args.dashboard.resolve(), args.output_dir.resolve())
    print(json.dumps({"index": str(index_path), "archive": str(archive_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
