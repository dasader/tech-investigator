import { useState, useEffect } from "react";

export interface JobStatus {
  status: string;
  progress_pct: number;
  current_step: string | null;
  queue_position: number | null;
}

export function useJobStatus(jobId: number | null) {
  const [status, setStatus] = useState<JobStatus | null>(null);

  useEffect(() => {
    if (!jobId) return;
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/jobs/${jobId}`);
    ws.onmessage = (e) => setStatus(JSON.parse(e.data) as JobStatus);
    return () => ws.close();
  }, [jobId]);

  return status;
}
