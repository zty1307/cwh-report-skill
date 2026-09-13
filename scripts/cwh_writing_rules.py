"""Executable, meeting-independent writing frames shared by report consumers."""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

RULES_PATH = Path(__file__).resolve().parent.parent / "config/formal_writing_rules.v1.json"


@lru_cache(maxsize=1)
def writing_rules() -> dict[str, Any]:
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def writing_rules_sha256() -> str:
    return hashlib.sha256(RULES_PATH.read_bytes()).hexdigest()


def chinese_number(value: int) -> str:
    if value <= 0:
        raise ValueError("Report numbering starts at one")
    digits = "零一二三四五六七八九"
    if value < 10:
        return digits[value]
    if value < 100:
        tens, units = divmod(value, 10)
        return (digits[tens] if tens > 1 else "") + "十" + (digits[units] if units else "")
    return str(value)


def ordinal_prefix(value: int) -> str:
    prefixes = writing_rules()["viewpoint"]["cluster_ordinal_prefixes"]
    if value <= 0:
        raise ValueError("Report numbering starts at one")
    return prefixes[value - 1] if value <= len(prefixes) else f"{chinese_number(value)}是"


def opening_paragraph(meeting: dict[str, Any], date_label: str, agenda_topics: str) -> str:
    rules = writing_rules()["document"]
    # Only explicit, source-backed input may name a chair. Missing metadata
    # uses a neutral frame and never defaults to a historical office holder.
    chair_name = str(meeting.get("chair_name") or "").strip()
    chair_source = str(meeting.get("chair_source") or "").strip()
    if chair_name and chair_source:
        template = rules["opening_with_chair"]
    else:
        template = rules["opening_without_chair"]
    return template.format(date=date_label, agenda=agenda_topics, chair_name=chair_name)


def source_rank(row: dict[str, Any]) -> int:
    rules = writing_rules()["viewpoint"]
    if row.get("attribution_status") == "named_person":
        category = "named_expert"
    else:
        category = rules["source_type_classes"].get(str(row.get("source_type") or ""), "other_traceable_source")
        if row.get("attribution_status") == "self_media":
            category = "public_account"
    return rules["source_order"].index(category)


def unsupported_padding_issues(evidence: dict[str, Any]) -> list[str]:
    claim = str(evidence.get("formal_claim") or "")
    excerpt = str(evidence.get("source_excerpt") or "")
    return [phrase for phrase in writing_rules()["viewpoint"]["prohibited_padding"] if phrase in claim and phrase not in excerpt]
