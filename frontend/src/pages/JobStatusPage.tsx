import { useEffect } from "react";
import ProgressStepper from "../components/ProgressStepper";
import { useJobStatus } from "../hooks/useJobStatus";

interface Props { jobId: number; onComplete: () => void; }

/* ── 대기 화면 ──────────────────────────────────────────────────────────── */
function QueuedView({ position }: { position: number }) {
  const estimatedMin = Math.max(5, (position - 1) * 10 + 5);

  return (
    <div className="min-h-[calc(100vh-61px)] flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">

        {/* 순서 배지 + 동심원 */}
        <div className="flex flex-col items-center mb-10 fade-up">
          <div className="relative flex items-center justify-center mb-7" style={{ width: 160, height: 160 }}>
            {/* 퍼지는 링 2개 */}
            <div
              className="absolute rounded-full queue-ring-far"
              style={{ width: 160, height: 160, border: "1.5px solid var(--color-amber)" }}
            />
            <div
              className="absolute rounded-full queue-ring-near"
              style={{ width: 130, height: 130, border: "1.5px solid var(--color-amber)" }}
            />
            {/* 배경 링 */}
            <div
              className="absolute rounded-full queue-ring-bg"
              style={{ width: 108, height: 108, background: "var(--color-amber-light)" }}
            />
            {/* 중앙 배지 */}
            <div
              className="relative flex flex-col items-center justify-center rounded-full"
              style={{
                width: 88, height: 88,
                background: "var(--color-navy-dark)",
                boxShadow: "0 0 0 3px var(--color-amber-light), 0 8px 24px rgba(13,22,40,0.18)",
              }}
            >
              <span
                className="text-[9px] font-bold uppercase tracking-[0.18em]"
                style={{ color: "rgba(190,210,250,0.55)", letterSpacing: "0.18em" }}
              >
                대기 순서
              </span>
              <span
                className="text-4xl font-bold leading-none mt-0.5"
                style={{ fontFamily: "var(--font-data)", color: "#fff" }}
              >
                {position}
              </span>
            </div>
          </div>

          <h2
            className="text-[1.6rem] font-bold tracking-tight mb-1.5"
            style={{ fontFamily: "var(--font-heading)", color: "var(--color-navy-dark)", letterSpacing: "-0.01em" }}
          >
            분석 대기 중
          </h2>
          <p className="text-sm text-center max-w-xs" style={{ color: "var(--color-text-3)", lineHeight: 1.6 }}>
            현재 다른 분석이 진행 중입니다.<br />순서가 되면 자동으로 시작됩니다.
          </p>
        </div>

        {/* 정보 카드 */}
        <div
          className="rounded-2xl px-7 py-6 space-y-5 fade-up fade-up-1"
          style={{ background: "var(--color-surface)", border: "1px solid var(--color-border-subtle)", boxShadow: "0 2px 16px rgba(13,22,40,0.06)" }}
        >
          {/* 예상 대기 + 활성 인디케이터 */}
          <div className="flex items-end justify-between">
            <div>
              <p
                className="text-[10px] font-bold uppercase tracking-[0.14em] mb-1"
                style={{ color: "var(--color-text-3)" }}
              >
                예상 대기 시간
              </p>
              <p style={{ fontFamily: "var(--font-data)", color: "var(--color-amber)", lineHeight: 1 }}>
                <span className="text-4xl font-bold">~{estimatedMin}</span>
                <span className="text-base font-semibold ml-1.5" style={{ color: "var(--color-text-3)" }}>분</span>
              </p>
            </div>
            {/* 파동 바 3개 */}
            <div className="flex items-end gap-1 pb-1">
              {[
                { cls: "queue-bar",   h: 12 },
                { cls: "queue-bar-2", h: 20 },
                { cls: "queue-bar-3", h: 14 },
              ].map(({ cls, h }) => (
                <div
                  key={cls}
                  className={`w-1.5 rounded-full ${cls}`}
                  style={{ height: h, background: "var(--color-amber)", transformOrigin: "bottom" }}
                />
              ))}
            </div>
          </div>

          {/* 진행 바 */}
          <div>
            <div className="w-full h-1.5 rounded-full overflow-hidden" style={{ background: "var(--color-border)" }}>
              <div
                className="h-full rounded-full transition-all duration-700"
                style={{
                  width: `${Math.max(5, Math.round(100 / position))}%`,
                  background: "linear-gradient(90deg, var(--color-amber) 0%, #e8a030 100%)",
                  opacity: 0.65,
                }}
              />
            </div>
            <p className="text-[11px] mt-1.5" style={{ color: "var(--color-text-3)", fontFamily: "var(--font-body)" }}>
              대기열 {position}번째 &middot; 앞선 분석이 완료되면 자동으로 시작됩니다
            </p>
          </div>

          {/* 안내 */}
          <div
            className="flex gap-3 rounded-xl px-4 py-3"
            style={{ background: "var(--color-amber-light)", border: "1px solid rgba(192,112,16,0.12)" }}
          >
            <svg
              className="shrink-0 mt-0.5"
              style={{ width: 15, height: 15, color: "var(--color-amber)" }}
              fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <p className="text-[12.5px] leading-relaxed" style={{ color: "var(--color-warn)" }}>
              이 페이지를 닫아도 분석은 계속 진행됩니다.
              이메일 주소를 입력하셨다면 완료 시 알림을 받으실 수 있습니다.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── 진행 화면 쉘 ────────────────────────────────────────────────────────── */
function ProcessingShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-[calc(100vh-61px)] flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-xl">
        {/* 헤더 */}
        <div className="mb-9 fade-up">
          <div className="flex items-center gap-2.5 mb-2">
            {/* 라이브 도트 */}
            <span className="relative flex h-2.5 w-2.5">
              <span
                className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-60"
                style={{ background: "var(--color-amber)" }}
              />
              <span
                className="relative inline-flex rounded-full h-2.5 w-2.5"
                style={{ background: "var(--color-amber)" }}
              />
            </span>
            <h2
              className="text-2xl font-bold tracking-tight"
              style={{ fontFamily: "var(--font-heading)", color: "var(--color-navy-dark)", letterSpacing: "-0.01em" }}
            >
              분석 진행 중
            </h2>
          </div>
          <p className="text-sm pl-[1.125rem]" style={{ color: "var(--color-text-3)" }}>
            논문을 검색하고 Gemini AI로 수치를 추출합니다
          </p>
        </div>

        {/* 카드 */}
        <div
          className="rounded-2xl px-8 py-8 fade-up fade-up-1"
          style={{
            background: "var(--color-surface)",
            border: "1px solid var(--color-border-subtle)",
            boxShadow: "0 2px 16px rgba(13,22,40,0.06)",
          }}
        >
          {children}
        </div>

        <p
          className="text-center text-[11px] mt-5"
          style={{ color: "var(--color-text-3)" }}
        >
          완료 시 이메일로 알림을 보내드립니다 &middot; 예상 소요 시간 5–15분
        </p>
      </div>
    </div>
  );
}

/* ── 메인 ────────────────────────────────────────────────────────────────── */
export default function JobStatusPage({ jobId, onComplete }: Props) {
  const status = useJobStatus(jobId);

  useEffect(() => {
    if (status?.status === "done") {
      const t = setTimeout(onComplete, 1200);
      return () => clearTimeout(t);
    }
  }, [status?.status, onComplete]);

  if (status?.status === "pending" && status.queue_position != null) {
    return <QueuedView position={status.queue_position} />;
  }

  return (
    <ProcessingShell>
      <ProgressStepper
        currentStep={status?.current_step ?? null}
        progressPct={status?.progress_pct ?? 0}
        status={status?.status ?? "pending"}
      />
    </ProcessingShell>
  );
}
