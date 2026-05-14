import asyncio
import logging
import httpx
from app.config import settings
from app.agents import scopus_agent, openalex_agent
from app.agents._http_retry import get_with_retry

logger = logging.getLogger(__name__)


def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


def _dedup_key(paper: dict) -> str | None:
    doi = _norm(paper.get("doi"))
    if doi:
        return f"doi:{doi}"
    title = _norm(paper.get("title"))
    if title:
        return f"title:{title}"
    return None


def _merge_two(a: dict, b: dict) -> dict:
    """a, b는 같은 논문. 필드별 best-of 병합."""
    def longer(x: str | None, y: str | None) -> str:
        x, y = x or "", y or ""
        return x if len(x) >= len(y) else y

    def first_truthy(*vals):
        for v in vals:
            if v:
                return v
        return None

    merged = dict(a)
    merged["abstract"] = longer(a.get("abstract"), b.get("abstract"))
    merged["title"] = first_truthy(a.get("title"), b.get("title")) or ""
    merged["year"] = first_truthy(a.get("year"), b.get("year"))
    merged["journal_name"] = first_truthy(a.get("journal_name"), b.get("journal_name"))
    merged["country"] = first_truthy(a.get("country"), b.get("country"))
    merged["citation_count"] = max(
        int(a.get("citation_count") or 0), int(b.get("citation_count") or 0)
    )
    merged["doi"] = first_truthy(a.get("doi"), b.get("doi"))
    merged["paper_id"] = first_truthy(a.get("paper_id"), b.get("paper_id"))
    # OpenAlex가 기여했으면 country_lookup_done=True → extraction_agent의 OpenAlex 재조회 스킵
    if a.get("country_lookup_done") or b.get("country_lookup_done"):
        merged["country_lookup_done"] = True
    return merged


def merge_papers(s2_papers: list[dict], openalex_papers: list[dict]) -> list[dict]:
    """OpenAlex + S2 검색 결과를 DOI(없으면 title) 기준 필드별 best-of로 병합.

    dedup 키가 없는(DOI·title 모두 없는) 논문은 그대로 유지한다.
    결과는 citation_count 내림차순 정렬 — downstream 절단 시 인용수 높은 논문이 생존한다.
    """
    merged: dict[str, dict] = {}
    no_key: list[dict] = []
    for paper in [*s2_papers, *openalex_papers]:
        key = _dedup_key(paper)
        if key is None:
            no_key.append(paper)
        elif key in merged:
            merged[key] = _merge_two(merged[key], paper)
        else:
            merged[key] = paper
    all_papers = [*merged.values(), *no_key]
    all_papers.sort(key=lambda p: int(p.get("citation_count") or 0), reverse=True)
    return all_papers


SS_API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
SS_FIELDS = "paperId,title,abstract,year,citationCount,externalIds,venue"


async def search_papers_for_indicator(
    keywords: str,
    max_results: int | None = None,
    semaphore: asyncio.Semaphore | None = None,
    *,
    client: httpx.AsyncClient,
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
            client=client,
            params=params,
            headers=headers,
            service_name="Semantic Scholar",
            context=keywords,
            inter_attempt_sleep=1.3,
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


async def search_combined(
    keywords: str,
    *,
    s2_semaphore: asyncio.Semaphore,
    openalex_semaphore: asyncio.Semaphore,
    client: httpx.AsyncClient,
    max_results: int | None = None,
) -> list[dict]:
    """OpenAlex + Semantic Scholar를 동시 검색해 병합. 그레이스풀 다운.

    한 소스가 실패하면 warning 로그 후 그 소스는 빈 결과로 취급한다.
    둘 다 실패하면 RuntimeError를 올린다.
    """
    s2_result, oa_result = await asyncio.gather(
        search_papers_for_indicator(keywords, max_results, s2_semaphore, client=client),
        openalex_agent.search_papers_for_indicator(
            keywords, max_results, openalex_semaphore, client=client),
        return_exceptions=True,
    )
    s2_failed = isinstance(s2_result, BaseException)
    oa_failed = isinstance(oa_result, BaseException)
    if s2_failed and oa_failed:
        raise RuntimeError(
            f"combined search failed for {keywords!r}: "
            f"S2={s2_result}, OpenAlex={oa_result}"
        ) from s2_result
    if s2_failed:
        logger.warning(
            "combined search: S2 failed for %r (%s), using OpenAlex only",
            keywords, s2_result,
        )
    if oa_failed:
        logger.warning(
            "combined search: OpenAlex failed for %r (%s), using S2 only",
            keywords, oa_result,
        )
    s2_papers = [] if s2_failed else s2_result
    oa_papers = [] if oa_failed else oa_result
    return merge_papers(s2_papers, oa_papers)


async def search_all_sources(
    keywords: str,
    source: str = "semantic_scholar",
    max_results: int | None = None,
    semaphore: asyncio.Semaphore | None = None,
    *,
    client: httpx.AsyncClient,
) -> list[dict]:
    if source == "scopus":
        return await scopus_agent.search_papers_for_indicator(keywords, max_results, semaphore, client=client)
    if source == "openalex":
        return await openalex_agent.search_papers_for_indicator(keywords, max_results, semaphore, client=client)
    return await search_papers_for_indicator(keywords, max_results, semaphore, client=client)
