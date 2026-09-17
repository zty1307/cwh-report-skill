# Approved fill-in template candidate

This candidate imports the human-reviewed generic Word template, preserves its approved fixed phrases, and fills the same eleven slots for all models. Editorial wording is maintained separately from evidence/measurement rules in `config/editorial_template.v1.json`. It does not confer semantic approval, change statistics or turn an access failure into a verified collection result. Current sourced meeting metadata overrides the configurable chair default.

## Changed behavior

- One-source viewpoint target: 100–200 characters excluding attribution and whitespace, including punctuation. This is a soft writing target, not padding, truncation or a new 100-character rejection gate.
- Prefer faithful source wording; do not force every quotation into judgment/reason/scope fields.
- All current topics retain domestic-media and comment positions. Missing evidence produces a notice, not fabricated quotations or silently dropped topics.
- Word and Markdown share approved fixed prose. Template editing notes never enter generated prose. The original human-edited file is never overwritten.
- Default paragraph packing uses at most two complete claims and a 480-character soft limit; a single necessary long claim is never cut. Physical splitting does not certify semantic grouping.
- Source emphasis uses structured attribution, not verbs found inside a claim. Headings stay with following content and table headers stay with the first data row.
- Existing valid monitoring images are retained. Invalid/empty images trigger the documented fixed-style fallback. Word-cloud height and natural flow remain controlled by script.
- Reading contracts repeat required fields before submission for every provider; model-specific writing templates are not introduced.
- Batched hotword initial review no longer also requests whole-table coverage, padding or a completed global second pass. Exact candidate/source windows are retained; the separately invoked global review remains required.
- Bare meeting references followed directly by a statement or quotation (for example `会议明确……`) also require actual-source identification. Arabic numbers adjacent to Chinese text are included in the existing literal-support gate; a semantic approval cannot waive added dates or quantities.
- Synthesis may echo unchanged input metadata. Only five known metadata fields are removed after exact equality checks; unknown or altered fields still fail. Native headings, groups and selected claim IDs are preserved instead of discarding completed grouping.
- Program-generated raw-workbook topic charts use the same fixed style as the Word fallback: dark blue, descending values, one decimal in ten-thousands, complete wrapped labels. Duplicate labels do not merge statistical groups; original workbook row order is unchanged.
- Approved comments in one topic are not dropped when their individually reviewed headings differ. Existing headings are retained as separate clauses in one numbered topic, without inventing a combined stance. The quote coverage audit remains mandatory.

## Verified scope

The local regression suite passed 1189 tests, with seven skipped. Two previously delivered datasets were independently re-rendered and inspected: 15 and 13 pages, each with three tables and three original images. Source numbers, comments and evidence were preserved; existing display-heading normalization is recorded separately. These are layout regressions, not new end-to-end model runs or renewed semantic reviews.

Fresh two-article extraction used identical full source text and shared production instructions. DeepSeek completed in 43.578 seconds with source-span checks passing. GLM first omitted claim classification fields; after the shared required-field reminder, a fresh run completed in 24.062 seconds with those checks passing. These checks do not certify every extracted claim's editorial suitability.

HY4 timed out at 182.578 seconds on the same task. An isolated host request to disable thinking also timed out at 180.844 seconds; provider enforcement of that setting was not established. Do not advertise HY4 stability or three-model end-to-end acceptance from this candidate's template tests.

During a fresh full GLM run, initial hotword partitions timed out at approximately 35 seconds. An isolated replay of a 33-candidate packet also timed out at 90 seconds. Scoping initial review separately allowed one eight-candidate replay to return in 57.438 seconds, but the corresponding 33-candidate replay still timed out at 90.36 seconds. This instruction correction is not a demonstrated complete hotword performance fix. No running full test was patched or had its original clock reset.

A saved GLM claim exposed an unexpanded `会议明确` reference that an independent reviewer had approved. The updated detection requests actual-source disambiguation. A fresh local call returned a correction in 17.75 seconds, but also added a date absent from the selected excerpt; the corrected numeric gate rejects that addition. Field completeness is not production acceptance. These fixes were developed after the full tests started and require separately labelled verification, not retroactive certification of their frozen code.

