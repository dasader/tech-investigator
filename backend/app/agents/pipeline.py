import asyncio
import httpx
from typing import TypedDict, List
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session
from app.agents.search_agent import search_all_sources
from app.agents.extraction_agent import extract_metrics_from_paper
from app.agents.validation_agent import validate_and_rank
from app.agents.synthesis_agent import build_report_markdown
from app.models.indicator import Indicator
from app.models.metric_value import MetricValue
from app.models.job import Job
from app.config import settings

class PipelineState(TypedDict):
    job_id: int
    query_id: int
    category: str
    description: str
    search_source: str
    indicators: List[dict]
    search_results: dict      # indicator_id -> list of papers
    extracted_values: dict    # indicator_id -> list of extractions
    validated_values: dict    # indicator_id -> top3 validated
    report_markdown: str
    error: str

def _update_job(db: Session, job_id: int, progress_pct: float, current_step: str):
    job = db.query(Job).filter(Job.id == job_id).first()
    if job:
        job.progress_pct = progress_pct
        job.current_step = current_step
        db.commit()

async def search_node(state: PipelineState, db: Session, client: httpx.AsyncClient) -> PipelineState:
    _update_job(db, state["job_id"], 10.0, "논문 검색 중")
    semaphore = asyncio.Semaphore(1)
    results = {}
    tasks = [
        search_all_sources(
            ind["search_keywords"] or ind["name"],
            source=state["search_source"],
            semaphore=semaphore,
            client=client,
        )
        for ind in state["indicators"]
    ]
    paper_lists = await asyncio.gather(*tasks)
    for ind, papers in zip(state["indicators"], paper_lists):
        results[ind["id"]] = papers
    return {**state, "search_results": results}

async def extract_node(state: PipelineState, db: Session, client: httpx.AsyncClient) -> PipelineState:
    _update_job(db, state["job_id"], 40.0, "수치 추출 중")

    semaphore = asyncio.Semaphore(10)

    paper_groups: dict[str, dict] = {}
    for ind in state["indicators"]:
        papers = state["search_results"].get(ind["id"], [])[:settings.max_papers_per_indicator]
        for paper in papers:
            # doi → title → year+초록앞부분 순으로 중복 논문을 식별
            key = (paper.get("doi")
                   or paper.get("title")
                   or f"{paper.get('year','')}_{paper.get('abstract','')[:60]}")
            if key not in paper_groups:
                paper_groups[key] = {"paper": paper, "indicators": []}
            paper_groups[key]["indicators"].append(ind)

    tasks = [
        extract_metrics_from_paper(group["paper"], group["indicators"], semaphore, client=client)
        for group in paper_groups.values()
    ]
    batch_results = await asyncio.gather(*tasks, return_exceptions=True)

    extracted: dict = {ind["id"]: [] for ind in state["indicators"]}
    for batch in batch_results:
        if isinstance(batch, Exception):
            continue
        for ind_id, result in batch:
            if ind_id in extracted:
                extracted[ind_id].append(result)

    return {**state, "extracted_values": extracted}

async def validate_node(state: PipelineState, db: Session) -> PipelineState:
    _update_job(db, state["job_id"], 70.0, "교차 검증 중")
    validated = {}
    for ind in state["indicators"]:
        extractions = state["extracted_values"].get(ind["id"], [])
        top3 = validate_and_rank(extractions)
        validated[ind["id"]] = top3
        for mv_data in top3:
            v = mv_data.get("value")
            try:
                numeric_value = float(v) if v is not None else None
            except (TypeError, ValueError):
                numeric_value = None
            mv = MetricValue(
                indicator_id=ind["id"],
                value=numeric_value,
                unit=mv_data.get("unit"),
                year=mv_data.get("year"),
                country=mv_data.get("country"),
                confidence_score=mv_data.get("confidence_score", 0.0),
                paper_title=mv_data.get("paper_title"),
                journal_name=mv_data.get("journal_name"),
                doi=mv_data.get("doi"),
                source_url=mv_data.get("source_url"),
                quote=mv_data.get("quote"),
            )
            db.add(mv)
    db.commit()
    return {**state, "validated_values": validated}

async def synthesize_node(state: PipelineState, db: Session) -> PipelineState:
    _update_job(db, state["job_id"], 90.0, "리포트 생성 중")
    results_by_indicator = {
        ind["name"]: state["validated_values"].get(ind["id"], [])
        for ind in state["indicators"]
    }
    from datetime import datetime, timezone
    analyzed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    markdown = await build_report_markdown(state["category"], state["description"], results_by_indicator, analyzed_at, state["search_source"])
    return {**state, "report_markdown": markdown}

async def run_pipeline(job_id: int, db: Session) -> str:
    from app.models.job import Job
    from app.models.indicator import Indicator
    from app.models.tech_query import TechQuery

    job = db.query(Job).filter(Job.id == job_id).first()
    query = db.query(TechQuery).filter(TechQuery.id == job.query_id).first()
    indicators = db.query(Indicator).filter(
        Indicator.query_id == job.query_id,
        Indicator.confirmed_by_user == True
    ).all()

    state: PipelineState = {
        "job_id": job_id,
        "query_id": job.query_id,
        "category": query.category,
        "description": query.description,
        "search_source": query.search_source or "semantic_scholar",
        "indicators": [
            {"id": i.id, "name": i.name, "unit": i.unit, "search_keywords": i.search_keywords}
            for i in indicators
        ],
        "search_results": {},
        "extracted_values": {},
        "validated_values": {},
        "report_markdown": "",
        "error": "",
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        state = await search_node(state, db, client)
        state = await extract_node(state, db, client)
        state = await validate_node(state, db)
        state = await synthesize_node(state, db)
    return state["report_markdown"]
