# Model worker hosts

One controller owns execution, timers and output validation. Use one active model request at a time; independent review gets a fresh sequential session ID. Do not attach to another user's existing conversation or alter its installed Skill. Test with a copied Skill, separate job directory and session IDs. A directory contract is not an OS sandbox; use host sandboxing when untrusted workers have tools.

## Tool-capable CLI

Set `CWH_MODEL_COMMAND_JSON` to an argv array for your approved noninteractive CLI. It must read a prompt from stdin; `{session_id}` is replaced with a fresh UUID. Use an explicit model ID, no automatic fallback, and only needed read/write/research tools. Keep credentials in environment/auth storage, not argv or logs.

Set `CWH_PIPELINE_AI_COMMAND_JSON` to an argv array:

```json
["<python>", "<skill>/scripts/run_cwh_model_worker.py", "--task", "{task}"]
```

The adapter passes one bounded task, records its session, elapsed time and output presence, and leaves acceptance to the pipeline. The controller passes remaining cumulative time, not a fresh full budget. A timeout terminates only the child process tree created for this command, never all processes of a model/application name.

Optional `CWH_RAW_REVIEW_COMMAND_JSON` selects a no-tools CLI for raw-workbook review; the same main adapter then dispatches that stage through the inline JSON transport. Optional `CWH_VIEWPOINT_COMMAND_JSON` selects the experimental per-topic inline adapter for domestic viewpoints. These are argv arrays using the same session placeholder. Other stages still use `CWH_MODEL_COMMAND_JSON`. No vendor/model name is built into the Skill.

Before business data, check whether the CLI really permits the configured input/output paths. A no-tools model connectivity check does not prove file permissions. Windows hosts may expose `PowerShell` rather than `Bash`; this adapter does not need the model to execute either. Do not bypass approval failures or change another task's global settings. Use an approved non-tool transport if filesystem tools are unavailable.

Verify public search and full-page fetch separately: a successful search does not prove fetch permission. Some hosts return a permission error with `is_error=false`; the adapter checks explicit permission-denied tool events too. A permission blocker returns exit 23, a timeout 124; neither triggers a blind automatic worker retry. Per-process permission configuration requires user approval when a denied capability needs to be enabled. Never use a global permission bypass.

## Raw-review JSON transport

`run_cwh_inline_review.py --task <task>` is a narrower adapter for `raw_workbook_semantic_reviews` only. Configure the model CLI with no filesystem/shell tools and JSON or stream-JSON output. It receives source material over stdin and returns review JSON; host code writes only declared review outputs. It cannot perform downstream internet research or replace independent claim verification; unsupported stages return an explicit blocker.

The raw adapter reviews public TOP candidates, overseas articles and hotwords sequentially. Public/overseas packets retain the full supplied article contents. Hotword transport retains all candidate terms and up to two continuous source windows per term; these are indexes, not full-article verification. Original packets stay unchanged on disk. A term without adequate source support must not be selected. Host cache reuse checks both source packet and output SHA-256, never record IDs alone. New forward evaluations must not receive prior semantic decisions.

## Experimental topic batches

`run_cwh_batched_viewpoints.py` requires the controller-generated public corpus index. It sends full shortlisted articles and the current topic contract inline, with approved public-web tools only. Topics run sequentially within one cumulative stage budget; the model does not open files, compute hashes, render documents or design the workbench. Each batch output is checkpointed with input/output hashes and an explicit unvalidated status. Reuse is not semantic acceptance; the assembled draft must pass the same corpus, coverage, source-support, density and independent-review gates. Missing batches never produce a complete bundle. This transport remains opt-in until a fresh full-report evaluation passes.

`cwh_authoring_packet.py` derives the draft output shape from the maintained analysis schema and topic-specific source tasks. It removes unrelated comment, independent-review and renderer templates, not original article text. Packet-size reduction is measurable separately from token use and model latency; a smaller packet alone is not a successful test.

JSON transport may append missing container closers at end-of-output (never complete unfinished strings/values) or move a unique misplaced `research_audit.viewpoints` to its declared top-level slot. Each repair is audited. It never fills missing evidence rows or waives source/semantic gates; truncated arrays still fail record coverage checks.

## Delivery and success

Default research cutoff: 45 minutes; total budget: 60 minutes. Optional 40-minute mode remains separate. Review snapshots live in `review_delivery/`; they do not change pipeline status, source hashes, formal audit or `report/`. A status-only draft is not a completed report. Report formal success, review-only output, elapsed time, failed stage and untested stages separately. Do not infer multi-model reliability from unit tests or one connection probe.
