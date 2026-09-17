---
name: cwh-report-skill
description: Generate auditable State Council executive meeting (CWH/国务院常务会) public-opinion reports from standard or raw monitoring-system exports. Use for workbook normalization, evidence research and review, domestic comments and sentiment, overseas review, hotwords, and synchronized Word, Excel, JSON, audit, and HTML delivery.
---

# CWH Report Skill

## Outcome and inputs

Turn these two user inputs into a validated report package:

1. meeting date or agenda text;
2. either one organized standard workbook or a raw monitoring-export bundle.

Do not ask the user to prepare analysis JSON, comments, charts, or a third input file. Those are internal artifacts. Numerical传播口径 comes from the monitoring workbook. Qualitative claims come only from traceable reviewed evidence. Keep engineering status and missing-input details in audit files, never in formal prose.

## Default execution contract

In bounded profiles, deliver all available content even when a topic has no usable interpretation or comments. Controllers record real search/review coverage and explicit gaps, remove empty clusters, independently verify the claims that do exist, and continue Word/Excel/Markdown/HTML generation. Quantity/density targets must not withhold all outputs. `delivered_with_gaps` is a completed available-content delivery, not proof of absent discussion or certified full coverage. Source integrity, exact excerpts, numerical consistency and artifact existence remain enforced. Never fill gaps with fabricated voices, quotes or ratios.

The compiled bounded worker contains article-reading, grouping and independent-review interruptions locally. A timed-out or malformed article response remains unread; grouping failure preserves extracted claims in source order under a neutral topic label; unfinished independent reviews cannot enter prose. Record every interruption and all remaining coverage gaps. Allocate remaining author time fairly across topics, preserving the global delivery reserve. This is available-content recovery, not evidence that a provider completed every semantic task. Authentication, permissions, corrupted source identities and missing input cannot be relabelled as successful research; the outer runner still emits the separate labelled review package when formal delivery is unavailable.

Use the model-neutral `bounded_60m` profile in `config/execution_policy.v1.json` by default. Its wall-clock limit is 3600 seconds; research stops taking time after 3000 seconds, preserving delivery time. Time starts at the first `run` and includes worker waits and retries; `run` and `invalidate` do not reset it. An exhausted budget records `time_budget_exhausted`; use a new job directory for a new timed test. `bounded_40m` remains a tighter explicit option. Use `exhaustive` only when the user prefers uncapped research. Budgets are limits, not proof that a model has completed a report within them.

Before a full run, read [references/model_neutral_execution.md](references/model_neutral_execution.md) and [references/resumable_pipeline.md](references/resumable_pipeline.md). The machine-readable policy, generated task contract, and validators override narrative examples when they differ.

The controller resolves stage budgets from the input mode at intake. Standard input gives workbook validation 30 seconds, domestic authoring 1290 seconds and independent review 600 seconds. Raw input gives workbook semantic review 600 seconds, domestic authoring 1080 seconds and independent review 780 seconds. The report body takes priority over appendix completion; unfinished appendix records stay explicitly pending, not approved or excluded. Both modes preserve rendering and final checks within the same 3600-second limit; see `references/model_neutral_execution.md`. Never change a running job's clocks to apply a new policy.

In bounded delivery, the hotword count is a quality target, not a reason to withhold every artifact. Retain only genuinely supported terms after the required second pass, record configured versus actual counts, and continue with a shorter nonempty list. Never manufacture words to reach 36. An empty or unreviewed list remains a real missing-evidence state. The explicit 40-minute raw-input profile reserves up to 480 seconds for normalization; the global 2400-second clock is unchanged, and per-stage maxima cannot all be consumed at once.

The 60-minute profile carries forward unused predecessor allocations into the current node. It subtracts actual prior wall-clock time (including waits), never future-node budgets. New jobs use the 3600-second global limit and 3000-second research cutoff. Existing job contracts retain their original limits and clocks. Preparation uses at most one quarter of remaining author time; optional priority calls without 30 seconds are skipped in favor of existing discovery order, never counted as model review. Full reading, native claim writing and independent verification remain required for published claims.

Run the preflight before expensive model work:


```powershell
python scripts/cwh_preflight.py --skill-root .
```

Run complete work only through the durable pipeline:

