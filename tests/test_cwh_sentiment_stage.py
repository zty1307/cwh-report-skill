from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_cwh_sentiment_stage.py"
SPEC = importlib.util.spec_from_file_location("run_cwh_sentiment_stage", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def args(input_dir: Path, output_dir: Path, run_preparation: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        system_workbook=None,
        comment_detail=[],
        input_dir=str(input_dir),
        output_dir=str(output_dir),
        run_preparation=run_preparation,
        sentiment_skill_dir=None,
        sentiment_results=None,
        min_topic_denominator=20,
        backfill_workbook=None,
        backfill_output=None,
    )


class CwhSentimentStageTests(unittest.TestCase):
    def test_article_body_and_comment_count_are_not_comment_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            input_dir = root / "raw"
            input_dir.mkdir()
            with (input_dir / "公众文章最热样本.csv").open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["标题", "正文内容", "评论量"])
                writer.writeheader()
                writer.writerow({"标题": "政策解读", "正文内容": "这是一篇文章正文", "评论量": 18})

            audit = MODULE.run(args(input_dir, root / "out"))

            self.assertEqual(audit["status"], "missing_comment_detail")
            self.assertEqual(audit["comment_rows"], 0)
            self.assertEqual(audit["aggregate_comment_field_count"], 1)
            with Path(audit["outputs"]["sentiment_input"]).open("r", encoding="utf-8-sig", newline="") as handle:
                self.assertEqual(list(csv.DictReader(handle)), [])

    def test_direct_comment_text_is_extracted_with_stable_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            input_dir = root / "raw"
            input_dir.mkdir()
            source = input_dir / "评论明细.csv"
            with source.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["评论ID", "评论内容", "平台", "发布时间", "原文链接", "子议题"])
                writer.writeheader()
                writer.writerow({"评论ID": "c-1", "评论内容": "支持这项政策", "平台": "微博", "发布时间": "2026-07-11", "原文链接": "https://example.test/1", "子议题": "议题一"})
                writer.writerow({"评论ID": "c-2", "评论内容": "还需要观察", "平台": "微信", "发布时间": "2026-07-12", "原文链接": "https://example.test/2", "子议题": "议题二"})

            first = MODULE.run(args(input_dir, root / "out1"))
            second = MODULE.run(args(input_dir, root / "out2"))

            self.assertEqual(first["status"], "ready_for_preparation")
            self.assertEqual(first["comment_rows"], 2)
            with Path(first["outputs"]["sentiment_input"]).open("r", encoding="utf-8-sig", newline="") as handle:
                first_rows = list(csv.DictReader(handle))
            with Path(second["outputs"]["sentiment_input"]).open("r", encoding="utf-8-sig", newline="") as handle:
                second_rows = list(csv.DictReader(handle))
            self.assertEqual([row["sample_id"] for row in first_rows], [row["sample_id"] for row in second_rows])
            self.assertEqual(first_rows[0]["text"], "支持这项政策")
            self.assertEqual(first_rows[0]["topic"], "议题一")

    def test_generic_content_requires_comment_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            input_dir = root / "raw"
            input_dir.mkdir()
            with (input_dir / "混合数据.csv").open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["信息类型", "内容", "平台"])
                writer.writeheader()
                writer.writerow({"信息类型": "新闻", "内容": "新闻正文", "平台": "网站"})
                writer.writerow({"信息类型": "评论", "内容": "网民评论", "平台": "网站"})

            audit = MODULE.run(args(input_dir, root / "out"))

            self.assertEqual(audit["comment_rows"], 1)
            with Path(audit["outputs"]["sentiment_input"]).open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["text"], "网民评论")

    def test_json_comment_container_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            input_dir = root / "raw"
            input_dir.mkdir()
            payload = {"comments": [{"comment_id": "j1", "comment_content": "可以继续推进", "platform": "test"}]}
            (input_dir / "comment_details.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            audit = MODULE.run(args(input_dir, root / "out"))

            self.assertEqual(audit["comment_rows"], 1)
            self.assertEqual(audit["status"], "ready_for_preparation")

    def test_reviewed_results_create_topic_percentages_for_backfill(self) -> None:
        comments = [
            {"sample_id": "c1", "topic": "议题一"},
            {"sample_id": "c2", "topic": "议题一"},
            {"sample_id": "c3", "topic": "议题二"},
        ]
        metadata = {"topics": ["议题一", "议题二"]}
        with tempfile.TemporaryDirectory() as temp:
            results_path = Path(temp) / "results.csv"
            with results_path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["sample_id", "label", "label_source", "in_sentiment_denominator", "exclusion_reason", "needs_review"],
                )
                writer.writeheader()
                writer.writerows(
                    [
                        {"sample_id": "c1", "label": "positive", "label_source": "human_reviewed", "in_sentiment_denominator": "true", "exclusion_reason": "", "needs_review": "false"},
                        {"sample_id": "c2", "label": "negative", "label_source": "classifier", "in_sentiment_denominator": "true", "exclusion_reason": "", "needs_review": "false"},
                        {"sample_id": "c3", "label": "neutral", "label_source": "ai_reviewed", "in_sentiment_denominator": "true", "exclusion_reason": "", "needs_review": "false"},
                    ]
                )

            summary, blockers = MODULE.build_workbook_summary(comments, metadata, str(results_path))

            self.assertEqual(blockers, [])
            self.assertEqual(summary["status"], "ready_for_workbook_backfill")
            self.assertEqual(summary["topics"][0]["positive"], 0.5)
            self.assertEqual(summary["topics"][0]["negative"], 0.5)
            self.assertEqual(summary["topics"][1]["neutral"], 1.0)

    def test_small_topic_sample_is_observed_but_not_backfilled(self) -> None:
        comments = [{"sample_id": "c1", "topic": "议题一"}]
        metadata = {"topics": ["议题一"]}
        with tempfile.TemporaryDirectory() as temp:
            results_path = Path(temp) / "results.csv"
            with results_path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["sample_id", "label", "label_source", "in_sentiment_denominator", "exclusion_reason", "needs_review"],
                )
                writer.writeheader()
                writer.writerow(
                    {"sample_id": "c1", "label": "positive", "label_source": "human_reviewed", "in_sentiment_denominator": "true", "exclusion_reason": "", "needs_review": "false"}
                )

            summary, blockers = MODULE.build_workbook_summary(
                comments, metadata, str(results_path), min_topic_denominator=20
            )

            self.assertEqual(blockers, [])
            self.assertEqual(summary["status"], "no_topic_denominator")
            self.assertEqual(summary["topics"][0]["status"], "insufficient_sample")
            self.assertEqual(summary["topics"][0]["denominator"], 1)
            self.assertIsNone(summary["topics"][0]["negative"])
            self.assertEqual(summary["topics"][0]["observed_rates"]["negative"], 0.0)

    def test_reviewed_comments_emit_strict_report_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            input_dir = root / "raw"
            input_dir.mkdir()
            source = input_dir / "评论明细.csv"
            with source.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["评论ID", "评论内容", "平台", "发布时间", "原文链接", "子议题"])
                writer.writeheader()
                writer.writerow({"评论ID": "c-1", "评论内容": "支持", "平台": "今日头条", "发布时间": "2026-07-11", "原文链接": "https://example.test/1", "子议题": "议题一"})
                writer.writerow({"评论ID": "c-2", "评论内容": "无关内容", "平台": "今日头条", "发布时间": "2026-07-11", "原文链接": "https://example.test/2", "子议题": "议题一"})

            first = MODULE.run(args(input_dir, root / "stage1"))
            with Path(first["outputs"]["sentiment_input"]).open("r", encoding="utf-8-sig", newline="") as handle:
                comments = list(csv.DictReader(handle))
            results = root / "results.csv"
            with results.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["sample_id", "label", "label_source", "in_sentiment_denominator", "exclusion_reason", "needs_review", "ai_formal_include", "ai_semantic_quality", "ai_formal_reason", "comment_heading"])
                writer.writeheader()
                writer.writerow({"sample_id": comments[0]["sample_id"], "label": "positive", "label_source": "ai_reviewed", "in_sentiment_denominator": "true", "exclusion_reason": "", "needs_review": "false", "ai_formal_include": "true", "ai_semantic_quality": "substantive", "ai_formal_reason": "表达明确支持", "comment_heading": "支持推进相关政策"})
                writer.writerow({"sample_id": comments[1]["sample_id"], "label": "", "label_source": "ai_reviewed", "in_sentiment_denominator": "false", "exclusion_reason": "与会议无关", "needs_review": "false", "ai_formal_include": "false", "ai_semantic_quality": "off_topic", "ai_formal_reason": "与会议无关", "comment_heading": ""})

            second_args = args(input_dir, root / "stage2")
            second_args.sentiment_results = str(results)
            second = MODULE.run(second_args)

            handoff_path = Path(second["outputs"]["report_comment_handoff"])
            with handoff_path.open("r", encoding="utf-8-sig", newline="") as handle:
                handoff = list(csv.DictReader(handle))
            self.assertEqual(len(handoff), 1)
            self.assertEqual(handoff[0]["id"], comments[0]["sample_id"])
            self.assertEqual(handoff[0]["content"], "支持")
            self.assertEqual(handoff[0]["is_comment"], "true")
            self.assertEqual(handoff[0]["quote_verified"], "true")
            self.assertEqual(handoff[0]["evidence_mode"], "verbatim_public_comment")
            self.assertEqual(handoff[0]["ai_formal_include"], "true")
            self.assertEqual(handoff[0]["comment_heading"], "支持推进相关政策")
            self.assertEqual(second["report_comment_handoff"]["eligible_rows"], 1)
            self.assertEqual(second["report_comment_handoff"]["excluded_rows"], 1)
            self.assertEqual(second["status"], "ai_review_complete")
            self.assertEqual(second["formal_sentiment_percentages"], "available")

    def test_missing_formal_use_review_cannot_enter_report_handoff(self) -> None:
        comments = [{
            "sample_id": "c1", "topic": "议题一", "platform": "B站", "source": "用户",
            "text": "希望把政策变化说得更清楚", "url": "https://example.test/1", "comment_id": "1",
        }]
        with tempfile.TemporaryDirectory() as temp:
            results_path = Path(temp) / "results.csv"
            with results_path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["sample_id", "label", "label_source", "in_sentiment_denominator", "needs_review"])
                writer.writeheader()
                writer.writerow({"sample_id": "c1", "label": "neutral", "label_source": "ai_reviewed", "in_sentiment_denominator": "true", "needs_review": "false"})
            rows, audit = MODULE.build_report_comment_handoff(comments, str(results_path))
            self.assertEqual(rows, [])
            self.assertEqual(audit["missing_formal_review_rows"], 1)
            self.assertEqual(audit["status"], "partial")


if __name__ == "__main__":
    unittest.main()
