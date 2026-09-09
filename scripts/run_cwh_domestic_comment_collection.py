"""Collect traceable domestic-platform comments for the CWH sentiment stage.

MediaSpider Supervisor remains the collection engine.  This wrapper creates
auditable per-topic tasks, enforces a domestic-only platform allowlist, filters
the normalized output to real comment/reply rows inside the monitoring window,
and hands the resulting detail CSV to ``run_cwh_sentiment_stage.py``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DEFAULT_CONFIG = SKILL_DIR / "config" / "domestic_comment_collection.json"
DEFAULT_SUPERVISOR = Path(
    "D:/Codex/2026-06-15/ai-1-1-https-drive-weixin/work/mediaspider-supervisor"
)
DOMESTIC_TIMEZONE = ZoneInfo("Asia/Shanghai")
COMMENT_FIELDS = [
    "评论ID",
    "评论内容",
    "平台",
    "发布时间",
    "原文链接",
    "子议题",
    "来源",
    "点赞量",
    "信息类型",
    "采集来源",
    "原始文件",
    "父原帖标题",
    "父原帖发布时间",
    "父原帖来源",
]
EXCLUDED_FIELDS = COMMENT_FIELDS + ["排除原因", "时间窗状态", "原始来源类型"]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def batch_failure_blockers(batch_payload: dict[str, Any]) -> list[str]:
    """Turn Supervisor task outcomes into concise, actionable audit blockers."""
    blockers: list[str] = []
    for result in batch_payload.get("results") or []:
        if not isinstance(result, dict) or int(result.get("exit_code") or 0) == 0:
            continue
        stdout = str(result.get("stdout") or "")
        stderr = str(result.get("stderr") or "")
        combined = f"{stdout}\n{stderr}".lower()
        task_name = Path(str(result.get("task") or "unknown_task")).stem
        if "login required" in combined or "qrcode" in combined or "cookie may be invalid" in combined:
            reason = "需要有效登录态或扫码登录"
        elif result.get("timed_out"):
            reason = "采集超时"
        elif "captcha" in combined or "risk" in combined or "风控" in combined:
            reason = "触发验证码或平台风控"
        elif "no raw output" in combined:
            reason = "未产生原始数据"
        else:
            reason = f"Supervisor 退出码 {result.get('exit_code')}"
        message = f"任务 {task_name}：{reason}；详见该任务 run.log。"
        if message not in blockers:
            blockers.append(message)
    return blockers


def collection_gate_status(effective_run: bool, batch_returncode: int, accepted_comments: int) -> str:
    if not effective_run:
        return "dry_run_ready" if batch_returncode == 0 else "failed"
    if accepted_comments:
        return "ai_review_required"
    return "blocked_or_empty"


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "_", value).strip("_")
    return cleaned[:36] or "topic"


def canonical_platform(value: Any, config: dict[str, Any]) -> str:
    raw = str(value or "").strip().lower()
    aliases = {str(key).strip().lower(): str(item).strip().lower() for key, item in (config.get("platform_aliases") or {}).items()}
    return aliases.get(raw, raw)


def validate_platforms(values: list[str], config: dict[str, Any]) -> list[str]:
    allowed = {str(item).lower() for item in config.get("allowed_platforms") or []}
    blocked = {str(item).lower() for item in config.get("blocked_platforms") or []}
    result: list[str] = []
    for value in values:
        platform = canonical_platform(value, config)
        if not platform:
            continue
        if platform in blocked:
            raise ValueError(f"平台 {value!r} 已被当前境内评论采集策略明确排除。")
        if platform not in allowed:
            raise ValueError(f"平台 {value!r} 不在境内评论采集白名单中。")
        if platform not in result:
            result.append(platform)
    if not result:
        raise ValueError("至少需要一个境内评论采集平台。")
    return result


def load_scope(research_plan: Path) -> dict[str, Any]:
    plan = load_json(research_plan)
    period = plan.get("monitoring_period") or {}
    topics: list[dict[str, Any]] = []
    for index, item in enumerate(plan.get("topics") or [], start=1):
        if not isinstance(item, dict):
            continue
        title = str(item.get("topic") or item.get("title") or "").strip()
        if not title:
            continue
        queries = item.get("queries") or {}
        public_queries = queries.get("public_discussion") or []
        topics.append(
            {
                "index": index,
                "title": title,
                "aliases": [str(value).strip() for value in item.get("aliases") or [] if str(value).strip()],
                "public_queries": [str(value).strip() for value in public_queries if str(value).strip()],
            }
        )
    if not topics:
        raise ValueError("research_plan.json 中没有可用议题。")
    start = str(period.get("start") or "").strip()
    end = str(period.get("end") or "").strip()
    if not start or not end:
        raise ValueError("research_plan.json 缺少 monitoring_period.start/end。")
    return {
        "agenda": str((plan.get("input_contract") or {}).get("agenda") or "").strip(),
        "start": start,
        "end": end,
        "topics": topics,
    }


def han_length(value: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", value))


def clean_agenda_core(value: str) -> str:
    """Remove meeting procedure language while retaining the policy/event object."""
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"^20\d{2}[-/.年]\d{1,2}(?:[-/.月]\d{1,2}日?)?\s*", "", text)
    text = re.sub(r"(?:网友评论|网友\s*评论|大家怎么看|媒体评论|专家解读|公众号解读|自媒体观点)$", "", text)
    text = re.sub(r"^(?:国务院常务会议|国常会)\s*", "", text)
    text = re.sub(
        r"^(?:学习贯彻|传达学习|听取|研究部署|研究|审议通过|决定核准|决定|部署|审议)+",
        "",
        text,
    )
    text = re.sub(r"^(?:习近平总书记|国务院)(?:关于)?\s*", "", text)
    text = re.sub(r"[（(](?:草案|征求意见稿|修订草案)[）)]", "", text)
    text = re.sub(
        r"(?:建设情况汇报|情况汇报|实施有关工作|推进有关工作|有关工作|的重要讲话精神|的决定)$",
        "",
        text,
    )
    text = re.sub(r"等[一二三四五六七八九十百0-9]+个", " ", text)
    text = re.sub(r"(?:和|以及)做好", " ", text)
    text = re.sub(r"(?<=[\u4e00-\u9fff])(?:、|，|；|及|以及|和)(?=[\u4e00-\u9fff])", " ", text)
    text = re.sub(r"[《》〈〉“”\"'：:（）()]", " ", text)
    text = re.sub(r"\b做好\b", "", text)
    return re.sub(r"\s+", " ", text).strip()


def quoted_policy_objects(value: str) -> list[str]:
    """Prefer the deepest quoted regulation or document title when present."""
    matches = re.findall(r"[《〈]([^《》〈〉]{2,32})[》〉]", str(value or ""))
    output: list[str] = []
    for match in reversed(matches):
        cleaned = clean_agenda_core(match)
        if cleaned and cleaned not in output:
            output.append(cleaned)
    return output


def compact_query(value: str, max_han: int = 20) -> str:
    """Keep complete semantic chunks instead of truncating a Chinese sentence."""
    cleaned = clean_agenda_core(value)
    if not cleaned:
        return ""
    chunks = [re.sub(r"^(?:关于|做好|部分)", "", item) for item in cleaned.split()]
    chunks = [item for item in chunks if item]
    selected: list[str] = []
    for chunk in chunks:
        candidate = " ".join([*selected, chunk])
        if han_length(candidate) <= max_han:
            selected.append(chunk)
        elif not selected:
            # A single named policy object may legitimately be long; do not cut it mid-name.
            selected.append(chunk)
            break
    return " ".join(selected).strip()


def keyword_candidates(scope: dict[str, Any], topic: dict[str, Any]) -> list[str]:
    """Build short platform-search queries from a general CWH agenda title."""
    del scope  # The agenda date is deliberately not baked into reusable search terms.
    title = str(topic["title"])
    semantic_objects = quoted_policy_objects(title)
    semantic_objects.extend(
        compact_query(value)
        for value in [title, *(topic.get("aliases") or []), *(topic.get("public_queries") or [])]
    )

    cores: list[str] = []
    for value in semantic_objects:
        core = compact_query(value)
        if core and core not in cores:
            cores.append(core)

    output: list[str] = []
    for core in cores:
        for candidate in (f"国常会 {core}", core):
            if han_length(candidate) <= 24 and candidate not in output:
                output.append(candidate)
            if len(output) >= 2:
                return output
    return output


def create_tasks(
    scope: dict[str, Any],
    output_dir: Path,
    platforms: list[str],
    profile: dict[str, Any],
    media_home: str,
) -> dict[str, Any]:
    task_dir = output_dir / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    tasks = []
    for topic in scope["topics"]:
        for platform in platforms:
            task = {
                "collector": "domestic",
                "platform": platform,
                "crawler_type": "search",
                "login_type": "qrcode",
                "keywords": keyword_candidates(scope, topic),
                "get_comment": True,
                "get_sub_comment": bool(profile.get("get_sub_comment", False)),
                "max_posts": int(profile["max_posts"]),
                "max_comments_per_post": int(profile["max_comments_per_post"]),
                "max_concurrency": 1,
                "save_data_option": "jsonl",
                "headless": False,
                "cwh_topic": topic["title"],
                "cwh_topic_index": topic["index"],
                "cwh_topic_aliases": topic.get("aliases") or [],
                "cwh_monitoring_start": scope["start"],
                "cwh_monitoring_end": scope["end"],
                "cwh_collection_scope": "domestic_public_comments_only",
                "cwh_excluded_platforms": ["xhs", "tieba", "foreign"],
            }
            if media_home:
                task["mediaspider_home"] = media_home
            path = task_dir / f"{topic['index']:02d}_{platform}_{safe_name(topic['title'])}.json"
            write_json(path, task)
            tasks.append(
                {
                    "topic": topic["title"],
                    "topic_index": topic["index"],
                    "platform": platform,
                    "path": str(path),
                    "keywords": task["keywords"],
                }
            )
    manifest = {
        "schema_version": "1.0",
        "collector": "mediaspider-supervisor",
        "scope": "domestic_public_comments_only",
        "monitoring_period": {"start": scope["start"], "end": scope["end"]},
        "platforms": platforms,
        "excluded_platforms": ["xhs", "tieba", "foreign"],
        "topics": [item["title"] for item in scope["topics"]],
        "tasks": tasks,
    }
    manifest_path = task_dir / "manifest.json"
    write_json(manifest_path, manifest)
    return {"manifest": manifest_path, "task_dir": task_dir, "payload": manifest}


def parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if re.fullmatch(r"\d+(?:\.\d+)?", raw):
        number = float(raw)
        if number > 10_000_000_000:
            number /= 1000
        try:
            return datetime.fromtimestamp(number, tz=DOMESTIC_TIMEZONE)
        except (OverflowError, OSError, ValueError):
            return None
    normalized = raw.replace("年", "-").replace("月", "-").replace("日", " ").strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        parsed = None
    if parsed is None:
        for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(normalized, pattern)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=DOMESTIC_TIMEZONE)
    return parsed.astimezone(DOMESTIC_TIMEZONE)


def period_bounds(start: str, end: str) -> tuple[datetime, datetime]:
    start_dt = parse_datetime(start)
    end_dt = parse_datetime(end)
    if start_dt is None or end_dt is None:
        raise ValueError("监测起止时间无法解析。")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(start).strip()):
        start_dt = datetime.combine(start_dt.date(), time.min, tzinfo=DOMESTIC_TIMEZONE)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(end).strip()):
        end_dt = datetime.combine(end_dt.date() + timedelta(days=1), time.min, tzinfo=DOMESTIC_TIMEZONE)
    else:
        end_dt += timedelta(microseconds=1)
    if end_dt <= start_dt:
        raise ValueError("监测结束时间必须晚于开始时间。")
    return start_dt, end_dt


def window_status(value: Any, start_dt: datetime, end_dt: datetime) -> str:
    parsed = parse_datetime(value)
    if parsed is None:
        return "undated"
    if parsed < start_dt:
        return "before_window"
    if parsed >= end_dt:
        return "after_window"
    return "in_window"


def comment_identifier(sample: dict[str, Any]) -> str:
    explicit = str(sample.get("comment_id") or sample.get("raw_id") or "").strip()
    if explicit:
        return explicit
    payload = "|".join(
        str(sample.get(field) or "").strip()
        for field in ("platform", "raw_file", "published_at", "url", "content")
    )
    return "derived-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def as_comment_row(sample: dict[str, Any], comment_id: str) -> dict[str, Any]:
    return {
        "评论ID": comment_id,
        "评论内容": str(sample.get("content") or "").strip(),
        "平台": str(sample.get("platform") or "").strip(),
        "发布时间": str(sample.get("published_at") or "").strip(),
        "原文链接": str(sample.get("url") or "").strip(),
        "子议题": str(sample.get("topic") or "").strip(),
        "来源": str(sample.get("source") or "").strip(),
        "点赞量": sample.get("like_count") or sample.get("spread_count") or 0,
        "信息类型": "评论",
        "采集来源": "MediaSpider Supervisor",
        "原始文件": str(sample.get("raw_file") or "").strip(),
        "父原帖标题": str(sample.get("parent_post_title") or "").strip(),
        "父原帖发布时间": str(sample.get("parent_post_published_at") or "").strip(),
        "父原帖来源": str(sample.get("parent_post_source") or "").strip(),
    }


def canonical_post_url(value: Any) -> str:
    return re.sub(r"[/?#]+$", "", str(value or "").strip().lower())


def attach_parent_post_context(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Join comments to collected parent posts so AI review can judge event relevance."""
    posts: dict[tuple[str, str], dict[str, Any]] = {}
    for sample in samples:
        source_type = str(sample.get("source_type") or "").lower()
        is_comment = source_type == "netizen_comment" or str(sample.get("is_comment") or "").lower() in {"true", "1", "yes"}
        key = (str(sample.get("platform") or "").lower(), canonical_post_url(sample.get("url")))
        if not is_comment and key[1]:
            posts[key] = sample

    output: list[dict[str, Any]] = []
    for sample in samples:
        enriched = dict(sample)
        key = (str(sample.get("platform") or "").lower(), canonical_post_url(sample.get("url")))
        parent = posts.get(key)
        if parent and (str(sample.get("source_type") or "").lower() == "netizen_comment" or str(sample.get("is_comment") or "").lower() in {"true", "1", "yes"}):
            enriched["parent_post_title"] = str(parent.get("title") or parent.get("content") or "").strip()
            enriched["parent_post_published_at"] = str(parent.get("published_at") or "").strip()
            enriched["parent_post_source"] = str(parent.get("source") or "").strip()
        output.append(enriched)
    return output


