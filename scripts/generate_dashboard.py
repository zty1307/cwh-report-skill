from __future__ import annotations

import argparse
import base64
import hashlib
import json
import mimetypes
import re
import unicodedata
from collections import OrderedDict
from pathlib import Path
from typing import Any
from urllib.parse import quote

from report_rules import (
    cluster_needs_attribution_review,
    enrich_viewpoint_titles,
    formal_sentiment_available,
    formal_sentiment_row_ready,
)


TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "assets" / "cwh_dashboard_template.html"
MAINLAND_FOREIGN_LANGUAGE_OUTLETS = (
    "新华网海外版",
    "新华社海外版",
    "CGTN",
    "人民网英文版",
    "中国经济网英文版",
    "央视网英文版",
    "中国日报英文版",
)

OVERSEAS_REPORT_CATEGORIES = (
    "事实性报道",
    "解读性报道",
    "借题炒作/风险解读",
)

STRICT_OVERSEAS_COMMENT_PATTERNS = (
    r"推翻(?:中共|共产党|中国政府|政权)",
    r"打倒(?:中共|共产党|中国政府|政权)",
    r"颠覆(?:中共|共产党|中国政府|政权)",
    r"(?:中共|共产党|中国政府|政权).{0,8}(?:去死|独裁|邪恶|暴政|纳粹|魔鬼|垃圾|畜生)",
    r"(?:去死|独裁|邪恶|暴政|纳粹|魔鬼|垃圾|畜生).{0,8}(?:中共|共产党|中国政府|政权)",
    r"overthrow\s+(?:the\s+)?(?:ccp|communist\s+party|chinese\s+government|regime)",
    r"down\s+with\s+(?:the\s+)?(?:ccp|communist\s+party|chinese\s+government|regime)",
    r"f(?:uck|\*+k)\s+(?:the\s+)?(?:ccp|communist\s+party|chinese\s+government|regime)",
    r"(?:ccp|communist\s+party|chinese\s+government|regime).{0,36}(?:dictatorship|dictatorial|evil|tyranny|nazi|devil|scum)",
    r"(?:dictatorship|dictatorial|evil|tyranny|nazi|devil|scum).{0,36}(?:ccp|communist\s+party|chinese\s+government|regime)",
)


def as_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    return int(float(match.group(0))) if match else 0


def display_date(value: Any) -> str:
    text = str(value or "").strip()
    match = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if not match:
        return text
    year, month, day = match.groups()
    return f"{year}/{int(month)}/{int(day)}"


def canonical_topic_key(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text)


def chinese_date(value: Any) -> str:
    text = str(value or "").strip()
    match = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if not match:
        return text
    year, month, day = match.groups()
    return f"{year}年{int(month)}月{int(day)}日"


def normalized_sentiment(values: dict[str, Any] | None) -> dict[str, int]:
    values = values or {}
    raw = {
        "positive": max(0, as_int(values.get("positive"))),
        "neutral": max(0, as_int(values.get("neutral"))),
        "negative": max(0, as_int(values.get("negative"))),
    }
    total = sum(raw.values())
    if total <= 0:
        return {"positive": 0, "neutral": 0, "negative": 0}
    positive = round(raw["positive"] / total * 100)
    neutral = round(raw["neutral"] / total * 100)
    negative = max(0, 100 - positive - neutral)
    return {"positive": positive, "neutral": neutral, "negative": negative}


def path_from(value: Any) -> Path | None:
    text = str(value or "").strip()
    return Path(text) if text else None


def image_data_uri(value: Any) -> str:
    path = path_from(value)
    if not path or not path.exists() or not path.is_file():
        return ""
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def first_image_data_uri(*values: Any) -> str:
    """Return the first non-empty image, skipping stale artifact paths."""
    for value in values:
        uri = image_data_uri(value)
        if uri:
            return uri
    return ""


def is_overseas_row(row: dict[str, Any]) -> bool:
    region = str(row.get("region") or "").strip().lower()
    source_type = str(row.get("source_type") or "").strip().lower()
    sample_id = str(row.get("id") or "").strip().lower()
    return bool(
        region in {"overseas", "foreign", "境外"}
        or source_type.startswith("overseas")
        or source_type in {"境外媒体", "境外自媒体"}
        or sample_id.startswith("system-overseas-")
    )


def evidence_origin(row: dict[str, Any]) -> str:
    origin = str(row.get("data_origin") or "").strip().lower()
    sample_id = str(row.get("id") or "").strip().lower()
    if origin == "monitoring_system_excel" or sample_id.startswith("system-"):
        return "监测系统 Excel"
    return "公开网络补证"


def relative_href(path: Path | None, out_dir: Path) -> str:
    if not path:
        return "#"
    try:
        relative = path.resolve().relative_to(out_dir.resolve())
        return "./" + quote(relative.as_posix())
    except (OSError, ValueError):
        return path.resolve().as_uri() if path.is_absolute() else quote(path.as_posix())


def office_protocol(path: Path | None, app: str) -> str:
    if not path:
        return ""
    scheme = "ms-word" if app == "word" else "ms-excel"
    return f"{scheme}:ofe|u|{path.resolve().as_uri()}"


def artifact(value: Any, out_dir: Path, app: str = "") -> dict[str, str]:
    path = path_from(value)
    return {
        "path": str(path or ""),
        "href": relative_href(path, out_dir),
        "protocol": office_protocol(path, app) if app else "",
    }


def region_priority(row: dict[str, Any]) -> int:
    text = f"{row.get('source', '')}{row.get('title', '')}"
    region_markers = (
        (0, ("香港", "港澳")),
        (1, ("台湾", "中评")),
        (2, ("新加坡", "联合早报")),
        (3, ("澳门",)),
    )
    for priority, markers in region_markers:
        if any(marker in text for marker in markers):
            return priority
    return 4


