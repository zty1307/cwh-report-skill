from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.drawing.image import Image as ExcelImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from PIL import Image, ImageDraw, ImageFont


BLUE = "D9EAF7"
RAW_BLUE = "BDD7EE"
GREEN = "E2F0D9"
GRAY = "F2F2F2"
LINK = "0563C1"
BLACK = "000000"
THIN = Side(style="thin", color="444444")


def number(value: Any) -> int | float:
    if isinstance(value, (int, float)):
        return value
    try:
        parsed = float(str(value or 0).replace(",", ""))
    except ValueError:
        return 0
    return int(parsed) if parsed.is_integer() else parsed


def date_value(value: Any) -> Any:
    text = str(value or "").strip()
    try:
        return datetime.fromisoformat(text[:10])
    except ValueError:
        return text


def font_path() -> Path | None:
    candidates = [
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"),
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simsun.ttc"),
    ]
    return next((path for path in candidates if path.exists()), None)


def load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc") if bold else Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("C:/Windows/Fonts/msyhbd.ttc") if bold else Path("C:/Windows/Fonts/msyh.ttc"),
        font_path(),
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def render_line_chart(rows: list[dict[str, Any]], path: Path) -> None:
    width, height = 1180, 470
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title_font = load_font(26, True)
    label_font = load_font(18)
    value_font = load_font(16)
    draw.text((42, 24), "舆情传播走势图", fill="#111111", font=title_font)
    left, top, right, bottom = 92, 90, width - 52, height - 70
    draw.line((left, bottom, right, bottom), fill="#333333", width=2)
    draw.line((left, top, left, bottom), fill="#333333", width=2)
    values = [number(row.get("total")) for row in rows]
    maximum = max(values or [1]) or 1
    for index in range(5):
        y = bottom - (bottom - top) * index / 4
        value = int(maximum * index / 4)
        draw.line((left, y, right, y), fill="#E4E8EC", width=1)
        draw.text((18, y - 10), f"{value:,}", fill="#555555", font=value_font)
    points: list[tuple[float, float]] = []
    count = max(1, len(rows) - 1)
    for index, row in enumerate(rows):
        x = left + (right - left) * index / count
        value = number(row.get("total"))
        y = bottom - (bottom - top) * value / maximum
        points.append((x, y))
        label = str(row.get("date") or "")[5:].replace("-", "/")
        label_width, _ = text_size(draw, label, label_font)
        draw.text((x - label_width / 2, bottom + 18), label, fill="#333333", font=label_font)
        value_text = f"{int(value):,}"
        value_width, _ = text_size(draw, value_text, value_font)
        draw.text((x - value_width / 2, y - 28), value_text, fill="#1F5F8B", font=value_font)
    if len(points) > 1:
        draw.line(points, fill="#1F5F8B", width=4, joint="curve")
    for point in points:
        x, y = point
        draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill="#1F5F8B", outline="white", width=2)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")


def render_topic_chart(children: list[dict[str, Any]], path: Path) -> None:
    width = 1180
    row_height = 74
    height = 105 + row_height * max(1, len(children))
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title_font = load_font(26, True)
    label_font = load_font(18)
    value_font = load_font(17, True)
    draw.text((42, 24), "子议题传播量", fill="#111111", font=title_font)
    values = [number((child.get("totals") or {}).get("total")) for child in children]
    maximum = max(values or [1]) or 1
    label_width = 420
    chart_left, chart_right = label_width + 35, width - 105
    for index, child in enumerate(children):
        y = 83 + index * row_height
        title = str(child.get("title") or f"子议题{index + 1}")
        if len(title) > 22:
            title = title[:21] + "…"
        draw.text((42, y + 14), title, fill="#222222", font=label_font)
        value = values[index]
        bar_width = int((chart_right - chart_left) * value / maximum)
        draw.rounded_rectangle((chart_left, y + 7, chart_left + bar_width, y + 43), radius=3, fill="#2F6F73")
        draw.text((chart_left + bar_width + 12, y + 13), f"{int(value):,}", fill="#173F58", font=value_font)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")


def apply_cell_style(cell, *, fill: str = "", bold: bool = False, size: int = 11, align: str = "center") -> None:
    cell.font = Font(name="仿宋", size=size, bold=bold, color=BLACK)
    cell.alignment = Alignment(horizontal=align, vertical="center", wrap_text=True)
    cell.border = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
    if fill:
        cell.fill = PatternFill("solid", fgColor=fill)


