# KCI Open API Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `combined` 검색 모드의 세 번째 소스로 KCI(한국학술지 인용색인) Open API를 추가해 한국 연구 커버리지를 보강한다.

**Architecture:** `kci_agent.py` 신규 모듈이 articleSearch.kci → articleDetail.kci N+1 호출을 캡슐화하여 S2/OpenAlex와 동일한 시그니처를 제공한다. `search_combined`을 3-way `asyncio.gather`로 확장하고 `merge_papers`를 `*paper_lists` 가변 인자로 일반화한다. KCI key 미설정 시 빈 리스트를 즉시 반환해 기존 환경 호환성 유지.

**Tech Stack:** Python 3.12 / FastAPI / httpx / xml.etree.ElementTree (stdlib) / pytest-asyncio.

**Spec:** [`docs/superpowers/specs/2026-05-19-kci-integration-design.md`](../specs/2026-05-19-kci-integration-design.md)

---

## File Structure

**Create:**
- `backend/app/agents/kci_agent.py` — KCI 검색 + abstract 보강 캡슐화. 외부 인터페이스는 S2/OpenAlex agent와 동일.
- `backend/tests/test_kci_agent.py` — 5개 unit 테스트.

**Modify:**
- `backend/app/config.py` — `kci_api_key` 추가.
- `backend/app/agents/_http_retry.py` — XML 응답을 위한 `get_text_with_retry()` 추가 (기존 `get_with_retry()`는 JSON 전용).
- `backend/app/agents/search_agent.py` — `merge_papers` 가변 인자, `search_combined` 3-way 확장.
- `backend/app/agents/pipeline.py` — `SOURCE_PLAN["combined"]`에 `"kci": 3` 추가.
- `backend/app/utils.py` — `get_engine_label`의 combined 라벨에 "+ KCI".
- `backend/tests/test_utils.py` — engine label 기댓값 갱신.
- `backend/tests/test_search_agent.py` — 3-way merge / KCI 실패 / kci_semaphore 전달 테스트 추가.
- `frontend/src/pages/InputPage.tsx` — combined 라벨 텍스트.
- `.env.example`, `backend/.env.example` — `KCI_API_KEY=` 1줄.
- `CLAUDE.md` (루트) — combined 설명 + 환경변수.

**No changes:** DB schema, migrations, API 응답 형식, `extraction_agent.py`, `validation_agent.py`, `synthesis_agent.py`, frontend 외 모든 UI/타입.

---

## Task 1: Settings에 `kci_api_key` 추가

**Files:**
- Modify: `backend/app/config.py:7-9` (외부 API key들 옆)
- Modify: `.env.example` (외부 API 섹션)
- Modify: `backend/.env.example` (외부 API 섹션)

- [ ] **Step 1: `Settings`에 필드 추가**

`backend/app/config.py`의 9번 줄 `openalex_api_key: str = ""` 뒤에 추가:

```python
    kci_api_key: str = ""
```

- [ ] **Step 2: `.env.example`에 1줄 추가**

`OPENALEX_API_KEY=your_openalex_api_key` 줄 뒤에 추가:

```
KCI_API_KEY=your_kci_open_api_key
```

- [ ] **Step 3: `backend/.env.example`에도 동일하게 추가**

위와 동일.

- [ ] **Step 4: 설정 로드 확인**

Run: `docker compose exec api python -c "from app.config import settings; print(repr(settings.kci_api_key))"`
Expected: `''` (빈 문자열, .env 미설정 상태)

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py .env.example backend/.env.example
git commit -m "feat(config): add KCI_API_KEY setting"
```

---

## Task 2: `_http_retry`에 `get_text_with_retry` 추가

KCI는 XML 응답이므로 `response.json()`이 아닌 `response.text`를 반환하는 sibling 헬퍼가 필요하다.

**Files:**
- Modify: `backend/app/agents/_http_retry.py`
- Test: `backend/tests/test_http_retry.py` (없으면 신규)

- [ ] **Step 1: 테스트 파일 확인 및 생성**

```bash
ls backend/tests/test_http_retry.py 2>/dev/null || echo "no existing file"
```

없으면 신규 생성. 있으면 끝에 테스트 추가.

- [ ] **Step 2: 실패하는 테스트 작성**

`backend/tests/test_http_retry.py` (신규 또는 추가):

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
import httpx
from app.agents._http_retry import get_text_with_retry

pytestmark = pytest.mark.no_db


@pytest.mark.asyncio
async def test_get_text_returns_response_text(mock_httpx_client):
    client = AsyncMock(spec=httpx.AsyncClient)
    response = MagicMock()
    response.status_code = 200
    response.text = "<resultList><record>hello</record></resultList>"
    response.raise_for_status = MagicMock()
    client.get.return_value = response

    text = await get_text_with_retry(
        "https://example.invalid/api",
        client=client,
        service_name="TestService",
        context="kw",
    )
    assert text.startswith("<resultList>")
    assert "hello" in text


@pytest.mark.asyncio
async def test_get_text_raises_runtime_on_http_status_error():
    client = AsyncMock(spec=httpx.AsyncClient)
    err = httpx.HTTPStatusError(
        "500", request=MagicMock(),
        response=MagicMock(status_code=500),
    )
    client.get.side_effect = err

    with pytest.raises(RuntimeError, match="TestService API error 500"):
        await get_text_with_retry(
            "https://example.invalid/api",
            client=client,
            service_name="TestService",
            context="kw",
        )
```

