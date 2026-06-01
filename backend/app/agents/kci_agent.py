import asyncio
import logging
import xml.etree.ElementTree as ET
import httpx

from app.config import settings
from app.agents._http_retry import get_text_with_retry
from app.agents._doi import strip_doi_prefix

logger = logging.getLogger(__name__)

KCI_API_URL = "https://open.kci.go.kr/po/openapi/openApiSearch.kci"


def _pick_by_lang(elements: list[ET.Element], preferred: str = "english") -> str:
    """`lang="<preferred>"` 우선, 없으면 첫 번째 비어있지 않은 텍스트, 둘 다 없으면 빈 문자열.

    KCI는 lang 값으로 "english", "original"(보통 한국어), "foreign"을 사용한다.
    """
    fallback = ""
    for el in elements:
        text = (el.text or "").strip()
        if not text:
            continue
        if el.get("lang") == preferred:
            return text
        if not fallback:
            fallback = text
    return fallback


def _find_doi(article_info: ET.Element) -> str | None:
    doi_el = article_info.find("doi")
    if doi_el is None:
        return None
    return strip_doi_prefix(doi_el.text)


def _int_or(text: str | None, default: int | None) -> int | None:
    if not text:
        return default
    try:
        return int(text.strip())
    except ValueError:
        return default


def _text_or_none(el: ET.Element | None) -> str | None:
    if el is None or el.text is None:
        return None
    stripped = el.text.strip()
    return stripped or None


def _parse_search_xml(xml_text: str) -> list[dict]:
    """KCI articleSearch.kci XML → paper dict 목록.

    실제 응답 구조:
        <MetaData>
          <outputData>
            <record>
              <journalInfo>
                <journal-name>...</journal-name>
                <pub-year>2024</pub-year>
              </journalInfo>
              <articleInfo article-id="ART...">
                <title-group>
                  <article-title lang="original">...</article-title>
                  <article-title lang="english">...</article-title>
                </title-group>
                <abstract-group>
                  <abstract lang="original">...</abstract>
                  <abstract lang="english">...</abstract>
                </abstract-group>
                <doi>http://dx.doi.org/...</doi>
                <citation-count kci="N" wos="M">N</citation-count>
              </articleInfo>
            </record>
            ...
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise RuntimeError(f"KCI articleSearch XML parse error: {e}") from e

    papers: list[dict] = []
    for record in root.iter("record"):
        article = record.find("articleInfo")
        if article is None:
            continue
        article_id = article.get("article-id")
        if not article_id:
            continue

        titles = list(article.findall("title-group/article-title"))
        abstracts = list(article.findall("abstract-group/abstract"))

        journal_info = record.find("journalInfo")
        if journal_info is not None:
            journal_name = _text_or_none(journal_info.find("journal-name"))
            pub_year_el = journal_info.find("pub-year")
            year = _int_or(pub_year_el.text if pub_year_el is not None else None, None)
        else:
            journal_name = None
            year = None

        citation_el = article.find("citation-count")
        citation_count = _int_or(citation_el.text if citation_el is not None else None, 0) or 0

        papers.append({
            "paper_id": article_id,
            "title": _pick_by_lang(titles, "english"),
            "abstract": _pick_by_lang(abstracts, "english"),
            "year": year,
            "citation_count": citation_count,
            "doi": _find_doi(article),
            "journal_name": journal_name,
        })
    return papers


async def _fetch_search(
    keywords: str, max_results: int, *, client: httpx.AsyncClient,
) -> list[dict]:
    """단일 articleSearch.kci 호출 — 응답에 메타데이터·DOI·abstract 모두 포함."""
    params = {
        "apiCode": "articleSearch",
        "key": settings.kci_api_key,
        "keyword": keywords,
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


async def search_papers_for_indicator(
    keywords: str,
    max_results: int | None = None,
    semaphore: asyncio.Semaphore | None = None,
    *,
    client: httpx.AsyncClient,
) -> list[dict]:
    """KCI Open API로 keyword 검색해 paper dict 리스트 반환.

    `settings.kci_api_key`가 비어있으면 즉시 빈 리스트 (graceful no-op).
    abstract(한/영 어느 쪽이든)가 비어있는 paper는 drop.
    country는 항상 "South Korea"로 set, country_lookup_done=True로 extraction_agent의
    OpenAlex 재조회를 차단.
    """
    if not settings.kci_api_key:
        return []

    max_results = max_results if max_results is not None else settings.max_papers_per_indicator

    sem = semaphore or asyncio.Semaphore(1)
    async with sem:
        raw = await _fetch_search(keywords, max_results, client=client)

    papers: list[dict] = []
    for meta in raw:
        if not meta.get("abstract"):
            continue
        papers.append({
            **meta,
            "country": "South Korea",
            "country_lookup_done": True,
        })

    logger.info(
        "[KCI] keywords=%r returned=%d after_abstract_filter=%d",
        keywords, len(raw), len(papers),
    )
    return papers
