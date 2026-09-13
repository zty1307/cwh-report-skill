# CWH formal report rules

These rules are distilled from the mentor-provided formal reports:

- `0701-6月29日国务院CWH舆情情况.doc`
- `0713-7月10日国务院CWH舆情情况.doc`

The formal report must follow this stable structure. Do not invent a new chapter layout unless the user explicitly asks for a non-formal analysis draft.

The machine-readable source of truth is `config/formal_writing_rules.v1.json`. It captures cross-topic patterns rather than facts from one meeting. `scripts/normalize_cwh_analysis.py` assembles viewpoint paragraphs from verified atomic claims; the model does not improvise the final attribution, order or punctuation.

## Typography measured from both mentor reports

- Title: `华文中宋`, 22 pt, bold, centered, no first-line indent.
- Level 1 headings such as `一、舆情传播情况`: `黑体`, 16 pt, not additionally bolded, first-line indent 2 characters.
- Level 2 headings such as `（一）总事件传播情况`: `楷体_GB2312`, 16 pt, bold, first-line indent 2 characters.
- Viewpoint-group headings such as `1.建议……`: `仿宋_GB2312`, 16 pt, bold, first-line indent 2 characters.
- Body: `仿宋_GB2312`, 16 pt, first-line indent 2 characters.
- Subtopic and overseas tables: `微软雅黑`, 11 pt; header rows bold and centered.
- WeChat TOP table: `仿宋`, 12 pt; header rows bold and centered.

Apply these fonts directly to heading runs as well as to paragraph styles. Do not rely only on Word's built-in `Heading 1/2/3` theme fonts, because Word may substitute `+中文标题` or `MS Gothic`.

## Title and lead

Title:

```text
X月X日国务院常务会议舆情综述
```

Opening paragraph:

```text
国务院总理李强X月X日主持召开国务院常务会议，{agenda_topics}。本次国务院常务会议舆情传播情况如下：
```

Use the original agenda wording as much as possible. The number of subtopics is dynamic.

## Fixed sentence library

Use these as stable sentence frames and replace only bracketed values:

```text
本次常务会引发境内外媒体广泛报道，境内外传播总量约{total}条，舆论关注“李强主持召开国务院常务会议 {first_topic}”相关话题。经发酵，舆情热度于{peak_date}达到峰值。
境内主流媒体如人民网、新华网、央视网等均在显著位置刊文，共有相关报道{domestic_count}条。
新媒体中，微信公众平台相关信息{wechat_count}条、微博相关信息{weibo_count}条，视频号相关信息{video_count}条，新闻客户端、论坛等渠道共有相关信息{other_count}条。
境外媒体如{overseas_source_1}、{overseas_source_2}、{overseas_source_3}等予以关注，共有相关报道（含转载）{overseas_count}条。具体主流报道情况见附表。
```

For domestic viewpoints, support both a single-cluster paragraph and a multi-cluster `一是、二是……` pattern. Use `建议、认可、肯定、认为、期待、希望` only when supported by the evidence cluster.

For overseas coverage, first run an AI relevance review and exclude rows that only overlap with an agenda topic but do not report or interpret the meeting. Classify eligible rows by article body, then use the factual lead and a separate interpretive paragraph specified below. Do not number report categories:

```text
数据周期内，境外媒体以事实性报道为主。如{examples}等，少量解读如下：
{reviewed_interpretive_prose}
```

Use this factual lead only when supported by the reviewed category distribution. If there is no interpretation, use `，暂无评论性文章。` instead. Do not force a missing category into the report. Negative wording, criticism or a crawler-supplied tag alone is not proof of `借题炒作/风险解读`.

## 一、舆情传播情况

This chapter has exactly two sub-sections.

### （一）总事件传播情况

Required content:

- Overall domestic and overseas spread volume.
- Main public-opinion focus topic, usually quoted as `“李强主持召开国务院常务会议 {first_topic}等”`.
- Peak date.
- Domestic mainstream media volume.
- WeChat public-account volume.
- Weibo volume.
- Video-account volume.
- News client/forum/other channel volume.
- Overseas report volume.
- End by pointing to the appendix: `具体主流报道情况见附表。`

When true full-volume data is unavailable, use the best collected metric and keep the limitation in `cwh_audit.json`; do not put hollow placeholders such as `需补充数据` in the formal report body.

### （二）子议题传播情况

When the system workbook already contains the trend chart, subtopic-volume chart, or word-cloud image, embed those original assets directly. They are authoritative system outputs. Do not redraw them in a different chart type, color palette, order, unit, or title. Program-generated graphics are only a fallback when the corresponding workbook asset is absent.

