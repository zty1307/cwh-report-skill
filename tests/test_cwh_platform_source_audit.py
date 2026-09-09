from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("platform_audit", ROOT / "scripts" / "audit_baseline_platform_coverage.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class PlatformAuditTests(unittest.TestCase):
    def test_extracts_explicit_platform_samples(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "baseline.txt"
            source.write_text(
                "（一）境内媒体自媒体情况\n"
                "头条号“甲号”称，应完善机制。百家号“乙号”称，应强化保障。"
                "微信公众号“丙号”认为，应扩大覆盖。新华网称，应稳步推进。\n"
                "（二）网民评论情况",
                encoding="utf-8",
            )
            rows = MODULE.extract_text_samples("样本", source, {"新华网"})
            counts = MODULE.Counter(row.platform for row in rows)
            self.assertEqual(1, counts["toutiao_articles"])
            self.assertEqual(1, counts["baijiahao"])
            self.assertEqual(1, counts["wechat_public"])
            self.assertEqual(1, counts["publisher_site"])

    def test_waiting_login_is_not_completed_route(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            analysis = Path(temp) / "analysis.json"
            analysis.write_text(
                json.dumps(
                    {
                        "research_audit": {
                            "domestic_media_research": {
                                "coverage_by_topic": [
                                    {
                                        "topic": "议题",
                                        "checks": [
                                            {
                                                "source_id": "baijiahao",
                                                "status": "waiting_login",
                                                "terminal": False,
                                                "execution_mode": "browser_platform_search",
                                                "queries": ["百家号 议题"],
                                                "blocker": "captcha",
                                            }
                                        ],
                                    }
                                ]
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            audit = MODULE.audit_channels(analysis)
            row = audit["by_platform"]["baijiahao"]
            self.assertEqual(0, row["topics_with_valid_completed_route"])
            self.assertEqual({"waiting_login": 1}, row["status_counts"])


if __name__ == "__main__":
    unittest.main()
