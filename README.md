# CWH Report Skill

An auditable, resumable workflow for generating public-opinion reports for State Council executive meetings from monitoring-system exports.

The default `bounded_60m` profile is model-neutral: it exposes one JSON task contract at a time, enforces stage/query/fetch/output limits, and keeps deterministic writing, validation, state, hashing, rendering, and delivery outside the model. An optional `exhaustive` profile preserves uncapped research when elapsed time is not the priority.

Current evaluation version: **2026.09.13-v45** (`config/release.json`). This release unifies draft/final density gates, adds bounded Windows checkpoint retries, fixes automatic-worker handoff to independent review, restricts review outputs to the model's review packet, and persists time budgets across waits, retries and resume. It also includes the Dashboard evidence-mapping and failed-stage retry fixes. Multi-model completion within one hour is a forward-test target, not a claimed result.

Release validation on Windows / Python 3.12: source suite **280 passed**; public checkout **273 passed, 7 skipped** (private workbook fixtures are intentionally not distributed). Runtime preflight and Skill validation passed. A real monitoring workbook completed preflight, intake, workbook and research-plan stages in about 2.5 seconds, then correctly stopped at `waiting_ai`; this is an entry/resume smoke test, not an end-to-end model result. Fault tests cover transient/permanent checkpoint locks, interrupted success persistence, missing/rolled-back event history, cumulative deadlines, worker review boundaries and shared draft/final density decisions.

## 国产模型复测

更新完整 Skill 目录并确认 `config/release.json` 为 `2026.09.13-v45`。提供本期议程和原始监测表或标准总表；每个模型使用独立的新任务目录。旧测试中修改过哈希、回退过状态或使用旧节点结构的任务留作审计，不能继续用它证明新版本成功。

先确认可用的 Python（建议 3.12），运行 `python scripts/cwh_preflight.py --skill-root .`；按预检提示补齐依赖。Windows 若 `python` 命中商店别名，改用实际 Python 可执行文件的完整路径。

可直接把这段交给测试模型，并附议程及数据文件：

> 使用当前目录的 cwh-report-skill 完成这期报告。先读取 SKILL.md 并执行预检，使用 bounded_60m 和新的 job-dir。由流水线按序生成任务；你只完成当前 tasks 文件声明的输出，再调用 run 续跑。独立复核使用新的模型运行上下文，不能由撰稿运行自行认证。不得修改 Skill、配置、状态、事件、哈希或已验证产物。遇到证据不足、登录或超时，按契约保留阻断和日志。完成后核验 Word、Excel、JSON、审计与 HTML，报告真实总耗时、最终状态和全部阻断。

标准总表入口（从本目录执行，替换议程与路径）：

```powershell
python scripts/run_cwh_resumable_pipeline.py run `
  --job-dir outputs/model_retest_v45_new `
  --agenda "本期会议日期或完整议程" `
  --system-workbook "D:\path\本期标准总表.xlsx" `
  --execution-profile bounded_60m --no-open
```

没有外部工作器时停在 `waiting_ai`，执行当前任务包后用同一命令续跑。自动工作器通过 `CWH_PIPELINE_AI_COMMAND_JSON` 接入。总计时从首次 `run` 开始，节点计时从首次进入节点开始，均包含等待和重试；重复 `run` 或 `invalidate` 不重置。超时记录 `time_budget_exhausted`，不能计为一小时内成功。原始导出目录的入口及必需元数据见 `references/raw_workbook_pipeline.md`。

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
