interface Props { currentStep: string | null; progressPct: number; status: string; }

const PIPELINE_STEPS = [
  { key: "검색",   label: "논문 검색",   sub: "Paper Search",   pct: 10 },
  { key: "추출",   label: "수치 추출",   sub: "Data Extraction", pct: 40 },
  { key: "검증",   label: "교차 검증",   sub: "Validation",      pct: 70 },
  { key: "리포트", label: "보고서 생성", sub: "Report",          pct: 90 },
];

function stepIndex(pct: number) {
  for (let i = PIPELINE_STEPS.length - 1; i >= 0; i--) {
    if (pct >= PIPELINE_STEPS[i].pct) return i;
  }
  return -1;
}

export default function ProgressStepper({ currentStep, progressPct, status }: Props) {
  const activeStep = stepIndex(progressPct);

  return (
    <div className="space-y-8">

      <div className="flex items-start">
        {PIPELINE_STEPS.map((s, i) => {
          const done   = i < activeStep || status === "done";
          const active = i === activeStep && status !== "done";
          return (
            <div key={s.key} className="flex items-center flex-1 last:flex-none">
              <div className="flex flex-col items-center gap-2">
                <div className="relative flex items-center justify-center">
                  {active && (
                    <div
                      className="absolute rounded-full step-spin"
                      style={{ width: 40, height: 40 }}
                    />
                  )}
                  <div
                    className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all duration-500"
                    style={{
                      background: done
                        ? "var(--color-teal)"
                        : active
                          ? "var(--color-navy-dark)"
                          : "var(--color-border)",
                      color: done || active ? "#fff" : "var(--color-text-3)",
                      boxShadow: active
                        ? "0 0 0 5px var(--color-amber-light), 0 0 12px rgba(192,112,16,0.2)"
                        : done ? "0 0 0 3px rgba(13,122,111,0.12)" : undefined,
                    }}
                  >
                    {done ? (
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="3" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    ) : (
                      <span style={{ fontFamily: "var(--font-data)" }}>{i + 1}</span>
                    )}
                  </div>
                </div>

                <div className="flex flex-col items-center gap-0.5">
                  <span
                    className="text-[11px] font-semibold whitespace-nowrap"
                    style={{ color: active ? "var(--color-amber)" : done ? "var(--color-teal)" : "var(--color-text-3)" }}
                  >
                    {s.label}
                  </span>
                  <span
                    className="text-[9px] font-medium uppercase tracking-wider whitespace-nowrap"
                    style={{
                      fontFamily: "var(--font-data)",
                      color: active ? "rgba(192,112,16,0.55)" : done ? "rgba(13,122,111,0.45)" : "rgba(107,127,150,0.45)",
                    }}
                  >
                    {s.sub}
                  </span>
                </div>
              </div>

              {i < PIPELINE_STEPS.length - 1 && (
                <div
                  className="h-px flex-1 mx-2 mb-8 rounded transition-all duration-700"
                  style={{
                    background: done
                      ? "var(--color-teal)"
                      : "var(--color-border)",
                  }}
                />
              )}
            </div>
          );
        })}
      </div>

      <div className="space-y-2">
        <div
          className="w-full h-2 rounded-full overflow-hidden"
          style={{ background: "var(--color-border)" }}
        >
          <div
            className={`h-2 rounded-full transition-all duration-700 ${status !== "done" && progressPct > 0 ? "progress-bar-animated" : ""}`}
            style={{
              width: `${status === "done" ? 100 : progressPct}%`,
              background: status === "done" ? "var(--color-teal)" : "var(--color-amber)",
            }}
          />
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {status !== "done" && status !== "failed" && (
              <span
                className="inline-flex w-1.5 h-1.5 rounded-full animate-pulse"
                style={{ background: "var(--color-amber)" }}
              />
            )}
            <p
              className="text-xs"
              style={{ color: "var(--color-text-3)", fontFamily: "var(--font-body)" }}
            >
              {status === "done" ? "분석 완료" : currentStep || "대기 중..."}
            </p>
          </div>
          <p
            className="text-xs font-semibold tabular-nums"
            style={{ color: "var(--color-text-2)", fontFamily: "var(--font-data)" }}
          >
            {status === "done" ? "100" : progressPct.toFixed(0)}
            <span className="font-normal ml-0.5 text-[10px]" style={{ color: "var(--color-text-3)" }}>%</span>
          </p>
        </div>
      </div>

      {status === "done" && (
        <div
          className="text-center py-3 rounded-xl text-sm font-semibold fade-up"
          style={{ background: "#ecfdf5", color: "var(--color-teal)", border: "1px solid #a7f3d0" }}
        >
          <svg className="inline w-4 h-4 mr-1.5 -mt-0.5" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          </svg>
          분석이 완료되었습니다. 결과 화면으로 이동합니다...
        </div>
      )}
      {status === "failed" && (
        <div
          className="text-center py-3 rounded-xl text-sm font-medium"
          style={{ background: "#fff1f0", color: "#c0392b", border: "1px solid #ffd0cc" }}
        >
          ⚠ 오류가 발생했습니다. 다시 시도해 주세요.
        </div>
      )}
    </div>
  );
}
