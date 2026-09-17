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


def test_invalid_shared_heading_uses_only_an_existing_single_approved_individual_heading():
    row = {'topic': '基础工程', 'platform': '境内平台', 'url': 'https://example.test/comment',
           'quote_verified': True, 'evidence_mode': 'platform_comment', 'comment_id': 'c1',
           'content': '这些基础工程将改善资源配置。', 'ai_formal_include': True,
           'ai_semantic_quality': 'substantive', 'topic_comment_heading': '基础工程影响',
           'comment_heading': '认为基础工程将改善资源配置'}
    original = copy.deepcopy(row)
    groups = formal.comment_groups([row])
    assert groups[0][0] == row['comment_heading']
    assert groups[0][1][0]['comment_id'] == 'c1'
    assert row == original


def test_invalid_shared_heading_does_not_combine_distinct_individual_judgments():
    base = {'topic': '基础工程', 'platform': '境内平台', 'url': 'https://example.test/comment',
            'quote_verified': True, 'evidence_mode': 'platform_comment', 'ai_formal_include': True,
            'ai_semantic_quality': 'substantive', 'topic_comment_heading': '基础工程影响'}
    rows = [{**base, 'comment_id': 'c1', 'content': '希望保持基本服务覆盖。',
             'comment_heading': '希望保持基本服务覆盖'},
            {**base, 'comment_id': 'c2', 'content': '应公开实施安排。',
             'comment_heading': '建议公开实施安排'}]
    original = copy.deepcopy(rows)
    assert formal.comment_groups(rows) == []
    assert rows == original


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


def test_exact_duplicated_institution_prefix_is_display_only_not_identity_rewrite():
    from cwh_writing_rules import formal_attribution
    row = {'speaker_name': '某主管部门有关负责人', 'speaker_role': '某主管部门',
           'attribution': '某主管部门某主管部门有关负责人', 'attribution_status': 'named_person'}
    original = copy.deepcopy(row)
    assert formal_attribution(row) == '某主管部门有关负责人'
    assert row == original
    row.update(speaker_name='张某', attribution='某主管部门张某')
    assert formal_attribution(row) == '某主管部门张某'


def test_final_renderer_rebuilds_stale_attribution_from_unchanged_atomic_evidence():
    row = {'speaker_name': '某主管部门有关负责人', 'speaker_role': '某主管部门',
           'attribution': '某主管部门某主管部门有关负责人', 'attribution_status': 'named_person',
           'formal_claim': '应明确实施条件并公布具体程序。', 'attribution_verb': '表示'}
    cluster = {'summary': '建议明确实施条件', 'evidence': [row],
               'details': '某主管部门某主管部门有关负责人表示，旧的预组装正文。'}
    original = copy.deepcopy(cluster)
    text = formal.cluster_wording(cluster)
    assert '某主管部门有关负责人表示' in text
    assert '某主管部门某主管部门' not in text and '旧的预组装正文' not in text
    assert cluster == original
    from generate_dashboard import evidence_attribution
    assert evidence_attribution(row, row)['attribution'] == '某主管部门有关负责人'
    assert cluster == original


def test_unapproved_chair_requires_current_source_and_neutral_profile_remains_available():
    generic = opening_paragraph({}, "1月2日", "研究公共服务工作")
    assert generic.startswith(writing_rules()['document']['approved_chair_default'])
    neutral = copy.deepcopy(writing_rules())
    neutral['document']['approved_chair_default'] = ''
    with mock.patch('cwh_writing_rules.writing_rules', return_value=neutral):
        assert '李强' not in opening_paragraph({}, '1月2日', '研究公共服务工作')
    assert "张某" not in opening_paragraph({"chair_name": "张某"}, "1月2日", "研究公共服务工作")
    sourced = opening_paragraph({"chair_name": "张某", "chair_source": "本期会议通稿"}, "1月2日", "研究公共服务工作")
    assert sourced.startswith("张某1月2日主持召开")