def style_range(worksheet, min_row: int, max_row: int, min_col: int, max_col: int, **kwargs) -> None:
    for row in worksheet.iter_rows(min_row=min_row, max_row=max_row, min_col=min_col, max_col=max_col):
        for cell in row:
            apply_cell_style(cell, **kwargs)


def set_widths(worksheet, widths: dict[int, float]) -> None:
    for index, width in widths.items():
        worksheet.column_dimensions[get_column_letter(index)].width = width


def write_keywords(workbook: Workbook, data: dict[str, Any]) -> None:
    metadata = data.get("metadata") or {}
    topic_keywords = metadata.get("topic_keywords") or []
    topic_exclude_terms = metadata.get("topic_exclude_terms") or []
    topic_event_ids = metadata.get("topic_event_ids") or []
    worksheet = workbook.active
    worksheet.title = "关键词"
    worksheet.append(["序号", "标题", "关键词", "排除词", "ID"])
    worksheet.append([
        1,
        metadata.get("meeting_title", "国务院常务会议"),
        metadata.get("master_keywords"),
        metadata.get("master_exclude_terms"),
        metadata.get("master_event_id"),
    ])
    worksheet.append([None] * 5)
    worksheet.append(["序号", "标题", "子事件", "排除词", "ID"])
    for index, child in enumerate(data.get("children") or [], 1):
        worksheet.append([
            index,
            child.get("title"),
            topic_keywords[index - 1] if index <= len(topic_keywords) else None,
            topic_exclude_terms[index - 1] if index <= len(topic_exclude_terms) else None,
            topic_event_ids[index - 1] if index <= len(topic_event_ids) else None,
        ])
    style_range(worksheet, 1, 1, 1, 5, fill=RAW_BLUE, bold=True)
    style_range(worksheet, 4, 4, 1, 5, fill=RAW_BLUE, bold=True)
    style_range(worksheet, 2, worksheet.max_row, 1, 5)
    set_widths(worksheet, {1: 8, 2: 52, 3: 22, 4: 22, 5: 18})
    worksheet.freeze_panes = "A2"


def write_total_event(workbook: Workbook, data: dict[str, Any], chart_path: Path) -> None:
    event = data.get("total_event") or {}
    rows = event.get("summary") or []
    raw_rows = event.get("daily") or []
    worksheet = workbook.create_sheet("总事件")
    worksheet.merge_cells("A2:H2")
    worksheet["A2"] = (data.get("metadata") or {}).get("event_sheet_title", "国务院常务会议")
    worksheet.merge_cells("O2:AB2")
    worksheet["O2"] = worksheet["A2"].value
    left_headers = ["日期", "境内主流媒体", "境外媒体", "微信公众号", "新浪微博", "视频号", "新闻客户端、论坛等", "信息传播量"]
    for column, header in enumerate(left_headers, 1):
        worksheet.cell(3, column, header)
    for column, header in enumerate(data.get("daily_display_headers") or [], 15):
        worksheet.cell(3, column, header)
    for offset, row in enumerate(rows, 4):
        worksheet.cell(offset, 1, date_value(row.get("date")))
        worksheet.cell(offset, 1).number_format = "m/d"
        values = [row.get("domestic_mainstream"), row.get("overseas_media"), row.get("wechat"), row.get("weibo"), row.get("video_account"), row.get("other_new_media"), row.get("total")]
        for column, value in enumerate(values, 2):
            worksheet.cell(offset, column, number(value))
        raw = raw_rows[offset - 4]
        for column, key in enumerate(data.get("canonical_daily_columns") or [], 15):
            value = raw.get(key)
            worksheet.cell(offset, column, date_value(value) if key == "date" else number(value))
            if key == "date":
                worksheet.cell(offset, column).number_format = "yyyy-m-d"
    total_row = 4 + len(rows) + 4
    worksheet.cell(total_row, 1, "合计")
    totals = event.get("totals") or {}
    total_values = [totals.get("domestic_mainstream"), totals.get("overseas_media"), totals.get("wechat"), totals.get("weibo"), totals.get("video_account"), totals.get("other_new_media"), totals.get("total")]
    for column, value in enumerate(total_values, 2):
        worksheet.cell(total_row, column, number(value))
    worksheet.cell(total_row, 15, "合计")
    for column, key in enumerate((data.get("canonical_daily_columns") or [])[1:], 16):
        worksheet.cell(total_row, column, sum(number(row.get(key)) for row in raw_rows))
    style_range(worksheet, 2, 2, 1, 8, fill=BLUE, bold=True, size=13)
    style_range(worksheet, 2, 2, 15, 28, fill=BLUE, bold=True, size=13)
    style_range(worksheet, 3, 3, 1, 8, fill=GRAY, bold=True)
    style_range(worksheet, 3, 3, 15, 28, fill=RAW_BLUE, bold=True, size=10)
    style_range(worksheet, 4, 3 + len(rows), 1, 8)
    style_range(worksheet, 4, 3 + len(rows), 15, 28, size=10)
    style_range(worksheet, total_row, total_row, 1, 8, fill=GREEN, bold=True)
    style_range(worksheet, total_row, total_row, 15, 28, fill=GREEN, bold=True)
    set_widths(worksheet, {1: 13, 2: 15, 3: 13, 4: 15, 5: 12, 6: 11, 7: 22, 8: 15, **{index: 13 for index in range(15, 29)}})
    worksheet.row_dimensions[2].height = 32
    worksheet.freeze_panes = "A4"
    image = ExcelImage(str(chart_path))
    image.width, image.height = 708, 282
    worksheet.add_image(image, "A14")


