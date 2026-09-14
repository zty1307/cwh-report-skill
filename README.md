# CWH Report Skill

An auditable, resumable workflow for generating public-opinion reports for State Council executive meetings from monitoring-system exports.

The default `bounded_60m` profile is model-neutral and uses one active model worker: it exposes bounded JSON tasks and keeps deterministic writing, validation, state, hashing, rendering, and delivery outside the model. Research has a 45-minute cutoff inside the one-hour total budget. `bounded_40m` remains a tighter explicit option; `exhaustive` preserves uncapped research. Independent evidence review remains a separate sequential run, not author self-certification.

Current evaluation version: **2026.09.14-v47-rc3** (`config/release.json`). This candidate adds host-compiled semantic decisions, claim-local verified quotation ranges, script-owned hotword evidence/scoring handoffs, bounded selected-field repairs and a watchdog that also covers blocked large-stdin delivery on Windows. Standard-workbook budgets reuse the raw-normalization allowance for authoring and independent review. Successful end-to-end completion within one hour on ordinary domestic models remains a forward-test target, not a claimed result.

Validation details and remaining limitations are recorded in [the candidate validation report](references/v47_validation.md). Real hy4 tests distinguish fresh raw review, recovery using earlier decisions, and report-stage continuation; none may be relabelled as a fresh full-report success. No API token reduction percentage or full-report speedup is claimed. Review-only snapshots do not count as formal report delivery.

See [rc3 observed results and unresolved gates](references/v47_rc3_validation.md) and [earlier rc2 observations](references/v47_rc2_validation.md). The compiled adapter remains opt-in through `CWH_SEMANTIC_COMMAND_JSON` and an approved `CWH_SEARCH_COMMAND_JSON`; generic fallback hosts still need their capability-specific adapters. Shared installed Skills and other model windows are not changed by a repository update.

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

更新完整 Skill 目录并确认 `config/release.json` 为 `2026.09.14-v47-rc3`。提供本期议程和原始监测表或标准总表；每个模型使用独立的新任务目录。旧测试中修改过哈希、回退过状态或使用旧节点结构的任务留作审计，不能继续用它证明新版本成功。

先确认可用的 Python（建议 3.12），运行 `python scripts/cwh_preflight.py --skill-root .`；按预检提示补齐依赖。Windows 若 `python` 命中商店别名，改用实际 Python 可执行文件的完整路径。

可直接把这段交给测试模型，并附议程及数据文件：

> 使用当前目录的 cwh-report-skill 完成这期报告。先读取 SKILL.md 并执行预检，使用 bounded_60m 和新的 job-dir，单工作器顺序运行。由流水线按序生成任务；你只完成当前 tasks 文件声明的输出，采集中间文件写入 stage_workspace，再调用 run 续跑。不重写报告正文和工作台，不重复读取全部资料。独立复核使用新的顺序模型运行上下文，不能由撰稿运行自行认证。不得修改 Skill、配置、状态、事件、哈希或已验证产物。遇到证据不足、登录或超时，按契约保留阻断和日志。完成后核验 Word、Excel、JSON、审计与 HTML，报告真实总耗时、最终状态和全部阻断。

标准总表入口（从本目录执行，替换议程与路径）：

```powershell
python scripts/run_cwh_resumable_pipeline.py run `
  --job-dir outputs/model_retest_v47_new `
  --agenda "本期会议日期或完整议程" `
  --system-workbook "D:\path\本期标准总表.xlsx" `
  --execution-profile bounded_60m --no-open
```

没有外部工作器时停在 `waiting_ai`，执行当前任务包后用同一命令续跑。自动工作器通过 `CWH_PIPELINE_AI_COMMAND_JSON` 接入，宿主配置见 [model worker hosts](references/model_worker_host.md)。总计时从首次 `run` 开始，节点计时从首次进入节点开始，均包含等待和重试；重复 `run` 或 `invalidate` 不重置。超时记录 `time_budget_exhausted`，不能计为一小时内成功。原始导出目录的入口及必需元数据见 `references/raw_workbook_pipeline.md`。

限时模式不再要求逐字重读全部监测文章：脚本保存完整池及议题索引，每个议题至少实际审核 `min(12, 本议题文章数)` 篇全文，其余明确记为 deferred，不能记成审核、排除或没有观点。完整证据、独立声音数量、观点密度及独立复核要求不降低；穷尽模式仍要求全部审核。议题批量模型传输仍属可选实验功能。

复测请保留 `pipeline_state.json`、`pipeline_events.jsonl`、`tasks/`、`logs/` 和 `report/`。状态文件的 `completed_elapsed_seconds` 是首次成功耗时；最终 `succeeded` 还需与事件历史、产物哈希和交付审计相符。等待、阻断和部分产物均不计成功。

The repository contains the complete Skill instructions, deterministic workbook pipeline, research and evidence contracts, domestic-comment and sentiment handoffs, report renderers, Word/Excel/HTML templates, With deployment files, and regression tests. It intentionally contains no monitoring data, completed reports, browser profiles, cookies, credentials, database files, or API keys.

## What this evaluates

The intended forward test starts with an unseen raw export bundle or standard monitoring workbook and checks whether an agent can complete:

1. raw exports to the standard workbook;
2. per-topic research and platform coverage;
3. traceable domestic viewpoints and real public comments;
4. overseas review, sentiment review, and hotword review;
5. independent evidence mapping and release gates;
6. synchronized Word, Excel, JSON, audit, and self-contained HTML output;
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

The public repository bundles Noto Sans CJK SC under the SIL Open Font License 1.1. An organization-specific approved font may be supplied at runtime through `CWH_CJK_FONT`. The internal Tencent font used by one reviewed deployment is not redistributed here because no public redistribution license was established.

## External capabilities

Public-web discovery, login-backed domestic collection, and reviewed model sentiment require their own approved tools, sessions, or model worker. The repository does not bundle personal login state and never treats an unavailable collector or `waiting_login` as successful completion.

## License status

No license for the repository's original source code has been granted yet. Public visibility permits inspection and evaluation but does not by itself grant permission to copy, modify, or redistribute the original source. Third-party components remain subject to their own licenses.
