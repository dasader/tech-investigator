import { useEffect, useState } from "react";
import MetricTable from "../components/MetricTable";
import TimeSeriesChart from "../components/TimeSeriesChart";
import CountryCompareChart from "../components/CountryCompareChart";
import { getResults } from "../api/client";
import { exportDataAsPdf, exportReportAsPdf } from "../utils/exportPdf";
import { getEngineLabel } from "../utils/format";
import type { ResultsData } from "../types/results";

interface Props { jobId: number; }

type Tab = "report" | "data";

function TabButton({ id, label, active, onClick }: { id: Tab; label: string; active: boolean; onClick: (id: Tab) => void }) {
  return (
    <button
      onClick={() => onClick(id)}
      style={{
        padding: "12px 24px",
        fontSize: "13px",
        fontWeight: 600,
        borderTop: "none",
        borderLeft: "none",
        borderRight: "none",
        borderBottomWidth: "2.5px",
        borderBottomStyle: "solid",
        borderBottomColor: active ? "var(--color-amber)" : "transparent",
        cursor: "pointer",
        transition: "all 0.2s",
        background: "none",
        color: active ? "var(--color-amber)" : "var(--color-text-3)",
        fontFamily: "var(--font-body)",
      }}
    >
      {label}
    </button>
  );
}

function SummaryBanner({ data }: { data: ResultsData }) {
  const totalPapers = data.indicators.reduce((acc, i) => acc + i.metric_values.length, 0);
  const analyzedAt  = data.analyzed_at
    ? new Date(data.analyzed_at).toLocaleDateString("ko-KR", { year: "numeric", month: "long", day: "numeric" })
    : null;

  return (
    <div
      className="rounded-2xl px-6 py-5 mb-8 grid grid-cols-2 md:grid-cols-4 gap-4 fade-up"
      style={{ background: "var(--color-navy-dark)", border: "1px solid rgba(255,255,255,0.06)" }}
    >
      {[
        { label: "분석 지표 수",  value: `${data.indicators.length}개` },
        { label: "추출 데이터 수", value: `${totalPapers}건` },
        { label: "데이터 기준일",  value: analyzedAt ?? "—" },
        { label: "분석 엔진",     value: getEngineLabel(data.search_source) },
      ].map(({ label, value }) => (
        <div key={label}>
          <p className="text-[11px] font-semibold uppercase tracking-widest mb-1" style={{ color: "rgba(150,180,220,0.6)" }}>
            {label}
          </p>
          <p className="text-sm font-semibold" style={{ color: "var(--color-text-inv)", fontFamily: "var(--font-body)" }}>
            {value}
          </p>
        </div>
      ))}
    </div>
  );
}

function SpinnerIcon({ className }: { className: string }) {
  return (
    <svg className={`animate-spin shrink-0 ${className}`} fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
    </svg>
  );
}

function PdfButton({ label, progress, onClick }: { label: string; progress: string | null; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      disabled={progress !== null}
      className="mb-1 inline-flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition-all disabled:opacity-60"
      style={{
        background: progress ? "var(--color-border)" : "var(--color-navy-dark)",
        color: "var(--color-text-inv)",
      }}
    >
      {progress ? (
        <>
          <SpinnerIcon className="w-3.5 h-3.5" />
          <span className="truncate max-w-[180px]">{progress}</span>
        </>
      ) : (
        <>
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 10v6m0 0l-3-3m3 3l3-3M3 17V7a2 2 0 012-2h6l2 2h6a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
          </svg>
          {label}
        </>
      )}
    </button>
  );
}

