# Internal Analysis Bundle

The user never supplies this file. The CWH skill creates it after reading the monitoring workbook and researching public evidence.

```json
{
  "metadata": {
    "meeting_date": "YYYY-MM-DD",
    "monitoring_start": "YYYY-MM-DD",
    "monitoring_end": "YYYY-MM-DD",
    "research_completed_at": "ISO-8601",
    "evidence_mapping_version": "1.0",
    "authoring_run_id": "unique id of the viewpoint-authoring pass"
  },
  "research_audit": {
    "domestic_media_research": {
      "registry_version": "2026.08-v4",
      "open_search_completed": true,
      "coverage_by_topic": [
        {
          "topic": "exact workbook topic title",
          "checks": [
            {"source_id": "xinhua", "status": "hit", "execution_mode": "site_restricted_search", "queries": ["..."], "urls": ["https://..."]},
            {"source_id": "toutiao_articles", "status": "access_failed", "execution_mode": "platform_specific", "queries": ["site:toutiao.com ..."], "urls": [], "blocker": "platform pages unavailable to the current adapter"}
          ]
        }
      ],
      "candidate_pool_by_topic": [
        {
          "topic": "exact workbook topic title",
          "candidates": [
            {
              "candidate_id": "stable unique id",
              "discovery_query_id": "query id from saturation.rounds[].executions[]",
              "first_seen_round": 1,
              "viewpoint_cluster_key": "stable semantic family within this topic",
              "source": "publisher or speaker",
              "title": "article title",
              "url": "original URL",
              "published_at": "YYYY-MM-DD",
              "published_at_source_text": "verbatim source-page timestamp text",
              "published_at_verified_from_source": true,
              "raw_corpus_record_ids": ["public_article:row:8"],
              "discovery_route": "registry:xinhua or open_search:query_name",
              "content_summary": "substantive full-page evidence summary",
              "source_type": "mainstream_media, expert, self_media_platform, etc.",
              "source_tier": "authoritative, mainstream, finance_industry or public_platform",
              "decision": "eligible, duplicate or excluded",
              "decision_reason": "why it is retained, deduplicated or excluded",
              "formal_use": "selected or reserve; reserve is used by both bounded profiles",
              "reserve_reason": "required when formal_use is reserve",
              "source_snapshot": {
                "snapshot_id": "stable id for the immutable article-text snapshot",
                "url": "same original URL as the candidate",
                "title": "same article title as the candidate",
                "captured_at": "ISO-8601",
                "capture_method": "monitoring_export, browser_article_text or approved_reader",
                "source_text": "complete normalized article text used for review",
                "source_text_sha256": "sha256 of source_text encoded as UTF-8"
              }
            }
          ],
          "saturation": {
            "completed": true,
            "stop_reason": "coverage_minimum_then_one_zero_new_round_or_budget_exhausted, or the exhaustive two-round rule",
            "route_coverage": [
              {"route": "open_web", "status": "completed"},
              {"route": "public_platform", "status": "completed"}
            ],
            "rounds": [
              {
                "round": 1,
                "queries_or_sources": ["exact query text"],
                "executions": [
                  {
                    "query_id": "q1",
                    "query": "exact query text",
                    "backend": "agent-reach/exa",
                    "route": "open_web",
                    "status": "completed",
                    "executed_at": "ISO-8601",
                    "result_count": 8,
                    "result_urls": ["https://..."],
                    "retained_candidate_ids": ["candidate-1"]
                  }
                ],
                "new_candidates": 8,
                "new_eligible_candidates": 5,
                "new_independent_viewpoints": 3
              },
              {"round": 2, "queries_or_sources": ["exact second query"], "executions": ["same structured execution object"], "new_candidates": 1, "new_eligible_candidates": 0, "new_independent_viewpoints": 0},
              {"round": 3, "queries_or_sources": ["exact third query"], "executions": ["same structured execution object"], "new_candidates": 0, "new_eligible_candidates": 0, "new_independent_viewpoints": 0}
            ]
          }
        }
      ]
    }
  },
  "viewpoints": {
    "by_topic": [
      {
        "topic": "exact workbook topic title",
        "heading": "evidence-backed analytical conclusion, not a copy of the agenda",
        "evidence_shortfall": {"reason": "required in bounded mode below four selected voices", "search_evidence": "query ids and blockers", "reviewed_by": "AI or human reviewer"},
        "single_cluster_exception": {"reason": "required only for a one-cluster topic", "search_evidence": "query ids and pool evidence", "reviewed_by": "AI or human reviewer"},
        "clusters": [
          {
            "summary": "one concise viewpoint conclusion",
            "details": "generated by scripts/normalize_cwh_analysis.py from evidence[].formal_claim; model-written text is replaced",
            "thin_cluster_exception": {"reason": "required only below two voices or 120 Chinese characters", "search_evidence": "query ids and pool evidence", "reviewed_by": "AI or human reviewer"},
            "evidence": [
              {
                "topic": "exact workbook topic title",
                "source": "publisher or speaker",
                "source_type": "mainstream_media or self_media",
                "platform": "news or wechat",
                "title": "article title",
                "content": "supporting excerpt or faithful paraphrase",
                "url": "original URL",
                "published_at": "YYYY-MM-DD",
                "research_query": "query used",
                "candidate_id": "id of an eligible candidate above",
                "selection_reason": "why this evidence represents its cluster",
                "evidence_id": "stable unique claim mapping id",
                "source_snapshot_id": "candidate source_snapshot.snapshot_id",
                "article_title": "same title as candidate and snapshot",
                "attribution": "full institution, role and person; or exact media/account voice",
                "attribution_status": "named_person, media_voice or self_media",
                "speaker_name": "one person, media outlet or account only",
                "speaker_role": "role/institution when the source provides it",
                "source_excerpt": "one continuous source-text span containing this speaker and claim",
                "source_excerpt_start": 0,
                "source_excerpt_end": 100,
                "formal_claim": "the exact claim text used inside cluster.details",
                "wording_fidelity": "verbatim, lightly_trimmed or faithful_paraphrase",
                "semantic_review": {
                  "verdict": "fully_supported",
                  "reviewed_by": "approved model or human reviewer",
                  "reviewed_at": "ISO-8601",
                  "rationale": "why the formal claim does not exceed the source",
                  "propositions": [
                    {
                      "text": "one independently checkable proposition from formal_claim",
                      "verdict": "fully_supported",
                      "source_quote": "continuous supporting text",
                      "source_quote_start": 0,
                      "source_quote_end": 50,
                      "rationale": "how this source span supports the proposition"
                    }
                  ]
                }
              }
            ]
          }
        ]
      }
    ]
  },
  "comments": {
    "selected": [
      {
        "topic": "exact workbook topic title",
        "source": "anonymized account or platform user",
        "source_type": "netizen_comment",
        "platform": "weibo, douyin, xhs, bili, zhihu, forum",
        "content": "verbatim public wording or an explicitly marked summary",
        "url": "original post/comment URL",
        "published_at": "YYYY-MM-DD HH:MM",
        "is_comment": true,
        "quote_verified": true,
        "evidence_mode": "verbatim_public_comment",
        "report_order": 1,
        "comment_heading": "明确的观点结论，例如：肯定全民健身政策惠民利民",
        "ai_formal_include": true,
        "ai_semantic_quality": "substantive",
        "ai_formal_reason": "说明这条评论为什么有信息量、适合或不适合进入正文"
      }
    ]
  }
}
```

