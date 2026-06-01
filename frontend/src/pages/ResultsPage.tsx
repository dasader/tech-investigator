import { useEffect, useMemo, useState } from "react";
import MetricTable from "../components/MetricTable";
import GlobalBestTable from "../components/GlobalBestTable";
import PageLoader from "../components/PageLoader";
import { getResults } from "../api/client";
import { printCurrentView } from "../utils/exportPdf";
import { getEngineLabel } from "../utils/format";
import { extractGlobalBestTable } from "../utils/markdownTable";
import type { ResultsData } from "../types/results";

interface Props { jobId: number; }

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

function PdfButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="mb-1 inline-flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition-all"
      style={{
        background: "var(--color-navy-dark)",
        color: "var(--color-text-inv)",
      }}
    >
      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 10v6m0 0l-3-3m3 3l3-3M3 17V7a2 2 0 012-2h6l2 2h6a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
      </svg>
      데이터 PDF 저장
    </button>
  );
}

export default function ResultsPage({ jobId }: Props) {
  const [results, setResults] = useState<ResultsData | null>(null);

  useEffect(() => {
    void getResults(jobId).then((data: ResultsData) => setResults(data));
  }, [jobId]);

  const globalBest = useMemo(
    () => (results?.report_markdown ? extractGlobalBestTable(results.report_markdown) : null),
    [results?.report_markdown],
  );

  if (!results) {
    return <PageLoader>결과를 불러오는 중...</PageLoader>;
  }

  return (
    <div className="max-w-7xl mx-auto px-6 py-10">

      <div className="mb-8 fade-up no-print">
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

      <div className="no-print">
        <SummaryBanner data={results} />
      </div>

      <div className="flex items-center justify-end mb-6 no-print">
        <PdfButton onClick={printCurrentView} />
      </div>

      <div className="space-y-10 fade-up">
        {globalBest && (
          <section>
            <h3
              className="text-lg font-semibold mb-4"
              style={{ fontFamily: "var(--font-heading)", color: "var(--color-navy-dark)" }}
            >
              지표별 글로벌 최고 달성치
            </h3>
            <GlobalBestTable data={globalBest} />
          </section>
        )}

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
      </div>
    </div>
  );
}