- [ ] **Step 3: 테스트 실행 (실패 확인)**

Run: `docker compose exec api pytest backend/tests/test_http_retry.py -v`
Expected: FAIL — `ImportError: cannot import name 'get_text_with_retry'`.

- [ ] **Step 4: 구현**

`backend/app/agents/_http_retry.py` 끝에 추가:

```python
async def get_text_with_retry(
    url: str,
    *,
    client: httpx.AsyncClient,
    params: dict | None = None,
    headers: dict | None = None,
    service_name: str,
    context: str = "",
    max_attempts: int = 3,
    timeout: float = 30.0,
    inter_attempt_sleep: float = 0.0,
    retry_status_codes: tuple[int, ...] = (429,),
) -> str:
    """`get_with_retry`의 text 버전. XML 응답 등 비-JSON 서비스용."""
    for attempt in range(max_attempts):
        try:
            response = await client.get(url, params=params, headers=headers, timeout=timeout)
            if response.status_code in retry_status_codes:
                await asyncio.sleep(10 * (attempt + 1))
                continue
            response.raise_for_status()
            return response.text
        except httpx.TimeoutException as e:
            raise RuntimeError(f"{service_name} API timeout for: {context}") from e
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"{service_name} API error {e.response.status_code}: {context}"
            ) from e
        except httpx.RequestError as e:
            raise RuntimeError(f"{service_name} network error: {context}") from e
        finally:
            if inter_attempt_sleep:
                await asyncio.sleep(inter_attempt_sleep)
    raise RuntimeError(f"{service_name} API error 429: {context}")
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `docker compose exec api pytest backend/tests/test_http_retry.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/agents/_http_retry.py backend/tests/test_http_retry.py
git commit -m "feat(http): add get_text_with_retry for XML responses"
```

---

## Task 3: `kci_agent` — 모듈 골격과 "key 없으면 skip" 동작

`settings.kci_api_key`가 빈 문자열이면 HTTP 호출 없이 즉시 `[]`를 반환한다. 기존 `.env`에 KCI 키 없는 환경 호환성을 유지하기 위함.

**Files:**
- Create: `backend/app/agents/kci_agent.py`
- Create: `backend/tests/test_kci_agent.py`

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/test_kci_agent.py` 신규:

```python
import asyncio
import pytest
from unittest.mock import AsyncMock
import httpx

from app.agents import kci_agent

pytestmark = pytest.mark.no_db


@pytest.mark.asyncio
async def test_kci_search_skips_when_no_api_key(monkeypatch):
    monkeypatch.setattr("app.agents.kci_agent.settings.kci_api_key", "")
    client = AsyncMock(spec=httpx.AsyncClient)

    result = await kci_agent.search_papers_for_indicator(
        "HBM bandwidth", max_results=10, client=client,
    )

    assert result == []
    client.get.assert_not_called()
```

- [ ] **Step 2: 테스트 실행 (실패)**

Run: `docker compose exec api pytest backend/tests/test_kci_agent.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agents.kci_agent'`.

- [ ] **Step 3: 최소 구현**

`backend/app/agents/kci_agent.py` 신규:

```python
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


async def search_papers_for_indicator(
    keywords: str,
    max_results: int | None = None,
    semaphore: asyncio.Semaphore | None = None,
    *,
    client: httpx.AsyncClient,
) -> list[dict]:
    if not settings.kci_api_key:
        return []
    # 이후 단계에서 채워질 구현
    return []
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `docker compose exec api pytest backend/tests/test_kci_agent.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/kci_agent.py backend/tests/test_kci_agent.py
git commit -m "feat(kci): scaffold agent with no-key skip behavior"
```

---

## Task 4: `kci_agent` — articleSearch + articleDetail happy path

영문 abstract가 있는 정상 응답에서 paper dict가 올바르게 정규화되는지 검증한다. articleSearch.kci 응답에서 `<record>` 목록을 파싱하고, 각 article에 대해 articleDetail.kci로 abstract를 보강한다.

> **구현 시 확인 필요:** KCI XML element 이름(`<article-id pubidtype="kciid">`, `<abstract language="eng">` 등)은 사용자가 발급받은 KCI Open API 문서로 확정. 본 task의 element 이름은 KISTI 표준 KCI Open API 스키마 기준. 다르다면 `_parse_search_xml` / `_parse_detail_xml` 두 함수만 조정.

**Files:**
- Modify: `backend/app/agents/kci_agent.py`
- Modify: `backend/tests/test_kci_agent.py`

- [ ] **Step 1: Happy path 테스트 추가**

`backend/tests/test_kci_agent.py` 끝에 추가:

```python
MOCK_SEARCH_XML = """<?xml version="1.0" encoding="UTF-8"?>
<resultList>
  <outputData>
    <record>
      <article-id pubidtype="kciid">ART001</article-id>
      <article-id pubidtype="doi">10.1234/foo.2024.001</article-id>
      <title-group>
        <article-title language="kor">한국어 제목</article-title>
        <article-title language="eng">High Bandwidth Memory Stack Yield</article-title>
      </title-group>
      <pub-year>2024</pub-year>
      <journal-name language="eng">Journal of Korean Semiconductor</journal-name>
      <journal-name language="kor">한국반도체학회지</journal-name>
      <citation-count>17</citation-count>
    </record>
  </outputData>
</resultList>"""

MOCK_DETAIL_XML = """<?xml version="1.0" encoding="UTF-8"?>
<resultList>
  <outputData>
    <record>
      <abstract-group>
        <abstract language="kor">한국어 초록 내용 1.2 마이크로미터.</abstract>
        <abstract language="eng">We report HBM3E stacking achieving 1.2 TB/s bandwidth.</abstract>
      </abstract-group>
    </record>
  </outputData>
</resultList>"""


def _make_xml_client(*, search_xml: str, detail_xml: str):
    """KCI 호출을 구분 — apiCode 파라미터로 search/detail mock 응답을 분기."""
    from unittest.mock import AsyncMock, MagicMock
    client = AsyncMock(spec=httpx.AsyncClient)

    async def fake_get(url, params=None, headers=None, timeout=None):
        api_code = (params or {}).get("apiCode")
        response = MagicMock()
        response.status_code = 200
        response.raise_for_status = MagicMock()
        response.text = detail_xml if api_code == "articleDetail" else search_xml
        return response

    client.get.side_effect = fake_get
    return client


@pytest.mark.asyncio
async def test_kci_search_returns_papers(monkeypatch):
    monkeypatch.setattr("app.agents.kci_agent.settings.kci_api_key", "test-key")
    client = _make_xml_client(search_xml=MOCK_SEARCH_XML, detail_xml=MOCK_DETAIL_XML)

    results = await kci_agent.search_papers_for_indicator(
        "HBM bandwidth", max_results=5, client=client,
    )

    assert len(results) == 1
    paper = results[0]
    assert paper["paper_id"] == "ART001"
    assert paper["doi"] == "10.1234/foo.2024.001"
    assert paper["title"] == "High Bandwidth Memory Stack Yield"  # 영문 우선
    assert paper["abstract"].startswith("We report HBM3E")  # 영문 우선
    assert paper["year"] == 2024
    assert paper["citation_count"] == 17
    assert paper["journal_name"] == "Journal of Korean Semiconductor"
    assert paper["country"] == "South Korea"
    assert paper["country_lookup_done"] is True
```

- [ ] **Step 2: 테스트 실행 (실패)**

Run: `docker compose exec api pytest backend/tests/test_kci_agent.py::test_kci_search_returns_papers -v`
Expected: FAIL — `assert 0 == 1` (현재 빈 리스트만 반환).

- [ ] **Step 3: 구현 — XML 파싱 헬퍼와 메인 흐름**

`backend/app/agents/kci_agent.py`를 다음 내용으로 **교체**:

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `docker compose exec api pytest backend/tests/test_kci_agent.py -v`
Expected: 2 passed (skip + happy path).

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/kci_agent.py backend/tests/test_kci_agent.py
git commit -m "feat(kci): articleSearch+articleDetail with English abstract preference"
```

---

## Task 5: `kci_agent` — 한글 abstract fallback

영문 abstract가 비어 있으면 한글 abstract를 사용한다. `_pick_by_lang`이 이미 이 동작을 구현하므로 테스트만 추가해 동작을 잠근다.

**Files:**
- Modify: `backend/tests/test_kci_agent.py`

- [ ] **Step 1: 테스트 추가**

