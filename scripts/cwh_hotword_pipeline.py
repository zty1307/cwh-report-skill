from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
from collections import Counter, defaultdict, deque
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont


DEFAULT_COLOR = "#0D4E6D"
DEFAULT_ROTATION = -15
DEFAULT_WIDTH = 1600
DEFAULT_HEIGHT = 1000
DEFAULT_TERM_COUNT = 42
DEFAULT_PRIMARY_FONT_MIN = 22
DEFAULT_PRIMARY_FONT_MAX = 150
DEFAULT_FONT_SCALE_EXPONENT = 3.0
DEFAULT_REPEAT_REFERENCE_MIN = 28
DEFAULT_REPEAT_REFERENCE_MAX = 96
DEFAULT_REPEAT_REFERENCE_EXPONENT = 0.5
DEFAULT_REPEAT_SCALES = (
    0.38,
    0.32,
    0.27,
    0.23,
    0.20,
    0.18,
    0.16,
    0.14,
    0.12,
    0.10,
    0.09,
    0.08,
)
DEFAULT_MAX_PLACED_INSTANCES = 289
DEFAULT_RENDER_SCALE = 2
DEFAULT_WORD_SPACING = 2
DEFAULT_LAYOUT_X_SPREAD = 1.10
DEFAULT_LAYOUT_Y_SPREAD = 0.98
DEFAULT_CLOUD_MASK_ASSET = Path(__file__).resolve().parent.parent / "assets" / "wordcloud_cloud_mask.png"
BUNDLED_CJK_FONT = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "TencentFont.otf"
BUNDLED_CJK_FALLBACK_FONT = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "NotoSansCJKsc-Regular.otf"
DEFAULT_FONT_PATH = BUNDLED_CJK_FONT
DEFAULT_MICROCLOUD_GRID = 300
DEFAULT_MICROCLOUD_DENSITY = 0.18
DEFAULT_MICROCLOUD_HEADLINE_SCALE = 1.30
DEFAULT_MICROCLOUD_BOUNDARY_FILL_START_RANK = 43
DEFAULT_MICROCLOUD_BOUNDARY_WEIGHT = 6.0
DEFAULT_MICROCLOUD_RANK_CURVE = (
    (1, 1.00),
    (2, 0.72),
    (3, 0.64),
    (4, 0.57),
    (5, 0.51),
    (6, 0.45),
    (8, 0.39),
    (10, 0.35),
    (15, 0.295),
    (22, 0.255),
    (30, 0.215),
    (42, 0.18),
    (43, 0.16),
    (55, 0.14),
    (65, 0.12),
)

# Rank anchors learned from the approved 微词云 reference. They describe a
# reusable composition: the strongest word sits at the visual centre, ranks
# two to seven form the lower/upper shoulders, and the remaining words fill
# the silhouette. They do not encode any meeting-specific word or coordinate.
DEFAULT_PRIMARY_ANCHORS = (
    (0.53, 0.55),
    (0.42, 0.70),
    (0.56, 0.36),
    (0.59, 0.22),
    (0.60, 0.11),
    (0.27, 0.86),
    (0.75, 0.68),
    (0.62, 0.05),
    (0.72, 0.81),
    (0.31, 0.92),
)

# Lower-ranked words are routed through stable zones instead of all starting
# from the same centre. The first repeated headwords fill balanced interior
# gaps; smaller repeated terms then trace the cloud perimeter so the three
# upper lobes, side arcs and flat lower edge remain legible.
DEFAULT_INTERIOR_FILL_ANCHORS = (
    (0.24, 0.48),
    (0.76, 0.48),
    (0.31, 0.61),
    (0.69, 0.60),
    (0.22, 0.72),
    (0.78, 0.72),
    (0.37, 0.82),
    (0.63, 0.83),
    (0.43, 0.44),
    (0.61, 0.43),
    (0.49, 0.73),
    (0.53, 0.88),
)
DEFAULT_PERIMETER_FILL_ANCHORS = (
    (0.36, 0.15),
    (0.43, 0.09),
    (0.51, 0.07),
    (0.59, 0.08),
    (0.67, 0.13),
    (0.74, 0.19),
    (0.81, 0.27),
    (0.87, 0.37),
    (0.91, 0.48),
    (0.92, 0.59),
    (0.89, 0.69),
    (0.84, 0.78),
    (0.76, 0.86),
    (0.66, 0.91),
    (0.55, 0.94),
    (0.44, 0.94),
    (0.33, 0.92),
    (0.24, 0.87),
    (0.17, 0.80),
    (0.11, 0.71),
    (0.08, 0.61),
    (0.09, 0.52),
    (0.13, 0.44),
    (0.19, 0.37),
    (0.26, 0.31),
    (0.33, 0.25),
)

# The approved 70-word reference becomes horizontally aligned after a +15°
# deskew. These normalized foci describe a reusable cloud-lobe skeleton. Every
# rank cycles through them; no meeting-specific term or final position is kept.
DEFAULT_FOCUS_ANCHORS = (
    (0.47, 0.53),
    (0.28, 0.68),
    (0.47, 0.40),
    (0.57, 0.33),
    (0.55, 0.25),
    (0.35, 0.76),
    (0.72, 0.63),
)

GENERIC_TERMS = {
    "国务院",
    "国务院常务会议",
    "国务院常务会",
    "国常会",
    "常务会议",
    "会议",
    "会议指出",
    "会议强调",
    "会议审议",
    "工作",
    "有关工作",
    "情况",
    "有关情况",
    "汇报",
    "研究",
    "审议通过",
    "进一步",
    "加快推进",
    "部署",
    "我国",
    "中国",
    "发展",
    "建设",
    "推进",
    "加强",
    "完善",
    "政策",
    "相关",
    "重点",
    "领域",
    "要求",
    "支持",
    "做好",
    "坚持",
    "关于",
    "使用",
    "决定",
    "通过",
    "调整",
    "范围",
    "召开",
    "实施",
    "开展",
    "进行",
    "提出",
    "指出",
    "强调",
    "认为",
    "表示",
    "以及",
    "其中",
    "此次",
    "本次",
    "投资",
    "项目",
    "工程",
    "市场",
    "制度",
    "条例",
    "机组",
}

HOTWORD_SEMANTIC_TYPES = {
    "agenda_topic",
    "policy_goal",
    "policy_tool",
    "governance_mechanism",
    "infrastructure_or_sector",
    "public_concern",
}
PROCEDURAL_HOTWORD_MARKERS = {
    "召开",
    "听取",
    "研究",
    "审议",
    "通过",
    "决定",
    "修改",
    "废止",
    "核准",
}
PROVINCE_REGION_PREFIXES = {
    "北京", "天津", "河北", "山西", "内蒙古", "辽宁", "吉林", "黑龙江",
    "上海", "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南",
    "湖北", "湖南", "广东", "广西", "海南", "重庆", "四川", "贵州",
    "云南", "西藏", "陕西", "甘肃", "青海", "宁夏", "新疆", "香港",
    "澳门", "台湾",
}
GEOGRAPHY_POLICY_QUALIFIERS = {
    "发展", "振兴", "改革", "开放", "合作", "治理", "保护", "生态",
    "经济", "产业", "就业", "教育", "医疗", "养老", "住房", "交通",
    "能源", "电网", "物流", "流域", "城市群", "一体化", "自贸港",
    "自贸区", "经济带", "示范区", "试验区", "通道", "基地", "安全",
}
ACCEPTED_HOTWORD_STYLE_PATTERNS = [
    "领域限定的议题名称：脱离上下文仍能识别具体政策领域",
    "政策目标或治理结果：使用完整名词短语，不包含会议程序动作",
    "政策工具或治理机制：写清适用对象、治理环节或政策领域",
    "基础设施、产业或公共服务名称：不得只保留项目、工程等载体词",
    "公众关切或风险名称：表达具体问题，不使用泛化情绪或公文套话",
    "证据长措辞可压缩为简洁展示词，但必须在evidence_aliases保留原文",
]
REJECTED_HOTWORD_STYLE_PATTERNS = [
    "会议程序动作：召开、听取、研究、审议、通过、决定、修改、废止、核准",
    "无领域限定的载体词：投资、项目、工程、市场、制度",
    "公文连接词或套话：关于、进一步、相关、做好、使用",
    "实体与时间噪声：纯地名、项目所在地、领导姓名、媒体名称、机构简称、日期",
    "断裂切片：被截断的人名、机构名、词根或半个短语",
]

GENERIC_PARTICLES = set("的了和与及或把被为在对等上中下前后要将从向让各更再就可需应")
SENTENCE_SPLIT = re.compile(r"[\s，。！？；：、,.!?;:（）()《》【】\[\]“”\"'—…/|]+")
CHINESE_BLOCK = re.compile(r"[\u3400-\u9fff]{2,32}")


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", "", "" if value is None else str(value)).lower()


def contains_any(text: str, needles: Iterable[str]) -> bool:
    normalized = normalize_text(text)
    return any(normalize_text(needle) in normalized for needle in needles if normalize_text(needle))


def canonical_document_key(row: dict[str, Any]) -> str:
    title = normalize_text(row.get("title"))
    if title:
        return title
    url = normalize_text(row.get("url"))
    return url or f"row:{row.get('source_row', '')}"


def topic_for_term(term: str, topic_aliases: list[list[str]]) -> list[int]:
    hits: list[int] = []
    normalized_term = normalize_text(term)
    for index, aliases in enumerate(topic_aliases, start=1):
        if any(
            normalize_text(alias) in normalized_term or normalized_term in normalize_text(alias)
            for alias in aliases
            if normalize_text(alias)
        ):
            hits.append(index)
    return hits


