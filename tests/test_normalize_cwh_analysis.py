from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "normalize_cwh_analysis.py"
SPEC = importlib.util.spec_from_file_location("normalize_cwh_analysis", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class NormalizeAnalysisTests(unittest.TestCase):
    def test_details_are_deterministic_and_attributed(self) -> None:
        payload = {
            "metadata": {},
            "viewpoints": {
                "by_topic": [{
                    "topic": "议题",
                    "clusters": [{
                        "summary": "建议提升协同性",
                        "details": "模型随意生成的旧段落。",
                        "evidence": [
                            {"attribution": "甲研究院", "formal_claim": "政策实施应强化跨部门协同。"},
                            {"speaker_name": "李明", "formal_claim": "指出应建立长效评估机制。"},
                        ],
                    }],
                }],
            },
        }
        normalized = MODULE.normalize_analysis(payload)
        cluster = normalized["viewpoints"]["by_topic"][0]["clusters"][0]
        self.assertEqual(
            "甲研究院认为，政策实施应强化跨部门协同。李明指出应建立长效评估机制。",
            cluster["details"],
        )
        self.assertEqual(
            "deterministic_from_atomic_claims",
            normalized["metadata"]["writing_assembly"],
        )


if __name__ == "__main__":
    unittest.main()
