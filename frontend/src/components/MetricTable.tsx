import type { MetricValue, IndicatorResult } from "../types/results";

interface Props { data: IndicatorResult[]; }

function ConfidenceBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const high = score >= 0.8;
  const mid  = score >= 0.5;
  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold"
      style={{
        background: high ? "#ecfdf5" : mid ? "#fffbeb" : "#fff1f0",
        color:      high ? "#15803d" : mid ? "#b45309" : "#c0392b",
        fontFamily: "var(--font-data)",
      }}
    >
      {high ? "●" : mid ? "◐" : "○"} {pct}%
    </span>
  );
}

function PaperLink({ mv }: { mv: MetricValue }) {
  const href  = mv.doi ? `https://doi.org/${mv.doi}` : mv.source_url ?? undefined;
  const title = mv.paper_title ?? "(제목 없음)";
  return href ? (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="hover:underline underline-offset-2 transition-colors"
      style={{ color: "var(--color-blue-data)", fontFamily: "var(--font-body)", lineHeight: 1.45 }}
      title={title}
    >
      {title}
    </a>
  ) : (
    <span style={{ color: "var(--color-text-2)", fontFamily: "var(--font-body)", lineHeight: 1.45 }}>{title}</span>
  );
}

function Quote({ quote }: { quote: string }) {
  return (
    <blockquote
      className="mt-1.5 pl-3 text-[12px] leading-relaxed italic"
      style={{
        borderLeft: "2px solid var(--color-border)",
        color: "var(--color-text-3)",
        fontFamily: "var(--font-body)",
      }}
    >
      {quote}
    </blockquote>
  );
}

function IndicatorCard({ item, index }: { item: IndicatorResult; index: number }) {
  return (
    <div
      className={`rounded-2xl overflow-hidden fade-up`}
      style={{
        background: "var(--color-surface)",
        border: "1px solid var(--color-border-subtle)",
        animationDelay: `${index * 0.07}s`,
      }}
    >
      {/* Card header */}
      <div
        className="px-6 py-3 flex items-center justify-between"
        style={{ background: "var(--color-navy-dark)", borderBottom: "1px solid rgba(255,255,255,0.06)" }}
      >
        <h3
          className="text-sm font-semibold"
          style={{ color: "var(--color-text-inv)", fontFamily: "var(--font-heading)" }}
        >
          {item.indicator.name}
        </h3>
        {item.indicator.unit && (
          <span
            className="text-[11px] px-2 py-0.5 rounded"
            style={{
              background: "rgba(255,255,255,0.08)",
              color: "rgba(180,210,250,0.7)",
              fontFamily: "var(--font-data)",
            }}
          >
            단위: {item.indicator.unit}
          </span>
        )}
      </div>

      {/* Numeric data table */}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr style={{ borderBottom: "1px solid var(--color-border-subtle)", background: "var(--color-surface-2)" }}>
              {["수치", "연도", "국가", "신뢰도"].map(h => (
                <th
                  key={h}
                  className="px-4 py-2.5 text-left text-[11px] font-semibold tracking-wider uppercase"
                  style={{ color: "var(--color-text-3)" }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {item.metric_values.map((mv, i) => (
              <tr
                key={i}
                style={{ borderBottom: i < item.metric_values.length - 1 ? "1px solid var(--color-border-subtle)" : undefined }}
              >
                <td className="px-4 py-3">
                  <span
                    className="font-semibold text-base"
                    style={{ color: "var(--color-navy)", fontFamily: "var(--font-data)" }}
                  >
                    {mv.value != null ? mv.value.toLocaleString() : "—"}
                  </span>
                  {mv.unit && mv.value != null && (
                    <span className="ml-1 text-xs" style={{ color: "var(--color-text-3)", fontFamily: "var(--font-data)" }}>
                      {mv.unit}
                    </span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <span
                    className="text-sm font-medium"
                    style={{ color: "var(--color-text-2)", fontFamily: "var(--font-data)" }}
                  >
                    {mv.year ?? "—"}
                  </span>
                </td>
                <td className="px-4 py-3 text-sm" style={{ color: "var(--color-text-2)" }}>
                  {mv.country ?? "—"}
                </td>
                <td className="px-4 py-3">
                  <ConfidenceBadge score={mv.confidence_score} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Citation section */}
      <div
        className="px-6 py-4 space-y-4"
        style={{ borderTop: "1px solid var(--color-border-subtle)", background: "var(--color-surface-2)" }}
      >
        <p className="text-[11px] font-semibold uppercase tracking-widest" style={{ color: "var(--color-text-3)" }}>
          출처 논문
        </p>
        {item.metric_values.map((mv, i) => (
          <div key={i} className="flex gap-3">
            <span
              className="shrink-0 w-5 h-5 mt-0.5 flex items-center justify-center rounded text-[10px] font-bold"
              style={{ background: "var(--color-navy-subtle)", color: "var(--color-navy-mid)" }}
            >
              {i + 1}
            </span>
            <div className="flex-1 min-w-0">
              <div className="flex items-start gap-2 flex-wrap">
                <span
                  className="shrink-0 text-[11px] font-medium px-1.5 py-0.5 rounded"
                  style={{
                    background: "var(--color-amber-light)",
                    color: "var(--color-amber)",
                    fontFamily: "var(--font-data)",
                  }}
                >
                  {mv.year ?? "연도미상"}
                </span>
                <p className="text-[13px] leading-snug flex-1">
                  <PaperLink mv={mv} />
                </p>
              </div>
              {(mv.journal_name || mv.doi) && (
                <p className="mt-0.5 text-[11px]" style={{ color: "var(--color-text-3)", fontFamily: "var(--font-data)" }}>
                  {mv.journal_name && <span className="italic mr-1">{mv.journal_name}{mv.doi ? "," : ""}</span>}
                  {mv.doi && <>DOI: {mv.doi}</>}
                </p>
              )}
              {mv.quote && <Quote quote={mv.quote} />}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function MetricTable({ data }: Props) {
  const visible = data.filter(item => item.metric_values.length > 0);

  if (!visible.length) {
    return (
      <div
        className="text-center py-12 rounded-2xl"
        style={{ background: "var(--color-surface)", border: "1px solid var(--color-border-subtle)", color: "var(--color-text-3)" }}
      >
        분석 데이터가 없습니다.
      </div>
    );
  }
  return (
    <div className="space-y-6">
      {visible.map((item, i) => <IndicatorCard key={item.indicator.name} item={item} index={i} />)}
    </div>
  );
}
