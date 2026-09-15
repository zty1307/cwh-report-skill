# Raw Workbook Pipeline Contract

Use this contract only for the independently testable stage that converts raw monitoring-system exports into the organized CWH summary workbook consumed by the report stage.

## Boundary

- Read raw exports and meeting metadata.
- Generate the standard workbook, comparison audit, normalized JSON and sheet previews.
- Do not invoke research, sentiment, formal Word or HTML dashboard code.
- Do not modify raw files, the optional manual baseline, report templates or dashboard assets.
- Treat the optional baseline as a post-generation acceptance reference only.

## Input Classification

Skip this stage when one workbook already contains `关键词`、`总事件`、`子事件1...N` and `子事件数据汇总`.

Run this stage when a directory contains a raw bundle identifiable by configurable filename and sheet aliases, including:

- one total-event heat-analysis workbook;
- numbered child-event heat-analysis workbooks;
- one overseas-news latest-sample workbook;
- one public-article hottest-sample workbook.

Do not trust the worksheet's advertised used range as the row count. Some monitoring exports contain a stale `A1` dimension while the underlying worksheet XML contains thousands of populated rows. In read-only ingestion, reset/recalculate dimensions (or inspect the XML bounds) before classifying a sheet as empty, and write both the advertised and effective dimensions to the audit.

Use `config/raw_workbook_mapping.json` for filename recognition, sheet aliases, field aliases, channel groups and semantic-filter patterns. Never hard-code a meeting date, topic title or period value into the program.

Preserve channel scope as well as quantities. The default raw `domestic_news` aggregate is labelled 境内新闻, not automatically certified as 境内主流媒体; broader configured groupings use 境内媒体. Keep canonical calculation keys unchanged and pass the explicit channel label through standard-workbook ingestion, formal prose/table and dashboard. A supplied standard workbook explicitly labelled 境内主流媒体 retains that input scope. Do not migrate a numerical difference into APP or another bucket merely to match a benchmark; source-level reclassification needs a separately auditable rule.

## Metadata

Raw heat-analysis exports do not reliably contain the meeting and child-topic titles. Create one period-specific JSON file outside the reusable program:

```json
{
  "meeting_title": "会议日期及名称",
  "event_sheet_title": "总事件表标题",
  "topic_titles": ["子议题一", "子议题二"],
  "topic_aliases": [["议题一语义别名"], ["议题二语义别名"]]
}
```

Require the number of `topic_titles` and `topic_aliases` groups to equal the number of child-event raw workbooks. Keep aliases broad enough to prepare genuine agenda-related overseas and WeChat candidates. Aliases are hints, not final semantic judgments: only a complete AI review may alter the raw overseas-news aggregate.

Record `topic_mapping_basis` for the identity of each original statistical group. A meeting agenda lists decisions, not the identities of numbered monitoring queries: never infer a child query title solely from agenda order, filename sorting or similar totals. Preserve combined statistical groups even when prose discusses their mechanisms separately; do not omit an agenda because another group was split. If the basis explicitly says inferred/assumed/推断/猜测 or `topic_mapping_status` is unconfirmed, obtain actual source identity or user confirmation before rendering factual labels. The host rejects known-unconfirmed mappings early (`topic_mapping_requires_confirmation`); after genuine confirmation record `topic_mapping_confirmed: true`, a confirmed status and the actual basis. Legacy explicit title metadata remains compatible but is not independently certified. Historical baseline numbers are acceptance references, not a way to manufacture missing query identities or channel counts.

When post-generation review exposes a wrongly prepared test mapping and the user-provided current baseline explicitly identifies those statistical groups, a separate benchmark-assisted correction run may use only that stated group identity/order. Record the baseline path/hash, exact identity-only scope and `topic_mapping_status: baseline_cross_checked`; do not label it user-confirmed or blind evaluation. Do not import baseline counts, sentiment, viewpoints, comments or overseas evidence. This development correction is not an identity-inference method for production without a baseline; retain the original failed/mislabeled run unchanged.

## Standalone Execution

```powershell
python cwh-report-skill/scripts/raw_system_workbook_pipeline.py `
  --input-dir "D:\path\原始数据" `
  --metadata outputs/cwh_raw_workbook/run_metadata.json `
  --config cwh-report-skill/config/raw_workbook_mapping.json `
  --output outputs/cwh_raw_workbook/CWH舆情情况_自动生成.xlsx `
  --audit outputs/cwh_raw_workbook/comparison_audit.md `
  --baseline "D:\path\人工基准表.xlsx"
```

