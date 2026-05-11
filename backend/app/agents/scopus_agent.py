import asyncio
import httpx
from app.config import settings

SCOPUS_API_URL = "https://api.elsevier.com/content/search/scopus"

_SCOPUS_COUNTRY_MAP: dict[str, str] = {
    "United States": "USA",
    "United States of America": "USA",
    "China": "China",
    "South Korea": "South Korea",
    "Korea": "South Korea",
    "Japan": "Japan",
    "Germany": "Germany",
    "United Kingdom": "UK",
    "France": "France",
    "Switzerland": "Switzerland",
    "Australia": "Australia",
    "Canada": "Canada",
    "India": "India",
    "Singapore": "Singapore",
    "Taiwan": "Taiwan",
    "Sweden": "Sweden",
    "Netherlands": "Netherlands",
    "Italy": "Italy",
    "Spain": "Spain",
    "Israel": "Israel",
    "Denmark": "Denmark",
    "Finland": "Finland",
    "Belgium": "Belgium",
    "Austria": "Austria",
    "Norway": "Norway",
    "Brazil": "Brazil",
    "Russia": "Russia",
    "Saudi Arabia": "Saudi Arabia",
    "Iran": "Iran",
    "Turkey": "Turkey",
}


def _resolve_country(affiliations: list) -> str | None:
    if not affiliations:
        return None
    raw = affiliations[0].get("affiliation-country")
    if not raw:
        return None
    return _SCOPUS_COUNTRY_MAP.get(raw, raw)


async def search_papers_for_indicator(
    keywords: str,
    max_results: int | None = None,
    semaphore: asyncio.Semaphore | None = None,
) -> list[dict]:
    max_results = max_results if max_results is not None else settings.max_papers_per_indicator
    headers = {
        "X-ELS-APIKey": settings.elsevier_api_key,
        "Accept": "application/json",
    }
    params: dict = {
        "query": keywords,
        "count": max_results,
        "field": "dc:title,dc:description,prism:doi,citedby-count,prism:coverDate,affiliation",
    }
    if settings.search_year_from:
        params["date"] = f"{settings.search_year_from}-"

    sem = semaphore or asyncio.Semaphore(1)
    entries: list = []
    async with sem:
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.get(SCOPUS_API_URL, params=params, headers=headers)
                    if response.status_code == 429:
                        await asyncio.sleep(10 * (attempt + 1))
                        continue
                    response.raise_for_status()
                    entries = (
                        response.json()
                        .get("search-results", {})
                        .get("entry", [])
                    )
                    break
            except httpx.TimeoutException:
                raise RuntimeError(f"Scopus API timeout for: {keywords}")
            except httpx.RequestError as e:
                raise RuntimeError(f"Scopus network error: {keywords}") from e
            finally:
                await asyncio.sleep(1.1)
        else:
            raise RuntimeError(f"Scopus API error 429: {keywords}")

    papers = [
        {
            "paper_id": entry.get("dc:identifier"),
            "title": entry.get("dc:title", ""),
            "abstract": entry.get("dc:description", ""),
            "year": int(entry["prism:coverDate"][:4]) if entry.get("prism:coverDate") else None,
            "citation_count": int(entry.get("citedby-count") or 0),
            "doi": entry.get("prism:doi"),
            "country": _resolve_country(entry.get("affiliation") or []),
        }
        for entry in entries
        if entry.get("dc:description")
    ]
    return papers