Use one table. Required columns:

- 序号
- 标题
- 境内主流媒体
- 新媒体
- 境外媒体
- 总量
- 网民情感：正面 / 中立 / 负面

The table must be generated for all detected subtopics, not hard-coded to four items.
Keep the full system subtopic titles in this table, including action wording such as `听取`、`研究`、`审议通过` and the full policy name. Use 11 pt table text; do not shorten titles merely to make the table fit one page.

## 二、境内舆论情况

This chapter has exactly three sub-sections.

### （一）境内媒体自媒体情况

Organize by subtopic or stable viewpoint group. Use numbered top-level items:

```text
1.建议……
2.认可……
3.肯定……
```

Before writing, build an audited candidate pool from the priority source registry and open-web discovery. The registry is not an allowlist. Follow the selected profile in `research_plan.json`: `bounded_60m` uses grouped lanes, at most 10 queries and 24 full-page fetches per topic, and stops after lane coverage plus one zero-new round or budget exhaustion; `exhaustive` searches individual required sources and requires two zero-new rounds. Keep a decision for every result actually reviewed within scope.

In bounded mode, select the strongest 6-12 independent voices per topic across 2-4 clusters and cap formal prose at 12 voices. Keep additional valid candidates as `formal_use=reserve` with `reserve_reason`; they stay auditable but do not lengthen the report. In exhaustive mode, map every eligible independent voice into prose. Exact mirrors remain duplicate audit records.

Every top-level item must begin with an evidence-supported stance or action verb such as `建议、认可、肯定、认为、期待、希望、支持、呼吁、质疑、担忧`. Remove empty wrappers such as `舆论关注` and do not copy a cluster summary as the heading when it lacks a stance. If a topic genuinely has only factual reporting after research, use the explicit exception `监测期内尚未形成评论性观点` and do not present the factual digest as a viewpoint.

The attitude verb is a conclusion from evidence, not a positivity template. Use `肯定/认可/支持` only when the source itself expresses approval, `建议/期待/呼吁` for proposals, `认为/指出` for analytical judgment, and `质疑/担忧` for criticism or risk. Do not rewrite neutral analysis as praise merely to imitate a historical report.

Inside a viewpoint group, use `一是、二是、三是、四是、五是` when there are multiple viewpoint clusters. The text after every ordinal must pass the same stance-verb gate as the top-level heading; do not write bare conclusions such as `一是宏观政策重在……` or `二是项目建设……`. A purely factual cluster may only use the explicit exceptions `尚未形成评论性观点` or `以事实性报道为主`.

Every claim should include evidence sources such as experts, media, institutions, or public accounts:

```text
某专家称……
某媒体报道称……
微信公众号“某某”称……
```

Avoid unsupported generic wording such as `媒体普遍认为` unless evidence is cited.
Formal Markdown and Word must not append `样本来源：……`、`公开网络补证`、`原始报道汇总` or any link-list paragraph after a viewpoint. Put the verified original link on the corresponding dashboard evidence card and keep source metadata in structured audit data. Formal body prose consists only of concrete attributed claims.
Write every independent voice as `完整机构/职务/姓名+认为/指出/建议+具体观点`; when no named person is available, write `媒体/平台/自媒体账号全名+认为/指出/建议+具体观点`. Prohibit vague aggregation such as `报道汇集刘某、伍某、严某等对……的分析` or `多家媒体关注……`; split genuinely distinct speakers into separate attributed sentences. If several URLs reproduce the same speaker and same claim, render that claim once and keep the other URLs as duplicate audit records.
For a mature multi-source cluster, normally use 2-4 selected independent voices. Each voice receives one complete 45-120-character attributed claim. A substantive agenda normally yields 2-4 clusters; one-cluster and thin-cluster cases need traceable exceptions. Do not compress several sources into an anonymous summary or inflate page count with repeated wording.
The shared executable density gate requires two distinct speaking subjects and at least 120 Chinese characters, or a `thin_cluster_exception` containing non-empty `reason`, `search_evidence` and `reviewed_by`. Both draft validation and final auditing use this rule. The exception is retained in the audit and does not waive the minimum quality of each claim, original-source mapping or independent semantic review. Repeated URLs, repeated speakers and repeated attribution verbs do not increase independent-voice count.
Bold each `一是/二是……` conclusion and the named source plus attribution verb (`某专家认为`、`某媒体报道称`、`微信公众号“某某”称`).

Apply the following source and wording rules to every meeting:

- Within one system subtopic, the same named person or the same media/self-media source should normally appear in only one viewpoint cluster. Merge that source's related observations into one fuller passage, then use independent voices for the remaining clusters. Limited reuse across different subtopics is allowed only when the source makes a separate, directly relevant argument; avoid letting one familiar expert dominate the whole chapter.
- Distinguish the speaking subject exactly. When the publication itself gives analysis or advice, write `某媒体认为/称/建议`. When the article quotes a verified person, write the person's full verified institution, title and name. When the article truly uses an unnamed source, write `某媒体援引业内人士观点称` and retain the review marker. Never invent `某媒体受访专家指出` when the original does not provide a name, and never convert a publication's own editorial judgment into an anonymous expert judgment.
- Use the source passage as the wording anchor. Lightly trim repetition and connect clauses for readability, but preserve the original claim's key nouns, verbs, scope, qualifications, examples and policy mechanism. Do not replace a specific source statement with a broader AI-created causal conclusion.
- Check each speaking subject separately, including several experts quoted by the same article. A single attributed proposition should normally contain about 45-120 Chinese characters of substantive content. A proposition with fewer than 30 Chinese characters fails the formal gate: return to the original passage to include its reasoning, mechanism, condition or example, combine a related passage from the same source, or omit that voice. Do not pad a weak sentence with generic policy language. Do not count noun phrases such as `宏观分析人士` or `政策解读文章` as attribution verbs, and do not merge several short expert statements into one long evidence row to pass the threshold.
- Public-article TOP ranking is not a writing-evidence filter. Before drafting, inspect the complete agenda-relevant raw public-article corpus and all eligible web candidates, regardless of read rank. When one article quotes several named speakers, extract and assess each voice separately. This rule is reusable across meetings and must not be relaxed or narrowed to imitate one benchmark.
- Period prose may cite a public-web page only when its source-page timestamp has been preserved and verified inside the monitoring window. Exclude later pages even when their wording closely matches the desired report; do not backdate them from search snippets or article subject matter.
- If a top-level subtopic has only one mature cluster, write the top-level heading and its evidence paragraph directly. Do not create a lone `一是` without a `二是`.

### （二）网民评论情况

Lead sentence:

```text
网民观点主要围绕{stance_summaries}等方面展开。主要评论如下：
```

Then group representative raw comments:

Search all workbook topics before selection. In `bounded_60m`, use the configured limit of six query executions and 30 retained candidates per topic, then select 2-3 traceable comments for each ready topic. `exhaustive` may continue to saturation. Preserve a topic-by-platform matrix with exclusions and blockers. Formal prose includes only topics with traceable substantive comments.

```text
一是认可……并期待……。网民称，“……”“……”。
二是质疑……并建议……。网民称，“……”“……”。
```

Use real collected comments only. Preserve original wording, with only light formatting cleanup. Keep platform/account/time/link/interaction metadata in structured data and appendices.
Every selected comment must have a completed AI formal-use review. The group heading must summarize the actual stance, expectation, criticism, reason or concrete suggestion shared by the quoted comments. Never fall back to `关注+议题名称`; a missing reviewed heading blocks formal rendering rather than triggering a generic title.
Treat each system agenda/subtopic as one comment group and one numbered item. Put 2-3 coherent representative comments beneath a single AI-reviewed `topic_comment_heading`; do not split different reactions to the same agenda into separate `一是/二是` items.

### （三）热词分布情况

Write one explanatory paragraph, not only a word list:

```text
从热词分布来看，“A”“B”“C”等词位居前列，相关讨论主要聚焦……。“D”“E”等词热度较高，讨论内容集中于……。“F”“G”等词持续热传，讨论重点进一步延伸至……。此外，“H”“I”等词受到关注，相关观点多涉及……。
```

Hotwords must be connected back to public attention points and subtopics.
Follow the ranked wording pattern `位居前列`、`热度较高`、`持续热传`、`受到关注`; introduce lower-ranked remaining topics with `此外`. Vary the second clause among `相关讨论主要聚焦`、`讨论内容集中于`、`讨论重点进一步延伸至`、`相关观点主要讨论` and `相关观点多涉及`. Do not repeat `舆论围绕` for every topic. If the workbook contains a word-cloud picture, use it unchanged.

## 三、境外舆论情况

This chapter has exactly two sub-sections:

```text
（一）境外媒体情况
（二）境外网民评论
```

### （一）境外媒体情况

Required content:

- Start with whether overseas media are mainly factual reposts/reports.
- List representative overseas reports with source and title.
- If there is interpretation or risk framing, write it as a separate paragraph after the factual-report sentence.
- If there is no commentary, use `暂无评论性文章。`