def first_text(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def contains_chinese(value: Any) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", str(value or "")))


def overseas_report_category(row: dict[str, Any]) -> str:
    raw = first_text(row, "overseas_category", "report_category", "category")
    aliases = {
        "事实报道": "事实性报道",
        "事实性": "事实性报道",
        "转载报道": "事实性报道",
        "一般解读": "解读性报道",
        "评论解读": "解读性报道",
        "风险解读": "借题炒作/风险解读",
        "借题炒作": "借题炒作/风险解读",
    }
    if raw in OVERSEAS_REPORT_CATEGORIES:
        return raw
    if raw in aliases:
        return aliases[raw]
    combined = " ".join(
        str(row.get(key) or "")
        for key in ("title", "title_cn", "summary", "summary_cn", "content", "translation_cn")
    ).lower()
    risk_markers = ("风险", "失衡", "质疑", "争议", "炒作", "危机", "risk", "imbalance", "controvers")
    if any(marker in combined for marker in risk_markers):
        return "借题炒作/风险解读"
    if row.get("interpretive_verified") or any(
        marker in combined for marker in ("分析", "解读", "评论", "认为", "指出", "analysis", "commentary", "opinion")
    ):
        return "解读性报道"
    return "事实性报道"


def is_disallowed_overseas_comment(row: dict[str, Any]) -> bool:
    text = " ".join(
        first_text(row, key)
        for key in ("content", "title", "translation", "translation_cn", "summary_cn")
    ).lower()
    return bool(text and any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in STRICT_OVERSEAS_COMMENT_PATTERNS))


def evidence_attribution(
    evidence: dict[str, Any],
    origin_row: dict[str, Any],
    context_text: str = "",
) -> dict[str, str]:
    attribution = first_text(
        evidence,
        "attribution",
        "expert_name",
        "speaker",
        "quoted_person",
        "author_name",
    ) or first_text(
        origin_row,
        "attribution",
        "expert_name",
        "speaker",
        "quoted_person",
        "author_name",
    )
    status = first_text(evidence, "attribution_status") or first_text(origin_row, "attribution_status")
    source = first_text(evidence, "source") or first_text(origin_row, "source", "platform")
    status_key = status.strip().lower()
    unresolved_statuses = {"media_only", "media", "source_only", "missing", "pending", "unresolved"}
    if attribution and status_key not in unresolved_statuses:
        return {"attribution": attribution, "attribution_status": status or "identified"}
    evidence_text = " ".join(
        first_text(row, key)
        for row in (evidence, origin_row)
        for key in ("description", "summary", "excerpt", "content", "title")
    )
    evidence_text = f"{evidence_text} {context_text}".strip()
    generic = ("专家", "媒体", "学者", "业内", "机构", "记者", "负责人", "舆论", "报道", "文章", "消息", "会议")
    role = r"(?:委员|理事长|研究员|教授|主任|副主任|主席|副主席|会长|副会长|院长|秘书长|分析师|首席经济学家|学者|专家)"
    boundary = r"(?:^|[。；，、：\s“”])"
    opinion_verb = r"(?:观点)?(?:认为|表示|指出|建议|强调|称|提到|预计|呼吁|主张)"
    occupation_suffix = r"(?!从业者|工作者|人士|群体)"
    person_patterns = (
        rf"{role}([\u4e00-\u9fff]{{2,4}}){occupation_suffix}{opinion_verb}",
        rf"{boundary}([\u4e00-\u9fff]{{2,4}}){occupation_suffix}{opinion_verb}",
        rf"{role}([\u4e00-\u9fff]{{2,4}}){occupation_suffix}从[^。；，]{{0,80}}(?:解读|分析|阐释|说明)",
        rf"{boundary}([\u4e00-\u9fff]{{2,4}}){occupation_suffix}从[^。；，]{{0,80}}(?:解读|分析|阐释|说明)",
    )
    for pattern in person_patterns:
        match = re.search(pattern, evidence_text)
        if match and not any(term in match.group(1) for term in generic):
            person = match.group(1)
            before = evidence_text[: match.start(1)]
            title_match = re.search(
                rf"([\u4e00-\u9fff（）()·]{{2,42}}{role})$",
                before,
            )
            if title_match:
                title = re.sub(
                    r"^(?:新华社|新华网|央视网|人民网|媒体|报道|文章)(?:援引|采访|报道称|称)",
                    "",
                    title_match.group(1),
                )
                full = f"{title}{person}"
            else:
                full = person
            return {"attribution": full, "attribution_status": "named_person"}
    if source and source not in {"来源", "未知来源", "境内媒体", "境内自媒体"}:
        return {"attribution": source, "attribution_status": "media_only"}
    return {"attribution": "", "attribution_status": "missing"}


def expand_named_attribution(context_text: str, attribution: dict[str, str]) -> dict[str, str]:
    if str(attribution.get("attribution_status") or "").lower() != "named_person":
        return attribution
    person = str(attribution.get("attribution") or "").strip()
    if not re.fullmatch(r"[\u4e00-\u9fff]{2,4}", person):
        return attribution
    role = r"(?:委员|理事长|研究员|教授|主任|副主任|主席|副主席|会长|副会长|院长|秘书长|分析师|首席经济学家|学者|专家)"
    match = re.search(rf"([\u4e00-\u9fff（）()·]{{2,42}}{role}){re.escape(person)}", context_text)
    if match:
        return {**attribution, "attribution": f"{match.group(1)}{person}"}
    return attribution


