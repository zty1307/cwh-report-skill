from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import zipfile


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR)) if str(SCRIPT_DIR) not in sys.path else None

from domestic_evidence_mapping import (  # noqa: E402
    apply_semantic_review_packet,
    mapping_problem_messages,
    validate_analysis_mapping,
    validate_release_mapping,
)


def valid_bundle() -> dict:
    source_text = "中指研究院研究总监吴建钦认为，城市更新已经成为中央常态化关注和推动的重大事项，国家层面专项规划将衔接目标、政策和实施机制。"
    excerpt = source_text
    claim = "城市更新已经成为中央常态化关注和推动的重大事项，国家层面专项规划将衔接目标、政策和实施机制。"
    return {
        "metadata": {"evidence_mapping_version": "1.0", "authoring_run_id": "author-run-1"},
        "research_audit": {
            "domestic_media_research": {
                "candidate_pool_by_topic": [
                    {
                        "topic": "城市更新",
                        "candidates": [
                            {
                                "candidate_id": "candidate-1",
                                "decision": "eligible",
                                "source": "中指研究院",
                                "title": "利好来了，国常会重磅部署",
                                "url": "https://example.com/city",
                                "source_snapshot": {
                                    "snapshot_id": "snapshot-1",
                                    "url": "https://example.com/city",
                                    "title": "利好来了，国常会重磅部署",
                                    "captured_at": "2026-05-15T18:00:00+08:00",
                                    "capture_method": "browser_article_text",
                                    "source_text": source_text,
                                    "source_text_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
                                },
                            }
                        ],
                    }
                ]
            }
        },
        "viewpoints": {
            "by_topic": [
                {
                    "topic": "城市更新",
                    "clusters": [
                        {
                            "details": f"中指研究院研究总监吴建钦认为，{claim}",
                            "evidence": [
                                {
                                    "evidence_id": "evidence-1",
                                    "candidate_id": "candidate-1",
                                    "source_snapshot_id": "snapshot-1",
                                    "url": "https://example.com/city",
                                    "article_title": "利好来了，国常会重磅部署",
                                    "attribution": "中指研究院研究总监吴建钦",
                                    "attribution_status": "named_person",
                                    "speaker_name": "吴建钦",
                                    "speaker_role": "中指研究院研究总监",
                                    "source_excerpt": excerpt,
                                    "source_excerpt_start": 0,
                                    "source_excerpt_end": len(source_text),
                                    "formal_claim": claim,
                                    "wording_fidelity": "lightly_trimmed",
                                    "selection_reason": "包含完整独立观点。",
                                    "semantic_review": {
                                        "verdict": "fully_supported",
                                        "reviewed_by": "approved-model",
                                        "reviewed_at": "2026-05-15T18:10:00+08:00",
                                        "rationale": "人物、判断和规划作用均由连续原文支持。",
                                        "propositions": [
                                            {
                                                "text": claim,
                                                "verdict": "fully_supported",
                                                "source_quote": excerpt,
                                                "source_quote_start": 0,
                                                "source_quote_end": len(source_text),
                                                "rationale": "连续原文直接支持。",
                                            }
                                        ],
                                    },
                                }
                            ],
                        }
                    ],
                }
            ]
        },
    }


def test_valid_mapping_passes() -> None:
    audit = validate_analysis_mapping(valid_bundle())
    assert audit["status"] == "passed"
    assert audit["mapped_evidence_count"] == 1
    assert audit["eligible_candidate_count"] == 1


def test_tampered_snapshot_and_excerpt_are_blocked() -> None:
    bundle = valid_bundle()
    candidate = bundle["research_audit"]["domestic_media_research"]["candidate_pool_by_topic"][0]["candidates"][0]
    candidate["source_snapshot"]["source_text"] += "被修改"
    evidence = bundle["viewpoints"]["by_topic"][0]["clusters"][0]["evidence"][0]
    evidence["source_excerpt_start"] = 1
    messages = mapping_problem_messages(validate_analysis_mapping(bundle))
    assert any("哈希不一致" in message for message in messages)
    assert any("连续原文不一致" in message for message in messages)


