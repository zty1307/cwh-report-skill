# Model-neutral execution contract

Bounded missing-evidence delivery now uses `deliver_available_with_gaps`: return usable evidence plus honest gaps, independently review existing claims and continue all output stages. Quantity targets must not stop Word/Excel/HTML delivery. The final audit may say `delivered_with_gaps` while preserving `ready_for_formal_delivery=false`; no claim of complete coverage is required for users to receive files. Source integrity and cross-output consistency still apply. Earlier references to missing-evidence blockers below describe hard access/structural failures, not a requirement to withhold all available content.

The default formal profile is `bounded_60m`, with a 3600-second limit and a 2700-second research cutoff that preserves delivery time. `bounded_40m` remains an explicit tighter option and `exhaustive` keeps uncapped research. These are engineering budgets, not evidence that every model can complete within them or permission to bypass a failed gate.

## Division of work

Scripts own input classification, workbook normalization, query generation, batching, deduplication, identifiers, time-window filtering, deterministic prose structure, rendering, hashing, retries and delivery status. A model may decide only relevance, speaker identity, atomic claims, stance, cluster assignment, semantic support and translation quality.

The model receives one bounded JSON task at a time. It writes final artifacts only to `declared_outputs` and collection seeds, raw responses or temporary batches only under `stage_workspace`. It must never edit the Skill, validators, `pipeline_state.json`, `pipeline_events.jsonl`, artifact hashes or report files. Missing evidence is a structured blocker, not an invitation to create a candidate or pad a paragraph. These contracts are instructions; the host must enforce filesystem permissions when sandboxing is required.

## Execution budgets

For `bounded_60m`, standard-workbook input reallocates 870 unused raw-normalization seconds: workbook 900→30, domestic authoring 720→1290, and independent review 300→600. Other stages, the 675-second reserve, 2700-second research cutoff and 3600-second total stay unchanged. The input-mode allocation is resolved once into the persisted contract and propagated to worker timeouts. Overrides cannot inflate the total or reduce independent review, rendering or final-gate allocations. Raw-input budgets are unchanged.

The executable limits live in `config/execution_policy.v1.json`. Both bounded profiles use one active model worker and serial stages. Stage limits are not increased by the reserve. Research lanes are bounded by query, page-fetch and formal-voice limits. Monitoring-system full text is always processed first. Independent review is a separate sequential run. See `model_worker_host.md` for permission-aware transports and honest review-only delivery. Models do not need to run shell commands or edit pipeline state.

The 40-minute allocation is: preflight 30 seconds, intake 15, workbook 150, plan 30, domestic evidence 540, independent review 300, comments 330, overseas 270, hotwords 90, render 165 and final gate 120. Research retains ten query executions per topic so all source lanes, open search and a zero-new check can fit. It caps full-page fetches at 18 and named-entity expansions at two; comments allow four queries and 30 retained candidates; overseas allows one supplemental query and six page fetches. Both bounded profiles retain the same minimum independent voices, formal voice cap, source mapping and independent semantic review. A large raw workbook or limited access may exhaust these budgets and must produce an honest blocker.

The controller persists the first-run clock and the first-entry clock of each stage. Waiting for manual worker output and retrying consume the same budgets; explicit resume and invalidation do not grant a new time window. Each subprocess timeout is clipped to the remaining stage and job time. In-process stages are checked at return and cannot be accepted after expiry. Expiry records `time_budget_exhausted` and retains checkpoints; start a new job directory for a new timed evaluation. The 40-minute target requires actual end-to-end model tests, including network, collection, retries and delivery. Report completion rate and elapsed time together; an early timeout is not a speed improvement or a successful report.

The bounded profile stops after minimum lane coverage plus one evidenced zero-new round, or when the lane budget is exhausted. Additional relevant candidates remain in the audit as `formal_use=reserve`; they do not have to expand the formal report indefinitely. The optional `exhaustive` profile retains the older two-zero-round behavior and has no wall-clock SLA.

Large raw corpora are indexed once, with per-topic reading order and separate full-article files. In bounded mode each topic requires at least `min(12, corpus size)` real full-article reviews. The remaining source IDs can be explicitly deferred only against a hash-matching complete controller index. Deferred records are never labelled reviewed, excluded or evidence of zero new viewpoints; quality gates on selected claims remain unchanged. The controller can hydrate missing snapshots by `raw_evidence_record_id`, removing repeated multi-megabyte copying by the model. Exhaustive mode still requires every record to be reviewed.

## Repair behavior

