from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("platform_runner", ROOT / "scripts" / "run_cwh_public_platform_research.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class PublicPlatformRunnerTests(unittest.TestCase):
    def test_builds_topic_specific_platform_tasks(self) -> None:
        plan = {
            "topics": [
                {
                    "topic": "研究某项工作",
                    "stable_source_tasks": [
                        {
                            "source_id": "baijiahao",
                            "query_families": ["百家号查询一", "百家号查询二"],
                        }
                    ],
                }
            ]
        }
        tasks = MODULE.platform_queries(plan, "baijiahao")
        self.assertEqual(2, len(tasks))
        self.assertEqual("baijiahao-t1-q1", tasks[0]["query_id"])
        self.assertEqual("研究某项工作", tasks[0]["topic"])

    def test_waiting_login_status_is_resumable(self) -> None:
        status = MODULE.adapter_status("baijiahao", {"exit_code": 2}, {})
        self.assertEqual("partial_waiting_login", status)

    def test_platform_adapter_query_strips_site_prefix(self) -> None:
        plan = {
            "topics": [
                {
                    "topic": "议题",
                    "stable_source_tasks": [
                        {
                            "source_id": "wechat_public",
                            "query_families": ["(site:mp.weixin.qq.com) 2026-05-15 国务院常务会议 议题"],
                        }
                    ],
                }
            ]
        }
        task = MODULE.platform_queries(plan, "wechat")[0]
        self.assertEqual("2026-05-15 国务院常务会议 议题", task["query"])

    def test_cwh_platform_adapters_reuse_the_workbench_profile(self) -> None:
        args = SimpleNamespace(max_results=10, headless=False, wait_for_human_seconds=0)
        tasks = [{"query": "国务院常务会议"}]
        profile = str(Path.home() / ".cwh" / "browser_profile")
        baijiahao = MODULE.baijiahao_command("node", tasks, Path("out"), args)
        wechat = MODULE.wechat_command("node", Path("wechat-skill"), tasks, Path("out"), args)
        self.assertEqual(profile, baijiahao[baijiahao.index("--profile-dir") + 1])
        self.assertEqual(profile, wechat[wechat.index("--profile-dir") + 1])

    def test_cwh_platform_adapters_read_the_connector_profile_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            local = Path(temp)
            marker = local / "cwh-report-skill" / "platform_profile.json"
            marker.parent.mkdir(parents=True)
            expected = local / "custom-profile"
            marker.write_text(json.dumps({"profile_dir": str(expected), "cdp_port": 9222}), encoding="utf-8")
            original = os.environ.get("LOCALAPPDATA")
            try:
                os.environ["LOCALAPPDATA"] = str(local)
                self.assertEqual(expected.resolve(), MODULE.cwh_browser_profile())
            finally:
                if original is None:
                    os.environ.pop("LOCALAPPDATA", None)
                else:
                    os.environ["LOCALAPPDATA"] = original


if __name__ == "__main__":
    unittest.main()
