"""The raw entrance must hand off actual packets, not the audit directory."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_cwh_resumable_pipeline as pipeline
import cwh_hotword_pipeline as hotwords
import cwh_preflight as preflight


def setup_raw(tmp_path):
    metadata = tmp_path / "metadata.json"
    metadata.write_text("{}", encoding="utf-8")
    return pipeline.CwhPipeline(tmp_path / "job", {
        "execution_profile": "bounded_60m", "metadata": str(metadata),
        "raw_input_dir": str(tmp_path),
    })


def test_raw_failure_emits_waiting_task_with_actual_packet_paths(tmp_path, monkeypatch):
    instance = setup_raw(tmp_path)
    def command(*args, **kwargs):
        for name in ("hotword", "overseas", "public_top"):
            pipeline.atomic_write_json(instance.artifacts / "run" / f"{name}_review_packet.json", {"kind": name})
        return 1, "review-required.log"
    monkeypatch.setattr(instance.runner, "run_command", command)
    outcome = instance.workbook(instance.runner, instance.runner.spec_by_id["workbook"])
    assert outcome.status == "waiting_ai"
    task = json.loads(Path(outcome.details["task"]).read_text(encoding="utf-8"))
    for name in ("hotword", "overseas", "public_top"):
        path = Path(task["inputs"][name])
        assert path.is_file() and path.parent == instance.artifacts / "run"


def test_raw_success_copies_full_corpus_to_downstream_location(tmp_path, monkeypatch):
    instance = setup_raw(tmp_path)
    content = {"candidates": [{"record_id": "a1", "content": "完整原文"}]}
    def command(*args, **kwargs):
        (instance.artifacts / "CWH舆情情况_标准总表.xlsx").write_bytes(b"test")
        pipeline.atomic_write_json(instance.artifacts / "run" / "public_article_evidence.json", content)
        return 0, "ok.log"
    monkeypatch.setattr(instance.runner, "run_command", command)
    outcome = instance.workbook(instance.runner, instance.runner.spec_by_id["workbook"])
    assert outcome.status == "succeeded"
    assert json.loads((instance.artifacts / "public_article_evidence.json").read_text(encoding="utf-8")) == content


def test_rejected_raw_review_does_not_recurse_forever(tmp_path, monkeypatch):
    instance = setup_raw(tmp_path)
    calls = []
    def command(*args, **kwargs):
        calls.append(1)
        pipeline.atomic_write_json(instance.artifacts / "run" / "hotword_review_packet.json", {})
        return 1, "bad-review.log"
    def worker(*args, **kwargs):
        for name in ("hotword", "overseas", "public_top"):
            pipeline.atomic_write_json(instance.artifacts / f"{name}_ai_review.json", {"invalid": True})
    monkeypatch.setattr(instance.runner, "run_command", command)
    monkeypatch.setattr(pipeline, "maybe_run_ai_worker", worker)
    outcome = instance.workbook(instance.runner, instance.runner.spec_by_id["workbook"])
    assert outcome.status == "failed" and outcome.error_code == "raw_review_rejected"
    assert len(calls) == 2


def test_preflight_checks_raw_runtime_dependencies():
    assert {"numpy", "PIL", "openpyxl", "docx"} <= set(preflight.REQUIRED_MODULES)


def test_cached_candidate_decisions_equal_uncached_rules():
    words = ["城市更新", "教育公平", "国务", "的建设", "啊啊", "跨区域服务", "A+B", ""] * 3
    hotwords.valid_candidate.cache_clear()
    assert [hotwords.valid_candidate(x) for x in words] == [hotwords.valid_candidate.__wrapped__(x) for x in words]
    assert hotwords.valid_candidate.cache_info().hits >= len(words) - 8


def test_small_wordcloud_font_never_calls_identity_native_filter(monkeypatch):
    from PIL import ImageFont
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 10) if sys.platform == "win32" else ImageFont.load_default()
    monkeypatch.setattr(hotwords.ImageFont, "truetype", lambda *args, **kwargs: font)
    original = hotwords.ImageFilter.MaxFilter
    def checked(size):
        assert size > 1
        return original(size)
    monkeypatch.setattr(hotwords.ImageFilter, "MaxFilter", checked)
    image, mask = hotwords._july19_text_sprite("ABC", Path("unused.ttf"), 10, "#0D4E6D", -15)
    assert image.width > 0 and mask.any()
