from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_readonly_dashboard_demo.py"
SPEC = importlib.util.spec_from_file_location("build_readonly_dashboard_demo", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ReadonlyDashboardDemoTests(unittest.TestCase):
    def test_builds_sanitized_single_file_package(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "dashboard.html"
            data = {
                "title": "测试报告",
                "source_path": r"D:\Codex\CWH\outputs\report_data.json",
                "artifacts": {
                    "word": {
                        "path": r"D:\Codex\CWH\outputs\report.docx",
                        "href": "file:///D:/Codex/CWH/outputs/report.docx",
                        "protocol": "ms-word:ofe|u|file:///D:/Codex/CWH/outputs/report.docx",
                    }
                },
            }
            source.write_text(
                "<!doctype html><title>CWH舆情报告工作台</title>"
                '<script id="dashboard-data" type="application/json">'
                + json.dumps(data, ensure_ascii=False)
                + "</script><script>"
                "const DEMO_MODE=new URLSearchParams(location.search).get('demo')==='1';"
                "async function callApi(){return fetch('/api/reports')}"
                "</script>",
                encoding="utf-8",
            )

            index_path, archive_path = MODULE.build_demo(source, root / "readonly")
            html = index_path.read_text(encoding="utf-8")

            self.assertIn("const DEMO_MODE=true;", html)
            self.assertIn("readonlyFetch('/api/reports')", html)
            self.assertNotIn("return fetch(", html)
            self.assertNotIn(r"D:\Codex", html)
            self.assertNotIn("file:///D:/", html)
            self.assertIn("只读演示不提供本机文件", html)
            with zipfile.ZipFile(archive_path) as archive:
                self.assertEqual(archive.namelist(), ["index.html"])


if __name__ == "__main__":
    unittest.main()