Validation feedback is machine-readable. A repair pass may change only the fields named by the validator and must preserve accepted identifiers and source snapshots. Each model stage receives at most two repair rounds per pipeline invocation in the bounded profile. A new explicit pipeline invocation rearms a previously failed stage but does not reset elapsed budgets; the operator does not edit attempts or hashes. Do not repeatedly resume an unchanged invalid output.

The latest event log is authoritative over a restored state snapshot. A state claiming an earlier run count or success after a later failed event is rejected as an integrity violation. Final success additionally requires every declared report and audit artifact to match its recorded hash.

Windows checkpoint replacement retries transient permission failures for at most 2.55 seconds of backoff. Persistent failures are surfaced with the old checkpoint intact. The model must never delete the target or patch its hash to clear a lock.

The subprocess watchdog runs separately from stdin/stdout communication. A Windows child that does not consume a large prompt cannot prevent timeout enforcement. Both monotonic and wall-clock deadlines are checked; a forward clock jump or resumed host does not grant more time. Cleanup targets only the child tree created for that invocation.

The host treats the final structured model event as authoritative even when a vendor CLI wrapper exits with shell code 0. A terminal rate-limit event or transient provider-network failure is normalized to a model-neutral `waiting_ai` checkpoint with any returned retry time; it does not consume semantic repair attempts or trigger immediate blind retries. Authentication, malformed output and semantic failures remain distinct hard failures. Raw review, compiled author/reviewer, comment, hotword and generic model adapters use the same transport classification.

`domestic_viewpoints` validates the unreviewed draft identically in automatic and manual-worker modes. Only the next stage requests independent semantic certification. That review worker may write its review packet; the controller alone writes the verified bundle and mapping audit. These are file contracts, not an operating-system sandbox; the host must scope worker permissions accordingly.

## Writing behavior

Reusable writing structure and sentence rules live in `config/formal_writing_rules.v1.json`. They were distilled from reviewed reports across unrelated subjects. They define chapter order, paragraph roles, stance headings, attribution forms, evidence density, comment grouping, hotword prose and overseas prose. No period-specific topic, person, source, number or conclusion is stored in the rules.

The model supplies atomic, evidence-backed judgments. Scripts assemble the fixed report skeleton. This keeps tone and structure stable across models while preserving the current meeting's evidence and uncertainty.

The compiled author may make one compact missing-reason completion call per topic (at most 45 seconds, 12 items and 32,000 request characters). Only already-returned dispositions with absent reasons are eligible; missing, duplicate or unknown IDs still fail exact coverage. For selected claims the host restores exact original excerpts rather than resending every full article. The completion model returns only IDs and reasons; existing claims, decisions, headings, source identities and spans cannot change. Original incomplete rows and the actual completion run are retained, and hash-checked identical requests can reuse their cache. This does not certify the original selection or bypass independent evidence verification.

The optional compiled transport presents original articles as numbered contiguous segments without deleting any characters. Models return an ordered segment-ID range; scripts extract verbatim text and exact offsets. This avoids copied or paraphrased quotations, but does not establish semantic support. Legacy free-text excerpts still require unique exact matches. A repeated voice in the same cluster keeps its first author-ordered formal claim; later statements stay auditable as reserves, without merging their meaning. Conflicting cross-cluster assignments still require model resolution.

Draft structural completion fills only missing deterministic identifiers, source-text hashes and unique exact excerpt offsets. Existing nonempty values are preserved for validation, including invalid ones; ambiguous identity or repeated excerpts are not guessed. Frozen independently reviewed bundles are refused. The author must still supply consistent discovery/query references and actual source facts. No completion helper can establish semantic truth.

Word and Markdown use the same executable opening, chapter, attribution, numbering, comment and overseas frames. Explicit `meeting.chair_name` plus `meeting.chair_source` is required to name a chair. Source priority uses only supplied metadata. Unsupported rhetorical padding is rejected rather than silently deleted. Templates never supply a meeting-specific person, media placement or an unsupported majority claim.

For token economy, keep accepted artifacts on disk; read only current-stage inputs and required references, reuse source snapshots, and return structured changes instead of redrafting full prose. `scripts/cwh_timing_report.py --job-dir <job>` reports measured command duration separately from wait and other uninstrumented time. It is not an API token meter; old logs without instrumentation remain unknown.

`cwh_viewpoint_gate.py` applies the same density rule before and after rendering. It counts distinct speaker identities and Chinese characters, not URL count or attribution verbs. Accepted `thin_cluster_exception` records appear in `cwh_audit.json` under `quality_summary.viewpoint_density_exceptions`. An exception never authorizes missing source evidence or unsupported claims.
