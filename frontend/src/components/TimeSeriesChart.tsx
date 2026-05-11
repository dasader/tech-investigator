import { LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer, ReferenceDot } from "recharts";
import ChartTooltip from "./ChartTooltip";

interface MetricValue { year: number | null; value: number | null; country: string | null; }
interface Props { indicatorName: string; values: MetricValue[]; unit?: string; }

export default function TimeSeriesChart({ indicatorName, values, unit }: Props) {
  const data = values
    .filter(v => v.year && v.value != null)
    .sort((a, b) => (a.year ?? 0) - (b.year ?? 0))
    .map(v => ({ year: v.year, value: v.value }));

  if (data.length < 2) return null;

  const maxVal = Math.max(...data.map(d => d.value ?? 0));

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
          {indicatorName} — 연도별 추이
        </h4>
        {unit && (
          <span className="text-xs" style={{ color: "var(--color-text-3)", fontFamily: "var(--font-data)" }}>{unit}</span>
        )}
      </div>
      <div className="px-4 pt-4 pb-2">
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data} margin={{ top: 8, right: 16, left: 8, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-subtle)" vertical={false} />
            <XAxis
              dataKey="year"
              tick={{ fontSize: 11, fontFamily: "var(--font-data)", fill: "var(--color-text-3)" }}
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
            <Tooltip content={<ChartTooltip labelSuffix="년" />} />
            <Line
              type="monotone"
              dataKey="value"
              stroke="var(--color-amber)"
              strokeWidth={2.5}
              dot={{ fill: "var(--color-amber)", strokeWidth: 0, r: 4 }}
              activeDot={{ r: 6, fill: "var(--color-amber)", stroke: "var(--color-amber-light)", strokeWidth: 3 }}
            />
            {data.find(d => d.value === maxVal) && (
              <ReferenceDot
                x={data.find(d => d.value === maxVal)!.year ?? undefined}
                y={maxVal}
                r={5}
                fill="var(--color-navy-dark)"
                stroke="var(--color-amber)"
                strokeWidth={2}
              />
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
