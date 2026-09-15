"""Deterministic font/layout checks; not a rendered Word pagination certificate."""
from pathlib import Path
import sys

from docx import Document
from docx.shared import Inches
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import cwh_hotword_pipeline as hotwords
from formalize_cwh_report import add_centered_picture


def test_process_font_override_precedes_package_fallback(monkeypatch, tmp_path):
    approved = tmp_path / 'approved-font.otf'
    approved.touch()
    monkeypatch.setenv('CWH_CJK_FONT', str(approved))
    assert hotwords.resolve_font(None) == approved
    assert '第九周' not in str(hotwords.DEFAULT_FONT_PATH)


def test_inline_cloud_preserves_aspect_ratio_and_caps_height(tmp_path):
    fixture = tmp_path / 'image.png'
    Image.new('RGB', (1600, 1000), 'white').save(fixture)
    doc = Document()
    shape = add_centered_picture(doc, str(fixture), Inches(5.8), '词云', max_height=Inches(3.0))
    assert shape.height == Inches(3.0)
    assert abs(shape.width / shape.height - 1.6) < 1e-5
    assert doc.paragraphs[-1].paragraph_format.line_spacing == 1
    assert not doc.paragraphs[-1]._p.xpath('.//w:br')


def test_cloud_limits_do_not_enlarge_small_graphics(tmp_path):
    fixture = tmp_path / 'small.png'
    Image.new('RGB', (1600, 1000), 'white').save(fixture)
    doc = Document()
    shape = add_centered_picture(doc, str(fixture), Inches(2), '词云', max_height=Inches(3.0))
    assert shape.width == Inches(2)