def normalize_comment_samples(
    samples: list[dict[str, Any]],
    config: dict[str, Any],
    platforms: list[str],
    start: str,
    end: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    start_dt, end_dt = period_bounds(start, end)
    allowed = set(platforms)
    blocked = {str(item).lower() for item in config.get("blocked_platforms") or []}
    accepted_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    excluded: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()

    for sample in samples:
        platform = canonical_platform(sample.get("platform"), config)
        sample = dict(sample)
        sample["platform"] = platform
        comment_id = comment_identifier(sample)
        row = as_comment_row(sample, comment_id)
        status = window_status(sample.get("published_at"), start_dt, end_dt)
        reason = ""
        if platform in blocked or platform not in allowed:
            reason = "platform_not_allowed"
        elif str(sample.get("region") or "domestic").lower() != "domestic":
            reason = "non_domestic"
        elif str(sample.get("source_type") or "").lower() != "netizen_comment" and str(sample.get("is_comment") or "").lower() not in {"true", "1", "yes"}:
            reason = "not_comment_or_reply"
        elif not row["评论内容"]:
            reason = "blank_comment_text"
        elif not row["子议题"] or row["子议题"].lower() == "unclassified":
            reason = "unclassified_topic"
        elif row["父原帖发布时间"] and window_status(row["父原帖发布时间"], start_dt, end_dt) == "before_window":
            reason = "parent_post_before_window"
        elif status != "in_window":
            reason = status

        if reason:
            excluded_row = dict(row)
            excluded_row.update(
                {
                    "排除原因": reason,
                    "时间窗状态": status,
                    "原始来源类型": str(sample.get("source_type") or ""),
                }
            )
            excluded.append(excluded_row)
            reasons[reason] += 1
            continue

        key = (platform, comment_id)
        existing = accepted_by_key.get(key)
        if existing:
            topics = [item for item in existing["子议题"].split("||") if item]
            if row["子议题"] not in topics:
                topics.append(row["子议题"])
                existing["子议题"] = "||".join(topics)
            reasons["duplicate_comment_id_merged"] += 1
        else:
            accepted_by_key[key] = row

    accepted = sorted(
        accepted_by_key.values(),
        key=lambda row: (row["子议题"], row["平台"], row["发布时间"], row["评论ID"]),
    )
    audit = {
        "samples_seen": len(samples),
        "accepted_comments": len(accepted),
        "excluded_rows": len(excluded),
        "reason_counts": dict(sorted(reasons.items())),
        "by_platform": dict(sorted(Counter(row["平台"] for row in accepted).items())),
        "by_topic": dict(sorted(Counter(row["子议题"] for row in accepted).items())),
        "monitoring_period": {"start": start, "end": end},
    }
    return accepted, excluded, audit


def run_command(command: list[str], *, stream: bool = False) -> subprocess.CompletedProcess[str]:
    if stream:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        lines: list[str] = []
        if process.stdout is not None:
            for line in iter(process.stdout.readline, ""):
                lines.append(line)
                print(line, end="", flush=True)
            process.stdout.close()
        returncode = process.wait()
        return subprocess.CompletedProcess(command, returncode, "".join(lines), "")
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect domestic public comments for CWH sentiment analysis via MediaSpider Supervisor.")
    parser.add_argument("--research-plan", required=True, type=Path)
    parser.add_argument("--monitoring-start", default="", help="Optional exact monitoring-window start override, e.g. 2026-07-10 19:00:00+08:00.")
    parser.add_argument("--monitoring-end", default="", help="Optional exact monitoring-window end override, e.g. 2026-07-13 13:30:00+08:00.")
    parser.add_argument("--system-workbook", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--platforms", default="", help="Comma list from wb,dy,ks,bili,zhihu. Empty uses the configured trial platforms; xhs, tieba and foreign platforms are rejected.")
    parser.add_argument("--profile", choices=["trial", "formal", "deep"], default="trial")
    parser.add_argument("--max-posts", type=int, default=0)
    parser.add_argument("--max-comments-per-post", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0, help="Maximum platform/topic tasks for an explicit trial; 0 (the default) runs all generated tasks.")
    parser.add_argument("--supervisor", type=Path, default=DEFAULT_SUPERVISOR)
    parser.add_argument("--media-home", default="")
    parser.add_argument("--task-timeout-sec", type=int, default=300)
    parser.add_argument("--keep-proxy", action="store_true")
    parser.add_argument("--run", action="store_true", help="Run real collection. Default only validates generated Supervisor commands.")
    parser.add_argument("--reuse-run-dir", action="append", default=[], help="Existing Supervisor run directory to ingest; may be repeated.")
    parser.add_argument("--reuse-only", action="store_true", help="Skip collection and only normalize the supplied --reuse-run-dir outputs.")
    parser.add_argument("--run-preparation", action="store_true", help="Run the large-scale sentiment preparation stage when comments are collected.")
    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.reuse_only and not args.reuse_run_dir:
        raise ValueError("--reuse-only requires at least one --reuse-run-dir.")
    config = load_json(Path(args.config).resolve())
    scope = load_scope(Path(args.research_plan).resolve())
    if str(args.monitoring_start or "").strip():
        scope["start"] = str(args.monitoring_start).strip()
    if str(args.monitoring_end or "").strip():
        scope["end"] = str(args.monitoring_end).strip()
    period_bounds(scope["start"], scope["end"])
    raw_platforms = [item.strip() for item in str(args.platforms or "").split(",") if item.strip()]
    if not raw_platforms:
        raw_platforms = [str(item) for item in config.get("default_trial_platforms") or []]
    platforms = validate_platforms(raw_platforms, config)
    profile = dict((config.get("profiles") or {}).get(args.profile) or {})
    if not profile:
        raise ValueError(f"配置中不存在采集档位 {args.profile!r}。")
    if args.max_posts:
        profile["max_posts"] = args.max_posts
    if args.max_comments_per_post:
        profile["max_comments_per_post"] = args.max_comments_per_post

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    task_package = create_tasks(scope, output_dir, platforms, profile, args.media_home)
    collection_enabled = bool(args.run and not args.reuse_only)
    effective_run = bool(collection_enabled or args.reuse_only)
    batch_output = output_dir / ("batch_run.json" if collection_enabled else "batch_reuse.json" if args.reuse_only else "batch_dry_run.json")
    batch_command = [
        sys.executable,
        str(SCRIPT_DIR / "run_mediacrawler_batch.py"),
        "--manifest",
        str(task_package["manifest"]),
        "--supervisor",
        str(Path(args.supervisor).resolve()),
        "--platforms",
        ",".join(platforms),
        "--limit",
        str(args.limit),
        "--task-timeout-sec",
        str(args.task_timeout_sec),
        "--out",
        str(batch_output),
    ]
    if args.media_home:
        batch_command.extend(["--media-home", args.media_home])
    if args.keep_proxy:
        batch_command.append("--keep-proxy")
    if collection_enabled:
        batch_command.append("--run")
    if args.reuse_only:
        write_json(batch_output, {"dry_run": False, "selected_count": 0, "reuse_only": True, "results": []})
        batch_result = subprocess.CompletedProcess(batch_command, 0, "reuse-only: collection skipped", "")
    else:
        batch_result = run_command(batch_command, stream=collection_enabled)

    comment_path = output_dir / "境内公开评论明细.csv"
    excluded_path = output_dir / "境内评论排除明细.csv"
    normalized_path = output_dir / "mediaspider_normalized_samples.json"
    write_csv(comment_path, [], COMMENT_FIELDS)
    write_csv(excluded_path, [], EXCLUDED_FIELDS)
    normalization: dict[str, Any] = {
        "samples_seen": 0,
        "accepted_comments": 0,
        "excluded_rows": 0,
        "reason_counts": {},
        "by_platform": {},
        "by_topic": {},
        "monitoring_period": {"start": scope["start"], "end": scope["end"]},
    }
    run_dirs: list[str] = []
    batch_payload: dict[str, Any] = {}
    if effective_run and batch_output.exists():
        batch_payload = load_json(batch_output)
        batch_run_dirs = [
            str(item.get("run_dir"))
            for item in batch_payload.get("results") or []
            if item.get("run_dir") and Path(str(item.get("run_dir"))).exists()
        ]
        reuse_run_dirs = [str(Path(item).resolve()) for item in args.reuse_run_dir if Path(item).exists()]
        run_dirs = list(dict.fromkeys([*batch_run_dirs, *reuse_run_dirs]))
        if run_dirs:
            ingest_command = [
                sys.executable,
                str(SCRIPT_DIR / "ingest_mediacrawler_outputs.py"),
                *run_dirs,
                "--output",
                str(normalized_path),
            ]
            ingest_result = run_command(ingest_command)
            if ingest_result.returncode == 0 and normalized_path.exists():
                samples = attach_parent_post_context(load_json(normalized_path).get("samples") or [])
                accepted, excluded, normalization = normalize_comment_samples(
                    [item for item in samples if isinstance(item, dict)],
                    config,
                    platforms,
                    scope["start"],
                    scope["end"],
                )
                write_csv(comment_path, accepted, COMMENT_FIELDS)
                write_csv(excluded_path, excluded, EXCLUDED_FIELDS)

    sentiment_stage: dict[str, Any] = {"status": "not_run"}
    if effective_run:
        sentiment_dir = output_dir / "sentiment_stage"
        sentiment_command = [
            sys.executable,
            str(SCRIPT_DIR / "run_cwh_sentiment_stage.py"),
            "--comment-detail",
            str(comment_path),
            "--output-dir",
            str(sentiment_dir),
        ]
        if args.system_workbook:
            sentiment_command.extend(["--system-workbook", str(Path(args.system_workbook).resolve())])
        if args.run_preparation:
            sentiment_command.append("--run-preparation")
        sentiment_result = run_command(sentiment_command)
        sentiment_stage = {
            "status": "completed" if sentiment_result.returncode == 0 else "failed",
            "returncode": sentiment_result.returncode,
            "stdout": sentiment_result.stdout[-3000:],
            "stderr": sentiment_result.stderr[-3000:],
            "output_dir": str(sentiment_dir),
        }

    blockers: list[str] = []
    if collection_enabled and batch_result.returncode:
        blockers.append("MediaSpider 批次存在失败任务；请检查批次结果和对应 run.log。")
        blockers.extend(batch_failure_blockers(batch_payload))
    if effective_run and not normalization.get("accepted_comments"):
        blockers.append("本轮没有获得监测时段内、可追溯且已归入子议题的境内评论。")
    if effective_run and normalization.get("accepted_comments"):
        blockers.append("已取得候选评论，但尚未完成结合父原帖语境的逐条AI相关性与情感审核；当前结果不得进入正式报告。")
    status = collection_gate_status(
        effective_run,
        batch_result.returncode,
        int(normalization.get("accepted_comments") or 0),
    )
    audit = {
        "schema_version": "1.0",
        "status": status,
        "scope": "domestic_public_comments_only",
        "collector": "MediaSpider Supervisor",
        "platforms": platforms,
        "explicitly_excluded": ["xhs", "tieba", "all_foreign_platforms"],
        "profile": {"name": args.profile, **profile},
        "task_count": len(task_package["payload"]["tasks"]),
        "task_limit": args.limit,
        "mode": "reuse_only" if args.reuse_only else "real_collection" if collection_enabled else "dry_run",
        "batch_command": batch_command,
        "batch_returncode": batch_result.returncode,
        "batch_stdout": batch_result.stdout[-3000:],
        "batch_stderr": batch_result.stderr[-3000:],
        "run_dirs": run_dirs,
        "normalization": normalization,
        "ai_review": {
            "status": "required" if normalization.get("accepted_comments") else "not_applicable",
            "required_context": ["topic", "parent_post_title", "parent_post_published_at", "text"],
            "formal_use_allowed": False,
        },
        "sentiment_stage": sentiment_stage,
        "blockers": blockers,
        "outputs": {
            "manifest": str(task_package["manifest"]),
            "batch_result": str(batch_output),
            "normalized_samples": str(normalized_path),
            "comment_detail": str(comment_path),
            "excluded_detail": str(excluded_path),
        },
    }
    write_json(output_dir / "domestic_comment_collection_audit.json", audit)
    return audit


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    audit = run(build_parser().parse_args())
    print(
        json.dumps(
            {
                "status": audit["status"],
                "platforms": audit["platforms"],
                "accepted_comments": audit["normalization"]["accepted_comments"],
                "audit": str(Path(audit["outputs"]["comment_detail"]).parent / "domestic_comment_collection_audit.json"),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
