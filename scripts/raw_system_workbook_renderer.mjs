import fs from "node:fs/promises";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);
const artifactTool = await import(pathToFileURL(require.resolve("@oai/artifact-tool")).href);
const { SpreadsheetFile } = artifactTool;

const [inputPath, sheetArg, previewArg] = process.argv.slice(2);
if (!inputPath || !sheetArg || !previewArg) {
  throw new Error("Usage: node raw_system_workbook_renderer.mjs <input.xlsx> <sheet-name> <preview.png>");
}
const requests = sheetArg === "--batch" ? JSON.parse(previewArg) : [{ sheetName: sheetArg, previewPath: previewArg }];
if (!Array.isArray(requests) || !requests.length || requests.some(row =>
  typeof row.sheetName !== "string" || !row.sheetName || typeof row.previewPath !== "string" || !row.previewPath)) {
  throw new Error("Render requests must contain explicit sheet names and preview paths");
}

const bytes = await fs.readFile(inputPath);
const workbook = await SpreadsheetFile.importXlsx(bytes);
const drawingRanges = {
  "总事件": "A1:N19",
  "子事件数据汇总": "A1:K38",
  "词云": "A1:N42",
};
let failed = false;
for (const { sheetName, previewPath } of requests) {
  try {
    const renderOptions = { sheetName, scale: 1, format: "png" };
    if (drawingRanges[sheetName]) {
      renderOptions.range = drawingRanges[sheetName];
    } else {
      renderOptions.autoCrop = "all";
    }
    const preview = await workbook.render(renderOptions);
    await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
    console.log(JSON.stringify({ inputPath, sheetName, previewPath }));
  } catch (error) {
    failed = true;
    console.error(JSON.stringify({ inputPath, sheetName, previewPath, error: String(error) }));
  }
}
process.exit(failed ? 1 : 0);
