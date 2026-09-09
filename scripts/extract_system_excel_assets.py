from __future__ import annotations

import argparse
import posixpath
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pkg": "http://schemas.openxmlformats.org/package/2006/relationships",
    "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}


def rels_path(part_path: str) -> str:
    parent = posixpath.dirname(part_path)
    name = posixpath.basename(part_path)
    return posixpath.join(parent, "_rels", f"{name}.rels")


def resolve_target(part_path: str, target: str) -> str:
    if target.startswith("/"):
        return posixpath.normpath(target.lstrip("/"))
    return posixpath.normpath(posixpath.join(posixpath.dirname(part_path), target))


def relationship_map(archive: zipfile.ZipFile, part_path: str) -> dict[str, str]:
    path = rels_path(part_path)
    if path not in archive.namelist():
        return {}
    root = ET.fromstring(archive.read(path))
    return {
        relation.attrib["Id"]: resolve_target(part_path, relation.attrib["Target"])
        for relation in root.findall("pkg:Relationship", NS)
    }


def worksheet_path(archive: zipfile.ZipFile, sheet_name: str) -> str | None:
    workbook_path = "xl/workbook.xml"
    root = ET.fromstring(archive.read(workbook_path))
    relationships = relationship_map(archive, workbook_path)
    for sheet in root.findall("main:sheets/main:sheet", NS):
        if sheet.attrib.get("name") == sheet_name:
            relation_id = sheet.attrib.get(f"{{{NS['rel']}}}id")
            return relationships.get(relation_id or "")
    return None


def worksheet_index(workbook_path: Path, sheet_name: str) -> int | None:
    with zipfile.ZipFile(workbook_path) as archive:
        root = ET.fromstring(archive.read("xl/workbook.xml"))
        for index, sheet in enumerate(root.findall("main:sheets/main:sheet", NS), 1):
            if sheet.attrib.get("name") == sheet_name:
                return index
    return None


def extract_sheet_picture(
    workbook_path: Path,
    sheet_name: str,
    output_stem: Path,
) -> Path | None:
    with zipfile.ZipFile(workbook_path) as archive:
        sheet_path = worksheet_path(archive, sheet_name)
        if not sheet_path or sheet_path not in archive.namelist():
            return None
        sheet_root = ET.fromstring(archive.read(sheet_path))
        drawing = sheet_root.find("main:drawing", NS)
        if drawing is None:
            return None
        sheet_relationships = relationship_map(archive, sheet_path)
        drawing_id = drawing.attrib.get(f"{{{NS['rel']}}}id")
        drawing_path = sheet_relationships.get(drawing_id or "")
        if not drawing_path or drawing_path not in archive.namelist():
            return None
        drawing_root = ET.fromstring(archive.read(drawing_path))
        drawing_relationships = relationship_map(archive, drawing_path)
        for blip in drawing_root.findall(".//a:blip", NS):
            relation_id = blip.attrib.get(f"{{{NS['rel']}}}embed")
            image_path = drawing_relationships.get(relation_id or "")
            if not image_path or image_path not in archive.namelist():
                continue
            suffix = Path(image_path).suffix.lower() or ".png"
            destination = output_stem.with_suffix(suffix)
            destination.write_bytes(archive.read(image_path))
            return destination
    return None


def export_excel_charts(workbook_path: Path, output_dir: Path) -> dict[str, str]:
    script = Path(__file__).with_name("export_excel_charts.vbs")
    if not script.exists():
        return {}
    workbook_copy = output_dir / "_system_chart_source.xlsx"
    try:
        trend_sheet_index = worksheet_index(workbook_path, "总事件")
        topic_sheet_index = worksheet_index(workbook_path, "子事件数据汇总")
        if not trend_sheet_index or not topic_sheet_index:
            return {}
        shutil.copy2(workbook_path, workbook_copy)
        subprocess.run(
            [
                "cscript.exe",
                "//nologo",
                str(script),
                str(workbook_copy.resolve()),
                str(output_dir.resolve()),
                str(trend_sheet_index),
                str(topic_sheet_index),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return {}
    finally:
        try:
            workbook_copy.unlink(missing_ok=True)
        except OSError:
            pass
    candidates = {
        "trend_distribution": output_dir / "trend_distribution_system.png",
        "topic_distribution": output_dir / "topic_distribution_system.png",
    }
    return {key: str(path) for key, path in candidates.items() if path.exists() and path.stat().st_size > 0}


def extract_system_excel_assets(workbook_path: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    assets: dict[str, Any] = export_excel_charts(workbook_path, output_dir)
    picture_fallbacks = {
        "trend_distribution": ("总事件", output_dir / "trend_distribution_system"),
        "topic_distribution": ("子事件数据汇总", output_dir / "topic_distribution_system"),
    }
    for key, (sheet_name, output_stem) in picture_fallbacks.items():
        if key in assets:
            continue
        try:
            picture = extract_sheet_picture(workbook_path, sheet_name, output_stem)
        except (OSError, KeyError, ET.ParseError, zipfile.BadZipFile):
            picture = None
        if picture:
            assets[key] = str(picture)
    try:
        wordcloud = extract_sheet_picture(workbook_path, "词云", output_dir / "hotword_distribution_system")
    except (OSError, KeyError, ET.ParseError, zipfile.BadZipFile):
        wordcloud = None
    if wordcloud:
        assets["hotword_distribution"] = str(wordcloud)
    assets["source_workbook"] = str(workbook_path)
    return assets


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract existing CWH charts and word-cloud image from a monitoring workbook.")
    parser.add_argument("system_workbook")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    assets = extract_system_excel_assets(Path(args.system_workbook), Path(args.out_dir))
    for key, value in assets.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
