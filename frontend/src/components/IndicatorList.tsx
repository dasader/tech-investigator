import type { Indicator } from "../types/indicator";

interface Props {
  indicators: Indicator[];
  onUpdate: (id: number, data: Partial<Indicator>) => void;
  onDelete: (id: number) => void;
}

export default function IndicatorList({ indicators, onUpdate, onDelete }: Props) {
  return (
    <ul className="space-y-2">
      {indicators.map((ind, idx) => (
        <li
          key={ind.id}
          className="fade-up flex items-center gap-3 rounded-xl px-4 py-3 group transition-shadow hover:shadow-sm"
          style={{
            background: "var(--color-surface)",
            border: "1.5px solid var(--color-border-subtle)",
            animationDelay: `${idx * 0.04}s`,
          }}
        >
          <span
            className="shrink-0 w-5 h-5 flex items-center justify-center rounded text-[10px] font-bold"
            style={{ background: "var(--color-navy-subtle)", color: "var(--color-navy-mid)" }}
          >
            {idx + 1}
          </span>
          <input
            className="flex-1 text-sm font-medium bg-transparent focus:outline-none"
            style={{
              color: "var(--color-text)",
              fontFamily: "var(--font-body)",
              borderBottom: "1.5px solid transparent",
              transition: "border-color 0.15s",
            }}
            onFocus={e => { e.currentTarget.style.borderBottomColor = "var(--color-amber)"; }}
            onBlur={e =>  { e.currentTarget.style.borderBottomColor = "transparent"; }}
            value={ind.name}
            onChange={e => onUpdate(ind.id, { name: e.target.value })}
          />
          <input
            className="w-20 text-xs text-right bg-transparent focus:outline-none"
            style={{
              color: "var(--color-text-3)",
              fontFamily: "var(--font-mono)",
              borderBottom: "1.5px solid transparent",
              transition: "border-color 0.15s",
            }}
            onFocus={e => { e.currentTarget.style.borderBottomColor = "var(--color-amber)"; }}
            onBlur={e =>  { e.currentTarget.style.borderBottomColor = "transparent"; }}
            value={ind.unit || ""}
            placeholder="단위"
            onChange={e => onUpdate(ind.id, { unit: e.target.value })}
          />
          <button
            onClick={() => onDelete(ind.id)}
            className="shrink-0 w-6 h-6 flex items-center justify-center rounded-full text-sm opacity-0 group-hover:opacity-100 transition-opacity"
            style={{ color: "#c0392b", background: "#fff1f0" }}
            title="삭제"
          >
            ×
          </button>
        </li>
      ))}
    </ul>
  );
}
