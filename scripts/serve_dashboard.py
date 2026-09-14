from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import json
import mimetypes
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PureWindowsPath
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, unquote, urlparse
from urllib.request import Request, urlopen


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from archive_store import ArchiveStore
from cwh_hotword_pipeline import looks_like_pure_geography
from cwh_pipeline_runtime import atomic_write_json


SUPPORTED_DOMESTIC_PLATFORMS = ("wb", "dy", "ks", "bili", "zhihu")
PLATFORM_LOGIN_PROTOCOL_VERSION = 3


def available_port(host: str, preferred: int) -> int:
    for port in range(preferred, preferred + 30):
        with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((host, port))
            except OSError:
                continue
            return port
    raise OSError(f"No available local port in range {preferred}-{preferred + 29}")


def report_id(directory: Path) -> str:
    marker = directory / ".cwh_report_id"
    if marker.exists():
        value = marker.read_text(encoding="ascii", errors="ignore").strip().lower()
        if re.fullmatch(r"[a-f0-9]{12}", value):
            return value
    return hashlib.sha1(str(directory.resolve()).lower().encode("utf-8")).hexdigest()[:12]


def chinese_date(value: str) -> str:
    match = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", str(value or ""))
    if not match:
        return str(value or "")
    year, month, day = match.groups()
    return f"{year}年{int(month)}月{int(day)}日"


def normalize_manual_hotwords(
    data: dict,
    rows: object,
    baseline_words: object | None = None,
) -> tuple[list[dict], list[str]]:
    """Normalize dashboard edits while preserving the evidence metadata we already have."""

    if not isinstance(rows, list):
        raise ValueError("items must be a list")
    existing = [row for row in (data.get("hotwords") or []) if str(row.get("word") or "").strip()]
    existing_by_word = {str(row.get("word") or "").strip(): row for row in existing}
    baseline = {
        re.sub(r"\s+", "", str(word or "").strip())
        for word in (baseline_words if isinstance(baseline_words, list) else [])
        if str(word or "").strip()
    }
    topics = [str(topic) for topic in ((data.get("meeting") or {}).get("topics") or []) if str(topic).strip()]
    evidence_rows = list(data.get("samples") or []) + list(((data.get("comments") or {}).get("selected") or []))
    seen: set[str] = set()
    normalized: list[dict] = []
    unsupported: list[str] = []
    total = max(1, len(rows))

    for index, raw in enumerate(rows):
        if not isinstance(raw, dict):
            continue
        word = re.sub(r"\s+", "", str(raw.get("word") or "").strip())
        if not word or word in seen:
            continue
        if len(word) > 24:
            raise ValueError(f"热词过长：{word}")
        if looks_like_pure_geography(word):
            raise ValueError(f"纯地名或项目所在地不能单独作为热词：{word}")
        seen.add(word)
        previous = existing_by_word.get(word) or (existing[index] if index < len(existing) else {})
        supplied_weight = raw.get("weight")
        if supplied_weight in (None, ""):
            old_weight = previous.get("display_weight") or previous.get("score") or previous.get("weight")
            supplied_weight = old_weight if old_weight not in (None, "") else round(100 - 55 * index / max(1, total - 1))
        try:
            weight = max(1, min(100, round(float(supplied_weight))))
        except (TypeError, ValueError):
            raise ValueError(f"热词权重无效：{word}") from None
        topic = str(previous.get("topic") or "").strip()
        if not topic and topics:
            topic = topics[index % len(topics)]

        matching = []
        for evidence in evidence_rows:
            text = " ".join(str(evidence.get(key) or "") for key in ("title", "content", "summary", "excerpt"))
            if word in re.sub(r"\s+", "", text):
                matching.append(evidence)
        previous_evidence = list(previous.get("evidence") or [])
        if matching:
            evidence = [
                {
                    "source": str(row.get("source") or row.get("author") or ""),
                    "title": str(row.get("title") or row.get("content") or "")[:180],
                    "url": str(row.get("url") or ""),
                    "evidence_type": str(row.get("evidence_type") or row.get("sample_type") or "manual_match"),
                }
                for row in matching[:8]
            ]
        else:
            evidence = previous_evidence
        if not evidence and word not in baseline:
            unsupported.append(word)

        normalized.append(
            {
                **previous,
                "word": word,
                "topic": topic,
                "count": weight,
                "score": float(weight),
                "display_weight": float(weight),
                "rank": len(normalized) + 1,
                "selection_method": "manual_dashboard_review",
                "authority": "human_reviewed_hotword",
                "evidence": evidence,
                "evidence_basis": "existing_report_evidence_or_human_review",
            }
        )
    if not normalized:
        raise ValueError("请至少保留一个热词")
    if len(normalized) > 80:
        raise ValueError("一次最多保留80个热词")
    return normalized, unsupported


def manual_hotword_payload(items: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "method": "human_reviewed_dashboard_adjustment",
        "settings": {
            "shape": "cloud",
            "background": "transparent",
            "color": "#0D4E6D",
            "rotation": -15,
            "width": 1600,
            "height": 1000,
            "primary_font_min": 22,
            "primary_font_max": 150,
            "font_scale_exponent": 3.0,
            "max_placed_instances": 289,
            "no_margin": True,
            "format": "png",
        },
        "selected": [
            {
                "term": row["word"],
                "weight": int(row.get("display_weight") or row.get("count") or 1),
                "rank": index,
                "topic": str(row.get("topic") or ""),
                "selection_method": "manual_dashboard_review",
                "evidence_count": len(row.get("evidence") or []),
            }
            for index, row in enumerate(items, 1)
        ],
    }


