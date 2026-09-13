"""Fill missing mechanical evidence fields in a draft, never certify source facts.

Only exact input strings enter identifiers and offsets. Existing values, even
invalid ones, are left for the mapping validator. No fuzzy matching is used.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from cwh_pipeline_runtime import atomic_write_json


def _string(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _missing(row: dict[str, Any], field: str) -> bool:
    return field not in row or row[field] is None or row[field] == ""


def _id(prefix: str, *parts: str) -> str:
    encoded = json.dumps(parts, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return prefix + hashlib.sha256(encoded).hexdigest()


def _rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _speaker(row: dict[str, Any]) -> str:
    return next((_string(row.get(key)) for key in ("speaker_name", "voice_name", "voice") if _string(row.get(key))), "")


def _evidence_rows(data: dict[str, Any]):
    for topic in _rows(_object(data.get("viewpoints")).get("by_topic")):
        for cluster in _rows(topic.get("clusters")):
            for evidence in _rows(cluster.get("evidence")):
                yield _string(topic.get("topic")), evidence


def _matches(candidate: dict[str, Any], evidence: dict[str, Any]) -> bool:
    url = _string(evidence.get("url"))
    if not url or url != _string(candidate.get("url")):
        return False
    # Compare every supplied identity field. Absent fields do not justify a
    # guessed identity; multiple remaining candidates remain ambiguous.
    pairs = [
        (_string(candidate.get("source")), _string(evidence.get("source"))),
        (_string(candidate.get("title")), _string(evidence.get("article_title") or evidence.get("title"))),
        (_speaker(candidate), _speaker(evidence)),
    ]
    return not any(left and right and left != right for left, right in pairs)


def complete_analysis_structure(data: dict[str, Any]) -> dict[str, Any]:
    """Return a completed copy; ambiguous or inconsistent source fields survive.

    Call once on the authoring draft, before prose normalization and hashing for
    the independent review. Verified bundles are deliberately refused.
    """
    if not isinstance(data, dict):
        raise ValueError("analysis must be a JSON object")
    metadata = _object(data.get("metadata"))
    if metadata.get("semantic_review_packet_sha256") or any(
        _object(row.get("semantic_review")).get("review_pass") == "independent_second_pass"
        for _, row in _evidence_rows(data)
    ):
        raise ValueError("Frozen independently reviewed bundles cannot be structurally completed")
    result = copy.deepcopy(data)
    research = _object(_object(result.get("research_audit")).get("domestic_media_research"))
    candidates_by_topic: dict[str, list[dict[str, Any]]] = {}
    for pool in _rows(research.get("candidate_pool_by_topic")):
        topic = _string(pool.get("topic"))
        candidates = _rows(pool.get("candidates"))
        candidates_by_topic.setdefault(topic, []).extend(candidates)
        for candidate in candidates:
            snapshot = _object(candidate.get("source_snapshot"))
            text = _string(snapshot.get("source_text"))
            if not text.strip():
                continue
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if _missing(snapshot, "source_text_sha256"):
                snapshot["source_text_sha256"] = digest
            snapshot_url, snapshot_title = _string(snapshot.get("url")), _string(snapshot.get("title"))
            if snapshot_url and snapshot_title and _missing(snapshot, "snapshot_id"):
                snapshot["snapshot_id"] = _id("snapshot-", snapshot_url, snapshot_title, digest)
            url, title, source = (_string(candidate.get(key)) for key in ("url", "title", "source"))
            if topic and url and title and source and _missing(candidate, "candidate_id"):
                candidate["candidate_id"] = _id("candidate-", topic, url, title, source, _speaker(candidate), digest)

    for topic, evidence in _evidence_rows(result):
        candidates = candidates_by_topic.get(topic, []) if topic else []
        if _missing(evidence, "candidate_id"):
            matches = [row for row in candidates if _matches(row, evidence)]
            if len(matches) == 1 and _string(matches[0].get("candidate_id")):
                evidence["candidate_id"] = matches[0]["candidate_id"]
        candidate_id = _string(evidence.get("candidate_id"))
        matches = [row for row in candidates if candidate_id and row.get("candidate_id") == candidate_id]
        # Never choose the first row when duplicate IDs or URLs make identity
        # ambiguous. Existing inconsistent IDs are not silently repaired.
        if len(matches) != 1 or not _matches(matches[0], evidence):
            continue
        candidate = matches[0]
        snapshot = _object(candidate.get("source_snapshot"))
        snapshot_id = _string(snapshot.get("snapshot_id"))
        text, excerpt = _string(snapshot.get("source_text")), _string(evidence.get("source_excerpt"))
        if snapshot_id and _missing(evidence, "source_snapshot_id"):
            evidence["source_snapshot_id"] = snapshot_id
        if text and excerpt:
            start = text.find(excerpt)
            if start >= 0 and text.find(excerpt, start + 1) < 0:
                for field, value in (("source_excerpt_start", start), ("source_excerpt_end", start + len(excerpt))):
                    if _missing(evidence, field):
                        evidence[field] = value
        speaker, claim = _speaker(evidence), _string(evidence.get("formal_claim"))
        if snapshot_id and excerpt and speaker and claim and _missing(evidence, "evidence_id"):
            evidence["evidence_id"] = _id("evidence-", topic, candidate_id, snapshot_id, speaker, excerpt, claim)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Complete missing mechanical fields in a CWH authoring draft.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    source, target = Path(args.input).resolve(), Path(args.output).resolve()
    if any("verified" in path.stem.lower() or path.name == "report_data.json" for path in (source, target)):
        parser.error("Use an authoring draft path, never a verified or rendered artifact")
    payload = json.loads(source.read_text(encoding="utf-8"))
    atomic_write_json(target, complete_analysis_structure(payload))
    print(json.dumps({"status": "structure_completed_not_verified", "output": str(target)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
