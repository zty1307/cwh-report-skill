# v47-rc1 validation — 2026-09-14

Evaluation notes only. Do not load prior test answers or reports into a fresh report-generation context.

## Scope and release status

Target: one sequential model worker, model-neutral rules, complete formal delivery within 60 minutes. The controller has a 45-minute research cutoff and cumulative stage/total budgets. The timeout is a limit, not a completion guarantee.

**Candidate, not a demonstrated one-hour formal-report release.** Real hy4 tests reached raw review and standard-workbook recovery, but have not passed the complete independent-review, comments, overseas, formal-render and delivery gates. Source/public unit-test results are reported separately from model results. No token-saving percentage is asserted.

## Fixes driven by observed failures

| Observed failure | Implemented response |
|---|---|
| Raw-review packets existed, controller looked in a different directory | Correct packet and full-corpus handoff; register the full corpus with its hash |
| Raw reviewer repeated a rejected output indefinitely | One bounded rerun per invocation; invalidate the rejected kind's cache; preserve other accepted decisions |
| Small-font wordcloud process crashed in Pillow | Skip identity MaxFilter(1); cache repeated deterministic candidate checks |
| Missing runtime capability found late | Preflight NumPy and real Asia/Shanghai timezone support; remove unused pandas requirement |
| Model shell/read/write permission errors | Host owns scripts and output writes; inline raw-review JSON transport; isolated cwd and fresh session IDs |
| Whole-corpus read loops consumed the viewpoint budget | Complete corpus index, bounded full-article reading order, exact raw-ID hydration; optional sequential topic batches |
| Search worked but full-page fetch was denied | Check these capabilities separately; recognize permission-denied tool events even when is_error is false; no blind permission/timeout retries |
| Repeated large cross-stage instructions in authoring packets | Derive the authoring-only JSON shape from the maintained schema, omit comment/reviewer/renderer templates, retain source and semantic constraints |
| Incomplete run had no usable status document/workbench | Generate separately labelled review-only Word and fixed-template HTML from hash-verified accepted data; never mark them formal |
| Windows file sharing interrupted manifest update | Use the shared bounded-backoff atomic JSON writer |
| Model included title-only overseas rows and treated its own summary as verified interpretation | Reject missing/title-only bodies; require explicit verification plus a continuous original interpretive_excerpt for interpretive inclusion |

Bounded corpus coverage is an explicit policy change: review at least min(12, topic corpus size) complete articles per topic, retain every original article, and mark unread IDs deferred rather than reviewed, excluded or evidence of saturation. Full-source support, voice/density gates and independent review remain required. Exhaustive mode still requires all articles.

## Real model experiments

The CLI explicitly selected hy4-preview-ioa. Each experiment had an isolated copied Skill, input directory and new session IDs; no other WorkBuddy window or shared installed Skill was modified. No fallback model was used.

| Experiment | Observed result |
|---|---|
| Initial full-agent transport | Wrong shell tool, then noninteractive write/execute denial; no report. CLI exit 0 did not mean successful delivery |
| Host-run raw review, first transport | Valid review JSON was wrapped in output_shape; parser repaired without changing semantic decisions |
| Fresh raw reviews | Public TOP 272.578 s, overseas 355.688 s, hotwords 200.266 s; all three produced real decisions. Three of 42 selected hotwords violated fixed lexical constraints |
| Explicit recovery, not fresh forward | Audited filtering removed those three invalid selections (39 remain); workbook and research plan passed. Subsequent file-reading loop timed out before producing a viewpoint bundle; total 750.609 s |
| Initial topic batches | Public search returned tool results; 2/2 attempted full-page fetches were permission-denied. Three unsuccessful attempts consumed 419.406 s before the retry fix |
| User-approved process-local WebFetch probe | One real government homepage fetch succeeded in 18.141 s, without shared setting changes or a global permission bypass |
| Topic batch after permission configuration | No permission-denied result; first topic timed out without a completed bundle. Full run stopped after 181.875 s, with one attempt, not repeated retries |
| Compact authoring contract | Prompt reduced from 88,330 to 45,490 characters with the same 12 full articles; first-topic timeout still occurred (181.406 s total). This is a measured payload reduction, not a proven latency or token reduction |
| Separate single-topic latency diagnostic | Returned after 449.813 s, with 5 search and 5 fetch tool calls. Its JSON missed a closing brace and misnested viewpoints. Audited, syntax-only repair recovered the response, but original evidence gates still rejected source/snapshot mismatches, unsupported claim wording and unexecuted platform coverage. This is not a completed report |

Recovery inputs include a prior test's inferred, unconfirmed topic mapping. Those runs are engineering diagnostics, not independently confirmed factual evaluation. The recovery workbook passed an interim build, not the final candidate's strengthened overseas checks: rereading the 50 real model decisions found two title-only inclusions and five interpretive inclusions without exact original analytical excerpts. The current gate rejects those seven decisions; original experiment files remain unchanged. A different accepted overseas count after new semantic review must not be called correct solely because the workbook passed its structural checks.

## Verification limits

Regression: source **355 passed**; public checkout **348 passed, 7 skipped** (private fixtures excluded). Public Skill validation and the actual WorkBuddy runtime preflight passed.

- WorkBuddy Python 3.13.14 passed the actual dependency preflight and a native small-font hotword probe. Shared runtime packages were not modified.
- Review-workbench browser checks at 1600 px and 390 px found no JavaScript errors or horizontal body overflow, with the review-only warning visible. This does not verify the uncompleted formal workbench.
- The review Word file was generated, but packaged page rendering could not run because soffice was unavailable. Word visual QA is **not passed**.
- Fresh one-hour formal completion, final report prose quality, downstream semantic correctness and cross-model reliability remain unproven.
- The per-topic inline adapter is opt-in and experimental. Cached batches are byte-verified but still unvalidated until the normal full pipeline gates pass.