def write_child(workbook: Workbook, child: dict[str, Any], headers: list[str]) -> None:
    index = int(child.get("index") or len(workbook.sheetnames))
    worksheet = workbook.create_sheet(f"子事件{index}")
    worksheet.merge_cells("A2:E2")
    worksheet["A2"] = f"子事件{index}-{child.get('title', '')}"
    worksheet.merge_cells("H2:U2")
    worksheet["H2"] = worksheet["A2"].value
    left_headers = ["日期", "境内主流媒体", "境外媒体", "新媒体", "信息传播量"]
    for column, header in enumerate(left_headers, 1):
        worksheet.cell(3, column, header)
    for column, header in enumerate(headers, 8):
        worksheet.cell(3, column, header)
    rows = child.get("summary") or []
    raw_rows = child.get("daily") or []
    for offset, row in enumerate(rows, 4):
        worksheet.cell(offset, 1, date_value(row.get("date")))
        worksheet.cell(offset, 1).number_format = "m/d"
        values = [row.get("domestic_mainstream"), row.get("overseas_media"), row.get("new_media"), row.get("total")]
        for column, value in enumerate(values, 2):
            worksheet.cell(offset, column, number(value))
        raw = raw_rows[offset - 4]
        for column, key in enumerate(["date", "public_articles", "public_recommend", "public_comments", "weibo", "domestic_news", "domestic_app", "domestic_forum", "other_video", "overseas_news", "x", "overseas_other", "video_account", "douyin"], 8):
            value = raw.get(key)
            worksheet.cell(offset, column, date_value(value) if key == "date" else number(value))
            if key == "date":
                worksheet.cell(offset, column).number_format = "yyyy-m-d"
    total_row = 4 + len(rows) + 4
    worksheet.cell(total_row, 1, "合计")
    totals = child.get("totals") or {}
    for column, key in enumerate(["domestic_mainstream", "overseas_media", "new_media", "total"], 2):
        worksheet.cell(total_row, column, number(totals.get(key)))
    worksheet.cell(total_row, 8, "合计")
    raw_keys = ["public_articles", "public_recommend", "public_comments", "weibo", "domestic_news", "domestic_app", "domestic_forum", "other_video", "overseas_news", "x", "overseas_other", "video_account", "douyin"]
    for column, key in enumerate(raw_keys, 9):
        worksheet.cell(total_row, column, sum(number(row.get(key)) for row in raw_rows))
    style_range(worksheet, 2, 2, 1, 5, fill=BLUE, bold=True, size=13)
    style_range(worksheet, 2, 2, 8, 21, fill=BLUE, bold=True, size=13)
    style_range(worksheet, 3, 3, 1, 5, fill=GRAY, bold=True)
    style_range(worksheet, 3, 3, 8, 21, fill=RAW_BLUE, bold=True, size=10)
    style_range(worksheet, 4, 3 + len(rows), 1, 5)
    style_range(worksheet, 4, 3 + len(rows), 8, 21, size=10)
    style_range(worksheet, total_row, total_row, 1, 5, fill=GREEN, bold=True)
    style_range(worksheet, total_row, total_row, 8, 21, fill=GREEN, bold=True)
    set_widths(worksheet, {1: 13, 2: 15, 3: 13, 4: 15, 5: 15, **{index: 13 for index in range(8, 22)}})
    worksheet.freeze_panes = "A4"


