"""The same workbench asset renders different periods without model code."""
import copy
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from cwh_preflight import run_preflight
from generate_dashboard import TEMPLATE_PATH, generate_dashboard


def test_fixed_template_reuses_layout_preserves_mapping_and_escapes_data(tmp_path):
    template_before = TEMPLATE_PATH.read_bytes()
    report = {"meeting": {"meeting_date": "2026-01-02", "agenda": "研究测试工作"},
              "analysis_bundle": {"metadata": {"evidence_mapping_version": "1.0"},
                                  "sentinel": "</script><script>bad()</script>"}}
    original = copy.deepcopy(report)
    output = generate_dashboard(report, tmp_path / "workbench.html")
    first = output.read_bytes()
    generate_dashboard(report, output)
    assert output.read_bytes() == first
    assert report == original
    assert TEMPLATE_PATH.read_bytes() == template_before
    html = first.decode("utf-8")
    payload = json.loads(re.search(r'<script id="dashboard-data" type="application/json">(.*?)</script>', html, re.S).group(1))
    assert payload["analysis_bundle"] == report["analysis_bundle"]
    assert "</script><script>bad()</script>" not in html
    assert "__DASHBOARD_DATA__" not in html
    report["analysis_bundle"]["sentinel"] = "全新一期的独立数据"
    generate_dashboard(report, output)
    assert output.read_bytes() != first
    assert "bad()" not in output.read_text(encoding="utf-8")
    assert TEMPLATE_PATH.read_bytes() == template_before


@pytest.mark.parametrize("template_text", [None, "missing data slot", "__DASHBOARD_DATA____DASHBOARD_DATA__", "__DASHBOARD_DATA__"])
def test_preflight_catches_missing_or_ambiguous_workbench_template(tmp_path, template_text):
    if template_text is not None:
        (tmp_path / "assets").mkdir()
        (tmp_path / "assets/cwh_dashboard_template.html").write_text(template_text, encoding="utf-8")
    checks = {row["id"]: row for row in run_preflight(tmp_path)["checks"]}
    assert checks["template:dashboard_data_slot"]["status"] == ("passed" if template_text == "__DASHBOARD_DATA__" else "failed")