`backend/tests/test_kci_agent.py` 끝에 추가:

```python
MOCK_DETAIL_KO_ONLY = """<?xml version="1.0" encoding="UTF-8"?>
<resultList>
  <outputData>
    <record>
      <abstract-group>
        <abstract language="kor">한국어 초록입니다. 대역폭 1.2 TB/s를 달성하였다.</abstract>
        <abstract language="eng"></abstract>
      </abstract-group>
    </record>
  </outputData>
</resultList>"""


@pytest.mark.asyncio
async def test_kci_search_korean_abstract_fallback(monkeypatch):
    monkeypatch.setattr("app.agents.kci_agent.settings.kci_api_key", "test-key")
    client = _make_xml_client(search_xml=MOCK_SEARCH_XML, detail_xml=MOCK_DETAIL_KO_ONLY)

    results = await kci_agent.search_papers_for_indicator(
        "HBM bandwidth", max_results=5, client=client,
    )

    assert len(results) == 1
    assert results[0]["abstract"].startswith("한국어 초록")
```

- [ ] **Step 2: 테스트 실행 (통과 확인)**

Run: `docker compose exec api pytest backend/tests/test_kci_agent.py::test_kci_search_korean_abstract_fallback -v`
Expected: PASS (구현 단계에서 이미 fallback 로직이 들어가 있음).

> 만약 실패한다면 `_pick_by_lang`의 fallback 분기 또는 `<abstract language="eng"></abstract>` 빈 텍스트 케이스 처리가 빠진 것. 해당 함수만 수정.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_kci_agent.py
git commit -m "test(kci): pin Korean abstract fallback behavior"
```

---

## Task 6: `kci_agent` — abstract 둘 다 빈 paper drop

한글/영문 abstract 모두 빈 경우 해당 paper는 결과에서 제외한다 (S2/OpenAlex 동일 정책).

**Files:**
- Modify: `backend/tests/test_kci_agent.py`

- [ ] **Step 1: 테스트 추가**

`backend/tests/test_kci_agent.py` 끝에 추가:

```python
MOCK_DETAIL_EMPTY = """<?xml version="1.0" encoding="UTF-8"?>
<resultList>
  <outputData>
    <record>
      <abstract-group>
        <abstract language="kor"></abstract>
        <abstract language="eng"></abstract>
      </abstract-group>
    </record>
  </outputData>
</resultList>"""


@pytest.mark.asyncio
async def test_kci_search_filters_no_abstract(monkeypatch):
    monkeypatch.setattr("app.agents.kci_agent.settings.kci_api_key", "test-key")
    client = _make_xml_client(search_xml=MOCK_SEARCH_XML, detail_xml=MOCK_DETAIL_EMPTY)

    results = await kci_agent.search_papers_for_indicator(
        "HBM bandwidth", max_results=5, client=client,
    )

    assert results == []
```

- [ ] **Step 2: 테스트 실행 (통과 확인)**

Run: `docker compose exec api pytest backend/tests/test_kci_agent.py::test_kci_search_filters_no_abstract -v`
Expected: PASS (Task 4의 `if not abstract: continue` 가드가 처리).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_kci_agent.py
git commit -m "test(kci): pin no-abstract paper filter"
```

---

## Task 7: `kci_agent` — articleDetail 일부 실패 시 graceful drop

articleDetail 중 일부 호출이 500 등으로 실패해도 나머지 paper는 정상 반환되어야 한다.

**Files:**
- Modify: `backend/tests/test_kci_agent.py`

- [ ] **Step 1: 테스트 추가**

`backend/tests/test_kci_agent.py` 끝에 추가:

```python
MOCK_SEARCH_XML_2RECORDS = """<?xml version="1.0" encoding="UTF-8"?>
<resultList>
  <outputData>
    <record>
      <article-id pubidtype="kciid">ART001</article-id>
      <article-id pubidtype="doi">10.1234/foo.2024.001</article-id>
      <title-group><article-title language="eng">Paper One</article-title></title-group>
      <pub-year>2024</pub-year><citation-count>10</citation-count>
    </record>
    <record>
      <article-id pubidtype="kciid">ART002</article-id>
      <title-group><article-title language="eng">Paper Two</article-title></title-group>
      <pub-year>2024</pub-year><citation-count>5</citation-count>
    </record>
  </outputData>
</resultList>"""


@pytest.mark.asyncio
async def test_kci_detail_partial_failure(monkeypatch, caplog):
    from unittest.mock import AsyncMock, MagicMock
    monkeypatch.setattr("app.agents.kci_agent.settings.kci_api_key", "test-key")
    client = AsyncMock(spec=httpx.AsyncClient)

    async def fake_get(url, params=None, headers=None, timeout=None):
        api_code = (params or {}).get("apiCode")
        response = MagicMock()
        response.raise_for_status = MagicMock()
        if api_code == "articleSearch":
            response.status_code = 200
            response.text = MOCK_SEARCH_XML_2RECORDS
            return response
        # articleDetail: ART001 성공, ART002 실패(500)
        if params.get("id") == "ART001":
            response.status_code = 200
            response.text = MOCK_DETAIL_XML
            return response
        err_response = MagicMock(status_code=500)
        raise httpx.HTTPStatusError("500", request=MagicMock(), response=err_response)

    client.get.side_effect = fake_get

    with caplog.at_level("WARNING", logger="app.agents.kci_agent"):
        results = await kci_agent.search_papers_for_indicator(
            "HBM bandwidth", max_results=5, client=client,
        )

    assert len(results) == 1
    assert results[0]["paper_id"] == "ART001"
    assert any("articleDetail failed" in r.message for r in caplog.records)
```

