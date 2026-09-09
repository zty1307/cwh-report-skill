from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_with_app_bundle.py"
SPEC = importlib.util.spec_from_file_location("build_with_app_bundle", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class WithBundleSeedTests(unittest.TestCase):
    def test_seed_dashboard_is_rebuilt_with_current_generator(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            source = base / "source"
            target = base / "target"
            source.mkdir()
            (source / "report_data.json").write_text("{}", encoding="utf-8")
            (source / "cwh_formal_report.docx").write_bytes(b"docx")
            (source / "cwh_dashboard.html").write_text("old snapshot", encoding="utf-8")
            generator = base / "generate_dashboard.py"
            generator.write_text("# generator", encoding="utf-8")

            with mock.patch.object(MODULE.subprocess, "run") as run:
                MODULE.copy_report_seed(
                    source,
                    target,
                    require_dashboard=True,
                    dashboard_generator=generator,
                )

            run.assert_called_once()
            command = run.call_args.args[0]
            self.assertEqual(Path(command[1]), generator)
            self.assertEqual(Path(command[-1]), target / "cwh_dashboard.html")
            self.assertTrue(run.call_args.kwargs["check"])


if __name__ == "__main__":
    unittest.main()
