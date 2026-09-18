from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from openpyxl import Workbook


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "serve_dashboard.py"
SPEC = importlib.util.spec_from_file_location("serve_dashboard", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class DashboardImportTests(unittest.TestCase):
    def test_manifest_update_uses_bounded_atomic_writer(self) -> None:
        job = self.app.start_import({"agenda": "测试会议"})
        directory = self.app._job_directory(job["job_id"])
        with mock.patch.object(MODULE, "atomic_write_json", wraps=MODULE.atomic_write_json) as writer:
            result = self.app._update_manifest(directory, status="waiting_ai")
        self.assertEqual("waiting_ai", result["status"])
        self.assertEqual(directory / "manifest.json", writer.call_args.args[0])

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.current = self.root / "current"
        self.current.mkdir()
        self.dashboard = self.current / "cwh_dashboard.html"
        self.dashboard.write_text("<!doctype html>", encoding="utf-8")
        (self.current / "report_data.json").write_text(
            json.dumps(
                {
                    "meeting": {
                        "date": "2026-07-10",
                        "agenda": "7月10日国务院常务会",
                        "topics": ["听取数字中国建设情况汇报"],
                        "topic_keywords": {"听取数字中国建设情况汇报": ["数字中国建设"]},
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.app = MODULE.DashboardApp(
            self.dashboard,
            self.root / "outputs",
            enable_codex_runner=False,
            workspace=self.root,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def standard_workbook() -> bytes:
        workbook = Workbook()
        workbook.active.title = "关键词"
        for name in ["总事件", "子事件1", "子事件数据汇总"]:
            workbook.create_sheet(name)
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as handle:
            path = Path(handle.name)
        try:
            workbook.save(path)
            workbook.close()
            return path.read_bytes()
        finally:
            path.unlink(missing_ok=True)

    def test_previous_dashboard_topics_cannot_label_new_upload(self) -> None:
        with self.assertRaisesRegex(ValueError, "不能沿用"):
            self.app._raw_metadata({"agenda": "2026年7月10日国务院常务会"})

    def test_communique_update_reuses_files_and_refuses_running_job(self) -> None:
        job = self.app.start_import({"agenda": "2026-07-31", "agenda_order_confirmed": True})
        self.app.upload_file(job['job_id'], 'keep.json', b'{}')
        updated = self.app.update_communique({'job_id': job['job_id'], 'agenda': '2026-07-31',
                                             'communique_url': 'https://www.gov.cn/a', 'agenda_order_confirmed': True})
        self.assertTrue(updated['agenda_order_confirmed'])
        self.assertEqual(len(updated['files']), 1)
        self.assertTrue(updated['communique_supplement_url'])
        directory = self.app._job_directory(job['job_id'])
        self.app._update_manifest(directory, status='workbook_running')
        with self.assertRaisesRegex(ValueError, '不能替换'):
            self.app.update_communique({'job_id': job['job_id']})
        with self.assertRaisesRegex(ValueError, '重复启动'):
            self.app.commit_import(job['job_id'])

    def test_service_manifest_describes_native_workbench(self) -> None:
        manifest = self.app.service_manifest()
        self.assertEqual(manifest["status"], "ok")
        self.assertEqual(manifest["report_runner"], "native")
        self.assertTrue(manifest["features"]["raw_workbook_normalization"])
        self.assertTrue(manifest["features"]["resumable_pipeline"])
        self.assertTrue(manifest["features"]["stage_level_quality_gates"])
        self.assertTrue(manifest["features"]["section_editing"])
        self.assertTrue(manifest["features"]["searchable_archive_database"])

    def test_pipeline_runner_is_available_without_a_model_worker(self) -> None:
        app = MODULE.DashboardApp(
            self.dashboard,
            self.root / "pipeline-outputs",
            report_runner="pipeline",
            workspace=self.root,
            pipeline_ai_command=[],
        )

        manifest = app.service_manifest()

        self.assertEqual("pipeline", manifest["report_runner"])
        self.assertTrue(manifest["features"]["resumable_pipeline"])
        self.assertFalse(manifest["features"]["model_worker_configured"])

    def test_pipeline_worker_command_comes_from_backend_only_configuration(self) -> None:
        command = ["approved-worker", "--task", "{task}", "--output", "{output}"]
        with mock.patch.dict(
            "os.environ",
            {"CWH_PIPELINE_AI_COMMAND_JSON": json.dumps(command)},
            clear=False,
        ):
            app = MODULE.DashboardApp(
                self.dashboard,
                self.root / "configured-pipeline-outputs",
                report_runner="pipeline",
                workspace=self.root,
            )

        self.assertEqual(command, app.pipeline_ai_command)
        self.assertTrue(app.service_manifest()["features"]["model_worker_configured"])

    def test_pipeline_job_stops_at_saved_ai_checkpoint_without_old_native_runner(self) -> None:
        app = MODULE.DashboardApp(
            self.dashboard,
            self.root / "pipeline-job-outputs",
            report_runner="pipeline",
            workspace=self.root,
            pipeline_ai_command=[],
        )
        job = app.start_import({"agenda": "2026年7月10日国务院常务会议"})
        directory = app._job_directory(job["job_id"])
        workbook = directory / "standard.xlsx"
        workbook.write_bytes(self.standard_workbook())
        app._update_manifest(directory, status="workbook_complete", workbook_path=str(workbook))
        output = app.library_root / "pipeline-output"
        output.mkdir(parents=True)

        class FakeProcess:
            pid = 12345

            def wait(inner_self) -> int:
                (output / "pipeline_state.json").write_text(
                    json.dumps(
                        {
                            "status": "waiting_ai",
                            "current_stage": "domestic_viewpoints",
                            "next_action": {"message": "等待AI完成境内观点审核。"},
                            "stages": [],
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                return 20

        with mock.patch.object(MODULE.subprocess, "Popen", return_value=FakeProcess()) as popen:
            app._run_pipeline_job(directory, output, [workbook])

        command = popen.call_args.args[0]
        self.assertIn("run_cwh_resumable_pipeline.py", " ".join(command))
        self.assertNotIn("cwh_orchestrator.py", " ".join(command))
        self.assertNotIn("--ai-worker-command-json", command)
        updated = app._read_manifest(directory)
        self.assertEqual("waiting_ai", updated["status"])
        self.assertEqual("pipeline", updated["report_runner"])
        self.assertEqual("domestic_viewpoints", updated["pipeline"]["current_stage"])

    def test_pipeline_job_injects_configured_stage_worker(self) -> None:
        worker = ["approved-worker", "--task", "{task}", "--output", "{output}"]
        app = MODULE.DashboardApp(
            self.dashboard,
            self.root / "worker-pipeline-outputs",
            report_runner="pipeline",
            workspace=self.root,
            pipeline_ai_command=worker,
        )
        job = app.start_import({"agenda": "2026年7月10日国务院常务会议"})
        directory = app._job_directory(job["job_id"])
        workbook = directory / "standard.xlsx"
        workbook.write_bytes(self.standard_workbook())
        app._update_manifest(directory, status="workbook_complete", workbook_path=str(workbook))
        output = app.library_root / "pipeline-output"
        output.mkdir(parents=True)

        class FakeProcess:
            pid = 12346

            def wait(inner_self) -> int:
                (output / "pipeline_state.json").write_text(
                    json.dumps(
                        {
                            "status": "waiting_ai",
                            "current_stage": "domestic_viewpoints",
                            "next_action": {"message": "等待AI完成境内观点审核。"},
                            "stages": [],
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                return 20

        with mock.patch.object(MODULE.subprocess, "Popen", return_value=FakeProcess()) as popen:
            app._run_pipeline_job(directory, output, [workbook])

        command = popen.call_args.args[0]
        option_index = command.index("--ai-worker-command-json")
        self.assertEqual(worker, json.loads(command[option_index + 1]))

    def test_with_entrypoint_defaults_to_pipeline_runner(self) -> None:
        candidates = (
            SCRIPT.parents[1] / "deploy" / "with" / "entrypoint.sh",
            SCRIPT.parents[2] / "entrypoint.sh",
        )
        entrypoint_path = next((path for path in candidates if path.exists()), None)
        self.assertIsNotNone(entrypoint_path, "With entrypoint.sh is missing")
        entrypoint = entrypoint_path.read_text(encoding="utf-8")
        self.assertIn("--report-runner pipeline", entrypoint)
        self.assertNotIn("--report-runner native", entrypoint)

    def test_archive_stores_reports_only_and_supports_search(self) -> None:
        word = self.current / "cwh_formal_report.docx"
        excel = self.current / "cwh_data_workbook.xlsx"
        audit = self.current / "cwh_audit.json"
        word.write_bytes(b"word")
        excel.write_bytes(b"excel")
        audit.write_text("{}", encoding="utf-8")
        data_path = self.current / "report_data.json"
        data = json.loads(data_path.read_text(encoding="utf-8"))
        data["system_data"] = {"monitoring_period": {"label": "7月10日至7月13日"}}
        data["artifacts"] = {
            "formal_docx": str(word),
            "data_workbook": str(excel),
            "audit": str(audit),
        }
        data_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        archive = self.app.archive("数字中国")

        self.assertEqual(1, archive["counts"]["reports"])
        self.assertNotIn("datasets", archive)
        self.assertIn("/reports/", archive["reports"][0]["dashboard"])
        self.assertIn("kind=word", archive["reports"][0]["word"])
        with self.assertRaises(FileNotFoundError):
            self.app.archive_artifact(archive["reports"][0]["id"], "data_workbook")
        connection = sqlite3.connect(self.app.archive_db)
        try:
            self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM reports").fetchone()[0])
            # Keep the two user-facing report files plus the internal structured
            # report state required by online editing and hotword regeneration.
            self.assertEqual(3, connection.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0])
        finally:
            connection.close()

    def test_archive_bundle_restores_files_and_keeps_version_history(self) -> None:
        word = self.current / "cwh_formal_report.docx"
        excel = self.current / "cwh_data_workbook.xlsx"
        word.write_bytes(b"word-v1")
        excel.write_bytes(b"excel-v1")
        data_path = self.current / "report_data.json"
        data = json.loads(data_path.read_text(encoding="utf-8"))
        data["artifacts"] = {"formal_docx": str(word), "data_workbook": str(excel)}
        data_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        first = self.app.archive()
        rid = first["reports"][0]["id"]
        baseline_versions = len(self.app.report_versions(rid)["versions"])
        self.assertGreaterEqual(baseline_versions, 1)

        # Reindexing unchanged files, including after archive hydration, must
        # not manufacture a new user-visible report revision.
        self.app._index_report_data(data_path)
        self.assertEqual(baseline_versions, len(self.app.report_versions(rid)["versions"]))

        dashboard = self.current / "cwh_dashboard.html"
        dashboard.write_text("<html>background refresh</html>", encoding="utf-8")
        self.app._index_report_data(data_path)
        self.assertEqual(baseline_versions, len(self.app.report_versions(rid)["versions"]))

        word.unlink()
        excel.unlink()
        data_path.unlink()
        restored_word = self.app.archive_artifact(rid, "word")
        self.assertEqual(b"word-v1", restored_word.read_bytes())
        self.assertIn("_archive_cache", str(restored_word))

        restored_directory = restored_word.parent
        self.assertTrue((restored_directory / "report_data.json").exists())
        self.assertFalse((restored_directory / "cwh_data_workbook.xlsx").exists())
        restored_data = self.current / "report_data.json"
        current_word = self.current / "cwh_formal_report.docx"
        current_word.write_bytes(b"word-v2")
        restored_data.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.app._index_report_data(restored_data, reason="section_edit")

        self.assertEqual(rid, self.app.archive()["reports"][0]["id"])
        versions = self.app.report_versions(rid)["versions"]
        self.assertEqual(baseline_versions + 1, len(versions))
        self.assertEqual("section_edit", versions[0]["reason"])
        self.assertEqual(b"word-v2", self.app.archive_artifact(rid, "word").read_bytes())
        with self.assertRaises(FileNotFoundError):
            self.app.archive_artifact(rid, "data_workbook")

    def test_storage_status_reports_persistent_artifacts(self) -> None:
        status = self.app.storage_status()
        self.assertEqual("sqlite", status["backend"])
        self.assertTrue(status["persistent_artifacts"])
        self.assertTrue(status["version_history"])
        self.assertGreaterEqual(status["report_count"], 1)

    def test_index_keeps_substantive_report_versions(self) -> None:
        data_path = self.current / "report_data.json"
        rid = self.app.archive()["reports"][0]["id"]
        before = len(self.app.report_versions(rid)["versions"])
        data = json.loads(data_path.read_text(encoding="utf-8"))
        data["formal_sections"] = {"domestic": "A newly reviewed substantive viewpoint"}
        data_path.write_text(json.dumps(data), encoding="utf-8")
        self.app._index_report_data(data_path)
        self.assertEqual(before + 1, len(self.app.report_versions(rid)["versions"]))
        self.app._index_report_data(data_path)
        self.assertEqual(before + 1, len(self.app.report_versions(rid)["versions"]))

    def test_artifact_rebinds_relative_windows_and_missing_local_paths(self) -> None:
        word = self.current / "cwh_formal_report.docx"
        word.write_bytes(b"report")
        for path in [r"old\current\cwh_formal_report.docx", "missing/cwh_formal_report.docx", r"D:\old\cwh_formal_report.docx"]:
            self.assertEqual(word.resolve(), self.app._artifact_candidate(path, word, self.current))

    def test_same_meeting_reuses_one_database_identity_after_directory_move(self) -> None:
        first = self.app.archive()
        rid = first["reports"][0]["id"]
        moved = self.root / "outputs" / "restored_copy"
        moved.mkdir(parents=True)
        (moved / "cwh_dashboard.html").write_text("<!doctype html>", encoding="utf-8")
        (moved / "report_data.json").write_bytes((self.current / "report_data.json").read_bytes())
        (moved / ".cwh_report_id").write_text("abcdef123456", encoding="ascii")

        self.app._index_report_data(moved / "report_data.json")

        self.assertEqual(rid, (moved / ".cwh_report_id").read_text(encoding="ascii"))
        self.assertEqual(1, self.app.storage_status()["report_count"])
        self.assertEqual(1, self.app.archive()["counts"]["reports"])

    def test_archive_reconciles_stale_owner_of_current_directory(self) -> None:
        first = self.app.archive()
        original_id = first["reports"][0]["id"]
        canonical_id = "fedcba654321"
        other_directory = self.root / "restored-canonical"
        other_directory.mkdir()
        connection = sqlite3.connect(self.app.archive_db)
        try:
            row = connection.execute(
                """
                SELECT meeting_date, title, monitoring_period, agenda, topic_text,
                       report_data_path, modified_ns, indexed_at, revision,
                       bundle_sha256, bundle_size, created_at, updated_at
                FROM reports WHERE id=?
                """,
                (original_id,),
            ).fetchone()
            self.assertIsNotNone(row)
            connection.execute(
                "UPDATE reports SET deleted_at='2026-08-07T00:00:00Z' WHERE id=?",
                (original_id,),
            )
            connection.execute(
                """
                INSERT INTO reports(
                    id, meeting_date, title, monitoring_period, agenda, topic_text,
                    directory, report_data_path, modified_ns, indexed_at, revision,
                    bundle_sha256, bundle_size, created_at, updated_at, deleted_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)
                """,
                (canonical_id, *row[:5], str(other_directory), *row[5:]),
            )
            connection.commit()
        finally:
            connection.close()

        self.app._index_report_data(self.current / "report_data.json")
        archive = self.app.archive()

        self.assertEqual(1, archive["counts"]["reports"])
        self.assertEqual(canonical_id, archive["reports"][0]["id"])
        connection = sqlite3.connect(self.app.archive_db)
        try:
            active = connection.execute(
                "SELECT id, directory FROM reports WHERE deleted_at IS NULL"
            ).fetchall()
            self.assertEqual([(canonical_id, str(self.current.resolve()))], active)
            stale_directory = connection.execute(
                "SELECT directory FROM reports WHERE id=?", (original_id,)
            ).fetchone()[0]
            self.assertIn("::superseded::", stale_directory)
        finally:
            connection.close()

    def test_archive_sync_keeps_current_directory_across_same_meeting_candidates(self) -> None:
        current_word = self.current / "cwh_formal_report.docx"
        current_word.write_bytes(b"current-word")
        current_data = self.current / "report_data.json"
        data = json.loads(current_data.read_text(encoding="utf-8"))
        data["audit"] = {"acceptance": {"ready_for_formal_delivery": True}}
        data["artifacts"] = {"formal_docx": str(current_word)}
        current_data.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        old_paths = []
        for name in ("old-a", "old-b"):
            directory = self.root / "outputs" / name
            directory.mkdir(parents=True)
            (directory / "cwh_dashboard.html").write_text(f"<!doctype html>{name}", encoding="utf-8")
            old_word = directory / "cwh_formal_report.docx"
            old_word.write_bytes(name.encode("ascii"))
            old_data = {**data, "artifacts": {"formal_docx": str(old_word)}}
            path = directory / "report_data.json"
            path.write_text(json.dumps(old_data, ensure_ascii=False), encoding="utf-8")
            old_paths.append(path)

        orders = [
            [current_data, *old_paths],
            [old_paths[1], current_data, old_paths[0]],
            [*reversed(old_paths), current_data],
        ]
        for order in orders:
            with mock.patch.object(self.app, "_report_data_candidates", return_value=iter(order)):
                self.app._archive_last_sync = 0
                archive = self.app.archive()
            self.assertTrue(archive["reports"][0]["current"])
            rid = archive["reports"][0]["id"]
            connection = sqlite3.connect(self.app.archive_db)
            try:
                directory = connection.execute("SELECT directory FROM reports WHERE id=?", (rid,)).fetchone()[0]
                word_path = connection.execute(
                    "SELECT path FROM artifacts WHERE report_id=? AND kind='word'", (rid,)
                ).fetchone()[0]
                self.assertEqual(str(self.current.resolve()), directory)
                self.assertEqual(str(current_word.resolve()), word_path)
            finally:
                connection.close()

    def test_archive_sync_selects_complete_historical_candidate_independent_of_order(self) -> None:
        candidates = []
        for name, complete in (("history-incomplete", False), ("history-complete", True)):
            directory = self.root / "outputs" / name
            directory.mkdir(parents=True)
            (directory / "cwh_dashboard.html").write_text(f"<!doctype html>{name}", encoding="utf-8")
            data = {
                "meeting": {"date": "2026-07-11", "agenda": "7月11日国务院常务会", "topics": ["测试议题"]},
                "audit": {"acceptance": {"ready_for_formal_delivery": complete}},
                "artifacts": {},
            }
            if complete:
                word = directory / "cwh_formal_report.docx"
                word.write_bytes(b"complete")
                data["artifacts"]["formal_docx"] = str(word)
            path = directory / "report_data.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            candidates.append(path)

        for order in (candidates, list(reversed(candidates))):
            with mock.patch.object(
                self.app,
                "_report_data_candidates",
                return_value=iter([self.current / "report_data.json", *order]),
            ):
                self.app._archive_last_sync = 0
                self.app.archive()
            connection = sqlite3.connect(self.app.archive_db)
            try:
                directory = connection.execute(
                    "SELECT directory FROM reports WHERE meeting_date='2026-07-11' AND deleted_at IS NULL"
                ).fetchone()[0]
                self.assertEqual(str(candidates[1].parent.resolve()), directory)
            finally:
                connection.close()

    def test_collector_status_does_not_claim_authenticated_social_access(self) -> None:
        status = self.app.collector_status()
        self.assertEqual(status["status"], "ok")
        self.assertTrue(status["providers"]["public_web"]["available"])
        self.assertFalse(status["providers"]["domestic_authenticated_social"]["available"])

    def test_assistant_requires_explicit_runtime_model_configuration(self) -> None:
        with mock.patch.dict("os.environ", {"CWH_LLM_ENDPOINT": "", "CWH_LLM_MODEL": ""}, clear=False):
            status = self.app.assistant_status()
        self.assertFalse(status["available"])
        self.assertIn("published apps", status["reason"])

    def test_user_session_key_is_stable_without_exposing_identity(self) -> None:
        headers = {"X-Taihu-User": "zhangsan"}
        first = self.app.user_key(headers, "127.0.0.1")
        second = self.app.user_key(headers, "10.0.0.2")
        self.assertEqual(first, second)
        self.assertRegex(first, r"^[a-f0-9]{24}$")
        self.assertNotIn("zhangsan", first)

    def test_user_drag_action_is_scoped_and_recorded(self) -> None:
        user_key = self.app.user_key({"X-Taihu-User": "zhangsan"})
        session_id = "a" * 32
        directory = self.app._user_session_root(user_key) / "runs" / session_id
        directory.mkdir(parents=True)
        self.app._write_session_state(directory, session_id=session_id, platform="dy", status="awaiting_verification")
        result = self.app.platform_session_action(
            user_key,
            {
                "session_id": session_id,
                "type": "drag",
                "start": {"x": 12, "y": 34},
                "end": {"x": 220, "y": 34},
            },
        )
        self.assertEqual(result["status"], "ok")
        action = json.loads((directory / "actions.jsonl").read_text(encoding="utf-8").strip())
        self.assertEqual(action["type"], "drag")
        self.assertEqual(action["start"], {"x": 12.0, "y": 34.0})
        self.assertEqual(action["end"], {"x": 220.0, "y": 34.0})

        self.app.platform_session_action(
            user_key,
            {
                "session_id": session_id,
                "type": "click",
                "start": {"x": 55, "y": 66},
                "end": {"x": 55, "y": 66},
            },
        )
        actions = [json.loads(row) for row in (directory / "actions.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(actions[-1]["type"], "click")

    def test_platform_ui_uses_the_local_real_browser_connector(self) -> None:
        template = (SCRIPT.parents[1] / "assets" / "cwh_dashboard_template.html").read_text(encoding="utf-8")
        self.assertNotIn('id="qr-stage"', template)
        self.assertIn("http://127.0.0.1:8791/connect?platform=", template)
        self.assertIn("http://127.0.0.1:8791/status?platform=", template)
        self.assertIn('id="platform-browser"', template)
        self.assertIn("baijiahao:{label:'百家号'", template)
        self.assertIn("wechat_weread:{label:'微信读书（公众号）'", template)
        self.assertNotIn("/platform-login?session_id=", template)

    def test_standard_workbook_is_exposed_before_report_stage(self) -> None:
        job = self.app.start_import({"agenda": "2026年7月10日国务院常务会"})
        self.app.upload_file(job["job_id"], "标准总表.xlsx", self.standard_workbook())
        queued = self.app.commit_import(job["job_id"])
        self.assertEqual(queued["status"], "workbook_queued")
        for _ in range(200):
            status = self.app.import_status(job["job_id"])
            if status["status"] in {"workbook_complete", "failed"}:
                break
            time.sleep(0.05)
        self.assertEqual(status["status"], "workbook_complete")
        self.assertEqual(status["progress"], 100)
        self.assertTrue(all(row["status"] == "complete" for row in status["steps"]))
        self.assertTrue(Path(status["workbook_path"]).exists())
        self.assertIn("kind=workbook", status["workbook_url"])
        self.assertTrue(status["workbook_protocol"].startswith("ms-excel:ofe|u|file:///"))
        self.assertEqual(self.app.report_runner, "native")

    def test_import_status_exposes_resumable_pipeline_state(self) -> None:
        job = self.app.start_import({"agenda": "2026年7月10日国务院常务会"})
        self.app.upload_file(job["job_id"], "标准总表.xlsx", self.standard_workbook())
        self.app.commit_import(job["job_id"])
        for _ in range(200):
            status = self.app.import_status(job["job_id"])
            if status["status"] in {"workbook_complete", "failed"}:
                break
            time.sleep(0.05)
        output_dir = self.root / "outputs" / "pipeline-test"
        output_dir.mkdir(parents=True)
        pipeline = {
            "status": "waiting_ai",
            "current_stage": "domestic_viewpoints",
            "stages": [
                {"stage_id": "workbook", "label": "标准总表", "status": "succeeded"},
                {"stage_id": "domestic_viewpoints", "label": "境内观点", "status": "waiting_ai"},
            ],
        }
        (output_dir / "pipeline_state.json").write_text(json.dumps(pipeline, ensure_ascii=False), encoding="utf-8")
        directory = self.app._job_directory(job["job_id"])
        self.app._update_manifest(
            directory,
            status="waiting_ai",
            report_output_dir=str(output_dir),
            message="等待AI审核",
        )

        resumed = self.app.import_status(job["job_id"])

        self.assertEqual("waiting_ai", resumed["pipeline"]["status"])
        self.assertEqual("domestic_viewpoints", resumed["pipeline"]["current_stage"])

    def test_waiting_report_job_can_be_resumed_without_reupload(self) -> None:
        job = self.app.start_import({"agenda": "2026年7月10日国务院常务会"})
        self.app.upload_file(job["job_id"], "标准总表.xlsx", self.standard_workbook())
        self.app.commit_import(job["job_id"])
        for _ in range(200):
            status = self.app.import_status(job["job_id"])
            if status["status"] in {"workbook_complete", "failed"}:
                break
            time.sleep(0.05)
        directory = self.app._job_directory(job["job_id"])
        self.app._update_manifest(directory, status="waiting_ai", message="等待AI审核")
        with mock.patch.object(MODULE.threading, "Thread") as thread:
            resumed = self.app.start_report(job["job_id"], "user")

        self.assertEqual("report_queued", resumed["status"])
        thread.assert_called_once()

    def test_full_agenda_replaces_previous_report_topics_for_raw_mapping(self) -> None:
        with self.assertRaisesRegex(ValueError, "本期通稿"):
            self.app._raw_metadata({"agenda": "国务院常务会议听取数字中国建设情况汇报；研究其他工作"})


if __name__ == "__main__":
    unittest.main()
