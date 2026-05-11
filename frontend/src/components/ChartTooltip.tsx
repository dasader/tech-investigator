interface Props {
  active?: boolean;
  payload?: { value: number }[];
  label?: string | number;
  labelSuffix?: string;
}

export default function ChartTooltip({ active, payload, label, labelSuffix = "" }: Props) {
  if (!active || !payload?.length) return null;
  return (
    <div
      className="px-3 py-2 rounded-lg shadow-lg text-xs"
      style={{
        background: "var(--color-navy-dark)",
        color: "var(--color-text-inv)",
        border: "1px solid rgba(255,255,255,0.1)",
        fontFamily: "var(--font-body)",
      }}
    >
      <p className="font-semibold mb-1" style={{ color: "rgba(180,205,240,0.7)" }}>
        {label}{labelSuffix}
      </p>
      <p className="font-bold text-sm" style={{ fontFamily: "var(--font-data)" }}>
        {payload[0].value?.toLocaleString()}
      </p>
    </div>
  );
}
