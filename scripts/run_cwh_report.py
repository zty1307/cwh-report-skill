from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import shlex
import subprocess
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_DATE = "2026-06-29"
DEFAULT_TOPICS = [
    "听取人工智能发展情况汇报",
    "研究当前外贸形势和贸易强国建设有关工作",
    "审议通过《“十五五”碳达峰行动方案》",
    "审议通过《国民健康“十五五”规划》",
]

KEYWORD_RULES = {
    "人工智能": ["人工智能", "AI", "算力", "大模型", "算法", "数据安全", "应用场景"],
    "外贸": ["外贸", "稳外贸", "贸易强国", "出口", "跨境电商", "数字贸易"],
    "贸易强国": ["贸易强国", "外贸", "数字贸易", "跨境电商", "出口"],
    "碳": ["碳达峰", "双碳", "碳排放", "绿色低碳", "碳核算", "节能改造"],
    "健康": ["国民健康", "医疗服务", "医保", "基层医疗", "健康产业", "老龄化"],
    "十五五": ["十五五", "规划", "高质量发展", "产业布局"],
}

OPENCLI_COLLECTORS = [
    ("bilibili", ["opencli.cmd", "bilibili", "search", "{query}", "-f", "yaml"], "self_media_video"),
    ("xiaohongshu", ["opencli.cmd", "xiaohongshu", "search", "{query}", "-f", "yaml"], "social_note"),
    ("weibo", ["opencli.cmd", "weibo", "search", "{query}", "-f", "yaml"], "netizen_comment"),
    ("weixin", ["opencli.cmd", "weixin", "search", "{query}", "-f", "yaml"], "self_media_article"),
    ("web", ["opencli.cmd", "web", "search", "{query}", "-f", "yaml"], "media"),
]


def normalize_date(text: str) -> str:
    match = re.search(r"(\d{1,2})月(\d{1,2})日", text)
    if not match:
        return DEFAULT_DATE
    return f"2026-{int(match.group(1)):02d}-{int(match.group(2)):02d}"


def infer_topics(text: str) -> list[str]:
    compact = re.sub(r"\s+", "", text or "")
    topics: list[str] = []
    for marker, topic in [
        ("人工智能", DEFAULT_TOPICS[0]),
        ("外贸", DEFAULT_TOPICS[1]),
        ("贸易强国", DEFAULT_TOPICS[1]),
        ("碳达峰", DEFAULT_TOPICS[2]),
        ("国民健康", DEFAULT_TOPICS[3]),
    ]:
        if marker in compact and topic not in topics:
            topics.append(topic)
    if topics:
        return topics
    chunks = [x.strip(" -、\t") for x in re.split(r"[；;。\n,，]+", text or "")]
    chunks = [x for x in chunks if len(x) >= 4 and "请帮" not in x]
    return chunks or DEFAULT_TOPICS[:]


def keywords_for(topic: str) -> list[str]:
    words: list[str] = []
    for marker, values in KEYWORD_RULES.items():
        if marker in topic:
            words.extend(values)
    return list(dict.fromkeys(words or [topic]))


