import copy
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from cwh_available_delivery import prepare_available_delivery, valid_gap, available_delivery
from domestic_evidence_mapping import validate_analysis_mapping
from report_rules import domestic_viewpoint_quality_issues


def material():
    return {"viewpoints": {"by_topic": [{"topic": "动态议题", "heading": "动态议题", "clusters": [{"cluster_key": "empty", "evidence": []}]}]},
            "research_audit": {"domestic_media_research": {
                "candidate_pool_by_topic": [{"topic": "动态议题", "candidates": [], "saturation": {"rounds": [{"executions": [{"query_id": "q1", "status": "access_failed", "result_count": 0}]}]}}],
                "public_article_corpus_review": {"topic_reviews": [{"topic": "动态议题", "reviewed_record_ids": ["r1"], "deferred_record_ids": ["r2"]}]}}}}


def test_empty_topic_is_explicit_gap_not_proof_of_no_discussion():
    original = material()
    data = prepare_available_delivery(original)
    topic = data["viewpoints"]["by_topic"][0]
    assert available_delivery(data) and valid_gap(topic)
    assert "不代表没有" in topic["evidence_gap"]["notice"]
    assert "另有1篇未审" in topic["evidence_gap"]["scope"]
    assert "access_failed" in topic["evidence_gap"]["search_evidence"]
    assert topic["delivery_adjustments"]["removed_empty_clusters"] == ["empty"]
    assert all(i["severity"] == "warning" for i in domestic_viewpoint_quality_issues(data))
    assert len(original["viewpoints"]["by_topic"][0]["clusters"]) == 1
    assert prepare_available_delivery(data) == data


def test_unmapped_eligible_candidate_cannot_be_excused_as_missing_evidence():
    original = material()
    original["research_audit"]["domestic_media_research"]["candidate_pool_by_topic"][0]["candidates"] = [{"candidate_id": "c1", "decision": "eligible"}]
    assert not valid_gap(prepare_available_delivery(original)["viewpoints"]["by_topic"][0])


def test_missing_research_does_not_create_zero_result_exception():
    original = material()
    original["research_audit"] = {}
    topic = prepare_available_delivery(original)["viewpoints"]["by_topic"][0]
    assert not valid_gap(topic) and "evidence_shortfall" not in topic


def test_density_count_audit_never_self_certifies_a_claim():
    original = material()
    evidence = {"speaker_name": "真实主体", "formal_claim": "只保留原有观点", "source_excerpt": "原有片段"}
    original["viewpoints"]["by_topic"][0]["clusters"] = [{"summary": "建议按实际需求优化服务", "details": "真实主体建议只保留原有观点", "evidence": [evidence]}]
    data = prepare_available_delivery(original)
    cluster = data["viewpoints"]["by_topic"][0]["clusters"][0]
    assert cluster["evidence"][0] == evidence
    assert "not_semantic_certification" in cluster["thin_cluster_exception"]["reviewed_by"]
    assert validate_analysis_mapping(data)["status"] == "blocked"


def test_channel_label_does_not_merge_independent_accounts():
    data = {"viewpoints": {"by_topic": [{"topic": "动态议题", "heading": "建议按实际需求优化公共服务覆盖范围", "clusters": [
        {"summary": "建议完善不同地区的服务覆盖", "evidence": [{"source": "公众号", "speaker_name": "账号甲", "attribution": "账号甲", "attribution_status": "self_media"}]},
        {"summary": "建议优化不同群体的服务供给", "evidence": [{"source": "公众号", "speaker_name": "账号乙", "attribution": "账号乙", "attribution_status": "self_media"}]}]}]}}
    assert not any(i['code'] == 'repeated_voice_within_topic' for i in domestic_viewpoint_quality_issues(data))
    data['viewpoints']['by_topic'][0]['clusters'][1]['evidence'][0]['speaker_name'] = '账号甲'
    assert any(i['code'] == 'repeated_voice_within_topic' for i in domestic_viewpoint_quality_issues(data))
