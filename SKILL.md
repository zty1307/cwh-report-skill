---
name: cwh-report-skill
description: Generate State Council executive meeting (CWH/国务院常务会) public-opinion reports from authoritative monitoring-system exports, including an independently testable raw-multi-workbook to standard-summary-workbook stage. Use for raw system Excel bundle normalization, AI-reviewed overseas-record reconciliation, standard workbook ingestion, agenda splitting, fixed event/keyword/statistical口径, media and netizen detail analysis, sentiment integration, viewpoints, hotwords, charts, mentor-style Excel, formal Word and HTML output.
---

# CWH Report Skill

## Goal

Automate the department's post-monitoring workflow:

> meeting agenda + monitoring-system exports -> normalized data -> analysis -> charts -> mentor-style Excel -> formal Word report + HTML dashboard.

The monitoring system is the authoritative source for传播总量、平台分布、逐日趋势、子事件数量 and公众号指标. Two audited corrections are exceptions: formal sentiment ratios come from `large-scale-sentiment-analysis`, and the raw `境外新闻` channel is reconciled from a complete AI-reviewed, deduplicated, in-window record universe before the standard workbook is finalized.

Produce one formal report plus structured artifacts. Keep engineering status and missing-input requests in `cwh_audit.json`, not in the formal body.

## User Input Contract

The normal formal workflow starts from two user inputs:

1. The meeting date or full agenda text, such as `7月10日国务院常务会`.
2. Either one organized standard summary workbook or a directory/bundle of raw department monitoring-system exports (`.xlsx/.xlsm/.csv/.tsv/.json`).

Do not ask the user to prepare a third file. Media/expert evidence, public-discussion evidence, analysis JSON, charts, regenerated Excel and Word are internal skill artifacts.

## Input Routing and Stage Boundaries

Keep four independently runnable stages inside this skill:

1. `raw workbook stage`: raw system exports -> standard summary workbook + comparison audit.
2. `domestic comment collection stage`: MediaSpider Supervisor and/or reviewed Agent Reach article seeds -> traceable in-window domestic comment detail; the current project profile excludes Xiaohongshu, Tieba and every foreign platform.
3. `sentiment stage`: system, reviewed MediaSpider or reviewed Agent Reach comment details -> audited row-level sentiment handoff and preparation artifacts.
4. `report stage`: standard summary workbook -> research, analysis, Word, report workbook and HTML dashboard.

### Non-bypassable formal-report entrance gate

In formal system mode, do not generate Word, report Excel or HTML until all of the following are true: a complete `analysis_bundle.json` contains evidence-backed domestic viewpoint clusters for every system subtopic; every eligible domestic article has an immutable full-text source snapshot and every formal claim passes the one-to-one `evidence_id` mapping gate defined in `references/analysis_bundle_schema.md`; real traceable domestic comments have completed the sentiment handoff; the hotword audit is complete; and the report's overseas appendix is derived only from the standard workbook's reviewed overseas universe. A missing item must produce only `report_data.json`, `cwh_audit.json` and the next research/collection actions. Do not render an incomplete formal report with placeholder prose.

`--no-auto-web`、`--no-agent-reach-plan` and `--no-tasks` are diagnostic switches, not formal-gate overrides. Do not use them for a full-report request unless a complete audited replacement artifact has already been supplied. The absence of an overseas review flag means reject, not include. Never restore excluded overseas rows from a raw sample file, classify formal overseas prose by keywords, or fall back from a reviewed summary to the full scraped page body.

Inspect workbook names and sheet structure before choosing the route. If the input already contains the standard sheets `关键词`、`总事件`、`子事件1...N`、`子事件数据汇总`, skip the raw workbook stage. If the input is a multi-file raw bundle such as `子1...子N` heat-analysis exports plus total-event, overseas-news and public-article samples, run the raw workbook stage first.

When the user asks only to organize, compare or test data workbooks, stop after stage 1 unless they explicitly request comment collection or sentiment. Run stage 2 when no system comment details exist and the user has authorized public comment collection. Run stage 3 on the resulting comment detail. When the user asks for the full report from raw exports, run stage 1, collect domestic comments when needed, complete stage 3, and pass the generated standard workbook and validated sentiment results to stage 4.

Read `references/raw_workbook_pipeline.md` before running or adapting stage 1. Keep its scripts, configuration, tests, outputs and audit independent from report rendering code.
Read `references/sentiment_pipeline.md` before running stage 2. Keep comment extraction and sentiment preparation independent from both raw workbook rendering and formal report rendering.

## Source Precedence

Before applying precedence, load `config/source_registry.v1.json`. It is a versioned priority seed library derived from reviewed baseline reports and expanded with required official, mainstream, finance/industry, public-platform, domestic-comment and overseas outlets. Historical baseline accounts are evaluation samples, not permanent must-check accounts: aggregate them by publishing platform, use missed baseline samples to diagnose platform-adapter gaps, and open or improve the affected platform route. For every system subtopic, execute each `must_check` source first and persist a coverage matrix (`hit`, `no_relevant_result`, `access_failed`, `waiting_login`, `not_applicable`), then run open search without a source allowlist for new expert, media and self-media voices. Preserve every discovered result in a per-topic candidate pool with `eligible`、`duplicate` or `excluded` and a reason. The registry is a stable starting set, not a closed allowlist or a formal-selection shortcut. Keep domestic article research, domestic comment collection and overseas research in separate audits.

Use this order:

1. Monitoring-system summary workbook: authoritative numerical口径.
2. Monitoring-system media/comment detail exports, when present: preferred evidence universe.
3. Reviewed sentiment results from `large-scale-sentiment-analysis`: required for every formal sentiment percentage; system labels never enter the formal denominator.
4. Agent-reach/public search: automatic qualitative evidence for media, expert, self-media and public-discussion sections when the summary workbook has no detail rows. Domestic rows and overseas social comments never alter system totals. An in-window overseas-media report may enter the audited overseas count only when it is passed through the same complete AI review, publisher classification and cross-source deduplication as system rows.
5. MediaSpider Supervisor foreign collector: automatic overseas evidence supplement when the local collector is available. Use `grounding` for overseas media and `x/youtube/reddit` for overseas public discussion. Only reviewed `grounding`/news rows can enter the audited overseas-media universe; overseas social rows never enter media totals.
6. MediaSpider Supervisor domestic collector: approved fallback source for formal sentiment when system comment detail is absent. Only real, traceable comments/replies inside the monitoring window may enter the sentiment gate; these rows never alter monitoring-system传播 totals.
7. Agent Reach-discovered domestic public articles plus an audited no-login public-comment adapter: supplemental fallback when MediaSpider is blocked. Search snippets, comment counts and article bodies never become comments. Every accepted row must retain article URL, comment ID, timestamp and reviewed topic mapping.

In formal system mode:

- Do not dynamically change the system's event keywords or event IDs.
- Generate domestic-comment tasks only when system comment detail is absent and the workflow/user has authorized public comment collection.
- Do not enforce arbitrary targets such as 5,000 samples or 200 comments.
- If the workbook lacks qualitative detail rows, automatically research public evidence. Do not stop and ask the user for another input.
- Public research normally fills prose and evidence links only. The sole numerical exception is a reviewed in-window overseas-media report explicitly admitted to the overseas audit universe; the pipeline then recalculates only the `境外新闻` channel and dependent totals while preserving every other raw channel.

## Main Entry

The user-facing invocation is simply: meeting agenda/date + organized system workbook or raw export bundle.

For a complete report, use the durable pipeline entry `scripts/run_cwh_resumable_pipeline.py`. It is the only component allowed to decide stage order, retries, resume behavior and formal completion. Do not ask one model invocation to improvise the entire raw-data-to-Word sequence. Read `references/resumable_pipeline.md` before running, adapting or deploying the full workflow.