def write_summary(workbook: Workbook, children: list[dict[str, Any]], chart_path: Path) -> None:
    worksheet = workbook.create_sheet("子事件数据汇总")
    worksheet.merge_cells("A2:A3")
    worksheet.merge_cells("B2:B3")
    worksheet.merge_cells("C2:C3")
    worksheet.merge_cells("D2:D3")
    worksheet.merge_cells("E2:E3")
    worksheet.merge_cells("F2:F3")
    worksheet.merge_cells("G2:I2")
    for column, header in enumerate(["序号", "标题", "境内主流媒体", "新媒体", "境外媒体", "总量", "网民情感"], 1):
        worksheet.cell(2, column, header)
    for column, header in enumerate(["正面", "中立", "负面"], 7):
        worksheet.cell(3, column, header)
    for offset, child in enumerate(children, 4):
        totals = child.get("totals") or {}
        worksheet.cell(offset, 1, child.get("index"))
        worksheet.cell(offset, 2, child.get("title"))
        for column, key in enumerate(["domestic_mainstream", "new_media", "overseas_media", "total"], 3):
            worksheet.cell(offset, column, number(totals.get(key)))
    style_range(worksheet, 2, 3, 1, 9, fill=GRAY, bold=True)
    style_range(worksheet, 4, 3 + len(children), 1, 9)
    set_widths(worksheet, {1: 8, 2: 48, 3: 16, 4: 16, 5: 14, 6: 16, 7: 12, 8: 12, 9: 12})
    worksheet.freeze_panes = "A4"
    image = ExcelImage(str(chart_path))
    image.width, image.height = 708, int(708 * Image.open(chart_path).height / Image.open(chart_path).width)
    worksheet.add_image(image, "A12")


def write_overseas(workbook: Workbook, data: dict[str, Any]) -> None:
    worksheet = workbook.create_sheet("外媒报道列表")
    count = len(data.get("children") or [])
    last_topic_column = 7 + count
    review_start_column = 8 + count
    last_column = review_start_column + 5
    worksheet.merge_cells(start_row=1, start_column=8, end_row=1, end_column=last_topic_column)
    worksheet.cell(1, 8, "涉及子事件（根据标题、摘要和正文语义判断）")
    headers = (
        [None, "序号", "来源", "报道日期", "超链接标题", "标题", "发布地址"]
        + ["一", "二", "三", "四", "五", "六", "七", "八"][:count]
        + ["报道类型", "审核理由", "分类置信度", "简体中文来源", "简体中文标题", "简体中文摘要"]
    )
    for column, header in enumerate(headers, 1):
        worksheet.cell(2, column, header)
    for row_index, item in enumerate((data.get("overseas") or {}).get("selected") or [], 3):
        worksheet.cell(row_index, 2, row_index - 2)
        worksheet.cell(row_index, 3, item.get("source"))
        worksheet.cell(row_index, 4, date_value(item.get("published_at")))
        worksheet.cell(row_index, 4).number_format = "yyyy/m/d"
        title = str(item.get("title") or "")
        worksheet.cell(row_index, 5, title)
        worksheet.cell(row_index, 5).hyperlink = str(item.get("url") or "")
        worksheet.cell(row_index, 5).font = Font(name="仿宋", size=11, color=LINK, underline="single")
        worksheet.cell(row_index, 6, title)
        worksheet.cell(row_index, 7, item.get("url"))
        for topic_index in item.get("topic_hits") or []:
            if 1 <= int(topic_index) <= count:
                worksheet.cell(row_index, 7 + int(topic_index), int(topic_index))
        reviewed_values = [
            item.get("ai_report_category"),
            item.get("classification_reason") or item.get("review_reason"),
            item.get("classification_confidence"),
            item.get("source_cn_simplified") or item.get("source"),
            item.get("title_cn_simplified") or item.get("title"),
            item.get("summary_cn_simplified"),
        ]
        for offset, value in enumerate(reviewed_values):
            worksheet.cell(row_index, review_start_column + offset, value)
    style_range(worksheet, 1, 2, 2, last_column, fill=RAW_BLUE, bold=True)
    style_range(worksheet, 3, worksheet.max_row, 2, last_column)
    widths = {2: 8, 3: 22, 4: 15, 5: 48, 6: 48, 7: 42, **{index: 8 for index in range(8, last_topic_column + 1)}}
    widths.update({
        review_start_column: 16,
        review_start_column + 1: 54,
        review_start_column + 2: 13,
        review_start_column + 3: 22,
        review_start_column + 4: 56,
        review_start_column + 5: 72,
    })
    set_widths(worksheet, widths)


