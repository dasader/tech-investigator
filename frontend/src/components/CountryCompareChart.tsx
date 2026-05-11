import { BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer, Cell } from "recharts";
import ChartTooltip from "./ChartTooltip";

interface MetricValue { country: string | null; value: number | null; }
interface Props { indicatorName: string; values: MetricValue[]; unit?: string; }

const PALETTE = [
  "#1e3a5f", "#2c5282", "#2b6cb0", "#3182ce", "#4299e1",
  "#63b3ed", "#90cdf4",
];

export default function CountryCompareChart({ indicatorName, values, unit }: Props) {
  const data = values
    .filter(v => v.country && v.value != null)
    .map(v => ({ country: v.country, value: v.value }));

  if (data.length < 2) return null;

  return (
    <div
      className="mt-4 rounded-2xl overflow-hidden"
      style={{ background: "var(--color-surface)", border: "1px solid var(--color-border-subtle)" }}
    >
      <div
        className="px-5 py-3 flex items-center justify-between"
        style={{ borderBottom: "1px solid var(--color-border-subtle)" }}
      >
        <h4 className="text-sm font-semibold" style={{ color: "var(--color-text)", fontFamily: "var(--font-heading)" }}>
          {indicatorName} — 국가별 비교
        </h4>
        {unit && (
          <span className="text-xs" style={{ color: "var(--color-text-3)", fontFamily: "var(--font-data)" }}>{unit}</span>
        )}
      </div>
      <div className="px-4 pt-4 pb-2">
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={data} margin={{ top: 8, right: 16, left: 8, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-subtle)" horizontal={true} vertical={false} />
            <XAxis
              dataKey="country"
              tick={{ fontSize: 11, fontFamily: "var(--font-body)", fill: "var(--color-text-3)" }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 11, fontFamily: "var(--font-data)", fill: "var(--color-text-3)" }}
              axisLine={false}
              tickLine={false}
              tickFormatter={v => v.toLocaleString()}
              width={60}
            />
            <Tooltip content={<ChartTooltip />} />
            <Bar dataKey="value" radius={[4, 4, 0, 0]}>
              {data.map((_, i) => (
                <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
