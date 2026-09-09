from __future__ import annotations

import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


COLLECTION = load_module(
    "run_cwh_domestic_comment_collection",
    SCRIPTS / "run_cwh_domestic_comment_collection.py",
)
SENTIMENT = load_module("run_cwh_sentiment_stage_for_collection", SCRIPTS / "run_cwh_sentiment_stage.py")
BATCH = load_module("run_mediacrawler_batch_for_collection", SCRIPTS / "run_mediacrawler_batch.py")
ADAPTER = load_module("run_mediaspider_task_for_collection", SCRIPTS / "run_mediaspider_task.py")


class DomesticCommentCollectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = COLLECTION.load_json(
            Path(__file__).resolve().parents[1] / "config" / "domestic_comment_collection.json"
        )

    def test_platform_allowlist_explicitly_rejects_xhs_and_foreign(self) -> None:
        self.assertEqual(
            COLLECTION.validate_platforms(["微博", "bilibili", "知乎"], self.config),
            ["wb", "bili", "zhihu"],
        )
        with self.assertRaises(ValueError):
            COLLECTION.validate_platforms(["xhs"], self.config)
        with self.assertRaises(ValueError):
            COLLECTION.validate_platforms(["tieba"], self.config)
        with self.assertRaises(ValueError):
            COLLECTION.validate_platforms(["youtube"], self.config)

    def test_exact_monitoring_bounds_exclude_late_same_day_comment(self) -> None:
        start_dt, end_dt = COLLECTION.period_bounds(
            "2026-07-10 19:00:00+08:00",
            "2026-07-13 13:30:00+08:00",
        )
        self.assertEqual(
            COLLECTION.window_status("2026-07-13 13:29:59+08:00", start_dt, end_dt),
            "in_window",
        )
        self.assertEqual(
            COLLECTION.window_status("2026-07-13 13:30:01+08:00", start_dt, end_dt),
            "after_window",
        )

    def test_long_agenda_titles_become_short_semantic_platform_queries(self) -> None:
        topic = {
            "title": "学习贯彻习近平总书记关于上半年行业形势和做好下半年改革工作的重要讲话精神",
            "aliases": [],
            "public_queries": [],
        }
        queries = COLLECTION.keyword_candidates({}, topic)
        self.assertIn("国常会 上半年行业形势 下半年改革工作", queries)
        self.assertNotIn("学习贯彻", " ".join(queries))
        self.assertLessEqual(len(queries), 2)
        self.assertTrue(all(COLLECTION.han_length(query) <= 24 for query in queries))

        regulation_queries = COLLECTION.keyword_candidates(
            {},
            {
                "title": "审议通过《国务院关于修改〈城市管理条例〉的决定（草案）》",
                "aliases": [],
                "public_queries": [],
            },
        )
        self.assertEqual(regulation_queries[0], "国常会 城市管理条例")
        self.assertNotIn("审议通过", " ".join(regulation_queries))

    def test_task_package_is_domestic_comment_only(self) -> None:
        scope = {
            "agenda": "7月10日国务院常务会",
            "start": "2026-07-10",
            "end": "2026-07-13",
            "topics": [
                {
                    "index": 1,
                    "title": "进一步部署防汛抗洪救灾工作",
                    "aliases": ["防汛救灾"],
                    "public_queries": ["国务院常务会议 防汛救灾 网友评论"],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp:
            package = COLLECTION.create_tasks(
                scope,
                Path(temp),
                ["wb", "bili"],
                {"max_posts": 10, "max_comments_per_post": 20},
                "",
            )
            manifest = COLLECTION.load_json(package["manifest"])
            self.assertEqual(manifest["platforms"], ["wb", "bili"])
            self.assertEqual(manifest["excluded_platforms"], ["xhs", "tieba", "foreign"])
            self.assertEqual(len(manifest["tasks"]), 2)
            task = COLLECTION.load_json(Path(manifest["tasks"][0]["path"]))
            self.assertEqual(task["collector"], "domestic")
            self.assertTrue(task["get_comment"])
            self.assertFalse(task["get_sub_comment"])
            self.assertNotIn("xhs", task["platform"])
            self.assertEqual(task["cwh_monitoring_start"], "2026-07-10")

    def test_normalization_filters_scope_window_and_non_comments(self) -> None:
        samples = [
            {
                "platform": "wb",
                "region": "domestic",
                "source_type": "netizen_comment",
                "content": "支持加强防汛救灾",
                "published_at": "2026-07-11 08:30:00",
                "topic": "进一步部署防汛抗洪救灾工作",
                "raw_id": "c1",
                "url": "https://weibo.example/1",
                "raw_file": "wb_comments.jsonl",
            },
            {
                "platform": "wb",
                "region": "domestic",
                "source_type": "netizen_comment",
                "content": "支持加强防汛救灾",
                "published_at": "2026-07-11 08:30:00",
                "topic": "研究自然资源保护利用有关工作",
                "raw_id": "c1",
                "url": "https://weibo.example/1",
                "raw_file": "wb_comments.jsonl",
            },
            {
                "platform": "xhs",
                "region": "domestic",
                "source_type": "netizen_comment",
                "content": "小红书样本",
                "published_at": "2026-07-11",
                "topic": "进一步部署防汛抗洪救灾工作",
                "raw_id": "x1",
            },
            {
                "platform": "youtube",
                "region": "overseas",
                "source_type": "netizen_comment",
                "content": "foreign sample",
                "published_at": "2026-07-11",
                "topic": "进一步部署防汛抗洪救灾工作",
                "raw_id": "y1",
            },
            {
                "platform": "bili",
                "region": "domestic",
                "source_type": "self_media_post",
                "content": "视频正文不是评论",
                "published_at": "2026-07-11",
                "topic": "进一步部署防汛抗洪救灾工作",
                "raw_id": "p1",
            },
            {
                "platform": "wb",
                "region": "domestic",
                "source_type": "netizen_comment",
                "content": "时间窗外评论",
                "published_at": "2026-07-14",
                "topic": "进一步部署防汛抗洪救灾工作",
                "raw_id": "c2",
            },
            {
                "platform": "wb",
                "region": "domestic",
                "source_type": "netizen_comment",
                "content": "无日期评论",
                "published_at": "",
                "topic": "进一步部署防汛抗洪救灾工作",
                "raw_id": "c3",
            },
        ]
        accepted, excluded, audit = COLLECTION.normalize_comment_samples(
            samples,
            self.config,
            ["wb", "bili"],
            "2026-07-10",
            "2026-07-13",
        )
        self.assertEqual(len(accepted), 1)
        self.assertIn("进一步部署防汛抗洪救灾工作", accepted[0]["子议题"])
        self.assertIn("研究自然资源保护利用有关工作", accepted[0]["子议题"])
        self.assertEqual(audit["reason_counts"]["duplicate_comment_id_merged"], 1)
        self.assertEqual(audit["reason_counts"]["platform_not_allowed"], 2)
        self.assertEqual(audit["reason_counts"]["not_comment_or_reply"], 1)
        self.assertEqual(audit["reason_counts"]["after_window"], 1)
        self.assertEqual(audit["reason_counts"]["undated"], 1)
        self.assertEqual(len(excluded), 5)

    def test_collection_csv_is_accepted_by_sentiment_gate(self) -> None:
        row = {
            "评论ID": "c1",
            "评论内容": "支持数字中国继续建设",
            "平台": "wb",
            "发布时间": "2026-07-12",
            "原文链接": "https://weibo.example/1",
            "子议题": "听取数字中国建设情况汇报",
            "来源": "用户A",
            "点赞量": 3,
            "信息类型": "评论",
            "采集来源": "MediaSpider Supervisor",
            "原始文件": "wb_comments.jsonl",
            "父原帖标题": "国务院常务会议部署数字中国建设",
            "父原帖发布时间": "2026-07-11",
            "父原帖来源": "示例账号",
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "境内公开评论明细.csv"
            COLLECTION.write_csv(path, [row], COLLECTION.COMMENT_FIELDS)
            tables = SENTIMENT.read_tables(path)
            sheet_name, rows, starting_row = tables[0]
            comments, _ = SENTIMENT.parse_rows(rows, path, sheet_name, starting_row)
            self.assertEqual(len(comments), 1)
            self.assertEqual(comments[0]["text"], "支持数字中国继续建设")
            self.assertEqual(comments[0]["topic"], "听取数字中国建设情况汇报")
            self.assertEqual(comments[0]["parent_post_title"], "国务院常务会议部署数字中国建设")

    def test_comment_in_window_is_rejected_when_parent_post_predates_window(self) -> None:
        topic = "研究公共服务改革有关工作"
        samples = [
            {
                "platform": "bili",
                "region": "domestic",
                "source_type": "self_media_post",
                "title": "其他会议讨论公共服务改革",
                "content": "其他会议讨论公共服务改革",
                "published_at": "2026-07-09",
                "url": "https://www.bilibili.com/video/av1",
                "topic": topic,
            },
            {
                "platform": "bili",
                "region": "domestic",
                "source_type": "netizen_comment",
                "content": "这项改革需要继续观察",
                "published_at": "2026-07-11",
                "url": "https://www.bilibili.com/video/av1/",
                "topic": topic,
                "raw_id": "comment-1",
            },
        ]
        enriched = COLLECTION.attach_parent_post_context(samples)
        accepted, excluded, audit = COLLECTION.normalize_comment_samples(
            enriched,
            self.config,
            ["bili"],
            "2026-07-10",
            "2026-07-13",
        )
        self.assertEqual(accepted, [])
        self.assertEqual(audit["reason_counts"]["parent_post_before_window"], 1)
        parent_excluded = [row for row in excluded if row["排除原因"] == "parent_post_before_window"]
        self.assertEqual(parent_excluded[0]["父原帖标题"], "其他会议讨论公共服务改革")

    def test_login_failure_is_reported_as_actionable_blocker(self) -> None:
        blockers = COLLECTION.batch_failure_blockers(
            {
                "results": [
                    {
                        "task": "01_wb_防汛救灾.json",
                        "exit_code": 3,
                        "timed_out": False,
                        "stdout": "Status: login required; no raw output was produced.",
                        "stderr": "",
                    }
                ]
            }
        )
        self.assertEqual(len(blockers), 1)
        self.assertIn("需要有效登录态或扫码登录", blockers[0])

    def test_platform_circuit_breaker_only_stops_empty_blocked_runs(self) -> None:
        blocked = {
            "timed_out": False,
            "stdout": "Status: login required; no raw output was produced.",
            "stderr": "",
            "inspection": {"metrics": {"posts": 0, "comments": 0}},
        }
        partial_success = {
            **blocked,
            "inspection": {"metrics": {"posts": 1, "comments": 12}},
        }
        self.assertTrue(BATCH.should_circuit_break_platform(blocked))
        self.assertFalse(BATCH.should_circuit_break_platform(partial_success))

    def test_collected_candidates_remain_blocked_pending_ai_review(self) -> None:
        self.assertEqual(COLLECTION.collection_gate_status(True, 0, 3), "ai_review_required")
        self.assertEqual(COLLECTION.collection_gate_status(True, 0, 0), "blocked_or_empty")
        self.assertEqual(COLLECTION.collection_gate_status(False, 0, 0), "dry_run_ready")

    def test_batch_defaults_to_bundled_runtime_adapter(self) -> None:
        adapter = Path(BATCH.resolve_runtime_adapter())
        self.assertEqual(adapter.name, "run_mediaspider_task.py")
        self.assertTrue(adapter.exists())

    def test_runtime_adapter_prefers_mediaspider_virtualenv_python(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            expected = Path(temp) / ".venv" / "Scripts" / "python.exe"
            expected.parent.mkdir(parents=True)
            expected.touch()
            self.assertEqual(BATCH.resolve_adapter_python("fallback-python", temp), str(expected))

    def test_task_login_artifacts_are_stable_and_local_to_task(self) -> None:
        task = Path("out/tasks/01_bili_topic.json")
        qr, state = BATCH.task_login_artifacts(task)
        self.assertEqual(qr, Path("out/tasks/01_bili_topic.qrcode.png"))
        self.assertEqual(state, Path("out/tasks/01_bili_topic.login_state.json"))

    def test_default_profile_is_isolated_under_collection_output(self) -> None:
        task = (Path("out") / "tasks" / "01_bili_topic.json").resolve()
        expected = (Path("out") / "browser_profiles" / "%s_user_data_dir").resolve()
        self.assertEqual(BATCH.default_profile_template(task), str(expected))

    def test_runtime_adapter_forces_raw_output_inside_audit_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp) / "one_task_run"
            resolved = ADAPTER.bind_task_output(
                {"platform": "bili", "save_data_path": "unsafe-global-folder"},
                run_dir,
            )
            expected = str((run_dir / "raw").resolve())
            self.assertEqual(resolved["save_data_path"], expected)
            argv = ADAPTER.build_media_argv(resolved)
            self.assertEqual(argv[argv.index("--save_data_path") + 1], expected)

    def test_only_deep_profile_collects_sub_comments(self) -> None:
        profiles = self.config["profiles"]
        self.assertFalse(profiles["trial"]["get_sub_comment"])
        self.assertFalse(profiles["formal"]["get_sub_comment"])
        self.assertTrue(profiles["deep"]["get_sub_comment"])

    def test_reuse_only_requires_existing_run_directory_argument(self) -> None:
        parser = COLLECTION.build_parser()
        args = parser.parse_args([
            "--research-plan", "plan.json",
            "--output-dir", "out",
            "--reuse-only",
        ])
        with self.assertRaisesRegex(ValueError, "reuse-run-dir"):
            COLLECTION.run(args)

    def test_collection_cli_does_not_silently_limit_topic_coverage(self) -> None:
        parser = COLLECTION.build_parser()
        args = parser.parse_args([
            "--research-plan", "plan.json",
            "--output-dir", "out",
        ])
        self.assertEqual(args.limit, 0)


if __name__ == "__main__":
    unittest.main()