- [ ] **Step 2: 테스트 실행 (통과 확인)**

Run: `docker compose exec api pytest backend/tests/test_kci_agent.py::test_kci_detail_partial_failure -v`
Expected: PASS (`_fetch_detail_throttled`의 try/except가 None 반환 → 상위 `continue`).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_kci_agent.py
git commit -m "test(kci): pin articleDetail partial failure resilience"
```

---

## Task 8: `merge_papers` 가변 인자 일반화

`merge_papers(s2, oa)` → `merge_papers(*paper_lists)`로 변경. 호출처는 다음 task에서 갱신.

**Files:**
- Modify: `backend/app/agents/search_agent.py`
- Modify: `backend/tests/test_search_agent.py`

- [ ] **Step 1: 새 테스트 추가 (3-way merge)**

`backend/tests/test_search_agent.py`의 어딘가에 추가 (기존 merge 테스트와 인접한 곳):

```python
def test_merge_papers_3way_dedup_by_doi():
    from app.agents.search_agent import merge_papers
    s2 = [{"doi": "10.1/x", "title": "Paper X", "abstract": "short", "citation_count": 5, "country": None}]
    oa = [{"doi": "10.1/x", "title": "Paper X", "abstract": "much longer abstract content", "citation_count": 8, "country": "USA"}]
    kci = [
        {"doi": "10.1/x", "title": "Paper X", "abstract": "", "citation_count": 0, "country": "South Korea", "country_lookup_done": True},
        {"doi": "10.2/y", "title": "Paper Y", "abstract": "ko-only paper", "citation_count": 2, "country": "South Korea"},
    ]

    merged = merge_papers(s2, oa, kci)

    by_doi = {p["doi"]: p for p in merged}
    # 중복 DOI 1건 + KCI-only 1건 = 2건
    assert len(merged) == 2
    # OA country가 우선, KCI default가 fallback
    assert by_doi["10.1/x"]["country"] == "USA"
    assert by_doi["10.2/y"]["country"] == "South Korea"
    # 가장 긴 abstract 유지
    assert by_doi["10.1/x"]["abstract"] == "much longer abstract content"
    # citation_count는 max
    assert by_doi["10.1/x"]["citation_count"] == 8
