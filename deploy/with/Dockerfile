FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NODE_VERSION=22.17.1 \
    PATH=/opt/node/bin:$PATH \
    CWH_APP_ROOT=/app \
    CWH_DATA_ROOT=/app/data \
    CWH_ARCHIVE_DB=/app/data/cwh_archive.sqlite3 \
    CWH_DB_CONFIG=/app/config/mysql_runtime.json \
    CWH_ARCHIVE_SEED_DIR=/app/seed/archive \
    CWH_PORTABLE_XLSX=1 \
    CWH_ENABLE_SHARED_COLLECTORS=1 \
    CWH_MEDIASPIDER_SUPERVISOR=/app/mediaspider-supervisor \
    CWH_MEDIASPIDER_HOME=/app/MediaSpider \
    CWH_FOREIGN_PLATFORMS=grounding,youtube

WORKDIR /app
COPY requirements.txt /app/requirements.txt
COPY MediaSpider /app/MediaSpider
RUN pip install --no-cache-dir -r /app/requirements.txt \
    && if [ -f /app/MediaSpider/requirements.txt ]; then pip install --no-cache-dir -r /app/MediaSpider/requirements.txt; fi
RUN python -c "from opencc import OpenCC; assert OpenCC('t2s').convert('陸新建核電機組') == '陆新建核电机组'"
RUN python -c "import urllib.request; urllib.request.urlretrieve('https://nodejs.org/dist/v22.17.1/node-v22.17.1-linux-x64.tar.gz', '/tmp/node.tar.gz')" \
    && mkdir -p /opt/node \
    && tar -xzf /tmp/node.tar.gz -C /opt/node --strip-components=1 \
    && rm -f /tmp/node.tar.gz \
    && node --version \
    && npm --version \
    && npm install -g mcporter \
    && agent-reach --help >/dev/null \
    && mcporter --help >/dev/null

COPY cwh-report-skill /app/cwh-report-skill
COPY mediaspider-supervisor /app/mediaspider-supervisor
COPY seed /app/seed
COPY config /app/config
COPY entrypoint.sh /app/entrypoint.sh
RUN mkdir -p /app/data /app/cwh-report-skill/assets/fonts \
    && python -c "import urllib.request; urllib.request.urlretrieve('https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf', '/app/cwh-report-skill/assets/fonts/NotoSansCJKsc-Regular.otf')" \
    && chmod +x /app/entrypoint.sh

EXPOSE 8000
CMD ["/app/entrypoint.sh"]
