from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

TEXT_KEYS = [
    "content", "body", "text", "desc", "title", "note_desc", "comment_content", "comment_text",
    "comment", "message", "raw_text", "snippet", "nickname",
]
COMMENT_TEXT_KEYS = [
    "content", "body", "text", "comment_content", "comment_text",
    "comment", "message", "raw_text", "snippet",
]
TITLE_KEYS = ["title", "note_title", "desc", "content", "text", "video_title"]
URL_KEYS = ["url", "link", "source_url", "note_url", "video_url", "share_url", "jump_url"]
ID_KEYS = ["id", "item_id", "note_id", "aweme_id", "video_id", "source_id", "uid", "user_id"]
COMMENT_ID_KEYS = ["comment_id", "cid", "reply_id", "parent_comment_id"]
AUTHOR_KEYS = ["author", "publisher", "site", "nickname", "user_nickname", "user_name", "screen_name", "creator", "sec_uid", "source"]
SPREAD_KEYS = ["spread_count", "liked_count", "like_count", "likes", "play_count", "view_count", "read_count", "share_count", "collect_count", "score"]
COMMENT_COUNT_KEYS = ["comment_count", "comments_count", "reply_comment_total", "sub_comment_count"]
TIME_KEYS = ["published_at", "create_date_time", "time", "created_at", "publish_time", "create_time", "last_modify_ts"]
COMMENT_MARKERS = ["comment", "评论", "reply"]
PLATFORM_ALIASES = {
    "xiaohongshu": "xhs",
    "douyin": "dy",
    "kuaishou": "ks",
    "bilibili": "bili",
    "weibo": "wb",
    "twitter": "x",
}
PLATFORM_NAMES = [
    "xhs", "xiaohongshu", "dy", "douyin", "ks", "kuaishou",
    "bili", "bilibili", "wb", "weibo", "tieba", "zhihu",
    "x", "twitter", "youtube", "reddit", "tiktok", "instagram",
    "bluesky", "threads", "pinterest", "truthsocial", "hackernews",
    "techmeme", "grounding", "github", "polymarket",
]
FOREIGN_SOCIAL_PLATFORMS = {"x", "youtube", "reddit", "tiktok", "instagram", "bluesky", "threads", "pinterest", "truthsocial"}
FOREIGN_MEDIA_PLATFORMS = {"grounding", "techmeme", "hackernews", "github", "polymarket"}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
    return rows


