"""Mechanical completion cannot invent or certify evidence."""
import copy
import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from complete_cwh_evidence_structure import complete_analysis_structure


def draft():
    candidate = {
        "url": "https://example.test/article", "title": "测试原文", "source": "测试来源",
        "speaker_name": "测试发言人",
        "source_snapshot": {"url": "https://example.test/article", "title": "测试原文",
                            "source_text": "前文。保留全部限定条件的原文。后文。"},
    }
    evidence = {"url": candidate["url"], "source": candidate["source"],
                "speaker_name": candidate["speaker_name"],
                "source_excerpt": "保留全部限定条件的原文。", "formal_claim": "依据原文表述的判断。"}
    return {"research_audit": {"domestic_media_research": {
        "candidate_pool_by_topic": [{"topic": "议题", "candidates": [candidate]}]}},
        "viewpoints": {"by_topic": [{"topic": "议题", "clusters": [{"evidence": [evidence]}]}]}}


def rows(data):
    return (data["research_audit"]["domestic_media_research"]["candidate_pool_by_topic"][0]["candidates"],
            data["viewpoints"]["by_topic"][0]["clusters"][0]["evidence"])


def test_completion_is_idempotent_and_does_not_mutate_source():
    original = draft()
    saved = copy.deepcopy(original)
    completed = complete_analysis_structure(original)
    assert original == saved
    assert complete_analysis_structure(completed) == completed
    candidates, evidence = rows(completed)
    snapshot = candidates[0]["source_snapshot"]
    assert snapshot["source_text_sha256"] == hashlib.sha256(snapshot["source_text"].encode()).hexdigest()
    assert evidence[0]["candidate_id"] == candidates[0]["candidate_id"]
    assert evidence[0]["source_snapshot_id"] == snapshot["snapshot_id"]
    assert snapshot["source_text"][evidence[0]["source_excerpt_start"]:evidence[0]["source_excerpt_end"]] == evidence[0]["source_excerpt"]
    assert evidence[0]["evidence_id"].startswith("evidence-")
    assert "semantic_review" not in evidence[0]


def test_order_does_not_change_ids():
    original = draft()
    candidates, _ = rows(original)
    second = copy.deepcopy(candidates[0])
    second["url"] += "/other"
    candidates.append(second)
    left = complete_analysis_structure(original)
    candidates.reverse()
    right = complete_analysis_structure(original)
    assert rows(left)[0][0]["candidate_id"] == rows(right)[0][1]["candidate_id"]
    assert rows(left)[1] == rows(right)[1]


def test_duplicate_candidates_are_not_arbitrarily_linked():
    original = draft()
    candidates, _ = rows(original)
    candidates.append(copy.deepcopy(candidates[0]))
    _, evidence = rows(complete_analysis_structure(original))
    assert "candidate_id" not in evidence[0]
    assert "evidence_id" not in evidence[0]


def test_repeated_excerpt_does_not_get_guessed_offsets():
    original = draft()
    candidates, _ = rows(original)
    candidates[0]["source_snapshot"]["source_text"] *= 2
    _, evidence = rows(complete_analysis_structure(original))
    assert "source_excerpt_start" not in evidence[0]
    assert "source_excerpt_end" not in evidence[0]


def test_existing_invalid_fields_are_preserved_for_validator():
    original = draft()
    candidates, evidence = rows(original)
    candidates[0]["source_snapshot"]["source_text_sha256"] = "wrong-hash"
    evidence[0]["source_excerpt_start"] = 999
    evidence[0]["source_snapshot_id"] = "wrong-snapshot"
    completed_candidates, completed_evidence = rows(complete_analysis_structure(original))
    assert completed_candidates[0]["source_snapshot"]["source_text_sha256"] == "wrong-hash"
    assert completed_evidence[0]["source_excerpt_start"] == 999
    assert completed_evidence[0]["source_snapshot_id"] == "wrong-snapshot"


def test_conflicting_identity_is_not_linked():
    original = draft()
    _, evidence = rows(original)
    evidence[0]["speaker_name"] = "不同发言人"
    _, completed = rows(complete_analysis_structure(original))
    assert "candidate_id" not in completed[0]


def test_missing_original_is_not_invented():
    original = draft()
    candidates, _ = rows(original)
    del candidates[0]["source_snapshot"]["source_text"]
    completed_candidates, completed_evidence = rows(complete_analysis_structure(original))
    assert "source_text" not in completed_candidates[0]["source_snapshot"]
    assert "candidate_id" not in completed_evidence[0]


def test_raw_hydration_preserves_identity_and_records_host_capture():
    original = draft()
    candidates, evidence = rows(original)
    candidates[0] = {"raw_evidence_record_id": "raw-1"}
    raw = {"record_id": "raw-1", "url": "https://example.test/article", "title": "测试原文", "source": "测试来源",
           "account": "真实账号", "published_at": "2026-05-16", "content": "前文。保留全部限定条件的原文。后文。"}
    completed = complete_analysis_structure(original, {"candidates": [raw]})
    candidate = rows(completed)[0][0]
    assert candidate["account"] == "真实账号"
    assert candidate["source_snapshot"]["capture_method"] == "monitoring_export"
    assert candidate["source_snapshot"]["captured_at"]
    assert complete_analysis_structure(completed, {"candidates": [raw]}) == completed


@pytest.mark.parametrize("marker", ["metadata", "evidence"])
def test_frozen_reviewed_bundles_are_refused(marker):
    original = draft()
    if marker == "metadata":
        original["metadata"] = {"semantic_review_packet_sha256": "frozen"}
    else:
        rows(original)[1][0]["semantic_review"] = {"review_pass": "independent_second_pass"}
    with pytest.raises(ValueError, match="Frozen"):
        complete_analysis_structure(original)