The pipeline keeps deterministic scripts and AI work separate. It checkpoints each accepted artifact, records hashes and logs, and resumes from the first incomplete stage. `waiting_login` is a resumable adapter condition, never a successful or terminal workflow result: record the blocked adapter, continue every approved no-login/system fallback, and stop the full workflow only when the validator proves that all in-scope fallbacks are exhausted or user action is genuinely required. `waiting_ai` and `waiting_review` likewise do not imply completion. An AI statement that work is complete never advances the pipeline; only the stage validator can do so. Use direct stage scripts below for diagnosis and isolated module tests, not as an alternative informal orchestration path.

For public-platform article discovery, run `scripts/run_cwh_public_platform_research.py` from the research plan. WeChat uses the enhanced `wechat-search-weread` visible-browser adapter and must resolve every retained result to an `mp.weixin.qq.com` original page before formal use. Baijiahao uses a visible Baidu browser, saves captcha/login checkpoints, and resumes with the same browser profile after human verification. Never solve or bypass a captcha automatically. A waiting WeChat or Baijiahao adapter must not prevent Toutiao, open-web, monitoring-corpus or other approved routes from continuing.

Use `scripts/audit_baseline_platform_coverage.py` for platform-coverage calibration. Report baseline attributed-sample counts by platform, current topic-platform route coverage, concrete failure reasons and baseline candidate recall. Route coverage and candidate recall are separate metrics; an article hit never proves that every topic-platform query ran, and a completed query does not prove that a benchmark sample was recalled.

For a raw bundle, generate the standard workbook first:

```powershell
python cwh-report-skill/scripts/raw_system_workbook_pipeline.py `
  --input-dir "D:\path\原始数据" `
  --metadata outputs/cwh_raw_workbook/run_metadata.json `
  --output outputs/cwh_raw_workbook/CWH舆情情况_自动生成.xlsx `
  --audit outputs/cwh_raw_workbook/comparison_audit.md `
  --baseline "D:\path\人工基准表.xlsx"
```

The first run always writes `run/overseas_review_packet.json` and `run/hotword_review_packet.json`. It must stop before workbook generation when the hotword review is absent. Use the active model to review every hotword candidate, remove fragments and generic language, merge synonyms, check topic coverage, and supplement missing terms from the packet's traceable document excerpts. Produce a complete hotword review JSON with `review_method=ai_semantic_review` and `second_pass_completed=true`. Also complete the overseas review before formal delivery. Rerun with:

```powershell
python cwh-report-skill/scripts/raw_system_workbook_pipeline.py `
  --input-dir "D:\path\原始数据" `
  --metadata outputs/cwh_raw_workbook/run_metadata.json `
  --hotword-review outputs/cwh_raw_workbook/run/hotword_ai_review.json `
  --overseas-review outputs/cwh_raw_workbook/run/overseas_ai_review.json `
  --output outputs/cwh_raw_workbook/CWH舆情情况_自动生成.xlsx `
  --audit outputs/cwh_raw_workbook/comparison_audit.md
```

The hotword review must contain 36-42 evidence-backed terms by default, normally 5-8 per topic. Every item needs topic hits, an evidence tier, a semantic type, `standalone_topic_label=true`, a selection reason and AI representativeness. A term must make sense by itself as an agenda topic, policy goal/tool, governance mechanism, infrastructure/sector or public concern. Reject meeting procedure words and unqualified carrier nouns such as `召开`、`投资`、`项目`、`工程`、`市场`; retain a carrier noun only inside a field-qualified phrase that independently identifies the current agenda. Reject standalone locations, project sites, people, organizations, outlets and dates; a geographic word may remain only inside a complete policy, governance or sector concept. Core terms need two documents; supporting terms need one traceable high-quality document. If AI condenses a longer source phrase, preserve the verbatim wording in `evidence_aliases` and validate evidence against that wording. If too few clean candidates survive, the active model must propose additional terms from packet evidence; the program must never fill the gap with deterministic n-grams. An absent, incomplete or invalid hotword review blocks word-cloud and workbook generation. Keep the review prompt schema-based and meeting-agnostic: never seed it with accepted terms copied from a previous report, a fixed agenda count or period-specific examples.

The overseas review must cover every raw overseas candidate, classify each included row as `overseas_origin_media` or `mainland_outward_media`, assign all applicable subtopics, enforce the monitoring window, and keep a reason and confidence value. The pipeline counts both eligible publisher classes in the overseas total, writes only `overseas_origin_media` to the formal appendix, deduplicates canonical URLs and same-publisher repeats across system and supplemental reports, retains cross-publisher转载, and automatically recalculates overall daily totals plus each subtopic's overseas count. If the review is absent or incomplete, keep raw counts, write `ai_review_required`, and block formal delivery rather than letting deterministic keyword rules masquerade as AI review.

`--baseline` is optional and is read only after generation for acceptance comparison. Never read baseline result values while generating the workbook. If the request ends at workbook processing, deliver the generated workbook, review audit and comparison audit at this point.

Run the independent sentiment entrance gate against any supplied detail exports. It scans a directory safely but admits only row-level comments; article bodies beside a numeric comment-count field are rejected:

```powershell
python cwh-report-skill/scripts/run_cwh_sentiment_stage.py `
  --system-workbook "D:\path\CWH舆情情况.xlsx" `
  --input-dir "D:\path\系统导出" `
  --output-dir outputs/cwh_sentiment_stage `
  --run-preparation
```

If the status is `missing_comment_detail`, keep all formal sentiment ratio cells blank. When domestic public collection is authorized, run the MediaSpider Supervisor stage instead of fabricating or defaulting sentiment. If the status is `prepared_for_seed_review`, continue the active-learning workflow in `references/sentiment_pipeline.md`; do not treat the prepared seed batch as final labels.

Create and validate domestic comment tasks first. This project's default profile uses Weibo and Bilibili for a small trial, supports `wb,dy,ks,bili,zhihu`, and rejects `xhs`, `tieba`, plus every foreign platform:

```powershell
python cwh-report-skill/scripts/run_cwh_domestic_comment_collection.py `
  --research-plan outputs/cwh_system_report/research_plan.json `
  --system-workbook "D:\path\CWH舆情情况.xlsx" `
  --output-dir outputs/cwh_domestic_comments `
  --platforms "wb,bili" `
  --profile trial `
  --limit 2
```

The default invocation is a Supervisor dry-run. Add `--run --run-preparation` only after the generated commands, limits, visible-browser login state and output paths have been checked. The collection stage writes `境内公开评论明细.csv`, `境内评论排除明细.csv`, the task manifest, raw-run references and a JSON audit. Stop on login, captcha or account-risk signals; do not bypass platform controls.

If MediaSpider is blocked, use Agent Reach/Exa to discover relevant domestic public articles, manually verify each article-to-topic mapping in a seed JSON, then collect only publicly exposed, no-login comments. The current audited adapter supports 今日头条. Keep the raw API responses and time-window exclusions:

```powershell
python cwh-report-skill/scripts/run_cwh_agent_reach_comment_collection.py `
  --seed-file outputs/cwh_agent_reach_comments/seed_articles.json `
  --output-dir outputs/cwh_agent_reach_comments `
  --start-date 2026-07-10 `
  --end-date 2026-07-13