`--config` defaults to the bundled mapping. `--baseline` is optional. Node.js is auto-detected from `PATH` or `CWH_NODE_PATH`. Make `@oai/artifact-tool` available through the skill's `node_modules` or `NODE_PATH` before building the workbook.

The first invocation also emits `run/hotword_review_packet.json` and stops before workbook generation. The active model must review its candidates and document excerpts, supplement missing clean terms from that evidence, and create `run/hotword_ai_review.json`. Rerun with `--hotword-review path\to\hotword_ai_review.json`.

Minimum hotword review shape:

```json
{
  "review_method": "ai_semantic_review",
  "second_pass_completed": true,
  "selected": [
    {
      "term": "政策工具",
      "topic_hits": [1],
      "evidence_tier": "core",
      "semantic_type": "policy_tool",
      "standalone_topic_label": true,
      "evidence_aliases": ["原文中的完整证据措辞"],
      "selection_reason": "两家独立来源均将其作为议题重点",
      "ai_representativeness": "高"
    }
  ]
}
```

Core terms need two independent documents; supporting terms need one traceable high-quality document. Every term must pass a standalone topic-label test and declare one of the allowed semantic types. Remove generic verbs, fragments, pure locations, project sites, people, dates, organizations, outlets, official boilerplate, meeting actions and unqualified carrier nouns such as `召开`、`投资`、`项目`. A geographic word is eligible only when it forms a complete policy, governance or sector concept rather than naming where an individual project sits. Preserve the full verbatim source phrase in `evidence_aliases` when AI shortens it into a human-report-style display label. Merge synonyms and complete a second topic-coverage/noise pass. If fewer than the configured minimum survive, AI must propose more terms from `document_samples`. Never fill the count with deterministic n-grams.

Keep the AI prompt independent of any historical meeting. Supply only semantic-type definitions, accepted/rejected construction patterns, the current run's dynamic `topics`, current candidates and current evidence excerpts. Never include accepted terms from a previous report, a hard-coded topic count, a meeting date or a period-specific topic example as review guidance.

The first run emits `run/overseas_review_packet.json`. Complete its AI semantic review and rerun with `--overseas-review path\to\overseas_ai_review.json` before formal delivery. The review file is an internal workflow artifact, not a third user input.

Minimum review shape:

```json
{
  "review_method": "ai_semantic_review",
  "items": [
    {
      "record_id": "system_raw:2:...",
      "decision": "include",
      "publisher_class": "overseas_origin_media",
      "topic_hits": [1, 3],
      "review_reason": "标题和正文均以本次会议及相关议题为主体",
      "classification_confidence": 0.96,
      "content_type": "factual",
      "ai_report_category": "事实性报道",
      "source_cn_simplified": "境外媒体中文名",
      "title_cn_simplified": "经审核的简体中文标题",
      "summary_cn_simplified": "解读性报道须填写可核验的简体中文分析摘要；事实性报道可留空",
      "interpretive_verified": false
    }
  ],
  "supplemental_rows": []
}
```

`items` must cover every packet row. `supplemental_rows` uses the same decision fields and also carries source, title, URL, publication time and content.

## Authority and Calculations

