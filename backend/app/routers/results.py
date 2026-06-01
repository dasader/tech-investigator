import markdown as md_lib
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app.models.job import Job
from app.models.indicator import Indicator
from app.models.tech_query import TechQuery
from app.utils import get_search_source, get_engine_label, get_or_404, DEFAULT_SEARCH_SOURCE

router = APIRouter(tags=["results"])

@router.get("/jobs/{job_id}/results")
def get_results(job_id: int, db: Session = Depends(get_db)):
    job = get_or_404(db, Job, job_id, "Job not found")
    if job.status != "done":
        return JSONResponse(
            status_code=202,
            content={"job_id": job_id, "status": job.status, "message": "Processing not complete"},
        )

    tech_query = db.query(TechQuery).filter(TechQuery.id == job.query_id).first()
    search_source = (tech_query.search_source if tech_query else None) or DEFAULT_SEARCH_SOURCE
    category = tech_query.category if tech_query else ""
    description = tech_query.description if tech_query else ""

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
                    "journal_name": mv.journal_name,
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
        "search_source": search_source,
        "category": category,
        "description": description,
        "indicators": output,
    }


@router.get("/jobs/{job_id}/pdf")
def download_pdf(job_id: int, db: Session = Depends(get_db)):
    job = get_or_404(db, Job, job_id, "Job not found")
    if not job.report_markdown:
        raise HTTPException(status_code=404, detail="Report not available")

    search_source = get_search_source(db, job.query_id)
    engine_label = get_engine_label(search_source)
    analyzed_date = job.completed_at.strftime("%Y-%m-%d") if job.completed_at else "—"

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
  .meta-bar {{ background: #f5f7fa; border: 1px solid #e0e4ea; border-radius: 6px; padding: 8px 14px; margin-bottom: 20px; font-size: 12px; color: #555; display: flex; gap: 24px; }}
  .meta-bar span {{ font-weight: 600; color: #1a1a2e; }}
  @media print {{ body {{ margin: 20mm; }} }}
</style>
</head>
<body>
<div class="meta-bar">
  <div>분석 기준일&nbsp;<span>{analyzed_date}</span></div>
  <div>분석 엔진&nbsp;<span>{engine_label}</span></div>
</div>
{html_body}
<script>if (window.top === window) {{ window.addEventListener('load', () => window.print()); }}</script>
</body>
</html>"""
    return HTMLResponse(content=full_html)
