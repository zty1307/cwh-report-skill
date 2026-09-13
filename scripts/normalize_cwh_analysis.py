#!/usr/bin/env python3
"""Mechanically assemble formal viewpoint prose from reviewed atomic evidence.

The model is responsible for evidence selection and faithful ``formal_claim``
values.  This module owns the repetitive report wording so different model
families cannot silently change attribution style, ordering, or punctuation.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from cwh_pipeline_runtime import atomic_write_json


STANCE_RE = re.compile(r"^(认为|指出|建议|强调|表示|称|提出|研判|预计|呼吁|担忧|主张)")


def clean_sentence(value: Any) -> str:
    text = re.sub(r"\s+", "", str(value or "").strip())
    return text.rstrip("。；;，,")


def evidence_sentence(row: dict[str, Any]) -> str:
    claim = clean_sentence(row.get("formal_claim"))
    if not claim:
        return ""
    subject = clean_sentence(
        row.get("attribution")
        or row.get("speaker_name")
        or row.get("source")
        or row.get("platform")
    )
    if not subject or subject in claim:
        return claim
    if STANCE_RE.match(claim):
        return f"{subject}{claim}"
    return f"{subject}认为，{claim}"


def assemble_cluster_details(cluster: dict[str, Any]) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for row in cluster.get("evidence") or []:
        if not isinstance(row, dict):
            continue
        sentence = evidence_sentence(row)
        signature = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", sentence).lower()
        if not sentence or not signature or signature in seen:
            continue
        seen.add(signature)
        parts.append(sentence)
    return "。".join(parts) + ("。" if parts else "")


def normalize_analysis(data: dict[str, Any]) -> dict[str, Any]:
    for topic in ((data.get("viewpoints") or {}).get("by_topic") or []):
        if not isinstance(topic, dict):
            continue
        for cluster in topic.get("clusters") or []:
            if not isinstance(cluster, dict):
                continue
            details = assemble_cluster_details(cluster)
            if details:
                cluster["details"] = details
                cluster.pop("analysis", None)
    metadata = data.setdefault("metadata", {})
    metadata["writing_contract_version"] = "formal-writing-rules.v1"
    metadata["writing_assembly"] = "deterministic_from_atomic_claims"
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize CWH analysis prose deterministically.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="", help="Defaults to in-place update of --input.")
    args = parser.parse_args()
    source = Path(args.input).resolve()
    target = Path(args.output).resolve() if args.output else source
    data = json.loads(source.read_text(encoding="utf-8"))
    atomic_write_json(target, normalize_analysis(data))
    print(json.dumps({"status": "ok", "output": str(target)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