```

- [ ] **Step 2: 테스트 실행 (실패)**

Run: `docker compose exec api pytest backend/tests/test_search_agent.py::test_merge_papers_3way_dedup_by_doi -v`
Expected: FAIL — `TypeError: merge_papers() takes 2 positional arguments but 3 were given`.

- [ ] **Step 3: 시그니처 변경**

`backend/app/agents/search_agent.py:56-74`의 `merge_papers`를 다음으로 교체:

```python
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
```

- [ ] **Step 4: 기존 호출처 호환 확인**

`backend/app/agents/search_agent.py:169`의 `merge_papers(s2_papers, oa_papers)` 호출은 `*args` 시그니처와 그대로 호환됨 (positional 2개 → 길이 2 paper_lists). 코드 수정 불필요.

- [ ] **Step 5: 새 테스트 + 전체 search_agent 테스트 통과 확인**

Run: `docker compose exec api pytest backend/tests/test_search_agent.py -v`
Expected: 모든 기존 테스트 + 신규 1개 통과.

- [ ] **Step 6: Commit**

```bash
git add backend/app/agents/search_agent.py backend/tests/test_search_agent.py
git commit -m "refactor(search): generalize merge_papers to variadic *paper_lists"
```

---

## Task 9: `search_combined` 3-way 확장

`search_combined`에 `kci_semaphore` 추가, `asyncio.gather`에 KCI 호출 추가, 3-way graceful degrade.

**Files:**
- Modify: `backend/app/agents/search_agent.py`
- Modify: `backend/tests/test_search_agent.py`

- [ ] **Step 1: 3-way 정상 동작 + KCI 단독 실패 시 진행 테스트 추가**

`backend/tests/test_search_agent.py`에 추가:

```python
@pytest.mark.asyncio
async def test_search_combined_kci_failure_continues(mock_httpx_client, monkeypatch):
    from app.agents import search_agent
    from app.agents import openalex_agent, kci_agent

    async def fake_s2(*a, **kw):
        return [{"doi": "10.1/a", "title": "A", "abstract": "x", "year": 2024, "citation_count": 3, "paper_id": "S1"}]

    async def fake_oa(*a, **kw):
        return [{"doi": "10.2/b", "title": "B", "abstract": "y", "year": 2024, "citation_count": 2, "paper_id": "O1", "country": "USA"}]

    async def fake_kci(*a, **kw):
        raise RuntimeError("KCI down")

    monkeypatch.setattr(search_agent, "search_papers_for_indicator", fake_s2)
    monkeypatch.setattr(openalex_agent, "search_papers_for_indicator", fake_oa)
    monkeypatch.setattr(kci_agent, "search_papers_for_indicator", fake_kci)

    client = mock_httpx_client()
    results = await search_agent.search_combined(
        "HBM",
        s2_semaphore=asyncio.Semaphore(1),
        openalex_semaphore=asyncio.Semaphore(10),
        kci_semaphore=asyncio.Semaphore(3),
        client=client,
    )
    dois = {p["doi"] for p in results}
    assert "10.1/a" in dois
    assert "10.2/b" in dois


@pytest.mark.asyncio
async def test_search_combined_3way_all_fail_raises(mock_httpx_client, monkeypatch):
    from app.agents import search_agent
    from app.agents import openalex_agent, kci_agent

    async def boom(*a, **kw):
        raise RuntimeError("down")

    monkeypatch.setattr(search_agent, "search_papers_for_indicator", boom)
    monkeypatch.setattr(openalex_agent, "search_papers_for_indicator", boom)
    monkeypatch.setattr(kci_agent, "search_papers_for_indicator", boom)

    client = mock_httpx_client()
    with pytest.raises(RuntimeError, match="all sources failed"):
        await search_agent.search_combined(
            "HBM",
            s2_semaphore=asyncio.Semaphore(1),
            openalex_semaphore=asyncio.Semaphore(10),
            kci_semaphore=asyncio.Semaphore(3),
            client=client,
        )
```

- [ ] **Step 2: 테스트 실행 (실패)**

Run: `docker compose exec api pytest backend/tests/test_search_agent.py::test_search_combined_kci_failure_continues -v`
Expected: FAIL — `TypeError: search_combined() got an unexpected keyword argument 'kci_semaphore'`.

- [ ] **Step 3: `search_combined` 갱신**

`backend/app/agents/search_agent.py:131-169`의 `search_combined`를 다음으로 교체:

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `docker compose exec api pytest backend/tests/test_search_agent.py -v`
Expected: 모든 기존 테스트 + 신규 2개 통과.

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/search_agent.py backend/tests/test_search_agent.py
git commit -m "feat(search): combined mode 3-way with KCI + graceful degrade"
```

---

## Task 10: `SOURCE_PLAN` 갱신 + `search_all_sources`가 `kci_semaphore` 전달

**Files:**
- Modify: `backend/app/agents/pipeline.py:33-36`
- Modify: `backend/app/agents/search_agent.py:172-191`
- Modify: `backend/tests/test_search_agent.py`

- [ ] **Step 1: 테스트 추가 — `search_all_sources` combined이 kci_semaphore를 전달하는지**

`backend/tests/test_search_agent.py`에 추가:

```python
@pytest.mark.asyncio
async def test_search_all_sources_combined_passes_kci_semaphore(mock_httpx_client, monkeypatch):
    """combined 호출 시 semaphores dict에 'kci' 키가 있고 search_combined로 전달되는지."""
    from app.agents import search_agent
    captured: dict = {}

    async def fake_search_combined(keywords, **kw):
        captured.update(kw)
        return []

    monkeypatch.setattr(search_agent, "search_combined", fake_search_combined)

    client = mock_httpx_client()
    await search_agent.search_all_sources(
        "HBM",
        source="combined",
        max_results=5,
        semaphores={
            "semantic_scholar": asyncio.Semaphore(1),
            "openalex": asyncio.Semaphore(10),
            "kci": asyncio.Semaphore(3),
        },
        client=client,
    )
    assert "kci_semaphore" in captured
    assert isinstance(captured["kci_semaphore"], asyncio.Semaphore)
```

