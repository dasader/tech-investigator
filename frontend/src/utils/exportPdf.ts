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

// ─── Section divider ──────────────────────────────────────────────────────────
function drawSectionHeader(
  doc: jsPDF, font: string,
  x: number, y: number, w: number,
  name: string, unit: string | null | undefined, idx: number,
): number {
  const h = 11;
  doc.setFillColor(18, 32, 68);
  doc.roundedRect(x, y, w, h, 2, 2, "F");

  // amber left bar
  doc.setFillColor(215, 140, 20);
  doc.roundedRect(x, y, 3.5, h, 1, 1, "F");

  // index badge
  const badge = String(idx + 1).padStart(2, "0");
  doc.setFontSize(6.5);
  doc.setTextColor(215, 140, 20);
  doc.setFont(font, "normal");
  doc.text(badge, x + 7, y + 7.2);

  doc.setFontSize(10.5);
  doc.setTextColor(225, 235, 252);
  doc.text(name, x + 16, y + 7.2);

  if (unit) {
    doc.setFontSize(7.5);
    doc.setTextColor(140, 175, 230);
    doc.text(`단위: ${unit}`, x + w - 3, y + 7.2, { align: "right" });
  }
  return h + 4;
}

// ─── Line chart (time series) ─────────────────────────────────────────────────
function drawLineChart(
  doc: jsPDF, font: string,
  x: number, y: number, w: number, h: number,
  rawData: { year: number; value: number }[],
  title: string, unit?: string | null,
) {
  // 연도별 최고값만 취함 (지그재그 방지)
  const yearMap = new Map<number, number>();
  for (const d of rawData) {
    const cur = yearMap.get(d.year);
    if (cur == null || d.value > cur) yearMap.set(d.year, d.value);
  }
  const data = [...yearMap.entries()]
    .map(([year, value]) => ({ year, value }))
    .sort((a, b) => a.year - b.year);
  if (data.length < 2) return;

  doc.setFillColor(248, 250, 253);
  doc.setDrawColor(210, 220, 238);
  doc.setLineWidth(0.2);
  doc.roundedRect(x, y, w, h, 2.5, 2.5, "FD");

  doc.setFont(font, "normal");
  doc.setFontSize(7.5);
  doc.setTextColor(18, 34, 72);
  doc.text(`${title} — 연도별 추이`, x + 4, y + 6);
  if (unit) {
    doc.setFontSize(6.5);
    doc.setTextColor(130, 150, 180);
    doc.text(unit, x + w - 4, y + 6, { align: "right" });
  }

  const LABEL_W = 14, PAD_R = 4, PAD_T = 11, PAD_B = 8;
  const cx  = x + LABEL_W;
  const cy2 = y + PAD_T;
  const cw  = w - LABEL_W - PAD_R;
  const ch  = h - PAD_T - PAD_B;

  const years  = data.map(d => d.year);
  const values = data.map(d => d.value);
  const minY = Math.min(...values);
  const maxY = Math.max(...values);
  const yRange = maxY - minY || Math.abs(maxY) || 1;
  const minX = Math.min(...years);
  const maxX = Math.max(...years);
  const xRange = maxX - minX || 1;

  const sx = (yr: number) => cx + ((yr - minX) / xRange) * cw;
  const sy = (v: number)  => cy2 + ch - ((v - minY) / yRange) * ch;

  for (let g = 0; g <= 3; g++) {
    const gy = cy2 + (g / 3) * ch;
    doc.setDrawColor(218, 226, 240);
    doc.setLineWidth(0.15);
    doc.line(cx, gy, cx + cw, gy);
    const gv = maxY - (g / 3) * yRange;
    doc.setFontSize(5.5);
    doc.setTextColor(165, 178, 200);
    const gLabel = Math.abs(gv) >= 1000 ? (gv / 1000).toFixed(1) + "k" : gv.toFixed(Math.abs(gv) < 1 ? 2 : 0);
    doc.text(gLabel, cx - 1.5, gy + 1.5, { align: "right" });
  }

  doc.setFontSize(5.5);
  doc.setTextColor(165, 178, 200);
  const step = Math.max(1, Math.floor(data.length / 5));
  data.forEach((d, i) => {
    if (i % step === 0 || i === data.length - 1)
      doc.text(String(d.year), sx(d.year), cy2 + ch + 5, { align: "center" });
  });

  doc.setDrawColor(215, 140, 20);
  doc.setLineWidth(0.7);
  for (let i = 1; i < data.length; i++)
    doc.line(sx(data[i - 1].year), sy(data[i - 1].value), sx(data[i].year), sy(data[i].value));

  data.forEach(d => {
    doc.setFillColor(215, 140, 20);
    doc.circle(sx(d.year), sy(d.value), 0.9, "F");
  });

  const maxIdx = values.indexOf(maxY);
  if (maxIdx >= 0) {
    doc.setFillColor(12, 26, 58);
    doc.setDrawColor(215, 140, 20);
    doc.setLineWidth(0.5);
    doc.circle(sx(data[maxIdx].year), sy(data[maxIdx].value), 1.8, "FD");
  }
}

