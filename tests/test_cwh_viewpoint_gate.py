from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from cwh_viewpoint_gate import cluster_density_result, independent_voice_keys
from cwh_orchestrator import build_system_audit
from run_cwh_resumable_pipeline import validate_analysis_bundle


def thin_cluster():
    return {
        "summary": "认为公共服务应完善配套措施",
        "details": "测试媒体认为，公共服务建设应兼顾不同群体的实际需求，完善需求反馈和定期评估机制，并在实施过程中明确责任主体与适用条件。",
        "evidence": [{"speaker_name": "测试媒体", "source": "测试媒体", "url": "https://example.com/a", "candidate_id": "candidate-a"}],
    }


EXCEPTION = {"reason": "该观点仅检得一个独立声音", "search_evidence": "query-1已执行且结果保存在候选池", "reviewed_by": "independent-reviewer"}


@pytest.mark.parametrize("exception,passed", [(None, False), ({"reason": "不足"}, False), ("approved", False), ({**EXCEPTION, "reviewed_by": []}, False), (EXCEPTION, True)])
def test_draft_and_final_audit_agree_on_thin_cluster(tmp_path, exception, passed):
    cluster = thin_cluster()
    cluster["thin_cluster_exception"] = exception
    viewpoints = {"by_topic": [{"topic": "公共服务", "heading": "认为公共服务应完善配套措施", "clusters": [cluster]}]}
    path = tmp_path / "analysis.json"
    path.write_text(json.dumps({"viewpoints": viewpoints}, ensure_ascii=False), encoding="utf-8")
    draft_problems = validate_analysis_bundle(path, ["公共服务"], require_semantic_review=False)
    audit = build_system_audit({}, [], [], viewpoints)
    assert (not any("成文密度门禁" in problem for problem in draft_problems)) is passed
    assert (not audit["quality_summary"]["thin_viewpoint_clusters"]) is passed
    assert bool(audit["quality_summary"]["viewpoint_density_exceptions"]) is passed
    # Passing density alone must never certify the incomplete report.
    assert audit["acceptance"]["ready_for_formal_delivery"] is False


def test_repeated_attribution_and_duplicate_speakers_do_not_create_independent_voices():
    cluster = thin_cluster()
    cluster["details"] *= 4
    cluster["evidence"].append({**cluster["evidence"][0], "url": "https://example.com/mirror"})
    result = cluster_density_result(cluster)
    assert result["independent_voices"] == 1
    assert result["passed"] is False


def test_only_chinese_characters_count_toward_density():
    cluster = thin_cluster()
    cluster["evidence"].append({"speaker_name": "另一媒体"})
    cluster["details"] += "!!! 123 abc" * 30
    assert cluster_density_result(cluster)["passed"] is False
    cluster["details"] = "中" * 120
    assert cluster_density_result(cluster)["passed"] is True


def test_exception_cannot_waive_empty_prose_or_missing_evidence():
    for key, value in [("details", ""), ("evidence", [])]:
        cluster = copy.deepcopy(thin_cluster())
        cluster["thin_cluster_exception"] = EXCEPTION
        cluster[key] = value
        assert cluster_density_result(cluster)["passed"] is False


@pytest.mark.parametrize('people,claims_per_person', [(1, 13), (4, 4), (13, 1)])
def test_bounded_formal_cap_and_shortfall_count_subjects_not_claims(tmp_path, people, claims_per_person):
    evidence = [{'candidate_id': f'c{p}-{i}', 'speaker_name': f'主体{p}',
                 'url': 'https://example.test/article'}
                for p in range(people) for i in range(claims_per_person)]
    assert len(independent_voice_keys(evidence)) == people
    pool = {'topic': '公共服务', 'candidates': [
        {'candidate_id': row['candidate_id'], 'decision': 'eligible'} for row in evidence],
        'saturation': {'stop_reason': 'coverage_minimum_then_one_zero_new_round_or_budget_exhausted'}}
    bundle = {'viewpoints': {'by_topic': [{'topic': '公共服务', 'clusters': [
        {**thin_cluster(), 'evidence': evidence}]}]},
        'research_audit': {'domestic_media_research': {'candidate_pool_by_topic': [pool]}}}
    path = tmp_path / 'draft.json'
    path.write_text(json.dumps(bundle), encoding='utf-8')
    problems = validate_analysis_bundle(path, ['公共服务'], require_semantic_review=False)
    assert any('超过12个硬上限' in p for p in problems) == (people > 12)
    assert any('低于4个且缺少evidence_shortfall' in p for p in problems) == (people < 4)
    # These synthetic rows are deliberately not valid evidence.
    assert any('缺少字段' in p for p in problems)
