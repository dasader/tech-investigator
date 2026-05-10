import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.database import SessionLocal
from app.models.job import Job

router = APIRouter()

@router.websocket("/ws/jobs/{job_id}")
async def job_status_ws(websocket: WebSocket, job_id: int):
    await websocket.accept()
    db = SessionLocal()
    try:
        while True:
            job = db.query(Job).filter(Job.id == job_id).first()
            if not job:
                await websocket.send_json({"error": "not found"})
                await websocket.close()
                break
            await websocket.send_json({
                "status": job.status,
                "progress_pct": job.progress_pct,
                "current_step": job.current_step,
            })
            if job.status in ("done", "failed"):
                break
            await asyncio.sleep(3)
    except WebSocketDisconnect:
        pass
    finally:
        db.close()