```

Pass `境内公开评论明细_AgentReach.csv` into `run_cwh_sentiment_stage.py`. Do not automate around authentication, captcha or platform controls, and do not treat Agent Reach search-result text as a public comment.

After reviewed row-level results are returned, rerun the sentiment stage with `--sentiment-results`. It must produce both `sentiment_workbook_summary.json` for the Excel denominator gate and `report_comment_handoff.csv` for report evidence. Use `scripts/backfill_cwh_sentiment_workbook.ps1` to copy the already accepted standard workbook and change only `子事件数据汇总!G:I`; never rerun the raw-workbook builder merely to add sentiment, because doing so can replace already accepted chart layout and styling.

Comment collection, sentiment, Excel, dashboard and prose are one required full-report chain, not optional one-off additions. When system comment detail is absent, collect approved domestic-platform comments, complete reviewed sentiment, and invoke the report stage with `--comment-handoff report_comment_handoff.csv --sentiment-results reviewed.csv --sentiment-summary sentiment_workbook_summary.json`. The dashboard displays every qualified traceable comment under its system subtopic. The formal report uses representative quotations from the same rows. The per-topic denominator gate controls only formal percentages and population-level sentiment wording; it must never hide valid comments from the dashboard. Regenerate `report_data.json`, Word and HTML after every new reviewed comment batch so all artifacts remain synchronized.

For the report stage, use the organized input workbook or the workbook produced above. First build the per-topic research plan:

First build the per-topic research plan:

```powershell
python cwh-report-skill/scripts/build_research_plan.py `
  "D:\path\CWH舆情情况.xlsx" `
  --agenda "7月10日国务院常务会" `
  --output outputs/cwh_system_report/research_plan.json
```

Then use agent-reach and available public-web/social backends to research every topic and write `analysis_bundle.json` following `references/analysis_bundle_schema.md`. This is an internal file, not a user input. Preserve an immutable full-page text snapshot and hash for every eligible article, then map each formal claim to one speaker and one continuous source-text span with exact offsets. The authoring pass must not certify its own claims: the pipeline runs a separate `domestic_evidence_verification` model task with a different run id, freezes the draft hash, checks every proposition, and produces `analysis_bundle_verified.json`. Run `scripts/domestic_evidence_mapping.py` again against the finished report directory; missing, altered, partially supported, self-certified or final-output-lost mappings block delivery.

When MediaSpider Supervisor is available, run the foreign evidence branch from the same plan. The default command validates task generation; add `--run` for real collection:

```powershell
python cwh-report-skill/scripts/run_foreign_mediaspider.py `
  outputs/cwh_system_report/research_plan.json `
  --output-dir outputs/cwh_system_report/foreign_collection `
  --run
```

The branch produces `foreign_mediaspider_samples.json`. The CWH ingester separates overseas media from overseas public discussion and keeps original URLs. Social discussion remains qualitative only. Eligible news rows must be copied into the raw-stage overseas review's `supplemental_rows` before final workbook generation; do not add them to totals later in the renderer.

Finally render the report:

```powershell
python cwh-report-skill/scripts/cwh_orchestrator.py `
  --input-file outputs/cwh_agenda.txt `
  --system-workbook "D:\path\CWH舆情情况.xlsx" `
  --analysis-bundle outputs/cwh_system_report/analysis_bundle.json `
  --hotword-audit "D:\path\run\hotword_audit.json" `
  --overseas-supplements outputs/cwh_system_report/public_overseas_supplements.json `
  --out-dir outputs/cwh_system_report
```

`--hotword-audit` is mandatory for a system-workbook report and must be the AI-complete audit produced with that workbook. The report stage rejects a missing audit, an incomplete second pass, unsupported terms or a term count below the configured minimum. `--overseas-supplements` accepts the reviewed `{media: [...], comments: [...]}` bundle produced by overseas public research. Always pass the existing bundle again when rerunning the report with a new domestic-comment or sentiment handoff. A later domestic evidence batch must not erase previously reviewed overseas media or public comments. This report-stage argument controls prose evidence only; any supplemental media row that should affect the overseas count must already have entered the standard workbook through the raw-stage AI review and reconciliation.

When a reviewed standalone word cloud is newer than the image embedded in the selected workbook, pass it explicitly without changing the other system charts:

```powershell
python cwh-report-skill/scripts/cwh_orchestrator.py `
  --input-file outputs/cwh_agenda.txt `
  --system-workbook "D:\path\CWH舆情情况.xlsx" `
  --wordcloud-image "D:\path\reviewed_cwh_wordcloud.png" `
  --hotword-audit "D:\path\hotword_audit.json" `
  --out-dir outputs/cwh_system_report
```

Treat an approved website-rendered word-cloud JPG/PNG only as a style benchmark. Never crop, recolor or insert that raster as the new report asset. Use `assets/wordcloud_cloud_shape.ai` as the authoritative vector silhouette and `assets/wordcloud_cloud_mask.png` as its rasterized runtime mask; do not replace it with a screenshot-derived approximation. Use the approved July 19 hierarchy renderer: target 42 unique, semantically reviewed hotwords, place every accepted term once as a primary word, then add small repeated copies only as background texture until the total reaches 289 placements. Never fill the primary layer with character fragments merely to reach 42; an audited 36-41 terms is preferable when evidence is thinner. Map primary words through the 22–150 font range with exponent `3.0`. Size repeats from the independent 28–96 reference range and twelve descending scales; cap their rendered size at 36 px so they never become secondary headwords. Use the fixed seed `20260710`, prefer edge-touching positions for early repeat attempts, rotate every word by `-15°`, render in `#0D4E6D` on a transparent background, and crop all transparent margins. Use the approved CWH font through the backend-only `CWH_CJK_FONT` path when it is lawfully available; otherwise use the bundled OFL-licensed Noto CJK fallback. Do not switch this formal path to the later 65-instance maximal-rectangle or integral-occupancy experiments.

The dashboard hotword module is an editorial review surface, not a second extraction algorithm. It lists one hotword per line with an optional `| weight` value, preserves the current topic and evidence metadata for unchanged terms, checks newly entered terms against the report's media/self-media/comment evidence, and always uses the configured approved CWH font, or the bundled OFL-licensed Noto CJK fallback, plus the approved formal cloud renderer. The input is read-only until the user clicks `修改`. `保存` performs regeneration and persistence as one action: it writes the reviewed terms and audit, regenerates the formal Markdown/Word/dashboard, and records a report version. Explain `weight` as a 1-100 font-size/display weight, never as an all-network heat score, propagation count or model confidence. A manually retained zero-match term must remain visible in the hotword audit as human-reviewed rather than being presented as automatically evidenced.

For an existing `report_data.json`, the same pair is available through `formalize_cwh_report.py --wordcloud-image --hotword-audit`; regenerate the dashboard afterward. The audit synchronizes ranked terms and weights used by prose/dashboard, while the PNG changes only the word-cloud asset and leaves the monitoring-system trend and subtopic charts untouched.

`--system-details` and `--sentiment-results` remain optional compatibility inputs when the department later provides raw detail exports. They are never required from the user in the normal two-input workflow.

Normalize the summary workbook independently when debugging:

```powershell
python cwh-report-skill/scripts/ingest_monitoring_workbook.py `
  "D:\path\CWH舆情情况.xlsx" `
  --output outputs/cwh_system_data.json
```

## Outputs

- Raw workbook stage: `CWH舆情情况_自动生成.xlsx`, `comparison_audit.md`, `run/overseas_review_packet.json`, `run/overseas_review_audit.json`, normalized run JSON and per-sheet previews.
- Raw workbook stage also produces `run/cwh_wordcloud.png` and `run/hotword_audit.json`. Build hotwords from deduplicated relevant public-article evidence, keep document/title/source/topic evidence for every selected term, and embed the exact PNG bytes into the standard workbook's `词云` sheet.
- `cwh_formal_report.docx`: formal mentor-facing Word report.
- `cwh_dashboard.html`: self-contained briefing dashboard with report-aligned editable prose, system charts, appendix tables, and one-click artifact entry points.
- `cwh_formal_report.md`: reviewable text version.
- `cwh_data_workbook.xlsx`: regenerated mentor-style data workbook.
- `report_data.json`: stable structured handoff object.
- `cwh_audit.json`: data-source validation, missing exports, and review checklist.
- `sentiment_analysis/sentiment_input.csv`: raw comment handoff when semantic labeling is needed.
- `charts/*`: overall trend, topic distribution, platform distribution, and hotword visuals.
- `appendices/*`: evidence tables.

## With deployment

The skill includes a deployable With application, not only a static dashboard demo.

