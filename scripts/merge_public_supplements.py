#!/usr/bin/env python3
"""Merge traceable public-web overseas evidence into an existing report_data.json."""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any


CATEGORY_ALIASES = {
    "转载报道": "事实性报道",
    "事实报道": "事实性报道",
    "事实性": "事实性报道",
    "一般解读": "解读性报道",
    "评论解读": "解读性报道",
    "风险解读": "借题炒作/风险解读",
    "借题炒作": "借题炒作/风险解读",
}

STRICT_OVERSEAS_COMMENT_PATTERNS = (
    r"(?:推翻|打倒|颠覆)(?:中共|共产党|中国政府|政权)",
    r"(?:中共|共产党|中国政府|政权).{0,12}(?:独裁|邪恶|暴政|纳粹|魔鬼|垃圾|畜生|应当垮台|必须下台)",
    r"(?:overthrow|down\s+with).{0,20}(?:ccp|communist\s+party|chinese\s+government|regime)",
    r"(?:ccp|communist\s+party|chinese\s+government|regime).{0,36}(?:dictatorship|evil|tyranny|nazi|devil|scum)",
    r"(?:ccp|中共).{0,24}(?:neglected\s+the\s+development\s+of\s+the\s+country\s*side|忽视农村发展)",
)


def disallowed_overseas_comment(row: dict[str, Any]) -> bool:
    import re

    text = " ".join(
        str(row.get(key) or "")
        for key in ("content", "title", "translation", "translation_cn", "summary_cn")
    )
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in STRICT_OVERSEAS_COMMENT_PATTERNS)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_date(value: Any) -> date | None:
    text = str(value or "").strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def in_window(value: Any, start: Any, end: Any) -> bool:
    current = parse_date(value)
    lower = parse_date(start)
    upper = parse_date(end)
    if current is None:
        return False
    return (lower is None or current >= lower) and (upper is None or current <= upper)


def append_unique(rows: list[dict[str, Any]], row: dict[str, Any], keys: tuple[str, ...]) -> bool:
    marker = tuple(str(row.get(key) or "").strip() for key in keys)
    for item in rows:
        if tuple(str(item.get(key) or "").strip() for key in keys) != marker:
            continue
        # Re-running a supplement bundle may enrich an existing item with a
        # translation, summary, or provenance label. Merge those fields rather
        # than silently discarding the newer evidence metadata.
        item.update(
            {
                key: value
                for key, value in row.items()
                if value not in (None, "", [], {})
            }
        )
        return False
    rows.append(row)
    return True


def merge(report: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(report)
    period = (output.get("system_data") or {}).get("monitoring_period") or {}
    start, end = period.get("start"), period.get("end")
    samples = output.setdefault("samples", [])
    appendices = output.setdefault("appendices", {})
    overseas_appendix = appendices.setdefault("overseas_reports", [])
    overseas = output.setdefault("overseas", {})
    groups = overseas.setdefault("groups", {})
    public_comments = overseas.setdefault("public_comments", [])
    added_media = 0
    added_comments = 0

    for raw in bundle.get("media") or []:
        row = deepcopy(raw)
        row.setdefault("source_type", "overseas_media")
        row.setdefault("platform", "公开网站")
        row.setdefault("region", "overseas")
        row.setdefault("origin", "public_web_supplement")
        row.setdefault("quote_verified", False)
        row.setdefault("interpretive_verified", bool(row.get("summary") or row.get("content")))
        raw_category = str(row.get("overseas_category") or row.get("category") or "事实性报道").strip()
        category = CATEGORY_ALIASES.get(raw_category, raw_category)
        if category not in {"事实性报道", "解读性报道", "借题炒作/风险解读"}:
            category = "事实性报道"
        row["category"] = category
        row["overseas_category"] = category
        row["in_monitoring_window"] = in_window(row.get("published_at"), start, end)
        if not row.get("url") or not row.get("title"):
            continue
        if append_unique(overseas_appendix, row, ("url",)):
            added_media += 1
        append_unique(samples, row, ("url",))
        append_unique(groups.setdefault(category, []), row, ("url",))

    for raw in bundle.get("comments") or []:
        row = deepcopy(raw)
        row.setdefault("source_type", "overseas_netizen")
        row.setdefault("platform", "X")
        row.setdefault("region", "overseas")
        row.setdefault("origin", "agent_reach")
        row.setdefault("is_comment", True)
        row.setdefault("quote_verified", True)
        row.setdefault("evidence_mode", "platform_reply")
        row["in_monitoring_window"] = in_window(row.get("published_at"), start, end)
        if not row.get("url") or not row.get("content") or not (row.get("comment_id") or row.get("reply_id")):
            continue
        if disallowed_overseas_comment(row):
            overseas.setdefault("excluded_public_comments", []).append(
                {**row, "exclusion_reason": "obvious_anti_party_or_anti_government_content"}
            )
            continue
        if append_unique(public_comments, row, ("url", "reply_id", "comment_id")):
            added_comments += 1

    overseas["needs_manual_review"] = bool(public_comments)
    summary = overseas.setdefault("summary", {})
    summary["公开网络补证"] = sum(1 for row in overseas_appendix if row.get("origin") == "public_web_supplement")
    audit = output.setdefault("audit", {})
    quality = audit.setdefault("quality_summary", {})
    quality["detail_samples"] = len(samples)
    quality["overseas_public_comments"] = len(public_comments)
    audit.setdefault("supplement_merge", {}).update(
        {
            "added_overseas_media": added_media,
            "added_overseas_comments": added_comments,
            "monitoring_window": {"start": start, "end": end},
        }
    )
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge overseas public-web evidence into report_data.json")
    parser.add_argument("report_data")
    parser.add_argument("supplements")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    report_path = Path(args.report_data).resolve()
    output_path = Path(args.output).resolve() if args.output else report_path
    merged = merge(load_json(report_path), load_json(Path(args.supplements).resolve()))
    output_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(merged.get("audit", {}).get("supplement_merge", {}), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
