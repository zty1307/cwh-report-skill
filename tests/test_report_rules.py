from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from report_rules import (  # noqa: E402
    attributed_claims,
    cluster_needs_attribution_review,
    domestic_viewpoint_quality_issues,
    enrich_viewpoint_titles,
    formal_sentiment_available,
    formal_sentiment_row_ready,
)
from cwh_orchestrator import analysis_bundle_rows, reset_inherited_sentiment  # noqa: E402


def test_reuses_full_verified_title_within_same_topic() -> None:
    data = {
        "viewpoints": {
            "by_topic": [
                {
                    "clusters": [
                        {"details": "北京邮电大学邮政发展研究中心主任赵国君认为，应完善物流体系。"},
                        {"details": "赵国君指出，应健全统一规则。"},
                    ]
                }
            ]
        }
    }
    enrich_viewpoint_titles(data)
    assert data["viewpoints"]["by_topic"][0]["clusters"][1]["details"].startswith(
        "北京邮电大学邮政发展研究中心主任赵国君指出"
    )


def test_named_person_does_not_trigger_review_warning() -> None:
    cluster = {
        "details": "工信部信息通信经济专家委员会委员盘和林认为，应统筹发展与安全。",
        "evidence": [{"source": "风口财经", "attribution_status": "media_only"}],
    }
    assert cluster_needs_attribution_review(cluster) is False


def test_named_expert_does_not_cover_anonymous_secondary_source() -> None:
    cluster = {
        "details": "王鹏认为应加强基础研究。上海证券报受访专家指出，应完善应用生态。",
        "evidence": [{"source": "上海证券报", "attribution_status": "media_only"}],
    }
    assert cluster_needs_attribution_review(cluster) is True


def test_only_anonymous_expert_still_triggers_review_warning() -> None:
    cluster = {
        "details": "上海证券报受访专家指出，应完善应用生态。",
        "evidence": [{"source": "上海证券报", "attribution_status": "media_only"}],
    }
    assert cluster_needs_attribution_review(cluster) is True


def test_media_voice_does_not_require_missing_expert_warning() -> None:
    cluster = {
        "details": "证券日报认为，资本市场应发挥支持科技创新的关键枢纽作用，并提升服务新质生产力发展的质效。",
        "evidence": [{"source": "证券日报", "attribution_status": "media_only"}],
    }
    assert cluster_needs_attribution_review(cluster) is False


def test_short_attributed_claim_is_detected() -> None:
    claims = attributed_claims("西南财经大学经济学院教授吴垠认为，多元主体参与和协同创新是形成区域互补格局的重要条件。")
    assert claims[0]["claim_cjk_length"] < 30