After moving the workspace or changing Windows accounts, resolve the current Python runtime and report directory; do not reuse old absolute launcher paths. `scripts/launch_workbench.py` starts a hidden loopback-only process and checks both dashboard and archive availability. It never kills other processes or schedules desktop shutdown. Installed Skill, source, release ZIP, preview and published site are separate delivery surfaces: record and verify each, retain prior versions, and never call a built ZIP a completed online deployment. Rebase bundled artifact paths before dashboard rendering and retain the approved word-cloud PNG plus its audit. Preserve any verified cloud-only fixes when synchronizing source; substantive report/Word edits discovered during indexing must create a revision, whereas HTML-only refreshes must not.

Build the application bundle from a reviewed seed report:

```powershell
python cwh-report-skill/scripts/build_with_app_bundle.py `
  --seed-report outputs/cwh_current_report `
  --archive-report outputs/cwh_previous_report `
  --output-dir outputs/cwh_with_full_app
```

Repeat `--archive-report` for every reviewed historical period that should be visible immediately after deployment. The runtime copies these seeds into `/app/data/archive`, rebuilds their dashboards, and imports them idempotently into the configured archive database.

The archive contains the editable dashboard, native Python backend, portable raw-workbook builder, report renderer, Docker configuration and a current seed report. In With, deploy the bundled `.with/Dockerfile` and expose port `8000` behind the platform's Taihu authentication.

Archive synchronization must be idempotent across repeated scans, service restarts and restored directories. If a stale database row still owns a report directory while the same meeting already has an active canonical identity, retain the active identity, retire the stale directory owner without deleting its historical row, and rebind the live directory before indexing. When multiple filesystem directories contain the same meeting, select one candidate before database upsert: the dashboard currently being served wins; otherwise prefer a formally accepted directory with both Word and dashboard artifacts, then the newer complete candidate. Filesystem traversal order must never change the canonical directory or its artifacts. A local workbench is healthy only when both `cwh_dashboard.html` and the first-screen `/api/archive` endpoint return HTTP 200; a static page alone is only partial availability. The launcher must allow one bounded cold archive scan to finish instead of issuing repeated short-timeout requests against the same synchronization lock.

The With runtime must use `serve_dashboard.py --report-runner pipeline`. Do not switch a formal deployment back to `native` merely because a model worker is not configured: pipeline mode must finish deterministic nodes, persist the checkpoint and stop at `waiting_ai`. Configure an approved per-stage worker later through backend-only `CWH_PIPELINE_AI_COMMAND_JSON`; rerun the same task to continue without rebuilding accepted upstream artifacts or replacing the report database. The legacy `native` runner is retained only for compatibility and isolated diagnostics.

Pipeline mode supports:

- multiple raw monitoring exports or one standard summary workbook;
- raw-export normalization and downloadable standard workbook;
- deterministic workbook processing without the local Codex CLI, followed by gated AI stages and formal Word, Excel, JSON, audit and HTML rendering only after their contracts pass;
- editable report sections that rebuild the Word document on save;
- report history and direct HTTP artifact downloads;
- a searchable archive with separate report and data-workbook views;
- report-only database snapshots containing the self-contained HTML report and formal Word, with searchable metadata and report-only revision history; processing Excel, JSON, audit and crawler files remain outside the shared archive;
- revision history after report generation and section saves, with on-demand restoration after container restart or redeployment.

Local runs use SQLite by default. Shared With deployments must use a With-managed MySQL database through backend-only `CWH_MYSQL_*` environment variables or `CWH_DB_CONFIG`; install `PyMySQL` and set `CWH_DB_BACKEND=mysql`. Never expose database credentials in dashboard HTML, API responses, logs, or report artifacts. `/api/storage/status` may expose only backend type, schema version and non-sensitive record counts.

The portable workbook path uses `CWH_PORTABLE_XLSX=1`, openpyxl and embedded PNG charts so Linux does not depend on Excel COM, PowerShell or `@oai/artifact-tool`. Monitoring-system figures remain authoritative.

Do not claim that browser-login collectors or reviewed model sentiment are available merely because the app is deployed. The With bundle installs the Agent Reach CLI and `mcporter` inside the same application for zero-configuration public-web discovery; it is a separate dependency that MediaSpider's foreign fallback may call, not a MediaSpider built-in. Login-backed Agent Reach channels, authenticated MediaSpider collection and `large-scale-sentiment-analysis` still require their own sessions, credentials, model worker or reviewed result files. Without them, the app must retain source evidence from the monitoring export and attempt only permitted public-web supplementation. Hide the formal sentiment columns and population-level sentiment wording entirely until the current run has a reviewed result file, every displayed subtopic is marked `ready`, and every denominator is greater than zero. Never present historical labels carried by an older `report_data.json` as results of the current run.

## Workflow

1. Classify the input as an organized standard workbook or a raw multi-file bundle.
2. When raw, run the independent raw workbook stage once to create `overseas_review_packet.json` and `hotword_review_packet.json`. Use the active model to complete both review artifacts, including AI supplementation of missing clean hotwords from traceable packet evidence, then rerun with `--overseas-review` and `--hotword-review`. Never accept a metadata list or deterministic fallback as proof of AI review. Preserve an already organized standard workbook unchanged.
3. Parse the agenda and read the selected standard monitoring-system workbook.
4. Prefer workbook subevents, keywords, exclusion terms, event IDs, and monitoring dates over generated guesses.
5. Read total-event daily metrics and preserve the department's exact composite formula.
6. Read every subevent independently. Total-event rows are globally deduplicated; subevent totals may overlap and must not be summed into the overall total.
7. Build `research_plan.json` from every workbook subevent and the monitoring window.
8. Use agent-reach/public search to build the broadest practical accessible candidate pool of current media, expert and self-media interpretations for each subevent. Search the stable registry first but allow any relevant public-web source. Execute authoritative/mainstream, finance/industry/expert, university/think-tank and public-platform/self-media routes separately. Toutiao, WeChat and Baijiahao are mandatory platform routes. Run WeChat through WeRead platform search plus original-page verification and Baijiahao through the visible-browser adapter plus human captcha/login handoff; save the platform audit separately from general web search. The workbench's top-right “连接平台” panel exposes `百家号` and `微信读书（公众号）`: the local connector opens their real verification pages in the persistent local CWH collection profile, polls `waiting_login`, and records `connected` only after the slider or QR-login page clears. Site cookies remain domain-scoped. The CWH public-platform runner explicitly passes `%USERPROFILE%\.cwh\browser_profile` to both article adapters. Close the verification browser after the panel reports connected so the search adapter can reuse the profile. Never copy cookies or QR images into reports, logs or bundles. A generic web-search miss never proves that a platform has no relevant sample: save the platform-specific/site-restricted query before using `no_relevant_result`, otherwise record `access_failed` or `waiting_login` and its blocker. Expand every useful named expert, institution and account with a name-plus-topic query. Keep original URLs, full-page evidence and every inclusion, duplicate or exclusion decision. Never stop merely because two usable sources have been found.
9. After completing the title/body review of every overseas row already present in the raw Excel, always run a supplemental overseas-media search as a separate required pass. Use MediaSpider Supervisor `grounding` and/or Agent Reach public-web/news search, preserve queries, candidates, deduplication and blockers, and continue until consecutive search rounds add no material new high-relevance report. Separately collect overseas public discussion from currently permitted adapters such as X/YouTube; skip a platform explicitly paused by the user (currently Reddit) without attempting to open it, and record that scope limitation.
10. Search available social backends for public discussion. Quote only verbatim text with an original URL and comment identifier; otherwise write an unquoted viewpoint summary and record the source. Record comment coverage as a topic-by-platform matrix including the no-login Toutiao public-comment route and honest per-topic blockers for login-backed platforms. A global platform status or article hit is not comment-collection evidence.
11. Continue domestic open-search rounds until both open-web and public-platform routes are completed or honestly blocked and two consecutive rounds add no material high-relevance independent viewpoint. Persist every exact query, backend, route, execution time, result count, URL snapshot and retained candidate ID; a model-written zero count or generic round label is invalid. Only after this saturation audit, cluster the complete eligible pool. Every `eligible` independent sample must be assigned to an existing viewpoint cluster or create a new cluster, and must enter both the dashboard and formal prose; there is no two-item, four-item or other per-cluster output cap. Exact mirrors and substantive reposts stay `duplicate` audit records and never enter prose, visible cards or independent-voice counts. Write the internal `analysis_bundle.json`, preserve every candidate decision and immutable article-text snapshot, and record `candidate_id`, unique `evidence_id`, single speaker, article title, continuous source excerpt with offsets, decomposed semantic review, cluster mapping and decision reason on each formal evidence row. A substantive topic normally has 2-4 mature clusters; single-cluster or thin-cluster exceptions require actual search evidence. Run the evidence-density, eligible-to-formal completeness and domestic-evidence mapping audits, and continue research for thin clusters and one-item comment groups when public evidence is available.
12. Export all usable netizen comments to the sentiment handoff, run `large-scale-sentiment-analysis`, and feed results back by `sample_id`. Preserve system labels only as `system_sentiment_reference` for comparison.
13. Extract and reuse the workbook's existing overall-trend chart, subevent-volume chart, and word-cloud picture. Treat these as system-authoritative visual assets; redraw only the individual asset that is genuinely absent.
14. Generate hotwords, appendices, mentor-style Excel, Markdown, Word, self-contained HTML dashboard, and audit output. For hotwords, first let AI read each subtopic's traceable domestic media/self-media evidence and verified original netizen comments, propose 5-8 concise policy or concern phrases, merge synonyms, and remove fragments, generic verbs, outlet names, people and dates. Match the accepted human-report abstraction level: each phrase must independently identify an agenda topic, policy goal/tool, governance mechanism, infrastructure/sector or public concern; reject meeting actions and unqualified carriers such as `召开`、`投资`、`项目`. Require `semantic_type` and `standalone_topic_label=true`. Use two evidence tiers: a core term needs at least two independent evidence rows; a supporting term may use one high-quality traceable row only after AI verifies that it represents a substantive concern rather than a wording fragment, and it must receive a lower display weight. A core agenda anchor may also remain with one row. Allow a concise AI display label to use verified longer source wording through `evidence_aliases`; never confuse semantic compression with unsupported invention. Target 36-42 primary terms across all subtopics, normally 5-8 per topic, but never invent or retain broken n-grams to hit the target. Score only a display weight: 30% independent-sample coverage, 20% title/lead prominence, 15% source diversity, 15% AI semantic representativeness, 10% verified-comment mentions and 10% subtopic balance. If no comments are available, redistribute that 10% proportionally. Run a second AI audit for missing topics, unsupported terms, synonym duplication, official-copy dominance and noisy snippets. Keep every component, evidence tier, representative links and the selection reason. A workbook or model-proposed term absent from the evidence corpus must never enter the formal report, and the display weight must never be described as precise all-network heat.
15. Validate that every number comes from the workbook and every qualitative claim comes from a traceable system or public evidence row. The Word artifact audit must also confirm three required tables, three embedded images, appendix hyperlinks, and byte-level reuse of the workbook's trend chart, subtopic chart and word-cloud picture. The dashboard must render the overview plus the report's four fixed work areas, embed the system visual assets, and expose working Word, Excel, structured-data, and audit entries.

## Qualitative Writing Rules

- Domestic media/self-media claims use the actual speaking subject. When an article quotes a verified person, preserve the person's full institution, title and name; detect names from both the evidence summary and the full viewpoint paragraph, including forms such as `某某认为/指出` and `某某从……解读`. When a publication itself analyzes or recommends, write `某媒体认为/称/建议`; a media or institution voice is complete attribution and does not require an expert-name warning. Only a genuinely anonymous expert/industry-person claim should use `某媒体援引业内人士观点称` and show `未识别到具体专家姓名，建议核验原文`. Never invent a person or turn a media judgment into `某媒体受访专家指出`.
- Formal body prose contains concrete attributed claims only. Never append `样本来源：……`、`公开网络补证`、`原始报道汇总` or a standalone link list. Never substitute `报道汇集某某等对……的分析`、`多家媒体关注……` or similar aggregation for `完整机构/职务/姓名+具体观点`; when no named person exists, use the exact media/platform/self-media account name plus its concrete viewpoint.
- Within one system subtopic, the same named person or media/self-media source should normally appear in only one cluster. Merge its related statements into one fuller passage and use independent voices for the remaining clusters. Limited cross-subtopic reuse is allowed only for a separate, directly relevant argument; do not let one familiar expert dominate multiple subtopics.
- Preserve the source passage as the wording anchor. Lightly remove repetition and connect clauses, but retain its key nouns, verbs, scope, qualifications, examples and policy mechanism. Review each speaking subject separately even when one article quotes several people; never let a combined multi-person evidence row hide one short proposition. Each attributed proposition should normally contain 45-120 Chinese characters of substantive meaning. Fewer than 30 Chinese characters fails the formal gate: expand from the same source excerpt, combine related wording from that source or omit the voice; never pad with generic policy language. Treat `分析` or `解读` as an attribution verb only in an actual verb phrase such as `分析认为/分析指出/分析称`; noun phrases such as `宏观分析人士` and `政策解读文章` must not satisfy the gate.
- A mature viewpoint cluster normally starts at two independent voices but has no upper cap: include every eligible independent sample mapped to it. Write each voice as a complete attributed claim, normally 45-120 Chinese characters, so cluster length scales with the number of verified samples instead of being forced into a 120-300-character ceiling. A substantive topic normally has 2-4 mature clusters. One-cluster and thin-cluster results require structured exceptions backed by the saved query evidence; if the eligible pool already contains multiple viewpoint families, a one-cluster exception is invalid. If a justified subtopic has only one mature cluster, write the numbered heading and evidence paragraph directly; never output a lone `一是` without `二是`.
- Deduplicate by speaking subject plus substantive claim, not merely by URL. If several publishers, mirrors or reposts reproduce the same person's materially identical statement, render the claim once; retain the other URLs only as `decision=duplicate` research-audit records. Duplicate pages never increase the independent-sample count.
- Apply two separate AI reviews to every overseas report before formal rendering, starting with the full title and body already present in the raw monitoring Excel. First decide `meeting_relevance`: the article must substantively report or interpret the meeting, not merely discuss a broadly related agenda topic. Only then assign `事实性报道`, `解读性报道`, or `借题炒作/风险解读` from the article body. Public-web supplementation is used only when the Excel body is missing/inadequate or additional evidence is genuinely needed; it is not a prerequisite for finding interpretation. Store `meeting_relevance`, `formal_include`, `ai_report_category`, `classification_reason`, `classification_confidence`, reviewed Simplified Chinese title/source/summary and `interpretive_verified` in the structured row and in the standard workbook. Never silently default a row with missing classification to factual.
- In formal prose, do not number overseas report categories. Start with `数据周期内，境外媒体以事实性报道为主。如……等`. If eligible interpretation exists, end that paragraph with `，少量解读如下：` and write a new short paragraph summarizing up to three reviewed analytical reports. If none exists, end with `，暂无评论性文章。`.
- Keep original-language overseas text and its Chinese translation in structured data. The dashboard report list displays only the reviewed Chinese title and original-page link for every row; it must not show inconsistent small-print summaries, original titles or raw article bodies. Formal Word/Markdown prose and the overseas appendix use verified Chinese titles and Chinese summaries only. Every non-Chinese formal row must carry `title_cn` and `summary_cn`; rows without them stay in evidence data and do not enter the formal appendix.
- Synthesize overseas netizen comments by viewpoint theme in Chinese; do not mechanically list comments or account IDs in formal prose. Each `一是、二是……` theme occupies its own paragraph and may quote one or two representative Chinese translations, attributed only to the platform. Exclude explicit calls to overthrow the Party or government and direct anti-Party/anti-government abuse. Do not use that filter to remove ordinary criticism of policy execution, disaster response, infrastructure, transparency or public communication. System and supplemental provenance/window labels remain in structured data and the dashboard, not in formal-report wording.
- Run a dedicated AI semantic review over domestic and overseas comment candidates before formal writing. Store `ai_formal_include`, `ai_semantic_quality`, `ai_formal_reason`, `comment_heading` and, for overseas themes, `comment_summary`. For domestic comments, one system agenda/subtopic is exactly one numbered `一是/二是` item; use one shared `topic_comment_heading` to synthesize the 2-3 selected comments, and never split reactions to the same agenda into several numbered items. Exclude reaction-only or low-information wording such as `好的`、`挺好`、`感谢分享` and pure emoji, even when traceable. Comment headings must express the actual stance or expectation and vary with the evidence; do not generate every heading as `关注+议题名称`. Scripts enforce the reviewed fields and guard empty reactions but do not replace the AI judgment.
- Domestic comment collection must search every authoritative workbook topic across every currently permitted platform adapter before selection. It has no target quote count and cannot stop because one topic already yielded enough material. Preserve a topic-by-platform matrix with execution mode, query or reviewed seed URL, result count, eligible comment IDs, candidates and blockers; a global platform status or article hit cannot prove comment coverage. Only topics with traceable substantive original comments enter formal numbered groups.
- Treat domestic viewpoint titles as stance conclusions, not topic labels or bare analytical noun phrases. They must begin with an evidence-supported verb such as `建议、认可、肯定、认为、期待、希望、支持、呼吁、质疑、担忧`; a fact-only topic may instead state `监测期内尚未形成评论性观点`. Missing or generic titles block formal rendering.
- Do not write the zero-sample conclusion merely because the workbook contains no social rows. Formal system mode requires a completed non-dry-run foreign public-discussion collection audit (or already reviewed traceable overseas comments). When that audit genuinely yields zero eligible comments, use the exact sentence `境外网民对本次国务院常务会议关注度较低，暂无评论性观点。` Overseas-media review and overseas-comment collection are separate gates.
- In media/self-media prose, preserve a person's verified institution and title before the name. A clearly attributed media or institutional analysis needs no expert-name marker. Add `【未识别到具体专家姓名，建议核验原文】` only beside the exact anonymous-expert claim that still depends on an unverified person; a named expert elsewhere in the cluster does not resolve that separate anonymous claim.
- In the overseas-media section, never render category numbering. Follow the factual lead plus optional `少量解读如下：` paragraph described above. Formal Word/Markdown prose and appendix cells display only reviewed Simplified Chinese outlet names, titles and summaries. Keep original-language and Traditional Chinese fields only in structured evidence and the dashboard.
- The formal overseas appendix is a representative TOP10 after meeting-relevance review, report-category review, complete Simplified Chinese normalization and story deduplication. Fewer than ten rows is valid only when the complete reviewed, normalized and deduplicated formal set truly contains fewer than ten; missing translation fields or weak character checks must never silently reduce the list.
- In the WeChat TOP10 appendix, normalize account names first, then apply only explicit reviewed aliases in `public_publisher_families`, and keep the highest-read relevant article from each publisher family before ranking. Never use fuzzy similarity to merge unrelated accounts; independent programme accounts remain separate unless explicitly configured. Determine relevance from the full title/body and current agenda semantics. A concise headline that omits `国常会` is eligible only when its body explicitly identifies this meeting and substantively covers a current agenda; account authority and topic overlap alone never prove relevance. Record lower-read same-family rows as `duplicate_source_lower_read_count` in the raw-workbook audit.
- Treat public-article ranking and viewpoint evidence as two independent products of the same raw detail corpus. `公众TOP` is a distinct-publisher ranking for the appendix; it must never cap, filter or define the domestic media/self-media candidate universe. Build `public_article_evidence.json` from every agenda-relevant raw public-article row before TOP selection, preserve the full body, URL, publisher, publication time and topic hits, and record every exact-duplicate or exclusion reason.
- Keep domestic discovery as three auditable pools: the raw monitoring full-text pool, fixed-registry web discovery, and open-web/public-platform discovery. A registry `hit` must point to a candidate actually discovered by that web or platform execution; a raw monitoring record can corroborate or deduplicate it but can never prove that the web search ran. Preserve failed backends as `access_failed`, preserve the successful fallback execution separately, and give every saved result URL an eligible/duplicate/excluded candidate decision.
- Spreadsheet metadata is not row evidence. In read-only mode, an export may advertise a stale `A1` used range even when thousands of rows exist. Reset/recalculate worksheet dimensions or verify the underlying XML before declaring a raw sheet empty; record the advertised and recalculated dimensions in the audit.
- One article may contain several independently attributable voices. Review the whole body and extract each named expert, institution or media voice separately with its own excerpt and claim. When a structured row lists several named speakers together, the dashboard must split it into one complete viewpoint card per speaker, repeat the same original-page link where necessary, and count the cards by independent speaking subject rather than by URL. Never stop at the first speaker or collapse several speakers into an anonymous article summary.
- Every public-web candidate eligible for period prose must preserve a source-page publication timestamp, the exact source text used to verify it, and `published_at_verified_from_source=true`. Reject candidates outside the monitoring window from period prose and statistics; later material may remain only as explicitly labelled post-window evidence.

## Monitoring Workbook Contract

Read `references/system_data_contract.md` when ingesting a new system export or adapting field names.

The mentor workbook pattern contains:

- `关键词`: total event and subevents, query expressions, exclusions, event IDs.
- `总事件`: daily overall/channel metrics and total spread.
- `子事件1...N`: independent daily metrics per subevent.
- `子事件数据汇总`: subevent domestic/new-media/overseas totals and sentiment ratios.
- `外媒报道列表`: source, date, title, URL, and multi-subevent hit flags.
- `词云`: system/analyst hotword candidates.
- `公众TOP`: WeChat account, title, read count, 在看 count, and URL.

Do not recompute system totals from ordinary detail-row counts. The only permitted detail-to-aggregate reconciliation is the complete audited overseas-media universe produced before standard-workbook finalization; it may replace only `境外新闻` and dependent totals, never another channel.

## Sentiment Rules

There is one formal path: run the installed `large-scale-sentiment-analysis` workflow on usable comment rows following `references/sentiment_pipeline.md`, then回灌 by `sample_id`. System-provided labels and aggregate ratios are preserved only as reference fields and never used in the report denominator.

Use `scripts/run_cwh_sentiment_stage.py` as the independent entry and schema gate. It always writes a header-bearing `sentiment_input.csv`, a label schema, and JSON/Markdown audits. With `--run-preparation`, it invokes the installed large-scale sentiment cleaning, quality-profile and stratified seed-batch scripts only when row-level comment text exists.

Never default unlabeled comments to neutral. Never mix media articles or policy text into the netizen sentiment denominator.

## Formal Acceptance

Formal delivery requires:

- a valid system summary workbook;
- nonzero total-event daily/total metrics;
- all subevent totals and monitoring dates;
- usable, traceable media/self-media public evidence for viewpoint claims;
- real platform comment/reply rows for the netizen-comment section. A quoted row must preserve the comment wording, platform, source page URL, timestamp when available, and a comment/reply identifier or raw comment-file provenance. Public posts, video titles and `public_discussion_summary` rows are evidence leads only and must never appear as netizen comments, quoted or paraphrased;
- completed audited sentiment processing from the installed sentiment skill;
- overseas and WeChat TOP detail when those modules appear in the report;
- complete Word/Excel generation and audit consistency.
- complete self-contained dashboard generation with no external web dependency.
- domestic media/self-media prose that passes source-diversity, attribution-form and minimum-claim-density checks. Repeated use of the same voice in multiple clusters of one subtopic, invented anonymous-interview attribution, or a substantive attributed claim below 30 Chinese characters blocks formal delivery until revised from the source evidence.
- a density audit that compares section characters, mature clusters, independent voices and traceable comment-group coverage with the reviewed benchmark. Page count is diagnostic only: never manipulate font, margins, spacing or unverifiable quotations to reach a historical page total. A shorter comment section caused by exhausted traceable collection remains an explicit audit limitation.

Missing qualitative evidence produces internal actions such as `research_public_media_evidence` and `research_public_comment_evidence`. The skill should continue researching with available backends instead of asking the user for another file. It must not produce `continue_mediaspider_bulk_collection` in system mode.

## Formal Report Template

Follow `references/formal_report_rules.md` and use:

`templates/formal_report_template_complete_20260714.docx`

Fixed top-level structure:

1. `一、舆情传播情况`
2. `二、境内舆论情况`
3. `三、境外舆论情况`
4. `附录`

Chapter three has exactly two second-level sections: `（一）境外媒体情况` and `（二）境外网民评论`. Never place overseas-media prose directly under the chapter heading without the first second-level heading.

Keep the template's reusable sentence frames, fonts, margins, page number, table style, and heading hierarchy. Do not expose placeholders or QA status in the final report body.

## Data Workbook Rules

Always generate `cwh_data_workbook.xlsx` from the normalized system data.

- Preserve system keywords, exclusions, and event IDs.
- Preserve the system monitoring window and every daily value.
- Preserve the department's composite传播量 formula.
- Preserve overlapping subevent totals without forcing them to add up to the overall total.
- Do not use system sentiment percentages in the formal table. Use only audited comment-level sentiment results. Until the denominator is valid, omit sentiment columns and population-level sentiment wording instead of showing stale ratios or `待分析` placeholders.
- Preserve external URLs and multi-topic hit flags.
- Preserve WeChat reads/在看 values exactly, including values such as `100000+` when available.
- For `公众TOP`, AI must read and decide every candidate at the maximum-read cutoff before the TOP10 selection; expand the reviewed batch if needed. Exclude roundups and articles where the meeting is only a minor catalyst, keep only the highest-read eligible article from each normalized public-account/source, then rank distinct-source representatives by read count and use `在看`/recommend count as the deterministic tie-break when reads share a system cap such as `100000+`. Never take ten articles first and deduplicate afterward; fewer than ten rows is valid only when fewer than ten eligible distinct sources remain. Preserve every inclusion/exclusion reason so a baseline discrepancy can be explained instead of copied blindly.
- Generate the full `public_article_evidence` corpus before `公众TOP`. TOP ranking may consume that corpus, but report research must receive the complete eligible corpus independently and must document an include/duplicate/exclude decision for every row it reviews.

## HTML Dashboard Rules

Always generate `cwh_dashboard.html` from the same `report_data.json` used by Word and Excel.

- Package `assets/cwh_dashboard_template.html` and `scripts/generate_dashboard.py` inside the skill. Do not hard-code any meeting-specific topic, figure, total, quote, or artifact path in the template.
- Use five switchable work areas rather than one long page: `总览`、`一、舆情传播情况`、`二、境内舆论情况`、`三、境外舆论情况`、`四、附录与报告生成`.
- In each formal-report work area, show the corresponding system data, charts, appendix rows, viewpoint evidence, comments, or hotwords first, then put the exact generated prose in a Word-like editable page. The page is read-only until `修改`; `保存` writes section blocks back to `report_data.json` and rebuilds the formal Word; `撤销` supports multi-step history. Preserve native `Ctrl+C/V/Z` and add `Ctrl+S` for save.
- Keep the six subtopics authoritative to the monitoring-system workbook. AI-generated viewpoint clusters are subordinate writing arguments inside those subtopics; label them `成文分论点`, never present their count as additional topics or a delivery KPI.
- Show the workbook's trend chart, subtopic chart, word cloud, subtopic statistics, overseas appendix, and WeChat TOP rows under the corresponding report part. Do not show a separately drawn platform-distribution chart unless that chart itself exists in the reference workbook or formal report.
- The reviewed word cloud is a required persistent artifact, not an optional decoration. Every regeneration, section save, directory copy, archive restore and deployment rebuild must preserve the same reviewed word-cloud PNG in Word, the self-contained HTML and the workbench hotword module. Resolve image candidates by existence and nonzero size rather than by the first nonempty path string: a stale absolute path must be recorded and skipped while the local reviewed pipeline image, audited image or workbook-extracted image is still tried. Before delivery, assert that all three surfaces contain a visible, nonzero-dimension word cloud and that Word/HTML reuse the selected PNG bytes; never silently replace an available reviewed cloud with the generic fallback renderer.
- Part one should expose only support that directly explains the prose: the workbook trend chart, subtopic chart and subtopic statistics. Do not repeat a decorative channel KPI strip when the same counts already appear in the prose and system data.
- Part two has separate `媒体/自媒体观点`, `网民评论` and `热词分布` modules, and the first two use the same authoritative subtopic tabs. Retain every `eligible` domestic media/self-media candidate from the saturated registry-plus-open-web pool in the dashboard without a hard row cap, and write the same complete eligible independent set into formal prose. An eligible candidate may not remain dashboard-only. Excluded and duplicate decisions stay in research audit; duplicate original/repost/mirror pages are not visible samples. Every real comment and every independent media/self-media claim must expose an obvious original-link action when a URL exists. Put each module's exact formal prose directly below its evidence, not in one detached chapter-level editor.
- Every visible public-web media row must be an independent attributed claim and carry the full corresponding viewpoint sentence in addition to source, title and original URL. Do not render duplicate pages as bare links or repeated claim cards.
- The domestic media/self-media module must exclude every row marked `region=overseas/foreign/境外`, every `overseas*` source type, and every monitoring-system overseas record even when its generic source type is only `media`. Label evidence provenance explicitly as `监测系统 Excel` or `公开网络补证`; never present supplemental web evidence as if it came from the monitoring workbook.
- Formal prose in HTML and Word must use the same emphasis rules: numbered viewpoint headings such as `1.建议……` are bold in full, while the lead sentence beginning `一是/二是/三是……` is bold through its first sentence-ending punctuation. Embedded HTML tables must mirror the corresponding Word table's header rows, column structure, borders and distinctive fills.
- Formal Word generation must never add paragraph-level pagination controls that appear as black square formatting marks in the page margin. Do not set `keep_with_next`, `keep_together` or `page_break_before` on generated paragraphs, table cells or report styles. Keep a final defensive cleanup only for marks inherited from an external or legacy template, while preserving the approved fonts, sizes, spacing, indentation, borders and other base formatting. The DOCX audit must assert zero `w:keepNext`, `w:keepLines` and `w:pageBreakBefore` occurrences in both `word/document.xml` and `word/styles.xml`.
- The overview must distinguish monitoring-system totals, monitoring-system detail rows, public supplemental evidence and real platform comments. Never label their merged count as a system metric. Use a compact channel-distribution bar plus a complete subtopic statistics table so users can inspect the whole dataset at a glance; avoid verbose methodology prose and decorative KPI cards. List every system subtopic by name.
- Overseas reports and traceable overseas comments have no fixed display cap. Continue agent-reach/MediaSpider expansion until relevant original URLs are exhausted or results materially stop changing. Split overseas reports into `监测系统原有报道` and `公开网络补充报道`. Keep overseas-report full text, original-language titles and Chinese summaries in structured evidence, but render every report row uniformly as source, date and one clickable reviewed Chinese title; do not selectively expand summaries, original titles or raw article bodies under only some rows. Foreign-language comments must retain the original text, a Chinese translation, date, platform, comment identifier and direct URL.
- In the third dashboard work area, `（一）境外媒体情况` contains only overseas-media report data and its matching formal prose; `（二）境外网民评论` contains only overseas social comments and its matching formal prose. Keep the two editors independent and ordered exactly like the Word report.
- Use report-aligned internal tabs in every dashboard work area: chapter one switches between `（一）总事件传播情况` and `（二）子议题传播情况`; chapter two switches among its three fixed subsections; chapter three switches between its two fixed subsections; the appendix switches between its two fixed tables. Do not stack all subsections into one long page.
- Do not show engineering-step narration such as file recognition, event matching, aggregation or workbook validation after an import completes. The three commands `处理数据`, `打开总表`, and `生成报告` are sufficient; show a concise running state or error only when action is still required.
- Do not show evidence-pipeline counts such as system detail rows, public-web supplements or traceable-comment totals in the overview. They are audit quantities rather than report statistics and can be confused with monitoring-system propagation totals. Do not place a decorative progress line under the import commands.
- Keep reaction-only comments and emoji tokens visible in the dashboard evidence view, but remove platform reaction tokens such as `[赞]`, `[心]`, `[福]`, `[点亮平安灯]`, `[呲牙]` and Unicode emoji from formal Markdown/Word prose. If no substantive text remains after cleaning, exclude that comment from formal prose without deleting it from the evidence data.
- The shared history database stores reports only: the self-contained dashboard report and formal Word. Do not persist monitoring workbooks, normalized Excel, Markdown, JSON, audit files, crawler output or complete run directories in the report archive. Those files may still be generated and used in the current processing workspace. Keep report metadata searchable and keep report-only version history so colleagues can add and reopen reports after redeployment.
- Keep post-window findings visible as `监测期后补证`. They must never enter period statistics or period sentiment. When the in-window overseas-comment section would otherwise be empty, formal prose may include a clearly labelled post-window supplement after first stating that no in-window comments were obtained.
- In media/self-media topic panels, show one original link on each independent viewpoint card. Do not repeat it in a second `全部证据明细` block; same-claim reposts and mirrors remain research-audit records.
- Do not create a detached `相关原始报道与补充样本` section. A genuinely new attributed judgment becomes a normal viewpoint card. A page that adds no distinct speaking subject and claim remains audit-only and must not inflate the visible sample count.
- Preserve the full substantive attributed sentence from the mature cluster prose on each viewpoint card. Do not replace it with a shorter `formal_claim`, label-style summary or source excerpt merely to fit the card. The card may split a multi-voice cluster by speaker, but it must not reduce the speaker's qualifiers, reasoning chain or policy implications; substantive attributed claims remain at least 30 Chinese characters.
- Put the six channel totals used by `（一）总事件传播情况` directly above the trend chart in that work area: domestic mainstream media, WeChat public accounts, Weibo, Video Accounts, clients/forums, and overseas media.
- Store historical reports behind a searchable folder-style dialog so the sidebar remains stable as report volume grows.
- Do not add a standalone `数据与证据` navigation area. Evidence links may remain attached to the relevant writing arguments, while engineering audit details stay in `cwh_audit.json`.
- Embed charts and dashboard data into one HTML file so colleagues can open it offline and other agents can reproduce it without installing a frontend toolchain.
- For leadership demos outside the local workbench, build a sanitized read-only package with `scripts/build_readonly_dashboard_demo.py`. It must force demo mode, remove absolute local paths, disable editing/import/artifact actions, make no backend requests, and be published only through an approved authenticated platform such as With with Taihu identity access. Never expose the local workbench through a public tunnel.
- Prefer the monitoring workbook's extracted trend, subtopic, and hotword assets. Never redraw or relabel them as different system data.
- Provide a one-click Microsoft Word protocol link plus a normal file link; provide equivalent Excel access and direct links to structured data and audit output.
- Replace generic delivery-status furniture with a multi-file `数据导入` entry. Accept any number of exports, keep originals, and profile workbook/sheet/field structure. Route real raw bundles through the schema-driven `raw_system_workbook_pipeline.py`; keep its audit visible without coupling it to report rendering.
- Make the import entry a staged, deterministic handoff: `处理数据` first runs only the raw-workbook stage and shows real file matching, aggregation, sample filtering, chart generation and workbook verification states; enable `打开总表` only after the standard workbook and audit exist; start the AI report stage only when the user clicks `生成报告`. Never substitute simulated progress or start report research before the standard workbook is available.
- Add a `报告资料库` rail backed by the archive storage abstraction: SQLite at `CWH_ARCHIVE_DB` for local runs and With-managed MySQL for shared deployment. Store searchable report metadata, artifact metadata, a complete zipped report-directory snapshot and immutable revision snapshots. De-duplicate generated versions by meeting date for the default view, and expose independent `报告` and `数据表` tabs. Search date, title, monitoring period, agenda and subtopic text; keep Word/dashboard actions under reports and Excel/structured-data/audit actions under datasets. Re-index transactionally after seed import, report generation and section saves. Restore missing local files from the database on demand before serving or editing them; do not claim persistence if only filesystem paths are stored.
- Validate desktop and narrow-screen layouts, confirm no page-level horizontal overflow, and confirm every embedded image has nonzero natural dimensions.
- When the user asks to open, show, or copy the dashboard URL, run `scripts/serve_dashboard.py` in a hidden background process and return the printed `http://127.0.0.1:<port>/cwh_dashboard.html` address. Do not present a `file:///` URL as the browser entry point.
- After completing or testing a full formal-report workflow, start the local workbench server and include its `http://127.0.0.1:<port>/cwh_dashboard.html` address in the handoff unless the user explicitly asks not to launch it. Generating the HTML file without exposing the workbench address is an incomplete local handoff.