// ─── Bar chart (country compare) ──────────────────────────────────────────────
function drawBarChart(
  doc: jsPDF, font: string,
  x: number, y: number, w: number, h: number,
  rawData: { country: string; value: number }[],
  title: string, unit?: string | null,
) {
  if (rawData.length < 2) return;

  doc.setFillColor(248, 250, 253);
  doc.setDrawColor(210, 220, 238);
  doc.setLineWidth(0.2);
  doc.roundedRect(x, y, w, h, 2.5, 2.5, "FD");

  doc.setFont(font, "normal");
  doc.setFontSize(7.5);
  doc.setTextColor(18, 34, 72);
  doc.text(`${title} — 국가별 비교`, x + 4, y + 6);
  if (unit) {
    doc.setFontSize(6.5);
    doc.setTextColor(130, 150, 180);
    doc.text(unit, x + w - 4, y + 6, { align: "right" });
  }

  const LABEL_W = 24, PAD_R = 6, PAD_T = 11, PAD_B = 5;
  const bx  = x + LABEL_W;
  const by0 = y + PAD_T;
  const bw  = w - LABEL_W - PAD_R;
  const avH = h - PAD_T - PAD_B;
  const barH = Math.min(6.5, avH / rawData.length - 2.5);
  const gap  = Math.max(1.5, (avH - rawData.length * barH) / (rawData.length + 1));
  const maxV = Math.max(...rawData.map(d => d.value));

  const COLORS: [number, number, number][] = [
    [18, 36, 80], [28, 65, 120], [36, 94, 160],
    [46, 120, 190], [58, 145, 215], [88, 170, 232], [130, 198, 245],
  ];

  rawData.forEach((d, i) => {
    const rowY   = by0 + gap * (i + 1) + barH * i;
    const bwFill = Math.max(2, (d.value / maxV) * bw);
    const col    = COLORS[i % COLORS.length];

    doc.setFontSize(6);
    doc.setTextColor(50, 70, 105);
    const label = d.country.length > 10 ? d.country.slice(0, 10) + "." : d.country;
    doc.text(label, bx - 2, rowY + barH * 0.78, { align: "right" });

    doc.setFillColor(...col);
    doc.roundedRect(bx, rowY, bwFill, barH, 1, 1, "F");

    doc.setFontSize(5.5);
    doc.setTextColor(65, 88, 130);
    doc.text(d.value.toLocaleString(), bx + bwFill + 2, rowY + barH * 0.78);
  });
}

