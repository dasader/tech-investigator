import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

interface MetricValue { year: number | null; value: number | null; country: string | null; }
interface Props { indicatorName: string; values: MetricValue[]; }

export default function TimeSeriesChart({ indicatorName, values }: Props) {
  const data = values
    .filter(v => v.year && v.value != null)
    .sort((a, b) => (a.year ?? 0) - (b.year ?? 0))
    .map(v => ({ year: v.year, value: v.value }));
  if (!data.length) return null;
  return (
    <div className="mt-4">
      <h4 className="text-sm font-medium mb-2">{indicatorName} — 연도별 추이</h4>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data}>
          <XAxis dataKey="year" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Line type="monotone" dataKey="value" stroke="#3b82f6" dot />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