- Preserve every non-overseas daily value from the identified raw heat-analysis workbook.
- Calculate total-event and child-event summaries using the configured channel groups.
- Preserve child queries independently; never deduplicate across child topics and never force child totals to equal the total event.
- Review every raw overseas-news row with AI using title plus body, not keyword rules alone. Require an explicit include/exclude decision, reason, publisher class, confidence and all applicable topic hits.
- The raw monitoring Excel is the primary overseas evidence source. First read every candidate row's title, full body and stored link, then preserve every accepted row's AI report category, reason, confidence and reviewed Simplified Chinese source/title/summary in `外媒报道列表`. After this full-text review, mandatory supplemental search is a separate discovery pass: record queries, duplicates, exclusions, access failures and saturation; reconcile every new in-window eligible report back into the standard workbook before formal rendering. Supplemental search never substitutes for classifying interpretation already present in Excel. Missing classification blocks downstream formal rendering instead of defaulting to factual.
- Build one deduplicated in-window overseas-media universe from reviewed system rows and reviewed supplemental news. Count both `overseas_origin_media` and `mainland_outward_media` in the overseas channel; write only `overseas_origin_media` to the formal appendix.
- Deduplicate exact/canonical URLs and repeated rows from the same publisher. Retain the same report when it appears through different publishers because the formal count includes转载.
- Replace the total-event `overseas_news` daily values with reviewed unique-report counts, derive each child event's overseas daily values from reviewed multi-topic hits, and recalculate dependent totals. Never alter another channel during this reconciliation.
- Count a report once in the total event even when it hits several subtopics. Child-event overseas totals may therefore sum above the total-event overseas count.
- If the AI review is absent or incomplete, preserve the raw aggregate, mark `ai_review_required`, and do not treat preliminary script hints as formal selection.
- Use public-article detail samples for appendix/ranking, hotword evidence and a separate full domestic-viewpoint evidence corpus; they never replace system aggregate counts.
- Build `run/public_article_evidence.json` before ranking. It must scan every effective raw row without a read-count or TOP-N ceiling, retain the full article body and trace fields, map all applicable agenda topics, and preserve each include/duplicate/exclude decision. Deduplicate only exact/canonical URLs or exact full-text repeats; low rank, low read count or same broad publisher family is not a viewpoint-evidence exclusion.
- `公众TOP` and `public_article_evidence` have different contracts. The former ranks distinct publisher families for the appendix; the latter supplies the complete raw qualitative corpus to domestic viewpoint research. Never hand only the TOP review batch or final TOP10 to the analysis stage.
- Review each retained article for all speaking subjects. When one body quotes several named experts or institutions, emit separately attributable evidence rows for every substantive voice; do not keep only the first name and do not merge them into a generic media summary.
- Build `公众TOP` as a distinct-publisher-family ranking. AI must read and decide every candidate at the maximum-read cutoff before the final TOP N is selected; when the cutoff pool cannot supply N eligible distinct publisher families, expand the reviewed batch. Exclude multi-news roundups and articles where the meeting is only a minor market catalyst. First normalize exact account names, then apply only explicit reviewed aliases from `public_publisher_families`; never use fuzzy name similarity to merge unrelated accounts. Retain the highest-read eligible article from each family, then sort representatives by read count; when the system caps multiple rows at the same maximum such as `100000+`, use the system `在看`/recommend count as the deterministic secondary key. A short headline that omits a fixed meeting phrase is eligible when its body explicitly identifies this meeting and substantively covers a current agenda; account authority and topic overlap alone are insufficient. Never take the first N articles and deduplicate afterward. Return fewer than N rows only when fewer than N valid distinct families remain, and preserve every reviewed inclusion/exclusion reason in the audit.
- Audit export cutoffs before comparing totals. Record each raw workbook's export timestamp or filesystem timestamp, flag inconsistent cutoffs, and never explain a historical total mismatch by inventing channel reclassification. Aggregate channel fields may be regrouped only by the configured semantic mapping; source-level reclassification requires source-level rows plus an auditable mapping and cannot be reconstructed from aggregate totals alone.
- Keep sentiment as `待分析` until audited comment-level sentiment results exist.

## Acceptance

Require all expected sheets in the configured order, formula-error count zero, every sheet rendered, and the expected native charts present. Workbook generation additionally requires `hotwords.status=ai_review_complete`, `second_pass_completed=true`, the configured minimum accepted term count and evidence on every term. Formal acceptance also requires `overseas.status=ai_review_complete`, complete row coverage, daily reconciliation, `overseas counted total >= formal appendix rows`, and a nonempty audited `public_article_evidence` corpus whenever the raw public-article workbook contains eligible rows. Record advertised/effective sheet dimensions, field mapping, channel formulas, every AI decision, count deltas, baseline differences and unresolved rules in the audit artifacts.

Run the stage tests independently:

```powershell
python -m unittest discover `
  -s cwh-report-skill/tests `
  -p "test_raw_system_workbook_pipeline.py" `
  -v
