import fs from "node:fs/promises";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);
const artifactTool = await import(pathToFileURL(require.resolve("@oai/artifact-tool")).href);
const { SpreadsheetFile } = artifactTool;

const [inputPath, sheetName, previewPath] = process.argv.slice(2);
if (!inputPath || !sheetName || !previewPath) {
  throw new Error("Usage: node raw_system_workbook_renderer.mjs <input.xlsx> <sheet-name> <preview.png>");
}

const bytes = await fs.readFile(inputPath);
const workbook = await SpreadsheetFile.importXlsx(bytes);
const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 1, format: "png" });
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
console.log(JSON.stringify({ inputPath, sheetName, previewPath }));
process.exit(0);