def match_titled_person_in_evidence(
    context_text: str,
    evidence_text: str,
    attribution: dict[str, str],
) -> dict[str, str]:
    """Borrow a title from cluster prose only when the evidence names that same person."""

    if str(attribution.get("attribution_status") or "").lower() == "named_person":
        return expand_named_attribution(context_text, attribution)
    role = r"(?:委员|理事长|研究员|教授|主任|副主任|主席|副主席|会长|副会长|院长|秘书长|分析师|首席经济学家|学者|专家)"
    pattern = re.compile(
        rf"(?:^|[。；，])([^。；，]{{2,50}}?{role})([\u4e00-\u9fff]{{2,4}})(?=(?:认为|指出|表示|建议|强调|称|分析|解读|提到))"
    )
    for match in pattern.finditer(context_text):
        person = match.group(2)
        if person in evidence_text:
            title = re.sub(
                r"^(?:新华社|新华网|央视网|人民网|媒体|报道|文章)(?:援引|采访|报道称|称)",
                "",
                match.group(1),
            )
            return {
                "attribution": f"{title}{person}",
                "attribution_status": "named_person",
            }
    return attribution


def complete_claim_from_cluster_details(
    cluster_details: Any,
    attribution: dict[str, str],
    fallback: Any,
) -> str:
    """Return the full attributed sentence(s), not the compressed AI claim label."""

    details = str(cluster_details or "").strip()
    if not details:
        return str(fallback or "").strip()
    attribution_text = str(attribution.get("attribution") or "").strip()
    candidates = [attribution_text, named_person_from_attribution(attribution)]
    sentences = [row.strip() for row in re.findall(r"[^。！？!?]+[。！？!?]?", details) if row.strip()]
    for sentence in sentences:
        if any(candidate and candidate in sentence for candidate in candidates):
            return sentence
    return str(fallback or "").strip()


def expand_multi_voice_claims(
    cluster_details: Any,
    attribution: dict[str, str],
    fallback: Any,
) -> list[tuple[dict[str, str], str]]:
    """Split a reviewed multi-person source into one full claim per named voice.

    One article may quote several experts.  The dashboard must not collapse them
    into a short article-level sentence such as "the article cites A and B".
    Split only when the structured attribution explicitly names multiple people
    and every person can be matched to a complete attributed sentence in the
    reviewed cluster prose.
    """

    fallback_claim = complete_claim_from_cluster_details(cluster_details, attribution, fallback)
    if str(attribution.get("attribution_status") or "").strip().lower() != "named_person":
        return [(attribution, fallback_claim)]

    attribution_text = str(attribution.get("attribution") or "").strip()
    if not re.search(r"[、，,]|(?:和|与|及)", attribution_text):
        return [(attribution, fallback_claim)]

    people = [
        token.strip()
        for token in re.split(r"\s*(?:[、，,]|和|与|及)\s*", attribution_text)
        if re.fullmatch(r"[\u4e00-\u9fff]{2,4}", token.strip())
    ]
    if len(people) < 2:
        return [(attribution, fallback_claim)]

    details = str(cluster_details or "").strip()
    sentences = [row.strip() for row in re.findall(r"[^。！？!?]+[。！？!?]?", details) if row.strip()]
    opinion_verb = r"(?:认为|表示|指出|建议|强调|称|提到|预计|呼吁|主张)"
    expanded: list[tuple[dict[str, str], str]] = []
    for person in people:
        sentence = next((row for row in sentences if person in row), "")
        if not sentence:
            return [(attribution, fallback_claim)]
        subject_match = re.search(
            rf"([^。！？!?]{{0,80}}?{re.escape(person)})(?={opinion_verb})",
            sentence,
        )
        if not subject_match:
            return [(attribution, fallback_claim)]
        subject = subject_match.group(1).strip(" ，、；：")
        if not subject.endswith(person):
            return [(attribution, fallback_claim)]
        expanded.append(
            (
                {"attribution": subject, "attribution_status": "named_person"},
                sentence,
            )
        )
    return expanded


def named_person_from_attribution(attribution: dict[str, str]) -> str:
    status = str(attribution.get("attribution_status") or "").strip().lower()
    if status in {"media_only", "media", "source_only", "missing", "pending", "unresolved"}:
        return ""
    text = str(attribution.get("attribution") or "").strip()
    role = r"(?:委员|理事长|研究员|教授|主任|副主任|主席|副主席|会长|副会长|院长|秘书长|分析师|首席经济学家|学者|专家)"
    match = re.search(rf"{role}([\u4e00-\u9fff]{{2,4}})$", text)
    if match:
        return match.group(1)
    return text if re.fullmatch(r"[\u4e00-\u9fff]{2,4}", text) else ""


def dedupe_supporting_links(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "").strip()
        key = url.split("#", 1)[0].rstrip("/")
        if not key or key in seen:
            continue
        seen.add(key)
        output.append({
            "source": str(row.get("source") or row.get("platform") or "同观点来源"),
            "title": str(row.get("title") or "原文")[:220],
            "url": url,
            "origin": str(row.get("origin") or evidence_origin(row)),
            "claim": str(
                row.get("claim")
                or row.get("description")
                or row.get("content_summary")
                or row.get("decision_reason")
                or ""
            )[:800],
        })
    return output


