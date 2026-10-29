"""Normalize a monitoring-system public-account export for standalone screening."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from openpyxl import load_workbook


ALIASES = {
    "title": ("标题", "文章标题"),
    "content": ("正文内容", "正文", "文章内容", "内容"),
    "url": ("发文链接", "原文链接", "链接"),
    "published_at": ("发表时间", "发布时间", "发文时间"),
    "account": ("昵称", "账号名称", "账号", "账号昵称", "帐号昵称"),
    "site": ("站点名称", "平台", "来源平台"),
    "post_id": ("发文ID", "文章ID"),
}


def find_columns(headers: list[str]):
    positions = {}
    for field, aliases in ALIASES.items():
        matched = next((headers.index(name) for name in aliases if name in headers), None)
        if matched is None and field in ("title", "content", "url", "published_at"):
            raise ValueError(f"Missing required column {field}; accepted names: {aliases}")
        positions[field] = matched
    return positions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--sheet", default="")
    args = parser.parse_args()
    source = args.workbook.resolve()
    workbook = load_workbook(source, read_only=True, data_only=True)
    page = workbook[args.sheet] if args.sheet else workbook.worksheets[0]
    page.reset_dimensions()  # Some monitoring exports incorrectly declare A1.
    iterator = page.values
    headers = [str(value or "").strip() for value in next(iterator)]
    positions = find_columns(headers)
    records = []
    for excel_row, raw in enumerate(iterator, 2):
        data = {field: str(raw[index] or "").strip() if index is not None and index < len(raw) else ""
                for field, index in positions.items()}
        records.append({
            "id": f"r{excel_row}", "sheet": page.title, "excel_row": excel_row,
            **data,
            "content_sha256": hashlib.sha256(data["content"].encode("utf-8")).hexdigest(),
        })
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = {
        "source": str(source), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "sheet": page.title, "row_count": len(records),
        "nonempty_content_count": sum(bool(row["content"]) for row in records),
    }
    args.out.with_suffix(".manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
