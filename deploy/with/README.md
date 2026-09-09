# CWH With deployment

This package deploys the editable CWH workbench and its native Python backend.

Runtime workflow:

1. Upload a standard monitoring workbook or the raw multi-workbook export bundle.
2. Normalize raw exports into the standard CWH workbook.
3. Generate Word, Excel, structured data, charts and a new dashboard.
4. Save edited dashboard sections back into the Word report.
5. Run server-safe public-web and overseas evidence supplementation during report generation.
6. Browse generated reports through the report library.

The With service starts with `--report-runner pipeline`. Every accepted stage is
checkpointed with artifact hashes and an audit log. Without an approved model
worker, the workflow completes deterministic stages and stops at `waiting_ai`;
it does not fall back to the old monolithic renderer. Configure the future
per-stage worker through the backend-only `CWH_PIPELINE_AI_COMMAND_JSON`
environment variable. The value is a JSON string array and may use the
placeholders `{task}`, `{output}`, `{stage}`, `{job_dir}` and `{skill_root}`.
After the worker is configured, rerunning the same job continues from the saved
stage and preserves the report database.

Do not place API keys, cookies or database credentials inside the command JSON;
the command should invoke an adapter that reads approved secrets from With's
backend environment or managed secret store.

The image includes Agent Reach core tools and MediaSpider's foreign collector. Their live status is available from `/api/collectors/status`. Domestic evidence and social comments never change monitoring-system totals. Reviewed in-window overseas news can affect only the overseas channel after complete pre-workbook AI review and deduplication.

Local runs fall back to SQLite. Shared With deployments use the project-managed MySQL database through backend-only `CWH_MYSQL_*` variables or `CWH_DB_CONFIG`. The shared archive stores searchable metadata, the self-contained report dashboard, formal Word and report-only revision history. Excel, JSON, audit, crawler output and other processing attachments remain in the working area and are not written to the shared history database.

Weibo, Douyin and other login-protected domestic platforms remain disabled until a department-owned account and an approved secret/cookie storage mechanism are configured; personal browser sessions are never bundled into With. Reviewed large-model sentiment remains a separate audited stage.

The top-right “连接平台” panel can call the loopback-only companion connector (`start_platform_connector.cmd`) on the user's Windows computer. Its Baijiahao entry opens a site-limited Baidu result page and requests human action only if Baidu presents a slider. Its WeRead entry opens the official WeRead page for QR login. The server-side With container never receives, stores or bundles those local browser cookies; local article adapters explicitly reuse the connector profile marker after the user closes the verification browser.
