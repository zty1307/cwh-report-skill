# CWH formal report rules

These rules combine earlier mentor-report measurements with a comparative review of three unrelated periods (May, early July and late July). Baselines are evaluation material, not production inputs or a source of current facts.

The formal report must follow this stable structure. Do not invent a new chapter layout unless the user explicitly asks for a non-formal analysis draft.

The machine-readable source of truth is `config/formal_writing_rules.v1.json`. It captures cross-topic patterns rather than facts from one meeting. `scripts/normalize_cwh_analysis.py` assembles viewpoint paragraphs from verified atomic claims; the model does not improvise the final attribution, order or punctuation.

An exact statement in a source does not automatically belong to that source's publisher as an independent viewpoint. Pure retelling of meeting requirements remains meeting facts, even if “要” is paraphrased as “需”; use only the identified speaker's additional reasoning. Preserve distinctions between a proposal, a draft passed at the meeting, a published regulation, a local pilot and nationwide implementation. Overseas raw-review and supplemental-search summaries share the configured interpretation rule: policy judgment plus source-supported reasoning, not an article synopsis or review-process explanation. Keep qualifications in full; renderers must not cut a reviewed summary at an arbitrary character boundary.

## Typography retained from the earlier measured mentor reports

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
X月X日召开的国务院常务会议，{agenda_topics}。本次国务院常务会议舆情传播情况如下：
```

Use the original agenda wording as much as possible. The number of subtopics is dynamic. Only an explicit `meeting.chair_name` and its `meeting.chair_source` permit the source-backed chair variant from the configuration; never default to a historical person. Word and Markdown call the same opening helper.

## Fixed sentence library

Use these as stable sentence frames and replace only bracketed values:

```text
监测期内，相关信息传播总量约{total}条。{supported_peak_sentence}
境内主流媒体共有相关报道{domestic_count}条。
新媒体中，微信公众平台相关信息{wechat_count}条、微博相关信息{weibo_count}条，视频号相关信息{video_count}条，新闻客户端、论坛等渠道共有相关信息{other_count}条。
境外媒体共有相关报道（含转载）{overseas_count}条。{supported_source_examples}
```

The renderer fills these frames from workbook facts. Include a peak only with dated nonzero trend observations and source examples only from actual accepted rows. Never insert assumed prominent placement, broad attention, fixed publishers or a chair into these frames. For domestic viewpoints, support both a single-cluster paragraph and a multi-cluster `一是、二是……` pattern. Use the configured stance verbs only when supported by the evidence cluster.

For overseas coverage, first run an AI relevance review and exclude rows that only overlap with an agenda topic but do not report or interpret the meeting. Classify eligible rows by article body, then use the factual lead and a separate interpretive paragraph specified below. Do not number report categories:

```text
数据周期内，境外媒体以事实性报道为主。如{examples}等，少量解读如下：
{reviewed_interpretive_prose}
```

Use this majority lead only when factual reports exceed half of the eligible reviewed rows. Mixed coverage instead uses `境外媒体报道中包括事实性报道` and `相关解读如下`. If there is no interpretation, use `，暂无评论性文章。` instead. Do not force a missing category into the report. Negative wording, criticism or a crawler-supplied tag alone is not proof of `借题炒作/风险解读`.

## 一、舆情传播情况

This chapter has exactly two sub-sections.

### （一）总事件传播情况

Required content:

- Overall domestic and overseas spread volume.
- Any main focus statement must be grounded in the current evidence, never a fixed name or quoted historical title.
- Peak date only when supported by dated nonzero workbook trend data.
- Domestic mainstream media volume.
- WeChat public-account volume.
- Weibo volume.
- Video-account volume.
- News client/forum/other channel volume.
- Overseas report volume.
- End by pointing to the appendix: `具体主流报道情况见附表。`

Numerical propagation facts must use the monitoring workbook's scope. Missing required workbook totals are a blocker; do not replace full-volume counts with a search sample. Keep limitations in `cwh_audit.json`; do not put hollow placeholders such as `需补充数据` in the formal report body.

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

Before writing, build an audited candidate pool from the priority source registry and open-web discovery. The registry is not an allowlist. Follow the selected profile in `research_plan.json`: both bounded profiles use grouped lanes and at most 10 queries per topic; full-page limits are 18 for `bounded_40m` and 24 for `bounded_60m`. Stop after lane coverage plus one zero-new round or budget exhaustion; `exhaustive` searches individual required sources and requires two zero-new rounds. Keep a decision for every result actually reviewed within scope. Caps are limits, not mandatory work quotas.

In bounded mode, select the strongest 6-12 independent voices per topic and cap formal prose at 12 voices. Usually use 2-4 clusters; genuinely distinct supported judgments may justify 5-6, without increasing the voice cap or inventing categories. Keep additional valid candidates as `formal_use=reserve` with `reserve_reason`; they stay auditable but do not lengthen the report. In exhaustive mode, map every eligible independent voice into prose. Exact mirrors remain duplicate audit records.

Normal interpretive headings begin with an evidence-supported stance or action verb such as `建议、认可、肯定、认为、期待、希望、支持、呼吁、质疑、担忧`. Remove empty wrappers such as `舆论关注` and do not use the first cluster's judgment in place of the full policy scope. If a topic lacks independently interpretable evidence, keep its original topic heading and the configured available-content gap notice, not a factual digest disguised as a viewpoint. When current host-recompiled heading review rejects a proposed title, its neutral topic/report fallback is allowed for available-content delivery; it does not certify a clear interpretive heading or erase outstanding strict writing-quality issues.

The attitude verb is a conclusion from evidence, not a positivity template. Use `肯定/认可/支持` only when the source itself expresses approval, `建议/期待/呼吁` for proposals, `认为/指出` for analytical judgment, and `质疑/担忧` for criticism or risk. Do not rewrite neutral analysis as praise merely to imitate a historical report.

Use the configured `viewpoint.selection_rule` before freezing claims: retain different substantive judgments actually present in the read sources, rather than letting several broad-meaning statements crowd out distinct mechanisms, conditions, risk boundaries or proposals. These are comparison dimensions, not mandatory topic columns. One article can provide multiple independently attributed voices. A cluster must have a genuinely shared judgment; different mechanisms cannot acquire the first speaker's causal chain merely by sharing a policy topic. `viewpoint.heading_support_rule` applies in the author and independent heading review, without an extra whole-report rewriting pass.

The common writing unit across baselines is a concrete judgment with its source-supported reason, mechanism, condition or suggestion, not a report introduction. Use `viewpoint.claim_composition_rule` and `viewpoint.cluster_structure_rule` in both author transports. Retain specific policy objects, implementation actors and effect boundaries; do not compress actual methods into abstract phrases such as “improve mechanisms”. Suggestions remain suggestions; pending drafts remain pending. Order clusters for understanding, not by outlet class. Do not inherit baseline dates, ratios, prominent-placement assertions, fixed expert names, positive sentiment, or weaknesses such as rhetorical slogans. Different comment reactions may coexist within a topic; the current grouping contract is not inferred from one baseline's numbered count.

Inside a viewpoint group, use dynamically generated `一是、二是……` when there are multiple viewpoint clusters; there is no fixed five- or eight-group truncation. Normal interpretive cluster headings use the same source-grounded stance rule as the top-level heading; do not write a bare factual deployment as an independent judgment. A host-audited neutral fallback can preserve available content after rejected heading review, but remains an unresolved writing-quality issue, not a certified common judgment. Pure meeting-action facts do not qualify as independent interpretive voices.

Every claim should include evidence sources such as experts, media, institutions, or public accounts:

```text
某专家称……
某媒体报道称……
微信公众号“某某”称……
```

Avoid unsupported generic wording such as `媒体普遍认为` unless evidence is cited.
Formal Markdown and Word must not append `样本来源：……`、`公开网络补证`、`原始报道汇总` or any link-list paragraph after a viewpoint. Put the verified original link on the corresponding dashboard evidence card and keep source metadata in structured audit data. Formal body prose consists only of concrete attributed claims.
Write every independent voice as `完整机构/职务/姓名+认为/指出/建议+具体观点`; when no named person is available, write `媒体/平台/自媒体账号全名+认为/指出/建议+具体观点`. Prohibit vague aggregation such as `报道汇集刘某、伍某、严某等对……的分析` or `多家媒体关注……`; split genuinely distinct speakers into separate attributed sentences. If several URLs reproduce the same speaker and same claim, render that claim once and keep the other URLs as duplicate audit records.

For self-media, the formal display name includes the platform type. Derive it from the evidence URL when possible: `微信公众号“账号”称`、`头条号“账号”称`、`百家号“账号”称`、`微博账号“账号”称`; if the platform cannot be determined, use `自媒体账号“账号”称`. Keep the raw account name unchanged in evidence data. The model may provide a source-supported attribution verb, while the deterministic fallback uses `认为` for named people and `称` for media/self-media, avoiding a mechanical wall of `认为` without inventing stronger approval or criticism.

Headings are editorial conclusions, not stitched summaries. A top-level viewpoint heading should normally contain 12-26 Chinese characters and a cluster heading 10-24. Each heading expresses one central judgment; do not join different clusters with `并/与/及`. Choose `认可、肯定、建议、期待、希望、支持、质疑、担忧、强调、认为` according to the evidence. Variation is desirable only when the source stance supports it; never turn neutral analysis into approval merely to vary the verb.
For a mature multi-source cluster, normally use 2-4 selected independent voices. Each voice receives one complete 45-120-character attributed claim. Cluster count follows the configured structure rule, not a fixed four-angle ceiling; one-cluster and thin-cluster cases need traceable exceptions. Do not compress several sources into an anonymous summary or inflate page count with repeated wording.
The shared executable density gate requires two distinct speaking subjects and at least 120 Chinese characters, or a `thin_cluster_exception` containing non-empty `reason`, `search_evidence` and `reviewed_by`. Both draft validation and final auditing use this rule. The exception is retained in the audit and does not waive the minimum quality of each claim, original-source mapping or independent semantic review. Repeated URLs, repeated speakers and repeated attribution verbs do not increase independent-voice count.
Bold each `一是/二是……` conclusion and the named source plus attribution verb (`某专家认为`、`某媒体报道称`、`微信公众号“某某”称`).

Apply the following source and wording rules to every meeting:

- Within one system subtopic, the same named person or the same media/self-media source should normally appear in only one viewpoint cluster. The author selects its most substantive, source-supported complete claim before freezing and independent review; the host never merges reserve claims or changes frozen meanings to create a fuller passage. Limited reuse across different subtopics is allowed only when the source makes a separate, directly relevant argument; avoid letting one familiar expert dominate the whole chapter.
- Distinguish the speaking subject exactly. When the publication itself gives analysis or advice, write `某媒体认为/称/建议`. When the article quotes a verified person, write the person's full verified institution, title and name. When the article truly uses an unnamed source, write `某媒体援引业内人士观点称` and retain the review marker. Never invent `某媒体受访专家指出` when the original does not provide a name, and never convert a publication's own editorial judgment into an anonymous expert judgment.
- Use the source passage as the wording anchor. Lightly trim repetition and connect clauses for readability, but preserve the original claim's key nouns, verbs, scope, qualifications, examples and policy mechanism. Do not replace a specific source statement with a broader AI-created causal conclusion.
- Check each speaking subject separately, including several experts quoted by the same article. A single attributed proposition should normally contain about 45-120 Chinese characters of substantive content. A proposition with fewer than 30 Chinese characters fails the formal gate: return to the original passage to include its reasoning, mechanism, condition or example, combine a related passage from the same source, or omit that voice. Do not pad a weak sentence with generic policy language. Do not count noun phrases such as `宏观分析人士` or `政策解读文章` as attribution verbs, and do not merge several short expert statements into one long evidence row to pass the threshold.
- Public-article TOP ranking is not a writing-evidence filter. Use the complete controller corpus index to choose bounded full-text reads regardless of appendix read rank; retain unread IDs as deferred, not reviewed or excluded. Exhaustive mode reads the entire corpus. When one article quotes several named speakers, extract and assess each voice separately. This rule is reusable across meetings and must not be relaxed or narrowed to imitate one benchmark.
- Prefer named experts, professional institutions and media judgments that explain a policy mechanism, condition, effect boundary or concrete suggestion. Self-media remains eligible, but exclude commercial self-promotion for its own company/product, tangential promotion of an activity or service, and text whose substance is only a slogan, pun, metaphor or generic growth forecast. These are editorial-use exclusions, not deletions from the evidence pool.
- Tangential promotion, market-only pitches and slogan-only reasoning require semantic assessment of actual substance. Historical catchphrases are not general-purpose exclusion regexes. Financial or consumption analysis with a specific policy mechanism remains eligible; a slogan embedded in genuine reasoning does not by itself invalidate the entire claim.
- Period prose may cite a public-web page only when its source-page timestamp has been preserved and verified inside the monitoring window. Exclude later pages even when their wording closely matches the desired report; do not backdate them from search snippets or article subject matter.
- If a top-level subtopic has only one mature cluster, write the top-level heading and its evidence paragraph directly. Do not create a lone `一是` without a `二是`.

### （二）网民评论情况

Lead sentence:

```text
网民观点主要围绕{stance_summaries}等方面展开。主要评论如下：
```

The lead uses the first complete clause of each reviewed group heading. The configured 22-character length is an authoring recommendation, never a renderer cutoff: do not sever a word to meet it. Keep the full reviewed heading in the numbered body item. Selection uses the shared `comments.selection_quality_rule`: a long abstract endorsement is not automatically a substantive quotation. Rejecting it for formal selection must not change the frozen sentiment label or denominator; never invent a specific heading to conceal an empty original judgment.

The compiled comment host independently reviews only selected original quotations and their headings in a fresh serial context, within the existing stage clock (reserve up to 45 seconds, no parallel agent). It cannot relabel, rewrite or add comments. A rejected or uncompleted selection remains in the audit and sentiment corpus but not the formal quotations; available-content delivery continues with the gap marked. Empty selection skips this call.

Bounded collection reviews up to the configured 30 already captured rows per topic and 300 overall, rather than a per-topic cap below the unchanged 20-effective-comment percentage gate. No additional collection round is implied. All omitted rows remain auditable as deferred by sampling, not unrelated. A cap is not a quota: never invent comments, force labels or lower the readiness denominator. Describe sentiment as applying to the reviewed collected-comment sample, not the entire population.

Then group representative raw comments:

Search all workbook topics before selection. Use the configured per-topic query limit: four for `bounded_40m`, six for `bounded_60m`; both retain at most 30 candidates, then select 2-3 traceable comments for each ready topic. `exhaustive` may continue to saturation. Preserve a topic-by-platform matrix with exclusions and blockers. Formal prose includes only topics with traceable substantive comments.

```text
一是认可……并期待……。网民称，“……”“……”。
二是质疑……并建议……。网民称，“……”“……”。
```

Use real collected comments only. Preserve original wording, with only light formatting cleanup. Keep platform/account/time/link/interaction metadata in structured data and appendices.
Every selected comment must have a completed AI formal-use review. The group heading must summarize the actual stance, expectation, criticism, reason or concrete suggestion shared by the quoted comments. Never fall back to `关注+议题名称`; a missing reviewed heading blocks formal rendering rather than triggering a generic title.
Apply `comments.heading_summary_rule`: use a natural sentence about the actual object and opinion, not an abstract noun string copied from the quote with an added attitude verb. A genuine comment can remain in the sentiment denominator without being a suitable formal quotation. Preserve the original quote exactly; easier-to-read headings do not permit rewriting it.
Treat each system agenda/subtopic as one comment group and one numbered item. Put 2-3 coherent representative comments beneath a single AI-reviewed `topic_comment_heading`; do not split different reactions to the same agenda into separate `一是/二是` items.

### （三）热词分布情况

Write one explanatory paragraph, not only a word list:

```text
从热词分布来看，“A”“B”“C”等词主要涉及{议题甲}，相关观点认为{已审核判断}。“D”“E”等词主要涉及{议题乙}，相关观点建议{已审核建议}。此外，“F”“G”等词主要涉及{议题丙}，相关观点多涉及{有依据的讨论对象}。
```

Hotwords must be connected back to public attention points and subtopics.
Use the neutral configured word-group frame by default. `位居前列/热度较高` requires actual term-frequency comparison, and `持续热传` requires actual temporal term evidence; neither follows from topic propagation order or cloud layout. Historical report phrasing is not that evidence. Link only reviewed judgments using `相关观点`, without implying population-wide consensus. If the workbook contains a word-cloud picture, use it unchanged.
When the reviewed focus already starts with a stance verb, write `相关观点认为/建议/期待……`; do not produce malformed combinations such as `主要聚焦认为……` or infer population-wide consensus.

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

An interpretive summary contains only the materially additional impact, mechanism, risk or evaluation found in the article. Do not recap the meeting agenda and do not write meta-summaries such as `报道……并引述……解读……`.

The primary evidence source is the full title and body already contained in the current raw monitoring Excel. Classify every accepted Excel row as factual, interpretive or risk-framed before building the standard workbook, and preserve the classification, reason, confidence and reviewed Simplified Chinese source/title/summary in that workbook. Do not assume interpretation must come from supplemental search, and never silently default an unclassified row to factual. When interpretation exists, use the distribution-dependent transition above and summarize reviewed interpretive reports in the next paragraph. Do not number the report categories.

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

For relevance, distinguish policy-focused reporting from incidental mentions. A story may focus on the meeting itself or a concrete decision and its direct policy effects. A market roundup whose main subject is price movements or unrelated news is not eligible merely because it cites one meeting decision as a catalyst. Conversely, finance reporting is not categorically excluded when its full-text main line genuinely concerns that decision. The review reason must state this relationship; genre, keyword hits and historical appendix inclusion alone are not proof of eligibility.

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

Independent compiled review also receives topic and cluster headings, linked to their own evidence IDs. It checks stance, effects versus proposals, scope, conditions and repetitive cluster judgments. Certified replacements are display-only: the host keeps the original headings, actual reviewer run, rationale, supporting IDs and input digest in `research_audit.heading_quality`. Word and workbench use a replacement only while its supporting claims remain independently supported and the audit matches current inputs. Missing, uncertain, malformed or stale heading review produces a quality warning, never a fabricated conclusion or a reason to withhold available files. Explicitly rejected headings without a certified replacement use a neutral topic/report label, not the rejected judgment. Certified factual headings remain neutral instead of gaining an invented positive stance. Expert judgments may be summarized accurately without requiring the exact attribution verb in the source, but factual announcements are not praise. The main check shares the existing reviewer call; overlong headings and clear repetition or multi-center style faults share at most one compact repair call of at most 45 seconds when budget remains. Preserve actual host-run provenance, including prior actual repair runs in an isolated replay; never accept model-invented run IDs. No second full review or extra agent is required.

Filter only exact procedural-only comment phrases configured in `comments.procedural_only_texts` before semantic review. Retain the original text, timestamp, raw pointer and exclusion reason; a substantive comment containing the same words is not removed. Discovery quotas count nonprocedural candidates, not empty forwarding actions. Retain successful zero-result API response bodies and distinguish API-level errors from genuine zero results; neither proves that the topic has no public discussion. Unreviewed or excluded responses never enter the sentiment denominator.

Comment review receives `formal_quote_allowed` and `formal_quote_chars` calculated with the final renderer's exact configured length/format rule. Formatting eligibility is not a semantic verdict or a reason to remove a genuine opinion from the sentiment denominator; ineligible text cannot be shortened or rewritten to evade the limit. Specific neutral questions about applicability, execution or policy meaning can be representative formal quotes. Their headings use inquiry/clarification language, not invented opposition, policy defects or population-wide attention. Distinguish captured rows, sentiment-denominator rows, model-selected formal quotes and quotations actually rendered in Word. For speaker display, remove only an exact duplicated institution prefix when the frozen role-plus-name label repeats it; do not alter the frozen speaker identity or guess new roles.

Hotword prose uses the fixed neutral word-group template and supported viewpoint focus. Topic propagation volume may determine presentation order, but it is not word frequency or a temporal trend: do not turn that order into "top-ranked", "higher heat" or "continuously spreading" claims. Use "相关观点" for the linked reviewed interpretation rather than implying population-wide consensus. Word and workbench rebuild display paragraphs from the same current atomic evidence; stale preassembled `details` cannot override reviewed claims or retain outdated attribution.

Author claims distinguish `claim_kind=policy_reasoning` from `meeting_action_fact`. Only genuinely substantive mechanisms, conditions, impacts, suggestions or evaluations qualify as independent interpretation. A detailed meeting-action list is still factual reporting, even when republished by a court or government account or fully supported by the source. The host mechanically removes explicitly classified meeting-action facts from formal selection and retains their original classification/text in exclusions. Do not keyword-exclude substantive official implementation guidance or infer missing classifications in legacy responses; this field is not independent quality certification.

Every host-built topic author packet also carries `agenda_topics` from the current research plan. Use the complete current agenda to disambiguate the specific policy being commented on: shared generic words such as law, institution or investment do not justify assigning another agenda's interpretation to a thin topic. Candidate-list membership and full-meeting relevance are not final topic eligibility. The field participates in normal packet hashing/cache invalidation and contains no historical agenda dictionary.

Reading order may prioritize a generic named-professional attribution found in the original body near the current policy name or declared alias. This is a mechanical reading hint, not a speaker identity, independent-voice count or eligibility verdict. The shortlist retains up to 40 source-diversified articles; policy-driven author reading caps are 20 monitoring articles plus ten public pages in `bounded_60m`, 16 plus eight in `bounded_40m`. A specific current-policy title takes reading priority over a generic title containing “解读/专家”, which may be a multi-news or market roundup. Keep all raw IDs and complete original text; unread records remain deferred rather than semantically excluded. Never hard-code people or outlets from benchmark reports into this prioritization.

For bounded available-content delivery, a genuinely empty reviewed topic uses the fixed notice `本轮在监测期内未取得可引用的独立解读，保留该议题的传播数据；这不代表没有相关讨论。` beneath its original topic heading. No fabricated analytical heading or empty `一是` cluster is allowed. Preserve missing-comment/sentiment notices without claiming a zero-result collection when access failed. Keep all existing verified content and the fixed chapter layout. Quantity targets and unfilled sections are audit warnings, not reasons to withhold Word or the workbench; source failures remain auditable and unverified claims never become conclusions.

The formal report body should not contain engineering status blocks such as:

- `正式交付状态`
- `质量门禁`
- `低质量率`
- `目标完成情况`
- internal crawler failure logs

Those belong in `cwh_audit.json` and, if needed, a separate review note.

### 解读资格与原文支持分别核查

纯转述会议要求、既有规划条文、实施安排或统计数据，即使出处真实、细节完整，也不自动构成媒体自身解读。选材必须找到实际发言主体针对本次决策的独立判断、建议或评价；背景事实只支持原文已有判断，不能由模型补出因果或意义。无独立判断时排除并保留缺口，不能收窄成一个事实句后宣称解读通过。原文支持审核和标题审核均不能代替这一选材资格判断。共同规则由config/formal_writing_rules.v1.json的viewpoint.interpretation_eligibility_rule提供，并传入作者提示和各模型任务契约。

正式观点不保留裸“本次会议/此次会议/这次会议/该会议”；按原文明确真实会议名称，相关背景解读不能冒充本次常务会部署。作者先处理；独立审核另获原始标题与最多2000字原文开头，仅用于对象消歧，不能补充截取片段外的论据；宿主最终检查只识别未展开的文字风险，不猜会议身份。原始证据与旧交付不改。

境外summary_cn_simplified是正文观点，review_reason是选材审核理由。两者不能混写：“属会议事实之外新增的分析”“因此纳入”等只放审核理由；正式摘要直接写判断、机制和条件，无原文分析就不补造。

三期共性不是每期都要有外媒评论，而是把事实报道与实际解读分开呈现。每条外媒解读先写原文主体的中心判断，再保留直接支持它的必要依据和条件，通常1—2句、约80—180汉字；长度是建议，不硬截原文条件。项目名、部署清单、投资总额与历年数量不整段搬入观点，不能只加“认为”就把事实转成解读。纯事实仍列在事实报道及附录；没有独立判断时如实留缺口，不为向基准靠齐而补分析。共享规则由overseas.interpretive_summary_rule传入各批原文审核，公众号TOP批不接收境外摘要字段提示。

本期议程明确涉及的其他会议或背景政策的实质解读可以保留，但成文须明确原文实际讨论对象。不能把该原文中的“本次会议”“新增部署”等指称直接移到报告会议，冒称另一场会议的要求是本次报告会议的新决定。独立复核同时收到当前议题、议程组和原始标题，用于讨论对象消歧；标题不代替原文论据，不新增原文未支持的日期、因果或结论。
### 独立复核字段门禁与缓存恢复

合法JSON不代表复核可用。正文审核的rationale必须是非空字符串，空值、错误类型、缺字段和重复/漏掉证据ID不得成为支持认证。宿主在标题返修及原文认证前检查这些字段；字段无效时，只在原独立复核阶段剩余预算允许时重新发送冻结正文论断做一次最长45秒的真实复核，不重新审核标题、不增加全程预算。重试要求覆盖全部正文论断，因此每条新认证都归属实际新复核运行，不能给旧结论补写理由或重盖运行ID。旧原答、缓存、摘要哈希及真实运行保留；原先标题仍归原始实际标题审核运行。重试仍无效就明确失败，不重复三次读取同一坏缓存当作三次新复核。

境外范围字段使用两个字符串组成的JSON数组，片段ID逐字复制本条原文，不依原始行号猜编号。宿主可将完全明确的字符串化双ID数组无损转成数组，包括[o1/1, o1/2]这一编码；最终仍过原来同源、有序、存在的逐字切片门禁，并记录原字段和编码修复。跨原文、倒序、越界、多个值或无法无歧义解码的范围不修猜。

### 标题覆盖与跨议题唯一归属

分簇标题必须获得该簇全部保留论断的支持；独立审核的 supporting_claim_ids 只覆盖部分成员时，宿主拒绝采纳该标题，而不是把其余成员硬放在第一人的判断下。不同机制不能仅凭宏观主题相同合并，也不以顿号拼接多个中心来冒充共同判断。一级议题标题须以原生布尔 scope_preserved 确认保留输入议题的完整政策对象；不能为了短标题只留下第一簇或一个子对象。没有可采用的概括时保留原议题名称，不补造结论。这些检查只约束展示标题，不改冻结原文、主体和论断。

同一声明主体、职务和原始URL的完全相同判断跨议题出现时，脚本标记全部证据ID，已有全局独立审核按实际政策对象确定最直接的归属。脚本不自行删观点、猜去向或合并同名不同职务的人。原文有不同实质判断可以分属不同议题；不能靠稍改措辞将同一判断重复收录。

### Early publication-metadata validation

Before moving to the next author topic, validate selected web articles against their literal original publisher and complete publication date. Explicit source/date metadata on one line, or a standalone full timestamp immediately followed by a source/publishing-location label, may establish a publication date. Navigation dates, narrative event dates, month/day without year, and conflicting metadata dates must not be inferred. A verified out-of-period header is a deterministic exclusion with original model selection preserved in audit.

Other invalid selected-web metadata gets at most one local model repair, capped at 45 seconds and the current stage's remaining allocation with future-topic reserve. It uses a separate hash-checked model cache, never overwrites the raw author answer, and must pass the same original-text metadata gate afterward. Missing dates cannot be supplemented from URLs or meeting years. This does not reset stage retries or enlarge the full-run budget.
