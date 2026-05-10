import { useEffect, useState } from "react";
import MetricTable from "../components/MetricTable";
import TimeSeriesChart from "../components/TimeSeriesChart";
import CountryCompareChart from "../components/CountryCompareChart";
import { getResults } from "../api/client";

interface MetricValue {
  value: number | null;
  unit: string | null;
  year: number | null;
  country: string | null;
  confidence_score: number;
  paper_title: string | null;
  doi: string | null;
  source_url: string | null;
  quote: string | null;
}
interface IndicatorResult {
  indicator: { name: string; unit: string };
  metric_values: MetricValue[];
}
interface ResultsData {
  job_id: number;
  analyzed_at: string | null;
  indicators: IndicatorResult[];
}

interface Props { jobId: number; }

export default function ResultsPage({ jobId }: Props) {
  const [results, setResults] = useState<ResultsData | null>(null);

  useEffect(() => {
    void getResults(jobId).then((data: ResultsData) => setResults(data));
  }, [jobId]);

  if (!results) return <div className="p-8 text-center">결과를 불러오는 중...</div>;

  return (
    <div className="max-w-3xl mx-auto p-8">
      <div className="flex justify-between items-center mb-2">
        <h2 className="text-xl font-bold">분석 결과</h2>
        <a
          href={`/api/jobs/${jobId}/pdf`}
          className="bg-purple-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-purple-700"
        >
          PDF 다운로드
        </a>
      </div>
      {results.analyzed_at && (
        <p className="text-xs text-gray-400 mb-6">
          분석 기준일: {new Date(results.analyzed_at).toLocaleDateString("ko-KR")} — 이후 발표된 연구는 반영되지 않았을 수 있습니다.
        </p>
      )}
      <MetricTable data={results.indicators} />
      {results.indicators.map(item => (
        <div key={item.indicator.name}>
          <TimeSeriesChart indicatorName={item.indicator.name} values={item.metric_values} />
          <CountryCompareChart indicatorName={item.indicator.name} values={item.metric_values} />
        </div>
      ))}
    </div>
  );
}