```powershell
python scripts/run_cwh_resumable_pipeline.py run `
  --job-dir outputs/cwh_pipeline_job `
  --agenda "会议日期或完整议程" `
  --system-workbook "D:\path\CWH舆情情况.xlsx" `
  --execution-profile bounded_60m
```

For a raw bundle, replace `--system-workbook` with `--raw-input-dir` and provide required metadata according to [references/raw_workbook_pipeline.md](references/raw_workbook_pipeline.md). Direct stage scripts are for diagnosis and isolated tests, not an alternative orchestration path.

Establish each numbered raw child workbook's topic identity before semantic research. Use explicit export titles or a traceable monitoring-task/event-ID mapping; agenda order, filename order and similar quantities are not identity evidence. Keep the basis in internal period metadata, preserve combined statistical groups, and do not request another analysis file from the user. If identity is genuinely unavailable, ask only for the missing topic correspondence and retain the unresolved state; do not silently guess factual labels. A benchmark-assisted correction after review is separately labelled, not a blind test or a production fallback.

For an unattended model host, read [references/model_worker_host.md](references/model_worker_host.md). The host runs scripts; models should not need shell permission. A full-report request must not use `--until-stage` as its final invocation. Paused/workbook-only results are not report completion. Without an automatic worker, complete the current JSON task and resume; do not repeatedly resume unchanged outputs.

An incomplete full invocation generates `review_delivery/` separately from formal `report/`. Its Word and fixed-template workbench are labelled 待审核稿 and never pass the formal gate. Only hash-verified accepted workbook facts and independently verified viewpoints enter the review prose; missing evidence remains explicitly missing. This may be a partial/status-only draft, not a completed report. Diagnostic calls may use `--no-review-delivery`; this does not waive final delivery requirements.

## Model boundary

Each AI stage receives one `tasks/<stage>.json` generated by `scripts/cwh_model_contract.py`. The worker may write final artifacts only to `declared_outputs`, and intermediate seeds, raw responses and batches only under its `stage_workspace`. It must not:

- modify Skill code, configuration, validators, templates, pipeline state, event history, hashes, or finished report files;
- invent URLs, source pages, timestamps, people, quotations, comments, identifiers, or successful status;
- run downstream stages or weaken a gate;
- pad text to pass a length check.

Models decide only semantic relevance, candidate disposition, speaker identity, atomic claims, stance, cluster assignment, comment quality, sentiment, translation, and semantic support. Scripts own stage order, workbook calculations, query-plan generation, identifiers, deterministic prose assembly, validation, hashing, retries, rendering, and delivery status.

Missing evidence is a structured blocker. A model assertion that work is complete has no effect; only validators advance state. `waiting_ai`, `waiting_login`, and `waiting_review` are resumable conditions, not success. A failed stage is rearmed on the next explicit `run`; never hand-edit attempts or hashes.

### Single-worker, low-token operation