def test_noun_only_agenda_is_rendered_as_a_grammatical_sentence():
    agenda = formal.joined_agenda_topics(["城市更新", "农业农村现代化", "基础教育改革发展"])
    assert agenda == "城市更新、农业农村现代化和基础教育改革发展"
    text = opening_paragraph({}, "5月15日", agenda)
    assert text.startswith("国务院总理李强5月15日主持召开国务院常务会议，会议涉及")
    assert "等议题。" in text


def test_self_media_attribution_includes_platform_and_uses_stable_verb():
    row = {
        "speaker_name": "九开间", "source": "九开间", "attribution_status": "self_media",
        "url": "https://mp.weixin.qq.com/s/example", "formal_claim": "城市更新需要建立长期运营机制。",
    }
    assert evidence_sentence(row) == "微信公众号“九开间”称，城市更新需要建立长期运营机制"
    row["attribution_verb"] = "建议"
    assert evidence_sentence(row) == "微信公众号“九开间”建议，城市更新需要建立长期运营机制"


def test_unsupported_padding_is_blocked_but_original_quote_is_preserved():
    claim = "应完善不同部门的职责分工，保留具体实施条件并根据公开反馈定期评估政策效果，为高质量发展注入新动能"
    row = {"attribution": "测试机构", "source": "测试机构", "formal_claim": claim, "source_excerpt": "应完善不同部门的职责分工"}
    cluster = {"summary": "建议完善职责分工", "details": "测试机构认为，" + claim, "evidence": [row]}
    payload = {"viewpoints": {"by_topic": [{"topic": "公共服务", "heading": "建议完善职责分工", "clusters": [cluster]}]}}
    assert any(issue["code"] == "unsupported_rhetorical_padding" for issue in domestic_viewpoint_quality_issues(payload))
    row["source_excerpt"] = claim
    assert not any(issue["code"] == "unsupported_rhetorical_padding" for issue in domestic_viewpoint_quality_issues(payload))
    assert row["formal_claim"] == claim


def test_approved_editorial_frames_do_not_invent_numeric_peak_data():
    paragraphs = formal.total_event_paragraphs({"meeting": {}, "statistics": {"total_spread": 100, "by_source_bucket": {"domestic_media": 80, "overseas_media": 0}}})
    text = "".join(paragraphs)
    assert "100条" in text
    assert "80条" in text
    assert "峰值" not in text
    assert "李强" not in text
    assert "显著位置" in text
    assert "人民网" in text


def test_more_than_eight_groups_are_not_dropped_and_docx_matches_markdown(tmp_path):
    clusters = [{"summary": f"建议落实第{index}项配套要求", "details": f"测试机构认为，应落实第{index}项配套要求并保留实施条件。", "evidence": []} for index in range(1, 10)]
    groups = [(f"建议回应第{index}项公共需求", [{"content": "建议明确职责并建立公开反馈机制。", "quote_verified": True, "url": "https://example.test/comment"}]) for index in range(1, 10)]
    data = {"meeting": {"date": "2025-01-02", "topics": ["研究公共服务工作"]}, "statistics": {}, "viewpoints": {"by_topic": [{"heading": "建议落实配套要求", "clusters": clusters}]}, "comments": {"selected": []}, "topic_stats": []}
    with mock.patch.object(formal, "report_comment_groups", return_value=groups), mock.patch.object(formal, "ensure_docx_chart_images", return_value={}):
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


def test_comment_lead_uses_short_first_clause_but_body_keeps_full_heading():
    heading = "认为城市更新应优先保障居住安全，并完善长期运营和资金平衡机制"
    groups = [(heading, [{"content": "支持改善居住环境"}])]
    lead = formal.comment_lead({}, groups)
    assert "主要有城市更新应优先保障居住安全" in lead
    assert "主要有认为" not in lead
    assert "长期运营" not in lead
    assert groups[0][0] == heading


