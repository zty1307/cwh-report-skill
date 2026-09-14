import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prepare_cwh_corpus_index import prepare_corpus_index, complete_corpus_deferrals
from complete_cwh_evidence_structure import complete_analysis_structure
from run_cwh_resumable_pipeline import validate_analysis_bundle


def corpus():
    return {"candidates": [{"record_id": f"r{i}", "title": f"议题分析{i}", "source": f"来源{i}",
                             "url": f"https://example.test/{i}", "topic_hits": [1], "content": f"完整原文{i}"} for i in range(15)]}


def test_index_retains_all_raw_ids_and_separate_reading_order(tmp_path):
    data = corpus()
    source = tmp_path / "public_article_evidence.json"
    source.write_text(json.dumps(data), encoding="utf-8")
    index = json.loads(prepare_corpus_index(source, data, ["议题"]).read_text(encoding="utf-8"))
    assert index["candidate_count"] == 15
    assert set(index["topics"][0]["record_ids"]) == {x["record_id"] for x in data["candidates"]}
    assert all(Path(row["full_text_path"]).exists() for row in index["topics"][0]["shortlist"])


def test_bounded_deferral_never_calls_unread_records_reviewed(tmp_path):
    raw = corpus()
    source = tmp_path / "public_article_evidence.json"
    source.write_text(json.dumps(raw), encoding="utf-8")
    prepare_corpus_index(source, raw, ["议题"])
    row = {"topic": "议题", "reviewed_record_ids": [f"r{i}" for i in range(12)],
           "retained_record_ids": [], "excluded": [{"record_id": f"r{i}", "reason": "逐篇审核后排除"} for i in range(12)]}
    draft = {"research_audit": {"domestic_media_research": {"public_article_corpus_review": {"topic_reviews": [row]}}}}
    result = complete_corpus_deferrals(draft, raw, ["议题"])
    completed = result["research_audit"]["domestic_media_research"]["public_article_corpus_review"]["topic_reviews"][0]
    assert completed["reviewed_record_ids"] == row["reviewed_record_ids"]
    assert completed["deferred_record_ids"] == ["r12", "r13", "r14"]
    target = tmp_path / "draft.json"
    target.write_text(json.dumps(result), encoding="utf-8")
    strict = validate_analysis_bundle(target, ["议题"], require_semantic_review=False)
    bounded = validate_analysis_bundle(target, ["议题"], require_semantic_review=False, allow_deferred_corpus=True)
    assert any("未逐条审核" in x for x in strict)
    assert not any("未逐条审核" in x for x in bounded)
    assert bounded  # Deferral does not waive all the other evidence gates.
    source.write_text(json.dumps({"candidates": raw["candidates"][:14]}), encoding="utf-8")
    assert any("未逐条审核" in x for x in validate_analysis_bundle(target, ["议题"], require_semantic_review=False, allow_deferred_corpus=True))


def test_raw_source_hydration_only_fills_missing_exact_fields():
    candidate = {"raw_evidence_record_id": "r0", "speaker_name": "发言者"}
    draft = {"research_audit": {"domestic_media_research": {"candidate_pool_by_topic": [{"topic": "议题", "candidates": [candidate]}]}}}
    result = complete_analysis_structure(draft, corpus())
    enriched = result["research_audit"]["domestic_media_research"]["candidate_pool_by_topic"][0]["candidates"][0]
    assert enriched["source_snapshot"]["source_text"] == "完整原文0"
    assert enriched["source_snapshot"]["source_text_sha256"]
    assert "url" not in candidate
    enriched["url"] = "https://incorrect.test/"
    second = complete_analysis_structure(result, corpus())
    assert second["research_audit"]["domestic_media_research"]["candidate_pool_by_topic"][0]["candidates"][0]["url"] == "https://incorrect.test/"
