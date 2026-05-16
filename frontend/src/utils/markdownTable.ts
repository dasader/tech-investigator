export interface ParsedTable {
  headers: string[];
  rows: string[][];
}

export function extractGlobalBestTable(markdown: string | null): ParsedTable | null {
  if (!markdown) return null;
  const lines = markdown.split("\n");

  let startIdx = -1;
  for (let i = 0; i < lines.length; i++) {
    if (/^#{1,4}.*글로벌\s*최고\s*달성치/.test(lines[i])) {
      startIdx = i + 1;
      break;
    }
  }
  if (startIdx === -1) return null;

  let tableStart = -1;
  for (let i = startIdx; i < lines.length; i++) {
    if (lines[i].trimStart().startsWith("|")) {
      tableStart = i;
      break;
    }
    if (/^#{1,4}\s/.test(lines[i])) return null;
  }
  if (tableStart === -1) return null;

  const tableLines: string[] = [];
  for (let i = tableStart; i < lines.length; i++) {
    if (!lines[i].trimStart().startsWith("|")) break;
    tableLines.push(lines[i]);
  }

  const rows = tableLines
    .filter(l => !/^\s*\|[-| :]+\|\s*$/.test(l))
    .map(l => l.replace(/^\s*\||\|\s*$/g, "").split("|").map(c => c.trim()));

  if (rows.length < 2) return null;
  return { headers: rows[0], rows: rows.slice(1) };
}
