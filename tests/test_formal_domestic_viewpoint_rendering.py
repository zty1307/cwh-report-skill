from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
MODULE_PATH = ROOT / "scripts" / "formalize_cwh_report.py"
SPEC = importlib.util.spec_from_file_location("cwh_formalize_domestic", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_duplicate_supporting_pages_do_not_repeat_formal_claim() -> None:
    claim = "仇童伟认为，农业农村领域十五五规划为未来五年制定了施工图，并释放农业农村优先发展的鲜明信号。"
    evidence = [
        {
            "attribution": "南京农业大学金善宝农业现代化发展研究院研究员仇童伟",
            "formal_claim": claim,
            "supporting_samples": [
                {"source": "新华网", "url": "https://example.test/1", "claim": claim},
                {"source": "东方财富网", "url": "https://example.test/2", "claim": claim},
                {"source": "中国农业农村信息网", "url": "https://example.test/3", "claim": claim},
            ],
        }
    ]

    rendered = MODULE.evidence_text(evidence)

    assert rendered.count("仇童伟") == 1
    assert rendered.startswith("南京农业大学金善宝农业现代化发展研究院研究员仇童伟认为")
    assert "新华网" not in rendered
    assert "东方财富网" not in rendered


def test_cluster_fallback_uses_concrete_voice_not_source_list() -> None:
    rendered = MODULE.cluster_wording(
        {
            "summary": "认为城市更新应转向品质提升",
            "evidence": [
                {
                    "source": "深视新闻",
                    "attribution": "深视新闻",
                    "formal_claim": "深视新闻认为，各地应通过精耕细作推进城市结构优化和品质提升。",
                }
            ],
        }
    )

    assert "深视新闻认为" in rendered
    assert "样本来源" not in rendered
    assert "代表性公开证据包括" not in rendered