```

For a new batch, set `CWH_RAW_TEST_DIR` to its raw directory or add a separate fixture-specific test. Do not weaken production logic merely to match a historical manual workbook.

## Hotword and Word-cloud Contract

The raw stage owns hotword generation when the source bundle contains public-article samples:

1. Deduplicate relevant documents before scoring so repeated URLs or same-title syndication do not inflate heat.
2. Build candidates separately by subtopic from traceable domestic media/self-media rows and verified original comments. Retain independent-document count, title/lead hits, source-type diversity, verified-comment count, representative titles and URLs.
3. Ask AI to normalize candidates into concise 2-8 character nouns or policy phrases, merge synonyms, and remove fragments, generic words, outlet/person/date noise and unsupported abstractions. Core terms need two independent rows; a supporting term may remain with one traceable row only after explicit AI review.
4. Require a separate `hotword_ai_review.json`; a list embedded in metadata does not prove AI review. Rank accepted terms as 30% independent-sample coverage, 20% title/lead prominence, 15% source diversity, 15% AI semantic representativeness, 10% verified-comment mentions and 10% subtopic balance. If comments are unavailable, redistribute their share proportionally. The review file is internal, never a third user input.
5. Run a second AI audit for missing topics, no-evidence terms, synonym duplication, official-copy dominance, collection noise and misleading headline sizes, and require `second_pass_completed=true`. If too few clean terms remain, AI must supplement from traceable `document_samples`. Without a complete review, emit the review packet and stop before rendering the word cloud or workbook; never use deterministic fallback words in a formal result.
6. Render a transparent PNG with the configured shape, font, text color and rotation, crop it to visible content, and write the selected terms to `词云!A2:A...`.
7. Embed the exact PNG bytes into the workbook and preserve `run/hotword_audit.json` so the report stage can reuse the workbook asset byte-for-byte.
8. Use the bundled cloud silhouette by default with transparent background, `#0D4E6D` text, `-15` degree rotation, PNG output and no white margin. The default font is `assets/fonts/TencentFont.otf`, resolved relative to the Skill directory; no system-font installation or period-specific directory is required. The package includes the font on the basis of the project owner's confirmed distribution permission, recorded in `assets/fonts/TENCENT-FONT-NOTICE.md`. Run metadata `wordcloud.font_path` or the process-local `CWH_CJK_FONT` may explicitly override it. Noto is a fallback, not the Tencent typeface. Preserve the actual resolved font in the render audit; do not claim a fallback matches the reference font.
9. Use the approved 微词云 image as a drawing-style benchmark, never as reusable report pixels. Use `assets/wordcloud_cloud_shape.ai` as the authoritative cloud outline and its bundled transparent PNG as the runtime mask. Restore the approved July 19 layout: place 42 unique primary terms once, then add 247 small background repeats for 289 total placements. Use a 22–150 primary-font range with exponent `3.0`. Derive repeat sizes independently from the 28–96 reference range with twelve descending scales and keep every repeat at or below 36 px. Use seed `20260710`; route early repeat attempts toward the mask edge, preserve `#0D4E6D`, Tencent font, transparent background, `-15°` word rotation and no white margin. Allow run metadata to override the primary scale or total-placement cap, but do not let repeated copies inherit the enlarged primary hierarchy.
10. Reconstruct the drawing method rather than any saved arrangement. Process primary terms by descending weight, test their rotated glyph collision masks from the visual centre outward, and use seeded random fallback positions when needed. For repeated background copies, first seek positions touching the cloud edge band, then use the remaining mask area. Keep the historical font-size-dependent collision buffer (`5` px for sizes at least `18`, `3` px for sizes at least `12`, otherwise `1` px). Record every accepted term, font size, repeat round and position in `hotword_audit.json`; never extract text pixels or coordinates from a benchmark JPG/PNG.

## Report Handoff

For a full report request, pass the generated workbook unchanged to the existing report stage:

```powershell
python cwh-report-skill/scripts/cwh_orchestrator.py `
  --input-file outputs/cwh_agenda.txt `
  --system-workbook outputs/cwh_raw_workbook/CWH舆情情况_自动生成.xlsx `
  --analysis-bundle outputs/cwh_system_report/analysis_bundle.json `
  --hotword-audit outputs/cwh_raw_workbook/run/hotword_audit.json `
  --out-dir outputs/cwh_system_report
```

The report stage requires this AI-complete audit for every system workbook. It rejects missing or incomplete AI review instead of rebuilding formal hotwords from deterministic candidates.

Workbook preview verification imports the generated XLSX once in a single renderer process and renders every declared sheet with the existing ranges. Each sheet still requires a fresh, non-empty PNG; a partial batch or successful process exit alone does not pass verification. This changes transport/runtime overhead, not evidence review, workbook values, or acceptance thresholds.