Serve an existing dashboard locally:

```powershell
python cwh-report-skill/scripts/serve_dashboard.py `
  outputs/cwh_system_report/cwh_dashboard.html `
  --library-root outputs `
  --enable-codex-runner `
  --workspace . `
  --no-open
```

The server binds to `127.0.0.1` only. If port `8766` is occupied, it selects the next available local port. The multi-file import entry always runs the deterministic raw-workbook stage locally. With `--enable-codex-runner`, the later `生成报告` action starts a non-interactive Codex run under the current signed-in account, polls its status, and links the generated dashboard and Word back into the workbench. This local demo needs no separate model API key. A future department-system deployment must replace the local CLI runner with the department's authenticated model/agent service and access control; do not expose this development server to a network.

## Optional Supplements

MediaSpider domestic collection and agent-reach remain available for研发验证、公开证据核验 or a specifically approved missing-evidence supplement. MediaSpider Supervisor also has a distinct foreign collector covering X, YouTube, Reddit, TikTok, Instagram, Bluesky, Threads, grounding and other sources. The CWH normal workflow may use that foreign branch for overseas evidence. News reports can affect the overseas count only through the pre-workbook AI review; social-platform rows never affect media counts.

```powershell
python cwh-report-skill/scripts/cwh_orchestrator.py `
  --input-file outputs/cwh_agenda.txt `
  --system-workbook "D:\path\CWH舆情情况.xlsx" `
  --hotword-audit "D:\path\run\hotword_audit.json" `
  --supplemental-collection `
  --run-mediaspider `
  --out-dir outputs/cwh_system_plus_supplement
```

Supplemental rows must be marked by source. Domestic evidence and social comments cannot alter authoritative system totals. Reviewed in-window overseas news is the narrow exception and must be reconciled in the raw workbook stage, never patched into totals during report rendering.

## References

- `references/raw_workbook_pipeline.md`: raw multi-file identification, metadata, standalone execution, acceptance and handoff contract.
- `references/system_data_contract.md`: system workbook/detail export schema and authority rules.
- `references/analysis_bundle_schema.md`: internal public-evidence and AI-analysis handoff schema.
- `references/formal_report_rules.md`: fixed report structure and writing rules.
- `references/sentiment_pipeline.md`: raw-comment semantic classification contract.
- `references/report_schema.md`: `report_data.json` handoff schema.
- `references/capability_matrix.md`: current implementation coverage.
