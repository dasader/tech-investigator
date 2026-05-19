import asyncio
import logging
import xml.etree.ElementTree as ET
import httpx

from app.config import settings
from app.agents._http_retry import get_text_with_retry

logger = logging.getLogger(__name__)

KCI_API_URL = "https://open.kci.go.kr/po/openapi/openApiSearch.kci"

# articleDetail.kci N+1 호출 throttle (process-wide, indicator 외 동시성과 별도).
_DETAIL_SEM = asyncio.Semaphore(5)


def _pick_by_lang(records: list[ET.Element], preferred: str = "eng") -> str:
    """`<element language="eng">` 우선, 없으면 첫 번째 비어있지 않은 텍스트, 둘 다 없으면 빈 문자열."""
    fallback = ""
    for r in records:
        text = (r.text or "").strip()
        if not text:
            continue
        if r.get("language") == preferred:
            return text
        if not fallback:
            fallback = text
    return fallback


def _find_doi(record: ET.Element) -> str | None:
    for aid in record.findall("article-id"):
        if aid.get("pubidtype") == "doi" and (aid.text or "").strip():
            return aid.text.strip()
    return None


def _find_kci_id(record: ET.Element) -> str | None:
    for aid in record.findall("article-id"):
        if aid.get("pubidtype") == "kciid" and (aid.text or "").strip():
            return aid.text.strip()
    return None


def _parse_search_xml(xml_text: str) -> list[dict]:
    """articleSearch.kci XML → 메타데이터 dict 목록 (abstract 제외)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise RuntimeError(f"KCI articleSearch XML parse error: {e}") from e

    metas: list[dict] = []
    for record in root.iter("record"):
        kci_id = _find_kci_id(record)
        if not kci_id:
            continue
        title_group = record.find("title-group")
        titles = list(title_group.findall("article-title")) if title_group is not None else []
        journals = list(record.findall("journal-name"))
        year_el = record.find("pub-year")
        citation_el = record.find("citation-count")
        try:
            year = int((year_el.text or "").strip()) if year_el is not None and year_el.text else None
        except ValueError:
            year = None
        try:
            citation_count = int((citation_el.text or "").strip()) if citation_el is not None and citation_el.text else 0
        except ValueError:
            citation_count = 0

        metas.append({
            "paper_id": kci_id,
            "title": _pick_by_lang(titles, "eng"),
            "year": year,
            "citation_count": citation_count,
            "doi": _find_doi(record),
            "journal_name": _pick_by_lang(journals, "eng") or None,
        })
    return metas


def _parse_detail_xml(xml_text: str) -> dict:
    """articleDetail.kci XML → {'abstract': '...'} (영문 우선, 한글 fallback)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise RuntimeError(f"KCI articleDetail XML parse error: {e}") from e

    abstracts: list[ET.Element] = list(root.iter("abstract"))
    return {"abstract": _pick_by_lang(abstracts, "eng")}


async def _fetch_search(
    keywords: str, max_results: int, *, client: httpx.AsyncClient,
) -> list[dict]:
    params = {
        "apiCode": "articleSearch",
        "key": settings.kci_api_key,
        "searchQuery": keywords,
        "displayCount": min(max_results, 100),
        "page": 1,
    }
    xml_text = await get_text_with_retry(
        KCI_API_URL,
        client=client,
        params=params,
        service_name="KCI",
        context=keywords,
        inter_attempt_sleep=0.2,
    )
    return _parse_search_xml(xml_text)


async def _fetch_detail_throttled(
    kci_id: str, *, client: httpx.AsyncClient,
) -> dict | None:
    """detail 호출은 _DETAIL_SEM으로 throttle. 실패하면 None 반환(상위에서 drop)."""
    async with _DETAIL_SEM:
        try:
            params = {
                "apiCode": "articleDetail",
                "key": settings.kci_api_key,
                "id": kci_id,
            }
            xml_text = await get_text_with_retry(
                KCI_API_URL,
                client=client,
                params=params,
                service_name="KCI",
                context=f"detail:{kci_id}",
                inter_attempt_sleep=0.2,
            )
            return _parse_detail_xml(xml_text)
        except Exception as e:
            logger.warning("KCI articleDetail failed for %s: %s", kci_id, e)
            return None


async def search_papers_for_indicator(
    keywords: str,
    max_results: int | None = None,
    semaphore: asyncio.Semaphore | None = None,
    *,
    client: httpx.AsyncClient,
) -> list[dict]:
    if not settings.kci_api_key:
        return []

    from app.config import settings as _s  # late import for monkeypatch in tests
    max_results = max_results if max_results is not None else _s.max_papers_per_indicator

    sem = semaphore or asyncio.Semaphore(1)
    async with sem:
        metas = await _fetch_search(keywords, max_results, client=client)

    if not metas:
        logger.info("[KCI] keywords=%r returned=0", keywords)
        return []

    details = await asyncio.gather(
        *[_fetch_detail_throttled(m["paper_id"], client=client) for m in metas],
        return_exceptions=False,
    )

    papers: list[dict] = []
    for meta, detail in zip(metas, details):
        if detail is None:
            continue
        abstract = detail.get("abstract") or ""
        if not abstract:
            continue
        papers.append({
            **meta,
            "abstract": abstract,
            "country": "South Korea",
            "country_lookup_done": True,
        })

    logger.info(
        "[KCI] keywords=%r returned=%d after_detail_fetch=%d after_abstract_filter=%d",
        keywords, len(metas), sum(1 for d in details if d is not None), len(papers),
    )
    return papers
