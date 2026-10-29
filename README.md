# CWH Report Skill

An auditable, resumable workflow for generating public-opinion reports for State Council executive meetings from monitoring-system exports.

**产研交接：** [完整流程说明与打开方式](docs/production-handoff/README.md) · [下载交接文档离线包](https://github.com/zty1307/cwh-report-skill/raw/refs/heads/main/docs/production-handoff/常务会产研交接文档.zip)

业务交付为Word报告、配套Excel和HTML工作台；来源依据、审核结果、结构化中间数据和日志由后台留存，不作为额外业务交付件。参考程序仍保留内部文件，本次文档同步不修改运行输出或质量门禁。MCP部分仅列拟取数据及用途，尚待接入验证。

The default `bounded_45m` profile is model-neutral and uses one active model worker. The complete job has a 2700-second limit, a 2460-second research cutoff and a 240-second delivery buffer. Scripts own scheduling, calculations, validation, state, caching, rendering and delivery; models read complete selected articles, extract viewpoints and perform separate independent review. `bounded_40m`, `bounded_60m` and `exhaustive` remain explicit alternatives.

Current evaluation version: **2026.10.29-feedback45** (`config/release.json`). This publication synchronizes the source used in the complete GLM test on **2026-10-23**: **37m51.25s**, all 12 stages completed, with **28 domestic body claims** (24 from monitoring exports and 4 from public-web research). The result remains `delivered_with_gaps`, not certified formal delivery. See [measured results and limitations](references/feedback45_validation.md).

统计规则：总事件、各子事件分别从“细分渠道-日趋势”取数；细分新闻列归境内主流媒体，百家号、头条等独立保留并归新媒体；微信合计公众文章、在看／推荐量、精选评论量三项；微博、视频号单列，不将父级汇总列与子级细数重复累加。境外仍经原文审核后回算，本阶段正式情感百分比留空。

引述规则：境内媒体自媒体观点中的具名个人须核实机构、职务、姓名；普通个人、普通网友和仅自报经历者不作该部分样本。账号自身发言归完整账号名，转引专家归专家。正文直接写主体和观点，去除采访过程套话及重复账号抬头。真实网民评论仍按独立评论章节规则审核。规则同步不代表已完成新一轮真实模型报告测试。

实测源码的自动化验证：1632项测试通过、7项因外部夹具或环境条件跳过、5项子测试通过；预检通过。本次GitHub同步另检查发布目录、源码一致性和回归测试，结果见[发布验证说明](references/feedback45_validation.md)。

Earlier candidate validation is retained in [the historical validation report](references/v47_validation.md). Historical hy4 recovery or report-stage continuation must not be relabelled as a fresh full-report success. The newer GLM measurement is one complete run on one input period and host, not a guarantee for every model, period or provider; no token reduction percentage is claimed.

Earlier [rc3 observations](references/v47_rc3_validation.md) and [rc2 observations](references/v47_rc2_validation.md) remain historical. Configure an approved semantic host through `CWH_SEMANTIC_COMMAND_JSON` and public-web discovery through `CWH_SEARCH_COMMAND_JSON`; other hosts require compatible adapters. This repository update does not install into other model windows or bundle personal sessions.

## 固定流程与低 token 分工

| 环节 | 固定执行部分 | 模型保留的工作 |
|---|---|---|
| 写作 | 章节、导语、数据句式、来源顺序、归因拼接、编号、评论导语、热词与境外句式、Word/Markdown 排版 | 基于证据的标题、逐条观点和语义复核 |
| 工作台 | 固定 HTML 模板读取统一数据，生成导航、图表、证据卡、报告视图和导出入口；保留系统原图 | 无需写 HTML/CSS/JavaScript 或重新设计页面 |
| 证据结构 | 对可唯一确定的缺失 ID、哈希、连续摘录偏移进行补齐，校验映射并保留原文 | 真实性、相关性、发言主体、观点归类和原文支持判断 |
| 控制与恢复 | 固定节点顺序、当前任务包、断点、缓存、时间预算、校验、局部修复反馈、统一交付 | 处理当前节点明确要求的语义字段或报告真实阻断 |

常规运行不加载大型工作台模板，不让模型重写整篇正文；只读当前任务需要的输入与参考规范，复用已接受原文和产物。默认 CLI 只输出当前状态、任务、错误及节点状态表；完整历史仍保存在 `pipeline_state.json`，旧 stdout 消费程序可加 `--output-format full`。可运行 `python scripts/cwh_timing_report.py --job-dir <任务目录>` 查看已记录的节点/命令时间；它不是 token 计量器。

固定的是结构与机制，不是某期报告的事实。主持人、媒体名称、峰值、来源占比和评价结论均不得从历史模板继承。达到时间上限但未通过交付门禁仍算失败；不得为压时缩短证据、取消独立复核或伪造评论。

## 国产模型复测

更新完整 Skill 目录并确认 `config/release.json` 为 `2026.10.29-feedback45`。提供本期议程和原始监测表或标准总表；每个模型使用独立的新任务目录。当前默认 `bounded_45m`，单个AI任务按顺序执行；原文筛选、全网搜索和薄弱议题补充在同一整轮中自动衔接。旧测试、暂停后的诊断续跑不能充当新的45分钟完整实测。

先确认可用的 Python（建议 3.12），运行 `python scripts/cwh_preflight.py --skill-root .`；按预检提示补齐依赖。Windows 若 `python` 命中商店别名，改用实际 Python 可执行文件的完整路径。

可直接把这段交给测试模型，并附议程及数据文件：

> 使用当前目录的 cwh-report-skill 完成这期报告。先读取 SKILL.md 并执行预检，使用 bounded_45m 和新的 job-dir，单工作器顺序运行。由流水线按序生成任务；你只完成当前 tasks 文件声明的输出，采集中间文件写入 stage_workspace，再调用 run 续跑。不重写报告正文和工作台，不重复读取全部资料。独立复核使用新的顺序模型运行上下文，不能由撰稿运行自行认证。不得修改 Skill、配置、状态、事件、哈希或已验证产物。遇到证据不足、登录或超时，按契约保留阻断和日志。完成后核验 Word、Excel、JSON、审计与 HTML，报告真实总耗时、最终状态和全部阻断。

标准总表入口（从本目录执行，替换议程与路径）：

```powershell
python scripts/run_cwh_resumable_pipeline.py run `
  --job-dir outputs/model_retest_v47_new `
  --agenda "本期会议日期或完整议程" `
  --system-workbook "D:\path\本期标准总表.xlsx" `
  --execution-profile bounded_45m --no-open
```

没有外部工作器时停在 `waiting_ai`，执行当前任务包后用同一命令续跑。自动工作器通过 `CWH_PIPELINE_AI_COMMAND_JSON` 接入，宿主配置见 [model worker hosts](references/model_worker_host.md)。总计时从首次 `run` 开始，节点计时从首次进入节点开始，均包含等待和重试；重复 `run` 或 `invalidate` 不重置。超时记录 `time_budget_exhausted`，不能计为45分钟内完成。原始导出目录的入口及必需元数据见 `references/raw_workbook_pipeline.md`。

原始监测模式先由脚本保留完整语料和备选索引，默认首批最多50篇、合计11万字符交给AI读完整导出正文；未读备选不记成排除。每题均保留公开搜索及网页阅读机会，薄弱议题优先。独立核验后仍薄弱时，自动回捞未读备选、补读网页，并依据前序剔除理由调整搜索词。新增观点仍须独立复核；已完成阅读复用缓存，不能通过重置时钟扩大预算。详见[原始筛选集成](references/raw_sample_screen_integration.md)和[定向补搜与缓存](references/adaptive_web_research.md)。

复测请保留 `pipeline_state.json`、`pipeline_events.jsonl`、`tasks/`、`logs/` 和 `report/`。状态文件的 `completed_elapsed_seconds` 是首次成功耗时；最终 `succeeded` 还需与事件历史、产物哈希和交付审计相符。等待、阻断和部分产物均不计成功。

The repository contains the complete Skill instructions, deterministic workbook pipeline, research and evidence contracts, domestic-comment and sentiment handoffs, report renderers, Word/Excel/HTML templates, With deployment files, and regression tests. It intentionally contains no monitoring data, completed reports, browser profiles, cookies, credentials, database files, or API keys.

## What this evaluates

The intended forward test starts with an unseen raw export bundle or standard monitoring workbook and checks whether an agent can complete:

1. raw exports to the standard workbook;
2. per-topic research and platform coverage;
3. traceable domestic viewpoints and real public comments;
4. overseas review, sentiment review, and hotword review;
5. independent evidence mapping and release gates;
6. synchronized Word, Excel, and self-contained HTML business outputs, with JSON and audit files retained internally;
7. checkpoint/resume behavior, including non-terminal `waiting_login` and `waiting_ai` states.

Historical baseline reports must remain outside the generation context and may be used only by an independent evaluator after generation.

## Install as a Skill

Copy this directory to the target agent's Skill directory and keep its folder name as `cwh-report-skill`. The target runtime must support local file access and Python execution; a chat-only language model can review the instructions but cannot run the workflow.

Validate the Skill structure with the validator supplied by the target Codex installation:

```text
python <skill-creator>/scripts/quick_validate.py <path-to>/cwh-report-skill
```

## Runtime entry points

- Full resumable workflow: `scripts/run_cwh_resumable_pipeline.py`
- Runtime and policy preflight: `scripts/cwh_preflight.py`
- Model-worker task contract: `scripts/cwh_model_contract.py`
- Deterministic viewpoint prose assembly: `scripts/normalize_cwh_analysis.py`
- Draft-only mechanical evidence completion: `scripts/complete_cwh_evidence_structure.py`
- Shared executable writing frames: `scripts/cwh_writing_rules.py`
- Fixed workbench renderer: `scripts/generate_dashboard.py`
- Observed stage/command timing: `scripts/cwh_timing_report.py`
- Raw-workbook stage: `scripts/raw_system_workbook_pipeline.py`
- Domestic-comment stage: `scripts/run_cwh_domestic_comment_collection.py`
- Sentiment entrance gate: `scripts/run_cwh_sentiment_stage.py`
- Report renderer: `scripts/cwh_orchestrator.py`
- With application builder: `scripts/build_with_app_bundle.py`

The With runtime uses pipeline mode. Connect a model-specific stage worker through the backend-only `CWH_PIPELINE_AI_COMMAND_JSON` environment variable. Do not embed credentials in that value; the adapter should read them from an approved secret store.

## Fonts

The package bundles `assets/fonts/TencentFont.otf` (TTTGB Medium) as the default wordcloud font. It is loaded relative to the Skill directory: users do not need to install a system font or configure an absolute path. Generated wordcloud PNGs carry the rendered glyphs into Word and HTML, so viewers do not need the font either. The project owner confirmed permission to distribute this font with the Skill on 2026-09-15; see `assets/fonts/TENCENT-FONT-NOTICE.md` for the recorded scope and documentation status.

Noto Sans CJK SC remains bundled under the SIL Open Font License 1.1 as a fallback. An explicitly selected approved font may override the default through run metadata `wordcloud.font_path` or the process-local `CWH_CJK_FONT`.

## External capabilities

Public-web discovery, login-backed domestic collection, and reviewed model sentiment require their own approved tools, sessions, or model worker. The repository does not bundle personal login state and never treats an unavailable collector or `waiting_login` as successful completion.

## License status

No license for the repository's original source code has been granted yet. Public visibility permits inspection and evaluation but does not by itself grant permission to copy, modify, or redistribute the original source. Third-party components remain subject to their own licenses.