- Default to one active model worker and serial stages; do not spawn agents unless the user explicitly requests them. Independent second-pass review remains a separate sequential run with fresh context, not simultaneous agents or author self-certification.
- Read this entry and the execution contract once per run, then only the current task's required references and inputs. Reuse existing accepted artifacts and source snapshots; do not repeatedly dump all files, search the same URL or redraft complete report sections.
- Return the current stage's structured fields, not a narrative status essay. Use existing batching scripts; repair only reported invalid fields while preserving accepted source text and identifiers.
- In compiled large-topic authoring, article batches only read full sources and extract attributed claims with exact ranges. They do not draft provisional headings or groups. A separate native synthesis selects and groups existing claims, using explicit priority and scripted reserve bookkeeping in bounded mode. Extraction success does not replace synthesis or independent verification.
- For a large monitoring corpus, use the controller's per-topic reading indexes rather than repeatedly loading the whole JSON. Bounded mode targets at least `min(12, topic corpus size)` actual full-article reviews per topic; available-with-gaps delivery may fall short only with a complete hash-matching corpus index, the exact unread ID set and a reading-shortfall notice. Unread rows are never counted as reviewed. Exhaustive mode still requires all rows. Full source support and independent claim review are unchanged.
- New bounded plans freeze a time-aware initial reading allocation, starting at 12 monitoring articles plus four public pages per topic when time is tight and expanding toward configured ceilings when time permits. An optional native metadata-priority call selects which observed pages to read, never certifies their content. Failed optional ranking falls back to recorded discovery order; permission or quota failures remain real blockers. Limits do not truncate source text or waive independent verification.
- Large raw hotword packets in available-with-gaps delivery are reviewed in native batches of at most 40 candidates and a separate native global second pass. Preserve all original candidates, topic indices and per-term source windows. Native source-backed phrase additions remain allowed; the original full-source gate recalculates evidence counts. Empty or unreviewed results do not become completed hotword reviews.
- For raw-monitoring candidates, supply the real `raw_evidence_record_id`. The controller fills missing original source fields/full text from that immutable row; do not copy long snapshots or calculate hashes manually. Existing wrong values still fail validation.
- The controller completes missing deterministic IDs, SHA-256 values and unique exact excerpt offsets before draft validation. Ambiguous matches remain errors; query/candidate references must still be consistent. Never manufacture IDs for absent evidence.
- Do not manually calculate hashes, prose punctuation or numbering. Use `scripts/cwh_timing_report.py --job-dir <job>` to inspect recorded stage/command timings; it does not measure token usage or certify success.
- CLI output defaults to a compact handoff: current status, task, errors and stage status map. Full history remains in `pipeline_state.json`; use `--output-format full` only for diagnosis or a legacy stdout consumer.

## Input Routing and Stage Boundaries

The pipeline order is fixed:

1. `preflight`
2. `intake`
3. `workbook`
4. `research_plan`
5. `domestic_viewpoints`
6. `domestic_evidence_verification`
7. `domestic_comments_sentiment`
8. `overseas_evidence`
9. `hotwords`
10. `render`
11. `delivery_gate`

If the workbook already contains `关键词`、`总事件`、`子事件1...N` and `子事件数据汇总`, treat it as the standard workbook. Otherwise run the independently testable raw-workbook stage first. When the user asks only for workbook organization or comparison, stop after `workbook` (stage 3).

## Non-bypassable evidence rules

- Workbook topics, dates, event IDs, exclusions, totals, channel counts, trend data, and embedded charts are authoritative. Do not infer or rewrite them.
- Read `config/source_registry.v1.json` as a priority seed, not an allowlist. Follow the grouped lanes and caps emitted by `research_plan.json` in both bounded profiles; only `exhaustive` expands every required source separately.
- Preserve an explicit `eligible`, `duplicate`, or `excluded` decision for every reviewed search result, with the executed query and URL snapshot.
- Each eligible claim needs a verified in-window publication time, immutable full-text snapshot and hash, one speaking subject, a continuous excerpt with exact offsets, and a substantive `formal_claim` (normally 45-120 Chinese characters, not a truncation cap). Extract distinct judgments separately even from one speaker; one judgment may use several short sentences. Search snippets are not source snapshots.
- Interpretation eligibility is separate from exact quotation and source support. Pure retelling of meeting requirements or existing policy provisions remains facts, not the publisher's own judgment. Use the configured `viewpoint.interpretation_eligibility_rule`: identify the real subject's independent judgment about the current decision, preserve implementation stages and conditions, and never add an evaluation just to turn a fact into an interpretation.
- In bounded mode, select 6-12 representative independent voices per topic when evidence permits, with a hard formal cap of 12. Keep other valid candidates as `formal_use=reserve` with `reserve_reason`. Fewer than four selected voices requires a traceable `evidence_shortfall`. Exhaustive mode maps every eligible voice into prose.
- The authoring model does not certify its own claim. A separate model run with a different run ID reviews every proposition against the frozen source bundle.
- Before independent review, `scripts/complete_cwh_evidence_structure.py` completes mechanical draft fields and `scripts/normalize_cwh_analysis.py` regenerates `cluster.details` from ordered atomic claims. Do not preserve model-written paragraph wording or run completion on a frozen verified bundle.
- Draft and final density checks share `scripts/cwh_viewpoint_gate.py`: normally two independent speakers and 120 Chinese characters. A thinner cluster needs `thin_cluster_exception` with non-empty `reason`, `search_evidence`, and `reviewed_by`; accepted exceptions remain in the final audit. This never waives source mapping, per-claim quality or independent semantic review. Repeating a speaker or attribution verb does not create another voice.
- Domestic comments must be real in-window comment/reply text with platform, original URL, comment identifier, and formal-use review. Article bodies, search snippets, and comment counts are not comments.
- Sentiment ratios come only from the reviewed comment-level sentiment pipeline. Hide formal sentiment when a topic is not `ready` or has a zero denominator.
- Overseas media and overseas public comments are separate evidence universes. Review meeting relevance, category, deduplication, and Simplified Chinese translation before formal use. A completed zero-result collection is not the same as a failed collection.
- Use existing monitoring-system chart images byte-for-byte when available. Public evidence does not change workbook counts except through the audited in-window overseas-media reconciliation stage.

