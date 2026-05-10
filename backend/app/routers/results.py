import markdown as md_lib
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app.models.job import Job
from app.models.indicator import Indicator

router = APIRouter(tags=["results"])

@router.get("/jobs/{job_id}/results")
def get_results(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "done":
        return JSONResponse(
            status_code=202,
            content={"job_id": job_id, "status": job.status, "message": "Processing not complete"},
        )
    indicators = (
        db.query(Indicator)
        .filter(Indicator.query_id == job.query_id)
        .options(joinedload(Indicator.metric_values))
        .all()
    )
    output = []
    for ind in indicators:
        output.append({
            "indicator": {"id": ind.id, "name": ind.name, "unit": ind.unit},
            "metric_values": [
                {
                    "value": mv.value,
                    "unit": mv.unit,
                    "year": mv.year,
                    "country": mv.country,
                    "confidence_score": mv.confidence_score,
                    "paper_title": mv.paper_title,
                    "doi": mv.doi,
                    "source_url": mv.source_url,
                    "quote": mv.quote,
                }
                for mv in ind.metric_values
            ],
        })
    return {
        "job_id": job_id,
        "analyzed_at": job.completed_at.isoformat() if job.completed_at else None,
        "report_markdown": job.report_markdown,
        "indicators": output,
    }


@router.get("/jobs/{job_id}/pdf")
def download_pdf(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.report_markdown:
        raise HTTPException(status_code=404, detail="Report not available")

    html_body = md_lib.markdown(str(job.report_markdown), extensions=["tables"])
    full_html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>TechSpec 보고서 - Job {job_id}</title>
<style>
  body {{ font-family: 'Noto Sans KR', 'Malgun Gothic', sans-serif; margin: 40px; font-size: 13px; line-height: 1.6; color: #222; }}
  table {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
  th, td {{ border: 1px solid #ccc; padding: 8px 10px; text-align: left; }}
  th {{ background: #f0f0f0; font-weight: 600; }}
  h1 {{ font-size: 20px; color: #1a1a2e; margin-bottom: 4px; }}
  h2 {{ font-size: 16px; color: #1a1a2e; margin-top: 24px; }}
  h3 {{ font-size: 14px; color: #333; }}
  blockquote {{ border-left: 3px solid #ccc; padding-left: 12px; color: #555; }}
  @media print {{ body {{ margin: 20mm; }} button {{ display: none; }} }}
</style>
</head>
<body>
<button onclick="window.print()" style="margin-bottom:16px;padding:8px 16px;background:#7c3aed;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px;">PDF로 저장 (인쇄)</button>
{html_body}
</body>
</html>"""
    return HTMLResponse(content=full_html)
