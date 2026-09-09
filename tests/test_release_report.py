import base64
import json
from pathlib import Path
import sys
import zipfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from verify_release_report import verify


def seed(tmp_path):
    (tmp_path / "charts").mkdir()
    images = {}
    with zipfile.ZipFile(tmp_path / "cwh_formal_report.docx", "w") as archive:
        for label, file in [("trend", "trend_distribution_system.png"), ("topic", "topic_distribution_system.png"), ("hotword", "hotword_distribution_pipeline.png")]:
            payload = ("approved-" + label).encode()
            (tmp_path / "charts" / file).write_bytes(payload)
            archive.writestr("word/media/" + file, payload)
            images[label] = "data:image/png;base64," + base64.b64encode(payload).decode()
    (tmp_path / "report_data.json").write_text('{"meeting":{"date":"2026-07-10"},"hotwords":[]}', encoding="utf-8")
    (tmp_path / "cwh_dashboard.html").write_text('<script id="dashboard-data">' + json.dumps({"images": images}) + '</script>', encoding="utf-8")
    return tmp_path


def test_release_accepts_identical_approved_charts(tmp_path):
    assert verify(seed(tmp_path))["passed"]


def test_release_blocks_missing_wordcloud(tmp_path):
    directory = seed(tmp_path)
    (directory / "charts/hotword_distribution_pipeline.png").unlink()
    with pytest.raises(ValueError, match="Missing required approved chart"):
        verify(directory)


def test_release_blocks_silently_replaced_wordcloud(tmp_path):
    directory = seed(tmp_path)
    (directory / "charts/hotword_distribution_pipeline.png").write_bytes(b"unapproved fallback")
    with pytest.raises(ValueError, match="Dashboard does not contain approved"):
        verify(directory)
