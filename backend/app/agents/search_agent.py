import asyncio
import httpx
from app.config import settings
from app.agents import scopus_agent, openalex_agent

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
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.get(SS_API_URL, params=params, headers=headers)
                    if response.status_code == 429:
                        await asyncio.sleep(10 * (attempt + 1))
                        continue
                    response.raise_for_status()
                    data = response.json().get("data", [])
                    break
            except httpx.TimeoutException:
                raise RuntimeError(f"Semantic Scholar API timeout for: {keywords}")
            except httpx.HTTPStatusError as e:
                raise RuntimeError(f"Semantic Scholar API error {e.response.status_code}: {keywords}") from e
            except httpx.RequestError as e:
                raise RuntimeError(f"Semantic Scholar network error: {keywords}") from e
            finally:
                await asyncio.sleep(1.1)
        else:
            raise RuntimeError(f"Semantic Scholar API error 429: {keywords}")

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
