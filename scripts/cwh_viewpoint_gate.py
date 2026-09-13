"""Shared density decision for draft validation and final delivery auditing.

This gate does not replace candidate provenance or independent semantic review.
An audited exception only waives aggregate cluster density, never those gates.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache(maxsize=1)
def density_policy() -> dict[str, Any]:
    path = Path(__file__).resolve().parent.parent / "config/formal_writing_rules.v1.json"
    return json.loads(path.read_text(encoding="utf-8"))["viewpoint"]["density_gate"]


def cluster_density_result(cluster: dict[str, Any]) -> dict[str, Any]:
    policy = density_policy()
    evidence = [row for row in cluster.get("evidence") or [] if isinstance(row, dict)]
    # A repeated speaker is one voice even across several URLs, claims or verbs.
    voices = {
        re.sub(r"\s+", "", str(row.get("speaker_name") or row.get("attribution") or row.get("source") or "")).casefold()
        for row in evidence
    } - {""}
    details = str(cluster.get("details") or "").strip()
    cjk_length = len(re.findall(r"[\u4e00-\u9fff]", details))
    exception = cluster.get("thin_cluster_exception")
    valid_exception = isinstance(exception, dict) and all(
        isinstance(exception.get(key), str) and exception[key].strip()
        for key in policy["exception_required_fields"]
    )
    thin = len(voices) < policy["minimum_independent_voices"] or cjk_length < policy["minimum_details_cjk"]
    # No evidence or empty prose cannot be excused as merely thin evidence.
    has_content = bool(voices) and cjk_length > 0
    accepted_exception = bool(has_content and thin and valid_exception)
    passed = bool(has_content and (not thin or accepted_exception))
    return {
        "passed": passed,
        "independent_voices": len(voices),
        "details_cjk": cjk_length,
        "accepted_exception": exception if accepted_exception else None,
        "message": "" if passed else (
            f"成文密度门禁：{len(voices)}个独立声音、{cjk_length}个汉字；"
            f"要求至少{policy['minimum_independent_voices']}个独立声音和"
            f"{policy['minimum_details_cjk']}个汉字，或提供完整thin_cluster_exception"
            "（reason、search_evidence、reviewed_by）；无证据或空正文不能例外放行。"
        ),
    }
