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

## Verified scope

The local regression suite passed 1171 tests, with seven skipped. Two previously delivered datasets were independently re-rendered and inspected: 15 and 13 pages, each with three tables and three original images. Source numbers, comments and evidence were preserved; existing display-heading normalization is recorded separately. These are layout regressions, not new end-to-end model runs or renewed semantic reviews.

Fresh two-article extraction used identical full source text and shared production instructions. DeepSeek completed in 43.578 seconds with source-span checks passing. GLM first omitted claim classification fields; after the shared required-field reminder, a fresh run completed in 24.062 seconds with those checks passing. These checks do not certify every extracted claim's editorial suitability.

HY4 timed out at 182.578 seconds on the same task. An isolated host request to disable thinking also timed out at 180.844 seconds; provider enforcement of that setting was not established. Do not advertise HY4 stability or three-model end-to-end acceptance from this candidate's template tests.

During a fresh full GLM run, initial hotword partitions timed out at approximately 35 seconds. An isolated replay of a 33-candidate packet also timed out at 90 seconds. Scoping initial review separately allowed one eight-candidate replay to return in 57.438 seconds, but the corresponding 33-candidate replay still timed out at 90.36 seconds. This instruction correction is not a demonstrated complete hotword performance fix. No running full test was patched or had its original clock reset.

## Release boundary

Keep candidate publication separate from main. Do not package raw workbooks, source articles, benchmark reports, private output HTML, model logs or credentials. The approved generic template, rules, scripts and tests are distributable project resources; local diagnostics remain outside this repository.
