import { useState, useEffect } from "react";

interface JobStatus {
  status: string;
  progress_pct: number;
  current_step: string | null;
}

export function useJobStatus(jobId: number | null) {
  const [status, setStatus] = useState<JobStatus | null>(null);

  useEffect(() => {
    if (!jobId) return;
    const ws = new WebSocket(`ws://localhost:8017/ws/jobs/${jobId}`);
    ws.onmessage = (e) => setStatus(JSON.parse(e.data) as JobStatus);
    return () => ws.close();
  }, [jobId]);

  return status;
}
