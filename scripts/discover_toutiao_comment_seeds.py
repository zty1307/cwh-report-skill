"""Discover and audit public Toutiao comments from reviewed search queries.

This helper uses only Toutiao's public search page and public article comment
endpoint. Search results and article bodies are never counted as comments.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


CHINA_TZ = timezone(timedelta(hours=8))
SEARCH_URL = "https://so.toutiao.com/search?keyword={}"
COMMENT_URL = "https://www.toutiao.com/article/v2/tab_comments/?{}"


def fetch_text(url: str, referer: str = "", timeout: int = 30) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/138 Safari/537.36",
        "Accept": "text/html,application/json,text/plain,*/*",
    }
    if referer:
        headers["Referer"] = referer
    with urlopen(Request(url, headers=headers), timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def discover(query: str, *, timeout: float = 30) -> dict[str, str]:
    page = fetch_text(SEARCH_URL.format(quote(query)), timeout=timeout)
    found: dict[str, str] = {}
    for match in re.finditer(r'cr-params="([^"]+)"', page):
        params = html.unescape(match.group(1))
        gid = re.search(r'"gid"\s*:\s*"?(\d{18,20})', params)
        title = re.search(r'"title"\s*:\s*"([^"]*)', params)
        if gid:
            found[gid.group(1)] = html.unescape(title.group(1)) if title else ""
    for match in re.finditer(r'\\?"gid\\?"\s*:\s*(\d{18,20})', page):
        found.setdefault(match.group(1), "")
    return found


def comment_endpoint(gid: str, offset: int, count: int) -> str:
    query = urlencode({
        "aid": 24,
        "app_name": "toutiao_web",
        "group_id": gid,
        "item_id": gid,
        "offset": offset,
        "count": count,
    })
    return COMMENT_URL.format(query)


def iter_comments(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in payload.get("data") or []:
        comment = item.get("comment") if isinstance(item, dict) else None
        if isinstance(comment, dict) and str(comment.get("text") or "").strip():
            rows.append(comment)
    return rows


def parse_time(value: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), tz=CHINA_TZ)
    except (TypeError, ValueError, OSError):
        return None


def parse_bound(value: str, *, end: bool = False) -> datetime:
    text = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        text += " 23:59:59" if end else " 00:00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=CHINA_TZ)
    return parsed.astimezone(CHINA_TZ)


def run(args: argparse.Namespace) -> dict[str, Any]:
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    provenance: dict[str, set[str]] = defaultdict(set)
    titles: dict[str, str] = {}
    search_audit = []
    for query in args.query:
        try:
            items = discover(query)
            search_audit.append({"query": query, "ids": len(items), "error": ""})
            for gid, title in items.items():
                provenance[gid].add(query)
                if title:
                    titles[gid] = title
        except Exception as exc:
            search_audit.append({"query": query, "ids": 0, "error": str(exc)})
        time.sleep(args.delay)

    start = parse_bound(args.start)
    end = parse_bound(args.end, end=True)
    article_rows = []
    comments = []
    for gid in sorted(provenance):
        referer = f"https://www.toutiao.com/article/{gid}/"
        try:
            payload = json.loads(fetch_text(comment_endpoint(gid, 0, args.page_size), referer))
            exposed = iter_comments(payload)
            in_window = []
            for comment in exposed:
                created = parse_time(comment.get("create_time"))
                if created and start <= created <= end:
                    in_window.append(comment)
                    comments.append({
                        "comment_id": str(comment.get("id_str") or comment.get("id") or ""),
                        "content": str(comment.get("text") or "").strip(),
                        "published_at": created.isoformat(),
                        "platform": "今日头条",
                        "article_id": gid,
                        "article_title": titles.get(gid, ""),
                        "article_url": referer,
                        "source": str(comment.get("user_name") or ""),
                        "likes": comment.get("digg_count", ""),
                        "discovered_by_queries": sorted(provenance[gid]),
                    })
            article_rows.append({
                "article_id": gid,
                "title": titles.get(gid, ""),
                "url": referer,
                "queries": sorted(provenance[gid]),
                "api_total": int(payload.get("total_number") or 0),
                "exposed": len(exposed),
                "in_window": len(in_window),
                "error": "",
            })
        except Exception as exc:
            article_rows.append({
                "article_id": gid, "title": titles.get(gid, ""), "url": referer,
                "queries": sorted(provenance[gid]), "api_total": 0, "exposed": 0,
                "in_window": 0, "error": str(exc),
            })
        time.sleep(args.delay)

    unique = {row["comment_id"]: row for row in comments if row["comment_id"]}
    audit = {
        "policy": "境内公开、无需登录；搜索摘要和文章正文不计作评论",
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "searches": search_audit,
        "articles_discovered": len(article_rows),
        "articles_with_comments": sum(row["in_window"] > 0 for row in article_rows),
        "comments_in_window": len(unique),
        "articles": sorted(article_rows, key=lambda row: (-row["in_window"], row["article_id"])),
    }
    (out_dir / "toutiao_search_comment_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "toutiao_search_comments.json").write_text(
        json.dumps(sorted(unique.values(), key=lambda row: (row["published_at"], row["comment_id"])), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", action="append", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--delay", type=float, default=0.25)
    args = parser.parse_args()
    audit = run(args)
    print(json.dumps({
        "articles_discovered": audit["articles_discovered"],
        "articles_with_comments": audit["articles_with_comments"],
        "comments_in_window": audit["comments_in_window"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
