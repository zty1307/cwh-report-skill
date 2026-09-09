from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


WINDOWS_PATH = re.compile(r"^[A-Za-z]:[\\/]")


def seed_version(directory: Path) -> str:
    path = directory / ".seed_manifest.json"
    if not path.exists():
        return ""
    try:
        return str(json.loads(path.read_text(encoding="utf-8")).get("seed_version") or "")
    except (json.JSONDecodeError, OSError):
        return ""


def install_seed(seed_directory: Path, data_root: Path, current: Path) -> None:
    if current.exists():
        if current.resolve().parent != data_root.resolve():
            raise ValueError(f"Refusing to replace directory outside data root: {current}")
        if (current / "report_data.json").exists():
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            archive = data_root / f"cwh_report_preseed_{stamp}"
            suffix = 1
            while archive.exists():
                archive = data_root / f"cwh_report_preseed_{stamp}_{suffix}"
                suffix += 1
            shutil.copytree(current, archive)
        shutil.rmtree(current)
    shutil.copytree(seed_directory, current)


def build_file_index(root: Path) -> dict[str, list[Path]]:
    index: dict[str, list[Path]] = {}
    for path in root.rglob("*"):
        if path.is_file():
            index.setdefault(path.name.lower(), []).append(path)
    return index


def rebase_paths(value: Any, file_index: dict[str, list[Path]]) -> Any:
    if isinstance(value, dict):
        return {key: rebase_paths(item, file_index) for key, item in value.items()}
    if isinstance(value, list):
        return [rebase_paths(item, file_index) for item in value]
    if not isinstance(value, str) or not (WINDOWS_PATH.match(value) or value.startswith("/app/") or value.startswith("/data/")):
        return value
    basename = Path(value.replace("\\", "/")).name.lower()
    matches = file_index.get(basename) or []
    # Do not corrupt an unbundled evidence path by reducing it to a basename.
    return str(matches[0]) if matches else value


def prepare_report_directory(directory: Path) -> None:
    data_path = directory / "report_data.json"
    if not data_path.exists():
        raise FileNotFoundError(f"Seed report_data.json not found: {data_path}")
    data = json.loads(data_path.read_text(encoding="utf-8"))
    data = rebase_paths(data, build_file_index(directory))
    artifacts = data.setdefault("artifacts", {})
    explicit = {
        "formal_docx": directory / "cwh_formal_report.docx",
        "formal_report": directory / "cwh_formal_report.md",
        "data_workbook": directory / "cwh_data_workbook.xlsx",
        "report_data": directory / "report_data.json",
        "audit": directory / "cwh_audit.json",
        "dashboard": directory / "cwh_dashboard.html",
    }
    for key, path in explicit.items():
        if path.exists() or key in {"report_data", "dashboard"}:
            artifacts[key] = str(path)
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    scripts = Path(__file__).resolve().parent
    if str(scripts) not in os.sys.path:
        os.sys.path.insert(0, str(scripts))
    from generate_dashboard import generate_dashboard

    generate_dashboard(data, directory / "cwh_dashboard.html")


def install_archive_seeds(seed_archive: Path, data_root: Path) -> None:
    if not seed_archive.is_dir():
        return
    archive_root = data_root / "archive"
    archive_root.mkdir(parents=True, exist_ok=True)
    for seed in sorted(path for path in seed_archive.iterdir() if path.is_dir()):
        target = archive_root / seed.name
        bundled_version = seed_version(seed)
        installed_version = seed_version(target)
        if not (target / "report_data.json").exists() or (bundled_version and bundled_version != installed_version):
            if target.exists():
                if target.resolve().parent != archive_root.resolve():
                    raise ValueError(f"Refusing to replace archive outside data root: {target}")
                shutil.rmtree(target)
            shutil.copytree(seed, target)
        prepare_report_directory(target)


def prepare(seed_directory: Path, data_root: Path, seed_archive: Path | None = None) -> Path:
    current = data_root / "current"
    data_root.mkdir(parents=True, exist_ok=True)
    bundled_version = seed_version(seed_directory)
    current_version = seed_version(current)
    if not (current / "report_data.json").exists() or (bundled_version and bundled_version != current_version):
        install_seed(seed_directory, data_root, current)
    prepare_report_directory(current)
    if seed_archive:
        install_archive_seeds(seed_archive, data_root)
    return current


def main() -> int:
    app_root = Path(os.environ.get("CWH_APP_ROOT", "/app"))
    seed = Path(os.environ.get("CWH_SEED_DIR", app_root / "seed/current"))
    seed_archive = Path(os.environ.get("CWH_ARCHIVE_SEED_DIR", app_root / "seed/archive"))
    data_root = Path(os.environ.get("CWH_DATA_ROOT", app_root / "data"))
    current = prepare(seed, data_root, seed_archive)
    print(json.dumps({"status": "ok", "current": str(current)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