def supporting_links_for_evidence(
    evidence: dict[str, Any],
    topic: str,
    samples: list[dict[str, Any]],
) -> list[dict[str, str]]:
    attribution = evidence_attribution(evidence, evidence)
    person = named_person_from_attribution(attribution)
    evidence_url = str(evidence.get("url") or "").strip().split("#", 1)[0].rstrip("/")
    links: list[dict[str, str]] = []
    seen = {evidence_url}
    for row in samples:
        row_topic = str(row.get("topic") or "")
        if row_topic != topic and topic not in (row.get("topic_hits") or []):
            continue
        row_text = " ".join(
            str(row.get(key) or "")
            for key in ("claim", "description", "summary", "excerpt", "content", "title", "source")
        )
        if not person or person not in row_text:
            continue
        url = str(row.get("url") or "").strip()
        key = url.split("#", 1)[0].rstrip("/")
        if not key or key in seen:
            continue
        seen.add(key)
        links.append({
            "source": str(row.get("source") or row.get("platform") or "同源来源"),
            "title": str(row.get("title") or "原文")[:220],
            "url": url,
            "origin": evidence_origin(row),
            "claim": str(
                row.get("claim")
                or row.get("description")
                or row.get("content_summary")
                or row.get("decision_reason")
                or ""
            )[:800],
        })
    return links


def dashboard_overseas_rows(data: dict[str, Any]) -> list[dict[str, str]]:
    rows = list((data.get("appendices") or {}).get("overseas_reports") or [])
    filtered = []
    for row in rows:
        if row.get("is_comment") or row.get("source_type") in {"overseas_public_discussion", "overseas_netizen"}:
            continue
        # Use the same reviewed evidence universe as the formal report. Rows
        # rejected by semantic meeting-relevance review must not reappear as a
        # dashboard-only category.
        if row.get("formal_include") is False or row.get("meeting_relevance") is False:
            continue
        source = str(row.get("source") or "")
        if any(marker.lower() in source.lower() for marker in MAINLAND_FOREIGN_LANGUAGE_OUTLETS):
            continue
        filtered.append(row)
    filtered.sort(key=lambda row: (str(row.get("published_at") or ""), region_priority(row)))
    output = []
    for row in filtered:
        raw_source = str(row.get("source") or "")
        source_cn = str(row.get("source_cn") or row.get("source_zh") or "").strip()
        if raw_source == "Wedoany English" and not source_cn:
            source_cn = "Wedoany英文网"
        source_display = (
            f"{raw_source}（{source_cn}）"
            if source_cn and source_cn != raw_source and not contains_chinese(raw_source)
            else source_cn or raw_source
        )
        original_title = first_text(row, "original_title", "title_original", "title")
        title_cn = first_text(
            row,
            "title_cn",
            "translation_title_cn",
            "title_translation_cn",
            "translated_title",
            "title_zh",
            "chinese_title",
        )
        if not title_cn and contains_chinese(original_title):
            title_cn = original_title
        original_description = first_text(
            row,
            "original_summary",
            "original_content",
            "summary_original",
            "content_original",
            "summary",
            "excerpt",
            "content",
            "title",
        )
        description_cn = first_text(
            row,
            "summary_cn",
            "interpretive_summary_cn",
            "translation_cn",
            "translation",
            "content_cn",
        )
        if not description_cn and contains_chinese(original_description):
            description_cn = original_description
        output.append(
            {
                "source": source_display,
                "date": display_date(row.get("published_at")),
                "title": (title_cn or original_title)[:300],
                "title_cn": title_cn[:300],
                "original_title": original_title[:300],
                "description": (description_cn or original_description)[:800],
                "description_cn": description_cn[:800],
                "original_description": original_description[:800],
                "category": overseas_report_category(row),
                "url": str(row.get("url") or "#"),
                # Rows already present in the monitoring-system appendix generally
                # have no explicit origin field. Only rows explicitly injected by
                # a public collection step should be labelled as supplements.
                "origin": (
                    "公开网络补证"
                    if str(row.get("origin") or "").lower()
                    in {"public_web_supplement", "agent_reach", "mediaspider", "media_spider"}
                    else "监测系统 Excel"
                ),
            }
        )
    return output


