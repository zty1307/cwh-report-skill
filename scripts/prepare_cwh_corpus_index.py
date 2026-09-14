"""Index every raw article; shortlist reading order without semantic rejection."""
import hashlib
import copy
from pathlib import Path
import re
from cwh_pipeline_runtime import atomic_write_json, sha256_file


def reading_fingerprint(text: str) -> set[str]:
    compact = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", text).lower()
    return {compact[i:i+8] for i in range(max(0, len(compact)-7))}


def near_same_reading(left: set[str], right: set[str]) -> bool:
    # Reading-order diversity only: these rows remain in the untouched corpus.
    return bool(left and right) and len(left & right) / min(len(left), len(right)) >= .82


def complete_corpus_deferrals(data: dict, corpus: dict, topics: list[str]) -> dict:
    """Account for unread records without pretending they were semantically reviewed."""
    result = copy.deepcopy(data)
    research = (result.get("research_audit") or {}).get("domestic_media_research") or {}
    reviews = (research.get("public_article_corpus_review") or {}).get("topic_reviews") or []
    for row in reviews:
        if row.get("topic") not in topics:
            continue
        topic_number = topics.index(row["topic"]) + 1
        expected = {item["record_id"] for item in corpus.get("candidates", []) if topic_number in item.get("topic_hits", [])}
        reviewed = set(row.get("reviewed_record_ids") or [])
        row.setdefault("deferred_record_ids", sorted(expected - reviewed))
        if row["deferred_record_ids"]:
            row.setdefault("deferral_reason", "未进入本轮限时逐篇审核，原文及索引保留供补审；未审不等于排除或没有观点。")
    return result


def prepare_corpus_index(source: Path, corpus: dict, topics: list[str]) -> Path:
    root = source.parent / "corpus_index"
    root.mkdir(exist_ok=True)
    rows = corpus.get("candidates") or []
    index = {"source_sha256": sha256_file(source), "candidate_count": len(rows), "reading_indexes": [], "topics": []}
    for number, topic in enumerate(topics, 1):
        candidates = [x for x in rows if number in x.get("topic_hits", [])]
        alias_groups = corpus.get("topic_aliases") or []
        aliases = [topic, *(alias_groups[number - 1] if number <= len(alias_groups) else [])]
        ranked = sorted(candidates, key=lambda x: (
            -bool(re.search("解读|专家|认为|指出|意味着|如何", str(x.get("title", "")))),
            -max((len(str(alias)) for alias in aliases if str(alias) and str(alias) in str(x.get("title", ""))), default=0),
            -len(re.findall("解读|专家|认为|指出|意味着|如何", str(x.get("title", "")))),
            len(str(x.get("title", ""))), str(x.get("record_id", ""))))
        sources = {}
        selected = []
        delayed, fingerprints, titles_seen = [], [], set()
        for diversified in (True, False):
            for row in ranked if diversified else delayed:
                source_name = str(row.get("account") or row.get("source") or "")
                if sources.get(source_name, 0) >= 2:
                    continue
                fingerprint = reading_fingerprint(str(row.get("content") or ""))
                title_key = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", str(row.get("title") or "")).lower()
                if diversified and ((title_key and title_key in titles_seen) or any(near_same_reading(fingerprint, prior) for prior in fingerprints)):
                    delayed.append(row)
                    continue
                sources[source_name] = sources.get(source_name, 0) + 1
                selected.append(row)
                fingerprints.append(fingerprint)
                titles_seen.add(title_key)
                if len(selected) == 20:
                    break
            if len(selected) == 20:
                break
        reading_order = []
        for row in selected:
            key = hashlib.sha256(str(row["record_id"]).encode()).hexdigest()[:20]
            article = root / f"article-{key}.json"
            atomic_write_json(article, row)
            reading_order.append({"record_id": row["record_id"], "title": row.get("title"),
                                  "source": row.get("source"), "full_text_path": str(article)})
        topic_index = root / f"topic-{number}.json"
        atomic_write_json(topic_index, {"topic": topic, "reading_order_only_not_review": True,
                                      "reading_diversity": "delay_high_overlap_fulltexts_without_excluding_them",
                                      "shortlist": reading_order,
                                      "all_candidates": [{k: row.get(k) for k in ("record_id", "title", "source", "published_at", "url")} for row in candidates]})
        index["reading_indexes"].append({"topic": topic, "path": str(topic_index)})
        index["topics"].append({"topic": topic, "record_ids": [x["record_id"] for x in candidates],
                                "reading_index": str(topic_index), "shortlist": reading_order})
    path = source.parent / "public_corpus_index.json"
    atomic_write_json(path, index)
    return path