- [ ] **Step 2: 테스트 실행 (실패)**

Run: `docker compose exec api pytest backend/tests/test_search_agent.py::test_search_all_sources_combined_passes_kci_semaphore -v`
Expected: FAIL — captured에 `kci_semaphore` 없음.

- [ ] **Step 3: `search_all_sources` 갱신**

`backend/app/agents/search_agent.py:172-191`의 함수에서 combined 분기를 다음으로 교체:

```python
    if source == "combined":
        return await search_combined(
            keywords,
            s2_semaphore=semaphores["semantic_scholar"],
            openalex_semaphore=semaphores["openalex"],
            kci_semaphore=semaphores["kci"],
            client=client,
            max_results=max_results,
        )
```

- [ ] **Step 4: `SOURCE_PLAN` 갱신**

`backend/app/agents/pipeline.py:33-36`을 교체:

```python
# search_source → {하위 소스: 동시성 한도}.
# 외부 API rate limit 기반: Semantic Scholar ~1 req/s, OpenAlex ~100 req/s, Scopus ~9 req/s, KCI 보수적.
# KCI는 indicator당 articleSearch+articleDetail N+1 호출이라 indicator-level 동시성을 3으로 보수 설정.
SOURCE_PLAN: dict[str, dict[str, int]] = {
    "combined": {"semantic_scholar": 1, "openalex": 10, "kci": 3},
    "scopus": {"scopus": 5},
}
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `docker compose exec api pytest backend/tests/test_search_agent.py backend/tests/test_pipeline.py -v`
Expected: 모든 테스트 통과.

- [ ] **Step 6: Commit**

```bash
git add backend/app/agents/pipeline.py backend/app/agents/search_agent.py backend/tests/test_search_agent.py
git commit -m "feat(pipeline): wire KCI into combined SOURCE_PLAN"
```

---

## Task 11: `get_engine_label` combined 라벨에 "+ KCI"

**Files:**
- Modify: `backend/app/utils.py:38-39`
- Modify: `backend/tests/test_utils.py`

- [ ] **Step 1: 테스트 기댓값 수정**

`backend/tests/test_utils.py:8` 및 17~18번 줄의 기댓값을 갱신:

```python
    assert get_engine_label("combined") == "OpenAlex + Semantic Scholar + KCI + Gemini"
```

그리고 17~18번 줄의 두 어설션(잔존 구값 처리):

```python
    assert get_engine_label("semantic_scholar") == "OpenAlex + Semantic Scholar + KCI + Gemini"
    assert get_engine_label("openalex") == "OpenAlex + Semantic Scholar + KCI + Gemini"
```

- [ ] **Step 2: 테스트 실행 (실패)**

Run: `docker compose exec api pytest backend/tests/test_utils.py -v`
Expected: FAIL — 현재 라벨은 `"OpenAlex + Semantic Scholar + Gemini"`.

- [ ] **Step 3: 함수 수정**

`backend/app/utils.py:35-39`을 교체:

```python
def get_engine_label(search_source: str) -> str:
    if search_source == "scopus":
        return "Scopus (Elsevier) + Gemini"
    # combined 및 기타 모든 값(마이그레이션 전 잔존 구값 포함) → 기본 라벨
    return "OpenAlex + Semantic Scholar + KCI + Gemini"
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `docker compose exec api pytest backend/tests/test_utils.py -v`
Expected: 모든 테스트 통과.

- [ ] **Step 5: Commit**

```bash
git add backend/app/utils.py backend/tests/test_utils.py
git commit -m "feat(utils): engine label includes KCI for combined mode"
```

---

## Task 12: 프론트엔드 라벨 텍스트 변경

**Files:**
- Modify: `frontend/src/pages/InputPage.tsx:8`, `:42`

- [ ] **Step 1: SOURCE_OPTIONS 라벨 변경**

`frontend/src/pages/InputPage.tsx:8`을 교체:

```tsx
  { value: "combined", label: "OpenAlex + Semantic Scholar + KCI" },
```

- [ ] **Step 2: sourceLabel fallback 문자열 변경**

`frontend/src/pages/InputPage.tsx:42`을 교체:

```tsx
    SOURCE_OPTIONS.find((o) => o.value === searchSource)?.label ?? "OpenAlex + Semantic Scholar + KCI";
```

- [ ] **Step 3: 컴파일 확인**

