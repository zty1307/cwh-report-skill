# CWH Report Skill

An auditable, resumable workflow for generating public-opinion reports for State Council executive meetings from monitoring-system exports.

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