Read [references/analysis_bundle_schema.md](references/analysis_bundle_schema.md) when producing or repairing the analysis bundle. Read [references/sentiment_pipeline.md](references/sentiment_pipeline.md) for comment collection and sentiment. Read [references/system_data_contract.md](references/system_data_contract.md) when adapting workbook fields.

## Formal writing and output

Read [references/formal_report_rules.md](references/formal_report_rules.md) before rendering. The executable cross-topic rules are in `config/formal_writing_rules.v1.json`; they were distilled from multiple unrelated baseline reports and contain no meeting-specific fact, person, source, number, or conclusion.

The formal report uses the fixed chapters `一、舆情传播情况`、`二、境内舆论情况`、`三、境外舆论情况` and `附录`. Lead with data, then interpretation. Use evidence-supported stance headings and concrete attribution. Do not write vague aggregations such as `媒体普遍认为`, source lists, engineering notes, or placeholder prose.

Use the shared claim-composition and cluster-structure rules in the current author task: concrete judgment plus its actual reasoning or conditions, not article introductions. Cluster count follows substantive evidence (usually 2-4, up to 5-6 distinct judgments when supported), never a mandatory topic checklist. Baseline style is useful; its dates, sentiment ratios, people, slogans and unsupported attention claims are not current facts.

Scripts share one rule configuration for Word and Markdown: opening, chapter names, propagation sentences, source ordering, attribution, numbering, comment lead, hotword frames and overseas transitions. Topic counts and numbering are dynamic; never discard the ninth group or shorten a qualification to fit a template. A chair is named only when `meeting.chair_name` and `meeting.chair_source` are provided; otherwise use the neutral opening. Never assume a particular person, publisher, peak date, prominent placement or factual-report majority from historical examples.

Raw overseas reviews and supplemental research use the same configured analysis-summary rule. Formal summaries state actual judgments and source-supported reasoning, not article introductions, stock-movement roundups or audit explanations. Keep review reasons separate and retain all qualifications; renderers must not truncate a reviewed summary at an arbitrary length.

The workbench is also script-owned: `scripts/generate_dashboard.py` injects structured data into the shipped `assets/cwh_dashboard_template.html`. Layout, styles, charts, navigation, evidence cards and export controls are reusable assets, not model coding tasks. The `render` stage produces Word, Excel, Markdown and HTML together; never ask a model to rebuild the page, emit HTML/CSS/JavaScript, redraw existing system charts or duplicate data into a separate hand-authored dashboard. Do not read the large HTML template into the model context during a normal report run. Template defects are Skill-development issues, not permission for a report worker to patch the renderer.

Required final artifacts are synchronized Word, report Excel, `report_data.json`, `cwh_audit.json`, evidence-mapping audit, and self-contained HTML. `delivery_gate` must verify all declared artifacts and hashes, including the same `evidence_id` mappings in structured data, Word, and HTML. A partial artifact set is not formal completion.

## Focused references

- [references/cwh_requirements.md](references/cwh_requirements.md): business acceptance criteria.
- [references/report_schema.md](references/report_schema.md): structured report fields.
- [references/capability_matrix.md](references/capability_matrix.md): runtime capability and fallback boundaries.
- [references/raw_workbook_pipeline.md](references/raw_workbook_pipeline.md): raw exports to reviewed standard workbook.
- [references/formal_report_rules.md](references/formal_report_rules.md): layout, wording, appendices, and rendering details.

Run the regression suite after changing policy, validators, or rendering:

```powershell
python -m pytest -q
```