Run: `cd frontend && npm run build`
Expected: 빌드 성공 (타입 오류 없음).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/InputPage.tsx
git commit -m "feat(frontend): show KCI in combined source label"
```

---

## Task 13: 루트 `CLAUDE.md` 갱신

**Files:**
- Modify: `CLAUDE.md` (프로젝트 루트)

- [ ] **Step 1: 검색 소스 모드 섹션 갱신**

`CLAUDE.md`에서 `### 검색 소스 모드` 블록을 찾아 `combined` 항목을 다음으로 교체:

```markdown
- `combined` (기본): Semantic Scholar + OpenAlex + KCI 동시 검색, DOI/title 기반 best-of 머지. 동시성 `S2=1` / `OpenAlex=10` / `KCI=3`. KCI는 한국학술지 인용색인이며 `KCI_API_KEY` 미설정 시 자동 skip되어 S2+OpenAlex만 사용.
```

- [ ] **Step 2: 핵심 패턴 섹션에 1줄 추가**

`### 핵심 패턴` 블록 끝에 추가:

```markdown
**KCI 통합** — KCI Open API(`open.kci.go.kr`)는 XML 응답 + articleSearch/articleDetail 2단 호출. `kci_agent.py`가 N+1 호출을 내부에 캡슐화하고 paper dict는 S2/OpenAlex와 동일한 형식으로 반환. country는 항상 "South Korea" default + `country_lookup_done=True`로 set되어 `extraction_agent`의 OpenAlex 재조회를 차단.
```

- [ ] **Step 3: 변경 확인**

Run: `git diff CLAUDE.md`
Expected: combined 라인 1개 갱신 + 핵심 패턴 섹션 1단락 추가.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude.md): document KCI integration in combined mode"
```

---

## Task 14: 전체 회귀 테스트 + 통합 검증

마지막으로 전체 테스트 + 실제 KCI 키로 한 번 돌려본다(키 발급자에게만 해당).

- [ ] **Step 1: 전체 backend 테스트**

Run: `docker compose exec api pytest`
Expected: 모든 테스트 통과 (기존 + 신규 KCI 테스트).

- [ ] **Step 2: 프론트엔드 빌드**

Run: `cd frontend && npm run build`
Expected: 빌드 성공.

- [ ] **Step 3: 실제 KCI 키로 1회 통합 실행 (사용자 환경)**

`backend/.env`에 `KCI_API_KEY=<발급받은 키>` 설정 후:

```bash
docker compose up --build
```

브라우저로 `http://localhost:8098` 접속 → 작은 기술 분야(예: "HBM" 단일 키워드)로 시범 실행. 결과 페이지의 "분석 엔진"이 `"OpenAlex + Semantic Scholar + KCI + Gemini"`로 표시되는지, 보고서 데이터에 country="South Korea" 논문이 포함되는지 확인.

- [ ] **Step 4: 로그에서 KCI 호출 확인**

```bash
docker compose logs api | Select-String "\[KCI\]"
```

Expected: `[KCI] keywords=... returned=N after_detail_fetch=M after_abstract_filter=K` 형식의 로그가 지표 개수만큼 출력.

- [ ] **Step 5: 발견된 이슈 정리 / KCI XML 스키마 차이 보정**

실제 KCI 응답이 본 plan의 예상 element 이름과 다르면 `_parse_search_xml`, `_parse_detail_xml` 두 함수만 조정. 다른 코드는 영향 없음.

---

## Self-Review Notes

**Spec 커버리지** — 스펙의 16개 섹션 모두 task에 매핑:
- §3 Architecture → Task 3,4,9
- §4 kci_agent → Task 3,4,5,6,7
- §5 merge_papers → Task 8
- §6 search_combined → Task 9
- §7 SOURCE_PLAN → Task 10
- §8 Config → Task 1
- §9 Country/abstract → Task 4,5,6
- §10 Error handling → Task 7,9
- §11 Tests → Task 3,4,5,6,7,9,10,11
- §12 Frontend/label → Task 11,12
- §13 No DB change → 검증됨 (migration task 없음)
- §14 Docs → Task 13
- §15 변경 표면 → Task 1~13 합산 일치
- §16 미해결 사항 → Task 14에서 실제 키로 보정

**Placeholder 검사**: "구현 시 확인 필요" 1건 (Task 4) — KCI XML element 이름. 외부에서 발급문서로 확정 필요한 항목이므로 정상 가정. TODO/TBD 없음.

**타입 일관성**:
- `paper_id` 키는 모든 agent에서 통일.
- `search_combined`의 키워드 인자 (`s2_semaphore`, `openalex_semaphore`, `kci_semaphore`) 명명은 SOURCE_PLAN의 키(`semantic_scholar`, `openalex`, `kci`)와 매핑됨 — `search_all_sources`에서 정확히 변환.
- `_DETAIL_SEM`은 `kci_agent.py` 내부에만 존재.