def deduplicate_documents(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = canonical_document_key(row)
        current = by_key.get(key)
        if current is None or len(str(row.get("content") or "")) > len(str(current.get("content") or "")):
            by_key[key] = row
    return list(by_key.values())


def relevant_documents(
    rows: list[dict[str, Any]],
    topic_aliases: list[list[str]],
    meeting_anchors: list[str],
) -> list[dict[str, Any]]:
    normalized_aliases = [
        [normalize_text(alias) for alias in aliases if normalize_text(alias)]
        for aliases in topic_aliases
    ]
    all_aliases = [alias for aliases in normalized_aliases for alias in aliases]
    normalized_anchors = [normalize_text(anchor) for anchor in meeting_anchors if normalize_text(anchor)]
    kept = []
    for row in rows:
        title = normalize_text(row.get("title"))
        content = normalize_text(row.get("content"))
        combined = title + content
        if any(alias in combined for alias in all_aliases) and (
            any(anchor in title for anchor in normalized_anchors)
            or any(anchor in content[:1800] for anchor in normalized_anchors)
            or sum(any(alias in combined for alias in aliases) for aliases in normalized_aliases) >= 2
        ):
            kept.append(row)
    return deduplicate_documents(kept)


def evidence_for_term(
    term: str,
    documents: list[dict[str, Any]],
    topic_aliases: list[list[str]],
) -> dict[str, Any]:
    normalized_term = normalize_text(term)
    matching = []
    title_hits = 0
    sources: set[str] = set()
    comment_count = 0
    media_document_count = 0
    for row in documents:
        title = normalize_text(row.get("title"))
        content = normalize_text(row.get("content"))
        if normalized_term and normalized_term in title + content:
            matching.append(row)
            title_hits += int(normalized_term in title)
            sources.add(str(row.get("account") or row.get("source") or "未知来源"))
            source_type = normalize_text(row.get("source_type") or row.get("evidence_type"))
            is_comment = bool(row.get("is_comment")) or source_type in {
                "netizen_comment",
                "platform_comment",
                "comment",
                "comments",
            }
            comment_count += int(is_comment)
            media_document_count += int(not is_comment)
    return {
        "term": term,
        "topic_hits": topic_for_term(term, topic_aliases),
        "document_count": len(matching),
        "title_hits": title_hits,
        "source_count": len(sources),
        "media_document_count": media_document_count,
        "comment_count": comment_count,
        "sample_titles": [str(row.get("title") or "") for row in matching[:3]],
        "sample_urls": [str(row.get("url") or "") for row in matching[:3]],
    }


def semantic_representativeness(item: dict[str, Any]) -> float:
    """Deterministic fallback for the 15-point AI review dimension."""
    term = str(item.get("term") or "")
    score = 7.0
    if 2 <= len(term) <= 8:
        score += 2.0
    if item.get("topic_hits"):
        score += 2.0
    if int(item.get("document_count") or 0) >= 2:
        score += 2.0
    if not any(generic in term for generic in GENERIC_TERMS if len(generic) >= 2):
        score += 2.0
    return min(15.0, score)


def normalize_ai_representativeness(value: Any, fallback: float) -> float:
    if isinstance(value, str):
        mapped = {"高": 15.0, "high": 15.0, "中": 10.0, "medium": 10.0, "低": 5.0, "low": 5.0}
        if value.strip().lower() in mapped:
            return mapped[value.strip().lower()]
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = fallback
    return max(0.0, min(15.0, numeric))


def score_hotword_evidence(
    item: dict[str, Any],
    *,
    comments_available: bool,
    topic_balance: float = 10.0,
    ai_representativeness: Any = None,
) -> tuple[float, dict[str, float]]:
    """Apply the original evidence-led display-weight formula."""
    raw = {
        "independent_sample_coverage": 30.0 * min(1.0, int(item.get("document_count") or 0) / 5.0),
        "title_or_lead_salience": 20.0 * min(1.0, int(item.get("title_hits") or 0) / 3.0),
        "source_diversity": 15.0 * min(1.0, int(item.get("source_count") or 0) / 4.0),
        "ai_semantic_representativeness": normalize_ai_representativeness(
            ai_representativeness,
            semantic_representativeness(item),
        ),
        "verified_comment_mentions": 10.0 * min(1.0, int(item.get("comment_count") or 0) / 3.0),
        "subtopic_balance": max(0.0, min(10.0, float(topic_balance))),
    }
    if comments_available:
        components = raw
    else:
        # The original rule redistributes the unavailable comment dimension
        # proportionally instead of treating a missing collector as zero heat.
        factor = 100.0 / 90.0
        components = {
            key: round(value * factor, 3)
            for key, value in raw.items()
            if key != "verified_comment_mentions"
        }
        components["verified_comment_mentions"] = 0.0
    return round(sum(components.values()), 3), components


def snippets_for_topic(text: str, aliases: list[str], radius: int = 110) -> list[str]:
    normalized = normalize_text(text)
    snippets: list[str] = []
    for alias in aliases:
        needle = normalize_text(alias)
        start = 0
        while needle and (position := normalized.find(needle, start)) >= 0:
            snippets.append(normalized[max(0, position - radius) : position + len(needle) + radius])
            start = position + len(needle)
            if len(snippets) >= 12:
                return snippets
    return snippets


@lru_cache(maxsize=131072)
def valid_candidate(term: str) -> bool:
    if not 2 <= len(term) <= 10:
        return False
    if term in GENERIC_TERMS:
        return False
    # Reject short pieces cut out of recurring meeting boilerplate, such as
    # “国务”“务院”“国常”“常会”. They are not valid semantic terms even when
    # a sliding n-gram extractor sees them in many titles.
    if len(term) <= 3 and any(term in generic for generic in GENERIC_TERMS if len(generic) > len(term)):
        return False
    if (term[0] in GENERIC_PARTICLES and not term.startswith("可持续")) or term[-1] in GENERIC_PARTICLES:
        return False
    if any(generic in term and len(term) <= len(generic) + 1 for generic in GENERIC_TERMS):
        return False
    if len(set(term)) <= 1:
        return False
    return bool(re.fullmatch(r"[\u3400-\u9fffA-Za-z0-9＋+－-]+", term))


def looks_like_pure_geography(term: str) -> bool:
    """Reject obvious place labels while allowing place-qualified policy concepts."""
    normalized = normalize_text(term)
    starts_with_region = any(normalized.startswith(prefix) for prefix in PROVINCE_REGION_PREFIXES)
    if not starts_with_region:
        return False
    return not any(qualifier in normalized for qualifier in GEOGRAPHY_POLICY_QUALIFIERS)


def generate_candidates(
    documents: list[dict[str, Any]],
    topic_titles: list[str],
    topic_aliases: list[list[str]],
) -> list[dict[str, Any]]:
    candidate_topics: dict[str, set[int]] = defaultdict(set)
    seed_terms: set[str] = set()
    for topic_index, (title, aliases) in enumerate(zip(topic_titles, topic_aliases), start=1):
        for term in [title, *aliases]:
            cleaned = normalize_text(term)
            cleaned = re.sub(r"^(进一步部署|听取|研究|审议通过)", "", cleaned)
            cleaned = re.sub(r"(有关工作|建设情况汇报|进展情况汇报|情况汇报)$", "", cleaned)
            if valid_candidate(cleaned):
                seed_terms.add(cleaned)
                candidate_topics[cleaned].add(topic_index)

    ngram_docs: dict[tuple[int, str], set[int]] = defaultdict(set)
    ngram_titles: Counter[tuple[int, str]] = Counter()
    ngram_sources: dict[tuple[int, str], set[str]] = defaultdict(set)
    normalized_topic_aliases = [
        [normalize_text(alias) for alias in aliases if normalize_text(alias)]
        for aliases in topic_aliases
    ]
    for doc_index, row in enumerate(documents):
        title = normalize_text(row.get("title"))
        combined = normalize_text(f"{row.get('title', '')}\n{row.get('content', '')}")
        source = str(row.get("account") or row.get("source") or "未知来源")
        for topic_index, aliases in enumerate(normalized_topic_aliases, start=1):
            if not any(alias in combined for alias in aliases):
                continue
            # Candidate extraction is only an evidence index for the model, so
            # cap per-document context instead of enumerating every 2-8 gram in
            # a long article. The AI review packet still carries document
            # excerpts and may add missing evidence-backed terms.
            snippets: list[str] = []
            for alias in aliases:
                start = 0
                for _ in range(2):
                    position = combined.find(alias, start)
                    if position < 0:
                        break
                    snippets.append(combined[max(0, position - 70) : position + len(alias) + 70])
                    start = position + len(alias)
                if len(snippets) >= 6:
                    break
            topic_text = f"{title}\n{''.join(snippets[:6])}"
            blocks = list(dict.fromkeys(CHINESE_BLOCK.findall(topic_text)))
            for block in blocks:
                block = block[:180]
                for length in range(2, min(7, len(block) + 1)):
                    for start in range(0, len(block) - length + 1):
                        term = block[start : start + length]
                        if not valid_candidate(term):
                            continue
                        key = (topic_index, term)
                        ngram_docs[key].add(doc_index)
                        ngram_sources[key].add(source)
                        if term in title:
                            ngram_titles[key] += 1

    raw_rows: list[dict[str, Any]] = []
    for (topic_index, term), doc_ids in ngram_docs.items():
        title_hits = ngram_titles[(topic_index, term)]
        source_count = len(ngram_sources[(topic_index, term)])
        doc_count = len(doc_ids)
        if doc_count < 2 and title_hits == 0:
            continue
        score = (doc_count * 1.8 + title_hits * 4.0 + source_count * 1.2) * (1.0 + min(len(term), 7) * 0.06)
        raw_rows.append(
            {
                "term": term,
                "topic_index": topic_index,
                "document_count": doc_count,
                "title_hits": title_hits,
                "source_count": source_count,
                "score": round(score, 3),
            }
        )

    raw_rows.sort(key=lambda item: (-item["score"], -len(item["term"]), item["term"]))
    filtered: list[dict[str, Any]] = []
    per_topic = Counter()
    for item in raw_rows:
        term = item["term"]
        topic_index = item["topic_index"]
        if per_topic[topic_index] >= 30:
            continue
        if any(
            term in kept["term"]
            and kept["topic_index"] == topic_index
            and kept["document_count"] >= item["document_count"] * 0.85
            for kept in filtered
        ):
            continue
        item["topic_hits"] = [topic_index]
        filtered.append(item)
        per_topic[topic_index] += 1

    evidence_by_term = {item["term"]: item for item in filtered}
    for term in seed_terms:
        evidence = evidence_for_term(term, documents, topic_aliases)
        current = evidence_by_term.get(term)
        if current:
            current["topic_hits"] = sorted(set(current["topic_hits"] + list(candidate_topics[term])))
            current["is_topic_anchor"] = True
            continue
        evidence["score"] = round(
            8.0
            + evidence["document_count"] * 1.8
            + evidence["title_hits"] * 4.0
            + evidence["source_count"] * 1.2,
            3,
        )
        filtered.append({**evidence, "is_topic_anchor": True})

    # Normalize each article only once. The previous implementation normalized
    # every full article again for every candidate, which made a 2,000-row
    # bundle take several minutes before the AI review could even start.
    evidence_map: dict[str, dict[str, Any]] = {
        item["term"]: {
            "term": item["term"],
            "topic_hits": topic_for_term(item["term"], topic_aliases),
            "document_count": 0,
            "title_hits": 0,
            "sources": set(),
            "media_document_count": 0,
            "comment_count": 0,
            "sample_titles": [],
            "sample_urls": [],
        }
        for item in filtered
    }
    terms_by_first: dict[str, list[str]] = defaultdict(list)
    for term in evidence_map:
        terms_by_first[term[0]].append(term)
    for row in documents:
        title = normalize_text(row.get("title"))
        content = normalize_text(row.get("content"))
        combined = title + content
        source = str(row.get("account") or row.get("source") or "未知来源")
        source_type = normalize_text(row.get("source_type") or row.get("evidence_type"))
        is_comment = bool(row.get("is_comment")) or source_type in {
            "netizen_comment", "platform_comment", "comment", "comments"
        }
        for first in set(combined):
            for term in terms_by_first.get(first, []):
                if term not in combined:
                    continue
                evidence = evidence_map[term]
                evidence["document_count"] += 1
                evidence["title_hits"] += int(term in title)
                evidence["sources"].add(source)
                evidence["comment_count"] += int(is_comment)
                evidence["media_document_count"] += int(not is_comment)
                if len(evidence["sample_titles"]) < 3:
                    evidence["sample_titles"].append(str(row.get("title") or ""))
                    evidence["sample_urls"].append(str(row.get("url") or ""))
    enriched = []
    for item in filtered:
        evidence = evidence_map[item["term"]]
        serializable_evidence = {
            key: value for key, value in evidence.items() if key != "sources"
        }
        serializable_evidence["source_count"] = len(evidence["sources"])
        enriched.append(
            {
                **item,
                **serializable_evidence,
                "topic_hits": item.get("topic_hits") or serializable_evidence["topic_hits"],
            }
        )
    enriched.sort(key=lambda item: (-float(item.get("score") or 0), -len(item["term"]), item["term"]))
    return enriched[:240]


def deterministic_selection(candidates: list[dict[str, Any]], term_count: int) -> list[dict[str, Any]]:
    comments_available = any(int(item.get("comment_count") or 0) > 0 for item in candidates)
    prepared = []
    for item in candidates:
        score, components = score_hotword_evidence(
            item,
            comments_available=comments_available,
            topic_balance=10.0,
        )
        prepared.append({**item, "display_score": score, "score_components": components})
    candidates = sorted(
        prepared,
        key=lambda item: (
            -float(item.get("display_score") or 0),
            -int(item.get("document_count") or 0),
            -len(str(item.get("term") or "")),
            str(item.get("term") or ""),
        ),
    )
    selected: list[dict[str, Any]] = []
    selected_terms: set[str] = set()
    topic_counts = Counter()
    topic_total = max((max(item.get("topic_hits") or [0]) for item in candidates), default=0)
    quota = max(4, math.ceil(term_count / max(1, topic_total)))

    def add(item: dict[str, Any]) -> bool:
        term = item["term"]
        document_count = int(item.get("document_count") or 0)
        if document_count < 1 or (document_count < 2 and not item.get("is_topic_anchor")):
            return False
        if term in selected_terms or term in GENERIC_TERMS:
            return False
        if any(term in existing or existing in term for existing in selected_terms if min(len(term), len(existing)) <= 3):
            return False
        selected_terms.add(term)
        selected.append(item)
        for topic in item.get("topic_hits") or []:
            topic_counts[topic] += 1
        return True

    for topic in range(1, topic_total + 1):
        for item in candidates:
            if topic in (item.get("topic_hits") or []) and topic_counts[topic] < quota:
                add(item)
            if topic_counts[topic] >= quota:
                break
    for item in candidates:
        if len(selected) >= term_count:
            break
        add(item)

    scores = [float(item.get("display_score") or 0) for item in selected] or [1.0]
    low, high = min(scores), max(scores)
    output = []
    for rank, item in enumerate(selected[:term_count], start=1):
        score = float(item.get("display_score") or 0)
        normalized = 0.5 if high == low else (score - low) / (high - low)
        weight = round(42 + 58 * math.sqrt(max(0.0, normalized)))
        output.append(
            {
                **item,
                "weight": weight,
                "rank": rank,
                "selection_method": "evidence_weighted_topic_balanced_fallback",
            }
        )
    return output


def normalize_explicit_selection(
    selected: list[Any],
    candidates: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    topic_aliases: list[list[str]],
    anchor_terms: set[str] | None = None,
) -> list[dict[str, Any]]:
    candidate_by_term = {item["term"]: item for item in candidates}
    output = []
    comments_available = any(
        bool(row.get("is_comment"))
        or normalize_text(row.get("source_type") or row.get("evidence_type"))
        in {"netizen_comment", "platform_comment", "comment", "comments"}
        for row in documents
    )
    anchor_terms = anchor_terms or set()
    for rank, raw in enumerate(selected, start=1):
        if isinstance(raw, str):
            term = raw
            weight = max(42, 100 - (rank - 1) * 2)
        else:
            term = str(raw.get("term") or "").strip()
            weight = int(raw.get("weight") or max(42, 100 - (rank - 1) * 2))
        if not term or term in {item["term"] for item in output}:
            continue
        evidence = candidate_by_term.get(term) or evidence_for_term(term, documents, topic_aliases)
        document_count = int(evidence.get("document_count") or 0)
        if document_count < 1 or (document_count < 2 and term not in anchor_terms):
            continue
        ai_value = raw.get("ai_representativeness") if isinstance(raw, dict) else "高"
        score, components = score_hotword_evidence(
            evidence,
            comments_available=comments_available,
            topic_balance=10.0,
            ai_representativeness=ai_value,
        )
        output.append(
            {
                **evidence,
                "term": term,
                "weight": max(1, min(100, weight)),
                "rank": len(output) + 1,
                "selection_method": "ai_semantic_review",
                "display_score": score,
                "score_components": components,
            }
        )
    return output


def build_hotword_review_packet(
    candidates: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    topic_titles: list[str],
    topic_aliases: list[list[str]],
    *,
    minimum_term_count: int,
    target_term_count: int,
) -> dict[str, Any]:
    """Create the evidence packet that the active model must review."""
    document_samples = []
    for row in documents:
        combined = f"{row.get('title', '')}\n{row.get('content', '')}"
        hits = [
            index
            for index, aliases in enumerate(topic_aliases, start=1)
            if contains_any(combined, aliases)
        ]
        document_samples.append(
            {
                "source_row": row.get("source_row"),
                "source": row.get("account") or row.get("source"),
                "title": row.get("title"),
                "url": row.get("url"),
                "topic_hits": hits,
                "content_excerpt": str(row.get("content") or "")[:500],
            }
        )
    return {
        "schema_version": 1,
        "status": "ai_review_required",
        "required_review_method": "ai_semantic_review",
        "instructions": [
            "逐项审查候选词，删除虚词、通用动词、人名、日期、媒体名、会议套话和残缺切片。",
            "只保留单独展示时即可指向一个会议议题、政策目标、政策工具、治理机制、产业基础设施或公众关切的短语。",
            "召开、听取、研究、审议、通过、决定、修改、废止、核准等会议程序动作不得作为热词；投资、项目、工程、市场等无领域限定的载体词不得作为热词。",
            "单独的地名、项目所在地、领导姓名、机构名、媒体名和日期不得作为热词；地域词只有与政策目标、治理机制或产业议题组成完整概念时才可保留。",
            "为每个入选词填写semantic_type，并明确standalone_topic_label=true；如果读者脱离上下文不能判断它在讲什么议题，就必须删除或补成完整政策短语。",
            "合并同义词，并按topics中的实际议题数量检查每个议题是否都有实质性词项。",
            "候选不足时，从document_samples的标题和正文摘录中补提有原文证据的新词。",
            "core词至少命中2条独立文档；supporting词可命中1条，但必须是AI确认的实质性议题表达。",
            "不得为凑数量保留噪声；若审核后少于最低数量，继续从证据中补提，而不是回退到规则词。",
        ],
        "minimum_term_count": minimum_term_count,
        "target_term_count": target_term_count,
        "accepted_style_patterns": ACCEPTED_HOTWORD_STYLE_PATTERNS,
        "rejected_style_patterns": REJECTED_HOTWORD_STYLE_PATTERNS,
        "allowed_semantic_types": sorted(HOTWORD_SEMANTIC_TYPES),
        "topics": [
            {"index": index, "title": title, "aliases": aliases}
            for index, (title, aliases) in enumerate(zip(topic_titles, topic_aliases), start=1)
        ],
        "candidate_count": len(candidates),
        "candidates": candidates,
        "document_sample_count": len(document_samples),
        "document_samples": document_samples,
        "review_output_shape": {
            "review_method": "ai_semantic_review",
            "second_pass_completed": True,
            "selected": [
                {
                    "term": "示例词",
                    "topic_hits": [1],
                    "evidence_tier": "core",
                    "semantic_type": "policy_tool",
                    "standalone_topic_label": True,
                    "evidence_aliases": ["原文中的完整证据措辞"],
                    "selection_reason": "说明该词为何代表实质议题并通过语义审核",
                    "ai_representativeness": "高",
                }
            ],
        },
    }


def apply_hotword_ai_review(
    review: dict[str, Any],
    candidates: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    topic_titles: list[str],
    topic_aliases: list[list[str]],
    *,
    minimum_term_count: int,
    target_term_count: int,
) -> list[dict[str, Any]]:
    method = str(review.get("review_method") or "").strip().lower()
    if method not in {"ai_semantic_review", "ai_semantic_review_with_human_edits"}:
        raise ValueError("热词审核文件缺少有效review_method，禁止生成正式词云")
    if review.get("second_pass_completed") is not True:
        raise ValueError("热词审核尚未完成第二遍议题覆盖、同义词和噪声复核")

    raw_selected = review.get("selected")
    if not isinstance(raw_selected, list):
        raise ValueError("热词审核文件的selected必须是列表")
    if len(raw_selected) > target_term_count:
        raise ValueError(f"热词审核结果超过目标上限{target_term_count}个")

    candidate_by_term = {item["term"]: item for item in candidates}
    comments_available = any(int(item.get("comment_count") or 0) > 0 for item in candidates)
    # Normalize every long article once, then reuse it for all AI-selected
    # display terms and their verbatim evidence aliases. This both supports
    # human-style concise labels backed by longer verbatim evidence phrases
    # and avoids re-normalizing the 2,000-row corpus once per term.
    prepared_documents = []
    for row in documents:
        title = normalize_text(row.get("title"))
        content = normalize_text(row.get("content"))
        source_type = normalize_text(row.get("source_type") or row.get("evidence_type"))
        prepared_documents.append(
            {
                "row": row,
                "title": title,
                "combined": title + content,
                "source": str(row.get("account") or row.get("source") or "未知来源"),
                "is_comment": bool(row.get("is_comment"))
                or source_type in {"netizen_comment", "platform_comment", "comment", "comments"},
            }
        )

    reviewed_evidence: dict[int, dict[str, Any]] = {}
    for index, raw in enumerate(raw_selected, start=1):
        if not isinstance(raw, dict):
            continue
        term = normalize_text(raw.get("term"))
        aliases = [
            normalize_text(alias)
            for alias in (raw.get("evidence_aliases") or raw.get("aliases") or [])
            if normalize_text(alias)
        ]
        needles = list(dict.fromkeys([term, *aliases])) if term else aliases
        matching = []
        title_hits = 0
        exact_match_count = 0
        sources: set[str] = set()
        comment_count = 0
        for prepared in prepared_documents:
            matched_needles = [needle for needle in needles if needle and needle in prepared["combined"]]
            if not matched_needles:
                continue
            matching.append(prepared["row"])
            title_hits += int(any(needle in prepared["title"] for needle in needles))
            exact_match_count += int(bool(term and term in prepared["combined"]))
            sources.add(prepared["source"])
            comment_count += int(prepared["is_comment"])
        reviewed_evidence[index] = {
            "term": term,
            "topic_hits": topic_for_term(term, topic_aliases),
            "document_count": len(matching),
            "exact_match_count": exact_match_count,
            "title_hits": title_hits,
            "source_count": len(sources),
            "media_document_count": len(matching) - comment_count,
            "comment_count": comment_count,
            "evidence_aliases": aliases,
            "sample_titles": [str(row.get("title") or "") for row in matching[:3]],
            "sample_urls": [str(row.get("url") or "") for row in matching[:3]],
        }
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    topic_total = len(topic_titles)
    errors: list[str] = []
    for index, raw in enumerate(raw_selected, start=1):
        if not isinstance(raw, dict):
            errors.append(f"第{index}项不是带审核字段的对象")
            continue
        term = normalize_text(raw.get("term"))
        reason = str(raw.get("selection_reason") or "").strip()
        tier = str(raw.get("evidence_tier") or "").strip().lower()
        semantic_type = str(raw.get("semantic_type") or "").strip().lower()
        standalone_topic_label = raw.get("standalone_topic_label") is True
        topic_hits = raw.get("topic_hits") or []
        if not term or not valid_candidate(term):
            errors.append(f"第{index}项“{term or '<empty>'}”是泛化词、残缺词或非法词")
            continue
        if term in seen:
            errors.append(f"第{index}项“{term}”重复")
            continue
        if not reason:
            errors.append(f"第{index}项“{term}”缺少selection_reason")
            continue
        if tier not in {"core", "supporting"}:
            errors.append(f"第{index}项“{term}”的evidence_tier必须为core或supporting")
            continue
        if semantic_type not in HOTWORD_SEMANTIC_TYPES:
            errors.append(f"第{index}项“{term}”缺少有效semantic_type")
            continue
        if not standalone_topic_label:
            errors.append(f"第{index}项“{term}”未通过脱离上下文仍可指向议题的standalone测试")
            continue
        if any(term.startswith(marker) or term.endswith(marker) for marker in PROCEDURAL_HOTWORD_MARKERS):
            errors.append(f"第{index}项“{term}”仍是会议程序动作，不是事件议题词")
            continue
        if looks_like_pure_geography(term):
            errors.append(f"第{index}项“{term}”是纯地名或项目所在地，不是事件议题词")
            continue
        if (
            not isinstance(topic_hits, list)
            or not topic_hits
            or any(not isinstance(hit, int) or hit < 1 or hit > topic_total for hit in topic_hits)
        ):
            errors.append(f"第{index}项“{term}”的topic_hits无效")
            continue

        evidence = reviewed_evidence.get(index) or evidence_for_term(term, documents, topic_aliases)
        document_count = int(evidence.get("document_count") or 0)
        required_documents = 2 if tier == "core" else 1
        if document_count < required_documents:
            errors.append(
                f"第{index}项“{term}”证据不足：{tier}需要{required_documents}条，实际{document_count}条"
            )
            continue
        score, components = score_hotword_evidence(
            evidence,
            comments_available=comments_available,
            topic_balance=10.0,
            ai_representativeness=raw.get("ai_representativeness"),
        )
        reviewed_topic_hits = sorted(set(topic_hits))
        seen.add(term)
        output.append(
            {
                **evidence,
                "term": term,
                "topic_hits": reviewed_topic_hits,
                # Overwrite any candidate-stage topic_index. A term may have
                # appeared near several agenda aliases; the reviewed mapping
                # is authoritative for the report handoff.
                "topic_index": reviewed_topic_hits[0],
                "evidence_tier": tier,
                "semantic_type": semantic_type,
                "standalone_topic_label": True,
                "selection_reason": reason,
                "ai_reviewed": True,
                "ai_representativeness": raw.get("ai_representativeness", "高"),
                "supplemented_by_ai": term not in candidate_by_term,
                "selection_method": "ai_semantic_review",
                "display_score": score,
                "score_components": components,
            }
        )

    if errors:
        raise ValueError("热词AI审核未通过：" + "；".join(errors[:12]))
    effective_minimum = 1 if review.get("delivery_policy") == "deliver_available_with_gaps" else minimum_term_count
    if len(output) < effective_minimum:
        raise ValueError(
            f"热词AI审核后仅{len(output)}个，少于最低{minimum_term_count}个；"
            "请让AI从审核包document_samples继续补提有证据的词"
        )

    scores = [float(item.get("display_score") or 0) for item in output] or [1.0]
    low, high = min(scores), max(scores)
    output.sort(
        key=lambda item: (
            -float(item.get("display_score") or 0),
            -int(item.get("document_count") or 0),
            item["term"],
        )
    )
    for rank, item in enumerate(output, start=1):
        score = float(item.get("display_score") or 0)
        normalized = 0.5 if high == low else (score - low) / (high - low)
        item["rank"] = rank
        item["weight"] = round(42 + 58 * math.sqrt(max(0.0, normalized)))
    return output


def build_hotword_payload(
    rows: list[dict[str, Any]],
    metadata: dict[str, Any],
    meeting_anchors: list[str],
    review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    topic_titles = list(metadata.get("topic_titles") or [])
    topic_aliases = list(metadata.get("topic_aliases") or [])
    settings = dict(metadata.get("wordcloud") or {})
    documents = relevant_documents(rows, topic_aliases, meeting_anchors)
    candidates = generate_candidates(documents, topic_titles, topic_aliases)
    term_count = int(settings.get("term_count") or DEFAULT_TERM_COUNT)
    minimum_term_count = int(settings.get("minimum_term_count") or min(36, term_count))
    deliver_available = bool(review and review.get("delivery_policy") == "deliver_available_with_gaps")
    review_packet = build_hotword_review_packet(
        candidates,
        documents,
        topic_titles,
        topic_aliases,
        minimum_term_count=minimum_term_count,
        target_term_count=term_count,
    )
    selected = []
    status = "ai_review_required"
    method = "ai_review_required"
    if review is not None:
        selected = apply_hotword_ai_review(
            review,
            candidates,
            documents,
            topic_titles,
            topic_aliases,
            minimum_term_count=minimum_term_count,
            target_term_count=term_count,
        )
        status = "ai_review_complete"
        method = "ai_semantic_review_with_evidence"
    return {
        "schema_version": 1,
        "status": status,
        "method": method,
        "review_method": review.get("review_method") if review else None,
        "second_pass_completed": bool(review and review.get("second_pass_completed") is True),
        "settings": {
            "term_count": term_count,
            "minimum_term_count": 1 if deliver_available else minimum_term_count,
            "configured_minimum_term_count": minimum_term_count,
            "shape": settings.get("shape") or "cloud",
            "background": "transparent",
            "color": settings.get("color") or DEFAULT_COLOR,
            "rotation": int(settings.get("rotation", DEFAULT_ROTATION)),
            "width": int(settings.get("width") or DEFAULT_WIDTH),
            "height": int(settings.get("height") or DEFAULT_HEIGHT),
            "font_path": settings.get("font_path") or "",
            "mask_path": settings.get("mask_path") or "",
            "primary_font_min": int(settings.get("primary_font_min") or DEFAULT_PRIMARY_FONT_MIN),
            "primary_font_max": int(settings.get("primary_font_max") or DEFAULT_PRIMARY_FONT_MAX),
            "font_scale_exponent": float(settings.get("font_scale_exponent") or DEFAULT_FONT_SCALE_EXPONENT),
            "max_placed_instances": int(
                settings.get("max_placed_instances") or DEFAULT_MAX_PLACED_INSTANCES
            ),
            "no_margin": True,
            "format": "png",
        },
        "corpus_audit": {
            "raw_document_count": len(rows),
            "deduplicated_relevant_document_count": len(documents),
            "candidate_count": len(candidates),
        },
        "delivery_policy": "deliver_available_with_gaps" if deliver_available else None,
        "count_shortfall": {
            "configured_minimum": minimum_term_count,
            "actual_count": len(selected),
            "notice": f"热词经审核仅保留{len(selected)}个，低于数量目标{minimum_term_count}个；不补造词条。"
        } if deliver_available and status == "ai_review_complete" and len(selected) < minimum_term_count else None,
        "selected": selected[:term_count],
        "candidates": candidates,
        "review_packet": review_packet,
    }


def resolve_font(requested: str | Path | None) -> Path:
    if requested:
        path = Path(requested)
        if path.exists():
            return path
        raise FileNotFoundError(f"指定词云字体不存在：{path}")
    candidates = [
        Path(os.environ["CWH_CJK_FONT"]) if os.environ.get("CWH_CJK_FONT") else None,
        BUNDLED_CJK_FONT,
        BUNDLED_CJK_FALLBACK_FONT,
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
        Path("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf"),
        # Keep report generation available in minimal Linux preview images. The
        # production Docker image installs Noto CJK, so this is only a fallback.
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for path in candidates:
        if path and path.exists():
            return path
    raise FileNotFoundError("未找到可用中文字体，请在wordcloud.font_path中指定字体文件")


def cloud_mask(width: int, height: int, mask_path: str | Path | None = None) -> np.ndarray:
    if mask_path:
        path = Path(mask_path)
        if not path.exists():
            raise FileNotFoundError(f"指定云朵遮罩不存在：{path}")
        source = Image.open(path).convert("RGBA")
    else:
        source = Image.open(DEFAULT_CLOUD_MASK_ASSET).convert("RGBA")

    alpha = source.getchannel("A")
    if alpha.getextrema()[0] < 255:
        allowed_source = alpha
    else:
        grayscale = source.convert("L")
        pixels = np.asarray(grayscale)
        dark = pixels < 180
        light = pixels > 220
        allowed_source = Image.fromarray(np.where(dark if dark.sum() < light.sum() else light, 255, 0).astype(np.uint8))

    source_bbox = allowed_source.getbbox()
    if not source_bbox:
        raise ValueError("云朵遮罩没有可用的非透明/前景区域")
    cropped = allowed_source.crop(source_bbox)
    scale = min(width / cropped.width, height / cropped.height)
    resized_width = max(1, round(cropped.width * scale))
    resized_height = max(1, round(cropped.height * scale))
    resized = cropped.resize((resized_width, resized_height), Image.Resampling.LANCZOS)
    mask_image = Image.new("L", (width, height), 0)
    offset = ((width - resized_width) // 2, (height - resized_height) // 2)
    mask_image.paste(resized, offset)
    return np.asarray(mask_image) > 16


def text_sprite(
    term: str,
    font_path: Path,
    font_size: int,
    color: str,
    rotation: int,
    word_spacing: int = DEFAULT_WORD_SPACING,
) -> tuple[Image.Image, np.ndarray]:
    font = ImageFont.truetype(str(font_path), font_size)
    bbox = font.getbbox(term, stroke_width=0)
    width = max(1, bbox[2] - bbox[0] + 8)
    height = max(1, bbox[3] - bbox[1] + 8)
    base_alpha = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(base_alpha)
    draw.text((4 - bbox[0], 4 - bbox[1]), term, font=font, fill=255)
    alpha = base_alpha.rotate(rotation, resample=Image.Resampling.BICUBIC, expand=True)
    crop_box = alpha.getbbox()
    if crop_box:
        alpha = alpha.crop(crop_box)
    red, green, blue = ImageColor.getrgb(color)
    rotated = Image.new("RGBA", alpha.size, (red, green, blue, 255))
    rotated.putalpha(alpha)
    filter_size = max(1, int(word_spacing))
    if filter_size % 2 == 0:
        filter_size += 1
    collision = alpha.filter(ImageFilter.MaxFilter(filter_size)) if filter_size > 1 else alpha
    return rotated, np.asarray(collision) > 18


def primary_font_size(
    ratio: float,
    minimum: int = DEFAULT_PRIMARY_FONT_MIN,
    maximum: int = DEFAULT_PRIMARY_FONT_MAX,
    exponent: float = DEFAULT_FONT_SCALE_EXPONENT,
) -> int:
    normalized = max(0.0, min(1.0, float(ratio)))
    return round(minimum + (maximum - minimum) * (normalized**exponent))


def _render_wordcloud_png_legacy(payload: dict[str, Any], output_path: Path, seed: int = 20260710) -> dict[str, Any]:
    settings = payload["settings"]
    width = int(settings.get("width") or DEFAULT_WIDTH)
    height = int(settings.get("height") or DEFAULT_HEIGHT)
    color = str(settings.get("color") or DEFAULT_COLOR)
    rotation = int(settings.get("rotation", DEFAULT_ROTATION))
    primary_minimum = int(settings.get("primary_font_min") or DEFAULT_PRIMARY_FONT_MIN)
    primary_maximum = int(settings.get("primary_font_max") or DEFAULT_PRIMARY_FONT_MAX)
    scale_exponent = float(settings.get("font_scale_exponent") or DEFAULT_FONT_SCALE_EXPONENT)
    render_scale = max(1, int(settings.get("render_scale") or DEFAULT_RENDER_SCALE))
    word_spacing = max(1, int(settings.get("word_spacing") or DEFAULT_WORD_SPACING))
    font_path = resolve_font(settings.get("font_path"))
    allowed = cloud_mask(width, height, settings.get("mask_path"))
    occupied = np.zeros((height, width), dtype=bool)
    rng = random.Random(seed)
    selected = sorted(payload.get("selected") or [], key=lambda item: -int(item.get("weight") or 1))
    if not selected:
        raise ValueError("词云没有可渲染的selected词条")
    max_placed_instances = max(
        len(selected),
        int(settings.get("max_placed_instances") or DEFAULT_MAX_PLACED_INSTANCES),
    )

    weights = [int(item.get("weight") or 1) for item in selected]
    low, high = min(weights), max(weights)
    primary_queue: list[tuple[dict[str, Any], int, int]] = []
    for item in selected:
        weight = int(item.get("weight") or 1)
        ratio = 0.5 if high == low else (weight - low) / (high - low)
        font_size = primary_font_size(ratio, primary_minimum, primary_maximum, scale_exponent)
        primary_queue.append((item, font_size, 0))
    # Keep the top-ranked term at the visual center, then reserve space for
    # long/large primary terms before short low-area terms fill the mask.
    # This avoids silently losing a long policy phrase late in the pass.
    if len(primary_queue) > 1:
        primary_queue = [
            primary_queue[0],
            *sorted(
                primary_queue[1:],
                key=lambda entry: (
                    -len(str(entry[0].get("term") or "")),
                    -(len(str(entry[0].get("term") or "")) * entry[1] * entry[1]),
                ),
            ),
        ]
    queue: list[tuple[dict[str, Any], int, int]] = list(primary_queue)
    for repeat_round, scale in enumerate(DEFAULT_REPEAT_SCALES, start=1):
        for item in selected:
            base_weight = int(item.get("weight") or 1)
            ratio = 0.5 if high == low else (base_weight - low) / (high - low)
            # Repeat copies are background texture. Keep their historical size
            # mapping independent from the enlarged primary hierarchy so a
            # headword's duplicate never becomes a second visual anchor.
            base_size = primary_font_size(
                ratio,
                DEFAULT_REPEAT_REFERENCE_MIN,
                DEFAULT_REPEAT_REFERENCE_MAX,
                DEFAULT_REPEAT_REFERENCE_EXPONENT,
            )
            font_size = max(10, round(base_size * scale))
            queue.append((item, font_size, repeat_round))

    placed: list[dict[str, Any]] = []
    def spiral_candidates(
        sprite_width: int,
        sprite_height: int,
        rank_index: int,
        repeat_round: int,
        attempt_count: int,
    ) -> Iterable[tuple[int, int]]:
        if repeat_round == 0 and rank_index < len(DEFAULT_PRIMARY_ANCHORS):
            anchor_x, anchor_y = DEFAULT_PRIMARY_ANCHORS[rank_index]
            anchor_left = round(width * anchor_x - sprite_width / 2)
            anchor_top = round(height * anchor_y - sprite_height / 2)
            yield (
                anchor_left,
                anchor_top,
            )
            # If the exact anchor is occupied, search its immediate
            # neighbourhood before falling back to the global spiral. This
            # keeps the headword hierarchy in the same compositional zones as
            # the reference while still supporting words of different lengths.
            local_phase = rng.random() * math.tau
            for local_attempt in range(96):
                angle = local_phase + local_attempt * 0.42
                radius = 2.0 + local_attempt * 0.72
                yield (
                    round(anchor_left + math.cos(angle) * radius * 1.12),
                    round(anchor_top + math.sin(angle) * radius * 0.88),
                )

        if repeat_round == 0 and rank_index >= len(DEFAULT_PRIMARY_ANCHORS):
            small_primary_index = rank_index - len(DEFAULT_PRIMARY_ANCHORS)
            if small_primary_index < len(DEFAULT_INTERIOR_FILL_ANCHORS):
                fill_x, fill_y = DEFAULT_INTERIOR_FILL_ANCHORS[small_primary_index]
            else:
                perimeter_index = small_primary_index - len(DEFAULT_INTERIOR_FILL_ANCHORS)
                fill_x, fill_y = DEFAULT_PERIMETER_FILL_ANCHORS[
                    perimeter_index % len(DEFAULT_PERIMETER_FILL_ANCHORS)
                ]
            fill_left = round(width * fill_x - sprite_width / 2)
            fill_top = round(height * fill_y - sprite_height / 2)
            yield fill_left, fill_top
            local_phase = rng.random() * math.tau
            for local_attempt in range(180):
                angle = local_phase + local_attempt * 0.46
                radius = 2.0 + local_attempt * 0.62
                yield (
                    round(fill_left + math.cos(angle) * radius * 1.14),
                    round(fill_top + math.sin(angle) * radius * 0.86),
                )

        if repeat_round > 0:
            repeat_index = rank_index - len(selected)
            if repeat_round == 1 and repeat_index < len(DEFAULT_INTERIOR_FILL_ANCHORS):
                fill_x, fill_y = DEFAULT_INTERIOR_FILL_ANCHORS[repeat_index]
            elif repeat_round == 1:
                perimeter_index = repeat_index - len(DEFAULT_INTERIOR_FILL_ANCHORS)
                fill_x, fill_y = DEFAULT_PERIMETER_FILL_ANCHORS[
                    perimeter_index % len(DEFAULT_PERIMETER_FILL_ANCHORS)
                ]
            else:
                fill_x, fill_y = DEFAULT_INTERIOR_FILL_ANCHORS[
                    repeat_index % len(DEFAULT_INTERIOR_FILL_ANCHORS)
                ]
            fill_left = round(width * fill_x - sprite_width / 2)
            fill_top = round(height * fill_y - sprite_height / 2)
            yield fill_left, fill_top
            local_phase = rng.random() * math.tau
            for local_attempt in range(180):
                angle = local_phase + local_attempt * 0.46
                radius = 2.0 + local_attempt * 0.62
                yield (
                    round(fill_left + math.cos(angle) * radius * 1.14),
                    round(fill_top + math.sin(angle) * radius * 0.86),
                )

        # Start each search near the visual centre and walk an elliptical
        # Archimedean spiral. This mirrors the compact centre-out packing of
        # the approved website reference and avoids the scattered random look.
        phase = rng.random() * math.tau
        if repeat_round == 0:
            origin_x = width * (0.50 + rng.uniform(-0.08, 0.08))
            origin_y = height * (0.55 + rng.uniform(-0.06, 0.06))
        else:
            origin_x = width * (0.50 + rng.uniform(-0.18, 0.18))
            origin_y = height * (0.53 + rng.uniform(-0.14, 0.14))
        radial_step = 0.50 if repeat_round == 0 else 0.38
        for attempt in range(attempt_count):
            angle = phase + attempt * 0.34
            radius = 2.0 + radial_step * attempt
            center_x = origin_x + math.cos(angle) * radius * 1.22
            center_y = origin_y + math.sin(angle) * radius * 0.78
            yield (
                round(center_x - sprite_width / 2),
                round(center_y - sprite_height / 2),
            )

    for rank_index, (item, initial_size, repeat_round) in enumerate(queue):
        if len(placed) >= max_placed_instances:
            break
        term = str(item["term"])
        font_size = initial_size
        successful = False
        for shrink in range(8 if repeat_round == 0 else 4):
            sprite, collision = text_sprite(
                term,
                font_path,
                font_size,
                color,
                rotation,
                word_spacing,
            )
            sprite_width, sprite_height = sprite.size
            if sprite_width >= width or sprite_height >= height:
                font_size = max(10 if repeat_round else 16, round(font_size * 0.85))
                continue
            attempt_count = 3600 if repeat_round == 0 else 2600
            for attempt, (candidate_x, candidate_y) in enumerate(
                spiral_candidates(sprite_width, sprite_height, rank_index, repeat_round, attempt_count)
            ):
                x = max(0, min(width - sprite_width, candidate_x))
                y = max(0, min(height - sprite_height, candidate_y))
                region_allowed = allowed[y : y + sprite_height, x : x + sprite_width]
                region_occupied = occupied[y : y + sprite_height, x : x + sprite_width]
                if collision.shape != region_allowed.shape:
                    continue
                if np.any(collision & ~region_allowed) or np.any(collision & region_occupied):
                    continue
                occupied[y : y + sprite_height, x : x + sprite_width] |= collision
                placed.append(
                    {
                        "term": term,
                        "font_size": font_size,
                        "repeat_round": repeat_round,
                        "x": x,
                        "y": y,
                        "width": sprite_width,
                        "height": sprite_height,
                    }
                )
                successful = True
                break
            if successful:
                break
            font_size = max(10 if repeat_round else 16, round(font_size * 0.84))

    # Render the accepted layout again at a higher pixel density. Placement is
    # still computed on the 1600x1000 design grid, so the extra resolution only
    # improves glyph edges; it does not alter the learned composition.
    canvas = Image.new("RGBA", (width * render_scale, height * render_scale), (0, 0, 0, 0))
    for placement in placed:
        sprite, _ = text_sprite(
            placement["term"],
            font_path,
            placement["font_size"] * render_scale,
            color,
            rotation,
            1,
        )
        canvas.alpha_composite(
            sprite,
            (placement["x"] * render_scale, placement["y"] * render_scale),
        )

    alpha_bbox = canvas.getchannel("A").getbbox()
    if not alpha_bbox:
        raise RuntimeError("词云渲染后为空")
    cropped = canvas.crop(alpha_bbox)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(output_path, format="PNG", optimize=True)
    payload["image_path"] = str(output_path.resolve())
    payload["render_audit"] = {
        "font_path": str(font_path.resolve()),
        "font_scale": {
            "primary_min": primary_minimum,
            "primary_max": primary_maximum,
            "exponent": scale_exponent,
            "repeat_reference_min": DEFAULT_REPEAT_REFERENCE_MIN,
            "repeat_reference_max": DEFAULT_REPEAT_REFERENCE_MAX,
            "repeat_reference_exponent": DEFAULT_REPEAT_REFERENCE_EXPONENT,
            "repeat_scales": list(DEFAULT_REPEAT_SCALES),
        },
        "layout_canvas_size": [width, height],
        "canvas_size": [width * render_scale, height * render_scale],
        "render_scale": render_scale,
        "word_spacing": word_spacing,
        "placement_distribution": "rank_anchors_then_interior_and_perimeter_zones",
        "output_size": list(cropped.size),
        "alpha_bbox_before_crop": list(alpha_bbox),
        "placed_instance_count": len(placed),
        "max_placed_instances": max_placed_instances,
        "placed_unique_term_count": len({item["term"] for item in placed}),
        "allowed_mask_pixel_count": int(allowed.sum()),
        "collision_coverage_ratio": round(float(occupied.sum() / max(1, allowed.sum())), 4),
        "all_primary_terms_placed": all(any(p["term"] == item["term"] and p["repeat_round"] == 0 for p in placed) for item in selected),
        "placed": placed,
    }
    return payload


def _render_wordcloud_png_multifocus_legacy(
    payload: dict[str, Any], output_path: Path, seed: int = 20260710
) -> dict[str, Any]:
    """Render the approved 70-instance cloud with whole-layout rotation.

    The cloud mask is deskewed first, words are packed horizontally by alpha
    pixels around seven reusable lobe foci, and the finished layout is rotated
    once. This matches the website's even gaps without copying a saved image or
    preserving any meeting-specific placement.
    """

    settings = payload["settings"]
    design_width = int(settings.get("width") or DEFAULT_WIDTH)
    design_height = int(settings.get("height") or DEFAULT_HEIGHT)
    color = str(settings.get("color") or DEFAULT_COLOR)
    rotation = int(settings.get("rotation", DEFAULT_ROTATION))
    primary_minimum = int(settings.get("primary_font_min") or DEFAULT_PRIMARY_FONT_MIN)
    primary_maximum = int(settings.get("primary_font_max") or DEFAULT_PRIMARY_FONT_MAX)
    scale_exponent = float(settings.get("font_scale_exponent") or DEFAULT_FONT_SCALE_EXPONENT)
    render_scale = max(1, int(settings.get("render_scale") or DEFAULT_RENDER_SCALE))
    word_spacing = max(0, int(settings.get("word_spacing") or DEFAULT_WORD_SPACING))
    max_placed_instances = max(
        len(payload.get("selected") or []),
        int(settings.get("max_placed_instances") or DEFAULT_MAX_PLACED_INSTANCES),
    )
    font_path = resolve_font(settings.get("font_path"))

    upright_allowed = cloud_mask(design_width, design_height, settings.get("mask_path"))
    layout_mask_image = Image.fromarray(np.where(upright_allowed, 255, 0).astype(np.uint8)).rotate(
        -rotation,
        resample=Image.Resampling.BICUBIC,
        expand=True,
    )
    allowed = np.asarray(layout_mask_image) > 24
    layout_height, layout_width = allowed.shape
    occupied = np.zeros_like(allowed)
    mask_points = np.argwhere(allowed)
    if not mask_points.size:
        raise ValueError("云朵遮罩没有可用区域")
    min_y, min_x = mask_points.min(axis=0)
    max_y, max_x = mask_points.max(axis=0)
    mask_span_x = max(1, int(max_x) - int(min_x))
    mask_span_y = max(1, int(max_y) - int(min_y))
    origin_x = (int(min_x) + int(max_x)) / 2
    origin_y = (int(min_y) + int(max_y)) / 2

    selected = sorted(payload.get("selected") or [], key=lambda item: -int(item.get("weight") or 1))
    if not selected:
        raise ValueError("词云没有可渲染的selected词条")
    weights = [int(item.get("weight") or 1) for item in selected]
    low, high = min(weights), max(weights)
    queue: list[tuple[dict[str, Any], int, int]] = []
    for item in selected:
        weight = int(item.get("weight") or 1)
        ratio = 0.5 if high == low else (weight - low) / (high - low)
        queue.append(
            (
                item,
                primary_font_size(ratio, primary_minimum, primary_maximum, scale_exponent),
                0,
            )
        )

    repeat_round = 1
    while len(queue) < max_placed_instances:
        scale = DEFAULT_REPEAT_SCALES[min(repeat_round - 1, len(DEFAULT_REPEAT_SCALES) - 1)]
        for item in selected:
            if len(queue) >= max_placed_instances:
                break
            weight = int(item.get("weight") or 1)
            ratio = 0.5 if high == low else (weight - low) / (high - low)
            reference_size = primary_font_size(
                ratio,
                DEFAULT_REPEAT_REFERENCE_MIN,
                DEFAULT_REPEAT_REFERENCE_MAX,
                DEFAULT_REPEAT_REFERENCE_EXPONENT,
            )
            queue.append((item, max(10, round(reference_size * scale)), repeat_round))
        repeat_round += 1

    rng = random.Random(seed)
    phase_cycle = (
        0.0,
        math.radians(135),
        math.radians(225),
        math.radians(315),
        math.radians(270),
        math.radians(45),
        math.radians(20),
        math.radians(165),
    )
    placed: list[dict[str, Any]] = []
    collision_filter_size = word_spacing * 2 + 1

    for rank_index, (item, initial_size, item_repeat_round) in enumerate(queue):
        if len(placed) >= max_placed_instances:
            break
        term = str(item["term"])
        font_size = initial_size
        successful = False
        for _shrink in range(9 if item_repeat_round == 0 else 5):
            sprite, collision = text_sprite(
                term,
                font_path,
                font_size,
                color,
                0,
                collision_filter_size,
            )
            sprite_width, sprite_height = sprite.size
            ink = np.asarray(sprite.getchannel("A")) > 18
            anchor_x, anchor_y = DEFAULT_FOCUS_ANCHORS[rank_index % len(DEFAULT_FOCUS_ANCHORS)]
            search_origin_x = int(min_x) + anchor_x * mask_span_x
            search_origin_y = int(min_y) + anchor_y * mask_span_y
            phase = phase_cycle[rank_index % len(phase_cycle)] + rng.uniform(-0.08, 0.08)
            direction = 1 if rank_index % 2 == 0 else -1

            for attempt in range(5200):
                if attempt == 0:
                    center_x, center_y = search_origin_x, search_origin_y
                else:
                    theta = attempt * 0.22
                    radius = 0.34 * attempt
                    center_x = search_origin_x + math.cos(phase + direction * theta) * radius * 1.35
                    center_y = search_origin_y + math.sin(phase + direction * theta) * radius * 0.80
                x = round(center_x - sprite_width / 2)
                y = round(center_y - sprite_height / 2)
                if x < 0 or y < 0 or x + sprite_width > layout_width or y + sprite_height > layout_height:
                    continue
                region_allowed = allowed[y : y + sprite_height, x : x + sprite_width]
                region_occupied = occupied[y : y + sprite_height, x : x + sprite_width]
                if ink.shape != region_allowed.shape or collision.shape != region_occupied.shape:
                    continue
                if np.any(ink & ~region_allowed) or np.any(collision & region_occupied):
                    continue
                occupied[y : y + sprite_height, x : x + sprite_width] |= collision
                placed.append(
                    {
                        "term": term,
                        "font_size": font_size,
                        "repeat_round": item_repeat_round,
                        "packed_x": x,
                        "x": x,
                        "y": y,
                        "width": sprite_width,
                        "height": sprite_height,
                    }
                )
                successful = True
                break
            if successful:
                break
            font_size = max(10 if item_repeat_round else 15, round(font_size * 0.86))

    for placement in placed:
        center_x = placement["x"] + placement["width"] / 2
        center_y = placement["y"] + placement["height"] / 2
        spread_center_x = origin_x + (center_x - origin_x) * DEFAULT_LAYOUT_X_SPREAD
        spread_center_y = origin_y + (center_y - origin_y) * DEFAULT_LAYOUT_Y_SPREAD
        placement["x"] = round(spread_center_x - placement["width"] / 2)
        placement["y"] = round(spread_center_y - placement["height"] / 2)

    render_pad_x = round(design_width * 0.10)
    render_pad_y = round(design_height * 0.05)
    horizontal = Image.new(
        "RGBA",
        ((layout_width + render_pad_x * 2) * render_scale, (layout_height + render_pad_y * 2) * render_scale),
        (0, 0, 0, 0),
    )
    for placement in placed:
        sprite, _ = text_sprite(
            placement["term"],
            font_path,
            placement["font_size"] * render_scale,
            color,
            0,
            1,
        )
        horizontal.alpha_composite(
            sprite,
            (
                (placement["x"] + render_pad_x) * render_scale,
                (placement["y"] + render_pad_y) * render_scale,
            ),
        )

    rotated = horizontal.rotate(rotation, resample=Image.Resampling.BICUBIC, expand=True)
    alpha_bbox = rotated.getchannel("A").getbbox()
    if not alpha_bbox:
        raise RuntimeError("词云渲染后为空")
    cropped = rotated.crop(alpha_bbox)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(output_path, format="PNG", optimize=True)

    payload["image_path"] = str(output_path.resolve())
    payload["render_audit"] = {
        "method": "rotated_mask_multifocus_alpha_spiral",
        "font_path": str(font_path.resolve()),
        "font_scale": {
            "primary_min": primary_minimum,
            "primary_max": primary_maximum,
            "exponent": scale_exponent,
            "repeat_reference_min": DEFAULT_REPEAT_REFERENCE_MIN,
            "repeat_reference_max": DEFAULT_REPEAT_REFERENCE_MAX,
            "repeat_reference_exponent": DEFAULT_REPEAT_REFERENCE_EXPONENT,
            "repeat_scales": list(DEFAULT_REPEAT_SCALES),
        },
        "layout_canvas_size": [layout_width, layout_height],
        "render_scale": render_scale,
        "word_spacing": word_spacing,
        "focus_anchors": [list(anchor) for anchor in DEFAULT_FOCUS_ANCHORS],
        "layout_x_spread": DEFAULT_LAYOUT_X_SPREAD,
        "layout_y_spread": DEFAULT_LAYOUT_Y_SPREAD,
        "placement_distribution": "multifocus_archimedean_spiral_with_alpha_collision",
        "rotation_strategy": "horizontal_layout_then_rotate_whole_canvas",
        "output_size": list(cropped.size),
        "alpha_bbox_before_crop": list(alpha_bbox),
        "placed_instance_count": len(placed),
        "max_placed_instances": max_placed_instances,
        "placed_unique_term_count": len({item["term"] for item in placed}),
        "allowed_mask_pixel_count": int(allowed.sum()),
        "collision_coverage_ratio": round(float(occupied.sum() / max(1, allowed.sum())), 4),
        "all_primary_terms_placed": all(
            any(p["term"] == item["term"] and p["repeat_round"] == 0 for p in placed)
            for item in selected
        ),
        "placed": placed,
    }
    return payload


def _microcloud_rank_ratio(rank: int) -> float:
    """Interpolate the reusable 65-word size hierarchy."""

    for index in range(1, len(DEFAULT_MICROCLOUD_RANK_CURVE)):
        left_rank, left_ratio = DEFAULT_MICROCLOUD_RANK_CURVE[index - 1]
        right_rank, right_ratio = DEFAULT_MICROCLOUD_RANK_CURVE[index]
        if rank <= right_rank:
            progress = (rank - left_rank) / max(1, right_rank - left_rank)
            return left_ratio + progress * (right_ratio - left_ratio)
    return DEFAULT_MICROCLOUD_RANK_CURVE[-1][1]


def _microcloud_best_free_rectangle(
    allowed: np.ndarray,
    occupied: np.ndarray,
    target_ratio: float,
    edge_distance: np.ndarray | None = None,
    boundary_weight: float = 0.0,
) -> dict[str, float]:
    """Find the maximal free rectangle using the website's 2.7 scorer.

    Candidate score is rectangle area multiplied by aspect-ratio similarity.
    The right-to-left scan also preserves the browser algorithm's tie-breaking.
    """

    free = allowed & ~occupied
    height, width = free.shape
    runs = [0] * (height + 1)
    best = {
        "x": 0.0,
        "y": 0.0,
        "width": 0.0,
        "height": 1.0,
        "score": 0.0,
        "base_score": 0.0,
        "edge_distance": 0.0,
    }

    for x in range(width - 1, -1, -1):
        column = free[:, x]
        for y in range(height):
            runs[y] = runs[y] + 1 if column[y] else 0

        stack: deque[tuple[int, int]] = deque()
        current = 0
        for y in range(height + 1):
            value = runs[y] if y < height else 0
            if value > current:
                stack.appendleft((y, current))
                current = value
            if value < current:
                last_start = y
                last_previous = 0
                while stack and value < current:
                    start_y, previous = stack.popleft()
                    last_start, last_previous = start_y, previous
                    rectangle_width = current
                    rectangle_height = y - start_y
                    if rectangle_width > 1 and rectangle_height > 1:
                        ratio_q = rectangle_width / rectangle_height / max(target_ratio, 1e-9)
                        similarity = 1.0 / ratio_q if ratio_q > 1.0 else ratio_q
                        base_score = rectangle_width * rectangle_height * similarity
                        center_edge_distance = 0.0
                        score = base_score
                        if edge_distance is not None and boundary_weight > 0:
                            center_x = min(width - 1, x + rectangle_width // 2)
                            center_y = min(height - 1, start_y + rectangle_height // 2)
                            center_edge_distance = float(edge_distance[center_y, center_x])
                            score *= 1.0 + boundary_weight / (1.0 + center_edge_distance)
                        if score > best["score"]:
                            best = {
                                "x": float(x),
                                "y": float(start_y),
                                "width": float(rectangle_width),
                                "height": float(rectangle_height),
                                "score": float(score),
                                "base_score": float(base_score),
                                "edge_distance": center_edge_distance,
                            }
                    current = previous
                current = value
                if current:
                    stack.appendleft((last_start, last_previous))
    return best


def _microcloud_edge_distance(allowed: np.ndarray) -> np.ndarray:
    """Return a four-neighbour distance map from each mask pixel to the edge."""

    height, width = allowed.shape
    distance = np.full((height, width), height + width, dtype=np.int32)
    pending: deque[tuple[int, int]] = deque()
    for y, x in np.argwhere(~allowed):
        distance[y, x] = 0
        pending.append((int(y), int(x)))
    while pending:
        y, x = pending.popleft()
        next_distance = int(distance[y, x]) + 1
        for next_y, next_x in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if (
                0 <= next_y < height
                and 0 <= next_x < width
                and next_distance < distance[next_y, next_x]
            ):
                distance[next_y, next_x] = next_distance
                pending.append((next_y, next_x))
    return distance


def _microcloud_text_alpha(text: str, font_path: Path, font_size: int) -> Image.Image:
    """Render a tightly cropped grayscale word sprite."""

    font = ImageFont.truetype(str(font_path), max(2, font_size))
    bbox = font.getbbox(text)
    padding = max(2, round(font_size * 0.03))
    sprite = Image.new(
        "L",
        (
            max(1, bbox[2] - bbox[0] + 2 * padding),
            max(1, bbox[3] - bbox[1] + 2 * padding),
        ),
        0,
    )
    ImageDraw.Draw(sprite).text(
        (padding - bbox[0], padding - bbox[1]),
        text,
        font=font,
        fill=255,
    )
    crop = sprite.getbbox()
    return sprite.crop(crop) if crop else sprite


def _render_wordcloud_png_max_free_rectangle_legacy(
    payload: dict[str, Any], output_path: Path, seed: int = 1
) -> dict[str, Any]:
    """Render a fresh 65-instance cloud with the Microcloud-style box packer.

    The reference contributes only the generic packing method and rank-size
    hierarchy. No reference word position or saved layout is reused.
    """

    settings = payload["settings"]
    color = str(settings.get("color") or DEFAULT_COLOR)
    rotation = int(settings.get("rotation", DEFAULT_ROTATION))
    grid_size = max(120, int(settings.get("layout_grid") or DEFAULT_MICROCLOUD_GRID))
    density = max(0.0, min(0.8, float(settings.get("density") or DEFAULT_MICROCLOUD_DENSITY)))
    headline_scale = max(
        0.5,
        float(settings.get("headline_scale") or DEFAULT_MICROCLOUD_HEADLINE_SCALE),
    )
    boundary_fill_start_rank = max(
        1,
        int(
            settings.get("boundary_fill_start_rank")
            or DEFAULT_MICROCLOUD_BOUNDARY_FILL_START_RANK
        ),
    )
    boundary_weight = max(
        0.0,
        float(settings.get("boundary_weight") or DEFAULT_MICROCLOUD_BOUNDARY_WEIGHT),
    )
    max_placed_instances = max(
        len(payload.get("selected") or []),
        int(settings.get("max_placed_instances") or DEFAULT_MAX_PLACED_INSTANCES),
    )
    font_path = resolve_font(settings.get("font_path"))

    selected = sorted(
        payload.get("selected") or [],
        key=lambda item: -int(item.get("weight") or 1),
    )
    if not selected:
        raise ValueError("No selected hotwords are available for rendering")

    upright_allowed = cloud_mask(grid_size, grid_size, settings.get("mask_path"))
    upright_image = Image.fromarray(np.where(upright_allowed, 255, 0).astype(np.uint8))
    layout_mask_image = upright_image.rotate(
        -rotation,
        resample=Image.Resampling.BICUBIC,
        expand=True,
    )
    allowed = np.asarray(layout_mask_image) > 127
    occupied = np.zeros_like(allowed, dtype=bool)
    plan_height, plan_width = allowed.shape
    shape_area = int(allowed.sum())
    if not shape_area:
        raise ValueError("The cloud mask has no usable foreground area")
    edge_distance = _microcloud_edge_distance(allowed) if boundary_weight else None

    raw_weights = [float(item.get("weight") or 1) for item in selected]
    top_weight, low_weight = max(raw_weights), min(raw_weights)
    relative_size = 10.0
    if top_weight != low_weight and low_weight > 0:
        weight_exponent = math.log(relative_size) / math.log(top_weight / low_weight)
    else:
        weight_exponent = 1.0
    normalized_weights = [
        (weight / top_weight) ** weight_exponent for weight in raw_weights
    ]
    normalized_sum = sum(normalized_weights)

    queue: list[dict[str, Any]] = []
    for item, normalized_weight in zip(selected, normalized_weights):
        queue.append(
            {
                "item": item,
                "normalized_weight": normalized_weight,
                "repeat_round": 0,
            }
        )
    repeat_index = 0
    while len(queue) < max_placed_instances:
        selected_index = repeat_index % len(selected)
        queue.append(
            {
                "item": selected[selected_index],
                "normalized_weight": normalized_weights[selected_index],
                "repeat_round": 1 + repeat_index // len(selected),
            }
        )
        repeat_index += 1

    nominal_font = ImageFont.truetype(str(font_path), 100)
    rng = random.Random(seed)
    placements: list[dict[str, Any]] = []
    first_height = 0.0

    for rank, entry in enumerate(queue[:max_placed_instances], start=1):
        term = str(entry["item"]["term"])
        bbox = nominal_font.getbbox(term)
        nominal_width = max(1, bbox[2] - bbox[0])
        nominal_height = max(1, bbox[3] - bbox[1])
        target_ratio = nominal_width / nominal_height
        free_rectangle = _microcloud_best_free_rectangle(
            allowed,
            occupied,
            target_ratio,
            edge_distance=edge_distance if rank >= boundary_fill_start_rank else None,
            boundary_weight=boundary_weight if rank >= boundary_fill_start_rank else 0.0,
        )
        if free_rectangle["width"] <= 1 or free_rectangle["height"] <= 1:
            break

        inset = density * min(free_rectangle["width"], free_rectangle["height"])
        rectangle_x = free_rectangle["x"] + inset / 2
        rectangle_y = free_rectangle["y"] + inset / 2
        rectangle_width = free_rectangle["width"] - inset
        rectangle_height = free_rectangle["height"] - inset
        fit_scale = min(
            rectangle_width / nominal_width,
            rectangle_height / nominal_height,
        )

        normalized_weight = float(entry["normalized_weight"])
        if rank == 1:
            target_scale = headline_scale * math.sqrt(
                normalized_weight
                / normalized_sum
                * shape_area
                / (nominal_width * nominal_height)
            )
            scale = min(fit_scale, target_scale)
            first_height = nominal_height * scale
        else:
            target_height = first_height * _microcloud_rank_ratio(rank)
            scale = min(fit_scale, target_height / nominal_height)

        word_width = nominal_width * scale
        word_height = nominal_height * scale
        if rank == 1:
            center_x = rectangle_x + rectangle_width / 2
            center_y = rectangle_y + rectangle_height / 2
        else:
            center_x = (
                rectangle_x
                + rectangle_width / 2
                + (rng.random() - 0.5) * max(0.0, rectangle_width - word_width)
            )
            center_y = (
                rectangle_y
                + rectangle_height / 2
                + (rng.random() - 0.5) * max(0.0, rectangle_height - word_height)
            )

        width = max(1, int(round(word_width)))
        height = max(1, int(round(word_height)))
        x = int(round(center_x - word_width / 2))
        y = int(round(center_y - word_height / 2))
        x = max(0, min(x, plan_width - width))
        y = max(0, min(y, plan_height - height))
        region_allowed = allowed[y : y + height, x : x + width]
        region_occupied = occupied[y : y + height, x : x + width]
        if not region_allowed.all():
            raise RuntimeError(f"Cloud-mask overflow at rank {rank}: {term}")
        if region_occupied.any():
            raise RuntimeError(f"Rectangle collision at rank {rank}: {term}")
        occupied[y : y + height, x : x + width] = True

        placements.append(
            {
                "term": term,
                "rank": rank,
                "repeat_round": int(entry["repeat_round"]),
                "source_weight": float(entry["item"].get("weight") or 1),
                "normalized_weight": normalized_weight,
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "font_size_plan": max(2, round(100 * scale)),
                "free_rectangle": free_rectangle,
            }
        )

    render_multiplier = max(8, int(settings.get("render_scale") or DEFAULT_RENDER_SCALE) * 4)
    horizontal = Image.new(
        "RGBA",
        (plan_width * render_multiplier, plan_height * render_multiplier),
        (0, 0, 0, 0),
    )
    solid_color = ImageColor.getrgb(color) + (255,)
    for placement in placements:
        sprite = _microcloud_text_alpha(
            placement["term"],
            font_path,
            placement["font_size_plan"] * render_multiplier,
        )
        target_size = (
            placement["width"] * render_multiplier,
            placement["height"] * render_multiplier,
        )
        if sprite.size != target_size:
            sprite = sprite.resize(target_size, Image.Resampling.LANCZOS)
        colored = Image.new("RGBA", sprite.size, solid_color)
        horizontal.paste(
            colored,
            (
                placement["x"] * render_multiplier,
                placement["y"] * render_multiplier,
            ),
            sprite,
        )

    rotated = horizontal.rotate(
        rotation,
        resample=Image.Resampling.BICUBIC,
        expand=True,
    )
    alpha_bbox = rotated.getchannel("A").getbbox()
    if not alpha_bbox:
        raise RuntimeError("The rendered word cloud is empty")
    cropped = rotated.crop(alpha_bbox)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(output_path, format="PNG", optimize=True)

    payload["image_path"] = str(output_path.resolve())
    payload["render_audit"] = {
        "method": "weiciyun_2_7_max_free_rectangle_rank_curve",
        "reference_layout_reused": False,
        "font_path": str(font_path.resolve()),
        "mask_path": str(
            Path(settings.get("mask_path") or DEFAULT_CLOUD_MASK_ASSET).resolve()
        ),
        "color": color,
        "rotation": rotation,
        "layout_grid": grid_size,
        "layout_canvas_size": [plan_width, plan_height],
        "density": density,
        "headline_scale": headline_scale,
        "boundary_fill_start_rank": boundary_fill_start_rank if boundary_weight else None,
        "boundary_weight": boundary_weight,
        "rank_curve": [list(item) for item in DEFAULT_MICROCLOUD_RANK_CURVE],
        "placement_mode": "typographic_rectangle",
        "rectangle_score": "area_times_aspect_ratio_similarity",
        "rotation_strategy": "horizontal_layout_then_rotate_whole_canvas",
        "render_multiplier": render_multiplier,
        "seed": seed,
        "output_size": list(cropped.size),
        "alpha_bbox_before_crop": list(alpha_bbox),
        "placed_instance_count": len(placements),
        "max_placed_instances": max_placed_instances,
        "placed_unique_term_count": len({item["term"] for item in placements}),
        "allowed_mask_pixel_count": shape_area,
        "rectangle_coverage_ratio": round(float(occupied.sum() / max(1, shape_area)), 4),
        "all_primary_terms_placed": all(
            any(
                placement["term"] == item["term"]
                and placement["repeat_round"] == 0
                for placement in placements
            )
            for item in selected
        ),
        "placed": placements,
    }
    return payload


def _july19_text_sprite(
    term: str,
    font_path: Path,
    font_size: int,
    color: str,
    rotation: int,
) -> tuple[Image.Image, np.ndarray]:
    """Render the exact glyph and collision masks used by the July 19 layout."""

    font = ImageFont.truetype(str(font_path), font_size)
    bbox = font.getbbox(term, stroke_width=0)
    width = max(1, bbox[2] - bbox[0] + 8)
    height = max(1, bbox[3] - bbox[1] + 8)
    base_alpha = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(base_alpha)
    draw.text((4 - bbox[0], 4 - bbox[1]), term, font=font, fill=255)
    alpha = base_alpha.rotate(rotation, resample=Image.Resampling.BICUBIC, expand=True)
    crop_box = alpha.getbbox()
    if crop_box:
        alpha = alpha.crop(crop_box)
    red, green, blue = ImageColor.getrgb(color)
    rotated = Image.new("RGBA", alpha.size, (red, green, blue, 255))
    rotated.putalpha(alpha)
    collision_filter = 5 if font_size >= 18 else 3 if font_size >= 12 else 1
    # Pillow's native size-one filter can crash on some Windows builds. It is
    # mathematically the identity, so bypass it without changing placement.
    collision = alpha.filter(ImageFilter.MaxFilter(collision_filter)) if collision_filter > 1 else alpha
    return rotated, np.asarray(collision) > 18


def render_wordcloud_png(
    payload: dict[str, Any], output_path: Path, seed: int = 20260710
) -> dict[str, Any]:
    """Render the approved July 19 hierarchy with small repeated background words."""

    settings = payload["settings"]
    width = int(settings.get("width") or DEFAULT_WIDTH)
    height = int(settings.get("height") or DEFAULT_HEIGHT)
    color = str(settings.get("color") or DEFAULT_COLOR)
    rotation = int(settings.get("rotation", DEFAULT_ROTATION))
    primary_minimum = int(settings.get("primary_font_min") or DEFAULT_PRIMARY_FONT_MIN)
    primary_maximum = int(settings.get("primary_font_max") or DEFAULT_PRIMARY_FONT_MAX)
    scale_exponent = float(settings.get("font_scale_exponent") or DEFAULT_FONT_SCALE_EXPONENT)
    font_path = resolve_font(settings.get("font_path"))
    allowed = cloud_mask(width, height, settings.get("mask_path"))
    allowed_image = Image.fromarray(np.where(allowed, 255, 0).astype(np.uint8))
    eroded = np.asarray(allowed_image.filter(ImageFilter.MinFilter(41))) > 0
    edge_band = allowed & ~eroded
    allowed_points = np.argwhere(allowed)
    mask_min_y, mask_min_x = allowed_points.min(axis=0)
    mask_max_y, mask_max_x = allowed_points.max(axis=0)
    occupied = np.zeros((height, width), dtype=bool)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    rng = random.Random(seed)
    selected = sorted(payload.get("selected") or [], key=lambda item: -int(item.get("weight") or 1))
    if not selected:
        raise ValueError("词云没有可渲染的selected词条")
    max_placed_instances = max(
        len(selected),
        int(settings.get("max_placed_instances") or DEFAULT_MAX_PLACED_INSTANCES),
    )

    weights = [int(item.get("weight") or 1) for item in selected]
    low, high = min(weights), max(weights)
    primary_queue: list[tuple[dict[str, Any], int, int]] = []
    for item in selected:
        weight = int(item.get("weight") or 1)
        ratio = 0.5 if high == low else (weight - low) / (high - low)
        font_size = primary_font_size(ratio, primary_minimum, primary_maximum, scale_exponent)
        primary_queue.append((item, font_size, 0))
    if len(primary_queue) > 1:
        primary_queue = [
            primary_queue[0],
            *sorted(
                primary_queue[1:],
                key=lambda entry: (
                    -len(str(entry[0].get("term") or "")),
                    -(len(str(entry[0].get("term") or "")) * entry[1] * entry[1]),
                ),
            ),
        ]
    repeat_queue: list[tuple[dict[str, Any], int, int]] = []
    for repeat_round, scale in enumerate(DEFAULT_REPEAT_SCALES, start=1):
        for item in selected:
            base_weight = int(item.get("weight") or 1)
            ratio = 0.5 if high == low else (base_weight - low) / (high - low)
            base_size = primary_font_size(
                ratio,
                DEFAULT_REPEAT_REFERENCE_MIN,
                DEFAULT_REPEAT_REFERENCE_MAX,
                DEFAULT_REPEAT_REFERENCE_EXPONENT,
            )
            font_size = max(10, round(base_size * scale))
            repeat_queue.append((item, font_size, repeat_round))

    placed: list[dict[str, Any]] = []
    primary_attempts = max(80, int(settings.get("primary_placement_attempts") or 220))
    repeat_attempts = max(40, int(settings.get("repeat_placement_attempts") or 120))
    primary_size_steps = max(3, int(settings.get("primary_size_steps") or 8))
    repeat_size_steps = max(2, int(settings.get("repeat_size_steps") or 3))
    primary_scale_used = 0.0

    def place_entries(entries: list[tuple[dict[str, Any], int, int]], capacity: int) -> list[str]:
        failures: list[str] = []
        for item, initial_size, repeat_round in entries:
            if len(placed) >= capacity:
                break
            term = str(item["term"])
            font_size = initial_size
            successful = False
            for _ in range(primary_size_steps if repeat_round == 0 else repeat_size_steps):
                sprite, collision = _july19_text_sprite(term, font_path, font_size, color, rotation)
                sprite_width, sprite_height = sprite.size
                if sprite_width >= width or sprite_height >= height:
                    font_size = max(10, round(font_size * 0.85))
                    continue
                attempt_count = primary_attempts if repeat_round == 0 else repeat_attempts
                for attempt in range(attempt_count):
                    if attempt == 0:
                        candidate_x = width // 2 - sprite_width // 2
                        candidate_y = int(height * 0.57) - sprite_height // 2
                    elif repeat_round > 0:
                        candidate_x = rng.randint(
                            max(0, int(mask_min_x) - sprite_width // 2),
                            min(width - sprite_width, int(mask_max_x) - sprite_width // 2),
                        )
                        candidate_y = rng.randint(
                            max(0, int(mask_min_y) - sprite_height // 2),
                            min(height - sprite_height, int(mask_max_y) - sprite_height // 2),
                        )
                    else:
                        spread = min(0.42, 0.08 + attempt / max(1, primary_attempts * 0.75))
                        candidate_x = round(rng.gauss(width * 0.50, width * spread)) - sprite_width // 2
                        candidate_y = round(rng.gauss(height * 0.58, height * spread * 0.72)) - sprite_height // 2
                    x = max(0, min(width - sprite_width, candidate_x))
                    y = max(0, min(height - sprite_height, candidate_y))
                    region_allowed = allowed[y : y + sprite_height, x : x + sprite_width]
                    region_occupied = occupied[y : y + sprite_height, x : x + sprite_width]
                    if collision.shape != region_allowed.shape:
                        continue
                    if np.any(collision & ~region_allowed) or np.any(collision & region_occupied):
                        continue
                    if repeat_round > 0 and attempt < round(repeat_attempts * 0.65):
                        region_edge = edge_band[y : y + sprite_height, x : x + sprite_width]
                        if not np.any(collision & region_edge):
                            continue
                    canvas.alpha_composite(sprite, (x, y))
                    occupied[y : y + sprite_height, x : x + sprite_width] |= collision
                    placed.append({
                        "term": term,
                        "font_size": font_size,
                        "repeat_round": repeat_round,
                        "x": x,
                        "y": y,
                        "width": sprite_width,
                        "height": sprite_height,
                    })
                    successful = True
                    break
                if successful:
                    break
                font_size = max(10, round(font_size * 0.84))
            if not successful:
                failures.append(term)
        return failures

    primary_failures: list[str] = []
    for primary_scale_used in (0.72, 0.62, 0.54, 0.47):
        occupied = np.zeros((height, width), dtype=bool)
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        placed = []
        rng = random.Random(seed)
        scaled_primary = [
            (item, max(10, round(font_size * primary_scale_used)), repeat_round)
            for item, font_size, repeat_round in primary_queue
        ]
        primary_failures = place_entries(scaled_primary, len(scaled_primary))
        if not primary_failures:
            break
    if primary_failures:
        raise RuntimeError("词云主词无法全部落位：" + "、".join(primary_failures))
    place_entries(repeat_queue, max_placed_instances)

    alpha_bbox = canvas.getchannel("A").getbbox()
    if not alpha_bbox:
        raise RuntimeError("词云渲染后为空")
    cropped = canvas.crop(alpha_bbox)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(output_path, format="PNG", optimize=True)
    payload["image_path"] = str(output_path.resolve())
    payload["render_audit"] = {
        "method": "july19_hierarchy_edge_fill",
        "font_path": str(font_path.resolve()),
        "font_family": list(ImageFont.truetype(str(font_path), 32).getname()),
        "font_sha256": hashlib.sha256(font_path.read_bytes()).hexdigest(),
        "font_scale": {
            "primary_min": primary_minimum,
            "primary_max": primary_maximum,
            "exponent": scale_exponent,
            "repeat_reference_min": DEFAULT_REPEAT_REFERENCE_MIN,
            "repeat_reference_max": DEFAULT_REPEAT_REFERENCE_MAX,
            "repeat_reference_exponent": DEFAULT_REPEAT_REFERENCE_EXPONENT,
            "repeat_scales": list(DEFAULT_REPEAT_SCALES),
        },
        "placement_budget": {
            "primary_attempts_per_size": primary_attempts,
            "repeat_attempts_per_size": repeat_attempts,
            "primary_size_steps": primary_size_steps,
            "repeat_size_steps": repeat_size_steps,
            "primary_scale_used": primary_scale_used,
        },
        "canvas_size": [width, height],
        "output_size": list(cropped.size),
        "alpha_bbox_before_crop": list(alpha_bbox),
        "placed_instance_count": len(placed),
        "max_placed_instances": max_placed_instances,
        "placed_unique_term_count": len({item["term"] for item in placed}),
        "allowed_mask_pixel_count": int(allowed.sum()),
        "collision_coverage_ratio": round(float(occupied.sum() / max(1, allowed.sum())), 4),
        "all_primary_terms_placed": all(
            any(
                placement["term"] == item["term"]
                and placement["repeat_round"] == 0
                for placement in placed
            )
            for item in selected
        ),
        "placed": placed,
    }
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从标准化CWH数据生成可审计热词词云PNG")
    parser.add_argument("normalized", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--payload", type=Path)
    parser.add_argument("--seed", type=int, default=20260710)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    normalized = json.loads(args.normalized.read_text(encoding="utf-8"))
    payload = normalized.get("hotwords")
    if not payload:
        raise ValueError("normalized JSON中缺少hotwords")
    render_wordcloud_png(payload, args.output, args.seed)
    normalized["hotwords"] = payload
    args.normalized.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.payload:
        args.payload.parent.mkdir(parents=True, exist_ok=True)
        args.payload.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "payload": str(args.payload or "")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