def test_structured_claim_is_not_split_on_reporting_verb_inside_claim() -> None:
    claim = (
        "规划强调强化企业创新主体地位，鼓励企业开展技术研发、构建服务体系、延伸产业链条，"
        "并通过长期运营提升农业服务质量和资源配置效率。"
    )
    details = f"区域农牧服务平台认为，{claim}"
    issues = domestic_viewpoint_quality_issues(
        {
            "viewpoints": {
                "by_topic": [
                    {
                        "topic": "研究农业服务体系建设",
                        "heading": "认为企业创新应形成长期服务能力",
                        "clusters": [
                            {
                                "summary": "认为企业创新应形成长期服务能力",
                                "details": details,
                                "evidence": [
                                    {
                                        "attribution": "区域农牧服务平台",
                                        "attribution_status": "media_voice",
                                        "formal_claim": claim,
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        }
    )
    assert not any(item["code"] == "attributed_claim_too_short" for item in issues)


def test_structured_short_claim_is_still_rejected() -> None:
    issues = domestic_viewpoint_quality_issues(
        {
            "viewpoints": {
                "by_topic": [
                    {
                        "topic": "研究产业服务体系建设",
                        "heading": "认为服务能力仍需提升",
                        "clusters": [
                            {
                                "summary": "认为服务能力仍需提升",
                                "details": "区域服务平台认为，应提升服务能力。",
                                "evidence": [
                                    {
                                        "attribution": "区域服务平台",
                                        "attribution_status": "media_voice",
                                        "formal_claim": "应提升服务能力。",
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        }
    )
    assert any(item["code"] == "attributed_claim_too_short" for item in issues)


def test_analysis_person_noun_does_not_hide_later_short_expert_claim() -> None:
    text = (
        "中国金融信息网梳理多位宏观分析人士观点："
        "民生银行首席经济学家温彬认为“发力提效”意味着政策强度提升并做好增量储备；"
        "粤开证券首席经济学家罗志恒认为，政策应发挥存量效能并及时谋划增量政策，"
        "强化逆周期调节并推动财政资金尽快形成实物工作量。"
    )
    claims = attributed_claims(text)
    assert claims[0]["subject"] == "民生银行首席经济学家温彬"
    assert claims[0]["claim_cjk_length"] == 20
    issues = domestic_viewpoint_quality_issues(
        {
            "viewpoints": {
                "by_topic": [
                    {
                        "topic": "研究宏观政策有关工作",
                        "heading": "认为宏观政策应发力提效",
                        "clusters": [
                            {
                                "summary": "认为宏观政策应提升强度",
                                "details": text,
                                "evidence": [],
                            }
                        ],
                    }
                ]
            }
        }
    )
    assert any(item["code"] == "attributed_claim_too_short" for item in issues)


def test_multiple_attributions_in_one_clause_are_checked_separately() -> None:
    claims = attributed_claims(
        "某研究院研究员张三认为，应完善长期机制，某大学教授李四指出，还要建立跨部门数据共享、实施评估和风险处置闭环。"
    )
    assert [item["subject"] for item in claims] == ["某研究院研究员张三", "某大学教授李四"]
    assert claims[0]["claim_cjk_length"] < 30


def test_multiple_speakers_sharing_one_claim_are_rejected() -> None:
    details = (
        "民生银行首席经济学家温彬、粤开证券首席经济学家罗志恒认为，"
        "下半年宏观政策应提高强度、加强增量储备并推动存量政策更快见效，形成更有力的逆周期调节。"
    )
    issues = domestic_viewpoint_quality_issues(
        {
            "viewpoints": {
                "by_topic": [
                    {
                        "topic": "研究宏观政策有关工作",
                        "heading": "认为宏观政策应发力提效",
                        "clusters": [
                            {
                                "summary": "认为宏观政策应提升强度",
                                "details": details,
                                "evidence": [],
                            }
                        ],
                    }
                ]
            }
        }
    )
    assert any(item["code"] == "multiple_voices_in_one_attribution" for item in issues)


def test_composite_title_is_not_mistaken_for_multiple_speakers() -> None:
    details = (
        "国家卫生健康委党组书记、主任雷海潮认为，应把健康优先融入规划、投入、治理和评价全过程，"
        "并完善基层服务、医防协同和健康影响评估机制。"
    )
    issues = domestic_viewpoint_quality_issues(
        {
            "viewpoints": {
                "by_topic": [
                    {
                        "topic": "研究健康优先有关工作",
                        "heading": "认为健康优先应融入治理全过程",
                        "clusters": [
                            {
                                "summary": "认为健康优先应融入治理全过程",
                                "details": details,
                                "evidence": [],
                            }
                        ],
                    }
                ]
            }
        }
    )
    assert not any(item["code"] == "multiple_voices_in_one_attribution" for item in issues)


def test_dashboard_rows_keep_eligible_unselected_candidate_pool_items() -> None:
    bundle = {
        "research_audit": {
            "domestic_media_research": {
                "candidate_pool_by_topic": [
                    {
                        "topic": "研究某项工作",
                        "candidates": [
                            {
                                "candidate_id": "selected-1",
                                "decision": "eligible",
                                "source": "媒体甲",
                                "title": "报道甲",
                                "url": "https://example.com/a",
                                "content_summary": "观点甲",
                            },
                            {
                                "candidate_id": "eligible-2",
                                "decision": "eligible",
                                "source": "媒体乙",
                                "title": "报道乙",
                                "url": "https://example.com/b",
                                "content_summary": "观点乙",
                            },
                            {
                                "candidate_id": "excluded-3",
                                "decision": "excluded",
                                "source": "媒体丙",
                                "title": "弱相关稿",
                                "url": "https://example.com/c",
                            },
                        ],
                    }
                ]
            }
        },
        "viewpoints": {
            "by_topic": [
                {
                    "topic": "研究某项工作",
                    "clusters": [
                        {
                            "evidence": [
                                {
                                    "candidate_id": "selected-1",
                                    "source": "媒体甲",
                                    "url": "https://example.com/a",
                                    "content": "观点甲",
                                }
                            ]
                        }
                    ],
                }
            ]
        },
    }
    rows = analysis_bundle_rows(bundle)
    by_candidate = {row.get("candidate_id"): row for row in rows if row.get("candidate_id")}
    assert set(by_candidate) == {"selected-1", "eligible-2"}
    assert by_candidate["eligible-2"]["candidate_pool_status"] == "eligible_not_selected_for_formal"


def test_repeated_voice_within_topic_is_a_quality_error() -> None:
    data = {
        "viewpoints": {
            "by_topic": [
                {
                    "topic": "研究某项工作",
                    "clusters": [
                        {
                            "summary": "观点一",
                            "details": "某研究院教授张三认为，应完善长期机制并补齐关键环节，推动政策目标转化为可执行的制度安排。",
                            "evidence": [{"attribution": "某研究院教授张三", "attribution_status": "named_person"}],
                        },
                        {
                            "summary": "观点二",
                            "details": "张三指出，应加强部门协同和信息共享，形成覆盖规划、实施、评估和反馈的闭环治理体系。",
                            "evidence": [{"attribution": "某研究院教授张三", "attribution_status": "named_person"}],
                        },
                    ],
                }
            ]
        }
    }
    issues = domestic_viewpoint_quality_issues(data)
    assert any(item["code"] == "repeated_voice_within_topic" for item in issues)


def test_unnamed_interview_expert_form_is_rejected() -> None:
    data = {
        "viewpoints": {
            "by_topic": [
                {
                    "topic": "研究某项工作",
                    "clusters": [
                        {
                            "summary": "观点",
                            "details": "上海证券报受访专家指出，应贯通基础研究、技术攻关、场景应用和生态建设，形成全链条产业支撑能力。",
                            "evidence": [{"source": "上海证券报", "attribution_status": "media_only"}],
                        }
                    ],
                }
            ]
        }
    }
    issues = domestic_viewpoint_quality_issues(data)
    assert any(item["code"] == "media_attribution_needs_review" for item in issues)


def test_stale_sentiment_counts_are_not_formal_results() -> None:
    stale = {
        "sentiment": {"positive": 100, "neutral": 0, "negative": 0},
        "sentiment_authority": "large_scale_sentiment_analysis",
        "sentiment_formal_ready": False,
        "sentiment_sample_status": "pending",
        "sentiment_denominator": 0,
    }
    assert formal_sentiment_row_ready(stale) is False
    assert formal_sentiment_available({"topic_stats": [stale]}) is False


def test_inherited_sample_sentiment_is_reset_before_current_run() -> None:
    samples = [
        {
            "sentiment": "positive",
            "sentiment_source": "ai_reviewed",
            "sentiment_status": "classified",
            "in_sentiment_denominator": True,
        }
    ]
    reset_inherited_sentiment(samples)
    assert samples[0]["inherited_sentiment_reference"]["sentiment"] == "positive"
    assert samples[0]["sentiment"] == "unknown"
    assert samples[0]["sentiment_source"] == "unprocessed"
    assert samples[0]["in_sentiment_denominator"] is False
