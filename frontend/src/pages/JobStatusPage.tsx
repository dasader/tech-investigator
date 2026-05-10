import { useEffect } from "react";
import ProgressStepper from "../components/ProgressStepper";
import { useJobStatus } from "../hooks/useJobStatus";

interface Props { jobId: number; onComplete: () => void; }

export default function JobStatusPage({ jobId, onComplete }: Props) {
  const status = useJobStatus(jobId);

  useEffect(() => {
    if (status?.status === "done") onComplete();
  }, [status?.status, onComplete]);

  return (
    <div className="max-w-xl mx-auto p-8">
      <h2 className="text-xl font-bold mb-6">분석 진행 중</h2>
      <ProgressStepper
        currentStep={status?.current_step ?? null}
        progressPct={status?.progress_pct ?? 0}
        status={status?.status ?? "pending"}
      />
      <p className="text-center text-xs text-gray-400 mt-4">완료 시 이메일로 알림을 보내드립니다 (5~15분 소요)</p>
    </div>
  );
}
