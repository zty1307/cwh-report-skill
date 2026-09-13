from __future__ import annotations

import copy
import sys
from pathlib import Path
from unittest import mock

from docx import Document

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import formalize_cwh_report as formal
from cwh_writing_rules import opening_paragraph, ordinal_prefix, writing_rules
from normalize_cwh_analysis import normalize_analysis, evidence_sentence
from report_rules import domestic_viewpoint_quality_issues


def test_explicit_zero_is_not_replaced_by_sample_count_and_peak_requires_valid_date():
    stats = {"total_spread": 0, "total_samples": 500,
             "by_date": {"无日期": 9999, "2026-99-99": 8888, "2026-01-02": 5}}
    text = formal.total_event_paragraphs({"statistics": stats})[0]
    assert "约0条" in text
    assert "1月2日达到峰值" in text
    assert "500" not in text and "99月" not in text


def test_source_priority_is_stable_and_normalization_is_idempotent():
    rows = [
        {"speaker_name": "账号甲", "attribution_status": "self_media", "formal_claim": "应完善实施反馈机制。"},
        {"speaker_name": "媒体甲", "source_type": "central_media", "formal_claim": "应明确责任边界。"},
        {"speaker_name": "专家甲", "attribution_status": "named_person", "formal_claim": "应保留适用条件。"},
        {"speaker_name": "专家乙", "attribution_status": "named_person", "formal_claim": "应及时复核效果。"},
    ]
    payload = {"viewpoints": {"by_topic": [{"clusters": [{"evidence": rows}]}]}}
    normalized = normalize_analysis(payload)
    cluster = normalized["viewpoints"]["by_topic"][0]["clusters"][0]
    assert [row["speaker_name"] for row in cluster["evidence"]] == ["专家甲", "专家乙", "媒体甲", "账号甲"]
    assert cluster["details"].startswith("专家甲认为，")
    assert normalize_analysis(copy.deepcopy(normalized)) == normalized


def test_normalizer_never_keeps_unsupported_old_prose():
    payload = {"viewpoints": {"by_topic": [{"clusters": [{"details": "旧的无证据段落", "analysis": "另一旧段落", "evidence": []}]}]}}
    cluster = normalize_analysis(payload)["viewpoints"]["by_topic"][0]["clusters"][0]
    assert cluster["details"] == ""
    assert "analysis" not in cluster


def test_mentioning_subject_inside_claim_does_not_erase_attribution():
    assert evidence_sentence({"speaker_name": "甲机构", "formal_claim": "该措施涉及甲机构的职责。"}).startswith("甲机构认为，")


def test_chair_name_requires_explicit_current_source():
    generic = opening_paragraph({}, "1月2日", "研究公共服务工作")
    assert "李强" not in generic
    assert "张某" not in opening_paragraph({"chair_name": "张某"}, "1月2日", "研究公共服务工作")
    sourced = opening_paragraph({"chair_name": "张某", "chair_source": "本期会议通稿"}, "1月2日", "研究公共服务工作")
    assert sourced.startswith("张某1月2日主持召开")


def test_unsupported_padding_is_blocked_but_original_quote_is_preserved():
    claim = "应完善不同部门的职责分工，保留具体实施条件并根据公开反馈定期评估政策效果，为高质量发展注入新动能"
    row = {"attribution": "测试机构", "source": "测试机构", "formal_claim": claim, "source_excerpt": "应完善不同部门的职责分工"}
    cluster = {"summary": "建议完善职责分工", "details": "测试机构认为，" + claim, "evidence": [row]}
    payload = {"viewpoints": {"by_topic": [{"topic": "公共服务", "heading": "建议完善职责分工", "clusters": [cluster]}]}}
    assert any(issue["code"] == "unsupported_rhetorical_padding" for issue in domestic_viewpoint_quality_issues(payload))
    row["source_excerpt"] = claim
    assert not any(issue["code"] == "unsupported_rhetorical_padding" for issue in domestic_viewpoint_quality_issues(payload))
    assert row["formal_claim"] == claim


def test_propagation_frames_do_not_invent_publisher_placement_or_peak():
    paragraphs = formal.total_event_paragraphs({"meeting": {}, "statistics": {"total_spread": 100, "by_source_bucket": {"domestic_media": 80, "overseas_media": 0}}})
    text = "".join(paragraphs)
    assert "100条" in text
    assert "80条" in text
    assert "峰值" not in text
    assert "李强" not in text
    assert "显著位置" not in text
    assert "人民网" not in text


def test_more_than_eight_groups_are_not_dropped_and_docx_matches_markdown(tmp_path):
    clusters = [{"summary": f"建议落实第{index}项配套要求", "details": f"测试机构认为，应落实第{index}项配套要求并保留实施条件。", "evidence": []} for index in range(1, 10)]
    groups = [(f"建议回应第{index}项公共需求", [{"content": "建议明确职责并建立公开反馈机制。", "quote_verified": True, "url": "https://example.test/comment"}]) for index in range(1, 10)]
    data = {"meeting": {"date": "2025-01-02", "topics": ["研究公共服务工作"]}, "statistics": {}, "viewpoints": {"by_topic": [{"heading": "建议落实配套要求", "clusters": clusters}]}, "comments": {"selected": []}, "topic_stats": []}
    with mock.patch.object(formal, "comment_groups", return_value=groups), mock.patch.object(formal, "ensure_docx_chart_images", return_value={}):
        markdown = formal.render_formal_markdown(data, tmp_path)
        path = tmp_path / "report.docx"
        formal.write_docx(data, path)
    word = "\n".join(p.text for p in Document(path).paragraphs)
    assert ordinal_prefix(9) == "九是"
    assert ordinal_prefix(12) == "十二是"
    for text in [opening_paragraph(data["meeting"], "1月2日", "研究公共服务工作"), formal.comment_lead(data, groups), "九是建议落实第9项配套要求", "九是建议回应第9项公共需求"]:
        assert text in markdown
        assert text in word


def test_hotword_frames_cover_all_topics_without_truncating_conditions():
    headings = [{"topic": f"议题{index}", "clusters": [{"summary": f"建议落实议题{index}并保留特殊地区与特定群体的适用条件"}]} for index in range(1, 10)]
    data = {"hotwords": [{"topic": f"议题{index}", "word": f"主题词{index}"} for index in range(1, 10)], "viewpoints": {"by_topic": headings}}
    text = formal.hotword_paragraph(data)
    for index in range(1, 10):
        assert f"主题词{index}" in text
        assert f"建议落实议题{index}并保留特殊地区与特定群体的适用条件" in text
    assert text.startswith(writing_rules()["hotwords"]["opening"])
