# CWH capability matrix

| Module | Current capability | Authority / source |
|---|---|---|
| User input | Accept meeting date or agenda plus one organized workbook or a raw system-export bundle | Exactly two logical user inputs |
| Raw workbook stage | Identify total/child heat exports and overseas/WeChat samples, calculate the documented channel groups, generate the standard workbook and comparison audit, and remain independently testable | Raw monitoring-system files + period metadata |
| Agenda/subevent parsing | Parse the agenda and prefer workbook-defined subevents when present | Agenda + system workbook |
| Event configuration | Preserve system keywords, exclusions, event IDs, and monitoring window | System workbook |
| Overall spread | Read authoritative daily and channel values; reconcile the overseas-news channel from the complete AI-reviewed record universe before final totals | System workbook + overseas review audit |
| Subevent spread | Read overlapping subevent totals; retain system sentiment only as an audit reference | System workbook |
| Internal research plan | Generate topic-specific media, expert, overseas, and public-discussion queries | Parsed subevents and monitoring window |
| Media viewpoints | Research public sources, cluster claims, and retain URLs and source metadata | Agent-reach / public web evidence |
| Public-web supplement | Run the Agent Reach CLI and mcporter packaged in the With application for zero-configuration search and webpage discovery; MediaSpider may call this dependency as a fallback, but does not contain it | Packaged Agent Reach runtime + source registry |
| Netizen discussion | Display every qualified traceable comment by system subtopic in the dashboard and use representative original quotations in Word; never treat post titles or search snippets as comments | `report_comment_handoff.csv` from reviewed comment rows |
| Domestic comment collection | Use MediaSpider Supervisor to collect real comments/replies from the configured domestic allowlist; enforce the monitoring window and exclude XHS plus every foreign platform | MediaSpider raw output + collection audit |
| Sentiment | Run the audited `large-scale-sentiment-analysis` workflow on accepted domestic comments and回灌 by `sample_id`; emit one summary for the Excel denominator gate and one strict handoff for dashboard/report evidence | Accepted domestic comments + audited results + `sentiment_workbook_summary.json` |
| Overseas evidence | Preserve the monitoring workbook's overseas evidence; the current project profile does not crawl foreign social platforms | Monitoring workbook |
| Overseas | Preserve system counts and appendix rows; public research supplements narrative evidence only | System workbook + marked public evidence |
| Hotwords | Preserve system candidates, map them to topics, and create an evidence-corpus visualization | System workbook + qualitative corpus |
| WeChat TOP | Preserve account, title, read count, like count, and link fields | System workbook |
| Excel | Regenerate a mentor-style workbook without changing authoritative values | `cwh_data_workbook.xlsx` |
| Word | Render the fixed departmental structure, reusable wording, charts, appendices, and typography | Formal template |
| HTML dashboard | Render an offline briefing workbench with overview plus four report-aligned work areas, editable generated prose, embedded system charts, appendix tables, and one-click Word/Excel access | `cwh_dashboard.html` |
| Dashboard web entry | Serve the generated HTML on a loopback HTTP address for browser access; never expose a `file:///` link as the user-facing entry | `scripts/serve_dashboard.py` |
| Audit | Check system authority, evidence traceability, missing topics, output completeness, and formal-delivery blockers | `cwh_audit.json` |
| Optional system details | Ingest a separate detail export when one exists, but never require it from the user | Optional compatibility input |
| Domestic comment fallback | When system comment detail is absent and collection is authorized, MediaSpider comments may supply the separate sentiment denominator but never replace or revise system spread totals | Explicit domestic-comment stage |

## Two-input contract

The normal workflow requires only:

1. The State Council executive meeting date or full agenda.
2. One organized department monitoring-system workbook or a bundle/directory of raw monitoring-system exports.

The skill must not ask the user for a third detail file. When the second input is raw, it first creates the standard summary workbook and its independent audit. It then builds an internal research plan, gathers public qualitative evidence, creates an `analysis_bundle.json`, and generates the formal Word report, mentor-style Excel workbook, self-contained HTML dashboard, charts, appendices, structured data, and audit record when the user requested the report stage.

## Authority boundary

All quantities, platform totals, trend values, subevent totals and overseas counts come from the monitoring workbook. Formal sentiment ratios come from the separate audited comment-level workflow. Public research is used only for media, expert, self-media, overseas narrative, and public-discussion evidence. It must never be added to the system counts.

Only URL-backed wording marked as verified may be quoted as a public post or comment. Unverified discussion may be summarized without quotation marks and must remain distinguishable in the audit data.
