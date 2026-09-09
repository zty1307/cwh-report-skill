#!/bin/sh
set -eu

export CWH_APP_ROOT="${CWH_APP_ROOT:-/app}"
export CWH_DATA_ROOT="${CWH_DATA_ROOT:-/app/data}"
export CWH_PORTABLE_XLSX=1
export PYTHONIOENCODING=utf-8

# With-managed MySQL is selected by the backend-only runtime configuration.
# Local and preview builds without that file continue to use SQLite.
if [ -f "${CWH_DB_CONFIG:-/app/config/mysql_runtime.json}" ]; then
  export CWH_DB_BACKEND=mysql
fi

python /app/cwh-report-skill/scripts/prepare_with_runtime.py
exec python /app/cwh-report-skill/scripts/serve_dashboard.py \
  /app/data/current/cwh_dashboard.html \
  --library-root /app/data \
  --workspace /app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --report-runner pipeline \
  --no-open
