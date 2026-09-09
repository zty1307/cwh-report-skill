from __future__ import annotations

import contextlib
import hashlib
import io
import json
import mimetypes
import os
import re
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator


SCHEMA_VERSION = 3


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _as_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, dict):
        return row
    return {key: row[key] for key in row.keys()}


def _load_config() -> dict[str, Any]:
    path = str(os.environ.get("CWH_DB_CONFIG") or "").strip()
    if not path:
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _setting(config: dict[str, Any], env_name: str, config_name: str, default: Any = "") -> Any:
    value = os.environ.get(env_name)
    if value is not None and str(value).strip():
        return value
    value = config.get(config_name)
    return value if value is not None and str(value).strip() else default


class ArchiveStore:
    """Persist report metadata and report-only snapshots.

    SQLite remains the zero-configuration local backend. MySQL is used by the
    shared With deployment. Both backends keep the same logical schema so a
        report can be indexed, downloaded, edited, and restored after redeployment.
        Source workbooks, JSON, audit files, crawler output and other run attachments
        deliberately stay outside the shared report library.
    """

    def __init__(self, library_root: Path):
        self.library_root = library_root.resolve()
        config = _load_config()
        requested = str(_setting(config, "CWH_DB_BACKEND", "backend", "sqlite")).strip().lower()
        self.backend = "mysql" if requested in {"mysql", "mariadb"} else "sqlite"
        self.sqlite_path = Path(
            os.environ.get("CWH_ARCHIVE_DB") or self.library_root / "cwh_archive.sqlite3"
        ).resolve()
        self.mysql = {
            "host": str(_setting(config, "CWH_MYSQL_HOST", "host")),
            "port": int(_setting(config, "CWH_MYSQL_PORT", "port", 3306)),
            "database": str(_setting(config, "CWH_MYSQL_DATABASE", "database")),
            "user": str(_setting(config, "CWH_MYSQL_USER", "user")),
            "password": str(_setting(config, "CWH_MYSQL_PASSWORD", "password")),
            "charset": "utf8mb4",
            "connect_timeout": int(_setting(config, "CWH_MYSQL_CONNECT_TIMEOUT", "connect_timeout", 10)),
            "read_timeout": int(_setting(config, "CWH_MYSQL_READ_TIMEOUT", "read_timeout", 60)),
            "write_timeout": int(_setting(config, "CWH_MYSQL_WRITE_TIMEOUT", "write_timeout", 120)),
        }
        if self.backend == "mysql":
            missing = [key for key in ("host", "database", "user", "password") if not self.mysql[key]]
            if missing:
                raise RuntimeError("MySQL archive configuration is incomplete: " + ", ".join(missing))
        self.initialize()

    @contextlib.contextmanager
    def connection(self):
        if self.backend == "mysql":
            try:
                import pymysql
            except ImportError as exc:
                raise RuntimeError("PyMySQL is required for the MySQL archive backend") from exc
            connection = pymysql.connect(
                **self.mysql,
                autocommit=False,
                cursorclass=pymysql.cursors.DictCursor,
            )
        else:
            self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.sqlite_path, timeout=30)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        if self.backend == "mysql":
            statements = [
                """
                CREATE TABLE IF NOT EXISTS cwh_schema_version (
                    id TINYINT PRIMARY KEY,
                    version INT NOT NULL,
                    updated_at VARCHAR(32) NOT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """,
                """
                CREATE TABLE IF NOT EXISTS reports (
                    id VARCHAR(64) PRIMARY KEY,
                    meeting_date VARCHAR(32) NOT NULL DEFAULT '',
                    title VARCHAR(512) NOT NULL,
                    monitoring_period VARCHAR(512) NOT NULL DEFAULT '',
                    agenda LONGTEXT NOT NULL,
                    topic_text LONGTEXT NOT NULL,
                    directory TEXT NOT NULL,
                    report_data_path TEXT NOT NULL,
                    modified_ns BIGINT NOT NULL DEFAULT 0,
                    indexed_at VARCHAR(32) NOT NULL,
                    revision INT NOT NULL DEFAULT 1,
                    bundle_sha256 CHAR(64) NOT NULL DEFAULT '',
                    bundle_size BIGINT NOT NULL DEFAULT 0,
                    created_at VARCHAR(32) NOT NULL,
                    updated_at VARCHAR(32) NOT NULL,
                    deleted_at VARCHAR(32) NULL,
                    INDEX idx_reports_date (meeting_date),
                    INDEX idx_reports_updated (updated_at),
                    FULLTEXT INDEX idx_reports_search (title, agenda, topic_text)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """,
                """
                CREATE TABLE IF NOT EXISTS artifacts (
                    report_id VARCHAR(64) NOT NULL,
                    category VARCHAR(32) NOT NULL,
                    kind VARCHAR(64) NOT NULL,
                    display_name VARCHAR(255) NOT NULL,
                    path TEXT NOT NULL,
                    relative_path VARCHAR(1024) NOT NULL,
                    file_name VARCHAR(512) NOT NULL,
                    mime_type VARCHAR(255) NOT NULL DEFAULT 'application/octet-stream',
                    size_bytes BIGINT NOT NULL DEFAULT 0,
                    modified_ns BIGINT NOT NULL DEFAULT 0,
                    sha256 CHAR(64) NOT NULL DEFAULT '',
                    PRIMARY KEY (report_id, kind),
                    CONSTRAINT fk_artifacts_report FOREIGN KEY (report_id) REFERENCES reports(id) ON DELETE CASCADE,
                    INDEX idx_artifacts_category (category, kind)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """,
                """
                CREATE TABLE IF NOT EXISTS report_bundles (
                    report_id VARCHAR(64) PRIMARY KEY,
                    revision INT NOT NULL,
                    compression VARCHAR(16) NOT NULL DEFAULT 'zip',
                    content LONGBLOB NOT NULL,
                    sha256 CHAR(64) NOT NULL,
                    size_bytes BIGINT NOT NULL,
                    stored_bytes BIGINT NOT NULL,
                    created_at VARCHAR(32) NOT NULL,
                    CONSTRAINT fk_bundle_report FOREIGN KEY (report_id) REFERENCES reports(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """,
                """
                CREATE TABLE IF NOT EXISTS report_versions (
                    report_id VARCHAR(64) NOT NULL,
                    revision INT NOT NULL,
                    reason VARCHAR(128) NOT NULL DEFAULT 'index',
                    bundle_sha256 CHAR(64) NOT NULL,
                    content LONGBLOB NOT NULL,
                    size_bytes BIGINT NOT NULL,
                    stored_bytes BIGINT NOT NULL,
                    created_at VARCHAR(32) NOT NULL,
                    PRIMARY KEY (report_id, revision),
                    CONSTRAINT fk_versions_report FOREIGN KEY (report_id) REFERENCES reports(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """,
            ]
            with self.connection() as connection:
                with connection.cursor() as cursor:
                    for statement in statements:
                        cursor.execute(statement)
                    cursor.execute("SELECT version FROM cwh_schema_version WHERE id=1")
                    previous = cursor.fetchone()
                    previous_version = int((previous or {}).get("version") or 0)
                    if previous_version < 3:
                        self._migrate_mysql_report_only(cursor)
                    cursor.execute(
                        """
                        INSERT INTO cwh_schema_version(id, version, updated_at) VALUES(1, %s, %s)
                        ON DUPLICATE KEY UPDATE version=VALUES(version), updated_at=VALUES(updated_at)
                        """,
                        (SCHEMA_VERSION, _now()),
                    )
            return

        with self.connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS cwh_schema_version (
                    id INTEGER PRIMARY KEY CHECK(id=1),
                    version INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY,
                    meeting_date TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL,
                    monitoring_period TEXT NOT NULL DEFAULT '',
                    agenda TEXT NOT NULL DEFAULT '',
                    topic_text TEXT NOT NULL DEFAULT '',
                    directory TEXT NOT NULL UNIQUE,
                    report_data_path TEXT NOT NULL,
                    modified_ns INTEGER NOT NULL DEFAULT 0,
                    indexed_at TEXT NOT NULL,
                    revision INTEGER NOT NULL DEFAULT 1,
                    bundle_sha256 TEXT NOT NULL DEFAULT '',
                    bundle_size INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT '',
                    deleted_at TEXT
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    report_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    path TEXT NOT NULL,
                    relative_path TEXT NOT NULL DEFAULT '',
                    file_name TEXT NOT NULL,
                    mime_type TEXT NOT NULL DEFAULT 'application/octet-stream',
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    modified_ns INTEGER NOT NULL DEFAULT 0,
                    sha256 TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (report_id, kind),
                    FOREIGN KEY (report_id) REFERENCES reports(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS report_bundles (
                    report_id TEXT PRIMARY KEY,
                    revision INTEGER NOT NULL,
                    compression TEXT NOT NULL DEFAULT 'zip',
                    content BLOB NOT NULL,
                    sha256 TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    stored_bytes INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (report_id) REFERENCES reports(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS report_versions (
                    report_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    reason TEXT NOT NULL DEFAULT 'index',
                    bundle_sha256 TEXT NOT NULL,
                    content BLOB NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    stored_bytes INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (report_id, revision),
                    FOREIGN KEY (report_id) REFERENCES reports(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_reports_date ON reports(meeting_date DESC);
                CREATE INDEX IF NOT EXISTS idx_reports_search ON reports(title, monitoring_period, topic_text);
                CREATE INDEX IF NOT EXISTS idx_artifacts_category ON artifacts(category, kind);
                """
            )
            self._ensure_sqlite_columns(connection)
            previous = connection.execute("SELECT version FROM cwh_schema_version WHERE id=1").fetchone()
            previous_version = int(previous[0] if previous else 0)
            if previous_version < 3:
                self._migrate_sqlite_report_only(connection)
            connection.execute(
                """
                INSERT INTO cwh_schema_version(id, version, updated_at) VALUES(1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET version=excluded.version, updated_at=excluded.updated_at
                """,
                (SCHEMA_VERSION, _now()),
            )

    @staticmethod
    def _filter_bundle(content: bytes, allowed_names: set[str]) -> tuple[bytes, str, int]:
        output = io.BytesIO()
        total_size = 0
        with zipfile.ZipFile(io.BytesIO(bytes(content or b""))) as source, zipfile.ZipFile(
            output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as target:
            for member in source.infolist():
                name = Path(member.filename).as_posix()
                if name not in allowed_names or member.is_dir():
                    continue
                payload = source.read(member)
                total_size += len(payload)
                info = zipfile.ZipInfo(name)
                info.date_time = (1980, 1, 1, 0, 0, 0)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                target.writestr(info, payload, compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)
        filtered = output.getvalue()
        return filtered, hashlib.sha256(filtered).hexdigest(), total_size

    def _migrate_mysql_report_only(self, cursor: Any) -> None:
        cursor.execute("SELECT report_id, relative_path, file_name FROM artifacts WHERE kind IN ('dashboard','word')")
        allowed: dict[str, set[str]] = {}
        for row in cursor.fetchall():
            rid = str(row["report_id"])
            allowed.setdefault(rid, set()).add(str(row.get("relative_path") or row.get("file_name") or ""))
        cursor.execute("SELECT report_id, content FROM report_bundles")
        for row in cursor.fetchall():
            rid = str(row["report_id"])
            bundle, digest, size = self._filter_bundle(row["content"], allowed.get(rid, set()))
            cursor.execute(
                "UPDATE report_bundles SET content=%s, sha256=%s, size_bytes=%s, stored_bytes=%s WHERE report_id=%s",
                (bundle, digest, size, len(bundle), rid),
            )
            cursor.execute(
                "UPDATE reports SET bundle_sha256=%s, bundle_size=%s WHERE id=%s",
                (digest, size, rid),
            )
        cursor.execute("SELECT report_id, revision, content FROM report_versions")
        for row in cursor.fetchall():
            rid = str(row["report_id"])
            bundle, digest, size = self._filter_bundle(row["content"], allowed.get(rid, set()))
            cursor.execute(
                "UPDATE report_versions SET content=%s, bundle_sha256=%s, size_bytes=%s, stored_bytes=%s WHERE report_id=%s AND revision=%s",
                (bundle, digest, size, len(bundle), rid, int(row["revision"])),
            )
        cursor.execute("DELETE FROM artifacts WHERE kind NOT IN ('dashboard','word') OR category<>'report'")

    def _migrate_sqlite_report_only(self, connection: sqlite3.Connection) -> None:
        allowed: dict[str, set[str]] = {}
        for row in connection.execute(
            "SELECT report_id, relative_path, file_name FROM artifacts WHERE kind IN ('dashboard','word')"
        ).fetchall():
            rid = str(row["report_id"])
            allowed.setdefault(rid, set()).add(str(row["relative_path"] or row["file_name"] or ""))
        for row in connection.execute("SELECT report_id, content FROM report_bundles").fetchall():
            rid = str(row["report_id"])
            bundle, digest, size = self._filter_bundle(row["content"], allowed.get(rid, set()))
            connection.execute(
                "UPDATE report_bundles SET content=?, sha256=?, size_bytes=?, stored_bytes=? WHERE report_id=?",
                (bundle, digest, size, len(bundle), rid),
            )
            connection.execute(
                "UPDATE reports SET bundle_sha256=?, bundle_size=? WHERE id=?",
                (digest, size, rid),
            )
        for row in connection.execute("SELECT report_id, revision, content FROM report_versions").fetchall():
            rid = str(row["report_id"])
            bundle, digest, size = self._filter_bundle(row["content"], allowed.get(rid, set()))
            connection.execute(
                "UPDATE report_versions SET content=?, bundle_sha256=?, size_bytes=?, stored_bytes=? WHERE report_id=? AND revision=?",
                (bundle, digest, size, len(bundle), rid, int(row["revision"])),
            )
        connection.execute("DELETE FROM artifacts WHERE kind NOT IN ('dashboard','word') OR category<>'report'")

    @staticmethod
    def _ensure_sqlite_columns(connection: sqlite3.Connection) -> None:
        additions = {
            "reports": {
                "revision": "INTEGER NOT NULL DEFAULT 1",
                "bundle_sha256": "TEXT NOT NULL DEFAULT ''",
                "bundle_size": "INTEGER NOT NULL DEFAULT 0",
                "created_at": "TEXT NOT NULL DEFAULT ''",
                "updated_at": "TEXT NOT NULL DEFAULT ''",
                "deleted_at": "TEXT",
            },
            "artifacts": {
                "relative_path": "TEXT NOT NULL DEFAULT ''",
                "mime_type": "TEXT NOT NULL DEFAULT 'application/octet-stream'",
                "sha256": "TEXT NOT NULL DEFAULT ''",
            },
        }
        for table, columns in additions.items():
            existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            for name, declaration in columns.items():
                if name not in existing:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")

    @staticmethod
    def _bundle_directory(
        directory: Path,
        artifacts: list[dict[str, Any]] | None = None,
    ) -> tuple[bytes, str, int]:
        buffer = io.BytesIO()
        total_size = 0
        paths = []
        for item in artifacts or []:
            path = Path(item.get("path") or "").resolve()
            if path.exists() and path.is_file() and (path.parent == directory or directory in path.parents):
                paths.append(path)
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in sorted(set(paths)):
                content = path.read_bytes()
                total_size += len(content)
                # Keep bundle bytes stable across extraction, restart, and host
                # migration. ZIP's default metadata embeds filesystem mtimes,
                # which would otherwise create a false report revision.
                info = zipfile.ZipInfo(path.relative_to(directory).as_posix())
                info.date_time = (1980, 1, 1, 0, 0, 0)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)
        content = buffer.getvalue()
        return content, hashlib.sha256(content).hexdigest(), total_size

    @staticmethod
    def _substantive_bundle_signature(content: bytes) -> str:
        """Ignore HTML refreshes and host path rebasing, not report edits."""
        def portable(value):
            if isinstance(value, dict):
                return {key: portable(item) for key, item in value.items()}
            if isinstance(value, list):
                return [portable(item) for item in value]
            if isinstance(value, str) and (re.match(r"^[A-Za-z]:[\\/]", value) or value.startswith("/")):
                return value.replace("\\", "/").rsplit("/", 1)[-1]
            return value

        digest = hashlib.sha256()
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                for name in sorted(archive.namelist()):
                    if name.endswith(".html"):
                        continue
                    payload = archive.read(name)
                    if name == "report_data.json":
                        data = json.loads(payload)
                        data.pop("artifacts", None)
                        payload = json.dumps(portable(data), sort_keys=True, ensure_ascii=False).encode("utf-8")
                    digest.update(name.encode("utf-8"))
                    digest.update(payload)
        except (ValueError, zipfile.BadZipFile):
            return hashlib.sha256(content).hexdigest()
        return digest.hexdigest()

    @staticmethod
    def _safe_extract(content: bytes, target: Path) -> None:
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            root = target.resolve()
            for member in archive.infolist():
                destination = (target / member.filename).resolve()
                if destination != root and root not in destination.parents:
                    raise ValueError("Unsafe path in archived report bundle")
            archive.extractall(target)

    def upsert_report(
        self,
        report: dict[str, Any],
        artifacts: list[dict[str, Any]],
        directory: Path,
        *,
        reason: str = "index",
    ) -> None:
        directory = directory.resolve()
        bundle, bundle_sha, bundle_size = self._bundle_directory(directory, artifacts)
        now = _now()
        rid = str(report["id"])
        with self.connection() as connection:
            if self.backend == "mysql":
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT id FROM reports WHERE directory=%s AND id<>%s",
                        (str(directory), rid),
                    )
                    for conflict in cursor.fetchall():
                        conflict_id = str(conflict["id"])
                        cursor.execute(
                            """
                            UPDATE reports
                            SET directory=%s, deleted_at=COALESCE(deleted_at, %s), updated_at=%s
                            WHERE id=%s
                            """,
                            (f"{directory}::superseded::{conflict_id}", now, now, conflict_id),
                        )
                    cursor.execute("SELECT revision, bundle_sha256, created_at FROM reports WHERE id=%s", (rid,))
                    existing = _as_dict(cursor.fetchone())
                    revision = int(existing.get("revision") or 0)
                    changed = str(existing.get("bundle_sha256") or "") != bundle_sha
                    record_version = not existing or (changed and reason != "index")
                    if existing and changed and reason == "index":
                        cursor.execute("SELECT content FROM report_bundles WHERE report_id=%s", (rid,))
                        previous = _as_dict(cursor.fetchone()).get("content")
                        record_version = previous is None or self._substantive_bundle_signature(bytes(previous)) != self._substantive_bundle_signature(bundle)
                    if not existing:
                        revision = 1
                    elif record_version:
                        revision += 1
                    created_at = str(existing.get("created_at") or now)
                    cursor.execute(
                        """
                        INSERT INTO reports(
                            id, meeting_date, title, monitoring_period, agenda, topic_text, directory,
                            report_data_path, modified_ns, indexed_at, revision, bundle_sha256,
                            bundle_size, created_at, updated_at, deleted_at
                        ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL)
                        ON DUPLICATE KEY UPDATE meeting_date=VALUES(meeting_date), title=VALUES(title),
                            monitoring_period=VALUES(monitoring_period), agenda=VALUES(agenda),
                            topic_text=VALUES(topic_text), directory=VALUES(directory),
                            report_data_path=VALUES(report_data_path), modified_ns=VALUES(modified_ns),
                            indexed_at=VALUES(indexed_at), revision=VALUES(revision),
                            bundle_sha256=VALUES(bundle_sha256), bundle_size=VALUES(bundle_size),
                            updated_at=VALUES(updated_at), deleted_at=NULL
                        """,
                        (
                            rid, report["meeting_date"], report["title"], report["monitoring_period"],
                            report["agenda"], report["topic_text"], str(directory), report["report_data_path"],
                            report["modified_ns"], now, revision, bundle_sha, bundle_size, created_at, now,
                        ),
                    )
                    cursor.execute("DELETE FROM artifacts WHERE report_id=%s", (rid,))
                    for item in artifacts:
                        cursor.execute(
                            """
                            INSERT INTO artifacts(
                                report_id, category, kind, display_name, path, relative_path, file_name,
                                mime_type, size_bytes, modified_ns, sha256
                            ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            """,
                            self._artifact_values(rid, item, directory),
                        )
                    if record_version:
                        cursor.execute(
                            """
                            INSERT INTO report_versions(report_id, revision, reason, bundle_sha256, content, size_bytes, stored_bytes, created_at)
                            VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
                            """,
                            (rid, revision, reason[:128], bundle_sha, bundle, bundle_size, len(bundle), now),
                        )
                    cursor.execute(
                        """
                        INSERT INTO report_bundles(report_id, revision, compression, content, sha256, size_bytes, stored_bytes, created_at)
                        VALUES(%s,%s,'zip',%s,%s,%s,%s,%s)
                        ON DUPLICATE KEY UPDATE revision=VALUES(revision), content=VALUES(content),
                            sha256=VALUES(sha256), size_bytes=VALUES(size_bytes), stored_bytes=VALUES(stored_bytes),
                            created_at=VALUES(created_at)
                        """,
                        (rid, revision, bundle, bundle_sha, bundle_size, len(bundle), now),
                    )
                    if str(report.get("meeting_date") or "").strip():
                        cursor.execute(
                            "UPDATE reports SET deleted_at=%s WHERE meeting_date=%s AND id<>%s AND deleted_at IS NULL",
                            (now, report["meeting_date"], rid),
                        )
                return

            conflict_rows = connection.execute(
                "SELECT id FROM reports WHERE directory=? AND id<>?", (str(directory), rid)
            ).fetchall()
            for conflict in conflict_rows:
                conflict_id = str(conflict["id"])
                connection.execute(
                    """
                    UPDATE reports
                    SET directory=?, deleted_at=COALESCE(deleted_at, ?), updated_at=?
                    WHERE id=?
                    """,
                    (f"{directory}::superseded::{conflict_id}", now, now, conflict_id),
                )
            existing_row = connection.execute(
                "SELECT revision, bundle_sha256, created_at FROM reports WHERE id=?", (rid,)
            ).fetchone()
            existing = _as_dict(existing_row)
            revision = int(existing.get("revision") or 0)
            changed = str(existing.get("bundle_sha256") or "") != bundle_sha
            record_version = not existing or (changed and reason != "index")
            if existing and changed and reason == "index":
                previous_row = connection.execute("SELECT content FROM report_bundles WHERE report_id=?", (rid,)).fetchone()
                previous = _as_dict(previous_row).get("content")
                record_version = previous is None or self._substantive_bundle_signature(bytes(previous)) != self._substantive_bundle_signature(bundle)
            if not existing:
                revision = 1
            elif record_version:
                revision += 1
            created_at = str(existing.get("created_at") or now)
            connection.execute(
                """
                INSERT INTO reports(
                    id, meeting_date, title, monitoring_period, agenda, topic_text, directory,
                    report_data_path, modified_ns, indexed_at, revision, bundle_sha256,
                    bundle_size, created_at, updated_at, deleted_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)
                ON CONFLICT(id) DO UPDATE SET meeting_date=excluded.meeting_date, title=excluded.title,
                    monitoring_period=excluded.monitoring_period, agenda=excluded.agenda,
                    topic_text=excluded.topic_text, directory=excluded.directory,
                    report_data_path=excluded.report_data_path, modified_ns=excluded.modified_ns,
                    indexed_at=excluded.indexed_at, revision=excluded.revision,
                    bundle_sha256=excluded.bundle_sha256, bundle_size=excluded.bundle_size,
                    updated_at=excluded.updated_at, deleted_at=NULL
                """,
                (
                    rid, report["meeting_date"], report["title"], report["monitoring_period"],
                    report["agenda"], report["topic_text"], str(directory), report["report_data_path"],
                    report["modified_ns"], now, revision, bundle_sha, bundle_size, created_at, now,
                ),
            )
            connection.execute("DELETE FROM artifacts WHERE report_id=?", (rid,))
            for item in artifacts:
                connection.execute(
                    """
                    INSERT INTO artifacts(
                        report_id, category, kind, display_name, path, relative_path, file_name,
                        mime_type, size_bytes, modified_ns, sha256
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    self._artifact_values(rid, item, directory),
                )
            if record_version:
                connection.execute(
                    """
                    INSERT INTO report_versions(report_id, revision, reason, bundle_sha256, content, size_bytes, stored_bytes, created_at)
                    VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (rid, revision, reason[:128], bundle_sha, bundle, bundle_size, len(bundle), now),
                )
            connection.execute(
                """
                INSERT INTO report_bundles(report_id, revision, compression, content, sha256, size_bytes, stored_bytes, created_at)
                VALUES(?,?,'zip',?,?,?,?,?)
                ON CONFLICT(report_id) DO UPDATE SET revision=excluded.revision, content=excluded.content,
                    sha256=excluded.sha256, size_bytes=excluded.size_bytes,
                    stored_bytes=excluded.stored_bytes, created_at=excluded.created_at
                """,
                (rid, revision, bundle, bundle_sha, bundle_size, len(bundle), now),
            )
            if str(report.get("meeting_date") or "").strip():
                connection.execute(
                    "UPDATE reports SET deleted_at=? WHERE meeting_date=? AND id<>? AND deleted_at IS NULL",
                    (now, report["meeting_date"], rid),
                )

    def canonical_report_id(
        self,
        preferred: str,
        meeting_date: str,
        directory: Path | str | None = None,
    ) -> str:
        """Reuse the active database identity for a meeting across restores.

        A report directory can move when With rebuilds or hydrates the app. Its
        filesystem-derived marker must not turn that move into a second report.
        The current marker wins when it is already active; otherwise the most
        recently updated active record for the same meeting is reused.
        """
        preferred = str(preferred or "").strip()
        meeting_date = str(meeting_date or "").strip()
        directory_text = str(Path(directory).resolve()) if directory else ""
        with self.connection() as connection:
            if self.backend == "mysql":
                with connection.cursor() as cursor:
                    row = None
                    if meeting_date:
                        cursor.execute(
                            """
                            SELECT id FROM reports
                            WHERE meeting_date=%s AND deleted_at IS NULL
                            ORDER BY (id=%s) DESC, updated_at DESC, modified_ns DESC
                            LIMIT 1
                            """,
                            (meeting_date, preferred),
                        )
                        row = cursor.fetchone()
                    if not row and directory_text:
                        cursor.execute(
                            """
                            SELECT id FROM reports
                            WHERE directory=%s
                            ORDER BY (deleted_at IS NULL) DESC, updated_at DESC, modified_ns DESC
                            LIMIT 1
                            """,
                            (directory_text,),
                        )
                        row = cursor.fetchone()
            else:
                row = None
                if meeting_date:
                    row = connection.execute(
                        """
                        SELECT id FROM reports
                        WHERE meeting_date=? AND deleted_at IS NULL
                        ORDER BY (id=?) DESC, updated_at DESC, modified_ns DESC
                        LIMIT 1
                        """,
                        (meeting_date, preferred),
                    ).fetchone()
                if not row and directory_text:
                    row = connection.execute(
                        """
                        SELECT id FROM reports
                        WHERE directory=?
                        ORDER BY (deleted_at IS NULL) DESC, updated_at DESC, modified_ns DESC
                        LIMIT 1
                        """,
                        (directory_text,),
                    ).fetchone()
        value = _as_dict(row).get("id")
        return str(value or preferred)

    @staticmethod
    def _artifact_values(rid: str, item: dict[str, Any], directory: Path) -> tuple[Any, ...]:
        path = Path(item["path"]).resolve()
        relative = path.relative_to(directory).as_posix()
        content = path.read_bytes()
        stat = path.stat()
        return (
            rid,
            item["category"],
            item["kind"],
            item["display_name"],
            str(path),
            relative,
            path.name,
            mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            stat.st_size,
            stat.st_mtime_ns,
            hashlib.sha256(content).hexdigest(),
        )

    def search_reports(self, needle: str = "") -> list[dict[str, Any]]:
        token = f"%{needle.strip()}%"
        if self.backend == "mysql":
            where = ""
            params: tuple[Any, ...] = ()
            if needle.strip():
                where = "AND (meeting_date LIKE %s OR title LIKE %s OR monitoring_period LIKE %s OR agenda LIKE %s OR topic_text LIKE %s)"
                params = (token, token, token, token, token)
            with self.connection() as connection, connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT * FROM reports WHERE deleted_at IS NULL {where} ORDER BY meeting_date DESC, modified_ns DESC",
                    params,
                )
                return [_as_dict(row) for row in cursor.fetchall()]
        where = ""
        params = ()
        if needle.strip():
            where = "AND (meeting_date LIKE ? OR title LIKE ? OR monitoring_period LIKE ? OR agenda LIKE ? OR topic_text LIKE ?)"
            params = (token, token, token, token, token)
        with self.connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM reports WHERE deleted_at IS NULL {where} ORDER BY meeting_date DESC, modified_ns DESC",
                params,
            ).fetchall()
        return [_as_dict(row) for row in rows]

    def list_artifacts(self) -> list[dict[str, Any]]:
        with self.connection() as connection:
            if self.backend == "mysql":
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT a.* FROM artifacts a JOIN reports r ON r.id=a.report_id WHERE r.deleted_at IS NULL"
                    )
                    rows = cursor.fetchall()
            else:
                rows = connection.execute(
                    "SELECT a.* FROM artifacts a JOIN reports r ON r.id=a.report_id WHERE r.deleted_at IS NULL"
                ).fetchall()
        return [_as_dict(row) for row in rows]

    def get_report(self, rid: str) -> dict[str, Any]:
        with self.connection() as connection:
            if self.backend == "mysql":
                with connection.cursor() as cursor:
                    cursor.execute("SELECT * FROM reports WHERE id=%s AND deleted_at IS NULL", (rid,))
                    row = cursor.fetchone()
            else:
                row = connection.execute("SELECT * FROM reports WHERE id=? AND deleted_at IS NULL", (rid,)).fetchone()
        return _as_dict(row)

    def artifact(self, rid: str, kind: str) -> dict[str, Any]:
        with self.connection() as connection:
            if self.backend == "mysql":
                with connection.cursor() as cursor:
                    cursor.execute("SELECT * FROM artifacts WHERE report_id=%s AND kind=%s", (rid, kind))
                    row = cursor.fetchone()
            else:
                row = connection.execute(
                    "SELECT * FROM artifacts WHERE report_id=? AND kind=?", (rid, kind)
                ).fetchone()
        return _as_dict(row)

    def hydrate(self, rid: str, cache_root: Path, preferred: Path | None = None) -> Path:
        report = self.get_report(rid)
        if not report:
            raise FileNotFoundError("Report not found")
        expected_sha = str(report.get("bundle_sha256") or "")
        preferred = preferred.resolve() if preferred else None
        if preferred and (preferred / "report_data.json").exists():
            return preferred
        target = (cache_root / rid).resolve()
        marker = target / ".cwh_bundle_sha256"
        if (target / "report_data.json").exists() and marker.exists() and marker.read_text(encoding="ascii").strip() == expected_sha:
            return target
        with self.connection() as connection:
            if self.backend == "mysql":
                with connection.cursor() as cursor:
                    cursor.execute("SELECT content, sha256 FROM report_bundles WHERE report_id=%s", (rid,))
                    bundle = cursor.fetchone()
            else:
                bundle = connection.execute(
                    "SELECT content, sha256 FROM report_bundles WHERE report_id=?", (rid,)
                ).fetchone()
        bundle_data = _as_dict(bundle)
        if not bundle_data:
            raise FileNotFoundError("Archived report bundle not found")
        if target.exists():
            import shutil
            shutil.rmtree(target)
        self._safe_extract(bytes(bundle_data["content"]), target)
        marker.write_text(str(bundle_data["sha256"]), encoding="ascii")
        return target

    def versions(self, rid: str) -> list[dict[str, Any]]:
        with self.connection() as connection:
            if self.backend == "mysql":
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT revision, reason, bundle_sha256, size_bytes, stored_bytes, created_at FROM report_versions WHERE report_id=%s ORDER BY revision DESC",
                        (rid,),
                    )
                    rows = cursor.fetchall()
            else:
                rows = connection.execute(
                    "SELECT revision, reason, bundle_sha256, size_bytes, stored_bytes, created_at FROM report_versions WHERE report_id=? ORDER BY revision DESC",
                    (rid,),
                ).fetchall()
        return [_as_dict(row) for row in rows]

    def status(self) -> dict[str, Any]:
        with self.connection() as connection:
            if self.backend == "mysql":
                with connection.cursor() as cursor:
                    cursor.execute("SELECT COUNT(*) AS count FROM reports WHERE deleted_at IS NULL")
                    report_count = int(cursor.fetchone()["count"])
                    cursor.execute(
                        "SELECT COUNT(*) AS count FROM artifacts a JOIN reports r ON r.id=a.report_id WHERE r.deleted_at IS NULL"
                    )
                    artifact_count = int(cursor.fetchone()["count"])
                    cursor.execute(
                        "SELECT COUNT(*) AS count FROM report_versions v JOIN reports r ON r.id=v.report_id WHERE r.deleted_at IS NULL"
                    )
                    version_count = int(cursor.fetchone()["count"])
            else:
                report_count = int(connection.execute("SELECT COUNT(*) FROM reports WHERE deleted_at IS NULL").fetchone()[0])
                artifact_count = int(connection.execute(
                    "SELECT COUNT(*) FROM artifacts a JOIN reports r ON r.id=a.report_id WHERE r.deleted_at IS NULL"
                ).fetchone()[0])
                version_count = int(connection.execute(
                    "SELECT COUNT(*) FROM report_versions v JOIN reports r ON r.id=v.report_id WHERE r.deleted_at IS NULL"
                ).fetchone()[0])
        return {
            "status": "ok",
            "backend": self.backend,
            "schema_version": SCHEMA_VERSION,
            "persistent_artifacts": True,
            "version_history": True,
            "report_count": report_count,
            "artifact_count": artifact_count,
            "version_count": version_count,
        }
