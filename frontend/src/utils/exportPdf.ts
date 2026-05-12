import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";
import type { ResultsData } from "../types/results";
import { getEngineLabel } from "./format";

type DocWithTable = jsPDF & { lastAutoTable: { finalY: number } };

function tableStyles(font: string) {
  return {
    headStyles: {
      fillColor: [14, 28, 64] as [number, number, number],
      textColor: [190, 210, 250] as [number, number, number],
      fontSize: 8.5, font, fontStyle: "normal" as const, halign: "left" as const,
      cellPadding: { top: 4, bottom: 4, left: 5, right: 5 },
    },
    bodyStyles: {
      textColor: [22, 38, 62] as [number, number, number],
      fontSize: 8.5, font, fontStyle: "normal" as const,
      cellPadding: { top: 3.5, bottom: 3.5, left: 5, right: 5 },
    },
    alternateRowStyles: { fillColor: [244, 246, 252] as [number, number, number] },
    theme: "grid" as const,
    tableLineColor: [205, 215, 235] as [number, number, number],
    tableLineWidth: 0.2,
  };
}

let fontCache: string | null = null;
let fontName = "helvetica";

async function loadKoreanFont(doc: jsPDF): Promise<string> {
  if (fontCache !== null) {
    if (fontName !== "helvetica") {
      doc.addFileToVFS("Pretendard-Regular.ttf", fontCache);
      doc.addFont("Pretendard-Regular.ttf", "Pretendard", "normal");
    }
    return fontName;
  }
  // Pretendard 우선, 실패 시 NanumGothic, 최종 fallback helvetica
  for (const [file, name] of [
    ["/fonts/Pretendard-Regular.ttf", "Pretendard"],
    ["/fonts/NanumGothic-Regular.ttf", "NanumGothic"],
  ] as const) {
    try {
      const res = await fetch(file);
      if (!res.ok) continue;
      const buf = await res.arrayBuffer();
      const bytes = new Uint8Array(buf);
      let binary = "";
      for (let i = 0; i < bytes.length; i += 1024)
        binary += String.fromCharCode(...bytes.subarray(i, Math.min(i + 1024, bytes.length)));
      fontCache = btoa(binary);
      fontName = name;
      doc.addFileToVFS(`${name}-Regular.ttf`, fontCache);
      doc.addFont(`${name}-Regular.ttf`, name, "normal");
      return name;
    } catch {
      continue;
    }
  }
  fontCache = "";
  return "helvetica";
}

// ─── Page footer ─────────────────────────────────────────────────────────────
function addPageFooter(doc: jsPDF, font: string, label: string, pageCount: number) {
  const pageW = doc.internal.pageSize.getWidth();
  const pageH = doc.internal.pageSize.getHeight();
  for (let p = 1; p <= pageCount; p++) {
    doc.setPage(p);
    doc.setDrawColor(200, 212, 232);
    doc.setLineWidth(0.3);
    doc.line(15, pageH - 14, pageW - 15, pageH - 14);
    doc.setFont(font, "normal");
    doc.setFontSize(7);
    doc.setTextColor(140, 158, 185);
    doc.text(label, 15, pageH - 8.5);
    doc.text(`${p} / ${pageCount}`, pageW - 15, pageH - 8.5, { align: "right" });
  }
}

// ─── Cover header ─────────────────────────────────────────────────────────────
function drawCoverHeader(
  doc: jsPDF, font: string,
  pageW: number, ML: number, CW: number,
  title: string,
  category: string | undefined,
  description: string | undefined,
  metaLine: string,
): number {
  doc.setFontSize(8.5);
  const descLines = description
    ? doc.splitTextToSize(`검색기술명: ${description}`, CW - 10).slice(0, 2) as string[]
    : [];
  const headerH = 22 + (category ? 8 : 0) + (descLines.length > 0 ? descLines.length * 5 + 2 : 0) + 10;

  // 배경
  doc.setFillColor(10, 18, 38);
  doc.rect(0, 0, pageW, headerH, "F");

  // 좌측 amber accent strip
  doc.setFillColor(215, 140, 20);
  doc.rect(0, 0, 4, headerH, "F");

  let cy = 16;

  doc.setFont(font, "normal");
  doc.setFontSize(18);
  doc.setTextColor(235, 240, 250);
  doc.text(title, ML, cy);
  cy += 10;

  if (category) {
    doc.setFontSize(9);
    doc.setTextColor(160, 195, 245);
    doc.text(`전략기술분야: ${category}`, ML, cy);
    cy += 7;
  }

  if (descLines.length > 0) {
    doc.setFontSize(8.5);
    doc.setTextColor(120, 158, 210);
    doc.text(descLines, ML, cy);
    cy += descLines.length * 5 + 2;
  }

  doc.setFontSize(7.5);
  doc.setTextColor(95, 130, 180);
  doc.text(metaLine, ML, cy + 2);

  // 하단 구분선
  doc.setFillColor(215, 140, 20);
  doc.rect(0, headerH - 1.5, pageW, 1.5, "F");

  return headerH + 10;
}


