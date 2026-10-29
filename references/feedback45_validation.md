# Feedback-led research and raw reserve recall: measured validation

Published version: `2026.10.29-feedback45`.

This publication synchronizes the source validated on **2026-10-23**. Runtime
scripts, business rules, templates and tests match that frozen local source.
Publication changes are limited to README guidance, release metadata and this
validation note. Monitoring exports, completed reports, native model logs,
credentials and personal sessions are not included in the repository.

## What changed

- Default complete workflow: `bounded_45m`, with a 2700-second total limit,
  2460-second research cutoff and 240-second delivery reserve.
- Raw export screening and public-web research are both part of the workflow.
  AI tasks run sequentially. Every topic retains public-web opportunities even
  when monitoring exports already supply candidates.
- After initial independent review, weak topics can recall a small batch of
  unread raw reserves. Ranking examines argument signals near the actual policy
  terms in the complete source; it does not approve a viewpoint or truncate text.
- Additional queries receive actual previous reading rejection reasons and a
  separate unread list. Repeated or invalid query plans are rejected.
- Completed article readings and raw collection receipts can be reused with
  source, model, context and rule checks. Completed extraction is distinct from
  editorial selection and independent evidence review.
- Supplementation preserves the original clock, complete sources and the verified
  baseline. Incomplete readings remain unread; unreviewed claims remain reserves.

See [adaptive research](adaptive_web_research.md) and
[raw screening integration](raw_sample_screen_integration.md) for the execution
contract and bounded opportunities.

## Complete GLM measurement

| Item | Observed result |
|---|---|
| Test date | 2026-10-23 |
| Model and host | `glm-5.3-ioa`, WorkBuddy native CLI |
| Input | Fresh run from one period's 60 raw export workbooks |
| Complete-run elapsed time | **2271.25 seconds / 37m51.25s** |
| Pipeline | All 12 stages completed |
| Initial raw articles actually read | 50 |
| Additional raw reserve articles actually read | 5 of 6 submitted to the small collection |
| Additional feedback-led queries completed | 12 |
| Public pages with acquired body text | 33 per-topic URLs |
| Public pages actually read by AI | 27 per-topic URLs |
| Repeated completed reading dispatches found | 0 |
| Final domestic body claims | 28: 24 raw-monitoring, 4 public-web |
| Final Word evidence mapping | Passed, 28 claims mapped |
| Source retention audit | Passed |
| Delivery class | `delivered_with_gaps` |
| Certified formal readiness | **false** |

Acquired body text is not automatically AI-read. Explicit publication metadata
can resolve an out-of-window source before a native semantic call; such a
disposition is not counted as AI full-text review. Per-topic URL totals may
overlap and claim counts are not universal distinct-person counts.

### Before and after automatic supplementation in this same run

| Topic | Initially verified body | Effective verified body |
|---|---:|---:|
| Artificial intelligence action | 5 | 7 |
| Teachers Law revision | 7 | 8 |
| Price Law amendment | 7 | 9 |
| Modification and repeal of administrative regulations | 1 | 4 |
| Total | **20** | **28** |

All three additional administrative-regulation claims came from unread raw
reserves. Public-web supplementation did not produce an additional adopted
claim for that topic. This does not establish that no usable web commentary
exists. Changed paraphrases are not automatically new speakers.

The actual completed raw collection was also replayed with native dispatch
forbidden: cached receipt reuse succeeded with **zero additional model calls**.
The complete cold run itself did not need to redispatch a completed article.
Independent quote review is a separate required operation, not another initial
article extraction.

## Remaining limitations

The generated package still recorded an insufficient-source grouping warning,
two sample-length warnings (160 and 161 characters against the 150-character
limit), and 33 reviewed hotwords against a target of 36. These warnings remain
visible; workflow completion is not certification that the report meets every
formal delivery requirement. No viewpoints or hotwords were invented to meet
quantity targets.

One later administrative-regulation query plan was rejected as invalid or
repeated. The completed count above includes only executed queries, not that
rejected plan. Search, source access and model availability can still fail or
exhaust their bounded opportunities.

This is one complete GLM run on one period and one host. Other models and API
hosts require their own compatible adapters and validation. MCP effectiveness
was not isolated in a controlled comparison. No general model ranking, token
reduction percentage or guarantee of future 45-minute success is claimed.

The earlier interrupted run was retained for diagnosis without resetting its
clock; it is not the timed complete run reported here. Development, interrupted
trials and post-run audits are separate from this measured execution.

## Automated checks

The frozen source regression run on 2026-10-23 passed **1632 tests and 5 subtests**,
with **7 skipped** for external fixtures or environment conditions. Preflight
passed. The GitHub publication directory is separately checked for regression,
preflight, runtime equality and unintended data before upload. Local audit
artifacts remain outside the public source tree.

The publication checkout was rerun on **2026-10-29** under its standard
`cwh-report-skill` directory name: **1632 passed, 7 skipped, 5 subtests passed**
in **46.32 seconds**. Skill structure validation and preflight passed. This is
an automated regression measurement, not another complete model report run.