Rules:

- The author submits semantic fields and actual source facts, not full report prose or dashboard code. Before draft validation, the controller calls `complete_cwh_evidence_structure.py` to fill missing deterministic IDs, full-text hashes and unique exact excerpt offsets. It preserves existing values, does not guess ambiguous matches, and never edits frozen verified bundles. Query-result snapshots and their candidate references still need consistent identifiers; this helper does not manufacture collection history. Independent review supplies certification only in the next stage.

- Topic names must exactly match workbook topics.
- Ingest the raw stage's complete `public_article_evidence` corpus independently of `公众TOP`. The appendix TOP review batch and final TOP10 are never the domestic-viewpoint candidate pool. For every raw corpus row, retain a link to one or more candidate decisions or an explicit corpus-level duplicate/exclusion reason; a candidate pool that silently drops raw rows fails review.
- Report `pool_summary` separately for `raw_monitoring`, `fixed_registry_web`, `open_web` and `public_platform_web`. Every candidate carries `discovery_origin` and its concrete query ID. Stable-source checks marked `hit` carry web-discovered `candidate_ids`; raw-monitoring candidates do not satisfy a web hit. Every URL saved in a completed search snapshot must appear in the candidate pool with an explicit eligible, duplicate or excluded decision. Backend rate limits, TLS failures and login blocks remain `access_failed`; they are not converted into zero-result searches.
- Treat worksheet dimension metadata as untrusted provenance. If a raw export advertised `A1` but dimension recalculation exposed populated rows, preserve that fact in the raw audit and use the recalculated corpus; never infer “no evidence” from the stale dimension.
- Read `config/source_registry.v1.json` and `config/execution_policy.v1.json`. In either bounded profile, execute the grouped registry lanes emitted by `research_plan.json`; in `exhaustive`, search every `must_check` domestic source separately. Record `hit`, `no_relevant_result`, `access_failed` or `not_applicable`. Missing required rows fail the gate.
- For `public_platform` sources, record the actual platform-specific or site-restricted queries and `execution_mode`. Use `weread_platform_search` for WeChat discovery and `browser_platform_search` for Baijiahao when those adapters run. A generic search-engine miss cannot be written as `no_relevant_result`. When a captcha or login is pending, use `waiting_login` with `terminal=false`, a screenshot/checkpoint and a concrete resume action; continue all other approved routes. When the platform cannot be searched for another reason, use `access_failed` with a concrete blocker. Candidate-pool saturation is valid only after both `open_web` and `public_platform` routes are completed or honestly blocked.
- Treat historical baseline accounts as evaluation samples, not permanent must-check accounts. Persist a platform calibration audit containing baseline sample counts, topic-platform route coverage, candidate recall and failure reasons. A platform with repeated benchmark misses is an adapter gap even if other platforms supply enough prose evidence.
- The registry is a priority seed, not an allowlist. Open search may and should retain relevant sources outside the registry. Build a per-topic candidate pool before viewpoint selection and preserve every discovered result with an `eligible`、`duplicate` or `excluded` decision plus a reason; never save only the two or three rows used in prose.
- Obey the selected execution profile. Both bounded profiles stop after required lane coverage and one zero-new round, or when its query/fetch/time budget is exhausted; `exhaustive` requires two zero-new rounds. Every executed round must preserve concrete query, backend, route, timestamp, result count, URL snapshot and retained candidate IDs.
- Every candidate carries `discovery_query_id` and `first_seen_round`; every eligible candidate also carries `viewpoint_cluster_key`. The validator verifies that the candidate URL exists in the referenced query-result snapshot. This prevents a sparse selected-only pool from being disguised as saturated research.
- Every eligible public-web candidate carries `published_at`, `published_at_source_text` and `published_at_verified_from_source=true`; the parsed time must fall within the monitoring window. Search-result dates, inferred dates and post-window pages may remain as excluded or explicitly labelled supplemental evidence but cannot support period prose.
- Cluster the eligible pool first. In either bounded profile, mark representative voices `formal_use=selected` and additional valid candidates `formal_use=reserve` with a reason; target 6-12 and cap formal prose at 12 independent voices per topic. Selected candidates must map to a formal cluster and final outputs; reserve candidates remain in the research audit. In `exhaustive`, every eligible candidate maps to formal prose. Exact mirrors remain `duplicate`.
- Select from the candidate pool with a scored rationale: direct meeting/topic relevance first, then verbatim traceability and full-text depth, distinct viewpoint contribution, independent publisher/speaker, contemporaneity, and source-type diversity. High authority alone does not outrank a more substantive, traceable self-media or expert interpretation; low-substance repetition never wins merely to fill a quota.
- Keep `domestic_media_research`, `domestic_comment_collection` and `overseas_media_research` as separate audits. Article discovery never proves that a platform comment adapter ran.
- Domestic comment collection covers every workbook topic and configured platform lane. In either bounded profile, use at most four query executions in `bounded_40m` or six in `bounded_60m` and retain at most 30 reviewed candidates per topic, then select 2-3 traceable comments for a ready topic; `exhaustive` continues to saturation. Preserve per-topic/per-platform results and blockers.
- Each topic `heading` must be an analytical conclusion such as `认可……`、`认为……`、`建议……` or `期待……`; never copy `听取……汇报`、`研究……工作` or `审议通过……` as the heading.
- Build 2-6 distinct viewpoint clusters per topic when evidence permits. A substantive topic normally needs at least two mature clusters. A one-cluster result must include `single_cluster_exception` with the actual search evidence; if the eligible pool already contains two or more viewpoint families, the exception cannot be used.
- Each mature cluster normally cites 2-4 selected independent voices. Preserve one complete attributed claim per voice, normally 45-120 Chinese characters. A thinner cluster must include `thin_cluster_exception` backed by completed search evidence.
- The model does not author `details`. `scripts/normalize_cwh_analysis.py` regenerates it from ordered `evidence[].formal_claim` rows, adding the verified subject and a fixed attribution verb only when needed. This makes attribution, ordering and punctuation deterministic across model families.
- Set `metadata.evidence_mapping_version=1.0`. Every eligible candidate must retain an immutable `source_snapshot` with the complete article text and SHA-256. Search snippets, generated summaries and stitched passages are not source snapshots.
- Preserve source-level wording evidence for every formal claim. Each evidence row must add `evidence_id`, `source_snapshot_id`, `article_title`, `attribution`, `attribution_status` (`named_person`, `media_voice` or `self_media`), one `speaker_name`, optional `speaker_role`, one continuous `source_excerpt` with exact character offsets, `formal_claim`, `wording_fidelity` (`verbatim`, `lightly_trimmed` or `faithful_paraphrase`) and a complete `semantic_review`. `source_excerpt` is the audit anchor; `formal_claim` may improve readability but must not add a stronger conclusion than the excerpt supports.
- Decompose each `formal_claim` into independently checkable `semantic_review.propositions`. Each proposition must be `fully_supported` and point to a continuous `source_quote` plus exact offsets in the same immutable snapshot. `partially_supported`, `unsupported` and `uncertain` evidence is audit-only and blocks formal rendering.
- Run `scripts/domestic_evidence_mapping.py` after viewpoint review and again after Word/HTML rendering. The first gate checks snapshot hashes, title/URL/candidate identity, one-speaker attribution, exact source spans, numbers and quoted terms. The second gate verifies that the same `evidence_id` mapping survives in `report_data.json`, the dashboard and Word body.
- The viewpoint-authoring pass stops before semantic certification. A separate `domestic_evidence_verification` pipeline stage reads the frozen draft hash and writes `domestic_evidence_semantic_review.json` with `review_version=1.0`, `review_pass=independent_second_pass`, a new `reviewer_run_id`, the exact `source_bundle_sha256`, and one review per `evidence_id`. The reviewer run id must differ from `metadata.authoring_run_id`. A deterministic merge produces `analysis_bundle_verified.json`; only that verified bundle may enter hotwords and rendering.
- In one system subtopic, use the same named person or source in only one viewpoint cluster unless the audit records a justified exception. Merge related statements from one source before selecting other independent voices. Cross-subtopic reuse should be rare and must represent a genuinely different claim.
- A source's own analysis uses `某媒体认为/称/建议`; a verified quoted person uses full institution/title/name; a genuinely anonymous source uses `某媒体援引业内人士观点称` plus a review marker. Never manufacture the construction `某媒体受访专家指出` without a named person.
- Each speaking subject is checked separately, including multiple people quoted in one article. Each attributed proposition should normally retain 45-120 Chinese characters of substantive source meaning. Claims below 30 Chinese characters fail the formal gate and must be expanded from the same source excerpt, combined with related wording from that source, or removed. Generic padding is not allowed. Bare noun phrases such as `宏观分析人士` and `政策解读文章` are not attribution verbs.
- When one raw article contains several named experts, institutions or editorial voices, create separate evidence rows and attribution checks for each substantive speaker. One article URL may therefore support several independently named voices, but their excerpts and claims must not be conflated.
- When several URLs carry the same speaker and materially identical claim, keep one `eligible` evidence row and mark the remaining pages `duplicate`. Never copy the same `formal_claim` into multiple visible evidence rows merely because the URL or publisher differs.
- If only one mature cluster exists under a subtopic, render it directly after the numbered top-level heading; do not emit a lone `一是`.
- Keep at least one evidence URL per viewpoint cluster and prefer two independent sources for important claims.
- Set `quote_verified=true` only for verbatim wording tied to a working original URL. The renderer quotes only verified rows.
- A historical benchmark quotation is not evidence by itself. Exact wording that cannot be tied to an original platform URL/comment identifier remains `untraceable_benchmark_text`, stays out of formal quotation marks and is reported as a benchmark audit gap rather than silently copied.
- If no traceable original comment is available, add an unquoted row with `quote_verified=false`, `evidence_mode=public_discussion_summary`, and a source URL. Never invent a username or quotation.
- AI must semantically review every traceable comment before formal rendering. Set `ai_formal_include=true` only when the comment expresses a substantive opinion, expectation, reason, policy judgment or concrete suggestion. Set it to `false` for pure reactions, greetings, repost notices, slogans without content, copied article text and remarks unrelated to the meeting. The script's short-text filter is only a final guard; it is not the semantic judge.
- Prefer 2-3 traceable public expressions in each selected comment group. Use `report_order` to control the formal sequence and one shared AI-reviewed `topic_comment_heading` for a specific conclusion such as `认为数字中国建设更系统化`、`肯定全民健身政策惠民利民`、`支持推动新兴支柱产业发展`、`期待做好防汛救灾工作` or `期待优化物流网络体系`. One system agenda/subtopic is one formal comment group; different reactions under the same agenda remain evidence dimensions inside that group and must not become separate numbered items. Do not mechanically use `关注+议题名称` for every group.
- Overseas comment rows use the same `ai_formal_include` gate and may add `comment_heading` plus `comment_summary`. Formal prose must synthesize Chinese viewpoints and quote one or two representative Chinese translations without account IDs.
- After the first research pass, inspect the audit actions. Continue researching `deepen_viewpoint_evidence` and `deepen_public_comment_evidence` items before rendering the final report; unresolved items remain explicit quality warnings and must never be filled with invented prose.
- Review the full overseas title/body already present in the raw monitoring Excel before any supplemental search. Set `meeting_relevance=true` and `formal_include=true` only when the article substantively reports or interprets the meeting itself; broad topical overlap is insufficient. Then use AI semantic review of the article body to populate `ai_report_category` (`事实性报道`、`解读性报道` or `借题炒作/风险解读`), `classification_reason` and `classification_confidence`, and preserve those fields through the standard workbook. A crawler label, title keyword, negative word or automatic category alone is never a final classification, and a missing category must never default to factual.
- Set `interpretive_verified=true` only when an overseas item contains a verifiable analytical passage. Every overseas row eligible for formal output must retain the original and provide reviewed Simplified Chinese fields (`title_cn_simplified`, `summary_cn_simplified`, `source_cn_simplified`). Traditional Chinese is normalized with the complete OpenCC conversion layer; foreign-language translation and the resulting names, policy terms, numbers and meaning are reviewed by AI. Traditional Chinese and foreign-language text may remain in evidence and the dashboard but never enters formal prose or appendix cells directly.
- The formal overseas appendix is a representative TOP10 selected after relevance review, category review, translation and story deduplication. The structured evidence and dashboard keep every accepted row.
- Public evidence normally fills qualitative prose only. A reviewed in-window overseas-media report is the sole count exception: it must be reconciled into the standard workbook before report rendering through the complete overseas audit. The analysis bundle never modifies workbook totals, dates, channel counts or WeChat metrics. Formal sentiment ratios come only from the audited comment-level sentiment pipeline.