class DashboardApp:
    WORKBOOK_STEPS = [
        "识别文件结构",
        "匹配总事件与子事件",
        "计算传播汇总",
        "筛选外媒与公众号样本",
        "生成词云和图表",
        "写入并校验标准总表",
    ]

    def __init__(
        self,
        dashboard: Path,
        library_root: Path,
        *,
        enable_codex_runner: bool = False,
        report_runner: str = "auto",
        workspace: Path | None = None,
        codex_command: str = "",
        pipeline_ai_command: list[str] | None = None,
    ):
        self.dashboard = dashboard.resolve()
        self.library_root = library_root.resolve()
        self.import_root = self.library_root / "_dashboard_imports"
        self.import_root.mkdir(parents=True, exist_ok=True)
        self.session_root = self.library_root / "_platform_sessions"
        self.session_root.mkdir(parents=True, exist_ok=True)
        self.enable_codex_runner = enable_codex_runner
        self.workspace = (workspace or self.library_root.parent).resolve()
        self.codex_command = codex_command or self._find_codex_command()
        self.pipeline_ai_command = self._pipeline_ai_command(pipeline_ai_command)
        if report_runner == "auto":
            report_runner = "codex" if enable_codex_runner and self.codex_command else "native"
        if report_runner not in {"native", "codex", "pipeline"}:
            raise ValueError(f"Unsupported report runner: {report_runner}")
        self.report_runner = report_runner
        self._manifest_lock = threading.Lock()
        self._session_lock = threading.Lock()
        self._archive_lock = threading.Lock()
        self._archive_sync_lock = threading.Lock()
        self._archive_last_sync = 0.0
        self._session_processes: dict[str, subprocess.Popen] = {}
        self.archive_store = ArchiveStore(self.library_root)
        # Kept for local compatibility and diagnostics; MySQL deployments use
        # archive_store as the source of truth.
        self.archive_db = self.archive_store.sqlite_path
        # Serve the explicitly prepared current dashboard when it exists. The
        # archive is a recovery source, not a replacement for the live UI.
        if self.archive_store.backend == "mysql" and not self.dashboard.exists():
            existing = self.archive_store.search_reports()
            if existing:
                try:
                    restored = self.archive_store.hydrate(
                        str(existing[0]["id"]),
                        self.library_root / "_archive_cache",
                    )
                    restored_dashboard = restored / "cwh_dashboard.html"
                    if restored_dashboard.exists():
                        self.dashboard = restored_dashboard.resolve()
                except (OSError, ValueError, FileNotFoundError):
                    pass
        self._index_report_data(self.dashboard.parent / "report_data.json")

    @staticmethod
    def _find_codex_command() -> str:
        candidates = [
            shutil.which("codex.cmd"),
            shutil.which("codex"),
            str(Path.home() / "AppData/Roaming/npm/codex.cmd"),
        ]
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                return str(Path(candidate).resolve())
        return ""

    @staticmethod
    def _pipeline_ai_command(value: list[str] | None) -> list[str]:
        if value is not None:
            return [str(item) for item in value if str(item).strip()]
        raw = str(os.environ.get("CWH_PIPELINE_AI_COMMAND_JSON") or "").strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"CWH_PIPELINE_AI_COMMAND_JSON is invalid JSON: {exc}") from exc
        if not isinstance(parsed, list) or not parsed or not all(isinstance(item, str) and item.strip() for item in parsed):
            raise ValueError("CWH_PIPELINE_AI_COMMAND_JSON must be a non-empty JSON string array")
        return parsed

    def service_manifest(self) -> dict:
        """Return a small, non-sensitive description of the running workbench."""
        return {
            "status": "ok",
            "application": "cwh-report-workbench",
            "release_id": json.loads((SCRIPT_DIR.parent / "config/release.json").read_text(encoding="utf-8")).get("release_id", "unknown") if (SCRIPT_DIR.parent / "config/release.json").exists() else "unversioned",
            "mode": "full",
            "read_only": False,
            "report_runner": self.report_runner,
            "storage": self.archive_store.backend,
            "features": {
                "multi_file_import": True,
                "raw_workbook_normalization": True,
                "report_generation": True,
                "resumable_pipeline": True,
                "stage_level_quality_gates": True,
                "model_worker_configured": (
                    bool(self.codex_command)
                    if self.report_runner == "codex"
                    else bool(self.pipeline_ai_command)
                    if self.report_runner == "pipeline"
                    else False
                ),
                "section_editing": True,
                "report_history": True,
                "searchable_archive_database": True,
                "shared_supplemental_collection": self.shared_collectors_enabled(),
                "report_assistant": self.assistant_status()["available"],
                "platform_qr_login": self.domestic_collector_available(),
            },
        }

    @staticmethod
    def shared_collectors_enabled() -> bool:
        return str(os.environ.get("CWH_ENABLE_SHARED_COLLECTORS") or "").strip().lower() in {"1", "true", "yes", "on"}

    def collector_status(self) -> dict:
        supervisor = Path(os.environ.get("CWH_MEDIASPIDER_SUPERVISOR") or "/app/mediaspider-supervisor")
        media_home = Path(os.environ.get("CWH_MEDIASPIDER_HOME") or "/app/MediaSpider")
        return {
            "status": "ok",
            "enabled": self.shared_collectors_enabled(),
            "providers": {
                "public_web": {"available": True, "scope": "media_and_public_web_evidence"},
                "mediaspider_foreign": {
                    "available": (supervisor / "scripts/run_task.py").exists() and (media_home / "foreign_collect.py").exists(),
                    "scope": "overseas_media_and_public_platform_evidence",
                    "platforms": [item.strip() for item in (os.environ.get("CWH_FOREIGN_PLATFORMS") or "grounding,youtube").split(",") if item.strip()],
                },
                "agent_reach": {
                    "available": bool(shutil.which("agent-reach")),
                    "scope": "upstream_tool_health_and_zero_config_channels",
                },
                "domestic_authenticated_social": {
                    "available": self.domestic_collector_available(),
                    "scope": "weibo_douyin_and_other_login_protected_platforms",
                    "platforms": list(SUPPORTED_DOMESTIC_PLATFORMS),
                    "login": "per_user_qrcode",
                    "login_protocol": PLATFORM_LOGIN_PROTOCOL_VERSION,
                    "reason": "Each user scans the platform QR code. Browser profiles are isolated by the authenticated workbench identity.",
                },
            },
        }

    @staticmethod
    def assistant_status() -> dict:
        endpoint = str(os.environ.get("CWH_LLM_ENDPOINT") or "").strip()
        model = str(os.environ.get("CWH_LLM_MODEL") or "").strip()
        provider = str(os.environ.get("CWH_LLM_API_STYLE") or "openai").strip().lower()
        return {
            "status": "ok",
            "available": bool(endpoint and model),
            "provider": provider,
            "model": model,
            "reason": "" if endpoint and model else "With does not inject its editor Claude into published apps. Configure a company-approved runtime model endpoint.",
        }

    def assistant_chat(self, payload: dict) -> dict:
        status = self.assistant_status()
        if not status["available"]:
            raise ValueError(status["reason"])
        message = str(payload.get("message") or "").strip()
        if not message:
            raise ValueError("Message is required")
        history = payload.get("history") or []
        safe_history = []
        for row in history[-12:]:
            if not isinstance(row, dict):
                continue
            role = str(row.get("role") or "").strip().lower()
            content = str(row.get("content") or "").strip()
            if role in {"user", "assistant"} and content:
                safe_history.append({"role": role, "content": content[:6000]})
        report = self._current_report_data()
        meeting = report.get("meeting") or {}
        context = {
            "title": report.get("title"),
            "agenda": report.get("agenda") or meeting.get("agenda"),
            "meeting_date": report.get("meeting_date") or meeting.get("date"),
            "topics": [row.get("display") or row.get("topic") for row in report.get("topics") or []],
            "totals": report.get("totals") or {},
            "report_blocks": report.get("report_blocks") or {},
        }
        system = (
            "You are the CWH report assistant embedded in an internal State Council executive meeting "
            "public-opinion workbench. Answer in Chinese. Use only the supplied report context and the "
            "user's request. Distinguish monitoring-system figures from supplemental public evidence; "
            "never invent totals, comments, sources, links, or sentiment ratios. When asked to revise prose, "
            "return concise report-ready wording and identify the target section.\n\n"
            "Current report context:\n" + json.dumps(context, ensure_ascii=False)[:50000]
        )
        messages = [{"role": "system", "content": system}, *safe_history, {"role": "user", "content": message[:12000]}]
        endpoint = str(os.environ["CWH_LLM_ENDPOINT"]).strip()
        model = str(os.environ["CWH_LLM_MODEL"]).strip()
        api_key = str(os.environ.get("CWH_LLM_API_KEY") or "").strip()
        timeout = max(10, int(os.environ.get("CWH_LLM_TIMEOUT_SEC") or 120))
        provider = str(status["provider"])
        headers = {"Content-Type": "application/json"}
        if provider == "anthropic":
            if api_key:
                headers["x-api-key"] = api_key
            headers["anthropic-version"] = os.environ.get("CWH_ANTHROPIC_VERSION") or "2023-06-01"
            body = {
                "model": model,
                "max_tokens": int(os.environ.get("CWH_LLM_MAX_TOKENS") or 2500),
                "system": system,
                "messages": [row for row in messages if row["role"] != "system"],
            }
        else:
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            body = {
                "model": model,
                "messages": messages,
                "temperature": 0.2,
                "max_tokens": int(os.environ.get("CWH_LLM_MAX_TOKENS") or 2500),
            }
        request = Request(endpoint, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), headers=headers, method="POST")
        try:
            with urlopen(request, timeout=timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise RuntimeError(f"Model service returned HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"Model service is unreachable: {exc.reason}") from exc
        if provider == "anthropic":
            answer = "\n".join(str(row.get("text") or "") for row in result.get("content") or [] if row.get("type") == "text").strip()
        else:
            choices = result.get("choices") or []
            answer = str((((choices[0] if choices else {}).get("message") or {}).get("content")) or "").strip()
        if not answer:
            raise RuntimeError("Model service returned no assistant text")
        return {"status": "ok", "answer": answer, "model": model, "provider": provider}

    @staticmethod
    def user_key(headers, remote_address: str = "", client_id: str = "") -> str:
        candidates = [
            headers.get("X-Taihu-User"),
            headers.get("X-WOA-User"),
            headers.get("X-Auth-Request-User"),
            headers.get("X-Forwarded-User"),
            headers.get("X-User"),
        ]
        identity = next((str(value).strip() for value in candidates if str(value or "").strip()), "")
        clean_client_id = str(client_id or "").strip().lower()
        if not identity and re.fullmatch(r"[a-f0-9-]{32,64}", clean_client_id):
            identity = "client:" + clean_client_id
        if not identity:
            identity = "local:" + (remote_address or "unknown")
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]

    def domestic_collector_available(self) -> bool:
        supervisor = Path(os.environ.get("CWH_MEDIASPIDER_SUPERVISOR") or "/app/mediaspider-supervisor")
        media_home = Path(os.environ.get("CWH_MEDIASPIDER_HOME") or "/app/MediaSpider")
        return (supervisor / "scripts/run_task.py").exists() and (media_home / "main.py").exists()

    def _user_session_root(self, user_key: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{24}", user_key):
            raise ValueError("Invalid user session key")
        root = (self.session_root / user_key).resolve()
        if root.parent != self.session_root:
            raise ValueError("Invalid user session root")
        root.mkdir(parents=True, exist_ok=True)
        return root

    @staticmethod
    def _session_state_path(directory: Path) -> Path:
        return directory / "state.json"

    def _write_session_state(self, directory: Path, **changes) -> dict:
        with self._session_lock:
            path = self._session_state_path(directory)
            current = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            current.update(changes)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporary, path)
        return current

    def _session_directory(self, user_key: str, session_id: str) -> Path:
        root = self._user_session_root(user_key) / "runs"
        directory = (root / session_id).resolve()
        if directory.parent != root.resolve() or not directory.exists():
            raise FileNotFoundError("Platform session not found")
        return directory

    def platform_sessions(self, user_key: str) -> dict:
        root = self._user_session_root(user_key)
        rows = []
        for path in sorted((root / "runs").glob("*/state.json"), key=lambda item: item.stat().st_mtime_ns, reverse=True) if (root / "runs").exists() else []:
            try:
                rows.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        latest = {}
        for row in rows:
            platform = str(row.get("platform") or "")
            if row.get("status") in {"starting", "awaiting_scan", "awaiting_verification"}:
                session_id = str(row.get("session_id") or "")
                with self._session_lock:
                    running = session_id in self._session_processes and self._session_processes[session_id].poll() is None
                if not running:
                    row["status"] = "failed"
                    row["message"] = "服务重启后原扫码会话已失效，请重新连接。"
                    state_path = root / "runs" / session_id / "state.json"
                    if state_path.exists():
                        self._write_session_state(state_path.parent, **row)
            if platform and platform not in latest:
                latest[platform] = row
        return {"status": "ok", "available": self.domestic_collector_available(), "sessions": latest}

    def start_platform_session(self, user_key: str, platform: str) -> dict:
        platform = str(platform or "").strip().lower()
        if platform not in SUPPORTED_DOMESTIC_PLATFORMS:
            raise ValueError("Unsupported domestic platform")
        if not self.domestic_collector_available():
            raise ValueError("The full MediaSpider browser runtime is not installed in this deployment")
        current = self.platform_sessions(user_key).get("sessions", {}).get(platform) or {}
        if current.get("status") in {"starting", "awaiting_scan", "awaiting_verification"}:
            session_id = str(current.get("session_id") or "")
            started_at = str(current.get("started_at") or "")
            try:
                age_seconds = (datetime.now() - datetime.fromisoformat(started_at)).total_seconds()
            except (TypeError, ValueError):
                age_seconds = 10**9
            stale_after = max(90, int(os.environ.get("CWH_QR_TIMEOUT_SEC") or 180) + 45)
            if age_seconds <= stale_after:
                return current
            with self._session_lock:
                stale_process = self._session_processes.get(session_id)
            if stale_process and stale_process.poll() is None:
                stale_process.terminate()
            try:
                stale_directory = self._session_directory(user_key, session_id)
                self._write_session_state(
                    stale_directory,
                    status="failed",
                    message="登录会话启动超时，已自动清理，请重新连接。",
                )
            except FileNotFoundError:
                pass
        user_root = self._user_session_root(user_key)
        session_id = uuid.uuid4().hex
        directory = user_root / "runs" / session_id
        directory.mkdir(parents=True, exist_ok=False)
        profile = user_root / "profiles"
        profile.mkdir(parents=True, exist_ok=True)
        raw = directory / "raw"
        raw.mkdir()
        task = {
            "collector": "domestic",
            "platform": platform,
            "crawler_type": "search",
            "login_type": "qrcode",
            "keywords": "国务院常务会议",
            "get_comment": False,
            "get_sub_comment": False,
            "max_posts": 1,
            "max_comments_per_post": 1,
            "max_concurrency": 1,
            "save_data_option": "jsonl",
            "save_data_path": str(raw),
            "headless": True,
            "run_dir": str(directory / "supervisor_run"),
        }
        task_path = directory / "task.json"
        task_path.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
        state = self._write_session_state(
            directory,
            session_id=session_id,
            platform=platform,
            status="starting",
            qr_ready=False,
            login_protocol=PLATFORM_LOGIN_PROTOCOL_VERSION,
            started_at=datetime.now().isoformat(timespec="seconds"),
            message="正在启动平台登录页…",
        )
        media_home = Path(os.environ.get("CWH_MEDIASPIDER_HOME") or "/app/MediaSpider")
        env = os.environ.copy()
        env["MEDIASPIDER_HOME"] = str(media_home)
        env.setdefault("PYTHONIOENCODING", "utf-8")
        media_python = media_home / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
        if not media_python.exists():
            media_python = Path(sys.executable)
        command = [
            str(media_python),
            str(SCRIPT_DIR / "platform_qr_login.py"),
            "--platform", platform,
            "--profile", str((profile / f"{platform}_user_data_dir").resolve()),
            "--qr-path", str(directory / "qrcode.png"),
            "--state-path", str(self._session_state_path(directory)),
            "--action-path", str(directory / "actions.jsonl"),
            "--timeout-sec", str(max(60, int(os.environ.get("CWH_QR_TIMEOUT_SEC") or 180))),
        ]
        log_path = directory / "login.log"
        log = log_path.open("w", encoding="utf-8", errors="replace")
        process = subprocess.Popen(
            command,
            cwd=str(media_home),
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            env=env,
        )
        with self._session_lock:
            self._session_processes[session_id] = process
        self._write_session_state(directory, process_id=process.pid, log_path=str(log_path))
        threading.Thread(
            target=self._monitor_platform_session,
            args=(directory, process, log),
            daemon=True,
            name=f"cwh-platform-{platform}-{session_id[:8]}",
        ).start()
        return state

    def _monitor_platform_session(self, directory: Path, process: subprocess.Popen, log) -> None:
        session_id = directory.name
        success_markers = ("login successful", "login success", "account logged in", "login state is valid")
        failure_markers = ("login failed", "failed by qrcode", "have not found qrcode", "captcha", "risk control")
        connected = False
        started_monotonic = time.monotonic()
        launch_timeout = max(45, int(os.environ.get("CWH_BROWSER_LAUNCH_TIMEOUT_SEC") or 90))
        startup_timeout = max(60, int(os.environ.get("CWH_BROWSER_STARTUP_TIMEOUT_SEC") or (launch_timeout + 15)))
        hard_timeout = max(90, int(os.environ.get("CWH_QR_TIMEOUT_SEC") or 180) + 45)
        try:
            while process.poll() is None:
                elapsed = time.monotonic() - started_monotonic
                try:
                    current_state = json.loads(self._session_state_path(directory).read_text(encoding="utf-8"))
                except (OSError, ValueError, json.JSONDecodeError):
                    current_state = {}
                if current_state.get("status") == "starting" and elapsed > startup_timeout:
                    process.terminate()
                    self._write_session_state(
                        directory,
                        status="failed",
                        message="平台登录浏览器启动超时，请重新连接；如持续出现，请检查平台风控或浏览器运行环境。",
                    )
                    break
                if elapsed > hard_timeout:
                    process.terminate()
                    self._write_session_state(
                        directory,
                        status="failed",
                        message="平台登录浏览器启动或扫码等待超时，请重新连接。",
                    )
                    break
                if current_state.get("status") == "connected":
                    connected = True
                text = (directory / "login.log").read_text(encoding="utf-8", errors="replace").lower() if (directory / "login.log").exists() else ""
                if any(marker in text for marker in success_markers):
                    connected = True
                    self._write_session_state(
                        directory,
                        status="connected",
                        qr_ready=(directory / "qrcode.png").exists(),
                        connected_at=datetime.now().isoformat(timespec="seconds"),
                        message="账号已连接，后续报告可复用该浏览器会话。",
                    )
                elif any(marker in text for marker in failure_markers):
                    self._write_session_state(directory, status="failed", message="平台登录未完成，请刷新二维码后重试。")
                time.sleep(1)
            return_code = process.returncode
            text = (directory / "login.log").read_text(encoding="utf-8", errors="replace").lower() if (directory / "login.log").exists() else ""
            try:
                connected = connected or json.loads(self._session_state_path(directory).read_text(encoding="utf-8")).get("status") == "connected"
            except (OSError, ValueError, json.JSONDecodeError):
                pass
            connected = connected or any(marker in text for marker in success_markers)
            if connected:
                self._write_session_state(directory, status="connected", return_code=return_code, message="账号已连接，后续报告可复用该浏览器会话。")
            else:
                self._write_session_state(directory, status="failed", return_code=return_code, message="扫码会话已结束但未确认登录成功，请重试。")
        finally:
            log.close()
            with self._session_lock:
                self._session_processes.pop(session_id, None)

    def platform_session_status(self, user_key: str, session_id: str, *, embed_images: bool = False) -> dict:
        directory = self._session_directory(user_key, session_id)
        state = json.loads(self._session_state_path(directory).read_text(encoding="utf-8"))
        if state.get("status") == "starting":
            try:
                age_seconds = (datetime.now() - datetime.fromisoformat(str(state.get("started_at") or ""))).total_seconds()
            except (TypeError, ValueError):
                age_seconds = 10**9
            launch_timeout = max(45, int(os.environ.get("CWH_BROWSER_LAUNCH_TIMEOUT_SEC") or 90))
            startup_timeout = max(60, int(os.environ.get("CWH_BROWSER_STARTUP_TIMEOUT_SEC") or (launch_timeout + 15)))
            if age_seconds > startup_timeout:
                with self._session_lock:
                    process = self._session_processes.get(session_id)
                if process and process.poll() is None:
                    process.terminate()
                log_path = directory / "login.log"
                log_tail = log_path.read_text(encoding="utf-8", errors="replace")[-1200:].strip() if log_path.exists() else ""
                message = "平台登录浏览器启动超时，请重新连接。"
                if log_tail:
                    message += f" 后台信息：{log_tail[-500:]}"
                state = self._write_session_state(directory, status="failed", message=message)
        qr_path = directory / "qrcode.png"
        preview_path = directory / "login_page_preview.png"
        state["qr_url"] = f"/api/platform-sessions?kind=qr&session_id={quote(session_id)}" if qr_path.exists() else ""
        state["preview_url"] = f"/api/platform-sessions?kind=preview&session_id={quote(session_id)}" if preview_path.exists() else ""
        if embed_images:
            state["qr_data_url"] = self._image_data_url(qr_path)
            state["preview_data_url"] = self._image_data_url(preview_path)
        return state

    @staticmethod
    def _image_data_url(path: Path) -> str:
        if not path.exists():
            return ""
        mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    def platform_session_qr(self, user_key: str, session_id: str) -> Path:
        path = self._session_directory(user_key, session_id) / "qrcode.png"
        if not path.exists():
            raise FileNotFoundError("QR code is not ready")
        return path

    def platform_session_preview(self, user_key: str, session_id: str) -> Path:
        path = self._session_directory(user_key, session_id) / "login_page_preview.png"
        if not path.exists():
            raise FileNotFoundError("Login page preview is not ready")
        return path

    def platform_session_action(self, user_key: str, payload: dict) -> dict:
        session_id = str(payload.get("session_id") or "")
        directory = self._session_directory(user_key, session_id)
        action_type = str(payload.get("type") or "")
        if action_type not in {"click", "drag"}:
            raise ValueError("Only user-performed click and drag actions are supported")
        clean = {"type": action_type, "start": {}, "end": {}, "created_at": datetime.now().isoformat(timespec="seconds")}
        for key in ("start", "end"):
            point = payload.get(key) or {}
            x = max(0.0, min(1280.0, float(point.get("x"))))
            y = max(0.0, min(900.0, float(point.get("y"))))
            clean[key] = {"x": x, "y": y}
        action_path = directory / "actions.jsonl"
        with self._session_lock:
            with action_path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(clean, ensure_ascii=False) + "\n")
        return {"status": "ok", "message": "已将你的拖动操作发送到平台登录页。"}

    def stop_platform_session(self, user_key: str, session_id: str) -> dict:
        directory = self._session_directory(user_key, session_id)
        with self._session_lock:
            process = self._session_processes.get(session_id)
        if process and process.poll() is None:
            process.terminate()
        return self._write_session_state(directory, status="stopped", message="扫码会话已停止。")

    def _job_directory(self, job_id: str) -> Path:
        directory = (self.import_root / job_id).resolve()
        if directory.parent != self.import_root or not directory.exists():
            raise FileNotFoundError("Import job not found")
        return directory

    def _read_manifest(self, directory: Path) -> dict:
        return json.loads((directory / "manifest.json").read_text(encoding="utf-8"))

    def _update_manifest(self, directory: Path, **changes) -> dict:
        with self._manifest_lock:
            manifest = self._read_manifest(directory)
            manifest.update(changes)
            manifest_path = directory / "manifest.json"
            atomic_write_json(manifest_path, manifest)
        return manifest

    @classmethod
    def _steps(cls, active: int = -1, complete_before: int = 0, *, failed: int = -1) -> list[dict[str, str]]:
        rows = []
        for index, label in enumerate(cls.WORKBOOK_STEPS):
            if index == failed:
                status = "error"
            elif index < complete_before:
                status = "complete"
            elif index == active:
                status = "running"
            else:
                status = "pending"
            rows.append({"label": label, "status": status})
        return rows

    def _current_report_data(self) -> dict:
        path = self.dashboard.parent / "report_data.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _topic_aliases(title: str, configured: list[str]) -> list[str]:
        aliases: list[str] = []
        for value in [*configured, title]:
            cleaned = str(value or "").strip().strip("《》‘’\"'。；;，,")
            if cleaned and cleaned not in aliases:
                aliases.append(cleaned)
        shortened = re.sub(r"^(进一步部署|听取|研究|审议通过)", "", title)
        shortened = re.sub(r"(有关工作|进展情况汇报|情况汇报|工作)$", "", shortened).strip("《》‘’\"'。；;，, ")
        if shortened and shortened not in aliases:
            aliases.append(shortened)
        return aliases

    def _raw_metadata(self, manifest: dict) -> dict:
        data = self._current_report_data()
        meeting = data.get("meeting") or {}
        topics = [str(value).strip() for value in meeting.get("topics") or [] if str(value).strip()]
        keywords = meeting.get("topic_keywords") or {}
        agenda = str(manifest.get("agenda") or meeting.get("agenda") or "").strip()
        if re.search(r"(进一步部署|部署|听取|研究|审议通过|审议|决定)", agenda):
            from cwh_orchestrator import infer_topics

            inferred_topics = [str(value).strip() for value in infer_topics(agenda) if str(value).strip()]
            if inferred_topics and inferred_topics != ["本次国务院常务会议"]:
                topics = inferred_topics
        if not topics:
            raise ValueError("当前工作台没有子议题信息，无法匹配原始子事件表。")
        date = str(meeting.get("date") or "").strip()
        if agenda:
            from cwh_orchestrator import normalize_date

            date = normalize_date(agenda) or date
        meeting_title = f"{chinese_date(date)}国务院常务会议" if date else agenda
        return {
            "meeting_title": meeting_title or "国务院常务会议",
            "event_sheet_title": agenda or meeting_title or "国务院常务会议",
            "topic_titles": topics,
            "topic_aliases": [
                self._topic_aliases(topic, [str(value) for value in keywords.get(topic, [])])
                for topic in topics
            ],
        }

    @staticmethod
    def _is_standard_workbook(profile: dict) -> str:
        required = {"关键词", "总事件", "子事件数据汇总"}
        for row in profile.get("files") or []:
            structure = row.get("structure") or {}
            sheet_names = {str(sheet.get("name") or "") for sheet in structure.get("sheets") or []}
            if required.issubset(sheet_names) and any(re.fullmatch(r"子事件\d+", name) for name in sheet_names):
                return str(row.get("name") or "")
        return ""

    @staticmethod
    def _excel_protocol(path: Path) -> str:
        return "ms-excel:ofe|u|" + path.resolve().as_uri()

    def _workbook_environment(self) -> tuple[str, dict[str, str]]:
        env = os.environ.copy()
        if os.name != "nt":
            node = shutil.which("node")
            if node:
                env["CWH_NODE_PATH"] = node
            env.setdefault("CWH_PORTABLE_XLSX", "1")
            return sys.executable, env
        dependencies = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies"
        python = dependencies / "python/python.exe"
        node = dependencies / "node/bin/node.exe"
        node_modules = dependencies / "node/node_modules"
        path_entries = [
            dependencies / "python",
            dependencies / "node/bin",
            dependencies / "bin/override",
            dependencies / "bin/fallback",
        ]
        env["PATH"] = os.pathsep.join([str(path) for path in path_entries if path.exists()] + [env.get("PATH", "")])
        if node.exists():
            env["CWH_NODE_PATH"] = str(node)
        if node_modules.exists():
            env["NODE_PATH"] = str(node_modules) + (os.pathsep + env["NODE_PATH"] if env.get("NODE_PATH") else "")
        return (str(python) if python.exists() else sys.executable), env

    @staticmethod
    def _artifact_candidate(value: object, fallback: Path, directory: Path) -> Path:
        raw = str(value or "").strip()
        if raw and (re.match(r"^[A-Za-z]:[\\/]", raw) or "\\" in raw):
            # Reports are commonly generated on Windows and then deployed to
            # With's Linux runtime. Rebind a Windows artifact path to the
            # self-contained report directory before pathlib interprets the
            # drive-prefixed string as a relative Linux filename.
            rebound = (directory / PureWindowsPath(raw).name).resolve()
            if rebound.exists():
                return rebound
        candidate = Path(raw) if raw else fallback
        if not candidate.is_absolute():
            candidate = directory / candidate
        candidate = candidate.resolve()
        if candidate.exists() and (candidate.parent == directory or directory in candidate.parents):
            return candidate
        # Database-restored reports may retain absolute paths from the
        # container that originally generated them. Rebind those paths to the
        # restored report directory by filename before indexing or editing.
        restored = (directory / candidate.name).resolve()
        if restored.exists():
            return restored
        return fallback.resolve() if fallback.exists() else candidate

    def _index_report_data(self, data_path: Path, *, reason: str = "index") -> None:
        data_path = data_path.resolve()
        directory = data_path.parent
        if self.import_root in directory.parents:
            return
        try:
            data = json.loads(data_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return
        meeting = data.get("meeting") or {}
        meeting_date = str(meeting.get("date") or "")
        title = f"{chinese_date(meeting_date)}国务院常务会议舆情情况" if meeting_date else directory.name
        period = str(((data.get("system_data") or {}).get("monitoring_period") or {}).get("label") or "")
        topics = [str(item) for item in (meeting.get("topics") or []) if str(item).strip()]
        rid = report_id(directory)
        rid = self.archive_store.canonical_report_id(rid, meeting_date, directory)
        marker = directory / ".cwh_report_id"
        if not marker.exists() or marker.read_text(encoding="ascii", errors="ignore").strip() != rid:
            marker.write_text(rid, encoding="ascii")
        artifacts = data.get("artifacts") or {}
        candidates = [
            ("report", "dashboard", "工作台", directory / "cwh_dashboard.html"),
            ("report", "word", "正式报告 Word", self._artifact_candidate(artifacts.get("formal_docx"), directory / "cwh_formal_report.docx", directory)),
            ("internal", "report_data", "结构化报告数据", data_path),
        ]
        indexed_artifacts = [
            {
                "category": category,
                "kind": kind,
                "display_name": display_name,
                "path": path,
            }
            for category, kind, display_name, path in candidates
            if path.exists() and path.is_file() and (path.parent == directory or directory in path.parents)
        ]
        with self._archive_lock:
            self.archive_store.upsert_report(
                {
                    "id": rid,
                    "meeting_date": meeting_date,
                    "title": title,
                    "monitoring_period": period,
                    "agenda": str(meeting.get("agenda") or ""),
                    "topic_text": "；".join(topics),
                    "report_data_path": str(data_path),
                    "modified_ns": data_path.stat().st_mtime_ns,
                },
                indexed_artifacts,
                directory,
                reason=reason,
            )

    def _report_data_candidates(self):
        yield self.dashboard.parent / "report_data.json"
        skipped = {
            ".git",
            "__pycache__",
            "node_modules",
            "tools",
            "MediaSpider",
            "mediaspider-supervisor",
            "cwh-report-skill",
            "_dashboard_imports",
            "_platform_sessions",
            "_archive_cache",
        }
        for root, directories, files in os.walk(self.library_root):
            directories[:] = [name for name in directories if name not in skipped and not name.startswith(".tmp")]
            if "report_data.json" in files:
                yield Path(root) / "report_data.json"

    def _archive_candidate(self, data_path: Path) -> dict | None:
        """Return lightweight selection metadata for one report directory.

        Archive scans can encounter many generated copies of the same meeting.
        Selecting a winner before upsert keeps the canonical report identity
        from moving once per filesystem candidate and avoids repeatedly
        compressing obsolete report bundles during a cold scan.
        """

        try:
            resolved = data_path.resolve()
        except OSError:
            return None
        directory = resolved.parent
        if self.import_root in directory.parents:
            return None
        try:
            data = json.loads(resolved.read_text(encoding="utf-8"))
            modified_ns = resolved.stat().st_mtime_ns
        except (OSError, ValueError, json.JSONDecodeError):
            return None
        meeting = data.get("meeting") or {}
        meeting_date = str(meeting.get("date") or "").strip()
        artifacts = data.get("artifacts") or {}
        dashboard = directory / "cwh_dashboard.html"
        word = self._artifact_candidate(
            artifacts.get("formal_docx"),
            directory / "cwh_formal_report.docx",
            directory,
        )
        word_is_local = word.exists() and word.is_file() and (word.parent == directory or directory in word.parents)
        dashboard_is_local = dashboard.exists() and dashboard.is_file()
        ready = bool((((data.get("audit") or {}).get("acceptance") or {}).get("ready_for_formal_delivery")))
        current_data = (self.dashboard.parent / "report_data.json").resolve()
        current = resolved == current_data
        meeting_key = f"meeting:{meeting_date}" if meeting_date else f"path:{str(resolved).lower()}"
        priority = (
            int(current),
            int(ready),
            int(word_is_local and dashboard_is_local),
            int(word_is_local),
            int(dashboard_is_local),
            int(modified_ns),
            str(resolved).lower(),
        )
        return {
            "path": resolved,
            "meeting_key": meeting_key,
            "priority": priority,
        }

    def _selected_archive_candidates(self) -> list[Path]:
        seen: set[Path] = set()
        selected: dict[str, dict] = {}
        for data_path in self._report_data_candidates():
            candidate = self._archive_candidate(data_path)
            if not candidate:
                continue
            resolved = candidate["path"]
            if resolved in seen:
                continue
            seen.add(resolved)
            key = str(candidate["meeting_key"])
            previous = selected.get(key)
            if previous is None or candidate["priority"] > previous["priority"]:
                selected[key] = candidate
        return [
            item["path"]
            for item in sorted(selected.values(), key=lambda row: (str(row["meeting_key"]), str(row["path"]).lower()))
        ]

    def _sync_archive(self) -> None:
        with self._archive_sync_lock:
            if time.time() - self._archive_last_sync < 30:
                return
            for data_path in self._selected_archive_candidates():
                self._index_report_data(data_path)
            self._archive_last_sync = time.time()

    def archive(self, search: str = "") -> dict:
        self._index_report_data(self.dashboard.parent / "report_data.json")
        self._sync_archive()
        rows = self.archive_store.search_reports(str(search or ""))
        artifact_rows = self.archive_store.list_artifacts()
        artifacts_by_report: dict[str, dict[str, dict]] = {}
        for item in artifact_rows:
            artifacts_by_report.setdefault(str(item["report_id"]), {})[str(item["kind"])] = item
        by_period: dict[str, dict] = {}
        current_directory = self.dashboard.parent.resolve()
        for row in rows:
            key = str(row["meeting_date"] or row["title"])
            current = by_period.get(key)
            row_is_current = Path(str(row["directory"])).resolve() == current_directory
            current_is_current = bool(current and Path(str(current["directory"])).resolve() == current_directory)
            if current is None or (row_is_current, int(row["modified_ns"])) > (current_is_current, int(current["modified_ns"])):
                by_period[key] = row
        reports = []
        for row in by_period.values():
            rid = str(row["id"])
            indexed = artifacts_by_report.get(rid, {})
            dashboard = indexed.get("dashboard")
            word = indexed.get("word")
            common = {
                "id": rid,
                "date": str(row["meeting_date"]),
                "title": str(row["title"]),
                "period": str(row["monitoring_period"]),
                "topics": [item for item in str(row["topic_text"]).split("；") if item],
                "current": Path(str(row["directory"])).resolve() == current_directory,
            }
            reports.append({
                **common,
                "dashboard": f"/reports/{rid}/{quote(str(dashboard['file_name']))}" if dashboard else "",
                "word": f"/api/archive/artifact?report_id={quote(rid)}&kind=word" if word else "",
            })
        reports.sort(key=lambda row: row["date"], reverse=True)
        return {"reports": reports, "counts": {"reports": len(reports)}}

    def reports(self) -> list[dict[str, object]]:
        return self.archive().get("reports") or []

    def archive_artifact(self, rid: str, kind: str) -> Path:
        self._sync_archive()
        report_row = self.archive_store.get_report(rid)
        artifact_row = self.archive_store.artifact(rid, kind)
        if not report_row or not artifact_row:
            raise FileNotFoundError("Archive artifact not found")
        directory = self.report_directory(rid)
        if not directory:
            raise FileNotFoundError("Archive report not found")
        relative = str(artifact_row.get("relative_path") or artifact_row.get("file_name") or "")
        path = (directory / relative).resolve()
        if path != directory and directory not in path.parents:
            raise ValueError("Archive artifact path is outside the restored report")
        if not path.exists() or not path.is_file():
            raise FileNotFoundError("Archive artifact not found")
        return path

    def report_directory(self, rid: str) -> Path | None:
        row = self.archive_store.get_report(rid)
        if not row:
            self._sync_archive()
            row = self.archive_store.get_report(rid)
        if not row:
            return None
        preferred = Path(str(row.get("directory") or "")).resolve()
        return self.archive_store.hydrate(
            rid,
            self.library_root / "_archive_cache",
            preferred=preferred,
        )

    def storage_status(self) -> dict:
        return self.archive_store.status()

    def report_versions(self, rid: str) -> dict:
        if not self.archive_store.get_report(rid):
            raise FileNotFoundError("Report not found")
        return {"report_id": rid, "versions": self.archive_store.versions(rid)}

    def save_section(self, rid: str, payload: dict) -> dict:
        directory = self.report_directory(rid)
        if not directory:
            raise FileNotFoundError("Report not found")
        key = str(payload.get("section") or "")
        if key not in {"one", "two", "three", "four"}:
            raise ValueError("Invalid section")
        blocks = payload.get("blocks")
        if not isinstance(blocks, list):
            raise ValueError("blocks must be a list")
        cleaned = [
            {"role": str(row.get("role") or "p"), "text": str(row.get("text") or "").strip()}
            for row in blocks if isinstance(row, dict) and str(row.get("text") or "").strip()
        ]
        data_path = directory / "report_data.json"
        data = json.loads(data_path.read_text(encoding="utf-8"))
        data.setdefault("section_overrides", {})[key] = cleaned
        data.setdefault("edit_history", []).append({
            "section": key,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "block_count": len(cleaned),
        })
        from formalize_cwh_report import audit_formal_docx, write_docx
        from generate_dashboard import generate_dashboard

        word_path = Path(str((data.get("artifacts") or {}).get("formal_docx") or directory / "cwh_formal_report.docx"))
        if not word_path.is_absolute():
            word_path = directory / word_path
        word_path.parent.mkdir(parents=True, exist_ok=True)
        write_docx(data, word_path)
        data.setdefault("artifacts", {})["formal_docx"] = str(word_path)
        data.setdefault("audit", {})["formal_docx_validation"] = audit_formal_docx(data, word_path)
        data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        generate_dashboard(data, directory / "cwh_dashboard.html")
        self._index_report_data(data_path, reason="section_edit")
        return {
            "status": "saved",
            "section": key,
            "saved_at": data["edit_history"][-1]["saved_at"],
            "word": f"/reports/{rid}/{quote(word_path.name)}",
        }

    def preview_hotwords(self, rid: str, payload: dict) -> dict:
        directory = self.report_directory(rid)
        if not directory:
            raise FileNotFoundError("Report not found")
        data_path = directory / "report_data.json"
        data = json.loads(data_path.read_text(encoding="utf-8"))
        items, unsupported = normalize_manual_hotwords(
            data,
            payload.get("items"),
            payload.get("baseline_words"),
        )
        audit = manual_hotword_payload(items)
        token = uuid.uuid4().hex[:16]
        image_path = directory / f".hotword_preview_{token}.png"
        preview_path = directory / f".hotword_preview_{token}.json"
        preview_path.write_text(
            json.dumps(
                {
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "status": "queued",
                    "items": items,
                    "unsupported": unsupported,
                    "audit": audit,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        subprocess.Popen(
            [
                sys.executable,
                str(SCRIPT_DIR / "render_hotword_preview.py"),
                str(preview_path),
                str(image_path),
            ],
            cwd=str(directory),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {
            "status": "queued",
            "token": token,
            "item_count": len(items),
        }

    def hotword_preview_status(self, rid: str, payload: dict) -> dict:
        directory = self.report_directory(rid)
        if not directory:
            raise FileNotFoundError("Report not found")
        token = str(payload.get("token") or "").strip().lower()
        if not re.fullmatch(r"[a-f0-9]{16}", token):
            raise ValueError("无效的词云预览任务")
        preview_path = directory / f".hotword_preview_{token}.json"
        if not preview_path.exists():
            raise FileNotFoundError("词云预览任务不存在")
        try:
            preview = json.loads(preview_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"status": "running", "token": token}
        result = {"status": str(preview.get("status") or "queued"), "token": token}
        if result["status"] == "failed":
            result["error"] = str(preview.get("error") or "词云生成失败")
        if result["status"] == "complete":
            result.update(
                {
                    "items": [
                        {
                            "word": row["word"],
                            "topic": row.get("topic") or "",
                            "weight": int(row.get("display_weight") or row.get("count") or 1),
                        }
                        for row in (preview.get("items") or [])
                    ],
                    "unsupported": list(preview.get("unsupported") or []),
                    "image": f"/reports/{rid}/{quote(f'.hotword_preview_{token}.png')}",
                }
            )
        return result

    def save_hotwords(self, rid: str, payload: dict) -> dict:
        directory = self.report_directory(rid)
        if not directory:
            raise FileNotFoundError("Report not found")
        token = str(payload.get("token") or "").strip().lower()
        if not re.fullmatch(r"[a-f0-9]{16}", token):
            raise ValueError("请先重新生成词云预览")
        preview_path = directory / f".hotword_preview_{token}.json"
        image_path = directory / f".hotword_preview_{token}.png"
        if not preview_path.exists() or not image_path.exists():
            raise FileNotFoundError("词云预览已失效，请重新生成")

        preview = json.loads(preview_path.read_text(encoding="utf-8"))
        if preview.get("status") != "complete":
            raise ValueError("词云预览尚未完成")
        data_path = directory / "report_data.json"
        data = json.loads(data_path.read_text(encoding="utf-8"))
        data["hotwords"] = list(preview.get("items") or [])
        audit = dict(preview.get("audit") or {})
        audit["saved_at"] = datetime.now().isoformat(timespec="seconds")
        audit["unsupported_terms"] = list(preview.get("unsupported") or [])
        audit_path = directory / "hotword_audit.json"
        audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")

        chart_dir = directory / "charts"
        chart_dir.mkdir(parents=True, exist_ok=True)
        wordcloud_path = chart_dir / "hotword_distribution_pipeline.png"
        shutil.copyfile(image_path, wordcloud_path)
        artifacts = data.setdefault("artifacts", {})
        artifacts["wordcloud_image"] = str(wordcloud_path)
        artifacts["hotword_audit"] = str(audit_path)
        artifacts.setdefault("docx_charts", {})["hotword_distribution"] = str(wordcloud_path)

        from formalize_cwh_report import formalize_report, hotword_paragraph
        from generate_dashboard import generate_dashboard

        two_override = data.setdefault("section_overrides", {}).get("two")
        if isinstance(two_override, list):
            for index, row in enumerate(two_override):
                if row.get("role") == "h2" and "热词分布" in str(row.get("text") or ""):
                    replacement = {"role": "p", "text": hotword_paragraph(data)}
                    if index + 1 < len(two_override) and two_override[index + 1].get("role") == "p":
                        two_override[index + 1] = replacement
                    else:
                        two_override.insert(index + 1, replacement)
                    break

        saved_at = datetime.now().isoformat(timespec="seconds")
        data.setdefault("edit_history", []).append(
            {
                "section": "hotwords",
                "saved_at": saved_at,
                "hotword_count": len(data["hotwords"]),
                "unsupported_count": len(preview.get("unsupported") or []),
            }
        )
        formalize_report(data, directory)
        data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        generate_dashboard(data, directory / "cwh_dashboard.html")
        self._index_report_data(data_path, reason="hotword_edit")

        for stale in directory.glob(".hotword_preview_*"):
            try:
                stale.unlink()
            except OSError:
                pass
        return {
            "status": "saved",
            "saved_at": saved_at,
            "hotword_count": len(data["hotwords"]),
            "unsupported": list(preview.get("unsupported") or []),
            "word": f"/reports/{rid}/cwh_formal_report.docx",
        }

    def start_import(self, payload: dict) -> dict:
        job_id = datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8]
        directory = self.import_root / job_id
        (directory / "files").mkdir(parents=True)
        manifest = {
            "job_id": job_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "agenda": str(payload.get("agenda") or "").strip(),
            "files": [],
            "status": "uploading",
            "progress": 0,
            "steps": self._steps(),
        }
        (directory / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest

    def upload_file(self, job_id: str, name: str, content: bytes) -> dict:
        directory = self._job_directory(job_id)
        safe_name = Path(unquote(name)).name
        if not safe_name:
            raise ValueError("Missing filename")
        target = directory / "files" / safe_name
        if target.exists():
            target = target.with_name(f"{target.stem}_{uuid.uuid4().hex[:6]}{target.suffix}")
        target.write_bytes(content)
        manifest_path = directory / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"].append({"name": target.name, "size": len(content), "path": str(target)})
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"status": "uploaded", "name": target.name, "size": len(content), "file_count": len(manifest["files"])}

    def commit_import(self, job_id: str) -> dict:
        directory = self._job_directory(job_id)
        manifest_path = directory / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError("Import job not found")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not manifest.get("files"):
            raise ValueError("No files were uploaded")
        from profile_cwh_import import profile_files

        profile = profile_files(directory / "files")
        updates = {
            "profiled_at": datetime.now().isoformat(timespec="seconds"),
            "profile": profile,
            "runner_enabled": True,
            "report_runner": self.report_runner,
            "progress": 12,
            "steps": self._steps(active=1, complete_before=1),
        }
        output_dir = self.library_root / f"cwh_workbook_{job_id}"
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest = self._update_manifest(
            directory,
            **updates,
            status="workbook_queued",
            queued_at=datetime.now().isoformat(timespec="seconds"),
            workbook_output_dir=str(output_dir),
            message="文件已上传，正在准备处理。",
        )
        threading.Thread(
            target=self._run_workbook_job,
            args=(directory, output_dir),
            daemon=True,
            name=f"cwh-workbook-{job_id}",
        ).start()
        return manifest

    def _run_workbook_job(self, directory: Path, output_dir: Path) -> None:
        manifest = self._update_manifest(
            directory,
            status="workbook_running",
            started_at=datetime.now().isoformat(timespec="seconds"),
            progress=18,
            steps=self._steps(active=1, complete_before=1),
            message="正在匹配总事件、子事件和样本表。",
        )
        workbook_path = output_dir / "CWH舆情情况_自动生成.xlsx"
        audit_path = output_dir / "comparison_audit.md"
        log_path = directory / "workbook_run.log"
        metadata_path = directory / "run_metadata.json"
        try:
            standard_name = self._is_standard_workbook(manifest.get("profile") or {})
            if standard_name:
                source = directory / "files" / standard_name
                shutil.copy2(source, workbook_path)
                audit_path.write_text(
                    "# 标准总表处理记录\n\n"
                    f"- 已识别上传文件 `{standard_name}` 为标准总表。\n"
                    "- 文件包含关键词、总事件、子事件和子事件数据汇总表，未重复计算系统统计。\n",
                    encoding="utf-8",
                )
                self._update_manifest(
                    directory,
                    status="workbook_complete",
                    progress=100,
                    steps=self._steps(complete_before=len(self.WORKBOOK_STEPS)),
                    workbook_path=str(workbook_path),
                    workbook_audit_path=str(audit_path),
                    workbook_protocol=self._excel_protocol(workbook_path),
                    finished_at=datetime.now().isoformat(timespec="seconds"),
                    message="已识别标准总表，可以打开核对或继续生成报告。",
                )
                return

            metadata = self._raw_metadata(manifest)
            metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            self._update_manifest(
                directory,
                progress=28,
                steps=self._steps(active=2, complete_before=2),
                raw_metadata_path=str(metadata_path),
                message="文件匹配完成，正在计算各渠道与子议题传播汇总。",
            )
            python, env = self._workbook_environment()
            command = [
                python,
                str(SCRIPT_DIR / "raw_system_workbook_pipeline.py"),
                "--input-dir", str(directory / "files"),
                "--metadata", str(metadata_path),
                "--output", str(workbook_path),
                "--audit", str(audit_path),
            ]
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            with log_path.open("w", encoding="utf-8", errors="replace") as log:
                process = subprocess.Popen(
                    command,
                    cwd=str(self.workspace),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                    creationflags=creationflags,
                    env=env,
                )
                self._update_manifest(directory, process_id=process.pid, workbook_log_path=str(log_path))
                last_stage = ""
                while process.poll() is None:
                    normalized = output_dir / "run/normalized_raw_workbook.json"
                    hotword_audit = output_dir / "run/hotword_audit.json"
                    verification = output_dir / "run/builder_verification.json"
                    if verification.exists() or workbook_path.exists():
                        stage = "verify"
                        if last_stage != stage:
                            self._update_manifest(
                                directory,
                                progress=84,
                                steps=self._steps(active=5, complete_before=5),
                                message="总表与图表已生成，正在逐表校验。",
                            )
                    elif hotword_audit.exists():
                        stage = "charts"
                        if last_stage != stage:
                            self._update_manifest(
                                directory,
                                progress=66,
                                steps=self._steps(active=4, complete_before=4),
                                message="样本筛选完成，正在生成词云、图表和标准工作簿。",
                            )
                    elif normalized.exists():
                        stage = "filter"
                        if last_stage != stage:
                            self._update_manifest(
                                directory,
                                progress=48,
                                steps=self._steps(active=3, complete_before=3),
                                message="传播汇总计算完成，正在筛选外媒与公众号样本。",
                            )
                    else:
                        stage = "aggregate"
                    last_stage = stage
                    time.sleep(1)
                return_code = process.returncode

            if return_code == 0 and workbook_path.exists() and audit_path.exists():
                self._update_manifest(
                    directory,
                    status="workbook_complete",
                    progress=100,
                    steps=self._steps(complete_before=len(self.WORKBOOK_STEPS)),
                    workbook_path=str(workbook_path),
                    workbook_audit_path=str(audit_path),
                    workbook_log_path=str(log_path),
                    workbook_protocol=self._excel_protocol(workbook_path),
                    finished_at=datetime.now().isoformat(timespec="seconds"),
                    return_code=return_code,
                    message="原始表已处理为标准总表，可以打开核对或继续生成报告。",
                )
            else:
                current = self._read_manifest(directory)
                failed_index = next(
                    (index for index, row in enumerate(current.get("steps") or []) if row.get("status") == "running"),
                    5,
                )
                self._update_manifest(
                    directory,
                    status="failed",
                    steps=self._steps(complete_before=failed_index, failed=failed_index),
                    finished_at=datetime.now().isoformat(timespec="seconds"),
                    return_code=return_code,
                    workbook_log_path=str(log_path),
                    message="总表处理未完成，请查看处理记录。",
                )
        except Exception as exc:
            current = self._read_manifest(directory)
            failed_index = next(
                (index for index, row in enumerate(current.get("steps") or []) if row.get("status") == "running"),
                1,
            )
            self._update_manifest(
                directory,
                status="failed",
                steps=self._steps(complete_before=failed_index, failed=failed_index),
                finished_at=datetime.now().isoformat(timespec="seconds"),
                workbook_log_path=str(log_path),
                message=f"总表处理失败：{type(exc).__name__}: {exc}",
            )

    def start_report(self, job_id: str, user_key: str = "") -> dict:
        directory = self._job_directory(job_id)
        manifest = self._read_manifest(directory)
        workbook_path = Path(str(manifest.get("workbook_path") or ""))
        resumable_statuses = {
            "workbook_complete",
            "failed",
            "waiting_ai",
            "waiting_login",
            "waiting_review",
            "blocked",
            "interrupted",
            "paused",
        }
        if manifest.get("status") not in resumable_statuses or not workbook_path.exists():
            raise ValueError("请先完成总表处理。")
        if self.report_runner == "codex" and not self.codex_command:
            raise ValueError("未找到本机 Codex 命令，无法生成报告。")
        output_dir = self.library_root / f"cwh_report_{job_id}"
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest = self._update_manifest(
            directory,
            status="report_queued",
            report_output_dir=str(output_dir),
            report_queued_at=datetime.now().isoformat(timespec="seconds"),
            requested_by=user_key,
            message="标准总表已确认，报告生成任务正在排队。",
        )
        targets = {
            "native": self._run_native_report_job,
            "codex": self._run_codex_job,
            "pipeline": self._run_pipeline_job,
        }
        target = targets[self.report_runner]
        threading.Thread(
            target=target,
            args=(directory, output_dir, [workbook_path]),
            daemon=True,
            name=f"cwh-report-{job_id}",
        ).start()
        return manifest

    def import_status(self, job_id: str) -> dict:
        directory = self._job_directory(job_id)
        manifest = self._read_manifest(directory)
        workbook_value = str(manifest.get("workbook_path") or "").strip()
        if workbook_value and Path(workbook_value).exists():
            manifest["workbook_url"] = f"/api/import/artifact?job_id={quote(job_id)}&kind=workbook"
            manifest["workbook_protocol"] = self._excel_protocol(Path(workbook_value))
        output_dir_value = str(manifest.get("report_output_dir") or "").strip()
        output_dir = Path(output_dir_value) if output_dir_value else None
        if output_dir and output_dir.is_dir():
            pipeline_state = output_dir / "pipeline_state.json"
            if pipeline_state.exists():
                try:
                    manifest["pipeline"] = json.loads(pipeline_state.read_text(encoding="utf-8"))
                except (OSError, ValueError, json.JSONDecodeError):
                    manifest["pipeline"] = {"status": "invalid", "message": "管线状态文件无法读取。"}
            dashboards = sorted(output_dir.rglob("cwh_dashboard.html"), key=lambda path: path.stat().st_mtime_ns, reverse=True)
            for dashboard in dashboards:
                report_dir = dashboard.parent.resolve()
                if (report_dir / "report_data.json").exists():
                    rid = report_id(report_dir)
                    manifest["report_id"] = rid
                    manifest["dashboard_url"] = f"/reports/{rid}/{quote(dashboard.name)}"
                    word = report_dir / "cwh_formal_report.docx"
                    if word.exists():
                        manifest["word_url"] = f"/reports/{rid}/{quote(word.name)}"
                    break
        return manifest

    def import_artifact(self, job_id: str, kind: str) -> Path:
        directory = self._job_directory(job_id)
        manifest = self._read_manifest(directory)
        fields = {
            "workbook": "workbook_path",
            "audit": "workbook_audit_path",
            "log": "workbook_log_path",
        }
        field = fields.get(kind)
        if not field:
            raise ValueError("Unknown artifact")
        value = str(manifest.get(field) or "").strip()
        if not value:
            raise FileNotFoundError("Artifact not found")
        path = Path(value).resolve()
        allowed_roots = [directory.resolve(), Path(str(manifest.get("workbook_output_dir") or directory)).resolve()]
        if not any(path == root or root in path.parents for root in allowed_roots):
            raise ValueError("Artifact path is outside this job")
        if not path.exists():
            raise FileNotFoundError("Artifact not found")
        return path

    def _run_native_report_job(
        self,
        directory: Path,
        output_dir: Path,
        source_files: list[Path] | None = None,
    ) -> None:
        manifest = self._update_manifest(
            directory,
            status="report_running",
            report_started_at=datetime.now().isoformat(timespec="seconds"),
            report_runner="native",
            message="正在读取系统总表、生成图表和正式报告。",
        )
        workbook = (source_files or [Path(str(manifest.get("workbook_path") or ""))])[0]
        agenda = str(manifest.get("agenda") or "").strip()
        log_path = directory / "native_report_run.log"
        command = [
            sys.executable,
            str(SCRIPT_DIR / "cwh_orchestrator.py"),
            "--input",
            agenda or "国务院常务会议",
            "--system-workbook",
            str(workbook),
            "--out-dir",
            str(output_dir),
            "--data-mode",
            "system",
            "--no-tasks",
            "--no-agent-reach-plan",
            "--collection-profile",
            "formal",
            "--supplemental-collection",
            "--web-always",
            "--web-limit",
            "8",
        ]
        env = os.environ.copy()
        if self.shared_collectors_enabled():
            command.extend(
                [
                    "--run-foreign-mediaspider",
                    "--foreign-mediaspider-supervisor",
                    env.get("CWH_MEDIASPIDER_SUPERVISOR", "/app/mediaspider-supervisor"),
                    "--foreign-media-home",
                    env.get("CWH_MEDIASPIDER_HOME", "/app/MediaSpider"),
                    "--foreign-mediaspider-platforms",
                    env.get("CWH_FOREIGN_PLATFORMS", "grounding,youtube"),
                    "--foreign-mediaspider-timeout-sec",
                    env.get("CWH_FOREIGN_TIMEOUT_SEC", "300"),
                ]
            )
            user_key = str(manifest.get("requested_by") or "")
            connected = self.platform_sessions(user_key).get("sessions", {}) if user_key else {}
            platforms = [platform for platform in SUPPORTED_DOMESTIC_PLATFORMS if (connected.get(platform) or {}).get("status") == "connected"]
            if platforms and self.domestic_collector_available():
                command.extend(
                    [
                        "--run-mediaspider",
                        "--platforms",
                        ",".join(platforms),
                        "--mediaspider-supervisor",
                        env.get("CWH_MEDIASPIDER_SUPERVISOR", "/app/mediaspider-supervisor"),
                        "--media-home",
                        env.get("CWH_MEDIASPIDER_HOME", "/app/MediaSpider"),
                        "--mediaspider-limit",
                        "0",
                    ]
                )
                user_root = self._user_session_root(user_key)
                env["CWH_BROWSER_PROFILE_TEMPLATE"] = str((user_root / "profiles/%s_user_data_dir").resolve())
                env["CWH_MEDIASPIDER_RUNTIME_ADAPTER"] = str(SCRIPT_DIR / "run_mediaspider_task.py")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            with log_path.open("w", encoding="utf-8", errors="replace") as log:
                process = subprocess.Popen(
                    command,
                    cwd=str(self.workspace),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                    creationflags=creationflags,
                    env=env,
                )
                self._update_manifest(directory, process_id=process.pid, report_log_path=str(log_path))
                return_code = process.wait()
            dashboard = output_dir / "cwh_dashboard.html"
            data_path = output_dir / "report_data.json"
            complete = dashboard.exists() and data_path.exists()
            if complete:
                self.dashboard = dashboard.resolve()
                self._index_report_data(data_path, reason="generation")
                self._update_manifest(
                    directory,
                    status="complete",
                    finished_at=datetime.now().isoformat(timespec="seconds"),
                    return_code=return_code,
                    report_log_path=str(log_path),
                    message="本期报告已生成，可以打开工作台或下载 Word、Excel。",
                )
            else:
                self._update_manifest(
                    directory,
                    status="failed",
                    finished_at=datetime.now().isoformat(timespec="seconds"),
                    return_code=return_code,
                    report_log_path=str(log_path),
                    message="报告任务已结束，但产物不完整，请查看处理记录。",
                )
        except Exception as exc:
            self._update_manifest(
                directory,
                status="failed",
                finished_at=datetime.now().isoformat(timespec="seconds"),
                report_log_path=str(log_path),
                message=f"报告生成失败：{type(exc).__name__}: {exc}",
            )

    def _run_pipeline_job(self, directory: Path, output_dir: Path, source_files: list[Path] | None = None) -> None:
        manifest = self._update_manifest(
            directory,
            status="report_running",
            report_started_at=datetime.now().isoformat(timespec="seconds"),
            report_runner="pipeline",
            message=(
                "管线正在按节点处理数据并调用模型工作器。"
                if self.pipeline_ai_command
                else "管线正在执行确定性节点；遇到AI节点时会保存断点并等待模型接入。"
            ),
        )
        files = [str(path.resolve()) for path in source_files] if source_files else [
            str(Path(row["path"]).resolve()) for row in manifest.get("files", []) if row.get("path")
        ]
        if not files:
            self._update_manifest(
                directory,
                status="failed",
                finished_at=datetime.now().isoformat(timespec="seconds"),
                message="管线缺少标准总表，无法开始报告阶段。",
            )
            return
        agenda = str(manifest.get("agenda") or "").strip()
        log_path = directory / "pipeline_run.log"
        command = [
            sys.executable,
            str(SCRIPT_DIR / "run_cwh_resumable_pipeline.py"),
            "run",
            "--job-dir",
            str(output_dir),
            "--agenda",
            agenda or "国务院常务会议",
            "--system-workbook",
            files[0],
            "--no-open",
        ]
        if self.pipeline_ai_command:
            command.extend(
                ["--ai-worker-command-json", json.dumps(self.pipeline_ai_command, ensure_ascii=False)]
            )
        existing_state_path = output_dir / "pipeline_state.json"
        if existing_state_path.exists():
            try:
                existing_state = json.loads(existing_state_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                existing_state = {}
            failed_stage = str(existing_state.get("current_stage") or "")
            if existing_state.get("status") == "failed" and failed_stage:
                subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT_DIR / "run_cwh_resumable_pipeline.py"),
                        "invalidate",
                        "--job-dir",
                        str(output_dir),
                        "--invalidate-from",
                        failed_stage,
                    ],
                    cwd=str(self.workspace),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        env = os.environ.copy()
        env.setdefault("PYTHONIOENCODING", "utf-8")
        try:
            with log_path.open("w", encoding="utf-8", errors="replace") as log:
                process = subprocess.Popen(
                    command,
                    cwd=str(self.workspace),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                    creationflags=creationflags,
                    env=env,
                )
                self._update_manifest(directory, process_id=process.pid, report_log_path=str(log_path))
                return_code = process.wait()
            pipeline_state_path = output_dir / "pipeline_state.json"
            pipeline_state = (
                json.loads(pipeline_state_path.read_text(encoding="utf-8"))
                if pipeline_state_path.exists()
                else {}
            )
            dashboards = list(output_dir.rglob("cwh_dashboard.html"))
            complete = pipeline_state.get("status") == "succeeded" and any(
                (dashboard.parent / "report_data.json").exists() for dashboard in dashboards
            )
            result = {
                "finished_at": datetime.now().isoformat(timespec="seconds"),
                "return_code": return_code,
                "report_log_path": str(log_path),
                "pipeline_state_path": str(pipeline_state_path),
                "pipeline": pipeline_state,
            }
            if complete:
                newest = max(
                    (path for path in output_dir.rglob("report_data.json")),
                    key=lambda path: path.stat().st_mtime_ns,
                    default=None,
                )
                if newest:
                    self._index_report_data(newest, reason="generation")
                result.update(
                    {
                        "status": "complete",
                        "message": "本期报告已通过全部节点门禁，可以打开工作台或Word。",
                    }
                )
            else:
                pipeline_status = str(pipeline_state.get("status") or "failed")
                next_action = pipeline_state.get("next_action") or {}
                resumable = pipeline_status in {
                    "waiting_ai",
                    "waiting_login",
                    "waiting_review",
                    "blocked",
                    "paused",
                    "interrupted",
                }
                result.update(
                    {
                        "status": pipeline_status if resumable else "failed",
                        "message": str(
                            next_action.get("message")
                            or "管线尚未完成，请查看当前节点并继续运行。"
                        ),
                    }
                )
            self._update_manifest(directory, **result)
        except Exception as exc:
            self._update_manifest(
                directory,
                status="failed",
                finished_at=datetime.now().isoformat(timespec="seconds"),
                message=f"管线运行失败：{type(exc).__name__}: {exc}",
                report_log_path=str(log_path),
            )

    def _run_codex_job(self, directory: Path, output_dir: Path, source_files: list[Path] | None = None) -> None:
        manifest = self._update_manifest(
            directory,
            status="report_running",
            report_started_at=datetime.now().isoformat(timespec="seconds"),
            message="AI 正在识别数据、分析观点并生成报告。",
        )
        files = [str(path.resolve()) for path in source_files] if source_files else [
            str(Path(row["path"]).resolve()) for row in manifest.get("files", []) if row.get("path")
        ]
        agenda = str(manifest.get("agenda") or "").strip()
        log_path = directory / "codex_run.log"
        worker_prompt = (
            "请读取任务文件 {task}，使用已安装的 cwh-report-skill 只完成其中指定的当前节点。"
            "严格遵守inputs、rules和completion_contract，将所有约定产物写到任务指定路径。"
            "不得运行后续节点，不得读取基准成品报告或其他历史输出，不得用说明文字冒充结构化产物。"
            "完成前自行校验证据链接、字段、时间窗和AI审核标记。"
        )
        ai_worker_command = [
            self.codex_command,
            "--search",
            "-a",
            "never",
            "-s",
            "workspace-write",
            "-C",
            str(self.workspace),
            "exec",
            "--skip-git-repo-check",
            "--ephemeral",
            worker_prompt,
        ]
        command = [
            sys.executable,
            str(SCRIPT_DIR / "run_cwh_resumable_pipeline.py"),
            "run",
            "--job-dir",
            str(output_dir),
            "--agenda",
            agenda or "国务院常务会议",
            "--system-workbook",
            files[0],
            "--ai-worker-command-json",
            json.dumps(ai_worker_command, ensure_ascii=False),
        ]
        existing_state_path = output_dir / "pipeline_state.json"
        if existing_state_path.exists():
            try:
                existing_state = json.loads(existing_state_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                existing_state = {}
            failed_stage = str(existing_state.get("current_stage") or "")
            if existing_state.get("status") == "failed" and failed_stage:
                subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT_DIR / "run_cwh_resumable_pipeline.py"),
                        "invalidate",
                        "--job-dir",
                        str(output_dir),
                        "--invalidate-from",
                        failed_stage,
                    ],
                    cwd=str(self.workspace),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        env = os.environ.copy()
        bundled_dependencies = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies"
        runtime_paths = [bundled_dependencies / "python", bundled_dependencies / "bin"]
        existing_paths = [str(path) for path in runtime_paths if path.exists()]
        if existing_paths:
            env["PATH"] = os.pathsep.join(existing_paths + [env.get("PATH", "")])
        try:
            with log_path.open("w", encoding="utf-8", errors="replace") as log:
                process = subprocess.Popen(
                    command,
                    cwd=str(self.workspace),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                    creationflags=creationflags,
                    env=env,
                )
                self._update_manifest(directory, process_id=process.pid)
                return_code = process.wait()
            pipeline_state_path = output_dir / "pipeline_state.json"
            pipeline_state = (
                json.loads(pipeline_state_path.read_text(encoding="utf-8"))
                if pipeline_state_path.exists()
                else {}
            )
            dashboards = list(output_dir.rglob("cwh_dashboard.html"))
            complete = pipeline_state.get("status") == "succeeded" and any(
                (dashboard.parent / "report_data.json").exists() for dashboard in dashboards
            )
            result = {
                "finished_at": datetime.now().isoformat(timespec="seconds"),
                "return_code": return_code,
                "log_path": str(log_path),
                "pipeline_state_path": str(pipeline_state_path),
                "pipeline": pipeline_state,
            }
            if complete:
                newest = max(
                    (path for path in output_dir.rglob("report_data.json")),
                    key=lambda path: path.stat().st_mtime_ns,
                    default=None,
                )
                if newest:
                    self._index_report_data(newest, reason="generation")
                result.update({
                    "status": "complete",
                    "message": "本期报告已生成，可以打开工作台或 Word。",
                })
            else:
                pipeline_status = str(pipeline_state.get("status") or "failed")
                next_action = pipeline_state.get("next_action") or {}
                resumable = pipeline_status in {
                    "waiting_ai",
                    "waiting_login",
                    "waiting_review",
                    "blocked",
                    "paused",
                    "interrupted",
                }
                result.update({
                    "status": pipeline_status if resumable else "failed",
                    "message": str(next_action.get("message") or "管线尚未完成，请查看当前节点并继续运行。"),
                })
            self._update_manifest(directory, **result)
        except Exception as exc:
            self._update_manifest(
                directory,
                status="failed",
                finished_at=datetime.now().isoformat(timespec="seconds"),
                message=f"AI 运行失败：{type(exc).__name__}: {exc}",
                log_path=str(log_path),
            )


def handler_factory(app: DashboardApp):
    class Handler(BaseHTTPRequestHandler):
        server_version = "CWHWorkbench/0.2"

        def json_response(self, payload: dict | list, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                pass

        def read_json(self) -> dict:
            size = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(size).decode("utf-8")) if size else {}

        def authenticated_user_key(self, client_id: str = "") -> str:
            remote = str(self.client_address[0]) if self.client_address else ""
            return app.user_key(self.headers, remote, client_id)

        def send_file(self, path: Path) -> None:
            if not path.exists() or not path.is_file():
                self.send_error(404)
                return
            content = path.read_bytes()
            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", mime + ("; charset=utf-8" if mime.startswith("text/") else ""))
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(content)
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                pass

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/healthz":
                self.json_response({"status": "ok", "report_runner": app.report_runner})
                return
            if parsed.path == "/api/manifest":
                self.json_response(app.service_manifest())
                return
            if parsed.path == "/api/collectors/status":
                self.json_response(app.collector_status())
                return
            if parsed.path == "/api/storage/status":
                self.json_response(app.storage_status())
                return
            if parsed.path == "/api/assistant/status":
                self.json_response(app.assistant_status())
                return
            if parsed.path == "/platform-login":
                self.send_file(SCRIPT_DIR.parent / "assets" / "platform_login_page.html")
                return
            if parsed.path == "/api/platform-sessions":
                query = parse_qs(parsed.query)
                session_id = str((query.get("session_id") or [""])[0])
                kind = str((query.get("kind") or [""])[0])
                if session_id and kind == "status":
                    self.json_response(app.platform_session_status(self.authenticated_user_key(), session_id))
                    return
                if session_id and kind == "qr":
                    self.send_file(app.platform_session_qr(self.authenticated_user_key(), session_id))
                    return
                if session_id and kind == "preview":
                    self.send_file(app.platform_session_preview(self.authenticated_user_key(), session_id))
                    return
                self.json_response(app.platform_sessions(self.authenticated_user_key()))
                return
            if parsed.path == "/api/platform-sessions/status":
                query = parse_qs(parsed.query)
                session_id = str((query.get("session_id") or [""])[0])
                self.json_response(app.platform_session_status(self.authenticated_user_key(), session_id))
                return
            if parsed.path == "/api/platform-sessions/qr":
                query = parse_qs(parsed.query)
                session_id = str((query.get("session_id") or [""])[0])
                self.send_file(app.platform_session_qr(self.authenticated_user_key(), session_id))
                return
            if parsed.path == "/api/platform-sessions/preview":
                query = parse_qs(parsed.query)
                session_id = str((query.get("session_id") or [""])[0])
                self.send_file(app.platform_session_preview(self.authenticated_user_key(), session_id))
                return
            if parsed.path == "/api/reports":
                self.json_response(app.reports())
                return
            if parsed.path == "/api/archive":
                query = parse_qs(parsed.query)
                search = str((query.get("q") or [""])[0])
                self.json_response(app.archive(search))
                return
            if parsed.path == "/api/archive/artifact":
                query = parse_qs(parsed.query)
                rid = str((query.get("report_id") or [""])[0])
                kind = str((query.get("kind") or [""])[0])
                self.send_file(app.archive_artifact(rid, kind))
                return
            version_match = re.match(r"^/api/reports/([a-f0-9]{12})/versions$", parsed.path)
            if version_match:
                self.json_response(app.report_versions(version_match.group(1)))
                return
            if parsed.path == "/api/import/status":
                query = parse_qs(parsed.query)
                job_id = str((query.get("job_id") or [""])[0])
                self.json_response(app.import_status(job_id))
                return
            if parsed.path == "/api/import/artifact":
                query = parse_qs(parsed.query)
                job_id = str((query.get("job_id") or [""])[0])
                kind = str((query.get("kind") or [""])[0])
                self.send_file(app.import_artifact(job_id, kind))
                return
            if parsed.path in {"/", "/cwh_dashboard.html"}:
                self.send_file(app.dashboard)
                return
            root_candidate = (app.dashboard.parent / Path(unquote(parsed.path)).name).resolve()
            if parsed.path.count("/") == 1 and root_candidate.parent == app.dashboard.parent and root_candidate.exists():
                self.send_file(root_candidate)
                return
            match = re.match(r"^/reports/([a-f0-9]{12})/(.+)$", parsed.path)
            if match:
                directory = app.report_directory(match.group(1))
                if not directory:
                    self.send_error(404)
                    return
                candidate = (directory / Path(unquote(match.group(2))).name).resolve()
                if candidate.parent != directory.resolve():
                    self.send_error(403)
                    return
                self.send_file(candidate)
                return
            self.send_error(404)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            try:
                match = re.match(r"^/api/reports/([a-f0-9]{12})/hotwords/(preview|status|save)$", parsed.path)
                if match:
                    action = match.group(2)
                    payload = self.read_json()
                    if action == "preview":
                        result = app.preview_hotwords(match.group(1), payload)
                    elif action == "status":
                        result = app.hotword_preview_status(match.group(1), payload)
                    else:
                        result = app.save_hotwords(match.group(1), payload)
                    self.json_response(result)
                    return
                match = re.match(r"^/api/reports/([a-f0-9]{12})/save$", parsed.path)
                if match:
                    self.json_response(app.save_section(match.group(1), self.read_json()))
                    return
                if parsed.path == "/api/import/start":
                    self.json_response(app.start_import(self.read_json()), 201)
                    return
                if parsed.path == "/api/import/file":
                    query = parse_qs(parsed.query)
                    job_id = str((query.get("job_id") or [""])[0])
                    name = str((query.get("name") or [""])[0])
                    size = int(self.headers.get("Content-Length") or 0)
                    self.json_response(app.upload_file(job_id, name, self.rfile.read(size)), 201)
                    return
                if parsed.path == "/api/import/commit":
                    self.json_response(app.commit_import(str(self.read_json().get("job_id") or "")))
                    return
                if parsed.path == "/api/import/report":
                    self.json_response(app.start_report(str(self.read_json().get("job_id") or ""), self.authenticated_user_key()))
                    return
                if parsed.path == "/api/assistant/chat":
                    self.json_response(app.assistant_chat(self.read_json()))
                    return
                if parsed.path == "/api/platform-sessions/start":
                    payload = self.read_json()
                    self.json_response(app.start_platform_session(self.authenticated_user_key(str(payload.get("client_id") or "")), str(payload.get("platform") or "")), 201)
                    return
                if parsed.path == "/api/platform-sessions/list":
                    payload = self.read_json()
                    self.json_response(app.platform_sessions(self.authenticated_user_key(str(payload.get("client_id") or ""))))
                    return
                if parsed.path == "/api/platform-sessions/status":
                    payload = self.read_json()
                    self.json_response(
                        app.platform_session_status(
                            self.authenticated_user_key(str(payload.get("client_id") or "")),
                            str(payload.get("session_id") or ""),
                            embed_images=True,
                        )
                    )
                    return
                if parsed.path == "/api/platform-sessions/stop":
                    payload = self.read_json()
                    self.json_response(app.stop_platform_session(self.authenticated_user_key(str(payload.get("client_id") or "")), str(payload.get("session_id") or "")))
                    return
                if parsed.path == "/api/platform-sessions/action":
                    payload = self.read_json()
                    self.json_response(app.platform_session_action(self.authenticated_user_key(str(payload.get("client_id") or "")), payload))
                    return
                self.send_error(404)
            except (ValueError, json.JSONDecodeError) as exc:
                self.json_response({"error": str(exc)}, 400)
            except FileNotFoundError as exc:
                self.json_response({"error": str(exc)}, 404)
            except Exception as exc:
                self.json_response({"error": f"{type(exc).__name__}: {exc}"}, 500)

        def log_message(self, format: str, *args) -> None:
            sys.stdout.write("%s - %s\n" % (self.log_date_time_string(), format % args))

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the editable CWH report workbench")
    parser.add_argument("dashboard", help="Path to cwh_dashboard.html")
    parser.add_argument("--library-root", default="", help="Root containing historical CWH output directories")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--enable-codex-runner", action="store_true", help="Run the local Codex CLI after files are imported")
    parser.add_argument(
        "--report-runner",
        choices=["auto", "native", "codex", "pipeline"],
        default="auto",
        help=(
            "Report execution backend. Pipeline is the resumable With/Linux mode; "
            "native is retained only for compatibility."
        ),
    )
    parser.add_argument("--workspace", default="", help="Workspace used by the local Codex runner")
    parser.add_argument("--codex-command", default="", help="Optional explicit path to codex.cmd/codex")
    parser.add_argument(
        "--pipeline-ai-command-json",
        default="",
        help=(
            "Optional JSON string array for the approved per-stage model worker. "
            "Defaults to CWH_PIPELINE_AI_COMMAND_JSON."
        ),
    )
    args = parser.parse_args()
    dashboard = Path(args.dashboard).resolve()
    if not dashboard.exists():
        raise FileNotFoundError(f"Dashboard not found: {dashboard}")
    library_root = Path(args.library_root).resolve() if args.library_root else dashboard.parents[2]
    workspace = Path(args.workspace).resolve() if args.workspace else library_root.parent
    pipeline_ai_command = None
    if args.pipeline_ai_command_json:
        try:
            parsed_command = json.loads(args.pipeline_ai_command_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"--pipeline-ai-command-json is invalid JSON: {exc}") from exc
        if not isinstance(parsed_command, list):
            raise ValueError("--pipeline-ai-command-json must be a JSON string array")
        pipeline_ai_command = parsed_command
    app = DashboardApp(
        dashboard,
        library_root,
        enable_codex_runner=args.enable_codex_runner,
        report_runner=args.report_runner,
        workspace=workspace,
        codex_command=args.codex_command,
        pipeline_ai_command=pipeline_ai_command,
    )
    port = available_port(args.host, args.port)
    server = ThreadingHTTPServer((args.host, port), handler_factory(app))
    url = f"http://{args.host}:{port}/cwh_dashboard.html"
    print(url, flush=True)
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
