"""Apply an explicit human/AI review config to discovered Toutiao comments."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comments", required=True)
    parser.add_argument("--review-config", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    comments_path = Path(args.comments).resolve()
    config_path = Path(args.review_config).resolve()
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    comments = json.loads(comments_path.read_text(encoding="utf-8-sig"))
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    article_topics = {str(key): value for key, value in config["article_topics"].items()}
    exclusions = {str(key): value for key, value in config.get("excluded_comments", {}).items()}
    labels = {str(key): value for key, value in config.get("label_overrides", {}).items()}

    rows = []
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    exclusion_counts: Counter[str] = Counter()
    for comment in comments:
        cid = str(comment.get("comment_id") or "")
        platform = str(comment.get("platform") or "今日头条")
        sample_id = "comment-" + hashlib.sha256(f"{platform}|{cid}".encode("utf-8")).hexdigest()[:20]
        article_id = str(comment.get("article_id") or "")
        topic = article_topics.get(article_id, "")
        exclusion_reason = exclusions.get(cid, "")
        if not topic and not exclusion_reason:
            exclusion_reason = "母帖无法可靠映射到单一子议题"
        included = not exclusion_reason
        label = labels.get(cid, config.get("default_label", "positive")) if included else ""
        if included and label not in {"positive", "neutral", "negative"}:
            raise ValueError(f"Invalid label for {cid}: {label}")
        if included:
            counts[topic][label] += 1
        else:
            exclusion_counts[exclusion_reason] += 1
        rows.append({
            "sample_id": sample_id,
            "comment_id": cid,
            "platform": platform,
            "published_at": comment.get("published_at", ""),
            "article_id": article_id,
            "article_title": comment.get("article_title", ""),
            "article_url": comment.get("article_url", ""),
            "topic": topic,
            "content": comment.get("content", ""),
            "source": comment.get("source", ""),
            "likes": comment.get("likes", ""),
            "in_sentiment_denominator": str(included).lower(),
            "label": label,
            "label_source": "ai_reviewed",
            "needs_review": "false",
            "exclusion_reason": exclusion_reason,
        })

    fields = list(rows[0]) if rows else []
    with (out_dir / "toutiao_comments_reviewed.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    audit = {
        "comments_reviewed": len(rows),
        "comments_in_denominator": sum(sum(counter.values()) for counter in counts.values()),
        "comments_excluded": sum(exclusion_counts.values()),
        "negative_interpretation": "若 negative 为 0，仅表示本批有效样本未观察到负面，不代表总体负面舆情为 0%。",
        "topic_counts": {topic: dict(counter) for topic, counter in counts.items()},
        "exclusion_counts": dict(exclusion_counts),
        "review_config": str(config_path),
        "source_comments": str(comments_path),
    }
    (out_dir / "toutiao_comment_review_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False))


if __name__ == "__main__":
    main()
