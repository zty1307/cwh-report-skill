from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
MODULE_PATH = ROOT / "scripts" / "generate_dashboard.py"
SPEC = importlib.util.spec_from_file_location("cwh_generate_dashboard", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_dashboard_image_resolution_skips_stale_paths(tmp_path: Path) -> None:
    valid = tmp_path / "wordcloud.png"
    valid.write_bytes(b"reviewed-wordcloud")
    uri = MODULE.first_image_data_uri(tmp_path / "missing.png", valid)
    assert uri.startswith("data:image/png;base64,")


def test_person_is_detected_from_evidence_summary() -> None:
    result = MODULE.evidence_attribution(
        {
            "source": "风口财经",
            "content": "盘和林从数字经济、数字基础设施、公共服务和数据价值四个维度解读系统推进数字中国建设。",
            "attribution": "风口财经",
            "attribution_status": "media_only",
        },
        {},
    )

    assert result == {"attribution": "盘和林", "attribution_status": "named_person"}


def test_person_is_detected_from_viewpoint_context() -> None:
    result = MODULE.evidence_attribution(
        {"source": "风口财经", "attribution_status": "media_only"},
        {},
        "工信部信息通信经济专家委员会委员盘和林认为，应统筹发展与安全。",
    )

    assert result == {
        "attribution": "工信部信息通信经济专家委员会委员盘和林",
        "attribution_status": "named_person",
    }


def test_verified_titles_are_retained_with_names() -> None:
    result = MODULE.evidence_attribution(
        {"source": "21世纪经济报道", "attribution_status": "media_only"},
        {},
        "中国商业经济学会副会长宋向清认为，应支持多技术路线布局。",
    )

    assert result["attribution"] == "中国商业经济学会副会长宋向清"


def test_title_expansion_requires_same_named_person() -> None:
    named = MODULE.expand_named_attribution(
        "北京邮电大学邮政发展研究中心主任赵国君认为，应完善物流体系。",
        {"attribution": "赵国君", "attribution_status": "named_person"},
    )
    media_only = MODULE.expand_named_attribution(
        "国家自然灾害防治研究院研究员孙洪泉认为，应加强演练。国家数据局转载会议消息。",
        {"attribution": "国家数据局", "attribution_status": "media_only"},
    )
    assert named["attribution"] == "北京邮电大学邮政发展研究中心主任赵国君"
    assert media_only == {"attribution": "国家数据局", "attribution_status": "media_only"}


def test_media_only_is_retained_when_no_person_is_present() -> None:
    result = MODULE.evidence_attribution(
        {"source": "某媒体", "content": "文章关注数字基础设施建设。"},
        {},
    )

    assert result == {"attribution": "某媒体", "attribution_status": "media_only"}


def test_collective_term_is_not_treated_as_person() -> None:
    result = MODULE.evidence_attribution(
        {
            "source": "某媒体",
            "content": "人工智能从业者分别从供需匹配和创新落地角度解读数字基础设施建设。",
        },
        {},
    )

    assert result == {"attribution": "某媒体", "attribution_status": "media_only"}


def test_viewpoint_said_form_is_detected() -> None:
    result = MODULE.evidence_attribution(
        {
            "source": "新华网",
            "content": "国家自然灾害防治研究院研究员孙洪泉观点称，应提升复杂环境下的防灾减灾救灾能力。",
        },
        {},
    )

    assert result == {
        "attribution": "国家自然灾害防治研究院研究员孙洪泉",
        "attribution_status": "named_person",
    }


def test_template_hides_internal_attribution_line_for_named_people() -> None:
    template = (ROOT / "assets" / "cwh_dashboard_template.html").read_text(encoding="utf-8")

    assert "归因主体：" not in template
    assert "仅识别到媒体主体，待补专家姓名" not in template
    assert "未识别到具体专家姓名，建议核验原文" in template
    assert "named&&e.attribution" not in template
    assert 'class="attribution-warning"' not in template
    assert "待自有情感分析" not in template
    assert "return `<strong>${html}</strong>`" not in template
    assert "保存并生成词云" in template
    assert "不是传播热度" not in template
    assert "条独立观点样本" in template
    assert "support.map(supportUnit)" not in template


def test_overseas_report_rows_use_one_uniform_title_only_layout() -> None:
    template = (ROOT / "assets" / "cwh_dashboard_template.html").read_text(encoding="utf-8")

    assert "showDescription" not in template
    assert "showOriginalTitle" not in template
    assert "showOriginalDescription" not in template
    assert "overseas-original" not in template
    assert '${esc(title)} ↗</a></div></div>' in template


def test_dashboard_keeps_duplicate_direct_source_pages_in_audit_only() -> None:
    topic = "研究基础教育改革发展有关工作"
    data = {
        "samples": [
            {
                "topic": topic,
                "source": "微信公众号甲",
                "title": "代表性观点",
                "url": "https://mp.weixin.qq.com/s/example",
                "content": "公众号中的代表性观点。",
            }
        ],
        "analysis_bundle": {
            "research_audit": {
                "domestic_media_research": {
                    "candidate_pool_by_topic": [
                        {
                            "topic": topic,
                            "candidates": [
                                {
                                    "decision": "duplicate",
                                    "source": "新华网",
                                    "title": "国务院常务会议解读丨基础教育",
                                    "url": "https://www.news.cn/education/example.html",
                                    "decision_reason": "观点已在原始监测池出现。",
                                },
                                {
                                    "decision": "excluded",
                                    "source": "无关平台结果",
                                    "title": "其他会议",
                                    "url": "https://example.com/unrelated",
                                },
                            ],
                        }
                    ]
                }
            }
        },
    }

    result = MODULE.dashboard_media_evidence_by_topic(
        data,
        [{"topic": topic, "display": "基础教育改革发展"}],
    )

    assert [item["source"] for item in result[0]["items"]] == ["微信公众号甲"]


def test_dashboard_payload_preserves_analysis_bundle_for_release_mapping(tmp_path: Path) -> None:
    analysis_bundle = {"metadata": {"evidence_mapping_version": "1.0"}, "viewpoints": {"by_topic": []}}
    payload = MODULE.prepare_dashboard_data(
        {
            "analysis_bundle": analysis_bundle,
            "meeting": {},
            "system_data": {},
            "topic_stats": [],
            "artifacts": {},
            "audit": {},
        },
        tmp_path,
    )
    assert payload["analysis_bundle"] == analysis_bundle


def test_complete_claim_uses_full_cluster_sentence() -> None:
    details = (
        "中指研究院研究总监吴建钦认为，此次部署表明城市更新已成为中央常态化关注和推动的重大事项，"
        "首部国家层面专项规划将把目标、政策和实施机制衔接为完整行动路线，并增强社会资本参与预期。"
        "中国城市发展研究院投资部主任刘澄认为，政策转向存量提质。"
    )
    result = MODULE.complete_claim_from_cluster_details(
        details,
        {"attribution": "中指研究院研究总监吴建钦", "attribution_status": "named_person"},
        "吴建钦认为，城市更新战略地位进一步凸显。",
    )

    assert result.startswith("中指研究院研究总监吴建钦认为，此次部署表明")
    assert "完整行动路线" in result
    assert "刘澄" not in result


def test_multi_person_article_expands_to_one_full_claim_per_voice() -> None:
    details = (
        "同济大学中国交通研究院研究员林坦表示，针对物流网硬联通结构性短板和软联通全链条不优两类堵点，"
        "要健全多式联运规则，并完善物流可信数据空间。"
        "快递物流专家、贯铄资本CEO赵小敏指出，人工智能与物流融合将推动路由、服务、运转和公司内控体系的流程再造。"
    )

    result = MODULE.expand_multi_voice_claims(
        details,
        {"attribution": "林坦、赵小敏", "attribution_status": "named_person"},
        "文章援引林坦和赵小敏讨论物流体系。",
    )

    assert len(result) == 2
    assert result[0][0]["attribution"] == "同济大学中国交通研究院研究员林坦"
    assert result[1][0]["attribution"] == "快递物流专家、贯铄资本CEO赵小敏"
    assert result[0][1].startswith("同济大学中国交通研究院研究员林坦表示")
    assert result[1][1].startswith("快递物流专家、贯铄资本CEO赵小敏指出")
    assert all(len(claim) >= 45 for _, claim in result)
