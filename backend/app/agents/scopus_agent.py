import asyncio
from datetime import datetime
import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

SCOPUS_API_URL = "https://api.elsevier.com/content/search/scopus"
S2_BATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/batch"

_SCOPUS_COUNTRY_MAP: dict[str, str] = {
    "United States": "USA",
    "United States of America": "USA",
    "China": "China",
    "People's Republic of China": "China",
    "South Korea": "South Korea",
    "Korea": "South Korea",
    "Republic of Korea": "South Korea",
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
    "Czech Republic": "Czech Republic",
    "Norway": "Norway",
    "Brazil": "Brazil",
    "Russia": "Russia",
    "Russian Federation": "Russia",
    "Saudi Arabia": "Saudi Arabia",
    "United Arab Emirates": "UAE",
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


async def _batch_fetch_abstracts(doi_list: list[str]) -> dict[str, str]:
    """Semantic Scholar batch API로 DOI → abstract 매핑 반환."""
    if not doi_list:
        return {}
    ids = [f"DOI:{doi}" for doi in doi_list]
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                S2_BATCH_URL,
                params={"fields": "abstract"},
                json={"ids": ids},
            )
            if r.status_code != 200:
                return {}
            items = r.json()
            if len(items) != len(doi_list):
                logger.warning("S2 batch length mismatch: expected %d, got %d", len(doi_list), len(items))
            result: dict[str, str] = {}
            for doi, item in zip(doi_list, items):
                if item and item.get("abstract"):
                    result[doi] = item["abstract"]
            return result
    except Exception as e:
        logger.warning("S2 batch abstract fetch failed: %s", e)
        return {}


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
        "count": min(max_results, 25),  # Scopus free tier max is 25 per request
        "field": "dc:title,dc:description,prism:doi,citedby-count,prism:coverDate,affiliation,prism:publicationName",
    }
    if settings.search_year_from:
        params["date"] = f"{settings.search_year_from}-{datetime.now().year}"

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

    papers = []
    for entry in entries:
        aff = entry.get("affiliation") or []
        if isinstance(aff, dict):
            aff = [aff]
        papers.append(
            {
                "paper_id": entry.get("dc:identifier"),
                "title": entry.get("dc:title", ""),
                "abstract": entry.get("dc:description", ""),  # 대부분 빈값
                "year": int(entry["prism:coverDate"][:4]) if entry.get("prism:coverDate") else None,
                "citation_count": int(entry.get("citedby-count") or 0),
                "doi": entry.get("prism:doi"),
                "journal_name": entry.get("prism:publicationName") or None,
                "country": _resolve_country(aff),
            }
        )

    # Scopus free tier는 abstract를 반환하지 않으므로 S2 batch API로 보완
    doi_missing = [p["doi"] for p in papers if not p["abstract"] and p.get("doi")]
    if doi_missing:
        abstracts = await _batch_fetch_abstracts(doi_missing)
        for p in papers:
            if p.get("doi") and p["doi"] in abstracts:
                p["abstract"] = abstracts[p["doi"]]

    return [p for p in papers if p.get("abstract")]
