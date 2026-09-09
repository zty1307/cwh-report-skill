from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ingest_mediacrawler_outputs.py"
SPEC = importlib.util.spec_from_file_location("ingest_mediacrawler_outputs", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class MediaCrawlerIngestTests(unittest.TestCase):
    def test_bilibili_comment_url_is_derived_from_numeric_video_id(self) -> None:
        row = {"video_id": "116901174905144", "comment_id": "c1", "content": "支持"}
        normalized = MODULE.normalize(Path("bili/search_comments.jsonl"), row, {})

        self.assertIsNotNone(normalized)
        self.assertEqual(
            normalized["url"],
            "https://www.bilibili.com/video/av116901174905144/",
        )
        self.assertTrue(normalized["quote_verified"])

    def test_existing_url_takes_precedence(self) -> None:
        row = {
            "video_id": "116901174905144",
            "url": "https://www.bilibili.com/video/BV13hNc6zEDV/",
            "content": "支持",
        }
        self.assertEqual(MODULE.source_url_for("bili", row), row["url"])

    def test_weibo_comment_url_is_derived_from_note_id(self) -> None:
        self.assertEqual(
            MODULE.source_url_for("wb", {"note_id": "5320117229716365"}),
            "https://m.weibo.cn/detail/5320117229716365",
        )

    def test_blank_weibo_comment_does_not_fall_back_to_nickname(self) -> None:
        row = {"note_id": "5320117229716365", "comment_id": "c1", "nickname": "示例用户"}
        self.assertIsNone(MODULE.normalize(Path("weibo/search_comments.jsonl"), row, {}))


    def test_foreign_video_is_not_misclassified_as_a_netizen_comment(self) -> None:
        row = {
            "platform": "youtube",
            "item_id": "abc123",
            "title": "State Council meeting coverage",
            "body": "A public video description",
            "url": "https://www.youtube.com/watch?v=abc123",
        }
        normalized = MODULE.normalize(Path("youtube/items.json"), row, {})

        self.assertEqual(normalized["source_type"], "overseas_social_post")
        self.assertEqual(normalized["is_comment"], "false")
        self.assertFalse(normalized["quote_verified"])

    def test_foreign_comment_remains_traceable_public_discussion(self) -> None:
        row = {
            "platform": "youtube",
            "comment_id": "comment-1",
            "body": "A real comment",
            "url": "https://www.youtube.com/watch?v=abc123&lc=comment-1",
        }
        normalized = MODULE.normalize(Path("youtube/comments.json"), row, {})

        self.assertEqual(normalized["source_type"], "overseas_public_discussion")
        self.assertEqual(normalized["is_comment"], "true")
        self.assertTrue(normalized["quote_verified"])


if __name__ == "__main__":
    unittest.main()
