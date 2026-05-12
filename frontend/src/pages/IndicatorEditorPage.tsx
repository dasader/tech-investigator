import { useState, useEffect } from "react";
import IndicatorList from "../components/IndicatorList";
import { generateIndicators, updateIndicator, deleteIndicator, startJob } from "../api/client";

interface Indicator { id: number; name: string; unit: string; description: string; confirmed_by_user: boolean; }
interface Props { queryId: number; onNext: (jobId: number) => void; }

export default function IndicatorEditorPage({ queryId, onNext }: Props) {
  const [indicators, setIndicators] = useState<Indicator[]>([]);
  const [loading,    setLoading]    = useState(true);
  const [error,      setError]      = useState("");
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    generateIndicators(queryId)
      .then((data: Indicator[]) => { setIndicators(data); setLoading(false); })
      .catch(() => { setError("지표 생성에 실패했습니다. 페이지를 새로고침해 주세요."); setLoading(false); });
  }, [queryId]);

  const handleUpdate = (id: number, data: Partial<Indicator>) => {
    setIndicators(prev => prev.map(i => i.id === id ? { ...i, ...data } : i));
    void updateIndicator(id, data);
  };

  const handleDelete = (id: number) => {
    setIndicators(prev => prev.filter(i => i.id !== id));
    void deleteIndicator(id);
  };

  const handleConfirm = async () => {
    setConfirming(true);
    try {
      await Promise.all(indicators.map(i => updateIndicator(i.id, { confirmed_by_user: true })));
      const job = await startJob(queryId) as { id: number };
      onNext(job.id);
    } catch {
      setError("분석 시작에 실패했습니다. 다시 시도해 주세요.");
      setConfirming(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-[calc(100vh-61px)] flex flex-col items-center justify-center gap-4">
        <div
          className="w-10 h-10 rounded-full border-4 border-t-transparent animate-spin"
          style={{ borderColor: "var(--color-border)", borderTopColor: "var(--color-amber)" }}
        />
        <p className="text-sm" style={{ color: "var(--color-text-3)" }}>
          AI가 지표를 생성하고 있습니다&nbsp;<span style={{ fontFamily: "var(--font-data)" }}>(약 10~20초 소요)</span>
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-[calc(100vh-61px)] flex items-center justify-center px-4">
        <div
          className="max-w-sm w-full text-center p-8 rounded-2xl"
          style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)" }}
        >
          <p className="text-sm font-medium" style={{ color: "#c0392b" }}>{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-[calc(100vh-61px)] flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-2xl">
        <div className="mb-8 fade-up">
          <h2
            className="text-2xl font-bold tracking-tight mb-2"
            style={{ fontFamily: "var(--font-heading)", color: "var(--color-navy-dark)" }}
          >
            지표 확인 및 편집
          </h2>
          <p className="text-sm" style={{ color: "var(--color-text-3)" }}>
            이름·단위를 수정하거나 불필요한 지표를 삭제한 뒤 분석을 시작하세요.
          </p>
        </div>

        <div
          className="rounded-2xl shadow-sm overflow-hidden mb-6 fade-up fade-up-1"
          style={{ background: "var(--color-surface)", border: "1px solid var(--color-border-subtle)" }}
        >
          <div
            className="px-6 py-3 flex items-center justify-between text-xs font-semibold tracking-widest uppercase"
            style={{ background: "var(--color-navy-dark)", color: "rgba(180,205,240,0.6)" }}
          >
            <span>분석 지표 목록</span>
            <span
              className="px-2 py-0.5 rounded font-mono"
              style={{ background: "rgba(255,255,255,0.08)", color: "rgba(200,220,255,0.7)" }}
            >
              {indicators.length}개
            </span>
          </div>
          <div className="p-4">
            <IndicatorList indicators={indicators} onUpdate={handleUpdate} onDelete={handleDelete} />
          </div>
        </div>

        <button
          onClick={handleConfirm}
          disabled={confirming || indicators.length === 0}
          className="w-full py-3 rounded-xl text-sm font-semibold transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed fade-up fade-up-2"
          style={{
            background: "var(--color-navy-dark)",
            color: "var(--color-text-inv)",
            letterSpacing: "0.02em",
          }}
        >
          {confirming ? (
            <span className="flex items-center justify-center gap-2">
              <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
              분석 시작 중...
            </span>
          ) : `확정 후 분석 시작 (${indicators.length}개 지표) →`}
        </button>
      </div>
    </div>
  );
}