// ─── Data PDF ─────────────────────────────────────────────────────────────────
export async function exportDataAsPdf(
  data: ResultsData,
  onProgress: (msg: string | null) => void,
): Promise<void> {
  onProgress("폰트 로딩 중...");

  const doc = new jsPDF({ orientation: "portrait", unit: "mm", format: "a4" });
  const pageW = doc.internal.pageSize.getWidth();
  const pageH = doc.internal.pageSize.getHeight();
  const ML = 15, MR = 15;
  const CW = pageW - ML - MR; // 180mm

  const font = await loadKoreanFont(doc);

  const fmt = (n: number | null, unit: string | null) =>
    n != null ? `${n.toLocaleString()}${unit ? " " + unit : ""}` : "—";

  const analyzedAt   = data.analyzed_at ? new Date(data.analyzed_at).toLocaleDateString("ko-KR") : "";
  const engineLabel  = getEngineLabel(data.search_source);
  const totalPapers  = data.indicators.reduce((s, ind) => s + ind.metric_values.length, 0);
  const metaLine     = [
    `지표 ${data.indicators.length}개`,
    `데이터 ${totalPapers}건`,
    analyzedAt ? `기준일 ${analyzedAt}` : "",
    engineLabel,
  ].filter(Boolean).join(" · ");

  let y = drawCoverHeader(doc, font, pageW, ML, CW,
    "분석 데이터 보고서", data.category, data.description, metaLine);

  // 컬럼 너비: 4등분 (180 / 4 = 45mm)
  const COL = CW / 4; // 45mm

  for (let idx = 0; idx < data.indicators.length; idx++) {
    const item = data.indicators[idx];
    onProgress(`(${idx + 1}/${data.indicators.length}) ${item.indicator.name} 처리 중...`);

    if (y > pageH - 45) { doc.addPage(); y = 20; }

    y += drawSectionHeader(doc, font, ML, y, CW, item.indicator.name, item.indicator.unit, idx);

    if (item.metric_values.length === 0) {
      if (y > pageH - 20) { doc.addPage(); y = 20; }
      doc.setFont(font, "normal");
      doc.setFontSize(9);
      doc.setTextColor(160, 172, 192);
      doc.text("검색된 데이터가 없습니다.", ML + 4, y + 6);
      y += 14;
    } else {
      // 수치 테이블 — 4열 동일 너비
      autoTable(doc, {
        startY: y,
        margin: { left: ML, right: MR },
        head: [["수치", "연도", "국가", "신뢰도"]],
        body: item.metric_values.map(mv => [
          fmt(mv.value, mv.unit),
          mv.year?.toString() ?? "—",
          mv.country ?? "—",
          `${(mv.confidence_score * 100).toFixed(0)}%`,
        ]),
        ...tableStyles(font),
        columnStyles: {
          0: { cellWidth: COL },
          1: { cellWidth: COL, halign: "center" },
          2: { cellWidth: COL },
          3: { cellWidth: COL, halign: "center" },
        },
        tableWidth: CW,
      });
      y = (doc as DocWithTable).lastAutoTable.finalY + 6;

      // 출처 논문
      if (item.metric_values.some(mv => mv.paper_title)) {
        if (y > pageH - 30) { doc.addPage(); y = 20; }

        doc.setFont(font, "normal");
        doc.setFontSize(7.5);
        doc.setTextColor(100, 120, 158);
        doc.text("출처 논문", ML, y);
        doc.setDrawColor(195, 210, 235);
        doc.setLineWidth(0.25);
        doc.line(ML + 22, y - 1, ML + CW, y - 1);
        y += 5;

        item.metric_values.forEach((mv, j) => {
          if (!mv.paper_title) return;
          if (y > pageH - 22) { doc.addPage(); y = 20; }

          // 인덱스
          doc.setFontSize(7.5);
          doc.setTextColor(60, 90, 150);
          doc.text(`[${j + 1}]`, ML, y);

          // 연도
          if (mv.year) {
            doc.setFontSize(7);
            doc.setTextColor(160, 115, 30);
            doc.text(`${mv.year}`, ML + 9, y);
          }

          // 제목 (ML+20 부터)
          const TITLE_X = ML + 20;
          const TITLE_W = CW - 20;
          doc.setFontSize(8.5);
          doc.setTextColor(16, 36, 72);
          const titleLines = doc.splitTextToSize(mv.paper_title, TITLE_W) as string[];
          doc.text(titleLines, TITLE_X, y);
          y += titleLines.length * 4.5;

          // DOI
          if (mv.doi) {
            if (y > pageH - 15) { doc.addPage(); y = 20; }
            const doiText = `DOI: ${mv.doi}`;
            doc.setFontSize(7.5);
            doc.setTextColor(70, 105, 175);
            doc.text(doiText, TITLE_X, y);
            doc.link(TITLE_X, y - 3.5, doc.getTextWidth(doiText), 4.5, { url: `https://doi.org/${mv.doi}` });
            y += 4.5;
          }

          // 인용문 — 세로선 + 들여쓰기 텍스트
          if (mv.quote) {
            if (y > pageH - 20) { doc.addPage(); y = 20; }
            const Q_X = TITLE_X + 2;   // 인용문 텍스트 x (세로선 오른쪽 4mm)
            const Q_W = CW - 26;        // 사용 가능 너비
            const LINE_H = 4.5;
            const qLines = doc.splitTextToSize(`"${mv.quote}"`, Q_W) as string[];
            const blockH = qLines.length * LINE_H;

            // 세로 accent line — 텍스트 블록과 정확히 정렬
            doc.setDrawColor(175, 200, 235);
            doc.setLineWidth(0.8);
            doc.line(Q_X - 3, y - 2, Q_X - 3, y + blockH - LINE_H + 2.5);

            doc.setFontSize(7.5);
            doc.setTextColor(105, 128, 165);
            doc.text(qLines, Q_X, y);
            y += blockH + 3;
          }
          y += 3;
        });
        y += 2;
      }

      // 차트
      const tsData = item.metric_values
        .filter(v => v.year != null && v.value != null)
        .map(v => ({ year: v.year as number, value: v.value as number }));

      const ccMap = new Map<string, number>();
      for (const v of item.metric_values) {
        if (v.country && v.value != null) {
          const cur = ccMap.get(v.country);
          if (cur == null || v.value > cur) ccMap.set(v.country, v.value);
        }
      }
      const ccData = [...ccMap.entries()]
        .map(([country, value]) => ({ country, value }))
        .sort((a, b) => b.value - a.value)
        .slice(0, 7);

      const hasTs = tsData.length >= 2;
      const hasCc = ccData.length >= 2;
      const chartH = 52;

      if (hasTs || hasCc) {
        if (y > pageH - chartH - 5) { doc.addPage(); y = 20; }
        if (hasTs && hasCc) {
          const half = (CW - 3) / 2;
          drawLineChart(doc, font, ML,            y, half, chartH, tsData, item.indicator.name, item.indicator.unit);
          drawBarChart (doc, font, ML + half + 3, y, half, chartH, ccData, item.indicator.name, item.indicator.unit);
        } else if (hasTs) {
          drawLineChart(doc, font, ML, y, CW, chartH, tsData, item.indicator.name, item.indicator.unit);
        } else {
          drawBarChart (doc, font, ML, y, CW, chartH, ccData, item.indicator.name, item.indicator.unit);
        }
        y += chartH + 6;
      }
    }

    if (idx < data.indicators.length - 1) {
      if (y > pageH - 25) {
        doc.addPage(); y = 20;
      } else {
        doc.setDrawColor(205, 215, 235);
        doc.setLineWidth(0.25);
        doc.line(ML, y, pageW - MR, y);
        y += 10;
      }
    }
  }

  addPageFooter(doc, font,
    `TechSpec 분석 데이터${analyzedAt ? " · " + analyzedAt : ""}`,
    doc.getNumberOfPages());

  doc.save(`techspec-data-${data.job_id}-${new Date().toISOString().slice(0, 10)}.pdf`);
  onProgress(null);
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