def test_comment_cleanup_repairs_mixed_quotes_and_numeric_ranges():
    assert formal.clean_formal_comment('破旧不堪的"城中村”改造要覆盖50~70岁群体') == '破旧不堪的‘城中村’改造要覆盖50至70岁群体'


def test_comment_lead_preserves_a_complete_long_clause_without_cutting_a_word():
    heading = '认为公共服务改革应兼顾偏远地区特殊群体的长期基本保障需求'
    groups = [(heading, [{'content': '已审核的真实原话'}])]
    original = copy.deepcopy(groups)
    assert heading.removeprefix('认为') in formal.comment_lead({}, groups)
    assert groups == original


def test_sentiment_lead_never_presents_a_collected_sample_as_the_entire_public():
    data = {'comments': {'sentiment': {'positive': 25, 'neutral': 3, 'negative': 1}}}
    assert formal.netizen_sentiment_lead(data).startswith('从已审核的网民评论样本看')
    assert data['comments']['sentiment']['positive'] == 25


def test_partial_verified_role_attribution_preserves_the_literal_frozen_claim():
    row = {'speaker_name': '张某', 'speaker_role': '行业研究员、某机构负责人',
           'attribution': '行业研究员、某机构负责人张某', 'attribution_status': 'named_person',
           'attribution_verb': '表示',
           'formal_claim': '行业研究员张某认为，应依据实际需求确定投入节奏。',
           'semantic_review': {'verdict': 'fully_supported'}}
    original = copy.deepcopy(row)
    assert evidence_sentence(row) == row['formal_claim'].rstrip('。')
    assert row == original
    # Unverified roles and a different speaker must not trigger this shortcut.
    row['formal_claim'] = '投资顾问张某认为，应依据实际需求确定投入节奏。'
    assert evidence_sentence(row).startswith(row['attribution'] + '表示，')
    row['formal_claim'] = '行业研究员李某认为，应依据实际需求确定投入节奏。'
    assert evidence_sentence(row).startswith(row['attribution'] + '表示，')


def test_hotword_focus_with_stance_does_not_render_focus_thinks():
    data = {
        "hotwords": [{"topic": "研究公共服务工作", "word": "公共服务"}],
        "viewpoints": {"by_topic": [{"topic": "研究公共服务工作", "clusters": [{"summary": "认为应完善基层服务机制"}]}]},
    }
    text = formal.hotword_paragraph(data)
    assert "相关观点认为应完善基层服务机制" in text
    assert "聚焦认为" not in text


def test_topic_volume_order_does_not_invent_word_frequency_or_temporal_heat():
    data = {'hotwords': [{'topic': '公共服务', 'word': '制度覆盖面', 'count': 1}],
            'topic_stats': [{'topic': '公共服务', 'spread_count': 99999}]}
    text = formal.hotword_paragraph(data)
    assert '制度覆盖面' in text and '公共服务' in text
    assert all(phrase not in text for phrase in ('位居前列', '热度较高', '持续热传'))


def test_weak_self_media_promotion_is_blocked_and_repeated_heading_verb_is_warned():
    viewpoints = []
    for index in range(3):
        evidence = []
        if index == 0:
            evidence = [{
                "attribution_status": "self_media", "source": "某企业账号",
                "formal_claim": "这对某企业是市场机遇，并为其核心业务带来直接增效与价值释放。",
            }]
        viewpoints.append({
            "topic": f"议题{index}", "heading": "认为相关政策应完善长期实施机制",
            "clusters": [{"summary": "认为应完善长期实施机制", "details": "某媒体称，应完善长期实施机制并定期评估政策效果。", "evidence": evidence}],
        })
    issues = domestic_viewpoint_quality_issues({"viewpoints": {"by_topic": viewpoints}})
    codes = {row["code"] for row in issues}
    assert "commercial_self_promotion" in codes
    assert "mechanical_heading_verb_repetition" in codes
