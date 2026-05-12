import { useState } from "react";
import InputPage from "./pages/InputPage";
import IndicatorEditorPage from "./pages/IndicatorEditorPage";
import JobStatusPage from "./pages/JobStatusPage";
import ResultsPage from "./pages/ResultsPage";

type Step = "input" | "indicators" | "status" | "results";

const STEPS: { id: Step; label: string }[] = [
  { id: "input",      label: "기술 입력" },
  { id: "indicators", label: "지표 편집" },
  { id: "status",     label: "분석 진행" },
  { id: "results",    label: "결과 확인" },
];

export default function App() {
  const [step, setStep]       = useState<Step>("input");
  const [queryId, setQueryId] = useState<number | null>(null);
  const [jobId, setJobId]     = useState<number | null>(null);

  const currentIndex = STEPS.findIndex(s => s.id === step);

  return (
    <div className="min-h-screen" style={{ background: "var(--color-bg)" }}>
      <header style={{ background: "var(--color-navy-dark)", borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
        <div className="max-w-8xl mx-auto px-8 flex items-stretch justify-between">
          <button
            className="flex items-center gap-3 py-4 bg-transparent border-0 cursor-pointer"
            onClick={() => { setStep("input"); setQueryId(null); setJobId(null); }}
            title="처음으로"
          >
            <span className="font-serif text-xl font-semibold tracking-tight" style={{ color: "var(--color-text-inv)" }}>
              TechSpec
            </span>
            <span
              className="hidden sm:inline text-xs px-2 py-0.5 rounded"
              style={{ background: "rgba(255,255,255,0.08)", color: "rgba(200,215,240,0.7)" }}
            >
              국가전략기술 Spec 조사 서비스
            </span>
          </button>

          <nav className="flex items-stretch gap-0.5">
            {STEPS.map((s, i) => {
              const done   = i < currentIndex;
              const active = i === currentIndex;
              return (
                <div
                  key={s.id}
                  className="flex items-center gap-2 px-4 text-xs font-medium border-b-2 transition-all duration-300"
                  style={{
                    borderColor: active ? "var(--color-amber)" : done ? "rgba(96,120,200,0.5)" : "transparent",
                    color: active ? "var(--color-amber)" : done ? "rgba(140,165,220,0.85)" : "rgba(100,120,150,0.6)",
                  }}
                >
                  <span
                    className="flex items-center justify-center w-5 h-5 rounded-full text-[10px] font-bold shrink-0"
                    style={{
                      background: active ? "var(--color-amber)" : done ? "rgba(80,105,180,0.5)" : "rgba(60,80,110,0.3)",
                      color: active ? "var(--color-navy-dark)" : done ? "rgba(180,205,240,0.9)" : "rgba(100,120,150,0.5)",
                    }}
                  >
                    {done ? "✓" : i + 1}
                  </span>
                  <span className={i > currentIndex ? "hidden md:inline" : undefined}>{s.label}</span>
                </div>
              );
            })}
          </nav>
        </div>
      </header>

      <main>
        {step === "input" && (
          <InputPage onNext={id => { setQueryId(id); setStep("indicators"); }} />
        )}
        {step === "indicators" && queryId && (
          <IndicatorEditorPage queryId={queryId} onNext={id => { setJobId(id); setStep("status"); }} />
        )}
        {step === "status" && jobId && (
          <JobStatusPage jobId={jobId} onComplete={() => setStep("results")} />
        )}
        {step === "results" && jobId && (
          <ResultsPage jobId={jobId} />
        )}
      </main>
    </div>
  );
}
