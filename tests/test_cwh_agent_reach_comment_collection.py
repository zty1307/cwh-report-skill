from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_cwh_agent_reach_comment_collection.py"
SPEC = importlib.util.spec_from_file_location("run_cwh_agent_reach_comment_collection", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class AgentReachCommentCollectionTests(unittest.TestCase):
    def test_article_id_from_url(self) -> None:
        self.assertEqual(MODULE.article_id({"url": "https://www.toutiao.com/article/7661081803561894451/"}), "7661081803561894451")

    def test_comment_and_reply_are_parsed_and_deduped(self) -> None:
        reply = {"id_str": "r1", "text": "回复", "create_time": 1}
        top = {"id_str": "c1", "text": "评论", "create_time": 1, "reply_list": [reply], "new_reply_list": [reply]}
        parsed = MODULE.iter_comment_objects({"data": [{"comment": top}]})
        self.assertEqual([(row[0]["id_str"], row[1]) for row in parsed], [("c1", ""), ("r1", "c1")])

    def test_window_is_inclusive(self) -> None:
        self.assertTrue(MODULE.in_window({"发布时间": "2026-07-10 00:00:00+0800"}, "2026-07-10", "2026-07-13"))
        self.assertTrue(MODULE.in_window({"发布时间": "2026-07-13 23:59:59+0800"}, "2026-07-10", "2026-07-13"))
        self.assertFalse(MODULE.in_window({"发布时间": "2026-07-09 23:59:59+0800"}, "2026-07-10", "2026-07-13"))

    def test_normalization_preserves_provenance(self) -> None:
        row = MODULE.normalize_comment(
            {"id_str": "c1", "text": "支持", "create_time": 1783768467, "user_name": "用户", "user_id": 7, "publish_loc_info": "河北", "digg_count": 2},
            "",
            {"article_id": "7661081803561894451", "title": "标题", "topic": "听取数字中国建设情况汇报", "discovery_source": "Agent Reach / Exa"},
            "raw.json",
        )
        self.assertEqual(row["评论ID"], "c1")
        self.assertEqual(row["信息类型"], "评论")
        self.assertEqual(row["子议题"], "听取数字中国建设情况汇报")
        self.assertEqual(row["原文链接"], "https://www.toutiao.com/article/7661081803561894451/")


if __name__ == "__main__":
    unittest.main()