def decode_bytes(data: bytes) -> str:
    for enc in ("utf-8", "gb18030", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def run_command(args: list[str], timeout: int = 35) -> tuple[bool, str]:
    try:
        proc = subprocess.run(args, capture_output=True, timeout=timeout, check=False)
    except FileNotFoundError:
        return False, f"command not found: {args[0]}"
    except subprocess.TimeoutExpired:
        return False, f"command timed out after {timeout}s: {' '.join(args[:3])}"
    except Exception as exc:
        return False, str(exc)
    output = decode_bytes(proc.stdout or b"")
    if proc.stderr:
        output += "\n" + decode_bytes(proc.stderr)
    return proc.returncode == 0, output.strip()


def parse_yaml_like(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("(") or line.startswith("Update available"):
            continue
        if line.startswith("- "):
            if current:
                rows.append(current)
            current = {}
            line = line[2:].strip()
        match = re.match(r"([A-Za-z_]+):\s*(.*)", line)
        if match:
            current[match.group(1)] = match.group(2).strip().strip("'\"")
    if current:
        rows.append(current)
    return rows


def normalize_sample(topic: str, platform: str, row: dict[str, Any], default_source_type: str) -> dict[str, Any] | None:
    title = str(row.get("title") or row.get("desc") or row.get("content") or row.get("text") or "")
    content = str(row.get("content") or row.get("desc") or row.get("text") or title)
    if not title and not content:
        return None
    spread_raw = row.get("spread_count") or row.get("score") or row.get("play") or row.get("likes") or row.get("like_count") or row.get("read_count") or 0
    try:
        spread = int(str(spread_raw).replace(",", ""))
    except ValueError:
        spread = 0
    return {
        "topic": row.get("topic") or topic,
        "platform": row.get("platform") or platform,
        "source_type": row.get("source_type") or default_source_type,
        "source": row.get("source") or row.get("author") or row.get("nickname") or row.get("site") or platform,
        "title": title or content[:60],
        "content": content,
        "url": row.get("url") or row.get("link") or "",
        "spread_count": spread,
        "sentiment": row.get("sentiment") or "unknown",
        "sentiment_source": row.get("sentiment_source") or "unprocessed",
        "is_comment": row.get("is_comment") or ("true" if default_source_type in {"netizen_comment", "social_note"} else "false"),
        "confidence": row.get("confidence") or "auto-collected",
    }


def collect_opencli(topics: list[str], per_topic: int, platforms: set[str]) -> tuple[list[dict[str, Any]], list[str]]:
    samples: list[dict[str, Any]] = []
    errors: list[str] = []
    for topic in topics:
        query = f"国务院常务会 {topic}"
        for platform, command_template, source_type in OPENCLI_COLLECTORS:
            if platforms and platform not in platforms:
                continue
            command = [part.format(query=query) for part in command_template]
            ok, output = run_command(command, timeout=45)
            if not ok:
                errors.append(f"opencli/{platform}: {output[:300]}")
                continue
            rows = parse_yaml_like(output)
            count_before = len(samples)
            for row in rows[:per_topic]:
                sample = normalize_sample(topic, platform, row, source_type)
                if sample:
                    samples.append(sample)
            if len(samples) == count_before:
                errors.append(f"opencli/{platform}: returned no parseable rows")
    return samples, errors


def collect_mediacrawler(topics: list[str], per_topic: int) -> tuple[list[dict[str, Any]], list[str]]:
    template = os.getenv("CWH_MEDIACRAWLER_COMMAND", "").strip()
    if not template:
        return [], ["MediaCrawler未配置：设置 CWH_MEDIACRAWLER_COMMAND，例如 python D:/MediaCrawler/cwh_collect.py --query {query} --json"]
    samples: list[dict[str, Any]] = []
    errors: list[str] = []
    for topic in topics:
        query = f"国务院常务会 {topic}"
        command = [part.format(query=query) for part in shlex.split(template)]
        ok, output = run_command(command, timeout=180)
        if not ok:
            errors.append(f"mediacrawler: {output[:500]}")
            continue
        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            errors.append("mediacrawler: command did not return JSON")
            continue
        rows = data if isinstance(data, list) else data.get("samples", []) if isinstance(data, dict) else []
        for row in rows[:per_topic]:
            if isinstance(row, dict):
                sample = normalize_sample(topic, str(row.get("platform") or "mediacrawler"), row, str(row.get("source_type") or "media"))
                if sample:
                    samples.append(sample)
    return samples, errors


def collect_agent_reach_health() -> list[str]:
    ok, output = run_command(["agent-reach.exe", "doctor", "--json"], timeout=20)
    if not ok:
        return [f"agent-reach doctor未通过：{output[:400]}"]
    return ["agent-reach doctor已执行；平台实际采集由 opencli/MediaCrawler 适配器承接。"]


def collect_live(topics: list[str], per_topic: int, collectors: set[str], platforms: set[str]) -> tuple[list[dict[str, Any]], list[str]]:
    samples: list[dict[str, Any]] = []
    gaps: list[str] = []
    if "agent-reach" in collectors or "all" in collectors:
        gaps.extend(collect_agent_reach_health())
    if "mediacrawler" in collectors or "all" in collectors:
        rows, errs = collect_mediacrawler(topics, per_topic)
        samples.extend(rows)
        gaps.extend(errs)
    if "opencli" in collectors or "all" in collectors:
        rows, errs = collect_opencli(topics, per_topic, platforms)
        samples.extend(rows)
        gaps.extend(errs)
    return samples, gaps


def read_samples(path: str | None, topics: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    if not path:
        return [], []
    p = Path(path)
    if not p.exists():
        return [], [f"sample file not found: {path}"]
    rows: list[dict[str, Any]] = []
    if p.suffix.lower() == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        rows = data if isinstance(data, list) else data.get("samples", [])
    else:
        with p.open("r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
    out: list[dict[str, Any]] = []
    for row in rows:
        text = str(row.get("topic") or "") + " " + str(row.get("title") or "") + " " + str(row.get("content") or "")
        topic = row.get("topic") or match_topic(text, topics)
        sample = normalize_sample(topic, str(row.get("platform") or "imported"), row, str(row.get("source_type") or "unknown"))
        if sample:
            out.append(sample)
    return out, []


def match_topic(text: str, topics: list[str]) -> str:
    for topic in topics:
        for word in keywords_for(topic):
            if word and word in text:
                return topic
    return topics[0] if topics else "未归类"


def classify_counts(samples: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"domestic_media": 0, "self_media": 0, "comments": 0, "overseas": 0}
    for item in samples:
        source_type = str(item.get("source_type") or "")
        platform = str(item.get("platform") or "")
        if platform in {"x", "twitter", "youtube", "reddit", "overseas", "foreign_media"}:
            counts["overseas"] += 1
        elif str(item.get("is_comment", "")).lower() == "true" or source_type in {"comment", "netizen_comment", "social_note"}:
            counts["comments"] += 1
        elif source_type in {"media", "official_media", "news", "central_media", "mainstream_media", "commercial_media"}:
            counts["domestic_media"] += 1
        else:
            counts["self_media"] += 1
    return counts


def top_items(items: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    return sorted(items, key=lambda x: int(x.get("spread_count") or 0), reverse=True)[:limit]


def format_sample(item: dict[str, Any]) -> str:
    source = item.get("source") or item.get("platform") or "未知来源"
    title = item.get("title") or item.get("content") or "未命名样本"
    spread = int(item.get("spread_count") or 0)
    url = item.get("url") or ""
    parts = [f"{source}《{title}》"]
    if spread:
        parts.append(f"传播量/热度约 {spread}")
    if url:
        parts.append(f"链接：{url}")
    return "，".join(parts)


def sentiment_line(items: list[dict[str, Any]]) -> str:
    if not items:
        return "暂无可判定样本；需待评论或原始样本接入后复核。"
    counts = Counter(str(x.get("sentiment") or "unknown") for x in items)
    return f"正面 {counts.get('positive', 0)} 条、中性 {counts.get('neutral', 0)} 条、负面 {counts.get('negative', 0)} 条、未判定 {counts.get('unknown', 0)} 条。"


def build_report(meeting_date: str, topics: list[str], samples: list[dict[str, Any]], gaps: list[str]) -> str:
    by_platform = Counter(str(x.get("platform") or "unknown") for x in samples)
    counts = classify_counts(samples)
    total_spread = sum(int(x.get("spread_count") or 0) for x in samples)
    platform_text = "、".join(f"{k} {v}条" for k, v in by_platform.items()) or "当前未返回平台样本"
    lines = [
        f"# {meeting_date} 国务院常务会舆情情况报告草稿",
        "",
        "## 一、整体传播情况",
        f"会议议题：{'；'.join(topics)}。",
        f"传播数据：当前自动流程整理样本 {len(samples)} 条，累计可读传播量/热度约 {total_spread}。",
        f"- 境内媒体：{counts['domestic_media']} 条。",
        f"- 新媒体/自媒体：{counts['self_media']} 条。",
        f"- 网民评论：{counts['comments']} 条。",
        f"- 境外媒体：{counts['overseas']} 条。",
        f"- 平台分布：{platform_text}。",
        "- 传播量变化：demo 已输出图表数据结构；正式接入需使用系统分时序列生成固定样式走势线。",
        "",
        "## 二、子议题传播情况",
    ]
    for topic in topics:
        topic_samples = [x for x in samples if x.get("topic") == topic]
        media_like = [x for x in topic_samples if str(x.get("is_comment", "")).lower() != "true" and str(x.get("source_type")) not in {"comment", "netizen_comment", "social_note"}]
        comments = [x for x in topic_samples if str(x.get("is_comment", "")).lower() == "true" or str(x.get("source_type")) in {"comment", "netizen_comment", "social_note"}]
        lines.extend([
            f"### {topic}",
            f"传播情况：自动归集相关样本 {len(topic_samples)} 条，其中媒体/自媒体 {len(media_like)} 条、网民评论 {len(comments)} 条。",
            "媒体观点：" + ("；".join(format_sample(x) for x in top_items(media_like)) if media_like else "当前未采到规范媒体样本，需接入新闻源、公众号或内部系统数据。"),
            "网民评论：" + ("；".join(format_sample(x) for x in top_items(comments)) if comments else "当前未采到可用评论样本；需接入微博、抖音、小红书、公众号评论等登录态数据。"),
            f"情感倾向：{sentiment_line(topic_samples)}",
            f"候选热词：{'、'.join(keywords_for(topic))}（需人工确认）。",
            "",
        ])
    media_news = [x for x in samples if str(x.get("source_type")) in {"media", "official_media", "news", "central_media", "mainstream_media", "commercial_media"}]
    self_media = [x for x in samples if str(x.get("is_comment", "")).lower() != "true" and str(x.get("source_type")) not in {"media", "official_media", "news", "central_media", "mainstream_media", "commercial_media", "comment", "netizen_comment", "social_note"}]
    comments = [x for x in samples if str(x.get("is_comment", "")).lower() == "true" or str(x.get("source_type")) in {"comment", "netizen_comment", "social_note"}]
    hotwords = "、".join(dict.fromkeys(word for topic in topics for word in keywords_for(topic)))
    lines.extend([
        "## 三、境内媒体及自媒体观点",
        "媒体观点：" + ("；".join(format_sample(x) for x in top_items(media_news, 5)) if media_news else "当前未接入境内主流新闻源样本。"),
        "自媒体观点：" + ("；".join(format_sample(x) for x in top_items(self_media, 8)) if self_media else "当前未返回自媒体样本或仅有低相关样本。"),
        "",
        "## 四、网民评论情况",
        "评论汇总：" + ("；".join(format_sample(x) for x in top_items(comments, 8)) if comments else "当前未采到可用评论样本；正式流程需把评论采集作为重点补齐。"),
        f"情感倾向：{sentiment_line(comments)}",
        "",
        "## 五、候选热词及关注点",
        f"候选热词：{hotwords}（需人工确认）。",
        "关注点：" + "；".join(f"{topic}：{'、'.join(keywords_for(topic)[:4])}" for topic in topics),
        "",
        "## 六、境外关注情况",
        "转载报道：" + ("见样本表 overseas/foreign_media 分类。" if counts["overseas"] else "当前未接入境外媒体源，暂未返回可核验样本。"),
        "一般解读：当前 demo 未形成可核验境外解读样本。",
        "借题炒作：当前 demo 未形成可核验炒作样本；正式报告需人工判别。",
        "",
        "## 七、附录建议与人工审核清单",
        "数据补充：优先接入内部传播总量、公众号文章、评论采集、境外媒体和分时走势数据。",
        "人工审核：",
        "- 校验样本相关性，剔除泛化或误匹配样本。",
        "- 确认候选热词是否适合进入正式报告。",
        "- 对境外关注进行转载报道、一般解读、借题炒作分类。",
        "- 对网民评论保留原始表达，同时复核敏感表述。",
        "- 对媒体观点进行人工归纳，避免仅凭标题下结论。",
    ])
    if gaps:
        lines.append("")
        lines.append("## 采集与接入提示")
        for gap in gaps[:20]:
            lines.append(f"- {gap}")
    return "\n".join(lines) + "\n"


def write_svg(path: Path, platform_counts: dict[str, int]) -> None:
    width = 760
    height = 240
    max_value = max(platform_counts.values(), default=1)
    rows = []
    y = 40
    for name, value in platform_counts.items() or {"无样本": 0}.items():
        bar_w = int((value / max_value) * 520) if max_value else 0
        rows.append(f'<text x="24" y="{y + 18}" font-size="14">{html.escape(name)}</text>')
        rows.append(f'<rect x="140" y="{y}" width="{bar_w}" height="24" fill="#2f6f73"/>')
        rows.append(f'<text x="{150 + bar_w}" y="{y + 18}" font-size="14">{value}</text>')
        y += 44
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="#ffffff"/><text x="24" y="24" font-size="18" font-weight="700">平台样本分布</text>{"".join(rows)}</svg>'
    path.write_text(svg, encoding="utf-8")


def parse_set(value: str) -> set[str]:
    return {x.strip().lower() for x in value.split(",") if x.strip()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a CWH public-opinion report demo.")
    parser.add_argument("--input", default="", help="Meeting agenda or user request text.")
    parser.add_argument("--input-file", help="Read agenda text from a UTF-8 file.")
    parser.add_argument("--samples", help="Optional CSV/JSON raw samples to ingest.")
    parser.add_argument("--out-dir", default="outputs/cwh_report_demo", help="Output directory.")
    parser.add_argument("--no-live", action="store_true", help="Skip live collection adapters.")
    parser.add_argument("--collectors", default="opencli,mediacrawler,agent-reach", help="Comma list: opencli, mediacrawler, agent-reach, all.")
    parser.add_argument("--platforms", default="bilibili,weibo,weixin,web", help="OpenCLI platforms to use; Xiaohongshu is excluded by the current project profile.")
    parser.add_argument("--per-topic", type=int, default=4, help="Maximum live samples per platform per topic.")
    args = parser.parse_args()

    agenda = args.input
    if args.input_file:
        agenda = Path(args.input_file).read_text(encoding="utf-8")
    if not agenda:
        agenda = "；".join(DEFAULT_TOPICS)

    meeting_date = normalize_date(agenda)
    topics = infer_topics(agenda)
    samples, gaps = read_samples(args.samples, topics)
    collectors = parse_set(args.collectors)
    if "all" in collectors:
        collectors = {"all"}
    if not args.no_live:
        live_samples, live_gaps = collect_live(topics, args.per_topic, collectors, parse_set(args.platforms))
        samples.extend(live_samples)
        gaps.extend(live_gaps)
    else:
        gaps.append("已按 --no-live 跳过公开平台采集，仅生成结构化 demo。")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    by_platform = Counter(str(x.get("platform") or "unknown") for x in samples)
    report = build_report(meeting_date, topics, samples, gaps)
    audit = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "meeting_date": meeting_date,
        "topics": topics,
        "keywords": {topic: keywords_for(topic) for topic in topics},
        "collectors": sorted(collectors),
        "statistics": {
            "total_samples": len(samples),
            "total_spread": sum(int(x.get("spread_count") or 0) for x in samples),
            "by_platform": dict(by_platform),
            "by_topic": dict(Counter(str(x.get("topic") or "未归类") for x in samples)),
            "source_counts": classify_counts(samples),
        },
        "samples": samples,
        "collection_gaps": gaps,
        "review_items": [
            "样本相关性复核",
            "候选热词人工确认",
            "境外关注三分类",
            "网民评论原文可用性复核",
            "正式报告语气和敏感表述复核",
        ],
    }
    (out_dir / "cwh_report.md").write_text(report, encoding="utf-8")
    (out_dir / "cwh_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    write_svg(out_dir / "platform_distribution.svg", dict(by_platform))
    print(json.dumps({"status": "ok", "out_dir": str(out_dir), "report": str(out_dir / "cwh_report.md"), "audit": str(out_dir / "cwh_audit.json"), "total_samples": len(samples), "platform_distribution": dict(by_platform), "gaps": len(gaps)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
