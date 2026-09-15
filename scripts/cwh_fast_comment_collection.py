"""Fast, traceable no-login comment discovery for bounded CWH runs.

The collector derives queries from the current workbook topics. It retains raw
Toutiao response envelopes and produces the exact capture and coverage inputs
consumed by ``cwh_comment_semantics``. Other mandatory platforms are recorded
as login-blocked when no authorized session is supplied; no article body,
search result, or comment count is converted into a comment.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from cwh_pipeline_runtime import atomic_write_json
from cwh_toutiao_capture import normalize
from cwh_comment_filters import is_procedural_only
from discover_toutiao_comment_seeds import (
    comment_endpoint,
    discover,
    fetch_text,
    iter_comments,
    parse_bound,
    parse_time,
)


MEETING_MARKERS = ("国务院常务会议", "国常会")


def topic_fragments(topic: str, aliases=()) -> list[str]:
    """Return conservative topic aliases without period-specific vocabulary."""
    cleaned = re.sub(r"\s+", "", str(topic or ""))
    values = [cleaned]
    for part in re.split(r"[、，及与和]", cleaned):
        if len(part) >= 4:
            values.append(part)
    for value in list(values):
        root = re.sub(r'(?:建设|修改|修订|实施|有关工作)$', '', value)
        if len(root) >= 3 and root != value:
            values.append(root)
    values.extend(re.sub(r'\s+', '', alias) for alias in aliases if isinstance(alias, str) and len(alias.strip()) >= 3)
    return list(dict.fromkeys(value for value in values if value))


def query_variants(topic: str, aliases=()) -> list[str]:
    fragments = topic_fragments(topic)
    primary = fragments[0]
    suffixes = fragments[1:] or fragments
    queries = [
        f"国务院常务会议部署{primary}工作",
    ]
    # Put current, declared short names inside the bounded search cutoff,
    # rather than using them only after discovery for parent-title matching.
    declared = [re.sub(r'\s+', '', alias) for alias in aliases
                if isinstance(alias, str) and len(alias.strip()) >= 3]
    queries.extend(f"国务院常务会议{alias}" for alias in list(dict.fromkeys(declared))[:2]
                   if alias != primary)
    queries.extend([f"国务院常务会议研究推进{primary}", f"国务院常务会议研究{primary}"])
    queries.extend(f"国务院常务会议部署加快建设{fragment}" for fragment in reversed(suffixes))
    queries.append(f"国务院常务会议{primary}")
    return list(dict.fromkeys(queries))


def relevant_parent_title(title: str, topic: str, aliases=()) -> bool:
    compact = re.sub(r"\s+", "", str(title or ""))
    return any(marker in compact for marker in MEETING_MARKERS) and any(
        fragment in compact for fragment in topic_fragments(topic, aliases)
    )


def fetch_candidate(gid: str, search_title: str, timeout: int) -> dict[str, Any]:
    url = f"https://www.toutiao.com/article/{gid}/"
    endpoint = comment_endpoint(gid, 0, 50)
    body = fetch_text(endpoint, url, timeout=timeout)
    payload = json.loads(body)
    title = str((payload.get("repost_params") or {}).get("title") or search_title or "").strip()
    return {"gid": gid, "url": url, "endpoint": endpoint, "body": body, "payload": payload, "title": title}


def discover_topic(
    topic: str,
    start: str,
    end: str,
    raw_dir: Path,
    *,
    max_queries: int = 5,
    max_candidates_per_query: int = 80,
    max_articles: int = 3,
    timeout: int = 15,
    aliases=(),
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    left = parse_bound(start)
    right = parse_bound(end, end=True)
    accepted: list[dict[str, Any]] = []
    searches: list[dict[str, Any]] = []
    tried: set[str] = set()
    for query in query_variants(topic, aliases)[:max_queries]:
        try:
            found = discover(query)
            search_record = {"query": query, "status": "completed", "result_count": len(found),
                             "error": "", "candidate_outcomes": []}
            searches.append(search_record)
        except Exception as exc:
            searches.append({"query": query, "status": "access_failed", "result_count": 0,
                             "error": f"{type(exc).__name__}: {exc}"})
            continue
        candidates = [(gid, title) for gid, title in found.items() if gid not in tried][:max_candidates_per_query]
        tried.update(gid for gid, _ in candidates)
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(fetch_candidate, gid, title, timeout) for gid, title in candidates]
            for future in futures:
                try:
                    item = future.result()
                    response_path = raw_dir / f"candidate-response-{item['gid']}-{hashlib.sha256(item['body'].encode()).hexdigest()[:12]}.json"
                    atomic_write_json(response_path, {'url': item['endpoint'], 'status': 200,
                        'body': item['body'], 'search_title': item['title'], 'discovery_query': query})
                    message = item['payload'].get('message')
                    if message is not None and message != 'success':
                        search_record['candidate_outcomes'].append({'gid': item['gid'], 'title': item['title'],
                            'in_window_comments': 0, 'title_relevant': False, 'access_failed': True,
                            'raw_response_path': str(response_path),
                            'error': 'Comment API returned a non-success message; cannot infer zero comments'})
                        continue
                    comments = iter_comments(item["payload"])
                    in_window = [row for row in comments if (parse_time(row.get("create_time")) and
                                 left <= parse_time(row.get("create_time")) <= right)]
                    reviewable = [row for row in in_window if not is_procedural_only(row.get('text'))]
                    outcome = {"gid": item["gid"], "title": item["title"],
                               "in_window_comments": len(in_window),
                               "nonprocedural_comments_before_review": len(reviewable),
                               "procedural_filtered_comments": len(in_window) - len(reviewable),
                               "raw_response_path": str(response_path), "access_failed": False,
                               "title_relevant": relevant_parent_title(item["title"], topic, aliases)}
                    search_record["candidate_outcomes"].append(outcome)
                    if not reviewable or not outcome["title_relevant"]:
                        continue
                    # Preserve the exact response body. The separately recorded
                    # search title is context only and never injected into it.
                    raw_path = raw_dir / f"toutiao-{item['gid']}.json"
                    atomic_write_json(raw_path, {
                        "url": item["endpoint"], "status": 200, "body": item["body"],
                        "search_title": item["title"], "discovery_query": query,
                    })
                    accepted.append({
                        "topic": topic,
                        "query": query,
                        "gid": item["gid"],
                        "url": item["url"],
                        "raw_file": str(raw_path.resolve()),
                        "comment_count": len(in_window),
                        "nonprocedural_comment_count": len(reviewable),
                        "title": item['title'],
                    })
                except Exception as exc:
                    search_record["candidate_outcomes"].append({
                        "gid": "", "title": "", "in_window_comments": 0,
                        "title_relevant": False, "access_failed": True, "error": f"{type(exc).__name__}: {exc}",
                    })
                    continue
        accepted.sort(key=lambda row: (-row["nonprocedural_comment_count"], row["gid"]))
        if len(accepted) >= max_articles:
            break
    return accepted[:max_articles], searches


def required_comment_sources(registry: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row for row in registry.get("sources") or []
        if row.get("tier") == "comment_platform" and row.get("must_check")
    ]


def apply_review_cap(
    capture: dict[str, Any],
    url_topics: dict[str, str],
    *,
    max_total: int = 24,
    max_per_topic: int = 10,
) -> tuple[dict[str, Any], int]:
    """Bound model input while retaining every omitted row in the audit."""
    posts = {row["id"]: row for row in capture.get("posts") or []}
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in capture.get("rows") or []:
        url = str((posts.get(row.get("parent_post_id")) or {}).get("url") or "")
        topic = url_topics.get(url, "")
        if topic:
            buckets.setdefault(topic, []).append(row)
    for rows in buckets.values():
        rows.sort(key=lambda row: (-int(row.get("like_count") or 0),
                                   -min(len(str(row.get("text") or "")), 240),
                                   str(row.get("comment_id") or "")))
    selected: list[dict[str, Any]] = []
    topics = list(buckets)
    for rank in range(max_per_topic):
        for topic in topics:
            if len(selected) >= max_total:
                break
            if rank < len(buckets[topic]):
                selected.append(buckets[topic][rank])
        if len(selected) >= max_total:
            break
    selected_ids = {str(row.get("sample_id") or "") for row in selected}
    omitted = [
        {**row, "exclusion_reason": "bounded_semantic_review_sample_cap"}
        for row in capture.get("rows") or []
        if str(row.get("sample_id") or "") not in selected_ids
    ]
    used_posts = {row.get("parent_post_id") for row in selected}
    capture["rows"] = selected
    capture["posts"] = [row for row in capture.get("posts") or [] if row.get("id") in used_posts]
    capture["excluded"] = list(capture.get("excluded") or []) + omitted
    capture["review_cap"] = {
        "max_total": max_total,
        "max_per_topic": max_per_topic,
        "discovered_rows": len(selected) + len(omitted),
        "reviewed_rows": len(selected),
        "omitted_rows": len(omitted),
        "rule": "round_robin_by_topic_then_like_count_and_substantive_length",
    }
    return capture, len(omitted)


def metadata_topic_aliases(task_path: Path) -> tuple[dict, dict]:
    state_path = Path(task_path).resolve().parent.parent / 'pipeline_state.json'
    if not state_path.is_file():
        return {}, {}
    contract = json.loads(state_path.read_text('utf-8-sig')).get('input_contract') or {}
    raw = contract.get('metadata')
    if not raw:
        return {}, {}
    path = Path(raw)
    metadata = json.loads(path.read_text('utf-8-sig'))
    titles, aliases = metadata.get('topic_titles') or [], metadata.get('topic_aliases') or []
    if not aliases:
        return {}, {}
    if len(titles) != len(aliases) or any(not isinstance(row, list) for row in aliases):
        raise ValueError('Current input metadata aliases do not align with topic_titles')
    return dict(zip(titles, aliases)), {'metadata_file': str(path.resolve()),
        'metadata_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'basis': 'current_input_declared_aliases_not_historical_seed'}


def collect(task_path: Path) -> tuple[Path, Path, dict[str, Any]]:
    task = json.loads(Path(task_path).read_text(encoding="utf-8-sig"))
    workspace = Path(task["stage_workspace"]).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    raw_dir = workspace / "fast_comment_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    plan = json.loads(Path(task["inputs"]["research_plan"]).read_text(encoding="utf-8-sig"))
    registry = json.loads(Path(task["inputs"]["source_registry"]).read_text(encoding="utf-8-sig"))
    start = str(plan["monitoring_period"]["start"])
    end = str(plan["monitoring_period"]["end"])
    topics = [str(row["topic"]) for row in plan.get("topics") or []]
    alias_map, alias_provenance = metadata_topic_aliases(task_path)
    if not topics:
        raise ValueError("Research plan has no workbook topics")

    accepted_by_topic: dict[str, list[dict[str, Any]]] = {}
    searches_by_topic: dict[str, list[dict[str, Any]]] = {}
    claimed_urls: set[str] = set()
    observations = {"checks": []}
    for topic in topics:
        accepted, searches = discover_topic(topic, start, end, raw_dir, aliases=alias_map.get(topic, []))
        # One parent URL may not be routed to multiple topics.
        accepted = [row for row in accepted if row["url"] not in claimed_urls]
        claimed_urls.update(row["url"] for row in accepted)
        accepted_by_topic[topic] = accepted
        searches_by_topic[topic] = searches
        observations["checks"].extend({
            "source_id": "toutiao_public_comments",
            "status": "actual_comment_response_requires_normalization",
            "raw_file": row["raw_file"],
            "seed_url": row["url"],
        } for row in accepted)

    capture = normalize(observations, start, end)
    capture["topic_assignment_from_historical_seed"] = False
    discovered_comments = len(capture.get("rows") or [])
    url_topics = {row["url"]: topic for topic, rows in accepted_by_topic.items() for row in rows}
    capture, omitted_comments = apply_review_cap(capture, url_topics)
    multi_topic_parents = [{'parent_post_id': post['id'], 'topic_candidates': matched}
        for post in capture.get('posts') or []
        if len(matched := [topic for topic in topics
            if relevant_parent_title(post.get('text', ''), topic, alias_map.get(topic, []))]) > 1]
    capture_path = workspace / "comment_capture.json"
    atomic_write_json(capture_path, capture)
    atomic_write_json(workspace / "fast_comment_search_audit.json", {
        "topics": [{"topic": topic, "searches": searches_by_topic[topic],
                    "accepted_parent_posts": accepted_by_topic[topic]} for topic in topics]
    })

    ids_by_url: dict[str, list[str]] = {}
    posts = {row["id"]: row for row in capture.get("posts") or []}
    for row in capture.get("rows") or []:
        url = str((posts.get(row.get("parent_post_id")) or {}).get("url") or "")
        ids_by_url.setdefault(url, []).append(str(row.get("comment_id") or ""))

    required = required_comment_sources(registry)
    coverage = []
    for topic in topics:
        accepted = accepted_by_topic[topic]
        topic_ids = [item for row in accepted for item in ids_by_url.get(row["url"], [])]
        checks = []
        for source in required:
            source_id = str(source["id"])
            if source_id == "toutiao_public_comments":
                queries = [row["query"] for row in searches_by_topic[topic]]
                urls = [row["url"] for row in accepted]
                inaccessible = any(row['status'] == 'access_failed' or
                    any(o.get('access_failed') for o in row.get('candidate_outcomes') or [])
                    for row in searches_by_topic[topic])
                response_files = [o['raw_response_path'] for row in searches_by_topic[topic]
                    for o in row.get('candidate_outcomes') or [] if o.get('raw_response_path')]
                checks.append({
                    "source_id": source_id,
                    "status": "hit" if topic_ids else ("access_failed" if inaccessible else "no_relevant_result"),
                    "execution_mode": "fixed_no_login_toutiao_search_and_comment_api",
                    "queries_or_seed_urls": urls or queries,
                    "queries": queries,
                    "result_count": len(topic_ids),
                    "eligible_comment_ids": topic_ids,
                    "raw_files": list(dict.fromkeys([row["raw_file"] for row in accepted] + response_files)),
                    "blocker": "" if topic_ids else ("Some search/comment requests failed; cannot infer absence of discussion"
                        if inaccessible else "No in-window traceable comments found by bounded platform search"),
                    "fresh_discovery": True,
                })
            else:
                checks.append({
                    "source_id": source_id,
                    "status": "access_failed",
                    "execution_mode": "fixed_registry_login_preflight",
                    "queries_or_seed_urls": [f"{plan.get('agenda') or '国务院常务会议'} {topic}"],
                    "result_count": 0,
                    "eligible_comment_ids": [],
                    "raw_files": [],
                    "blocker": "Source registry requires login and this isolated fast run has no authorized platform session",
                })
        coverage.append({"topic": topic, "checks": checks})

    global_checks = []
    for source in required:
        source_id = str(source["id"])
        topic_checks = [next(check for check in row["checks"] if check["source_id"] == source_id) for row in coverage]
        status = "hit" if any(check["status"] == "hit" for check in topic_checks) else topic_checks[0]["status"]
        global_checks.append({"source_id": source_id, "status": status})
    audit = {
        "registry_version": registry.get("version"),
        "coverage_by_topic": coverage,
        "checks": global_checks,
        "terminal_status": "bounded_checks_completed",
        "waiting_login_terminal": False,
        "fresh_discovery": True,
        "collector": "fixed_no_login_fast_path_v1",
        "topic_alias_provenance": alias_provenance,
        "multi_topic_parents": multi_topic_parents,
    }
    audit_path = workspace / "comment_collection_audit.json"
    atomic_write_json(audit_path, audit)
    summary = {
        "topics": topics,
        "accepted_parent_posts": sum(len(rows) for rows in accepted_by_topic.values()),
        "discovered_comments": discovered_comments,
        "captured_comments": len(capture.get("rows") or []),
        "comments_omitted_by_review_cap": omitted_comments,
        "capture": str(capture_path),
        "audit": str(audit_path),
    }
    atomic_write_json(workspace / "fast_comment_collection_summary.json", summary)
    return capture_path, audit_path, summary


def prepare_task(task_path: Path) -> dict[str, Any]:
    capture_path, audit_path, summary = collect(task_path)
    task = json.loads(Path(task_path).read_text(encoding="utf-8-sig"))
    task["inputs"]["comment_capture"] = str(capture_path)
    task["inputs"]["comment_collection_audit"] = str(audit_path)
    atomic_write_json(Path(task_path), task)
    return summary
