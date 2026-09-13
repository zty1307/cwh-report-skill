# Model-neutral execution contract

The default formal profile is `bounded_60m`. It is designed for heterogeneous model workers and a one-hour wall-clock service target under normal network conditions. The target is an engineering budget, not permission to invent evidence or bypass a failed gate.

## Division of work

Scripts own input classification, workbook normalization, query generation, batching, deduplication, identifiers, time-window filtering, deterministic prose structure, rendering, hashing, retries and delivery status. A model may decide only relevance, speaker identity, atomic claims, stance, cluster assignment, semantic support and translation quality.

The model receives one bounded JSON task at a time. It writes only the declared JSON output. It must never edit the Skill, validators, `pipeline_state.json`, `pipeline_events.jsonl`, artifact hashes or report files. Missing evidence is a structured blocker, not an invitation to create a candidate or pad a paragraph.

## One-hour budget

The executable limits live in `config/execution_policy.v1.json`. The default budget reserves eight minutes for rendering, final audits and transient overhead. Research lanes are bounded by query, page-fetch and formal-voice limits. Monitoring-system full text is always processed first. Official/mainstream, industry/expert and public-platform lanes may execute in parallel.

The controller persists the first-run clock and the first-entry clock of each stage. Waiting for manual worker output and retrying consume the same budgets; explicit resume and invalidation do not grant a new hour. Each subprocess timeout is clipped to the remaining stage and job time. In-process stages are checked at return and cannot be accepted after expiry. Expiry records `time_budget_exhausted` and retains checkpoints; start a new job directory for a new timed evaluation. The one-hour target still requires actual model tests, including network and collection time.

The bounded profile stops after minimum lane coverage plus one evidenced zero-new round, or when the lane budget is exhausted. Additional relevant candidates remain in the audit as `formal_use=reserve`; they do not have to expand the formal report indefinitely. The optional `exhaustive` profile retains the older two-zero-round behavior and has no wall-clock SLA.

## Repair behavior

Validation feedback is machine-readable. A repair pass may change only the fields named by the validator and must preserve accepted identifiers and source snapshots. Each model stage receives at most two repair rounds in the bounded profile. A new explicit pipeline invocation rearms a previously failed stage; the operator does not edit attempts or hashes.

The latest event log is authoritative over a restored state snapshot. A state claiming an earlier run count or success after a later failed event is rejected as an integrity violation. Final success additionally requires every declared report and audit artifact to match its recorded hash.

Windows checkpoint replacement retries transient permission failures for at most 2.55 seconds of backoff. Persistent failures are surfaced with the old checkpoint intact. The model must never delete the target or patch its hash to clear a lock.

`domestic_viewpoints` validates the unreviewed draft identically in automatic and manual-worker modes. Only the next stage requests independent semantic certification. That review worker may write its review packet; the controller alone writes the verified bundle and mapping audit. These are file contracts, not an operating-system sandbox; the host must scope worker permissions accordingly.

## Writing behavior

Reusable writing structure and sentence rules live in `config/formal_writing_rules.v1.json`. They were distilled from reviewed reports across unrelated subjects. They define chapter order, paragraph roles, stance headings, attribution forms, evidence density, comment grouping, hotword prose and overseas prose. No period-specific topic, person, source, number or conclusion is stored in the rules.

The model supplies atomic, evidence-backed judgments. Scripts assemble the fixed report skeleton. This keeps tone and structure stable across models while preserving the current meeting's evidence and uncertainty.

`cwh_viewpoint_gate.py` applies the same density rule before and after rendering. It counts distinct speaker identities and Chinese characters, not URL count or attribution verbs. Accepted `thin_cluster_exception` records appear in `cwh_audit.json` under `quality_summary.viewpoint_density_exceptions`. An exception never authorizes missing source evidence or unsupported claims.
