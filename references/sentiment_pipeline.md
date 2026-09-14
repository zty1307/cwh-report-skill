# CWH Sentiment Pipeline

## Scope

Analyze only traceable domestic-platform netizen comments inside the monitoring window. Prefer monitoring-system comment detail; when it is absent and public collection is authorized, use the reviewed output of `run_cwh_domestic_comment_collection.py` or `run_cwh_agent_reach_comment_collection.py`. Media articles, posts, video descriptions, search snippets and policy texts are evidence for viewpoints, not members of the `网民情感` denominator. System sentiment labels and aggregate ratios are retained only as audit references; they never replace this pipeline or enter the formal denominator.

The current domestic collection profile supports `wb,dy,ks,bili,zhihu` and explicitly excludes Xiaohongshu, Tieba, plus all foreign platforms. Excluded-platform comments must never enter `子事件数据汇总!G:I`.

## Required Flow

1. If the system already provides comment/reply detail, use it. Otherwise run `scripts/run_cwh_domestic_comment_collection.py` through MediaSpider Supervisor. If that route is blocked, use Agent Reach/Exa to discover candidate domestic articles, review their topic mappings in a seed file, and run `scripts/run_cwh_agent_reach_comment_collection.py` only against public no-login endpoints. Retain seeds, raw responses, run logs and inspection metrics.
2. The collection gate keeps only allowed domestic platforms, real comment/reply rows, mapped subtopics and parseable timestamps inside the monitoring window. It writes exclusions and reasons separately. Do not bypass login, captcha, rate limits or access controls. Agent Reach search snippets, article bodies and numeric comment counts are discovery evidence only.
3. Run `scripts/run_cwh_sentiment_stage.py` against the accepted `境内公开评论明细.csv` or system comment details. It rejects article bodies and aggregate comment-count fields and creates stable `sample_id` values.
4. Require a non-empty `sentiment_input.csv`. A `missing_comment_detail` audit is a hard gate: keep formal sentiment pending rather than inventing percentages.
5. Use `--run-preparation` to invoke `large-scale-sentiment-analysis/scripts/prepare_text_data.py`, `profile_text_quality.py`, and `make_llm_batches.py`. Preserve volume by keeping duplicates; remove emoji-only rows from the effective sample and retain their audit file.
6. Create stratified seed batches. Cover all subtopics and platforms, plus short comments and different text-length buckets.
7. Let the AI read and label seed rows against `label_schema.md`. Rules may nominate candidates but cannot become truth labels.
8. Validate at least 20-30 reviewed examples per final label when the corpus is large enough and that label plausibly exists. For a genuinely tiny corpus, review every row directly, do not train or claim classifier quality, and disclose the exact per-topic denominator.
9. Train the text classifier, score all prepared comments, and select uncertain, close-margin, sarcasm-like, boundary, and random audit rows.
10. Repeat review and training until the convergence and audit gates pass.
11. Build one final result file covering every collected comment. Classified rows use `in_sentiment_denominator=true`; excluded rows use `false` and provide `exclusion_reason`; unresolved rows remain review blockers.
12. Rerun `run_cwh_sentiment_stage.py --sentiment-results <reviewed.csv>`. It must emit both `sentiment_workbook_summary.json` and `report_comment_handoff.csv`. The latter contains only reviewed, in-window, topic-mapped, traceable comment rows and is the sole domestic-comment entrance to report rendering.
13. Pass `sentiment_workbook_summary.json` and the already accepted standard workbook to `backfill_cwh_sentiment_workbook.ps1`. This post-stage copy changes only the sentiment cells and preserves accepted chart layout. A topic below the configured denominator gate remains blank in the formal percentage cells, but its reviewed comments remain available as sample observations.
14. Rerun CWH with all three artifacts: `--comment-handoff report_comment_handoff.csv --sentiment-results reviewed.csv --sentiment-summary sentiment_workbook_summary.json`. The dashboard must display every qualified comment by system subtopic; the formal report must use representative traceable quotations and gate population-level sentiment wording separately from sample observations.
15. Never finish a full report run after sentiment backfill alone. Regenerate `report_data.json`, Word and HTML from the same comment handoff so Excel, dashboard and report cannot drift apart.

## Result Contract

### Bounded capture and direct-review adapters

Authorized collector response envelopes can be normalized with `cwh_weibo_capture.py` or `cwh_toutiao_capture.py`. These scripts do not log in, export cookies or fetch private data. Weibo login must be explicitly authorized in an isolated host profile; public comment IDs/counts never authorize account actions. Retain raw response files, hashes, parent context, dates and exclusion reasons. Explicitly disclosed automated accounts, emoji-only rows and out-of-window rows do not enter the human-comment denominator. Duplicate captures of an ID are not additional public opinion.

For 1–300 real comments, `cwh_comment_semantics.py --capture <normalized.json> --workbook <accepted.xlsx> --output-dir <stage workspace>` uses `CWH_SEMANTIC_COMMAND_JSON` for one bounded direct review. Scripts validate original comment text against retained raw responses and compile the input, reviewed labels, summary and report handoff. Topic assignment comes from semantic review, not the discovery query or historical seed label. Parent-title-only context must remain explicitly labelled; it is not full article text. Larger corpora keep the preparation/classifier route. Platform coverage is a separate actual collector audit, not a model assertion; a standalone semantic test is not a full pipeline run.

Required key:

- `sample_id`: exact ID from `sentiment_input.csv`.

Required classification fields:

- `label` or `predicted_label`: `positive`, `neutral`, or `negative` for denominator rows.
- `label_source`: `ai_reviewed`, `human_reviewed`, `classifier`, or `active_learning_classifier`.
- `in_sentiment_denominator`: true/false.
- `exclusion_reason`: required when false.
- `confidence` or `prediction_confidence`: recommended.
- `needs_review`: must be false before formal delivery.

## Acceptance

- No raw crawler default labels.
- No unprocessed or unresolved comments.
- Effective denominator greater than zero.
- Positive/neutral/negative percentages use only denominator rows.
- Excluded counts and reasons remain available in `cwh_audit.json` and row-level data.
