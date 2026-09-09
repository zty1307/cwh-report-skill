from __future__ import annotations

import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import prepare_with_runtime


def write_report(directory: Path, version: str, title: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / ".seed_manifest.json").write_text(
        json.dumps({"seed_version": version}, ensure_ascii=False),
        encoding="utf-8",
    )
    (directory / "report_data.json").write_text(
        json.dumps({"meeting": {"agenda": title}, "artifacts": {}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (directory / "cwh_dashboard.html").write_text(title, encoding="utf-8")


def test_new_seed_replaces_current_and_archives_previous(tmp_path: Path, monkeypatch) -> None:
    seed = tmp_path / "seed"
    data_root = tmp_path / "data"
    current = data_root / "current"
    write_report(seed, "new-version", "新版")
    write_report(current, "old-version", "旧版")
    monkeypatch.setattr(prepare_with_runtime, "build_file_index", lambda _root: {})

    scripts = SCRIPT_DIR
    sys.path.insert(0, str(scripts)) if str(scripts) not in sys.path else None
    result = prepare_with_runtime.prepare(seed, data_root)

    assert result == current
    assert json.loads((current / ".seed_manifest.json").read_text(encoding="utf-8"))["seed_version"] == "new-version"
    archives = list(data_root.glob("cwh_report_preseed_*"))
    assert len(archives) == 1
    assert json.loads((archives[0] / ".seed_manifest.json").read_text(encoding="utf-8"))["seed_version"] == "old-version"


def test_same_seed_version_keeps_current_files(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    data_root = tmp_path / "data"
    current = data_root / "current"
    write_report(seed, "same-version", "种子")
    write_report(current, "same-version", "用户当前报告")

    prepare_with_runtime.prepare(seed, data_root)

    data = json.loads((current / "report_data.json").read_text(encoding="utf-8"))
    assert data["meeting"]["agenda"] == "用户当前报告"
    assert not list(data_root.glob("cwh_report_preseed_*"))


def test_archive_seeds_are_installed_and_prepared(tmp_path: Path) -> None:
    seed = tmp_path / "seed" / "current"
    seed_archive = tmp_path / "seed" / "archive"
    historical = seed_archive / "001_previous"
    data_root = tmp_path / "data"
    write_report(seed, "current-version", "current report")
    write_report(historical, "history-version", "historical report")

    prepare_with_runtime.prepare(seed, data_root, seed_archive)

    installed = data_root / "archive" / "001_previous"
    assert json.loads((installed / ".seed_manifest.json").read_text(encoding="utf-8"))["seed_version"] == "history-version"
    data = json.loads((installed / "report_data.json").read_text(encoding="utf-8"))
    assert data["meeting"]["agenda"] == "historical report"
    assert (installed / "cwh_dashboard.html").exists()


def test_rebase_handles_windows_and_previous_container_without_corrupting_missing_evidence(tmp_path: Path) -> None:
    image = tmp_path / "hotword_distribution_pipeline.png"
    image.write_bytes(b"approved image")
    index = prepare_with_runtime.build_file_index(tmp_path)
    for value in [r"D:\old\charts\hotword_distribution_pipeline.png", "/app/data/current/charts/hotword_distribution_pipeline.png"]:
        assert prepare_with_runtime.rebase_paths(value, index) == str(image)
    missing = r"D:\source\raw_evidence.xlsx"
    assert prepare_with_runtime.rebase_paths(missing, index) == missing
