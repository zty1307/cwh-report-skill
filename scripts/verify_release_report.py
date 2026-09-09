"""Fail release validation when an approved chart is missing or changed."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import zipfile

from domestic_evidence_mapping import mapping_problem_messages, validate_release_mapping


def verify(directory: Path) -> dict:
    data = json.loads((directory / "report_data.json").read_text(encoding="utf-8"))
    html = (directory / "cwh_dashboard.html").read_text(encoding="utf-8")
    match = re.search(r'<script[^>]+id="dashboard-data"[^>]*>(.*?)</script>', html, re.S)
    if not match:
        raise ValueError("Dashboard structured data is missing")
    dashboard = json.loads(match.group(1))
    hashes = {}
    with zipfile.ZipFile(directory / "cwh_formal_report.docx") as docx:
        image_hashes = {hashlib.sha256(docx.read(name)).hexdigest() for name in docx.namelist() if name.startswith("word/media/")}
    for kind, label, filename in [
        ("trend_distribution", "trend", "trend_distribution_system.png"),
        ("topic_distribution", "topic", "topic_distribution_system.png"),
        ("hotword_distribution", "hotword", "hotword_distribution_pipeline.png"),
    ]:
        image = directory / "charts" / filename
        if not image.is_file() or not image.stat().st_size:
            raise ValueError(f"Missing required approved chart: {image}")
        digest = hashlib.sha256(image.read_bytes()).hexdigest()
        embedded = str(dashboard.get("images", {}).get(label) or "")
        if ";base64," not in embedded or hashlib.sha256(base64.b64decode(embedded.split(",", 1)[1])).hexdigest() != digest:
            raise ValueError(f"Dashboard does not contain approved {kind}")
        if digest not in image_hashes:
            raise ValueError(f"Word does not contain approved {kind}")
        hashes[kind] = digest
    mapping_audit = None
    analysis_metadata = ((data.get("analysis_bundle") or {}).get("metadata") or {})
    if str(analysis_metadata.get("evidence_mapping_version") or "").strip():
        mapping_audit = validate_release_mapping(directory)
        mapping_problems = mapping_problem_messages(mapping_audit)
        if mapping_problems:
            raise ValueError("Domestic evidence mapping failed: " + "; ".join(mapping_problems[:12]))
    return {
        "passed": True,
        "meeting_date": (data.get("meeting") or {}).get("date"),
        "hotword_count": len(data.get("hotwords") or []),
        "chart_sha256": hashes,
        "domestic_evidence_mapping": mapping_audit or {"status": "legacy_unmapped"},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_dir", type=Path)
    print(json.dumps(verify(parser.parse_args().report_dir), ensure_ascii=False, indent=2))
