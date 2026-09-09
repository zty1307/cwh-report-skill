# CWH Monitoring-System Data Contract

## Authority

The department monitoring system is authoritative for numerical claims. The CWH skill may clean, validate, calculate documented formulas, analyze, and render those values, but it must not replace them with crawler-derived counts.

## Required Input Bundle

### Summary workbook

Required for formal delivery:

- event name and event ID;
- subevent names and event IDs;
- monitoring start/end dates;
- total-event daily channel metrics and total spread;
- every subevent's daily and total domestic/new-media/overseas metrics;
- subevent sentiment ratios when the system provides them, retained as audit references only.

Expected mentor-style sheets:

| Sheet | Required content |
|---|---|
| `关键词` | Total/subevent keywords, exclusions, event IDs |
| `总事件` | Daily overall summary and detailed channel fields |
| `子事件1...N` | Independent daily subevent metrics |
| `子事件数据汇总` | Subevent totals and sentiment ratios |
| `外媒报道列表` | Overseas evidence and multi-topic hit flags |
| `词云` | Candidate hotwords |
| `公众TOP` | WeChat ranking data |

### Detail exports

Required to automate qualitative report sections. CSV, JSON, XLSX, and XLSM are accepted.

Recommended fields:

| Canonical field | Common Chinese aliases |
|---|---|
| `id` | ID, 数据ID, 信息ID, 文章ID, 评论ID |
| `topic` | 子事件, 子议题, 议题, 事件名称 |
| `platform` | 平台, 渠道, 来源平台 |
| `source_type` | 来源类型, 媒体类型, 账号类型, 信息类型 |
| `source` | 来源, 媒体名称, 账号, 作者, 昵称 |
| `title` | 标题, 文章标题, 信息标题 |
| `content` | 内容, 正文, 摘要, 评论内容, 评论原文 |
| `url` | 链接, 原文链接, 发布地址, URL |
| `published_at` | 发布时间, 日期, 时间 |
| `spread_count` | 传播量, 阅读量, 浏览量, 播放量, 热度, 在看量 |
| `comment_count` | 评论量, 评论数, 精选评论量 |
| `sentiment` | 情感, 情感倾向, 情感属性 |

Comment rows should additionally identify that they are comments through `is_comment`, `信息类型`, or a comment-specific source type.

## Department Composite Metric

The observed total-event workbook uses:

```text
微信公众号 = 公众文章 + 公号在看量 + 公号精选评论量
新媒体 = 境内APP + 境内论坛 + 其他视频 + 推特 + 境外其他 + 抖音
信息传播量 = 境内主流媒体 + 境外媒体 + 微信公众号 + 新浪微博 + 视频号 + 新媒体
```

Subevent sheets use an independent query universe. One item may hit multiple subevents, so subevent totals are non-additive.

## Validation

Block formal delivery when:

- the total event has no daily/total values;
- any subevent lacks a total;
- monitoring dates are absent or inconsistent;
- viewpoint claims lack media/self-media detail evidence;
- netizen comment text is absent;
- raw comments remain unclassified until the audited sentiment workflow returns row-level results;
- a generated workbook/report changes the system's numbers.

Do not block on arbitrary crawler sample targets. The remedy for missing formal data is to request another system export.

## Optional Supplements

Crawler/search rows must retain a source marker such as `mediaspider`, `agent_reach`, or `public_web`. They may support evidence review but cannot change:

- overall spread totals;
- daily trend values;
- platform totals;
- subevent totals;
- system sentiment ratios as non-authoritative reference fields; formal ratios must come from the audited comment-level workflow.
