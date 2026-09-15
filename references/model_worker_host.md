# Model worker hosts

One controller owns execution, timers and output validation. Use one active model request at a time; independent review gets a fresh sequential session ID. Do not attach to another user's existing conversation or alter its installed Skill. Test with a copied Skill, separate job directory and session IDs. A directory contract is not an OS sandbox; use host sandboxing when untrusted workers have tools.

Do not assume that a provider honors a requested reasoning level, disabled-thinking flag, token ceiling or stream timeout. A host probe must measure the actual completion and preserve timeout failures. Provider-specific knobs belong in the isolated host configuration, not in the model-neutral Skill or a shared application's global settings. Small decision batches can be necessary even when the input fits the context window.

The compiled independent-review adapter permits at most one in-budget author repair of rejected claims. It writes a separate repaired bundle, never overwrites the accepted input, and restricts changes to those claims and their exact continuous quotation ranges. A fresh reviewer examines the changed items; unchanged verdicts retain their actual prior reviewer IDs and a hash-bound initial review record. The controller checks this provenance and the full draft/mapping gates. Rejection, repair timeout or insufficient remaining time cannot be converted to approval.

## Tool-capable CLI

Set `CWH_MODEL_COMMAND_JSON` to an argv array for your approved noninteractive CLI. It must read a prompt from stdin; `{session_id}` is replaced with a fresh UUID. Use an explicit model ID, no automatic fallback, and only needed read/write/research tools. Keep credentials in environment/auth storage, not argv or logs.

Set `CWH_PIPELINE_AI_COMMAND_JSON` to an argv array:

```json
["<python>", "<skill>/scripts/run_cwh_model_worker.py", "--task", "{task}"]
```

The adapter passes one bounded task, records its session, elapsed time and output presence, and leaves acceptance to the pipeline. The controller passes remaining cumulative time, not a fresh full budget. A timeout terminates only the child process tree created for this command, never all processes of a model/application name.

Optional `CWH_RAW_REVIEW_COMMAND_JSON` selects a no-tools CLI for raw-workbook review; the same main adapter then dispatches that stage through the inline JSON transport. Optional `CWH_VIEWPOINT_COMMAND_JSON` selects the experimental per-topic inline adapter for domestic viewpoints. These are argv arrays using the same session placeholder. Other stages still use `CWH_MODEL_COMMAND_JSON`. No vendor/model name is built into the Skill.

For a small actual comment capture, `CWH_COMMENT_CAPTURE` points to the host-normalized raw cohort and `CWH_COMMENT_COLLECTION_AUDIT` to actual per-topic platform observations. With `CWH_SEMANTIC_COMMAND_JSON`, the controller then dispatches comments through the deterministic compiler and copies only declared sentiment/handoff outputs. The host must collect these internal inputs; do not ask the report user to prepare them. A reused diagnostic capture must not be represented as fresh end-to-end discovery. No supplied capture means the existing collector-capable worker route remains active.

Before business data, check whether the CLI really permits the configured input/output paths. A no-tools model connectivity check does not prove file permissions. Windows hosts may expose `PowerShell` rather than `Bash`; this adapter does not need the model to execute either. Do not bypass approval failures or change another task's global settings. Use an approved non-tool transport if filesystem tools are unavailable.

Verify public search and full-page fetch separately: a successful search does not prove fetch permission. Some hosts return a permission error with `is_error=false`; the adapter checks explicit permission-denied tool events too. A permission blocker returns exit 23, a timeout 124; neither triggers a blind automatic worker retry. Per-process permission configuration requires user approval when a denied capability needs to be enabled. Never use a global permission bypass.

## Raw-review JSON transport

`run_cwh_inline_review.py --task <task>` is a narrower adapter for `raw_workbook_semantic_reviews` only. Configure the model CLI with no filesystem/shell tools and JSON or stream-JSON output. It receives source material over stdin and returns review JSON; host code writes only declared review outputs. It cannot perform downstream internet research or replace independent claim verification; unsupported stages return an explicit blocker.

The raw adapter reviews public TOP candidates, overseas articles and hotwords sequentially. Public/overseas packets retain the full supplied article contents. Hotword transport retains all candidate terms and up to two continuous source windows per term; these are indexes, not full-article verification. Original packets stay unchanged on disk. A term without adequate source support must not be selected. Host cache reuse checks both source packet and output SHA-256, never record IDs alone. New forward evaluations must not receive prior semantic decisions.

## Experimental topic batches

`run_cwh_batched_viewpoints.py` requires the controller-generated public corpus index. It sends full shortlisted articles and the current topic contract inline, with approved public-web tools only. Topics run sequentially within one cumulative stage budget; the model does not open files, compute hashes, render documents or design the workbench. Each batch output is checkpointed with input/output hashes and an explicit unvalidated status. Reuse is not semantic acceptance; the assembled draft must pass the same corpus, coverage, source-support, density and independent-review gates. Missing batches never produce a complete bundle. This transport remains opt-in until a fresh full-report evaluation passes.