export default function ResultsPage({ jobId }: Props) {
  const [results,           setResults]           = useState<ResultsData | null>(null);
  const [tab,               setTab]               = useState<Tab>("report");
  const [pdfProgress,       setPdfProgress]       = useState<string | null>(null);
  const [reportPdfProgress, setReportPdfProgress] = useState<string | null>(null);

  useEffect(() => {
    void getResults(jobId).then((data: ResultsData) => setResults(data));
  }, [jobId]);

  const handlePdfExport = async (
    exportFn: (data: ResultsData, setProgress: (s: string | null) => void) => Promise<void>,
    setProgress: (s: string | null) => void,
  ) => {
    if (!results) return;
    try {
      await exportFn(results, setProgress);
    } catch {
      setProgress(null);
      alert("PDF 생성 중 오류가 발생했습니다.");
    }
  };

  if (!results) {
    return (
      <div className="min-h-[calc(100vh-61px)] flex flex-col items-center justify-center gap-4">
        <div
          className="w-10 h-10 rounded-full border-4 border-t-transparent animate-spin"
          style={{ borderColor: "var(--color-border)", borderTopColor: "var(--color-amber)" }}
        />
        <p className="text-sm" style={{ color: "var(--color-text-3)" }}>결과를 불러오는 중...</p>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-6 py-10">

      {/* Page header */}
      <div className="mb-8 fade-up">
        <h2
          className="text-3xl font-bold tracking-tight"
          style={{ fontFamily: "var(--font-heading)", color: "var(--color-navy-dark)" }}
        >
          분석 결과
        </h2>
        {results.analyzed_at && (
          <p className="text-xs mt-1.5" style={{ color: "var(--color-text-3)" }}>
            기준일&nbsp;
            <span style={{ fontFamily: "var(--font-data)" }}>
              {new Date(results.analyzed_at).toLocaleDateString("ko-KR")}
            </span>
            &nbsp;— 이후 발표된 연구는 반영되지 않았을 수 있습니다
          </p>
        )}
      </div>

      {/* Summary banner */}
      <SummaryBanner data={results} />

      {/* Tabs + PDF button */}
      <div
        className="flex items-center justify-between mb-8 fade-up fade-up-1"
        style={{ borderBottom: "1px solid var(--color-border)" }}
      >
        <div className="flex">
          <TabButton id="report" label="보고서"    active={tab === "report"} onClick={setTab} />
          <TabButton id="data"   label="분석 데이터" active={tab === "data"}   onClick={setTab} />
        </div>

        {tab === "report" && (
          <PdfButton
            label="보고서 PDF 저장"
            progress={reportPdfProgress}
            onClick={() => handlePdfExport(exportReportAsPdf, setReportPdfProgress)}
          />
        )}

        {tab === "data" && (
          <PdfButton
            label="데이터 PDF 저장"
            progress={pdfProgress}
            onClick={() => handlePdfExport(exportDataAsPdf, setPdfProgress)}
          />
        )}
      </div>

      {/* Report tab */}
      {tab === "report" && (
        <div className="fade-up">
          {results.report_markdown ? (
            <div
              className="rounded-2xl overflow-hidden"
              style={{ border: "1px solid var(--color-border-subtle)" }}
            >
              <iframe
                src={`/api/jobs/${jobId}/pdf`}
                className="w-full border-0"
                style={{ height: "82vh", display: "block" }}
                title="분석 보고서"
              />
            </div>
          ) : (
            <div
              className="text-center py-20 rounded-2xl"
              style={{ background: "var(--color-surface)", border: "1px solid var(--color-border-subtle)", color: "var(--color-text-3)" }}
            >
              보고서 데이터가 없습니다.
            </div>
          )}
        </div>
      )}

      {/* Data tab */}
      {tab === "data" && (
        <div className="space-y-10 fade-up">
          <section>
            <h3
              className="text-lg font-semibold mb-5"
              style={{ fontFamily: "var(--font-heading)", color: "var(--color-navy-dark)" }}
            >
              지표별 수치 데이터
            </h3>
            <p className="text-xs mb-3 px-1" style={{ color: "var(--color-text-3)" }}>
              ※ 각 행은 서로 다른 논문에서 추출한 데이터 포인트이며, 연도는 해당 논문의 발표 연도입니다.
            </p>
            <MetricTable data={results.indicators} />
          </section>

          {results.indicators.some(i => i.metric_values.some(v => v.year && v.value != null)) && (
            <section>
              <h3
                className="text-lg font-semibold mb-5"
                style={{ fontFamily: "var(--font-heading)", color: "var(--color-navy-dark)" }}
              >
                연도별 추이 차트
              </h3>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {results.indicators.map((item, i) => (
                  <div key={item.indicator.name} id={`chart-ts-${i}`}>
                    <TimeSeriesChart
                      indicatorName={item.indicator.name}
                      values={item.metric_values}
                      unit={item.indicator.unit}
                    />
                  </div>
                ))}
              </div>
            </section>
          )}

          {results.indicators.some(i => i.metric_values.some(v => v.country && v.value != null)) && (
            <section>
              <h3
                className="text-lg font-semibold mb-5"
                style={{ fontFamily: "var(--font-heading)", color: "var(--color-navy-dark)" }}
              >
                국가별 비교 차트
              </h3>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {results.indicators.map((item, i) => (
                  <div key={item.indicator.name} id={`chart-cc-${i}`}>
                    <CountryCompareChart
                      indicatorName={item.indicator.name}
                      values={item.metric_values}
                      unit={item.indicator.unit}
                    />
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