def read_json(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return []
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        items_by_source = data.get("items_by_source")
        if isinstance(items_by_source, dict):
            output = []
            for source, rows in items_by_source.items():
                if not isinstance(rows, list):
                    continue
                for item in rows:
                    if not isinstance(item, dict):
                        continue
                    row = dict(item)
                    row.setdefault("platform", source)
                    row.setdefault("foreign_query_topic", data.get("topic"))
                    output.append(row)
            return output
        for key in ("samples", "data", "items", "rows", "comments", "posts"):
            value = data.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
        return [data]
    return []


def read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
        return list(csv.DictReader(f))


def first(row: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def intish(value: Any) -> int:
    try:
        return int(float(str(value).replace(",", "").strip()))
    except Exception:
        return 0


def first_int(row: dict[str, Any], keys: list[str]) -> int:
    best = 0
    for key in keys:
        best = max(best, intish(row.get(key)))
    engagement = row.get("engagement")
    if isinstance(engagement, dict):
        nested_keys = (
            ["views", "view_count", "likes", "like_count", "shares", "reposts", "score"]
            if keys == SPREAD_KEYS
            else ["comments", "comment_count", "replies", "reply_count"]
            if keys == COMMENT_COUNT_KEYS
            else []
        )
        for key in nested_keys:
            best = max(best, intish(engagement.get(key)))
    return best


def detect_platform(path: Path, row: dict[str, Any]) -> str:
    direct = row.get("platform") or row.get("source_platform") or row.get("source")
    if direct:
        value = str(direct).lower()
        return PLATFORM_ALIASES.get(value, value)
    for part in reversed(path.parts):
        value = part.lower()
        if value in PLATFORM_NAMES:
            return PLATFORM_ALIASES.get(value, value)
    name = path.name.lower()
    for platform in PLATFORM_NAMES:
        if re.search(rf"(^|[_\-.]){re.escape(platform)}([_\-.]|$)", name):
            return PLATFORM_ALIASES.get(platform, platform)
    return "mediacrawler"


def detect_source_type(path: Path, row: dict[str, Any]) -> str:
    name = path.name.lower()
    platform = detect_platform(path, row)
    container = str(row.get("container") or row.get("kind") or row.get("type") or "").lower()
    is_comment_row = bool(
        any(marker in name for marker in COMMENT_MARKERS)
        or row.get("comment_id")
        or row.get("comment_content")
        or row.get("parent_comment_id")
        or container in {"comment", "reply", "comment_reply", "sub_comment"}
    )
    if is_comment_row and platform in FOREIGN_SOCIAL_PLATFORMS:
        return "overseas_public_discussion"
    if is_comment_row:
        return "netizen_comment"
    if platform in FOREIGN_SOCIAL_PLATFORMS:
        return "overseas_social_post"
    if platform in FOREIGN_MEDIA_PLATFORMS:
        return "overseas_media"
    if platform in {"xhs", "dy", "ks", "wb"}:
        return "social_note"
    if platform in {"bili", "zhihu", "tieba"}:
        return "self_media_post"
    return "media"


def load_manifest_topics(root: Path) -> dict[str, str]:
    mapping = {}
    for manifest in root.rglob("manifest.json"):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            continue
        for item in data.get("tasks", []):
            task = item.get("task") or item.get("path")
            topic = item.get("topic")
            if task and topic:
                mapping[Path(task).stem] = topic
    for resolved in root.rglob("task.resolved.json"):
        try:
            data = json.loads(resolved.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        topic = data.get("cwh_topic") or data.get("topic")
        if topic:
            mapping[resolved.parent.name] = str(topic)
        for query, exact_topic in (data.get("cwh_topic_map") or {}).items():
            mapping[f"query::{query}"] = str(exact_topic)
    return mapping


def topic_from_path(path: Path, row: dict[str, Any], manifest_topics: dict[str, str]) -> str:
    if row.get("cwh_topic"):
        return str(row["cwh_topic"])
    if row.get("topic"):
        return str(row["topic"])
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    query_topic = str(
        row.get("foreign_query_topic")
        or metadata.get("data_assistant_query_topic")
        or metadata.get("query_topic")
        or ""
    ).strip()
    if query_topic and manifest_topics.get(f"query::{query_topic}"):
        return manifest_topics[f"query::{query_topic}"]
    for part in path.parts:
        for stem, topic in manifest_topics.items():
            if stem in part:
                return topic
    return "unclassified"


def raw_id_for(source_type: str, row: dict[str, Any]) -> str:
    if source_type == "netizen_comment":
        comment_id = first(row, COMMENT_ID_KEYS)
        if comment_id:
            return comment_id
    return first(row, ID_KEYS)


def source_url_for(platform: str, row: dict[str, Any]) -> str:
    """Return a traceable source URL, deriving it from stable platform IDs when needed."""
    url = first(row, URL_KEYS)
    if url:
        return url
    if platform == "bili":
        video_id = str(row.get("video_id") or "").strip()
        if re.fullmatch(r"\d+", video_id):
            return f"https://www.bilibili.com/video/av{video_id}/"
        if re.fullmatch(r"BV[0-9A-Za-z]+", video_id, flags=re.IGNORECASE):
            return f"https://www.bilibili.com/video/{video_id}/"
    if platform == "wb":
        note_id = str(row.get("note_id") or row.get("mblogid") or row.get("mid") or "").strip()
        if re.fullmatch(r"\d+", note_id):
            return f"https://m.weibo.cn/detail/{note_id}"
    return ""

def normalize(path: Path, row: dict[str, Any], manifest_topics: dict[str, str]) -> dict[str, Any] | None:
    source_type = detect_source_type(path, row)
    content = first(row, COMMENT_TEXT_KEYS if source_type == "netizen_comment" else TEXT_KEYS)
    title = content[:80] if source_type == "netizen_comment" else (first(row, TITLE_KEYS) or content[:80])
    if not content and not title:
        return None
    spread = first_int(row, SPREAD_KEYS)
    platform = detect_platform(path, row)
    is_foreign = platform in FOREIGN_SOCIAL_PLATFORMS | FOREIGN_MEDIA_PLATFORMS or source_type.startswith("overseas_")
    is_public_discussion = source_type in {"netizen_comment", "overseas_public_discussion"}
    url = source_url_for(platform, row)
    raw_id = raw_id_for(source_type, row)
    return {
        "topic": topic_from_path(path, row, manifest_topics),
        "platform": platform,
        "source_type": source_type,
        "region": "overseas" if is_foreign else "domestic",
        "source": first(row, AUTHOR_KEYS) or detect_platform(path, row),
        "title": title,
        "content": content or title,
        "url": url,
        "spread_count": spread,
        "comment_count": first_int(row, COMMENT_COUNT_KEYS),
        "published_at": first(row, TIME_KEYS),
        "comment_id": raw_id if source_type == "netizen_comment" else "",
        "reply_id": str(row.get("reply_id") or "").strip(),
        "parent_comment_id": str(row.get("parent_comment_id") or "").strip(),
        "like_count": first_int(row, ["liked_count", "like_count", "likes"]),
        "sentiment": "unknown",
        "sentiment_source": "unprocessed",
        "sentiment_status": "unprocessed",
        "in_sentiment_denominator": False,
        "is_comment": "true" if is_public_discussion else "false",
        "quote_verified": bool(is_public_discussion and url and (content or title)),
        "evidence_mode": "verbatim_public_comment" if is_public_discussion and url else "public_evidence",
        "raw_id": raw_id,
        "raw_file": str(path),
    }


def read_rows(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    try:
        if suffix == ".jsonl":
            return read_jsonl(path)
        if suffix == ".json":
            return read_json(path)
        if suffix == ".csv":
            return read_csv(path)
    except Exception:
        return []
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize MediaSpider/MediaCrawler raw outputs into CWH sample JSON.")
    parser.add_argument("paths", nargs="+", help="Run dirs, raw dirs, or files.")
    parser.add_argument("--output", default="outputs/cwh_mediacrawler_samples.json")
    args = parser.parse_args()

    roots = [Path(p) for p in args.paths]
    manifest_topics: dict[str, str] = {}
    for root in roots:
        if root.exists():
            manifest_topics.update(load_manifest_topics(root if root.is_dir() else root.parent))

    samples = []
    seen = set()
    files = []
    for root in roots:
        if root.is_file():
            files.append(root)
        elif root.exists():
            files.extend(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in {".jsonl", ".json", ".csv"})
    for file in files:
        for row in read_rows(file):
            sample = normalize(file, row, manifest_topics)
            if not sample:
                continue
            key = sample.get("raw_id") or sample.get("url") or (sample.get("platform"), sample.get("content")[:120])
            if key in seen:
                continue
            seen.add(key)
            samples.append(sample)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"samples": samples}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "files_scanned": len(files), "samples": len(samples), "output": str(out)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