def dashboard_overseas_comments(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = list((data.get("overseas") or {}).get("public_comments") or [])
    return [
        {
            "source": str(row.get("source") or row.get("platform") or "境外平台用户"),
            "platform": str(row.get("platform") or ""),
            "date": display_date(row.get("published_at")),
            "content": str(row.get("content") or row.get("title") or ""),
            "translation": str(row.get("translation") or row.get("translation_cn") or row.get("summary_cn") or ""),
            "url": str(row.get("url") or ""),
            "verified": bool(row.get("quote_verified")),
            "in_monitoring_window": row.get("in_monitoring_window") is not False,
            "comment_id": str(row.get("comment_id") or row.get("reply_id") or ""),
        }
        for row in rows
        if str(row.get("content") or row.get("title") or "").strip()
        and not is_disallowed_overseas_comment(row)
    ]


def dashboard_comment_groups(data: dict[str, Any]) -> list[dict[str, Any]]:
    selected = list((data.get("comments") or {}).get("selected") or [])
    selected.sort(key=lambda row: (row.get("report_order") if row.get("report_order") is not None else 999, str(row.get("published_at") or "")))
    groups: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for row in selected:
        if not is_actual_comment_row(row):
            continue
        heading = str(row.get("comment_heading") or row.get("topic") or "其他讨论")
        groups.setdefault(heading, []).append(
            {
                "content": str(row.get("content") or row.get("title") or ""),
                "source": str(row.get("source") or ""),
                "platform": str(row.get("platform") or ""),
                "url": str(row.get("url") or ""),
                "verified": bool(row.get("quote_verified")),
            }
        )
    return [{"heading": heading, "items": rows} for heading, rows in groups.items()]


def dashboard_comments_by_topic(data: dict[str, Any], topics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = list((data.get("comments") or {}).get("selected") or [])
    output: list[dict[str, Any]] = []
    for topic_row in topics:
        topic = str(topic_row.get("topic") or "")
        topic_key = canonical_topic_key(topic)
        items = []
        for row in selected:
            if not is_actual_comment_row(row):
                continue
            row_topics = [row.get("topic"), *(row.get("topic_hits") or [])]
            if topic_key not in {canonical_topic_key(value) for value in row_topics if value}:
                continue
            items.append({
                "heading": str(row.get("comment_heading") or f"关注{topic_row.get('display') or topic}"),
                "content": str(row.get("content") or row.get("title") or ""),
                "source": str(row.get("source") or ""),
                "platform": str(row.get("platform") or ""),
                "published_at": display_date(row.get("published_at")),
                "url": str(row.get("url") or ""),
                "verified": bool(row.get("quote_verified") and row.get("url")),
                "sentiment": str(row.get("sentiment") or "unknown"),
            })
        output.append({"topic": topic, "display": str(topic_row.get("display") or topic), "items": items})
    return output


def dashboard_media_evidence_by_topic(data: dict[str, Any], topics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    samples = list(data.get("samples") or [])
    # Only independent eligible voices are visible report samples.  Reposts,
    # mirrors and other same-claim pages remain in the research audit but must
    # not appear as extra dashboard cards or inflate the displayed sample count.
    research_audit = (
        ((data.get("analysis_bundle") or {}).get("research_audit") or {})
        .get("domestic_media_research")
        or {}
    )
    audited_candidates_by_topic: dict[str, list[dict[str, Any]]] = {}
    for pool_row in research_audit.get("candidate_pool_by_topic") or []:
        if not isinstance(pool_row, dict):
            continue
        pool_topic = str(pool_row.get("topic") or "").strip()
        if not pool_topic:
            continue
        audited_candidates_by_topic.setdefault(pool_topic, []).extend(
            {**row, "_audit_topic": pool_topic}
            for row in (pool_row.get("candidates") or [])
            if isinstance(row, dict) and str(row.get("decision") or "").lower() == "eligible"
        )

    def canonical_evidence_url(value: Any) -> str:
        return str(value or "").strip().split("#", 1)[0].rstrip("/")

    output: list[dict[str, Any]] = []
    for topic_row in topics:
        topic = str(topic_row.get("topic") or "")
        items: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        topic_candidates = list(audited_candidates_by_topic.get(topic) or [])
        if not topic_candidates:
            topic_key = canonical_topic_key(topic)
            for candidate_topic, rows in audited_candidates_by_topic.items():
                if canonical_topic_key(candidate_topic) == topic_key:
                    topic_candidates.extend(rows)

        for row in [*samples, *topic_candidates]:
            source_type = str(row.get("source_type") or "").strip().lower()
            if row.get("is_comment") or source_type in {
                "netizen_comment", "网民评论", "overseas_netizen", "overseas_public_discussion"
            }:
                continue
            if is_overseas_row(row):
                continue
            if (
                str(row.get("topic") or row.get("_audit_topic") or "") != topic
                and topic not in (row.get("topic_hits") or [])
            ):
                continue
            url = str(row.get("url") or "").strip()
            title = str(row.get("title") or row.get("content") or "").strip()
            source = str(row.get("source") or row.get("platform") or "来源").strip()
            if not url or url == "#" or not title:
                continue
            url_key = canonical_evidence_url(url)
            if url_key in seen_urls:
                continue
            seen_urls.add(url_key)
            attribution = evidence_attribution(row, row)
            description = str(
                row.get("summary")
                or row.get("excerpt")
                or row.get("content")
                or row.get("content_summary")
                or title
            )[:800]
            items.append({
                "source": source,
                "title": title[:220],
                "description": description,
                "platform": str(row.get("platform") or ""),
                "published_at": display_date(row.get("published_at")),
                "url": url,
                "origin": evidence_origin(row),
                **attribution,
            })
        output.append({"topic": topic, "display": str(topic_row.get("display") or topic), "items": items})
    return output


def is_actual_comment_row(row: dict[str, Any]) -> bool:
    mode = str(row.get("evidence_mode") or "").strip().lower()
    raw_file = str(row.get("raw_file") or "").lower()
    has_identity = bool(
        row.get("comment_id")
        or row.get("reply_id")
        or row.get("parent_comment_id")
        or any(marker in raw_file for marker in ("comment", "reply", "评论", "回复"))
    )
    return bool(
        row.get("quote_verified")
        and row.get("url")
        and mode in {"verbatim_public_comment", "verbatim_comment", "platform_comment", "platform_reply"}
        and has_identity
    )


def dashboard_wechat_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = list(((data.get("system_data") or {}).get("wechat_top") or []))
    best_by_source: dict[str, tuple[int, int, dict[str, Any]]] = {}
    for index, row in enumerate(rows):
        source = str(row.get("source") or "").strip()
        source_key = canonical_topic_key(source)
        if not source_key:
            source_key = canonical_topic_key(row.get("url") or row.get("title") or f"row-{index}")
        spread_count = as_int(row.get("spread_count") or row.get("spread_count_display"))
        current = best_by_source.get(source_key)
        if current is None or spread_count > current[0]:
            best_by_source[source_key] = (spread_count, index, row)
    rows = [item[2] for item in sorted(best_by_source.values(), key=lambda item: (-item[0], item[1]))[:10]]
    return [
        {
            "source": str(row.get("source") or ""),
            "title": str(row.get("title") or ""),
            "spread_count": str(row.get("spread_count_display") or row.get("spread_count") or "0"),
            "comment_count": str(row.get("comment_count") or "0"),
            "url": str(row.get("url") or "#"),
        }
        for row in rows
    ]


def split_formal_report(data: dict[str, Any]) -> dict[str, str]:
    report_path = path_from((data.get("artifacts") or {}).get("formal_report"))
    if not report_path or not report_path.exists():
        return {"lead": "", "one": "", "two": "", "three": "", "four": ""}

    text = report_path.read_text(encoding="utf-8").strip()
    headings = list(re.finditer(r"^##\s+(.+?)\s*$", text, flags=re.MULTILINE))
    if not headings:
        return {"lead": text, "one": "", "two": "", "three": "", "four": ""}

    sections = {"lead": text[: headings[0].start()].strip(), "one": "", "two": "", "three": "", "four": ""}
    for index, match in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        block = text[match.start() : end].strip()
        heading = match.group(1).strip()
        if heading.startswith("一、"):
            sections["one"] = block
        elif heading.startswith("二、"):
            sections["two"] = block
        elif heading.startswith("三、"):
            sections["three"] = block
        elif heading.startswith("附录") or heading.startswith("四、"):
            sections["four"] = block
    return {key: markdown_to_editor_text(value) for key, value in sections.items()}


def markdown_to_editor_text(text: str) -> str:
    lines = []
    for raw_line in str(text or "").splitlines():
        line = re.sub(r"^#{1,6}\s+", "", raw_line).rstrip()
        if re.match(r"^\|(?:\s*:?-{3,}:?\s*\|)+$", line):
            continue
        if line.startswith("|") and line.endswith("|"):
            cells = [cell.strip() for cell in line[1:-1].split("|")]
            line = "\t".join(cells)
        line = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1（\2）", line)
        lines.append(line)
    return "\n".join(lines).strip()


def editor_blocks(text: str) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []

    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if re.match(r"^\|(?:\s*:?-{3,}:?\s*\|)+$", line) or (line.startswith("|") and line.endswith("|")):
            continue
        match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if match:
            level = len(match.group(1))
            role = "h1" if level == 2 else "h2" if level == 3 else "h3"
            blocks.append({"role": role, "text": match.group(2).strip()})
            continue
        value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
        blocks.append({"role": "p", "text": value})
    return blocks


def build_report_blocks(data: dict[str, Any], report_path: Path | None) -> dict[str, list[dict[str, str]]]:
    sections: dict[str, list[dict[str, str]]] = {"lead": [], "one": [], "two": [], "three": [], "four": []}
    if report_path and report_path.exists():
        text = report_path.read_text(encoding="utf-8").strip()
        headings = list(re.finditer(r"^##\s+(.+?)\s*$", text, flags=re.MULTILINE))
        sections["lead"] = editor_blocks(text[: headings[0].start()] if headings else text)
        for index, match in enumerate(headings):
            end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
            heading = match.group(1).strip()
            if heading.startswith("一、"):
                key = "one"
            elif heading.startswith("二、"):
                key = "two"
            elif heading.startswith("三、"):
                key = "three"
            else:
                key = "four"
            sections[key] = editor_blocks(text[match.start():end])
    overrides = data.get("section_overrides") or {}
    for key in ["one", "two", "three", "four"]:
        rows = overrides.get(key)
        if not isinstance(rows, list):
            continue
        cleaned = [
            {"role": str(row.get("role") or "p"), "text": str(row.get("text") or "").strip()}
            for row in rows if isinstance(row, dict) and str(row.get("text") or "").strip()
        ]
        if cleaned:
            sections[key] = cleaned
    return sections


def prepare_dashboard_data(data: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    enrich_viewpoint_titles(data)
    meeting = data.get("meeting") or {}
    system_data = data.get("system_data") or {}
    overall = system_data.get("overall") or {}
    totals = overall.get("totals") or {}
    daily = list(overall.get("daily") or [])
    period = system_data.get("monitoring_period") or {}
    period_start = str(period.get("start") or "")
    period_end = str(period.get("end") or "")
    period_label = "至".join(filter(None, [chinese_date(period_start), chinese_date(period_end)])) or "监测周期未标注"
    meeting_date = str(meeting.get("date") or period_start or "")
    topics = list(data.get("topic_stats") or [])
    topic_display = {str(row.get("topic") or ""): str(row.get("display") or row.get("topic") or "") for row in topics}
    agenda_topics = [str(item) for item in meeting.get("topics") or [] if str(item).strip()]
    agenda = str(meeting.get("agenda") or "").strip()
    if len(agenda) < 24 and agenda_topics:
        agenda = "；".join(agenda_topics) + "。"

    chart_artifacts = (data.get("artifacts") or {}).get("docx_charts") or {}
    fallback_charts = (data.get("artifacts") or {}).get("charts") or {}
    local_system_charts = {
        key: out_dir / "charts" / f"{key}_system.png"
        for key in ("trend_distribution", "topic_distribution")
    }
    images = {
        "trend": image_data_uri(
            local_system_charts["trend_distribution"]
            if local_system_charts["trend_distribution"].exists()
            else chart_artifacts.get("trend_distribution") or fallback_charts.get("trend_distribution")
        ),
        "topic": image_data_uri(
            local_system_charts["topic_distribution"]
            if local_system_charts["topic_distribution"].exists()
            else chart_artifacts.get("topic_distribution") or fallback_charts.get("topic_distribution")
        ),
        "hotword": first_image_data_uri(
            (data.get("artifacts") or {}).get("wordcloud_image"),
            out_dir / "charts" / "hotword_distribution_pipeline.png",
            chart_artifacts.get("hotword_distribution"),
            fallback_charts.get("hotword_distribution"),
            out_dir / "charts" / "hotword_distribution_system.png",
        ),
    }

    topic_rows = []
    for row in topics:
        topic_rows.append(
            {
                "topic": str(row.get("topic") or ""),
                "display": str(row.get("display") or row.get("topic") or ""),
                "domestic_media": as_int(row.get("domestic_media")),
                "self_media": as_int(row.get("self_media")),
                "overseas_media": as_int(row.get("overseas_media")),
                "spread_count": as_int(row.get("spread_count")),
                "sentiment": normalized_sentiment(row.get("sentiment")),
                "sentiment_ready": formal_sentiment_row_ready(row),
                "sentiment_sample_status": str(row.get("sentiment_sample_status") or "pending"),
                "sentiment_denominator": as_int(row.get("sentiment_denominator")),
                "sentiment_authority": str(row.get("sentiment_authority") or "unverified"),
            }
        )

    all_samples = list(data.get("samples") or [])
    research_pool = (
        ((((data.get("analysis_bundle") or {}).get("research_audit") or {}).get("domestic_media_research") or {})
        .get("candidate_pool_by_topic"))
        or []
    )
    for pool_row in research_pool:
        if not isinstance(pool_row, dict):
            continue
        audit_topic = str(pool_row.get("topic") or "").strip()
        for candidate in pool_row.get("candidates") or []:
            if not isinstance(candidate, dict) or str(candidate.get("decision") or "").lower() != "duplicate":
                continue
            all_samples.append({
                **candidate,
                "topic": audit_topic,
                "topic_hits": [audit_topic],
                "claim": str(candidate.get("content_summary") or candidate.get("decision_reason") or ""),
                "description": str(candidate.get("content_summary") or candidate.get("decision_reason") or ""),
                "origin": "直接来源补证（同观点）",
            })
    sample_by_url: dict[str, list[dict[str, Any]]] = {}
    for sample in all_samples:
        url = str(sample.get("url") or "").strip()
        if url:
            sample_by_url.setdefault(url, []).append(sample)

    viewpoints = []
    for item in (data.get("viewpoints") or {}).get("by_topic") or []:
        clusters = []
        for cluster in item.get("clusters") or []:
            evidence_rows = []
            for evidence in cluster.get("evidence") or []:
                url = str(evidence.get("url") or "#")
                matches = sample_by_url.get(url, []) if url != "#" else []
                if is_overseas_row(evidence) or (matches and all(is_overseas_row(row) for row in matches)):
                    continue
                origin_row = matches[0] if matches else evidence
                attribution = evidence_attribution(
                    evidence,
                    origin_row,
                )
                context_text = "。".join(
                    str(cluster.get(key) or "") for key in ("summary", "details", "analysis")
                )
                direct_evidence_text = " ".join(
                    str(row.get(key) or "")
                    for row in (evidence, origin_row)
                    for key in ("attribution", "description", "summary", "excerpt", "content", "title")
                )
                attribution = match_titled_person_in_evidence(
                    context_text,
                    direct_evidence_text,
                    attribution,
                )
                expanded_claims = expand_multi_voice_claims(
                    cluster.get("details") or cluster.get("analysis"),
                    attribution,
                    evidence.get("formal_claim")
                    or evidence.get("claim")
                    or evidence.get("summary")
                    or evidence.get("excerpt")
                    or evidence.get("content"),
                )
                for voice_attribution, voice_claim in expanded_claims:
                    evidence_rows.append({
                        "source": str(evidence.get("source") or "来源"),
                        "title": str(evidence.get("title") or evidence.get("content") or "")[:160],
                        "claim": voice_claim[:800],
                        "description": str(
                            evidence.get("summary")
                            or evidence.get("excerpt")
                            or evidence.get("content")
                            or origin_row.get("summary")
                            or origin_row.get("excerpt")
                            or origin_row.get("content")
                            or evidence.get("title")
                            or ""
                        )[:800],
                        "url": url,
                        "origin": evidence_origin(origin_row),
                        "duplicate_source_audit": dedupe_supporting_links(
                            list(evidence.get("supporting_samples") or evidence.get("supporting_links") or [])
                            or supporting_links_for_evidence(evidence, str(item.get("topic") or ""), all_samples)
                        ),
                        **voice_attribution,
                    })
            if evidence_rows:
                normalized_cluster = {
                    **cluster,
                    "details": str(cluster.get("details") or cluster.get("analysis") or ""),
                    "evidence": evidence_rows,
                }
                clusters.append(
                    {
                        "summary": str(cluster.get("summary") or ""),
                        "details": str(cluster.get("details") or cluster.get("analysis") or ""),
                        "evidence": evidence_rows,
                        "needs_attribution_review": cluster_needs_attribution_review(normalized_cluster),
                    }
                )
        topic = str(item.get("topic") or "")
        viewpoints.append({"topic": topic, "display": topic_display.get(topic, topic), "clusters": clusters})

    audit = data.get("audit") or {}
    quality_summary = audit.get("quality_summary") or {}
    actual_comments = [
        row for row in ((data.get("comments") or {}).get("selected") or [])
        if is_actual_comment_row(row)
    ]
    traceable_overseas_comments = [
        row
        for row in ((data.get("overseas") or {}).get("public_comments") or [])
        if row.get("quote_verified")
        and row.get("url")
        and (row.get("comment_id") or row.get("reply_id"))
        and not is_disallowed_overseas_comment(row)
    ]
    system_detail_count = as_int((data.get("collection") or {}).get("system_evidence_sample_count"))
    supplemental_detail_count = max(0, len(data.get("samples") or []) - system_detail_count)
    docx_validation = audit.get("formal_docx_validation") or {}
    acceptance = audit.get("acceptance") or {}
    artifacts = data.get("artifacts") or {}
    peak = max(daily, key=lambda row: as_int(row.get("total_spread")), default={})
    title_date = chinese_date(meeting_date)
    title = f"{title_date}国务院常务会议舆情情况" if title_date else "国务院常务会议舆情情况"
    if data.get("delivery_class") == "review_draft":
        title += " 待审核稿 未通过正式交付"
    report_sections = split_formal_report(data)
    report_path = path_from((data.get("artifacts") or {}).get("formal_report"))
    blocks = build_report_blocks(data, report_path)
    report_marker = out_dir / ".cwh_report_id"
    persisted_report_id = report_marker.read_text(encoding="ascii", errors="ignore").strip().lower() if report_marker.exists() else ""
    report_id = (
        persisted_report_id
        if re.fullmatch(r"[a-f0-9]{12}", persisted_report_id)
        else hashlib.sha1(str(out_dir.resolve()).lower().encode("utf-8")).hexdigest()[:12]
    )

    return {
        # Keep the immutable upstream evidence mapping in the self-contained
        # dashboard. The delivery gate compares this exact structure with
        # report_data.json; a flattened display-only projection is not enough.
        "analysis_bundle": data.get("analysis_bundle") or {},
        "title": title,
        "sentiment_available": formal_sentiment_available(data),
        "meeting_date": chinese_date(meeting_date),
        "agenda": agenda,
        "generated_at": str(data.get("generated_at") or ""),
        "period": {"start": period_start, "end": period_end, "label": period_label},
        "totals": {
            "total_spread": as_int(totals.get("total_spread") or (data.get("statistics") or {}).get("total_spread")),
            "domestic_mainstream": as_int(totals.get("domestic_mainstream")),
            "overseas_media": as_int(totals.get("overseas_media")),
            "wechat_public": as_int(totals.get("wechat_public")),
            "weibo": as_int(totals.get("weibo")),
            "video_account": as_int(totals.get("video_account")),
            "new_media": as_int(totals.get("new_media")),
        },
        "peak": {
            "date": str(peak.get("date") or ""),
            "date_label": display_date(peak.get("date")),
            "value": as_int(peak.get("total_spread")),
        },
        "topics": topic_rows,
        "viewpoints": viewpoints,
        "media_evidence_by_topic": dashboard_media_evidence_by_topic(data, topic_rows),
        "comment_groups": dashboard_comment_groups(data),
        "comments_by_topic": dashboard_comments_by_topic(data, topic_rows),
        "hotwords": [
            {
                "word": str(row.get("word") or ""),
                "topic": str(row.get("topic") or ""),
                "count": max(1, as_int(row.get("count"))),
                "weight": max(
                    1,
                    as_int(
                        row.get("display_weight")
                        or row.get("score")
                        or row.get("weight")
                        or row.get("count")
                    ),
                ),
            }
            for row in list(data.get("hotwords") or [])
            if str(row.get("word") or "").strip()
        ],
        "overseas": dashboard_overseas_rows(data),
        "overseas_comments": dashboard_overseas_comments(data),
        "wechat_top": dashboard_wechat_rows(data),
        "report_sections": report_sections,
        "report_blocks": blocks,
        "report_id": report_id,
        "data_import": {"accept_multiple": True, "profile_only_until_adapter_ready": True},
        "images": images,
        "quality": {
            "subevents": as_int(quality_summary.get("system_subevents") or len(topic_rows)),
            "detail_samples": as_int(quality_summary.get("detail_samples") or len(data.get("samples") or [])),
            "comments": as_int(quality_summary.get("comment_details") or len((data.get("comments") or {}).get("selected") or [])),
            "traceable_comments": len(actual_comments) + len(traceable_overseas_comments),
            "domestic_details": as_int(quality_summary.get("domestic_media_details")),
            "system_detail_samples": system_detail_count,
            "supplemental_detail_samples": supplemental_detail_count,
            "viewpoint_clusters": sum(len(item.get("clusters") or []) for item in viewpoints),
            "hyperlinks": as_int(docx_validation.get("hyperlink_count")),
            "system_assets": bool(docx_validation.get("checks", {}).get("uses_monitoring_system_assets")),
            "docx_passed": bool(docx_validation.get("passed")),
        },
        "delivery": {
            "ready": bool(acceptance.get("ready_for_formal_delivery")),
            "blockers": len(acceptance.get("blockers") or []),
        },
        "artifacts": {
            "word": artifact(artifacts.get("formal_docx"), out_dir, "word"),
            "excel": artifact(artifacts.get("data_workbook"), out_dir, "excel"),
            "data": artifact(artifacts.get("report_data") or out_dir / "report_data.json", out_dir),
            "audit": artifact(artifacts.get("audit") or out_dir / "cwh_audit.json", out_dir),
        },
    }


def generate_dashboard(data: dict[str, Any], out_path: Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Dashboard template not found: {TEMPLATE_PATH}")
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    if "__DASHBOARD_DATA__" not in template:
        raise ValueError("Dashboard template is missing __DASHBOARD_DATA__ placeholder")
    dashboard_data = prepare_dashboard_data(data, out_path.parent)
    if data.get("delivery_class") == "review_draft" and not data.get("system_data"):
        dashboard_data["totals"] = dict.fromkeys(dashboard_data["totals"])
        dashboard_data["peak"]["value"] = None
    payload = json.dumps(dashboard_data, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    out_path.write_text(template.replace("__DASHBOARD_DATA__", payload), encoding="utf-8")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a self-contained CWH report dashboard from report_data.json")
    parser.add_argument("report_data", help="Path to report_data.json")
    parser.add_argument("--output", default="", help="Output HTML path. Defaults to cwh_dashboard.html beside report_data.json")
    args = parser.parse_args()
    data_path = Path(args.report_data)
    data = json.loads(data_path.read_text(encoding="utf-8"))
    output = Path(args.output) if args.output else data_path.parent / "cwh_dashboard.html"
    generate_dashboard(data, output)
    print(json.dumps({"status": "ok", "dashboard": str(output)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