`cwh_authoring_packet.py` derives the draft output shape from the maintained analysis schema and topic-specific source tasks. It removes unrelated comment, independent-review and renderer templates, not original article text. Packet-size reduction is measurable separately from token use and model latency; a smaller packet alone is not a successful test.

JSON transport may append missing container closers at end-of-output (never complete unfinished strings/values) or move a unique misplaced `research_audit.viewpoints` to its declared top-level slot. Each repair is audited. It never fills missing evidence rows or waives source/semantic gates; truncated arrays still fail record coverage checks.

The shared response parser can also insert exactly one missing object-member comma when the JSON decoder explicitly expects that delimiter before an intact string key and colon. The entire object must then parse without duplicate keys. It changes no value, key, string or container, records the original response-text hash and insertion position, and does not combine multiple repairs. Missing values, multiple missing commas and ambiguous shape stay invalid. Original stream logs remain immutable; parsed formatting is not semantic approval.

## Delivery and success

### Experimental host-compiled semantic transport

Setting `CWH_SEMANTIC_COMMAND_JSON` opts domestic authoring and independent review into `run_cwh_compiled_worker.py`. Supply a no-filesystem/no-shell JSON model command. Also configure `CWH_SEARCH_COMMAND_JSON` with the approved search-only host command. Other stages retain the normal adapter; this option is not yet a demonstrated complete one-hour release.

The same compiled setting dispatches `hotwords` to `cwh_hotword_semantics.py`. The host validates independently reviewed viewpoints, collects original article excerpts and formal comments, and asks for semantic term choices only. It validates literal source links and topic coverage before a separate sequential second pass. The host records the actual two run IDs, preserves rejected choices, computes evidence counts and display weights with the existing hotword engine, and writes only the declared audit. Too few accepted terms, missing topics, fabricated phrases or a timeout remains a blocker. No-tools packet compilation is implemented and regression-tested; full domestic-model timing and quality still require a real end-to-end test.

The host sends bounded query lists and reconstructs IDs, result URLs and execution records from actual tool-result events. A narrative claim that a search ran is ignored. Site-restricted coverage is checked against returned URL domains; off-scope search results do not prove a registry/platform hit. The included event parser supports the observed stream-JSON `WebSearch` result format; other hosts need their own tested observation adapter, not a fake-compatible audit. Query cache reuse requires a matching query plan and byte-verified tool log, from which observations are re-derived.

Original monitoring articles stay complete. The experimental compiler collects per-topic reading packets, then submits a single multi-topic semantic request to reduce repeated model-session overhead. The model returns dispositions, named subjects, continuous quotes, atomic claims and cluster headings. Scripts compile the full analysis structure and deterministic prose. A separate fresh model context reviews propositions; the compiler fills only IDs, timestamps and unique exact offsets, preserving rejected verdicts. All existing pipeline gates remain active. Retry feedback participates in the semantic input hash; an unchanged cached invalid answer cannot satisfy a new repair request.

Compiled packets now provide numbered, contiguous source segments covering the entire original text. Authors choose `quote_range: [first_id, last_id]` and independent reviewers choose `source_range` within the frozen excerpt. Scripts slice original bytes-as-decoded characters and reject invalid/out-of-excerpt ranges; they never paraphrase a quotation or infer semantic acceptance. Full source text is sent once per unique snapshot. Legacy free-text quotes remain supported only when the exact source mapping validates. Missing dates in monitoring article bodies do not invalidate the export's immutable `published_at`; newly fetched web pages still need source-anchored publication dates.

Independent-review input places each byte-verified excerpt immediately beside its claim with claim-local IDs such as `e7/1`. Complete original context remains verbatim in `sources.source_text`, without a competing full-article numbering scheme. The compiler translates local excerpt ranges back to original source offsets and rejects cross-claim IDs or changed text. This reduces redundant input structure and paragraph-number mistakes; it does not waive proposition review, certify a verdict, or establish a latency improvement without model measurement.

New segment IDs include a host-derived source prefix; a range belonging to another article is rejected even if its local paragraph numbers exist here. After a draft or compile error, a hash-matching author checkpoint supports a new selected-field semantic repair with only the affected selected articles; source metadata and excluded rows are not model-editable. Unscoped mapping errors include all selected topics. Invalid transport shape returns exit 65 for the controller's bounded repair, while timeout 124 and permission 23 remain non-blind-retry outcomes. Local diagnostics and prior author repairs are never fresh end-to-end success.

Do not assume host `minimal`, thinking switches or token-budget flags actually cap a provider's reasoning. Validate effective behavior with real requests. Optional stream metrics report activity counts and provider-reported usage, not private reasoning text, and never label a timed-out request as a token/latency improvement. These runtime options belong to host configuration, not vendor names hard-coded into the reusable Skill.

Default research cutoff: 45 minutes; total budget: 60 minutes. Optional 40-minute mode remains separate. Review snapshots live in `review_delivery/`; they do not change pipeline status, source hashes, formal audit or `report/`. A status-only draft is not a completed report. Report formal success, review-only output, elapsed time, failed stage and untested stages separately. Do not infer multi-model reliability from unit tests or one connection probe.
