"""Collect traceable public comments from Agent Reach-discovered article seeds.

The collector intentionally supports only public, no-login endpoints.  Search is
kept separate from collection: Agent Reach/Exa discovers candidate articles,
then a reviewed seed file fixes the article-to-CWH-topic mapping.  This avoids
turning search snippets or article bodies into fake "comments".
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


CSV_FIELDS = [
    "评论ID", "评论内容", "平台", "发布时间", "原文链接", "子议题", "来源",
    "点赞量", "信息类型", "采集来源", "原始文件", "用户ID", "发布地区",
    "父评论ID", "文章ID", "文章标题",
]
CHINA_TZ = timezone(timedelta(hours=8))


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def article_id(seed: dict[str, Any]) -> str:
    explicit = clean(seed.get("article_id") or seed.get("group_id"))
    if explicit:
        return explicit
    found = re.search(r"/article/(\d+)", clean(seed.get("url")))
    if not found:
        raise ValueError(f"无法从 seed 识别今日头条文章 ID：{seed!r}")
    return found.group(1)


def toutiao_endpoint(group_id: str, offset: int, count: int) -> str:
    query = urlencode(
        {
            "aid": "24",
            "app_name": "toutiao_web",
            "group_id": group_id,
            "item_id": group_id,
            "offset": offset,
            "count": count,
        }
    )
    return f"https://www.toutiao.com/article/v2/tab_comments/?{query}"


def fetch_json(url: str, referer: str, timeout: int = 20) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/138 Safari/537.36",
            "Referer": referer,
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def iter_comment_objects(payload: dict[str, Any]) -> list[tuple[dict[str, Any], str]]:
    """Return top-level comments and publicly exposed replies with parent IDs."""
    found: list[tuple[dict[str, Any], str]] = []

    def add(comment: Any, parent_id: str = "") -> None:
        if not isinstance(comment, dict):
            return
        cid = clean(comment.get("id_str") or comment.get("id"))
        if clean(comment.get("text")) and cid:
            found.append((comment, parent_id))
        for key in ("reply_list", "new_reply_list"):
            replies = comment.get(key) or []
            if isinstance(replies, list):
                for reply in replies:
                    add(reply, cid or parent_id)

    for item in payload.get("data") or []:
        if isinstance(item, dict):
            add(item.get("comment") or item)
    for item in payload.get("stick_comments") or []:
        if isinstance(item, dict):
            add(item.get("comment") or item)

    unique: dict[str, tuple[dict[str, Any], str]] = {}
    for item, parent in found:
        unique.setdefault(clean(item.get("id_str") or item.get("id")), (item, parent))
    return list(unique.values())


def published_at(value: Any) -> str:
    try:
        return datetime.fromtimestamp(int(value), tz=CHINA_TZ).strftime("%Y-%m-%d %H:%M:%S%z")
    except (TypeError, ValueError, OSError):
        return ""


def normalize_comment(comment: dict[str, Any], parent_id: str, seed: dict[str, Any], raw_name: str) -> dict[str, Any]:
    group_id = article_id(seed)
    url = clean(seed.get("url")) or f"https://www.toutiao.com/article/{group_id}/"
    return {
        "评论ID": clean(comment.get("id_str") or comment.get("id")),
        "评论内容": clean(comment.get("text")),
        "平台": "今日头条",
        "发布时间": published_at(comment.get("create_time")),
        "原文链接": url,
        "子议题": clean(seed.get("topic") or seed.get("topic_title")),
        "来源": clean(comment.get("user_name")),
        "点赞量": comment.get("digg_count", ""),
        "信息类型": "评论",
        "采集来源": clean(seed.get("discovery_source")) or "Agent Reach / Exa + 今日头条公开评论接口",
        "原始文件": raw_name,
        "用户ID": clean(comment.get("user_id")),
        "发布地区": clean(comment.get("publish_loc_info")),
        "父评论ID": parent_id,
        "文章ID": group_id,
        "文章标题": clean(seed.get("title")),
    }


def parse_china_datetime(value: str, *, end_of_day: bool = False) -> datetime:
    text = clean(value)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        text += " 23:59:59" if end_of_day else " 00:00:00"
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=CHINA_TZ)
    return parsed.astimezone(CHINA_TZ)


def in_window(row: dict[str, Any], start: str, end: str) -> bool:
    published = clean(row.get("发布时间"))
    if not published:
        return False
    try:
        current = parse_china_datetime(published)
        return parse_china_datetime(start) <= current <= parse_china_datetime(end, end_of_day=True)
    except ValueError:
        return False


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def collect_seed(
    seed: dict[str, Any], raw_dir: Path, page_size: int, max_pages: int, request_delay: float
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if clean(seed.get("platform") or "toutiao").lower() not in {"toutiao", "今日头条"}:
        raise ValueError("当前公开评论适配器仅支持今日头条；其他平台必须单独实现并审计。")
    gid = article_id(seed)
    referer = clean(seed.get("url")) or f"https://www.toutiao.com/article/{gid}/"
    pages: list[dict[str, Any]] = []
    comments: list[tuple[dict[str, Any], str]] = []
    offset = 0
    for page_no in range(1, max_pages + 1):
        payload = fetch_json(toutiao_endpoint(gid, offset, page_size), referer)
        pages.append(payload)
        comments.extend(iter_comment_objects(payload))
        if not payload.get("has_more"):
            break
        next_offset = payload.get("offset")
        offset = int(next_offset) if str(next_offset).isdigit() else offset + page_size
        if request_delay:
            time.sleep(request_delay)

    raw_name = f"toutiao_{gid}.json"
    (raw_dir / raw_name).write_text(json.dumps(pages, ensure_ascii=False, indent=2), encoding="utf-8")
    unique: dict[str, tuple[dict[str, Any], str]] = {}
    for comment, parent in comments:
        unique.setdefault(clean(comment.get("id_str") or comment.get("id")), (comment, parent))
    rows = [normalize_comment(comment, parent, seed, raw_name) for comment, parent in unique.values()]
    return rows, {
        "article_id": gid,
        "title": clean(seed.get("title")),
        "topic": clean(seed.get("topic") or seed.get("topic_title")),
        "url": referer,
        "api_total_number": max([int(page.get("total_number") or 0) for page in pages] or [0]),
        "exposed_unique_comments": len(rows),
        "pages_fetched": len(pages),
        "raw_file": str((raw_dir / raw_name).resolve()),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    seed_path = Path(args.seed_file).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    payload = json.loads(seed_path.read_text(encoding="utf-8-sig"))
    seeds = payload.get("articles") if isinstance(payload, dict) else payload
    if not isinstance(seeds, list) or not seeds:
        raise ValueError("seed 文件必须包含非空 articles 数组。")

    all_rows: list[dict[str, Any]] = []
    article_audits: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for seed in seeds:
        try:
            rows, audit = collect_seed(seed, raw_dir, args.page_size, args.max_pages, args.request_delay)
            all_rows.extend(rows)
            article_audits.append(audit)
        except Exception as exc:
            errors.append({"article": clean(seed.get("url") or seed.get("article_id")), "error": str(exc)})

    unique = {row["评论ID"]: row for row in all_rows if row["评论ID"]}
    rows = sorted(unique.values(), key=lambda item: (item["发布时间"], item["评论ID"]))
    eligible = [row for row in rows if in_window(row, args.start_date, args.end_date)]
    excluded = [dict(row, 排除原因="发布时间不在监测窗口") for row in rows if not in_window(row, args.start_date, args.end_date)]
    output_csv = output_dir / "境内公开评论明细_AgentReach.csv"
    excluded_csv = output_dir / "境内公开评论时间排除明细_AgentReach.csv"
    write_csv(output_csv, eligible)
    with excluded_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        fields = CSV_FIELDS + ["排除原因"]
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(excluded)
    audit = {
        "schema_version": "1.0",
        "status": "completed_with_errors" if errors else "completed",
        "policy": "境内公开、无需登录、不绕过风控；搜索摘要和文章正文不作为评论",
        "monitoring_window": {"start": args.start_date, "end": args.end_date},
        "seed_file": str(seed_path),
        "seed_articles": len(seeds),
        "comments_exposed": len(rows),
        "comments_in_window": len(eligible),
        "comments_outside_window": len(excluded),
        "articles": article_audits,
        "errors": errors,
        "outputs": {"comments": str(output_csv.resolve()), "excluded": str(excluded_csv.resolve()), "raw_dir": str(raw_dir.resolve())},
    }
    (output_dir / "agent_reach_comment_collection_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return audit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect public comments from reviewed Agent Reach article seeds.")
    parser.add_argument("--seed-file", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--start-date", required=True,
        help="Inclusive China time, YYYY-MM-DD or YYYY-MM-DD HH:MM:SS",
    )
    parser.add_argument(
        "--end-date", required=True,
        help="Inclusive China time, YYYY-MM-DD or YYYY-MM-DD HH:MM:SS",
    )
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--request-delay", type=float, default=0.3)
    return parser


def main() -> None:
    audit = run(build_parser().parse_args())
    print(json.dumps({"status": audit["status"], "comments_in_window": audit["comments_in_window"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
