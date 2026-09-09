from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ingest_monitoring_workbook import ingest_workbook


SOURCE_REGISTRY_PATH = Path(__file__).resolve().parent.parent / "config" / "source_registry.v1.json"


def load_source_registry() -> dict[str, Any]:
    return json.loads(SOURCE_REGISTRY_PATH.read_text(encoding="utf-8-sig"))


def stable_source_tasks(topic: str, meeting_date: str, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    subject = clean_topic(topic)
    tasks = []
    for source in sources:
        domains = [str(value).strip() for value in source.get("domains") or [] if str(value).strip()]
        query = " OR ".join(f"site:{domain}" for domain in domains)
        tier = str(source.get("tier") or "")
        platform_specific = tier in set(
            load_source_registry().get("execution", {}).get("platform_specific_search_required_for_tiers") or []
        )
        query_families = [
            f"({query}) {meeting_date} 国务院常务会议 {subject}" if query else f"{meeting_date} 国务院常务会议 {subject}",
        ]
        if platform_specific:
            query_families.extend(
                [
                    f"({query}) {subject} 释放什么信号 影响" if query else f"{subject} 释放什么信号 影响",
                    f"({query}) {subject} 认为 认可 建议 期待" if query else f"{subject} 认为 认可 建议 期待",
                    f'({query}) "{source["name"]}" {subject}' if query else f'{source["name"]} {subject}',
                ]
            )
        tasks.append(
            {
                "source_id": source["id"],
                "source_name": source["name"],
                "region": source["region"],
                "tier": tier,
                "must_check": bool(source.get("must_check")),
                "query": query_families[0],
                "query_families": query_families,
                "execution_mode": "platform_specific" if platform_specific else "site_restricted_search",
                "reader": source.get("reader"),
                "article_adapter": source.get("article_adapter"),
                "fallback_readers": source.get("fallback_readers") or [],
                "source_type": source.get("source_type"),
                "evidence_policy": source.get("evidence_policy"),
                "article_url_patterns": source.get("article_url_patterns") or [],
                "comment_adapter": source.get("comment_adapter"),
                "login_required": bool(source.get("login_required")),
                "waiting_login_terminal": bool(source.get("waiting_login_terminal", False)),
            }
        )
    return tasks


def clean_topic(value: str) -> str:
    return value.strip().strip("，。；")


def research_queries(topic: str, meeting_date: str) -> dict[str, list[str]]:
    subject = clean_topic(topic)
    return {
        "official_confirmation": [
            f"{meeting_date} 国务院常务会议 {subject}",
        ],
        "media_and_expert_viewpoints": [
            f"{meeting_date} 国务院常务会议 {subject} 专家 解读",
            f"{subject} 媒体 评论 建议",
            f"{subject} 释放什么信号 意味着什么 影响",
            f"{subject} 受益 利好 风险 争议",
        ],
        "self_media_viewpoints": [
            f"微信读书搜一搜：{meeting_date} 国务院常务会议 {subject}",
            f"今日头条站内/site限定：{subject} 国常会 观点 影响",
            f"百度可视浏览器+百家号限定：{subject} 观点 影响",
            f"{subject} 公众号 头条号 百家号 认可 建议 期待",
        ],
        "academic_and_think_tank_viewpoints": [
            f"site:edu.cn {meeting_date} {subject} 专家 认为 建议",
            f"{meeting_date} {subject} 研究院 智库 学者 解读",
            f"{meeting_date} {subject} 协会 学会 研讨 观点",
        ],
        "finance_and_industry_viewpoints": [
            f"{meeting_date} {subject} 研报 券商 首席 分析",
            f"{meeting_date} {subject} 行业研究 政策影响 风险",
        ],
        "named_entity_expansion": [
            f"对首轮每个具名专家、机构和自媒体账号继续执行“名称+{subject}”定向复核，并保存原始结果URL。",
        ],
        "public_discussion": [
            f"{meeting_date} 国务院常务会议 {subject} 网友 评论",
            f"{subject} 大家怎么看",
        ],
        "overseas": [
            f"{meeting_date} China State Council executive meeting {subject}",
        ],
    }


def build_plan(workbook_path: str, agenda: str = "") -> dict[str, Any]:
    system_data = ingest_workbook(workbook_path)
    registry = load_source_registry()
    sources = registry.get("sources") or []
    paused_platforms = {
        str(value).strip().lower()
        for value in (registry.get("execution") or {}).get("paused_platforms") or []
        if str(value).strip()
    }
    foreign_platforms = [value for value in ["grounding", "x", "youtube", "reddit"] if value not in paused_platforms]
    period = system_data.get("monitoring_period") or {}
    meeting_date = str(period.get("start") or "")
    topics = [str(item.get("title") or "").strip() for item in system_data.get("topics") or []]
    return {
        "version": "2.0",
        "input_contract": {
            "user_inputs": ["meeting_agenda_or_date", "monitoring_system_workbook"],
            "agenda": agenda,
            "system_workbook": str(Path(workbook_path)),
        },
        "monitoring_period": period,
        "topics": [
            {
                "topic": topic,
                "queries": research_queries(topic, meeting_date),
                "stable_source_tasks": stable_source_tasks(topic, meeting_date, sources),
                "minimum_evidence": {
                    "fixed_result_target": None,
                    "stop_rule": "candidate_pool_saturation_not_item_count",
                    "formal_sources_per_mature_cluster": "all_eligible_independent_samples_no_upper_cap",
                    "viewpoint_clusters": "evidence_driven_normally_2_to_6",
                    "traceable_public_comments": 0,
                },
                "candidate_pool_contract": {
                    "scope": "all_accessible_relevant_public_web_results",
                    "registry_role": "priority_seed_not_allowlist",
                    "retain_all_discovered_candidates": True,
                    "candidate_decisions": ["eligible", "duplicate", "excluded"],
                    "required_candidate_fields": [
                        "candidate_id",
                        "discovery_query_id",
                        "first_seen_round",
                        "source",
                        "title",
                        "url",
                        "published_at",
                        "discovery_route",
                        "content_summary",
                        "source_type",
                        "source_tier",
                        "decision",
                        "decision_reason",
                    ],
                    "saturation_rule": {
                        "stop_reason": "two_consecutive_rounds_no_material_new_independent_viewpoint",
                        "required_zero_new_rounds": 2,
                        "required_route_coverage": ["open_web", "public_platform"],
                        "platform_empty_result_rule": "Only a platform-specific executed query may conclude no_relevant_result; a generic web-search miss is not a platform result.",
                        "round_fields": [
                            "round",
                            "queries_or_sources",
                            "executions",
                            "new_candidates",
                            "new_eligible_candidates",
                            "new_independent_viewpoints",
                        ],
                        "execution_fields": [
                            "query_id",
                            "query",
                            "backend",
                            "route",
                            "status",
                            "executed_at",
                            "result_count",
                            "result_urls",
                            "retained_candidate_ids",
                        ],
                        "proof_rule": (
                            "A zero-new round is valid only when its concrete queries, backend, execution time, "
                            "result URLs and retained candidate IDs are saved. Labels such as general_open_search "
                            "or 专家定向检索 are not query evidence."
                        ),
                    },
                    "formal_selection_rule": (
                        "Cluster the complete eligible pool first. Every eligible independent sample must be assigned to "
                        "an existing viewpoint cluster or create a new cluster, and every assigned sample must enter both "
                        "the dashboard and formal prose. Exact mirrors remain duplicate audit records and never become "
                        "visible cards, formal sentences or independent voices; keep the decision reason on every row."
                    ),
                },
                "domestic_viewpoint_contract": {
                    "distinct_voice_per_cluster": True,
                    "same_voice_once_per_topic_by_default": True,
                    "preserve_source_excerpt": True,
                    "preferred_claim_cjk_range": [45, 120],
                    "minimum_claim_cjk": 30,
                    "media_voice_form": "某媒体认为/称/建议",
                    "named_person_form": "完整机构+职务+姓名+认为/指出/建议",
                    "anonymous_source_form": "某媒体援引业内人士观点称，并保留核验标记",
                    "formal_body_prohibitions": [
                        "样本来源或公开网络补证清单",
                        "报道汇集某某等对某议题的分析",
                        "同一人物同一观点因转载链接不同而重复成文",
                    ],
                    "topic_density": {
                        "normal_mature_clusters": [2, 4],
                        "independent_voices_per_cluster": "all_eligible_no_upper_cap",
                        "preferred_claim_cjk_range_per_voice": [45, 120],
                        "cluster_detail_length": "scales_with_eligible_voice_count_no_upper_cap",
                        "single_cluster_rule": (
                            "A substantive topic normally has at least two independently supported viewpoint clusters. "
                            "A single cluster is allowed only with a structured single_cluster_exception proving that "
                            "the complete audited eligible pool contains one material viewpoint family."
                        ),
                    },
                },
            }
            for topic in topics
        ],
        "global_tasks": {
            "public_platform_articles": {
                "runner": "scripts/run_cwh_public_platform_research.py",
                "required_platforms": ["toutiao_articles", "wechat_public", "baijiahao"],
                "waiting_login_terminal": False,
                "rule": (
                    "Execute each platform separately for every workbook topic. WeChat uses WeRead search then mp.weixin original-page verification; "
                    "Baijiahao uses a visible Baidu browser and human captcha/login handoff when required. A waiting adapter never ends the whole workflow: "
                    "checkpoint it, continue all approved fallbacks and resume later."
                ),
            },
            "public_comments": {
                "target_topics": "all_workbook_topics",
                "target_quotes": None,
                "fixed_result_target": None,
                "stop_rule": "per_topic_platform_coverage_and_saturation_not_quote_count",
                "rule": (
                    "Search every workbook topic through every currently permitted comment adapter and topic-specific query family. "
                    "Retain the complete accessible candidate pool and stop by saturation or a recorded platform blocker, never after a fixed quote count. "
                    "Only verbatim text with an original platform URL and comment identifier may be quoted; otherwise preserve an unquoted public-discussion summary."
                ),
                "audit_granularity": "topic_by_platform",
                "required_coverage_fields": [
                    "topic",
                    "source_id",
                    "status",
                    "execution_mode",
                    "queries_or_seed_urls",
                    "result_count",
                    "eligible_comment_ids",
                ],
            },
            "overseas": {
                "rule": "Prefer the monitoring workbook overseas list. Use MediaSpider Supervisor's foreign collector and public search to expand traceable overseas media and public-discussion evidence; these rows cannot change workbook counts.",
                "mediaspider_foreign": {
                    "platforms": foreign_platforms,
                    "paused_platforms": sorted(paused_platforms),
                    "foreign_mode": "fallback-only",
                    "deep_crawl": True,
                    "run_until": "no material new high-relevance URLs are found or a platform blocker is recorded",
                },
            },
        },
        "source_registry": {
            "version": registry.get("version"),
            "path": str(SOURCE_REGISTRY_PATH),
            "mode": (registry.get("execution") or {}).get("mode"),
            "required_source_ids": [row["id"] for row in sources if row.get("must_check")],
            "domestic_media_ids": [row["id"] for row in sources if row.get("region") == "domestic" and row.get("tier") != "comment_platform"],
            "domestic_comment_ids": [row["id"] for row in sources if row.get("tier") == "comment_platform"],
            "overseas_media_ids": [row["id"] for row in sources if row.get("region") == "overseas"],
        },
        "research_audit_contract": {
            "required_sections": ["domestic_media_research", "domestic_comment_collection", "overseas_media_research"],
            "coverage_states": (registry.get("execution") or {}).get("record_states") or [],
            "per_topic_coverage_required": True,
            "open_search_required": True,
            "candidate_pool_required": True,
            "saturation_required": True,
            "fixed_result_target_disabled": True,
            "rule": "先逐项执行稳定来源库，再做不受名单限制的开放检索；保留全部候选和筛选理由，连续两轮无新增高相关独立观点后才停止，媒体文章与评论采集不得混用状态。",
        },
        "authority_rules": [
            "All totals, channel counts, daily trends, subevent counts, overseas counts and WeChat TOP metrics come from the monitoring workbook. Formal sentiment ratios come only from audited comment-level analysis.",
            "Public research supplies qualitative evidence by default. A reviewed in-window overseas news report may affect only the overseas-news count after pre-workbook AI review and deduplication; report rendering never patches totals.",
            "Research must stay within the monitoring window for contemporaneous reporting; later material is excluded or labeled follow-up.",
            "Every quoted comment requires original wording, platform, URL and timestamp when available.",
            "Domestic viewpoint prose must preserve source excerpts, avoid reusing one voice across multiple clusters of the same subtopic, distinguish media editorial judgment from quoted expert judgment, and reject attributed claims shorter than 30 Chinese characters.",
            "Stable-source coverage is mandatory before open search. Every required source must be recorded as hit, no_relevant_result, access_failed or not_applicable for every topic.",
            "The registry is a priority seed, not an allowlist. Preserve the complete accessible candidate pool from registry and open-web discovery before selecting representative formal evidence.",
            "Do not stop after finding two sources. Stop only after two consecutive search rounds add no material independent viewpoint, and record every round plus every candidate decision.",
            "A saturation round is invalid unless it preserves concrete query executions, backend, execution time, result URL snapshot and retained candidate IDs. A self-reported zero count without result evidence never advances the pipeline.",
            "Every substantive topic normally needs at least two mature viewpoint clusters. A single-cluster result requires a structured evidence-based exception; page count is never padded, but thin evidence may not be silently accepted.",
            "A public-platform source may be recorded as no_relevant_result only after a platform-specific or site-restricted query was actually executed and its query evidence was saved; a generic web-search miss is not a platform result.",
            "Domestic media research and domestic public-comment collection are separate audited jobs; a media article hit never proves that comments were collected. Comment coverage must be recorded for every topic-platform pair, including honest login or access blockers.",
        ],
        "next_artifact": "analysis_bundle.json",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the internal research plan for a two-input CWH report run.")
    parser.add_argument("system_workbook")
    parser.add_argument("--agenda", default="")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(build_plan(args.system_workbook, args.agenda), ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
