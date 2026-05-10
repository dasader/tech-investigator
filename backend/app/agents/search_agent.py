import httpx
import asyncio
from app.config import settings

SS_API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
SS_FIELDS = "paperId,title,abstract,year,citationCount,externalIds"


async def search_papers_for_indicator(keywords: str, max_results: int = None) -> list[dict]:
    max_results = max_results or settings.max_papers_per_indicator
    headers = {}
    if settings.semantic_scholar_api_key:
        headers["x-api-key"] = settings.semantic_scholar_api_key

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            SS_API_URL,
            params={"query": keywords, "limit": max_results, "fields": SS_FIELDS},
            headers=headers,
        )
        response.raise_for_status()
        data = response.json().get("data", [])

    papers = [
        {
            "paper_id": p.get("paperId"),
            "title": p.get("title", ""),
            "abstract": p.get("abstract", ""),
            "year": p.get("year"),
            "citation_count": p.get("citationCount", 0),
            "doi": (p.get("externalIds") or {}).get("DOI"),
        }
        for p in data
        if p.get("abstract")
    ]
    return papers


async def search_all_sources(keywords: str, max_results: int = None) -> list[dict]:
    results = await search_papers_for_indicator(keywords, max_results)
    return results