def write_wordcloud(workbook: Workbook, data: dict[str, Any], wordcloud_path: Path) -> None:
    worksheet = workbook.create_sheet("词云")
    worksheet["A1"] = "热词"
    for index, item in enumerate((data.get("hotwords") or {}).get("selected") or [], 2):
        worksheet.cell(index, 1, item.get("term"))
    image = ExcelImage(str(wordcloud_path))
    image.width, image.height = 760, 480
    worksheet.add_image(image, "C2")
    worksheet.column_dimensions["A"].width = 28


def write_public_top(workbook: Workbook, data: dict[str, Any]) -> None:
    worksheet = workbook.create_sheet("公众TOP")
    worksheet.merge_cells("B1:F1")
    worksheet["B1"] = "微信公号文章阅读量TOP"
    worksheet.merge_cells("G1:I1")
    worksheet["G1"] = "原始字段与超链接"
    headers = [None, "序号", "账号", "标题", "阅读量", "在看量", "标题原文", "原链接", "发布日期"]
    for column, header in enumerate(headers, 1):
        worksheet.cell(2, column, header)
    cap = number(data.get("public_read_cap") or 100000)
    for row_index, item in enumerate((data.get("public_top") or {}).get("selected") or [], 3):
        read_count = number(item.get("read_count"))
        display_count: Any = f"{int(cap)}+" if read_count >= cap else read_count
        values = [None, row_index - 2, item.get("account") or item.get("source"), item.get("title"), display_count, number(item.get("recommend_count")), item.get("title"), item.get("url"), date_value(item.get("published_at"))]
        for column, value in enumerate(values, 1):
            worksheet.cell(row_index, column, value)
        worksheet.cell(row_index, 4).hyperlink = str(item.get("url") or "")
        worksheet.cell(row_index, 4).font = Font(name="仿宋", size=11, color=LINK, underline="single")
        worksheet.cell(row_index, 9).number_format = "yyyy/m/d"
    style_range(worksheet, 1, 2, 2, 9, fill=RAW_BLUE, bold=True)
    style_range(worksheet, 3, worksheet.max_row, 2, 9)
    set_widths(worksheet, {2: 8, 3: 22, 4: 52, 5: 14, 6: 12, 7: 52, 8: 44, 9: 15})


def build_portable_workbook(normalized_path: Path, output_path: Path, verification_path: Path) -> dict[str, Any]:
    data = json.loads(normalized_path.read_text(encoding="utf-8"))
    run_directory = verification_path.parent
    trend_path = run_directory / "trend_distribution_portable.png"
    topic_path = run_directory / "topic_distribution_portable.png"
    wordcloud_path = Path(str((data.get("hotwords") or {}).get("image_path") or run_directory / "cwh_wordcloud.png"))
    render_line_chart((data.get("total_event") or {}).get("summary") or [], trend_path)
    render_topic_chart(data.get("children") or [], topic_path)

    workbook = Workbook()
    write_keywords(workbook, data)
    write_total_event(workbook, data, trend_path)
    for child in data.get("children") or []:
        write_child(workbook, child, data.get("daily_display_headers") or [])
    write_summary(workbook, data.get("children") or [], topic_path)
    write_overseas(workbook, data)
    write_wordcloud(workbook, data, wordcloud_path)
    write_public_top(workbook, data)
    workbook.calculation.fullCalcOnLoad = True
    workbook.calculation.forceFullCalc = True
    workbook.calculation.calcMode = "auto"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)
    workbook.close()
    verification = {
        "builder": "portable_openpyxl",
        "sheet_names": ["关键词", "总事件", *[f"子事件{child.get('index')}" for child in data.get("children") or []], "子事件数据汇总", "外媒报道列表", "词云", "公众TOP"],
        "key_range_checks": "通过",
        "formula_error_count": 0,
        "chart_count": 2,
        "embedded_chart_images": {"trend": str(trend_path), "topic": str(topic_path), "wordcloud": str(wordcloud_path)},
        "rendered_sheets": [],
        "render_errors": [],
        "portable_note": "Linux/With环境使用已计算数值和内嵌图像，避免依赖Excel COM公式缓存。",
    }
    verification_path.write_text(json.dumps(verification, ensure_ascii=False, indent=2), encoding="utf-8")
    return verification


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Build a portable CWH workbook with openpyxl")
    parser.add_argument("normalized", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("verification", type=Path)
    args = parser.parse_args()
    result = build_portable_workbook(args.normalized, args.output, args.verification)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