## Fresh complete runs and resulting defects

Two isolated raw-input runs used frozen commit `404875f`, the same ten raw inputs and the bounded one-hour profile. DeepSeek completed the pipeline in 2207.063 seconds (36m47s); GLM completed in 1849.640 seconds (30m50s). Both delivered Word, Excel and a workbench with declared gaps. These are measured single runs, not evidence of repeatable stability or high-quality acceptance across three providers. Neither test's copied code, original outputs or clock was changed.

All 19 DeepSeek pages and 18 GLM pages were rendered and inspected. DeepSeek had 43 retained domestic claims and 27 approved hotwords, but two of four approved domestic quotes were lost in grouping. A separately labelled rendering replay after the comment fix displayed all four quotes and preserved the three original image hashes; all 19 replay pages were inspected. That replay does not renew the original claims' semantic approval.

GLM had 49 retained domestic claims but no final approved hotwords/cloud or formal domestic quotes. One topic had valid native grouping rejected solely for exact echoed metadata, then fell back to source order. Replaying both original and repair responses through the corrected normalization preserves the same five native groups, eleven selected claims and sixteen reserves. It does not introduce new semantic decisions or modify the original run. The raw portable chart used a divergent old style; the shared-style replacement was rendered from the real topic values and checked independently.

Separate GLM production-review diagnostics must be distinguished from the full run. An initial diagnostic used different host effort/thinking settings and timed out on six batches, retaining only two claims: a passed mapping check in that diagnostic is not report-quality success and does not establish a production regression. A further diagnostic uses the saved full-run effort/thinking settings: all seven body batches completed; the complete review took 201.110 seconds, retained 44 of 50 draft claims, approved 22 headings, and passed the current strict mapping gate. Original inputs were unchanged. No review batching policy was changed on the strength of the mismatched diagnostic. This is a new review of a saved draft, not another complete raw-input run.

The same 33-candidate hotword packet also returned five first-pass choices in 15.219 seconds using the normal semantic host setting, versus the earlier 90.360-second timeout under the attempted minimal/disabled-thinking setting. This is a single controlled component observation, not proof that an advertised reasoning switch has the same behavior on all providers or that the global hotword pass is complete. Host settings must be measured and kept separate from generic Skill rules.

A subsequent complete GLM hotword component reviewed all 205 candidates in 141.390 seconds, including the independent global pass, with no deferred batches. All 25 retained terms passed the original raw-article evidence scoring and rendered using the packaged font in an isolated output. The 36-term quantity target was not met; semantic term-choice quality is not certified by rendering or literal matching alone. The full original report remains unchanged. A fresh raw-input run of `61e629b` was then launched with explicitly recorded normal raw-review host settings; later chart edits were not injected into its copy.

Native Excel paths also read the shared bar color, preserve complete wrapped labels and display one decimal with the same unit. On a separate saved-workbook copy, the finalizer completed and the summary values, formulas and series bindings matched the original. Native Excel PDF rendering confirmed the displayed color, labels and units. An empty native PNG export was reproduced: export success now also requires a nonempty PNG signature, rather than treating a successful COM call as a valid picture. Existing image-validation fallback remains in place. The original workbook was never overwritten.

A fresh DeepSeek run at `d1d78ca` exposed a native-host compatibility defect: Windows PowerShell 5.1 read the UTF-8 chart JSON as the system ANSI code page and rejected the Chinese unit. That run initially failed in the workbook stage after 461.860 seconds; it must not be counted as uninterrupted success. `e8758b8` adds explicit UTF-8 decoding and a regression that executes the real configuration assignment through `powershell.exe`, not only modern `pwsh`. The full chart finalizer then completed on an isolated copy of the failed run's workbook. The owned test was resumed with its failed status and prior Skill preserved, original start time unchanged and repair downtime included. Its final outcome is still pending at this checkpoint.

## Release boundary

Keep candidate publication separate from main. Do not package raw workbooks, source articles, benchmark reports, private output HTML, model logs or credentials. The approved generic template, rules, scripts and tests are distributable project resources; local diagnostics remain outside this repository.
