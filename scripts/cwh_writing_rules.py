"""Executable, meeting-independent writing frames shared by report consumers."""
from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

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


def domestic_media_label(data: dict[str, Any]) -> str:
    """Keep a known input channel scope; legacy inputs retain their explicit frame."""
    label = str((((data.get("statistics") or {}).get("source_bucket_labels") or {})
                 .get("domestic_media")) or "").strip()
    if label in {"境内新闻", "国内新闻", "境内媒体", "境内主流媒体"}:
        return label
    return "境内媒体" if label else "境内主流媒体"


def ordinal_prefix(value: int) -> str:
    prefixes = writing_rules()["viewpoint"]["cluster_ordinal_prefixes"]
    if value <= 0:
        raise ValueError("Report numbering starts at one")
    return prefixes[value - 1] if value <= len(prefixes) else f"{chinese_number(value)}是"


def judgment_heading(value: Any) -> str:
    """One shared display frame; preserve explicit stance and source meaning."""
    heading = str(value or '').strip().rstrip('。；;')
    rules = writing_rules()['viewpoint']
    stances = tuple(rules['heading_stance_verbs'])
    reports = '|'.join(map(re.escape, [*stances, '指出', '表示', '称']))
    actor = r'(?:舆论|媒体|专家|机构)(?:普遍)?'
    heading = re.sub('^' + re.escape(rules['default_attribution_verb']) + '(?=' + actor + '(?:' + reports + '))', '', heading)
    heading = re.sub('^' + actor + '(?=(?:' + reports + '))', '', heading)
    if not heading.startswith(stances):
        heading = re.sub(r'^(?:指出|表示|称)', '', heading)
    if not heading or heading.startswith(stances) or any(marker in heading for marker in ('尚未形成评论性观点', '以事实性报道为主')):
        return heading
    return rules['default_attribution_verb'] + heading


def opening_paragraph(meeting: dict[str, Any], date_label: str, agenda_topics: str) -> str:
    rules = writing_rules()["document"]
    # Only explicit, source-backed input may name a chair. Missing metadata
    # uses a neutral frame and never defaults to a historical office holder.
    chair_name = str(meeting.get("chair_name") or "").strip()
    chair_source = str(meeting.get("chair_source") or "").strip()
    governing_verbs = ("听取", "研究", "审议", "进一步部署", "部署", "决定")
    if chair_name and chair_source:
        if not agenda_topics:
            template = rules["opening_with_chair_no_agenda"]
        elif agenda_topics.startswith(governing_verbs):
            template = rules["opening_with_chair"]
        else:
            template = rules["opening_with_chair_topic_list"]
    else:
        if not agenda_topics:
            template = rules["opening_without_chair_no_agenda"]
        elif agenda_topics.startswith(governing_verbs):
            template = rules["opening_without_chair"]
        else:
            template = rules["opening_without_chair_topic_list"]
    return template.format(date=date_label, agenda=agenda_topics, chair_name=chair_name)


def formal_attribution(row: dict[str, Any]) -> str:
    """Return a stable formal display label without changing evidence identity."""
    status = str(row.get("attribution_status") or "").strip().lower()
    subject = str(
        row.get("attribution")
        or row.get("speaker_name")
        or row.get("source")
        or row.get("platform")
        or ""
    ).strip()
    role = str(row.get('speaker_role') or '').strip()
    speaker = str(row.get('speaker_name') or '').strip()
    if role and speaker.startswith(role) and subject == role + speaker:
        # Exact duplicated prefix only; the frozen identity fields remain intact.
        subject = speaker
    if status != "self_media" or not subject:
        return subject
    if re.match(r"^(?:微信公众号|头条号|百家号|微博账号|自媒体账号)[“\"]", subject):
        return subject
    bare = str(row.get("speaker_name") or row.get("source") or row.get("attribution") or subject).strip()
    host = (urlsplit(str(row.get("url") or "")).hostname or "").lower()
    if host == "mp.weixin.qq.com" or host.endswith(".mp.weixin.qq.com"):
        platform = "微信公众号"
    elif host.endswith("toutiao.com"):
        platform = "头条号"
    elif host.endswith("baijiahao.baidu.com"):
        platform = "百家号"
    elif host.endswith("weibo.com") or host.endswith("weibo.cn"):
        platform = "微博账号"
    else:
        platform = "自媒体账号"
    return f"{platform}“{bare}”"


def attribution_verb(row: dict[str, Any]) -> str:
    rules = writing_rules()["viewpoint"]
    supplied = str(row.get("attribution_verb") or "").strip()
    if supplied in rules["attribution_verbs"]:
        return supplied
    status = str(row.get("attribution_status") or "").strip().lower()
    return rules["default_attribution_verbs_by_status"].get(status, rules["default_attribution_verb"])


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
