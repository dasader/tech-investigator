import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.database import SessionLocal
from app.models.job import Job

router = APIRouter()

@router.websocket("/ws/jobs/{job_id}")
async def job_status_ws(websocket: WebSocket, job_id: int):
    await websocket.accept()
    db = SessionLocal()
    prev = None
    try:
        while True:
            db.expire_all()
            job = db.query(Job).filter(Job.id == job_id).first()
            if not job:
                await websocket.send_json({"error": "not found"})
                await websocket.close()
                break
            queue_position = None
            if job.status == "pending":
                queue_position = db.query(Job).filter(
                    Job.status == "pending",
                    Job.id < job_id,
                ).count() + 1

            curr = (job.status, job.progress_pct, queue_position)
            if curr != prev:
                await websocket.send_json({
                    "status": job.status,
                    "progress_pct": job.progress_pct,
                    "current_step": job.current_step,
                    "queue_position": queue_position,
                })
                prev = curr
            if job.status in ("done", "failed"):
                break
            await asyncio.sleep(3)
    except WebSocketDisconnect:
        pass
    finally:
        db.close()
