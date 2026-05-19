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


def _longer(x: str | None, y: str | None) -> str:
    x, y = x or "", y or ""
    return x if len(x) >= len(y) else y


def _first_truthy(*vals):
    for v in vals:
        if v:
            return v
    return None


def _merge_two(a: dict, b: dict) -> dict:
    """a, b는 같은 논문. 필드별 best-of 병합."""
    merged = dict(a)
    merged["abstract"] = _longer(a.get("abstract"), b.get("abstract"))
    merged["title"] = _first_truthy(a.get("title"), b.get("title")) or ""
    merged["year"] = _first_truthy(a.get("year"), b.get("year"))
    merged["journal_name"] = _first_truthy(a.get("journal_name"), b.get("journal_name"))
    merged["country"] = _first_truthy(a.get("country"), b.get("country"))
    merged["citation_count"] = max(
        int(a.get("citation_count") or 0), int(b.get("citation_count") or 0)
    )
    merged["doi"] = _first_truthy(a.get("doi"), b.get("doi"))
    merged["paper_id"] = _first_truthy(a.get("paper_id"), b.get("paper_id"))
    # OpenAlex가 기여했으면 country_lookup_done=True → extraction_agent의 OpenAlex 재조회 스킵
    if a.get("country_lookup_done") or b.get("country_lookup_done"):
        merged["country_lookup_done"] = True
    return merged


def merge_papers(*paper_lists: list[dict]) -> list[dict]:
    """N개 검색 소스의 결과를 DOI(없으면 title) 기준 필드별 best-of로 병합.

    dedup 키가 없는(DOI·title 모두 없는) 논문은 그대로 유지한다.
    결과는 citation_count 내림차순 정렬 — downstream 절단 시 인용수 높은 논문이 생존한다.
    호출 순서가 first-truthy 필드(country, title, doi)에 영향: 먼저 들어온 값이 우선.
    """
    merged: dict[str, dict] = {}
    no_key: list[dict] = []
    for papers in paper_lists:
        for paper in papers:
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
    logger.info(
        "[S2] keywords=%r returned=%d after_abstract_filter=%d",
        keywords, len(data), len(papers),
    )
    return papers


async def search_combined(
    keywords: str,
    *,
    s2_semaphore: asyncio.Semaphore,
    openalex_semaphore: asyncio.Semaphore,
    kci_semaphore: asyncio.Semaphore,
    client: httpx.AsyncClient,
    max_results: int | None = None,
) -> list[dict]:
    """S2 + OpenAlex + KCI 동시 검색 후 best-of 머지. 그레이스풀 다운.

    1~2개 소스가 실패하면 warning 후 나머지로 진행. 셋 다 실패 시 RuntimeError.
    """
    from app.agents import kci_agent
    s2_result, oa_result, kci_result = await asyncio.gather(
        search_papers_for_indicator(keywords, max_results, s2_semaphore, client=client),
        openalex_agent.search_papers_for_indicator(
            keywords, max_results, openalex_semaphore, client=client),
        kci_agent.search_papers_for_indicator(
            keywords, max_results, kci_semaphore, client=client),
        return_exceptions=True,
    )
    names = ("S2", "OpenAlex", "KCI")
    results = (s2_result, oa_result, kci_result)
    failed = [n for n, r in zip(names, results) if isinstance(r, BaseException)]
    if len(failed) == 3:
        raise RuntimeError(
            f"all sources failed for {keywords!r}: "
            f"S2={s2_result}, OpenAlex={oa_result}, KCI={kci_result}"
        )
    for name, r in zip(names, results):
        if isinstance(r, BaseException):
            logger.warning(
                "combined search: %s failed for %r (%s), using remaining sources",
                name, keywords, r,
            )
    papers_lists = [[] if isinstance(r, BaseException) else r for r in results]
    return merge_papers(*papers_lists)


async def search_all_sources(
    keywords: str,
    source: str,
    max_results: int | None = None,
    *,
    semaphores: dict[str, asyncio.Semaphore],
    client: httpx.AsyncClient,
) -> list[dict]:
    if source == "scopus":
        return await scopus_agent.search_papers_for_indicator(
            keywords, max_results, semaphores["scopus"], client=client)
    if source == "combined":
        return await search_combined(
            keywords,
            s2_semaphore=semaphores["semantic_scholar"],
            openalex_semaphore=semaphores["openalex"],
            kci_semaphore=semaphores["kci"],
            client=client,
            max_results=max_results,
        )
    raise ValueError(f"unknown search_source: {source!r}")
