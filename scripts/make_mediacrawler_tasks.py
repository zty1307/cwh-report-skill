from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

DEFAULT_DATE = "2026-06-29"
DEFAULT_TOPICS = [
    "听取人工智能发展情况汇报",
    "研究当前外贸形势和贸易强国建设有关工作",
    "审议通过《“十五五”碳达峰行动方案》",
    "审议通过《国民健康“十五五”规划》",
]
KEYWORD_RULES = {
    "人工智能": ["国务院常务会 人工智能", "人工智能 发展", "AI 发展"],
    "外贸": ["国务院常务会 外贸", "稳外贸", "贸易强国"],
    "贸易强国": ["国务院常务会 贸易强国", "稳外贸", "数字贸易"],
    "碳": ["国务院常务会 碳达峰", "十五五 碳达峰", "双碳"],
    "健康": ["国务院常务会 国民健康", "国民健康 十五五", "健康规划"],
    "十五五": ["十五五 规划"],
}
PLATFORM_DEFAULTS = {
    "xhs": {"max_posts": 15, "max_comments_per_post": 30},
    "dy": {"max_posts": 15, "max_comments_per_post": 20},
    "bili": {"max_posts": 15, "max_comments_per_post": 30},
    "wb": {"max_posts": 20, "max_comments_per_post": 20},
    "zhihu": {"max_posts": 10, "max_comments_per_post": 20},
}


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
    return topics or DEFAULT_TOPICS[:]


def keywords_for(topic: str) -> list[str]:
    words = [f"国务院常务会 {topic}"]
    for marker, values in KEYWORD_RULES.items():
        if marker in topic:
            words.extend(values)
    return list(dict.fromkeys(words))


def safe_name(text: str) -> str:
    text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "_", text).strip("_")
    return text[:32] or "topic"


def main() -> None:
    parser = argparse.ArgumentParser(description="Create MediaSpider-compatible task JSONs for a CWH report.")
    parser.add_argument("--input", default="", help="Meeting agenda text.")
    parser.add_argument("--input-file", help="UTF-8 meeting agenda file.")
    parser.add_argument("--out-dir", default="outputs/cwh_mediacrawler_tasks", help="Task output directory.")
    parser.add_argument("--platforms", default="wb,dy,ks,bili,zhihu", help="Comma list of MediaSpider platforms; current CWH defaults exclude xhs, tieba and foreign platforms.")
    parser.add_argument("--media-home", default="", help="Optional MediaSpider home path.")
    parser.add_argument("--max-posts", type=int, default=0, help="Override max_posts for all platforms.")
    parser.add_argument("--max-comments", type=int, default=0, help="Override max_comments_per_post for all platforms.")
    args = parser.parse_args()

    agenda = args.input
    if args.input_file:
        agenda = Path(args.input_file).read_text(encoding="utf-8")
    topics = infer_topics(agenda)
    platforms = [x.strip() for x in args.platforms.split(",") if x.strip()]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir) / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    tasks = []
    for platform in platforms:
        defaults = PLATFORM_DEFAULTS.get(platform, {"max_posts": 10, "max_comments_per_post": 20})
        for idx, topic in enumerate(topics, 1):
            task = {
                "platform": platform,
                "crawler_type": "search",
                "login_type": "qrcode",
                "keywords": keywords_for(topic),
                "get_comment": True,
                "get_sub_comment": False,
                "max_posts": args.max_posts or defaults["max_posts"],
                "max_comments_per_post": args.max_comments or defaults["max_comments_per_post"],
                "max_concurrency": 1,
                "save_data_option": "jsonl",
                "headless": False,
                "cwh_topic": topic,
            }
            if args.media_home:
                task["media_crawler_home"] = args.media_home
            task_path = out_dir / f"{idx:02d}_{platform}_{safe_name(topic)}.json"
            task_path.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
            tasks.append({"topic": topic, "platform": platform, "task": str(task_path)})
    manifest = {"agenda": agenda, "topics": topics, "platforms": platforms, "tasks": tasks}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "out_dir": str(out_dir), "task_count": len(tasks), "manifest": str(out_dir / "manifest.json")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
