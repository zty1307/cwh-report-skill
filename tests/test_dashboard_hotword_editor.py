from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "serve_dashboard.py"
SPEC = importlib.util.spec_from_file_location("serve_dashboard_hotword_test", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class DashboardHotwordEditorTests(unittest.TestCase):
    def test_preserves_existing_metadata_and_accepts_manual_weight(self) -> None:
        data = {
            "meeting": {"topics": ["议题甲", "议题乙"]},
            "hotwords": [
                {
                    "word": "数字中国",
                    "topic": "议题甲",
                    "display_weight": 88,
                    "evidence": [{"source": "来源甲", "url": "https://example.com/a"}],
                },
                {"word": "全民健身", "topic": "议题乙", "display_weight": 70},
            ],
            "samples": [
                {
                    "source": "来源乙",
                    "title": "算力网建设提速",
                    "content": "围绕算力网建设形成新的公开讨论",
                    "url": "https://example.com/b",
                }
            ],
        }
        rows, unsupported = MODULE.normalize_manual_hotwords(
            data,
            [
                {"word": "数字中国"},
                {"word": "算力网", "weight": 91},
                {"word": "人工新增词", "weight": 45},
                {"word": "数字中国", "weight": 1},
            ],
        )
        self.assertEqual([row["word"] for row in rows], ["数字中国", "算力网", "人工新增词"])
        self.assertEqual(rows[0]["display_weight"], 88)
        self.assertEqual(rows[1]["display_weight"], 91)
        self.assertTrue(rows[1]["evidence"])
        self.assertEqual(unsupported, ["人工新增词"])

    def test_builds_renderer_payload_with_manual_authority(self) -> None:
        payload = MODULE.manual_hotword_payload(
            [
                {"word": "数字中国", "topic": "议题甲", "display_weight": 100, "evidence": [{}]},
                {"word": "算力网", "topic": "议题甲", "display_weight": 82, "evidence": []},
            ]
        )
        self.assertEqual(payload["method"], "human_reviewed_dashboard_adjustment")
        self.assertEqual(payload["settings"]["max_placed_instances"], 289)
        self.assertEqual(payload["selected"][1]["term"], "算力网")
        self.assertEqual(payload["selected"][1]["weight"], 82)

    def test_public_release_has_redistributable_cjk_font(self) -> None:
        skill_root = Path(__file__).resolve().parents[1]
        source = (skill_root / "scripts" / "cwh_hotword_pipeline.py").read_text(encoding="utf-8")
        self.assertIn('"CWH_CJK_FONT"', source)
        self.assertTrue((skill_root / "assets" / "fonts" / "NotoSansCJKsc-Regular.otf").exists())
        self.assertTrue((skill_root / "assets" / "fonts" / "LICENSE-NOTO.txt").exists())

    def test_baseline_terms_are_not_reported_as_new_without_evidence(self) -> None:
        data = {"meeting": {"topics": ["议题"]}, "hotwords": [], "samples": []}
        rows, unsupported = MODULE.normalize_manual_hotwords(
            data,
            [{"word": "原有热词", "weight": 80}, {"word": "本次新增", "weight": 60}],
            ["原有热词"],
        )
        self.assertEqual([row["word"] for row in rows], ["原有热词", "本次新增"])
        self.assertEqual(unsupported, ["本次新增"])

    def test_rejects_standalone_location_from_manual_editor(self) -> None:
        data = {"meeting": {"topics": ["防汛救灾"]}, "hotwords": [], "samples": []}
        with self.assertRaisesRegex(ValueError, "纯地名或项目所在地"):
            MODULE.normalize_manual_hotwords(data, [{"word": "辽宁庄河", "weight": 80}])


if __name__ == "__main__":
    unittest.main()
