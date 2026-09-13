# CWH report_data.json schema

`report_data.json` is the stable handoff object for the CWH report workflow. The report Markdown, charts, appendices, and future Yuanqi/API responses should be rendered from this object rather than from scattered text snippets.

## Top-level fields

| Field | Type | Meaning |
|---|---|---|
| `version` | string | Schema version. Current value: `0.2`. |
| `generated_at` | string | Local timestamp. |
| `meeting` | object | Meeting date, agenda text, and topic list. |
| `collection` | object | Sample counts, data-source status, generated crawler tasks, and gaps. |
| `system_data` | object | Normalized authoritative monitoring workbook, including event IDs, daily totals, subevents, overseas rows, hotwords, and WeChat TOP. |
| `statistics` | object | Overall counts by platform, source type, region, topic, sentiment, and time. |
| `topic_stats` | array | One row per subtopic for the report table. |
| `viewpoints` | object | Domestic media/self-media viewpoint summaries with evidence samples. |
| `comments` | object | Selected netizen comments and sentiment summary. |
| `hotwords` | array | Candidate hotwords with counts, topic attribution, and example text. |
| `overseas` | object | Overseas reports grouped as repost, interpretation, and hype/risk, plus `public_comments` from traceable overseas social discussion. Media rows and public-discussion rows must remain separate. |
| `appendices` | object | Appendix rows for overseas reports, WeChat/self-media top items, comments, and media samples. |
| `audit` | object | Data gaps, low-confidence items, and manual review checklist. |
| `artifacts` | object | Paths to generated report, dashboard, charts, appendices, data workbook, and task manifests. |

For formal system reports, `analysis_bundle.metadata.evidence_mapping_version` must be `1.0`. The embedded bundle must preserve every domestic article's hashed `source_snapshot` and every formal evidence row's one-to-one `evidence_id` mapping. The delivery directory also contains `domestic_evidence_mapping_audit.json`; a blocked or missing audit prevents archival release.

## Authority rule

When `collection.data_mode` is `system`, quantitative report claims come from `system_data` and the authoritative values copied into `statistics`/`topic_stats`. `samples` are evidence rows and their count must not replace system传播总量.

## Sample object

Normalized samples should use these fields whenever possible:

| Field | Meaning |
|---|---|
| `id` | Stable id from source or generated id. |
| `topic` | Matched CWH subtopic. |
| `platform` | Platform such as `news`, `web`, `wechat`, `weibo`, `douyin`, `xhs`, `bilibili`. |
| `source_type` | `central_media`, `mainstream_media`, `commercial_media`, `self_media`, `netizen`, `overseas_media`, etc. |
| `region` | `domestic` or `overseas`. |
| `source` | Media name, account name, or user name. |
| `title` | Title or short comment title. |
| `content` | Main text or comment body. |
| `url` | Source link if available. |
| `published_at` | Published timestamp if available. |
| `spread_count` | Read/play/like/heat count if available. |
| `comment_count` | Comment count if available. |
| `is_comment` | Boolean. |
| `sentiment` | `positive`, `neutral`, `negative`, or `unknown`. |
| `quality_flags` | List of flags such as `low_relevance`, `digest`, `short_comment`, `needs_review`. |

## Report rendering rules

Rendering is deterministic and does not request a model to author deliverable files. `cwh_orchestrator.py` generates Word, Markdown, Excel and the workbench from the same structured report. `generate_dashboard.py` injects a JSON payload into the single `__DASHBOARD_DATA__` slot in `assets/cwh_dashboard_template.html`; the model never rewrites HTML, styles, navigation, cards or export controls during report production. Preserve `analysis_bundle` and its evidence IDs in the payload. Existing system chart images remain authoritative assets. Only an explicit Skill-development task changes templates.

`meeting.chair_name` and `meeting.chair_source` are optional source-backed opening metadata. If either is absent, scripts use a neutral opening without a named chair. Never inherit a person from a historical template. `audit.writing_rules_sha256` records the executable writing-rule revision.

- Main body should not contain hollow placeholders such as `需补充数据`.
- If a required data source is unavailable, put it in `audit.data_gaps` and mention it briefly in the final audit section.
- Evidence-backed claims should cite sample source names or appendix rows.
- Netizen comments should preserve original wording and should not be over-polished.
- Overseas attention should be automatically pre-classified but always marked for manual review.

## Data workbook rendering rules

`artifacts.data_workbook` should point to `cwh_data_workbook.xlsx`. It is the reviewable data package matching the mentor's Excel workflow.

Required sheets:

| Sheet | Purpose |
|---|---|
| `关键词` | Total-event and sub-event keyword/query blocks. |
| `总事件` | Overall daily trend and platform-detail table. |
| `子事件1...子事件N` | One daily trend and platform-detail table per CWH subtopic. |
| `子事件数据汇总` | Subtopic aggregate counts and sentiment ratios. |
| `外媒报道列表` | Overseas report list with sub-event flags. |
| `词云` | Candidate hotwords for word-cloud/chart production. |
| `公众TOP` | WeChat/public-account top articles when available. |

The workbook is generated from `report_data.json`; it must not contain hard-coded sample-report figures.

## Dashboard rendering rules

`artifacts.dashboard` must point to the self-contained `cwh_dashboard.html` generated from this object.

- Render the authoritative totals and system charts from `system_data`, `statistics`, `topic_stats`, and `artifacts.docx_charts`.
- Render qualitative organization from `viewpoints`, `comments`, `hotwords`, `overseas`, and `appendices`.
- Render readiness and evidence coverage from `audit`.
- Keep artifact links relative when the target is in the same output directory, while also exposing Microsoft Office protocol links for Word and Excel.
- Embed data and chart bytes in the HTML. Do not require a web server, CDN, or package installation to view the result.
