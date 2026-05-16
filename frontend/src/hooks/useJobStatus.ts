import { useState, useEffect } from "react";
import { getJob } from "../api/client";

export interface JobStatus {
  status: string;
  progress_pct: number;
  current_step: string | null;
  queue_position: number | null;
}

const POLL_INTERVAL_MS = 3000;

export function useJobStatus(jobId: number | null) {
  const [status, setStatus] = useState<JobStatus | null>(null);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const poll = async () => {
      try {
        const job = await getJob(jobId);
        if (cancelled) return;
        const next: JobStatus = {
          status: job.status,
          progress_pct: job.progress_pct,
          current_step: job.current_step ?? null,
          queue_position: job.queue_position ?? null,
        };
        setStatus(prev =>
          prev
          && prev.status === next.status
          && prev.progress_pct === next.progress_pct
          && prev.current_step === next.current_step
          && prev.queue_position === next.queue_position
            ? prev
            : next,
        );
        if (job.status === "done" || job.status === "failed") return;
      } catch {
        // 일시적 네트워크 오류 시 다음 polling에서 재시도
      }
      if (!cancelled) {
        timer = setTimeout(poll, POLL_INTERVAL_MS);
      }
    };

    void poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [jobId]);

  return status;
}
