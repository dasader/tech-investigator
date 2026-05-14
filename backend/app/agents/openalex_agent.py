import asyncio
import logging
import httpx
from app.config import settings
from app.agents.country_codes import COUNTRY_CODES
from app.agents._http_retry import get_with_retry

logger = logging.getLogger(__name__)

OPENALEX_API_URL = "https://api.openalex.org/works"


def _reconstruct_abstract(inv_idx: dict[str, list[int]] | None) -> str:
    if not inv_idx:
        return ""
    positions: dict[int, str] = {}
    for word, idxs in inv_idx.items():
        for idx in idxs:
            positions[idx] = word
    if not positions:
        return ""
    return " ".join(positions[i] for i in sorted(positions.keys()))


def _strip_doi_prefix(doi: str | None) -> str | None:
    if not doi:
        return None
    for prefix in ("https://doi.org/", "http://doi.org/", "doi.org/"):
        stripped = doi.removeprefix(prefix)
        if stripped != doi:
            return stripped
    return doi


def _resolve_country(authorships: list) -> str | None:
    if not authorships:
        return None
    institutions = authorships[0].get("institutions") or []
    if not institutions:
        return None
    code = institutions[0].get("country_code")
    if not code:
        return None
    return COUNTRY_CODES.get(code, code)


def _resolve_journal(primary_location: dict | None) -> str | None:
    if not primary_location:
        return None
    source = primary_location.get("source") or {}
    return source.get("display_name") or None


async def search_papers_for_indicator(
    keywords: str,
    max_results: int | None = None,
    semaphore: asyncio.Semaphore | None = None,
    *,
    client: httpx.AsyncClient,
) -> list[dict]:
    max_results = max_results if max_results is not None else settings.max_papers_per_indicator
    params: dict = {
        "search": keywords,
        "per-page": min(max_results, 200),
        "sort": "cited_by_count:desc",
    }
    if settings.openalex_api_key:
        params["api_key"] = settings.openalex_api_key
    if settings.search_year_from:
        params["filter"] = f"from_publication_date:{settings.search_year_from}-01-01"

    sem = semaphore or asyncio.Semaphore(1)
    async with sem:
        data = await get_with_retry(
            OPENALEX_API_URL,
            client=client,
            params=params,
            service_name="OpenAlex",
            context=keywords,
        )

    results = data.get("results", []) or []
    papers: list[dict] = []
    for item in results:
        abstract = _reconstruct_abstract(item.get("abstract_inverted_index"))
        if not abstract:
            continue
        papers.append({
            "paper_id": item.get("id"),
            "title": item.get("title", "") or "",
            "abstract": abstract,
            "year": item.get("publication_year"),
            "citation_count": int(item.get("cited_by_count") or 0),
            "doi": _strip_doi_prefix(item.get("doi")),
            "journal_name": _resolve_journal(item.get("primary_location")),
            "country": _resolve_country(item.get("authorships") or []),
            # OpenAlex already exposed authorships here — a None country means
            # the work has no institutional affiliation. Tell extraction_agent
            # not to re-query the same /works endpoint for this paper.
            "country_lookup_done": True,
        })

    logger.info(
        "[OPENALEX] keywords=%r returned=%d after_abstract_filter=%d",
        keywords, len(results), len(papers),
    )
    return papers
