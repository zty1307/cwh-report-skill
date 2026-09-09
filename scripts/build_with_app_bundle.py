from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


RUNTIME_DIRECTORIES = ["assets", "config", "references", "scripts", "templates", "tests"]
ROOT_RUNTIME_FILES = ["SKILL.md", "start_platform_connector.cmd"]
SEED_FILES = [
    "cwh_audit.json",
    "cwh_dashboard.html",
    "cwh_data_workbook.xlsx",
    "cwh_standard_workbook.xlsx",
    "cwh_formal_docx_audit.json",
    "cwh_formal_report.docx",
    "cwh_formal_report.md",
    "cwh_report.md",
    "hotword_semantic_review.json",
    "hotword_audit.json",
    "report_data.json",
]
SEED_DIRECTORIES = ["appendices", "charts", "sentiment_analysis"]
DEFAULT_MEDIASPIDER_HOME = Path.home() / ".data_assistant" / "engines" / "MediaSpider"
DEFAULT_MEDIASPIDER_SUPERVISOR = Path("D:/Codex/2026-06-15/ai-1-1-https-drive-weixin/work/mediaspider-supervisor")


def copy_report_seed(
    source: Path,
    target: Path,
    *,
    require_dashboard: bool,
    dashboard_generator: Path | None = None,
) -> str:
    target.mkdir(parents=True)
    for name in SEED_FILES:
        path = source / name
        if path.exists():
            shutil.copy2(path, target / name)
    for name in SEED_DIRECTORIES:
        path = source / name
        if path.exists():
            shutil.copytree(path, target / name)
    report_data = target / "report_data.json"
    if report_data.exists():
        # Rebind before HTML generation: old host paths must never silently
        # remove the formal body, download links, or reviewed word cloud.
        from prepare_with_runtime import build_file_index, rebase_paths

        data = json.loads(report_data.read_text(encoding="utf-8"))
        data = rebase_paths(data, build_file_index(target))
        report_data.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if dashboard_generator and report_data.exists():
        subprocess.run(
            [
                sys.executable,
                str(dashboard_generator),
                str(report_data),
                "--output",
                str(target / "cwh_dashboard.html"),
            ],
            check=True,
        )
    required = [target / "report_data.json", target / "cwh_formal_report.docx"]
    if require_dashboard:
        required.append(target / "cwh_dashboard.html")
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Seed report is incomplete: " + ", ".join(missing))
    if dashboard_generator and report_data.exists():
        data = json.loads(report_data.read_text(encoding="utf-8"))
        if (data.get("artifacts") or {}).get("docx_charts"):
            from verify_release_report import verify

            verify(target)

    digest = hashlib.sha256()
    seed_files = sorted(path for path in target.rglob("*") if path.is_file())
    for path in seed_files:
        digest.update(path.relative_to(target).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    version = digest.hexdigest()
    manifest = {
        "schema_version": 1,
        "seed_version": version,
        "seed_report": str(source.resolve()),
        "files": [path.relative_to(target).as_posix() for path in seed_files],
    }
    (target / ".seed_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return version


def archive_seed_name(source: Path, index: int) -> str:
    name = re.sub(r"[^0-9A-Za-z_-]+", "_", source.name).strip("_") or "report"
    return f"{index:03d}_{name}"


def replace_directory(path: Path, allowed_parent: Path) -> None:
    if not path.exists():
        path.mkdir(parents=True)
        return
    if path.resolve().parent != allowed_parent.resolve():
        raise ValueError(f"Refusing to replace directory outside output parent: {path}")
    shutil.rmtree(path)
    path.mkdir(parents=True)


def copy_collectors(output_directory: Path, media_home: Path, supervisor: Path) -> None:
    foreign_entrypoint = media_home / "foreign_collect.py"
    foreign_sources = media_home / "foreign_sources"
    supervisor_script = supervisor / "scripts" / "run_task.py"
    if not foreign_entrypoint.exists() or not foreign_sources.is_dir():
        raise FileNotFoundError(f"MediaSpider foreign collector is incomplete: {media_home}")
    if not supervisor_script.exists():
        raise FileNotFoundError(f"MediaSpider supervisor is incomplete: {supervisor}")

    bundled_media = output_directory / "MediaSpider"
    if (media_home / "main.py").exists():
        shutil.copytree(
            media_home,
            bundled_media,
            ignore=shutil.ignore_patterns(
                ".git",
                ".venv",
                "venv",
                "__pycache__",
                "*.pyc",
                "*.pyo",
                "data",
                "cache",
                "*_user_data_dir",
            ),
        )
    else:
        bundled_media.mkdir()
        shutil.copy2(foreign_entrypoint, bundled_media / foreign_entrypoint.name)
        shutil.copytree(foreign_sources, bundled_media / "foreign_sources", ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        for name in ["FOREIGN_SOURCES.md", "LICENSE"]:
            source = media_home / name
            if source.exists():
                shutil.copy2(source, bundled_media / name)

    bundled_supervisor = output_directory / "mediaspider-supervisor"
    bundled_supervisor.mkdir()
    shutil.copytree(supervisor / "scripts", bundled_supervisor / "scripts", ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
    for name in ["SKILL.md", "LICENSE"]:
        source = supervisor / name
        if source.exists():
            shutil.copy2(source, bundled_supervisor / name)


def build_bundle(
    skill_root: Path,
    seed_report: Path,
    output_directory: Path,
    archive_reports: list[Path] | None = None,
    media_home: Path = DEFAULT_MEDIASPIDER_HOME,
    supervisor: Path = DEFAULT_MEDIASPIDER_SUPERVISOR,
) -> tuple[Path, Path]:
    output_directory = output_directory.resolve()
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    replace_directory(output_directory, output_directory.parent)

    bundled_skill = output_directory / "cwh-report-skill"
    bundled_skill.mkdir()
    for name in RUNTIME_DIRECTORIES:
        ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo")
        if name == "assets":
            ignore = shutil.ignore_patterns(
                "__pycache__",
                "*.pyc",
                "*.pyo",
                "NotoSansCJKsc-Regular.otf",
            )
        shutil.copytree(
            skill_root / name,
            bundled_skill / name,
            ignore=ignore,
        )
    for name in ROOT_RUNTIME_FILES:
        source = skill_root / name
        if source.exists():
            shutil.copy2(source, bundled_skill / name)
    copy_collectors(output_directory, media_home.resolve(), supervisor.resolve())

    deploy = skill_root / "deploy/with"
    for name in ["Dockerfile", "requirements.txt", "entrypoint.sh", "README.md"]:
        shutil.copy2(deploy / name, output_directory / name)
    with_directory = output_directory / ".with"
    with_directory.mkdir()
    shutil.copy2(deploy / "Dockerfile", with_directory / "Dockerfile")
    private_config = output_directory / "config"
    private_config.mkdir()
    (private_config / ".gitkeep").write_text("", encoding="ascii")

    seed = output_directory / "seed/current"
    dashboard_generator = skill_root / "scripts" / "generate_dashboard.py"
    seed_version = copy_report_seed(
        seed_report,
        seed,
        require_dashboard=True,
        dashboard_generator=dashboard_generator,
    )
    archive_directories: list[str] = []
    archive_root = output_directory / "seed/archive"
    current_resolved = seed_report.resolve()
    for index, archive_report in enumerate(archive_reports or [], 1):
        source = archive_report.resolve()
        if source == current_resolved:
            continue
        target = archive_root / archive_seed_name(source, index)
        copy_report_seed(
            source,
            target,
            require_dashboard=False,
            dashboard_generator=dashboard_generator,
        )
        archive_directories.append(str(source))

    manifest = {
        "status": "ok",
        "output_directory": str(output_directory),
        "archive": str(output_directory.with_suffix(".zip")),
        "seed_report": str(seed_report.resolve()),
        "seed_version": seed_version,
        "archive_reports": archive_directories,
    }
    (output_directory / "bundle_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    archive = Path(shutil.make_archive(str(output_directory), "zip", root_dir=output_directory))
    return output_directory, archive


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the full CWH With application bundle")
    parser.add_argument("--seed-report", type=Path, required=True)
    parser.add_argument(
        "--archive-report",
        type=Path,
        action="append",
        default=[],
        help="Optional historical report directory to preload. Repeat for multiple periods.",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--media-home", type=Path, default=DEFAULT_MEDIASPIDER_HOME)
    parser.add_argument("--mediaspider-supervisor", type=Path, default=DEFAULT_MEDIASPIDER_SUPERVISOR)
    args = parser.parse_args()
    skill_root = Path(__file__).resolve().parents[1]
    output, archive = build_bundle(
        skill_root,
        args.seed_report.resolve(),
        args.output_dir,
        [path.resolve() for path in args.archive_report],
        args.media_home,
        args.mediaspider_supervisor,
    )
    print(json.dumps({"status": "ok", "output": str(output), "archive": str(archive)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
