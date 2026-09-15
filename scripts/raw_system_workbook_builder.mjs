import fs from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);
const artifactTool = await import(pathToFileURL(require.resolve("@oai/artifact-tool")).href);
const { SpreadsheetFile, Workbook } = artifactTool;

const [normalizedPath, outputPath, previewsDir, verificationPath] = process.argv.slice(2);
if (!normalizedPath || !outputPath || !previewsDir || !verificationPath) {
  throw new Error("Usage: node raw_system_workbook_builder.mjs <normalized.json> <output.xlsx> <previews-dir> <verification.json>");
}

const data = JSON.parse(await fs.readFile(normalizedPath, "utf8"));
const workbook = Workbook.create();

const SHEET_ORDER = [
  "关键词",
  "总事件",
  ...data.children.map((child) => `子事件${child.index}`),
  "子事件数据汇总",
  "外媒报道列表",
  "词云",
  "公众TOP",
];

const COLORS = {
  title: "#D9EAF7",
  rawHeader: "#BDD7EE",
  summaryHeader: "#E2F0D9",
  secondaryHeader: "#F2F2F2",
  note: "#FFF2CC",
  border: "#444444",
  link: "#0563C1",
};

const borderAll = { preset: "all", style: "thin", color: COLORS.border };
const titleFormat = {
  fill: COLORS.title,
  font: { name: "仿宋", size: 13, bold: true, color: "#000000" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
  borders: borderAll,
};
const headerFormat = {
  fill: COLORS.secondaryHeader,
  font: { name: "仿宋", size: 12, bold: true, color: "#000000" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
  borders: borderAll,
};
const rawHeaderFormat = {
  fill: COLORS.rawHeader,
  font: { name: "仿宋", size: 10, bold: true, color: "#000000" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
  borders: borderAll,
};
const bodyFormat = {
  font: { name: "仿宋", size: 11, color: "#000000" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  borders: borderAll,
};

function columnLetter(index) {
  let value = index;
  let result = "";
  while (value > 0) {
    const remainder = (value - 1) % 26;
    result = String.fromCharCode(65 + remainder) + result;
    value = Math.floor((value - 1) / 26);
  }
  return result;
}

function dateValue(value) {
  return new Date(`${String(value).slice(0, 10)}T00:00:00`);
}

function dailyMatrix(rows) {
  return rows.map((row) => [
    dateValue(row.date),
    row.public_articles,
    row.public_recommend,
    row.public_comments,
    row.weibo,
    row.domestic_news,
    row.domestic_app,
    row.domestic_forum,
    row.other_video,
    row.overseas_news,
    row.x,
    row.overseas_other,
    row.video_account,
    row.douyin,
  ]);
}

function applyTableStyle(sheet, rangeAddress, headerAddress = null) {
  sheet.getRange(rangeAddress).format = bodyFormat;
  if (headerAddress) sheet.getRange(headerAddress).format = headerFormat;
}

function setWidths(sheet, widths) {
  for (const [column, width] of Object.entries(widths)) {
    sheet.getRange(`${column}1:${column}200`).format.columnWidth = width;
  }
}

function buildKeywordsSheet() {
  const sheet = workbook.worksheets.add("关键词");
  sheet.showGridLines = false;
  const metadata = data.metadata || {};
  const topicKeywords = metadata.topic_keywords || [];
  const topicExcludeTerms = metadata.topic_exclude_terms || [];
  const topicEventIds = metadata.topic_event_ids || [];
  sheet.getRange("A1:G1").values = [["序号", "标题", "关键词", "排除词", "ID", "", ""]];
  sheet.getRange("A2:G2").values = [[1, metadata.meeting_title, metadata.master_keywords || "", metadata.master_exclude_terms || "", metadata.master_event_id || "", "", ""]];
  sheet.getRange("A4:G4").values = [["序号", "标题", "子事件", "排除词", "ID", "", ""]];
  const topicRows = data.children.map((child, index) => [
    index + 1,
    child.title,
    topicKeywords[index] || "",
    topicExcludeTerms[index] || "",
    topicEventIds[index] || "",
    "",
    "",
  ]);
  sheet.getRange(`A5:G${4 + topicRows.length}`).values = topicRows;
  applyTableStyle(sheet, `A1:E${4 + topicRows.length}`);
  sheet.getRange("A1:E1").format = headerFormat;
  sheet.getRange("A4:E4").format = headerFormat;
  sheet.getRange("B2:B2").format.wrapText = true;
  sheet.getRange(`B5:B${4 + topicRows.length}`).format.wrapText = true;
  setWidths(sheet, { A: 8, B: 46, C: 44, D: 28, E: 20, F: 8, G: 20 });
  sheet.getRange("A2:G2").format.rowHeight = 42;
  sheet.freezePanes.freezeRows(1);
  return sheet;
}

function buildTotalSheet() {
  const sheet = workbook.worksheets.add("总事件");
  sheet.showGridLines = false;
  sheet.mergeCells("A2:H2");
  sheet.mergeCells("O2:AB2");
  sheet.getRange("A2").values = [[data.metadata.event_sheet_title]];
  sheet.getRange("O2").formulas = [["=A2"]];
  sheet.getRange("A2:H2").format = titleFormat;
  sheet.getRange("O2:AB2").format = titleFormat;

  const leftHeaders = ["日期", (data.channel_labels?.domestic_mainstream || "境内主流媒体"), "境外媒体", "微信公众号", "新浪微博", "视频号", "新闻客户端、论坛等", "信息传播量"];
  sheet.getRange("A3:H3").values = [leftHeaders];
  sheet.getRange("O3:AB3").values = [data.daily_display_headers];
  sheet.getRange("A3:H3").format = headerFormat;
  sheet.getRange("O3:AB3").format = rawHeaderFormat;

  const startRow = 4;
  const lastDataRow = startRow + data.total_event.daily.length - 1;
  sheet.getRange(`O${startRow}:AB${lastDataRow}`).values = dailyMatrix(data.total_event.daily);
  sheet.getRange(`O${startRow}:AB${lastDataRow}`).format = bodyFormat;
  sheet.getRange(`O${startRow}:O${lastDataRow}`).format.numberFormat = "yyyy/m/d";

  for (let row = startRow; row <= lastDataRow; row += 1) {
    sheet.getRange(`A${row}:H${row}`).formulas = [[
      `=TEXT(O${row},"m/d")`,
      `=T${row}`,
      `=X${row}`,
      `=P${row}+Q${row}+R${row}`,
      `=S${row}`,
      `=AA${row}`,
      `=U${row}+V${row}+W${row}+Y${row}+Z${row}+AB${row}`,
      `=SUM(B${row}:G${row})`,
    ]];
  }
  sheet.getRange(`A${startRow}:H${lastDataRow}`).format = bodyFormat;
  sheet.getRange(`A${startRow}:A${lastDataRow}`).format.numberFormat = "yyyy/m/d";

  const totalRow = Math.max(12, lastDataRow + 1);
  sheet.getRange(`A${totalRow}`).values = [["合计"]];
  for (let column = 2; column <= 8; column += 1) {
    const letter = columnLetter(column);
    sheet.getRange(`${letter}${totalRow}`).formulas = [[`=SUM(${letter}${startRow}:${letter}${lastDataRow})`]];
  }
  sheet.getRange(`O${totalRow}`).values = [["合计"]];
  for (let column = 16; column <= 28; column += 1) {
    const letter = columnLetter(column);
    sheet.getRange(`${letter}${totalRow}`).formulas = [[`=SUM(${letter}${startRow}:${letter}${lastDataRow})`]];
  }
  sheet.getRange(`A${totalRow}:H${totalRow}`).format = { ...headerFormat, fill: COLORS.summaryHeader };
  sheet.getRange(`O${totalRow}:AB${totalRow}`).format = { ...rawHeaderFormat, fill: COLORS.summaryHeader };

  const chart = sheet.charts.add("line", { chartType: "line", hasLegend: true });
  const series = chart.series.add("信息传播量");
  series.categoryFormula = `'总事件'!$A$${startRow}:$A$${lastDataRow}`;
  series.formula = `'总事件'!$H$${startRow}:$H$${lastDataRow}`;
  chart.hasLegend = true;
  chart.legend = { position: "bottom" };
  chart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 10 } };
  chart.yAxis = { numberFormatCode: "#,##0", textStyle: { fontSize: 10 } };
  chart.setPosition("I2", "N19");

  setWidths(sheet, {
    A: 12, B: 10, C: 10, D: 13, E: 13, F: 10, G: 16, H: 12,
    I: 10.5625, J: 13, K: 10.9375, L: 15.8125, M: 10.9375, N: 22.4375,
    O: 12, P: 9, Q: 12, R: 12, S: 10, T: 10, U: 10, V: 10, W: 10,
    X: 10, Y: 8, Z: 10, AA: 10, AB: 10,
  });
  sheet.getRange("A3:AB3").format.rowHeight = 34;
  sheet.freezePanes.freezeRows(3);
  return { sheet, totalRow, startRow, lastDataRow };
}

function buildChildSheet(child) {
  const sheetName = `子事件${child.index}`;
  const sheet = workbook.worksheets.add(sheetName);
  sheet.showGridLines = false;
  sheet.mergeCells("A2:E2");
  sheet.mergeCells("H2:U2");
  sheet.getRange("A2").values = [[`${sheetName}-${child.title}`]];
  sheet.getRange("H2").formulas = [["=A2"]];
  sheet.getRange("A2:E2").format = titleFormat;
  sheet.getRange("H2:U2").format = titleFormat;
  sheet.getRange("A3:E3").values = [["日期", (data.channel_labels?.domestic_mainstream || "境内主流媒体"), "境外媒体", "新媒体", "信息传播量"]];
  sheet.getRange("H3:U3").values = [data.daily_display_headers];
  sheet.getRange("A3:E3").format = headerFormat;
  sheet.getRange("H3:U3").format = rawHeaderFormat;

  const startRow = 4;
  const lastDataRow = startRow + child.daily.length - 1;
  sheet.getRange(`H${startRow}:U${lastDataRow}`).values = dailyMatrix(child.daily);
  sheet.getRange(`H${startRow}:U${lastDataRow}`).format = bodyFormat;
  sheet.getRange(`H${startRow}:H${lastDataRow}`).format.numberFormat = "yyyy/m/d";
  for (let row = startRow; row <= lastDataRow; row += 1) {
    sheet.getRange(`A${row}:E${row}`).formulas = [[
      `=TEXT(H${row},"m/d")`,
      `=M${row}`,
      `=Q${row}`,
      `=I${row}+J${row}+K${row}+L${row}+N${row}+O${row}+P${row}+R${row}+S${row}+T${row}+U${row}`,
      `=SUM(B${row}:D${row})`,
    ]];
  }
  sheet.getRange(`A${startRow}:E${lastDataRow}`).format = bodyFormat;
  sheet.getRange(`A${startRow}:A${lastDataRow}`).format.numberFormat = "yyyy/m/d";

  const totalRow = Math.max(12, lastDataRow + 1);
  sheet.getRange(`A${totalRow}`).values = [["合计"]];
  for (let column = 2; column <= 5; column += 1) {
    const letter = columnLetter(column);
    sheet.getRange(`${letter}${totalRow}`).formulas = [[`=SUM(${letter}${startRow}:${letter}${lastDataRow})`]];
  }
  sheet.getRange(`H${totalRow}`).values = [["合计"]];
  for (let column = 9; column <= 21; column += 1) {
    const letter = columnLetter(column);
    sheet.getRange(`${letter}${totalRow}`).formulas = [[`=SUM(${letter}${startRow}:${letter}${lastDataRow})`]];
  }
  sheet.getRange(`A${totalRow}:E${totalRow}`).format = { ...headerFormat, fill: COLORS.summaryHeader };
  sheet.getRange(`H${totalRow}:U${totalRow}`).format = { ...rawHeaderFormat, fill: COLORS.summaryHeader };
  setWidths(sheet, {
    A: 12, B: 10, C: 10, D: 12, E: 12, F: 3, G: 3,
    H: 12, I: 9, J: 12, K: 12, L: 10, M: 10, N: 10, O: 10, P: 10,
    Q: 10, R: 8, S: 10, T: 10, U: 10,
  });
  sheet.getRange("A3:U3").format.rowHeight = 34;
  sheet.freezePanes.freezeRows(3);
  return { sheet, totalRow, startRow, lastDataRow };
}

function buildChildSummary() {
  const sheet = workbook.worksheets.add("子事件数据汇总");
  sheet.showGridLines = false;
  sheet.mergeCells("A2:A3");
  sheet.mergeCells("B2:B3");
  sheet.mergeCells("C2:C3");
  sheet.mergeCells("D2:D3");
  sheet.mergeCells("E2:E3");
  sheet.mergeCells("F2:F3");
  sheet.mergeCells("G2:I2");
  sheet.getRange("A2:F2").values = [["序号", "标题", (data.channel_labels?.domestic_mainstream || "境内主流媒体"), "新媒体", "境外媒体", "总量"]];
  sheet.getRange("G2").values = [["网民情感"]];
  sheet.getRange("G3:I3").values = [["正面", "中立", "负面"]];
  sheet.getRange("A2:I3").format = { ...headerFormat, font: { name: "微软雅黑", size: 11, bold: true } };

  for (let index = 0; index < data.children.length; index += 1) {
    const child = data.children[index];
    const row = 4 + index;
    sheet.getRange(`A${row}:B${row}`).values = [[child.index, child.title]];
    sheet.getRange(`C${row}:F${row}`).values = [[
      child.totals.domestic_mainstream,
      child.totals.new_media,
      child.totals.overseas_media,
      child.totals.total,
    ]];
    sheet.getRange(`G${row}:I${row}`).values = [["", "", ""]];
  }
  const lastRow = 3 + data.children.length;
  sheet.getRange(`A4:I${lastRow}`).format = { ...bodyFormat, font: { name: "微软雅黑", size: 11 } };
  sheet.getRange(`B4:B${lastRow}`).format = { ...bodyFormat, font: { name: "微软雅黑", size: 11 }, horizontalAlignment: "left", wrapText: true };
  for (let row = 4; row <= lastRow; row += 1) sheet.getRange(`A${row}:I${row}`).format.rowHeight = 30;

  sheet.getRange("B19:C19").values = [["标题", "总量（万条）"]];
  sheet.getRange("B19:C19").format = headerFormat;
  const sorted = [...data.children].sort((a, b) => a.totals.total - b.totals.total);
  for (let index = 0; index < sorted.length; index += 1) {
    const child = sorted[index];
    const targetRow = 20 + index;
    sheet.getRange(`B${targetRow}:C${targetRow}`).values = [[
      child.title,
      child.totals.total / 10000,
    ]];
  }
  const helperLastRow = 19 + sorted.length;
  sheet.getRange(`B20:C${helperLastRow}`).format = bodyFormat;
  sheet.getRange(`C20:C${helperLastRow}`).format.numberFormat = "0.0";
  const chart = sheet.charts.add("bar", { chartType: "bar", hasLegend: false });
  const series = chart.series.add("总量（万条）");
  series.categoryFormula = `'子事件数据汇总'!$B$20:$B$${helperLastRow}`;
  series.formula = `'子事件数据汇总'!$C$20:$C$${helperLastRow}`;
  series.fill = "#5B9BD5";
  chart.hasLegend = false;
  chart.xAxis = { numberFormatCode: "0.0", textStyle: { fontSize: 9 } };
  chart.yAxis = { textStyle: { fontSize: 9 } };
  chart.setPosition("D17", "K35");

  setWidths(sheet, { A: 8, B: 56, C: 13, D: 13, E: 13, F: 13, G: 10, H: 10, I: 10, J: 3, K: 3, L: 3, M: 3, N: 3 });
  sheet.freezePanes.freezeRows(3);
  return sheet;
}

function buildOverseasSheet() {
  const sheet = workbook.worksheets.add("外媒报道列表");
  sheet.showGridLines = false;
  const topicCount = data.children.length;
  const lastTopicColumn = columnLetter(7 + topicCount);
  const reviewStartIndex = 8 + topicCount;
  const lastColumn = columnLetter(reviewStartIndex + 5);
  sheet.mergeCells(`H1:${lastTopicColumn}1`);
  sheet.getRange("H1").values = [["涉及子事件（根据标题、摘要和正文语义判断）"]];
  sheet.getRange(`H1:${lastTopicColumn}1`).format = { ...titleFormat, fill: "#FFFFFF", font: { name: "宋体", size: 14, bold: true, color: "#C00000" } };
  const topicLabels = ["一", "二", "三", "四", "五", "六", "七", "八"].slice(0, topicCount);
  const reviewHeaders = ["报道类型", "审核理由", "分类置信度", "简体中文来源", "简体中文标题", "简体中文摘要"];
  sheet.getRange(`B2:${lastColumn}2`).values = [["序号", "来源", "报道日期", "超链接标题", "标题", "发布地址", ...topicLabels, ...reviewHeaders]];
  sheet.getRange(`B2:${lastColumn}2`).format = { ...headerFormat, font: { name: "微软雅黑", size: 11, bold: true } };
  const selected = data.overseas.selected;
  for (let index = 0; index < selected.length; index += 1) {
    const item = selected[index];
    const row = 3 + index;
    const hitSet = new Set(item.topic_hits || []);
    sheet.getRange(`B${row}:D${row}`).values = [[index + 1, item.source || "", dateValue(item.published_at)]];
    sheet.getRange(`E${row}:G${row}`).values = [[item.title || "", item.title || "", item.url || ""]];
    sheet.getRange(`H${row}:${lastTopicColumn}${row}`).values = [Array.from({ length: topicCount }, (_, index) => index + 1).map((topic) => (hitSet.has(topic) ? topic : ""))];
    const reviewStartColumn = columnLetter(reviewStartIndex);
    sheet.getRange(`${reviewStartColumn}${row}:${lastColumn}${row}`).values = [[
      item.ai_report_category || "",
      item.classification_reason || item.review_reason || "",
      item.classification_confidence ?? "",
      item.source_cn_simplified || item.source || "",
      item.title_cn_simplified || item.title || "",
      item.summary_cn_simplified || "",
    ]];
  }
  const lastRow = Math.max(3, 2 + selected.length);
  sheet.getRange(`B3:${lastColumn}${lastRow}`).format = { ...bodyFormat, font: { name: "微软雅黑", size: 10 } };
  sheet.getRange(`D3:D${lastRow}`).format.numberFormat = "yyyy/m/d";
  sheet.getRange(`E3:E${lastRow}`).format = { ...bodyFormat, font: { name: "微软雅黑", size: 10, color: COLORS.link, underline: true }, horizontalAlignment: "left" };
  sheet.getRange(`F3:G${lastRow}`).format = { ...bodyFormat, font: { name: "微软雅黑", size: 10 }, horizontalAlignment: "left", wrapText: true };
  const widths = { A: 2, B: 8, C: 24, D: 14, E: 52, F: 64, G: 56 };
  for (let index = 8; index <= 7 + topicCount; index += 1) widths[columnLetter(index)] = 6;
  Object.assign(widths, {
    [columnLetter(reviewStartIndex)]: 16,
    [columnLetter(reviewStartIndex + 1)]: 54,
    [columnLetter(reviewStartIndex + 2)]: 13,
    [columnLetter(reviewStartIndex + 3)]: 22,
    [columnLetter(reviewStartIndex + 4)]: 56,
    [columnLetter(reviewStartIndex + 5)]: 72,
  });
  setWidths(sheet, widths);
  sheet.freezePanes.freezeRows(2);
  return sheet;
}

async function buildWordcloudSheet() {
  const sheet = workbook.worksheets.add("词云");
  sheet.showGridLines = false;
  const selected = data.hotwords?.selected || [];
  sheet.getRange("A1").values = [["热词"]];
  sheet.getRange("A1").format = headerFormat;
  if (selected.length) {
    sheet.getRange(`A2:A${selected.length + 1}`).values = selected.map((item) => [item.term]);
    sheet.getRange(`A2:A${selected.length + 1}`).format = {
      font: { name: "仿宋", size: 10, color: "#000000" },
      horizontalAlignment: "left",
      verticalAlignment: "center",
    };
  }
  setWidths(sheet, { A: 18, B: 30, C: 30, D: 30, E: 30, F: 3 });
  sheet.getRange("A1:F44").format.rowHeight = 22;
  const imagePath = data.hotwords?.image_path;
  if (imagePath) {
    const imageBytes = await fs.readFile(imagePath);
    const dataUrl = `data:image/png;base64,${imageBytes.toString("base64")}`;
    sheet.images.add({
      dataUrl,
      anchor: {
        from: { row: 1, col: 1, rowOffsetPx: 0, colOffsetPx: 0 },
        extent: { widthPx: 840, heightPx: 525 },
      },
    });
    // Keep the image rectangle inside the worksheet's used range so renderers
    // that crop to populated cells do not omit the embedded PNG.
    sheet.getRange("E25").values = [["\u200B"]];
    sheet.getRange("E25").format = { font: { size: 1, color: "#FFFFFF" } };
  } else {
    sheet.getRange("B2:E20").merge();
    sheet.getRange("B2").values = [["词云PNG未生成"]];
    sheet.getRange("B2:E20").format = {
      fill: "#FFFFFF",
      font: { name: "仿宋", size: 12, color: "#7F7F7F" },
      horizontalAlignment: "center",
      verticalAlignment: "center",
      borders: borderAll,
    };
  }
  sheet.freezePanes.freezeRows(1);
  return sheet;
}

function buildPublicTopSheet() {
  const sheet = workbook.worksheets.add("公众TOP");
  sheet.showGridLines = false;
  sheet.mergeCells("B1:F1");
  sheet.mergeCells("G1:I1");
  sheet.getRange("B1").values = [["微信公号文章阅读量TOP"]];
  sheet.getRange("G1").values = [["原始字段与超链接"]];
  sheet.getRange("B1:I1").format = titleFormat;
  sheet.getRange("B2:I2").values = [["序号", "账号", "标题", "阅读量", "在看量", "标题原文", "原链接", "发布日期"]];
  sheet.getRange("B2:I2").format = headerFormat;
  const selected = data.public_top.selected;
  for (let index = 0; index < selected.length; index += 1) {
    const item = selected[index];
    const row = 3 + index;
    const readDisplay = item.read_count === data.public_read_cap ? `${data.public_read_cap}+` : item.read_count;
    sheet.getRange(`B${row}:C${row}`).values = [[index + 1, item.account || item.source || ""]];
    sheet.getRange(`D${row}`).values = [[item.title || ""]];
    sheet.getRange(`E${row}:I${row}`).values = [[
      readDisplay,
      item.recommend_count ?? "",
      item.title || "",
      item.url || "",
      dateValue(item.published_at),
    ]];
  }
  const lastRow = Math.max(3, 2 + selected.length);
  sheet.getRange(`B3:I${lastRow}`).format = bodyFormat;
  sheet.getRange(`D3:D${lastRow}`).format = { ...bodyFormat, font: { name: "仿宋", size: 11, color: COLORS.link, underline: true }, horizontalAlignment: "left" };
  sheet.getRange(`G3:H${lastRow}`).format = { ...bodyFormat, horizontalAlignment: "left", wrapText: true };
  sheet.getRange(`I3:I${lastRow}`).format.numberFormat = "yyyy/m/d";
  setWidths(sheet, { A: 2, B: 7, C: 24, D: 52, E: 14, F: 10, G: 52, H: 56, I: 14 });
  sheet.freezePanes.freezeRows(2);
  return sheet;
}

buildKeywordsSheet();
buildTotalSheet();
for (const child of data.children) buildChildSheet(child);
buildChildSummary();
buildOverseasSheet();
await buildWordcloudSheet();
buildPublicTopSheet();

await fs.mkdir(path.dirname(outputPath), { recursive: true });
await fs.mkdir(previewsDir, { recursive: true });

const keyChecks = [];
for (const [sheetId, range] of [["总事件", "A1:AB12"], ["子事件数据汇总", "A1:I10"], ["词云", "A1:E20"], ["公众TOP", "B1:I12"]]) {
  const inspection = await workbook.inspect({
    kind: "table",
    sheetId,
    range,
    include: "values,formulas",
    tableMaxRows: 20,
    tableMaxCols: 30,
    maxChars: 12000,
  });
  keyChecks.push({ sheetId, range, ndjson: inspection.ndjson });
}
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
  maxChars: 20000,
});
const drawings = await workbook.inspect({ kind: "drawing", maxChars: 10000, options: { maxResults: 100 } });

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);

const actualSheetNames = workbook.worksheets.items.map((sheet) => sheet.name);
const errorLines = String(errors.ndjson || "")
  .split(/\r?\n/)
  .filter((line) => line.trim() && !line.includes('"kind":"notice"'));
const verification = {
  sheet_names: actualSheetNames,
  expected_sheet_order: SHEET_ORDER,
  sheet_order_ok: JSON.stringify(actualSheetNames) === JSON.stringify(SHEET_ORDER),
  rendered_sheets: [],
  render_errors: [],
  formula_error_count: errorLines.length,
  formula_error_scan: errors.ndjson,
  chart_count: 2,
  drawing_inspect: drawings.ndjson,
  key_range_checks: keyChecks.length,
  key_checks: keyChecks,
};
await fs.writeFile(verificationPath, JSON.stringify(verification, null, 2), "utf8");
console.log(JSON.stringify({ outputPath, verificationPath }));
process.exit(0);
