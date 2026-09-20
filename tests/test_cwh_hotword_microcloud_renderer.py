from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from PIL import Image


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "cwh_hotword_pipeline.py"
SPEC = importlib.util.spec_from_file_location("cwh_hotword_pipeline_for_test", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class July19HierarchyRendererTests(unittest.TestCase):
    def test_meeting_boilerplate_fragments_do_not_consume_candidate_slots(self) -> None:
        for term in ('国务', '务院常务会', '国务院常务', '务院常务会议',
                     '开国务院常务', '召开国务院常', '持召开国务院', '主持召开国务'):
            self.assertFalse(MODULE.valid_candidate(term), term)
        for term in ('数字中国', '经济形势', '民生保障', '公共服务', '政策协同',
                     '行政法规', '法治建设', '医疗服务', '可持续城市更新'):
            self.assertTrue(MODULE.valid_candidate(term), term)

    def test_sustainable_policy_phrase_is_not_rejected_as_particle_fragment(self) -> None:
        self.assertTrue(MODULE.valid_candidate("可持续更新模式"))
        self.assertTrue(MODULE.valid_candidate("可持续城市更新"))

    def test_renderer_uses_july19_hierarchy_layout(self) -> None:
        payload = {
            "settings": {
                "color": "#0D4E6D",
                "rotation": -15,
                "max_placed_instances": 5,
            },
            "selected": [
                {"term": term, "weight": weight}
                for term, weight in (
                    ("数字中国", 100),
                    ("人工智能", 70),
                    ("防汛抗洪救灾", 55),
                    ("新兴支柱产业", 40),
                    ("全民健身", 30),
                )
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "cloud.png"
            result = MODULE.render_wordcloud_png(payload, output_path, seed=20260710)
            audit = result["render_audit"]
            self.assertEqual(audit["method"], "july19_hierarchy_edge_fill")
            self.assertEqual(audit["placed_instance_count"], 5)
            self.assertEqual(audit["placed_unique_term_count"], 5)
            self.assertTrue(audit["all_primary_terms_placed"])
            self.assertEqual(
                [placement["repeat_round"] for placement in audit["placed"]],
                [0, 0, 0, 0, 0],
            )
            image = Image.open(output_path).convert("RGBA")
            self.assertIsNotNone(image.getchannel("A").getbbox())
            self.assertEqual(image.getchannel("A").getbbox(), (0, 0, *image.size))


if __name__ == "__main__":
    unittest.main()
