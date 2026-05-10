import { useState } from "react";
import InputPage from "./pages/InputPage";
import IndicatorEditorPage from "./pages/IndicatorEditorPage";
import JobStatusPage from "./pages/JobStatusPage";
import ResultsPage from "./pages/ResultsPage";

type Step = "input" | "indicators" | "status" | "results";

export default function App() {
  const [step, setStep] = useState<Step>("input");
  const [queryId, setQueryId] = useState<number | null>(null);
  const [jobId, setJobId] = useState<number | null>(null);

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white border-b px-8 py-4">
        <span className="font-bold text-lg text-blue-700">TechSpec</span>
        <span className="ml-2 text-xs text-gray-400">국가전략기술 Spec 조사 서비스</span>
      </nav>
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
    </div>
  );
}
