import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

interface MetricValue { country: string | null; value: number | null; }
interface Props { indicatorName: string; values: MetricValue[]; }

export default function CountryCompareChart({ indicatorName, values }: Props) {
  const data = values
    .filter(v => v.country && v.value != null)
    .map(v => ({ country: v.country, value: v.value }));
  if (!data.length) return null;
  return (
    <div className="mt-4">
      <h4 className="text-sm font-medium mb-2">{indicatorName} — 국가별 비교</h4>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={data}>
          <XAxis dataKey="country" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Bar dataKey="value" fill="#6366f1" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
