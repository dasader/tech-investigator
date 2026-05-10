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
interface Props { data: IndicatorResult[]; }

export default function MetricTable({ data }: Props) {
  return (
    <div className="space-y-6">
      {data.map(item => (
        <div key={item.indicator.name} className="border rounded-lg overflow-hidden">
          <div className="bg-gray-50 px-4 py-2 font-semibold text-sm">{item.indicator.name}</div>
          <table className="w-full text-sm">
            <thead className="bg-gray-100 text-xs text-gray-500">
              <tr>
                <th className="p-2 text-left">값</th>
                <th className="p-2 text-left">연도</th>
                <th className="p-2 text-left">국가</th>
                <th className="p-2 text-left">신뢰도</th>
                <th className="p-2 text-left">출처</th>
              </tr>
            </thead>
            <tbody>
              {item.metric_values.map((mv, i) => (
                <tr key={i} className="border-t">
                  <td className="p-2 font-medium">
                    {mv.value != null ? `${mv.value} ${mv.unit ?? ""}` : "—"}
                  </td>
                  <td className="p-2">{mv.year ?? "—"}</td>
                  <td className="p-2">{mv.country ?? "—"}</td>
                  <td className="p-2">
                    <span className={mv.confidence_score < 0.5 ? "text-orange-500" : "text-green-600"}>
                      {mv.confidence_score < 0.5 ? "⚠ " : ""}{(mv.confidence_score * 100).toFixed(0)}%
                    </span>
                  </td>
                  <td className="p-2">
                    {mv.source_url
                      ? <a href={mv.source_url} target="_blank" rel="noreferrer" className="text-blue-500 hover:underline text-xs">{mv.paper_title?.slice(0, 30)}...</a>
                      : <span className="text-xs text-gray-400">{mv.paper_title?.slice(0, 30)}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}
