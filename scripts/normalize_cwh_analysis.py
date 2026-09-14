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
from cwh_writing_rules import source_rank, writing_rules, writing_rules_sha256


STANCE_RE = re.compile("^(?:" + "|".join(re.escape(value) for value in writing_rules()["viewpoint"]["attribution_verbs"]) + ")")


def clean_sentence(value: Any) -> str:
    text = re.sub(r"\s+", "", str(value or "").strip())
    return text.rstrip("。；;，,")


def judgment_heading(value: Any) -> str:
    """Use a neutral reported-judgment frame, never invent approval or criticism."""
    heading = str(value or "").strip().rstrip("。；;")
    stances = tuple(writing_rules()["viewpoint"]["heading_stance_verbs"])
    if not heading or heading.startswith(stances) or any(marker in heading for marker in ("尚未形成评论性观点", "以事实性报道为主")):
        return heading
    return writing_rules()["viewpoint"]["default_attribution_verb"] + heading


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
    if not subject or claim.startswith(subject):
        return claim
    name = clean_sentence(row.get("speaker_name"))
    # Expand an existing exact name-only attribution; preserve the atomic claim
    # and its attribution verb, rather than introducing a second attribution.
    if name and subject.endswith(name) and claim.startswith(name) and STANCE_RE.match(claim[len(name):]):
        return subject + claim[len(name):]
    if STANCE_RE.match(claim):
        return f"{subject}{claim}"
    verb = writing_rules()["viewpoint"]["default_attribution_verb"]
    return f"{subject}{verb}，{claim}"


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
        topic["heading"] = judgment_heading(topic.get("heading"))
        for cluster in topic.get("clusters") or []:
            if not isinstance(cluster, dict):
                continue
            cluster["summary"] = judgment_heading(cluster.get("summary"))
            # Python's stable sort preserves source order within the same
            # priority class. Only explicit source metadata changes priority.
            cluster["evidence"] = sorted(cluster.get("evidence") or [], key=lambda row: source_rank(row) if isinstance(row, dict) else 999)
            details = assemble_cluster_details(cluster)
            cluster["details"] = details
            cluster.pop("analysis", None)
    metadata = data.setdefault("metadata", {})
    metadata["writing_contract_version"] = "formal-writing-rules.v1"
    metadata["writing_assembly"] = "deterministic_from_atomic_claims"
    metadata["writing_rules_sha256"] = writing_rules_sha256()
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
