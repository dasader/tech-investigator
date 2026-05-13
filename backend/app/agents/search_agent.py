import asyncio
from app.config import settings
from app.agents import scopus_agent, openalex_agent
from app.agents._http_retry import get_with_retry

SS_API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
SS_FIELDS = "paperId,title,abstract,year,citationCount,externalIds,venue"


async def search_papers_for_indicator(
    keywords: str,
    max_results: int | None = None,
    semaphore: asyncio.Semaphore | None = None,
) -> list[dict]:
    max_results = max_results if max_results is not None else settings.max_papers_per_indicator
    headers = {}
    if settings.semantic_scholar_api_key:
        headers["x-api-key"] = settings.semantic_scholar_api_key

    params: dict = {"query": keywords, "limit": max_results, "fields": SS_FIELDS}
    if settings.search_year_from:
        params["year"] = f"{settings.search_year_from}-"

    sem = semaphore or asyncio.Semaphore(1)
    async with sem:
        payload = await get_with_retry(
            SS_API_URL,
            params=params,
            headers=headers,
            service_name="Semantic Scholar",
            context=keywords,
            inter_attempt_sleep=1.1,
        )
        data = payload.get("data", [])

    papers = [
        {
            "paper_id": p.get("paperId"),
            "title": p.get("title", ""),
            "abstract": p.get("abstract", ""),
            "year": p.get("year"),
            "citation_count": p.get("citationCount", 0),
            "doi": (p.get("externalIds") or {}).get("DOI"),
            "journal_name": p.get("venue") or None,
            "country": None,
        }
        for p in data
        if p.get("abstract")
    ]
    return papers


async def search_all_sources(
    keywords: str,
    source: str = "semantic_scholar",
    max_results: int | None = None,
    semaphore: asyncio.Semaphore | None = None,
) -> list[dict]:
    if source == "scopus":
        return await scopus_agent.search_papers_for_indicator(keywords, max_results, semaphore)
    if source == "openalex":
        return await openalex_agent.search_papers_for_indicator(keywords, max_results, semaphore)
    return await search_papers_for_indicator(keywords, max_results, semaphore)