def test_merged_speakers_and_unsupported_number_are_blocked() -> None:
    bundle = valid_bundle()
    evidence = bundle["viewpoints"]["by_topic"][0]["clusters"][0]["evidence"][0]
    evidence["speaker_name"] = "吴建钦、刘澄"
    evidence["attribution"] = "吴建钦、刘澄"
    evidence["formal_claim"] += "并将在三年内完成。"
    bundle["viewpoints"]["by_topic"][0]["clusters"][0]["details"] += "并将在三年内完成。"
    messages = mapping_problem_messages(validate_analysis_mapping(bundle))
    assert all(message.startswith("[议题=") for message in messages)
    assert any("合并了多个发言人" in message for message in messages)
    assert any("新增了原文片段中没有的数字" in message for message in messages)


def test_semantic_review_must_be_fully_supported() -> None:
    bundle = valid_bundle()
    evidence = bundle["viewpoints"]["by_topic"][0]["clusters"][0]["evidence"][0]
    evidence["semantic_review"]["verdict"] = "partially_supported"
    evidence["semantic_review"]["propositions"][0]["verdict"] = "partially_supported"
    messages = mapping_problem_messages(validate_analysis_mapping(bundle))
    assert any("fully_supported" in message for message in messages)
    assert any("未被原文完全支持" in message for message in messages)


def test_semantic_propositions_cannot_hide_part_of_claim() -> None:
    bundle = valid_bundle()
    evidence = bundle["viewpoints"]["by_topic"][0]["clusters"][0]["evidence"][0]
    evidence["semantic_review"]["propositions"][0]["text"] = "城市更新已经成为中央常态化关注和推动的重大事项。"
    messages = mapping_problem_messages(validate_analysis_mapping(bundle))
    assert any("没有完整覆盖formal_claim" in message for message in messages)


def test_release_backcheck_requires_same_mapping_in_dashboard_and_word(tmp_path: Path) -> None:
    bundle = valid_bundle()
    report_data = {"analysis_bundle": bundle}
    (tmp_path / "report_data.json").write_text(json.dumps(report_data, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "cwh_dashboard.html").write_text(
        '<script id="dashboard-data">' + json.dumps(report_data, ensure_ascii=False) + "</script>",
        encoding="utf-8",
    )
    details = bundle["viewpoints"]["by_topic"][0]["clusters"][0]["details"]
    with zipfile.ZipFile(tmp_path / "cwh_formal_report.docx", "w") as archive:
        archive.writestr("word/document.xml", f"<w:document><w:body><w:p><w:r><w:t>{details}</w:t></w:r></w:p></w:body></w:document>")
    assert validate_release_mapping(tmp_path)["status"] == "passed"

    (tmp_path / "cwh_dashboard.html").write_text(
        '<script id="dashboard-data">' + json.dumps({"analysis_bundle": {}}, ensure_ascii=False) + "</script>",
        encoding="utf-8",
    )
    messages = mapping_problem_messages(validate_release_mapping(tmp_path))
    assert any("工作台未完整保留" in message for message in messages)


def test_independent_review_packet_is_merged_by_evidence_id() -> None:
    bundle = valid_bundle()
    evidence = bundle["viewpoints"]["by_topic"][0]["clusters"][0]["evidence"][0]
    review = dict(evidence.pop("semantic_review"))
    packet = {
        "review_version": "1.0",
        "review_pass": "independent_second_pass",
        "reviewer_run_id": "review-run-2",
        "source_bundle_sha256": "abc123",
        "reviews": [{"evidence_id": "evidence-1", **review}],
    }
    verified, issues = apply_semantic_review_packet(bundle, packet, source_bundle_sha256="abc123")
    assert issues == []
    merged = verified["viewpoints"]["by_topic"][0]["clusters"][0]["evidence"][0]["semantic_review"]
    assert merged["review_pass"] == "independent_second_pass"
    assert merged["reviewer_run_id"] == "review-run-2"
    assert validate_analysis_mapping(verified)["status"] == "passed"


def test_review_run_must_differ_from_authoring_run() -> None:
    bundle = valid_bundle()
    evidence = bundle["viewpoints"]["by_topic"][0]["clusters"][0]["evidence"][0]
    review = dict(evidence["semantic_review"])
    packet = {
        "review_version": "1.0",
        "review_pass": "independent_second_pass",
        "reviewer_run_id": "author-run-1",
        "source_bundle_sha256": "abc123",
        "reviews": [{"evidence_id": "evidence-1", **review}],
    }
    _, issues = apply_semantic_review_packet(bundle, packet, source_bundle_sha256="abc123")
    assert any(issue["code"] == "reviewer_not_independent" for issue in issues)
