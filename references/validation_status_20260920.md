# Validation snapshot — 2026-09-20

This is a candidate release, not a claim that every model or network environment is stable.
All models use the same Skill rules; model names below identify actual test hosts only.

## Observed results

- A fresh five-topic, eight-workbook GLM-5.3 run completed Word, Excel and HTML in **1938.968 seconds (32:19)** using code commit `82ce3151d9525c7bfee280f9b68443dec559707e`. No pre-collected comments were imported and no manual stage repair occurred in that run. The pipeline executed its public collection path.
- The GLM run retained 29 independently reviewed viewpoint claims across all five topics. Its formal Word structural checks passed, including the three required images/tables and coverage of approved comment quotations. Two numbered groups retained one speaker, and the reviewed cloud had 34 unique terms, below the 36–42 target. These remain explicit quality gaps.
- Earlier real runs produced artifacts with GLM, DeepSeek and native Codex in approximately 34–38 minutes while sharing a previously collected comment corpus. Those times do not include the earlier collection. Some had missing interpretations or headings requiring further revision; artifact generation alone was not accepted as high quality.
- A separate DeepSeek run with automatic collection completed after one source-adapter fix/resume in 2842.973 seconds (47:23, including the wait). One topic lacked formal interpretation after a model request stalled. This is not evidence of unattended high-quality stability.
- HY4 did not demonstrate a stable complete report within the target. Multiple bounded reading requests did not finish; no other model was silently substituted and incomplete output was not certified as a HY4 success.

## Checks and boundaries

- The current regression suite passed **1472 tests**, with **7 environment/fixture-dependent tests skipped**. These checks do not replace live model or page inspection. A subsequent display-only repair prevents duplicate attribution when an unchanged source sentence already attributes the same named speaker after a reporting connector or quoted clause.
- All three benchmark topic-table column-width sequences were checked against generated Word output and matched. Deterministic visual templates and bundled cloud font remain fixed; current meeting labels and quantities change.
- A separate GLM retained-evidence revision preserved 25 verified claims, used 11 groups with 2–3 distinct speakers each, and included all three independently accepted quotations. It was checked through actual Word rendering. It is an editorial/component revision, not another fresh full-flow time measurement.
- Failed source-order synthesis cannot publish concatenated claims. Native regrouping only reassigns existing claim IDs, preserving original evidence and review records; candidate-family indexes are rebuilt with the same assignments.
- Quoted opinions remain attributed opinions, not independent proof that every prediction made by a source is true. Missing source access, incomplete reading and missing comments remain visible in audits. User-approved editorial defaults are not empirical measurements.
- No raw monitoring exports, report copies, browser profiles, credentials or captured private session state are included in this validation note or release.

Use the measured result and the remaining gaps together. Do not advertise all-model stability, complete coverage, or a guaranteed one-hour SLA from these tests.
