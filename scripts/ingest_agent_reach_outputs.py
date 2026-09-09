from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

TEXT_KEYS = ["comment", "comment_text", "reply", "content", "text", "desc", "summary", "title"]
TITLE_KEYS = ["title", "note_title", "video_title", "content", "text"]
URL_KEYS = ["url", "link", "note_url", "video_url", "source_url"]
AUTHOR_KEYS = ["author", "nickname", "user_name", "source", "screen_name"]
PLATFORM_HINTS = ["xiaohongshu", "xhs", "bilibili", "bili", "v2ex", "reddit", "twitter", "x.com", "youtube"]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def read_json(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return []
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("samples", "items", "rows", "data", "comments", "replies", "posts", "results"):
            value = data.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
        return [data]
    return []


def read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
        return list(csv.DictReader(f))


def read_text_output(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return []
    rows = []
    chunks = [x.strip() for x in re.split(r"\n\s*\n", text) if x.strip()]
    for chunk in chunks[:100]:
        rows.append({"content": chunk, "title": chunk.splitlines()[0][:80], "source": path.stem})
    return rows


def read_rows(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        return read_jsonl(path)
    if suffix == ".json":
        return read_json(path)
    if suffix == ".csv":
        return read_csv(path)
    if suffix in {".txt", ".yaml", ".yml"}:
        return read_text_output(path)
    return []


def first(row: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def detect_platform(path: Path, row: dict[str, Any]) -> str:
    direct = str(row.get("platform") or row.get("source_platform") or "").strip()
    if direct:
        return direct
    text = f"{path} {first(row, URL_KEYS)}".lower()
    for hint in PLATFORM_HINTS:
        if hint in text:
            return "bili" if hint == "bilibili" else hint
    return "agent_reach"


def looks_like_comment(path: Path, row: dict[str, Any]) -> bool:
    text = f"{path.name} {' '.join(row.keys())}".lower()
    if any(x in text for x in ["comment", "reply", "replies", "评论", "回复"]):
        return True
    value = first(row, ["comment", "comment_text", "reply"])
    return bool(value)


def load_manifest_topics(root: Path) -> list[str]:
    topics: list[str] = []
    for manifest in root.rglob("manifest.json"):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            continue
        for topic in data.get("topics", []):
            if topic and topic not in topics:
                topics.append(str(topic))
    return topics


def match_topic(text: str, topics: list[str]) -> str:
    if not topics:
        return "unclassified"
    best = topics[0]
    best_score = -1
    for topic in topics:
        terms = [topic, *re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,12}", topic)]
        score = sum(1 for term in set(terms) if term and term in text)
        if score > best_score:
            best = topic
            best_score = score
    return best


def normalize(path: Path, row: dict[str, Any], topics: list[str], idx: int) -> dict[str, Any] | None:
    content = first(row, TEXT_KEYS)
    title = first(row, TITLE_KEYS) or content[:80]
    if not content and not title:
        return None
    error_text = f"{title}\n{content}".lower()
    if any(marker in error_text for marker in ["auth_required", "ok: false", "command not found", "exitcode", "traceback"]):
        return None
    platform = detect_platform(path, row)
    is_comment = looks_like_comment(path, row)
    text = f"{title} {content} {row.get('query', '')}"
    return {
        "id": str(row.get("id") or row.get("raw_id") or f"agent_reach_{idx:05d}"),
        "topic": str(row.get("topic") or match_topic(text, topics)),
        "platform": platform,
        "source_type": "netizen_comment" if is_comment else "self_media_post",
        "region": "domestic",
        "source": first(row, AUTHOR_KEYS) or platform,
        "title": title,
        "content": content or title,
        "url": first(row, URL_KEYS),
        "published_at": str(row.get("published_at") or row.get("created_at") or row.get("time") or ""),
        "spread_count": 0,
        "comment_count": 0,
        "is_comment": "true" if is_comment else "false",
        "quote_verified": bool(is_comment and first(row, URL_KEYS) and content),
        "evidence_mode": "verbatim_public_comment" if is_comment else "verbatim_public_post",
        "comment_id": str(row.get("comment_id") or row.get("reply_id") or row.get("id") or "") if is_comment else "",
        "raw_file": str(path),
        "sentiment": "unknown",
        "sentiment_source": "unprocessed",
        "sentiment_status": "unprocessed",
        "in_sentiment_denominator": False,
        "quality_flags": ["agent_reach_sample"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize agent-reach outputs into CWH sample JSON.")
    parser.add_argument("paths", nargs="+", help="agent-reach output files or directories.")
    parser.add_argument("--output", default="outputs/cwh_agent_reach_samples.json")
    parser.add_argument("--topics", default="", help="Optional JSON list or comma-separated topic names.")
    args = parser.parse_args()

    roots = [Path(p) for p in args.paths]
    topics: list[str] = []
    if args.topics:
        try:
            value = json.loads(args.topics)
            if isinstance(value, list):
                topics = [str(x) for x in value]
        except Exception:
            topics = [x.strip() for x in args.topics.split(",") if x.strip()]
    for root in roots:
        if root.exists():
            topics.extend(x for x in load_manifest_topics(root if root.is_dir() else root.parent) if x not in topics)

    files: list[Path] = []
    for root in roots:
        if root.is_file():
            if ".stderr" not in root.name:
                files.append(root)
        elif root.exists():
            files.extend(
                p
                for p in root.rglob("*")
                if p.is_file()
                and ".stderr" not in p.name
                and p.suffix.lower() in {".json", ".jsonl", ".csv", ".txt", ".yaml", ".yml"}
            )

    samples = []
    seen = set()
    for file in files:
        for row in read_rows(file):
            sample = normalize(file, row, topics, len(samples) + 1)
            if not sample:
                continue
            key = sample.get("url") or (sample.get("platform"), sample.get("content", "")[:120])
            if key in seen:
                continue
            seen.add(key)
            samples.append(sample)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"samples": samples}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "files_scanned": len(files), "samples": len(samples), "output": str(out)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
