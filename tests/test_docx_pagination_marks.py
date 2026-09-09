from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "formalize_cwh_report.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("formalize_cwh_report_for_pagination_test", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class DocxPaginationMarkTests(unittest.TestCase):
    def test_nonprinting_black_square_properties_are_removed(self) -> None:
        document = Document()
        paragraph = document.add_paragraph("测试正文")
        paragraph.paragraph_format.keep_with_next = True
        paragraph.paragraph_format.keep_together = True
        paragraph.paragraph_format.page_break_before = True
        document.styles["Heading 1"].paragraph_format.keep_with_next = True

        MODULE.remove_nonprinting_pagination_controls(document)

        for root in (document._element, document.styles.element):
            self.assertEqual([], list(root.iter(qn("w:keepNext"))))
            self.assertEqual([], list(root.iter(qn("w:keepLines"))))
            self.assertEqual([], list(root.iter(qn("w:pageBreakBefore"))))


if __name__ == "__main__":
    unittest.main()