// ─── Data PDF (현재 화면 직접 인쇄) ──────────────────────────────────────────
export function printCurrentView(): void {
  document.body.classList.add("printing-data");
  const cleanup = () => {
    document.body.classList.remove("printing-data");
    window.removeEventListener("afterprint", cleanup);
  };
  window.addEventListener("afterprint", cleanup);
  window.print();
}

// ─── Report PDF ───────────────────────────────────────────────────────────────
export async function exportReportAsPdf(
  data: ResultsData,
  onProgress: (msg: string | null) => void,
): Promise<void> {
  if (!data.report_markdown) {
    alert("보고서 데이터가 없습니다.");
    return;
  }
  onProgress("보고서 PDF 생성 중...");

  const doc = new jsPDF({ orientation: "portrait", unit: "mm", format: "a4" });
  const pageW = doc.internal.pageSize.getWidth();
  const pageH = doc.internal.pageSize.getHeight();
  const ML = 15, MR = 15;
  const CW = pageW - ML - MR;

  const font = await loadKoreanFont(doc);

  const analyzedAt  = data.analyzed_at ? new Date(data.analyzed_at).toLocaleDateString("ko-KR") : "";
  const engineLabel = getEngineLabel(data.search_source);
  const metaLine    = [
    analyzedAt ? `분석 기준일 ${analyzedAt}` : "",
    `분석 엔진 ${engineLabel}`,
  ].filter(Boolean).join(" · ");

  let y = drawCoverHeader(doc, font, pageW, ML, CW,
    "기술 동향 분석 보고서", data.category, data.description, metaLine);

  const lines = data.report_markdown.split("\n");
  let li = 0;

  while (li < lines.length) {
    const line = lines[li];

    if (y > pageH - 25) { doc.addPage(); y = 20; }

    if (line.startsWith("## ")) {
      if (y > pageH - 18) { doc.addPage(); y = 20; }
      const h = 11;
      doc.setFillColor(18, 32, 68);
      doc.roundedRect(ML, y, CW, h, 2, 2, "F");
      doc.setFillColor(215, 140, 20);
      doc.roundedRect(ML, y, 3.5, h, 1, 1, "F");
      doc.setFont(font, "normal");
      doc.setFontSize(10.5);
      doc.setTextColor(225, 235, 252);
      doc.text(line.slice(3).trim(), ML + 8, y + 7.2);
      y += h + 5;
      li++;

    } else if (line.startsWith("### ")) {
      if (y > pageH - 14) { doc.addPage(); y = 20; }
      doc.setFont(font, "normal");
      doc.setFontSize(9.5);
      doc.setTextColor(22, 42, 92);
      doc.text(line.slice(4).trim(), ML, y);
      doc.setDrawColor(175, 195, 228);
      doc.setLineWidth(0.3);
      doc.line(ML, y + 2.5, ML + CW, y + 2.5);
      y += 9;
      li++;

    } else if (line.trimStart().startsWith("|")) {
      const tableLines: string[] = [];
      while (li < lines.length && lines[li].trimStart().startsWith("|")) {
        tableLines.push(lines[li]);
        li++;
      }
      const rows = tableLines
        .filter(l => !l.match(/^\s*\|[-| :]+\|\s*$/))
        .map(l => l.replace(/^\s*\||\|\s*$/g, "").split("|").map(c => c.trim()));

      if (rows.length > 1) {
        if (y > pageH - 35) { doc.addPage(); y = 20; }
        autoTable(doc, {
          startY: y,
          margin: { left: ML, right: MR },
          head: [rows[0]],
          body: rows.slice(1),
          ...tableStyles(font),
          tableWidth: CW,
        });
        y = (doc as DocWithTable).lastAutoTable.finalY + 6;
      }

    } else if (line.trim() === "" || line.match(/^---+$/)) {
      y += 2;
      li++;

    } else if (line.trim()) {
      const text = line
        .replace(/\*\*(.*?)\*\*/g, "$1")
        .replace(/\*(.*?)\*/g, "$1")
        .replace(/^>\s*/, "")
        .trim();
      if (!text) { li++; continue; }

      doc.setFont(font, "normal");
      doc.setFontSize(9);
      doc.setTextColor(22, 38, 62);
      const wrapped = doc.splitTextToSize(text, CW) as string[];
      if (y + wrapped.length * 5.2 > pageH - 15) { doc.addPage(); y = 20; }
      doc.text(wrapped, ML, y);
      y += wrapped.length * 5.2 + 2;
      li++;

    } else {
      li++;
    }
  }

  addPageFooter(doc, font,
    `TechSpec 분석 보고서${analyzedAt ? " · " + analyzedAt : ""}`,
    doc.getNumberOfPages());

  doc.save(`techspec-report-${data.job_id}-${new Date().toISOString().slice(0, 10)}.pdf`);
  onProgress(null);
}