The primary evidence source is the full title and body already contained in the current raw monitoring Excel. Classify every accepted Excel row as factual, interpretive or risk-framed before building the standard workbook, and preserve the classification, reason, confidence and reviewed Simplified Chinese source/title/summary in that workbook. Do not assume interpretation must come from supplemental search, and never silently default an unclassified row to factual. When interpretation exists, the factual paragraph ends `，少量解读如下：` and the next paragraph summarizes a small number of reviewed interpretive reports. Do not number the report categories.

After every existing Excel row and linked body has been read and classified, run a separate supplemental overseas-media search as a required pass. Use MediaSpider Supervisor `grounding` and/or Agent Reach news/web search, retain the full candidate and saturation audit, and keep X、YouTube and other permitted social rows in `（二）境外网民评论`; never mix social posts into the overseas-media appendix. Skip any platform explicitly paused by the user (currently Reddit) and record that scope limitation. A supplemental news report may affect the overseas count only if it was admitted before workbook finalization through the complete AI overseas review, monitoring-window check and cross-source deduplication. The report renderer itself never patches aggregate counts.

### （二）境外网民评论

Then include:

```text
（二）境外网民评论
境外网民对本次国务院常务会议关注度较低，暂无评论性观点。
```

Use the default zero-sample sentence only after a completed non-dry-run foreign public-discussion collection audit shows that no eligible in-window comments were obtained. A reviewed overseas-media list is not proof that social comments were searched. If real overseas netizen comments are collected, replace the default sentence with evidence-backed comment groups. Formal prose treats approved system and supplemental comments alike, without discussing collection route or monitoring-window labels. Write every `一是、二是……` theme in a separate paragraph, omit account IDs, and quote one or two suitable Chinese translations using platform-level attribution. Keep provenance, original language, timestamps and direct URLs in the dashboard and structured audit data.

## 附录

### （一）外媒报道列表（部分）

Required columns:

- 序号
- 来源
- 报道日期
- 超链接标题

List actual overseas-origin media in this partial appendix. Do not include mainland foreign-language editions such as CGTN, 人民网英文版, 新华社海外版, 中国经济网英文版 or 央视网英文版, although they may remain included in the system's overall overseas count. Render titles as clickable blue underlined hyperlinks.
After relevance review, report-category review, Simplified Chinese normalization and story deduplication, select a representative TOP10 across available categories, regions and subtopics. Keep every accepted row in structured evidence and the dashboard. Use fewer than ten only when the complete eligible set genuinely has fewer than ten rows; missing Simplified Chinese fields are a review-stage error, not a reason to shorten the appendix. In the factual lead, use distinct publishers rather than several stories from one outlet. In the interpretive paragraph, synthesize 1-3 materially distinct angles and remove redundant constructions such as `指出，文章认为`; syndications of one angle are supporting distribution evidence, not separate analytical angles.

Formal Word and Markdown use Simplified Chinese only for overseas outlet names, titles, summaries and appendix cells. Traditional Chinese and foreign-language originals remain traceable in structured data and the dashboard. Traditional-to-Simplified normalization must use the complete OpenCC conversion layer rather than a small character blacklist. Foreign-language translation and converted names, policy terms, numbers and meaning require the overseas AI review before formal rendering.

### （二）传播量较大的公众号文章

Rank publisher families rather than raw rows. Normalize exact account names, then apply only the explicit alias groups in `config/raw_workbook_mapping.json`; retain the highest-read relevant item in each family before TOP10 ranking. Never use fuzzy similarity to merge unrelated accounts or automatically group independent programme accounts under a parent broadcaster.

Required table title:

```text
微信公号文章阅读量TOP
```

Required columns:

- 序号
- 账号
- 标题
- 阅读量
- 在看量

Use the department table appearance: dark navy merged title row and column-header row, white header text, a wide title column, and clickable blue underlined article titles. Preserve display values such as `10万+`/`100000+` when the workbook supplies them.

The table must consume the audited `公众TOP` result, not reconstruct relevance from account names or titles. AI reviews the full body for every maximum-read cutoff candidate, excludes mixed-news roundups and minor-catalyst mentions, deduplicates normalized accounts, ranks by read count and uses `在看` as the secondary key for capped ties. A prior human table is a comparison baseline, not an unexplained override of the current auditable ranking.

## Separation of formal report and audit

The formal report body should not contain engineering status blocks such as:

- `正式交付状态`
- `质量门禁`
- `低质量率`
- `目标完成情况`
- internal crawler failure logs

Those belong in `cwh_audit.json` and, if needed, a separate review note.
