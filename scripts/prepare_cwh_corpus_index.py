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


def professional_quote_hint(text: str, aliases: list[str]) -> int:
    """Reading hint only: named professional attribution near a policy object."""
    roles = '教授|研究员|研究总监|研究中心主任|研究院院长|研究院副院长|首席经济学家|首席分析师|首席专家|专委会副主任|专家委员会委员|联合会会长|副会长|理事长'
    verbs = '认为|表示|指出|强调|称|建议|解读'
    # Learn only explicitly attributed names from this same source. A later
    # "X told [outlet]" paragraph need not repeat the full professional role.
    names = {m.group(1) for m in re.finditer(
        rf'(?:{roles})([\u4e00-\u9fff]{{2,4}})(?=对|在|[，,]?\s*(?:{verbs}))', text)}
    starts = set()
    for name in names:
        pattern = rf'{re.escape(name)}(?:(?:对|在)[^。！？；\n]{{0,80}}?)?[，,]?\s*(?:{verbs})'
        for match in re.finditer(pattern, text):
            # Neighbouring background/bulletin paragraphs cannot lend their
            # topic to this attribution. All original rows remain readable.
            paragraph_start = text.rfind('\n', 0, match.start()) + 1
            paragraph_end = text.find('\n', match.end())
            if paragraph_end < 0:
                paragraph_end = len(text)
            context = text[max(paragraph_start, match.start()-500):min(paragraph_end, match.end()+500)]
            if any(alias and alias in context for alias in aliases):
                starts.add(match.start())
    return min(3, len(starts))


def reasoning_reading_hint(text: str, aliases: list[str]) -> int:
    """Prioritize reading possible reasoning near this policy, not eligibility.

    An unverified forecast or a policy-primary argument can match this hint.
    Neither is certified here; the unchanged author/reviewer gates decide.
    """
    markers = r'不等于|不意味着|取决于|有助于|这将|这意味着|意味着|预计|研判|建议|风险在于|前提是'
    # Declared short policy names remain meaningful even when the full agenda
    # title is long. A long title must not suppress all of its actual aliases.
    aliases = [alias for alias in aliases if len(alias) >= 3]
    paragraphs = [p.strip() for p in re.split(r'\n+', text) if p.strip()]
    starts = set()
    for number, paragraph in enumerate(paragraphs):
        prefix = ''
        if number and not re.match(r'^(?:[0-9]+[.、]|[一二三四五六七八九十]+、)', paragraph):
            prefix = paragraphs[number - 1][-200:]
        context = prefix + paragraph
        for match in re.finditer(markers, paragraph):
            position = len(prefix) + match.start()
            if any(alias and alias in context[max(0, position-200):position+len(match.group())+200]
                   for alias in aliases):
                starts.add((number, match.start()))
    return min(3, len(starts))


def prepare_corpus_index(source: Path, corpus: dict, topics: list[str], declared_aliases=None, *, shortlist_limit=40) -> Path:
    root = source.parent / "corpus_index"
    root.mkdir(exist_ok=True)
    rows = corpus.get("candidates") or []
    index = {"source_sha256": sha256_file(source), "candidate_count": len(rows), "reading_indexes": [], "topics": []}
    for number, topic in enumerate(topics, 1):
        candidates = [x for x in rows if number in x.get("topic_hits", [])]
        alias_groups = corpus.get("topic_aliases") or []
        aliases = [topic, *(alias_groups[number - 1] if number <= len(alias_groups) else [])]
        aliases.extend((declared_aliases or {}).get(topic) or [])
        aliases.append(re.sub(r'(?:修订|修改|建设|实施|有关工作)$', '', topic))
        aliases = list(dict.fromkeys(a for a in aliases if isinstance(a, str) and len(a) >= 3))
        hints = {str(x['record_id']): professional_quote_hint(str(x.get('content') or ''), aliases)
                 for x in candidates}
        reasoning_hints = {str(x['record_id']): reasoning_reading_hint(str(x.get('content') or ''), aliases)
                           for x in candidates}
        ranked = sorted(candidates, key=lambda x: (
            -hints[str(x['record_id'])],
            -max((len(str(alias)) for alias in aliases if str(alias) and str(alias) in str(x.get("title", ""))), default=0),
            -bool(reasoning_hints[str(x['record_id'])]),
            -bool(re.search("解读|专家|认为|指出|意味着|如何", str(x.get("title", "")))),
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
                if len(selected) >= shortlist_limit:
                    break
            if len(selected) >= shortlist_limit:
                break
        reading_order = []
        for row in selected:
            key = hashlib.sha256(str(row["record_id"]).encode()).hexdigest()[:20]
            article = root / f"article-{key}.json"
            atomic_write_json(article, row)
            reading_order.append({"record_id": row["record_id"], "title": row.get("title"),
                                  "professional_attribution_hint_count": hints[str(row['record_id'])],
                                  "reasoning_reading_hint_count": reasoning_hints[str(row['record_id'])],
                                  "source": row.get("source"), "full_text_path": str(article)})
        from cwh_raw_reading_discovery import discovery_cards
        discovery = discovery_cards(candidates, selected, aliases)
        originals = {row['record_id']: row for row in candidates}
        for row in discovery:
            key = hashlib.sha256(str(row['record_id']).encode()).hexdigest()[:20]
            article = root / f'article-{key}.json'
            atomic_write_json(article, originals[row['record_id']])
            row['full_text_path'] = str(article)
        topic_index = root / f"topic-{number}.json"
        atomic_write_json(topic_index, {"topic": topic, "reading_order_only_not_review": True,
                                      "reading_diversity": "delay_high_overlap_fulltexts_without_excluding_them",
                                      "priority_hint": "professional_attribution_then_possible_reasoning_near_current_policy_not_semantic_eligibility",
                                      "shortlist": reading_order,
                                      "discovery_shortlist": discovery,
                                      "all_candidates": [{k: row.get(k) for k in ("record_id", "title", "source", "published_at", "url")} for row in candidates]})
        index["reading_indexes"].append({"topic": topic, "path": str(topic_index)})
        index["topics"].append({"topic": topic, "record_ids": [x["record_id"] for x in candidates],
                                "reading_index": str(topic_index), "shortlist": reading_order,
                                "discovery_shortlist": discovery})
    path = source.parent / "public_corpus_index.json"
    atomic_write_json(path, index)
    return path
