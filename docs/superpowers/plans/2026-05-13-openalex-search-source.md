# OpenAlex 논문 검색 소스 추가 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** OpenAlex를 Semantic Scholar / Scopus와 나란히 세 번째 논문 검색 소스로 추가하여, 사용자가 입력 화면에서 선택할 수 있게 한다.

**Architecture:** `backend/app/agents/openalex_agent.py`에 `scopus_agent.py`와 동일한 인터페이스 (`async def search_papers_for_indicator`)를 가진 신규 모듈을 추가하고, `search_agent.search_all_sources` 디스패처에 `"openalex"` 분기를 추가한다. OpenAlex는 abstract를 `abstract_inverted_index` 형식으로 반환하므로 평문 복원 헬퍼를 함께 구현한다. 인증은 무료 polite pool 방식(요청에 `mailto=<email>` 추가)을 사용하며 — 일일 무료 한도(full-text search 1,000 calls/day)는 현재 운영 규모를 충분히 커버한다. 폴백 로직은 추가하지 않고 사용자가 명시적으로 고른 소스만 사용한다.

**Tech Stack:** FastAPI, httpx, pydantic-settings, SQLAlchemy, pytest-asyncio, React (Vite).

**핵심 설계 결정:**
- 기본 소스는 변경하지 않는다 (`semantic_scholar` 그대로).
- 인증: polite pool only (API key 없이 `mailto` 파라미터로 충분).
- `tech_queries.search_source`는 이미 `String(30)`이라 신규 마이그레이션 불필요 (`"openalex"`는 8자).
- 국가 코드 매핑(`country_code` → 풀네임)은 `extraction_agent.py`의 dict를 재활용하기 위해 `_COUNTRY_CODES` → `COUNTRY_CODES`로 public 이름 변경 후 import 공유.

**자료 참고:**
- OpenAlex 인증/요금: https://developers.openalex.org/api-reference/authentication
- 검색 엔드포인트 예: `GET https://api.openalex.org/works?search={kw}&per-page=30&mailto=<email>`

---

## File Structure

**신규**
- `backend/app/agents/openalex_agent.py` — 검색 함수 + abstract 복원 헬퍼.
- `backend/tests/test_openalex_agent.py` — 단위 테스트 (mock httpx 기반).

**수정**
- `backend/app/config.py` — `openalex_email` 설정 추가.
- `backend/app/agents/extraction_agent.py` — `_COUNTRY_CODES` → `COUNTRY_CODES` 이름 변경 (private → public).
- `backend/app/agents/search_agent.py` — `search_all_sources`에 `"openalex"` 분기 추가.
- `backend/tests/test_search_agent.py` — 디스패처 테스트 1건 추가.
- `backend/app/schemas/tech_query.py` — `Literal` 확장 (`"openalex"` 포함).
- `backend/app/utils.py` — `get_engine_label`에 OpenAlex 라벨 추가.
- `frontend/src/pages/InputPage.tsx` — `SOURCE_OPTIONS` 및 state 타입에 OpenAlex 추가.

---

## Task 1: 설정값 추가 (openalex_email)

**Files:**
- Modify: `backend/app/config.py:1-29`

- [ ] **Step 1: 설정 필드 추가**

`backend/app/config.py`의 `Settings` 클래스에 다음 줄을 `elsevier_api_key` 라인 바로 다음에 삽입 (다른 API key 필드와 동일하게 빈 문자열 default — 운영 환경에서 `.env`로 주입):

```python
    openalex_email: str = ""
```

- [ ] **Step 2: 컨테이너에서 설정 로드 확인**

Run: `docker compose exec api python -c "from app.config import settings; print(repr(settings.openalex_email))"`
Expected: `''` (default) 또는 `.env`에 `OPENALEX_EMAIL=...`로 오버라이드한 값.

- [ ] **Step 3: Commit**

```bash
git add backend/app/config.py
git commit -m "feat(openalex): add OPENALEX_EMAIL config for polite pool"
```

---

## Task 2: country code 매핑을 public으로 이름 변경

**목적:** `openalex_agent`가 동일한 국가 코드 → 풀네임 매핑을 재사용할 수 있도록 한다.

**Files:**
- Modify: `backend/app/agents/extraction_agent.py:34, 69`

- [ ] **Step 1: 변수 이름 변경**

`backend/app/agents/extraction_agent.py`에서 두 곳 모두 수정:

라인 34:
```python
_COUNTRY_CODES: dict[str, str] = {
```
→
```python
COUNTRY_CODES: dict[str, str] = {
```

라인 69 (`return _COUNTRY_CODES.get(code, code)`):
→
```python
        return COUNTRY_CODES.get(code, code)
```

- [ ] **Step 2: 기존 테스트가 깨지지 않는지 확인**

Run: `docker compose exec api pytest backend/tests/test_extraction_agent.py -v`
Expected: 기존과 동일하게 모두 PASS

- [ ] **Step 3: Commit**

```bash
git add backend/app/agents/extraction_agent.py
git commit -m "refactor(extraction): rename _COUNTRY_CODES to public COUNTRY_CODES"
```

---

## Task 3: abstract_inverted_index 복원 헬퍼 (TDD)

**목적:** OpenAlex는 라이선스 회피를 위해 abstract를 `{word: [position, ...]}` 형식으로 반환한다. 평문으로 복원하는 순수 함수를 먼저 작성한다.

**Files:**
- Create: `backend/app/agents/openalex_agent.py`
- Create: `backend/tests/test_openalex_agent.py`

- [ ] **Step 1: 실패하는 테스트 작성**

Create `backend/tests/test_openalex_agent.py`:

```python
import pytest
from app.agents.openalex_agent import _reconstruct_abstract

pytestmark = pytest.mark.no_db


def test_reconstruct_abstract_basic():
    inv_idx = {
        "We": [0],
        "present": [1],
        "HBM3E": [2],
        "memory": [3],
    }
    assert _reconstruct_abstract(inv_idx) == "We present HBM3E memory"


def test_reconstruct_abstract_repeated_words():
    inv_idx = {
        "the": [0, 4],
        "memory": [1, 5],
        "is": [2],
        "fast": [3],
    }
    # positions: 0=the 1=memory 2=is 3=fast 4=the 5=memory
    assert _reconstruct_abstract(inv_idx) == "the memory is fast the memory"


def test_reconstruct_abstract_none_returns_empty():
    assert _reconstruct_abstract(None) == ""


def test_reconstruct_abstract_empty_dict_returns_empty():
    assert _reconstruct_abstract({}) == ""


def test_reconstruct_abstract_handles_gaps():
    # OpenAlex 인덱스는 일반적으로 gap 없음. gap이 있어도 sort된 키 순서로 처리해야 함.
    inv_idx = {"word_a": [0], "word_b": [10]}
    result = _reconstruct_abstract(inv_idx)
    assert result == "word_a word_b"
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `docker compose exec api pytest backend/tests/test_openalex_agent.py -v`
Expected: `ImportError: cannot import name '_reconstruct_abstract' from 'app.agents.openalex_agent'`

- [ ] **Step 3: 최소 구현**

Create `backend/app/agents/openalex_agent.py`:

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `docker compose exec api pytest backend/tests/test_openalex_agent.py -v`
Expected: 4개 테스트 모두 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/openalex_agent.py backend/tests/test_openalex_agent.py
git commit -m "feat(openalex): add abstract_inverted_index reconstruction helper"
```

---

## Task 4: OpenAlex 검색 함수 본체 (TDD)

**Files:**
- Modify: `backend/app/agents/openalex_agent.py`
- Modify: `backend/tests/test_openalex_agent.py`

**참고 — OpenAlex `works` 응답 예시 (테스트 mock에 사용):**

```json
{
  "results": [
    {
      "id": "https://openalex.org/W123",
      "doi": "https://doi.org/10.1109/test.2024.001",
      "title": "HBM3E High Bandwidth Memory",
      "publication_year": 2024,
      "cited_by_count": 45,
      "abstract_inverted_index": {"We": [0], "present": [1], "HBM3E": [2]},
      "primary_location": {"source": {"display_name": "IEEE JSSC"}},
      "authorships": [
        {"institutions": [{"country_code": "KR"}]}
      ]
    }
  ]
}
```

- [ ] **Step 1: 정상 응답 테스트 작성 (실패)**

`backend/tests/test_openalex_agent.py` 하단에 추가:

```python
from unittest.mock import AsyncMock, patch, MagicMock
from app.agents.openalex_agent import search_papers_for_indicator

MOCK_OPENALEX_RESPONSE = {
    "results": [
        {
            "id": "https://openalex.org/W123",
            "doi": "https://doi.org/10.1109/test.2024.001",
            "title": "HBM3E High Bandwidth Memory",
            "publication_year": 2024,
            "cited_by_count": 45,
            "abstract_inverted_index": {"We": [0], "present": [1], "HBM3E": [2]},
            "primary_location": {"source": {"display_name": "IEEE JSSC"}},
            "authorships": [
                {"institutions": [{"country_code": "KR"}]}
            ],
        }
    ]
}


@pytest.mark.asyncio
async def test_search_returns_normalized_papers():
    with patch("app.agents.openalex_agent.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = MOCK_OPENALEX_RESPONSE
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        results = await search_papers_for_indicator("HBM bandwidth", max_results=5)

    assert len(results) == 1
    p = results[0]
    assert p["title"] == "HBM3E High Bandwidth Memory"
    assert p["abstract"] == "We present HBM3E"
    assert p["doi"] == "10.1109/test.2024.001"   # https://doi.org/ 접두사 제거
    assert p["year"] == 2024
    assert p["citation_count"] == 45
    assert p["country"] == "South Korea"           # KR → South Korea 매핑
    assert p["journal_name"] == "IEEE JSSC"


@pytest.mark.asyncio
async def test_search_filters_entries_without_abstract():
    no_abs = {
        "results": [
            {
                "id": "https://openalex.org/W1",
                "doi": None,
                "title": "Empty Abstract Paper",
                "publication_year": 2023,
                "cited_by_count": 0,
                "abstract_inverted_index": None,
                "primary_location": None,
                "authorships": [],
            }
        ]
    }
    with patch("app.agents.openalex_agent.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = no_abs
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        results = await search_papers_for_indicator("test", max_results=5)
    assert results == []


@pytest.mark.asyncio
async def test_search_raises_on_429():
    with patch("app.agents.openalex_agent.asyncio.sleep"), \
         patch("app.agents.openalex_agent.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_client.get.return_value = mock_response

        with pytest.raises(RuntimeError, match="OpenAlex API error 429"):
            await search_papers_for_indicator("HBM bandwidth")


@pytest.mark.asyncio
async def test_search_country_none_when_no_institutions():
    no_inst = {
        "results": [
            {
                "id": "https://openalex.org/W2",
                "doi": "https://doi.org/10.x/y",
                "title": "Paper without country",
                "publication_year": 2024,
                "cited_by_count": 3,
                "abstract_inverted_index": {"Hello": [0], "world": [1]},
                "primary_location": {"source": None},
                "authorships": [{"institutions": []}],
            }
        ]
    }
    with patch("app.agents.openalex_agent.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = no_inst
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        results = await search_papers_for_indicator("test", max_results=5)
    assert results[0]["country"] is None
    assert results[0]["journal_name"] is None
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `docker compose exec api pytest backend/tests/test_openalex_agent.py -v`
Expected: `ImportError: cannot import name 'search_papers_for_indicator'`

- [ ] **Step 3: 검색 함수 구현**

`backend/app/agents/openalex_agent.py` 전체를 아래로 교체:

```python
import asyncio
import logging
import httpx
from app.config import settings
from app.agents.extraction_agent import COUNTRY_CODES

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
        if doi.startswith(prefix):
            return doi[len(prefix):]
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
) -> list[dict]:
    max_results = max_results if max_results is not None else settings.max_papers_per_indicator
    params: dict = {
        "search": keywords,
        "per-page": min(max_results, 200),  # OpenAlex 한 페이지 최대 200
        "mailto": settings.openalex_email,
    }
    if settings.search_year_from:
        params["filter"] = f"from_publication_date:{settings.search_year_from}-01-01"

    sem = semaphore or asyncio.Semaphore(1)
    data: dict = {}
    async with sem:
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.get(OPENALEX_API_URL, params=params)
                    if response.status_code == 429:
                        await asyncio.sleep(10 * (attempt + 1))
                        continue
                    response.raise_for_status()
                    data = response.json()
                    break
            except httpx.TimeoutException:
                raise RuntimeError(f"OpenAlex API timeout for: {keywords}")
            except httpx.HTTPStatusError as e:
                raise RuntimeError(f"OpenAlex API error {e.response.status_code}: {keywords}") from e
            except httpx.RequestError as e:
                raise RuntimeError(f"OpenAlex network error: {keywords}") from e
            finally:
                await asyncio.sleep(0.2)  # polite pool 100 req/s 한도 내에서 여유
        else:
            raise RuntimeError(f"OpenAlex API error 429: {keywords}")

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
        })

    logger.info(
        "[OPENALEX] keywords=%r returned=%d after_abstract_filter=%d",
        keywords, len(results), len(papers),
    )
    return papers
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `docker compose exec api pytest backend/tests/test_openalex_agent.py -v`
Expected: 8개 테스트 모두 PASS (Task 3의 4건 + Task 4의 4건)

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/openalex_agent.py backend/tests/test_openalex_agent.py
git commit -m "feat(openalex): add search_papers_for_indicator with polite pool"
```

---

## Task 5: 디스패처에 openalex 분기 추가 (TDD)

**Files:**
- Modify: `backend/app/agents/search_agent.py:1-72`
- Modify: `backend/tests/test_search_agent.py`

- [ ] **Step 1: 실패하는 디스패처 테스트 추가**

`backend/tests/test_search_agent.py` 하단에 추가:

```python
@pytest.mark.asyncio
async def test_search_all_sources_uses_openalex_when_specified():
    with patch("app.agents.search_agent.openalex_agent") as mock_openalex:
        mock_openalex.search_papers_for_indicator = AsyncMock(return_value=[
            {"title": "OpenAlex Paper", "abstract": "abstract", "doi": "10.x/y",
             "year": 2024, "citation_count": 12, "paper_id": "OA1", "country": "South Korea",
             "journal_name": "Nature"}
        ])
        from app.agents.search_agent import search_all_sources
        results = await search_all_sources("HBM", source="openalex", max_results=5)

    mock_openalex.search_papers_for_indicator.assert_called_once()
    assert results[0]["title"] == "OpenAlex Paper"
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `docker compose exec api pytest backend/tests/test_search_agent.py::test_search_all_sources_uses_openalex_when_specified -v`
Expected: `AttributeError` 또는 디스패처가 fallback해서 `semantic_scholar` 호출 → assert 실패

- [ ] **Step 3: 디스패처 구현**

`backend/app/agents/search_agent.py`의 import 영역과 `search_all_sources` 함수를 수정.

라인 4를:
```python
from app.agents import scopus_agent
```
→
```python
from app.agents import scopus_agent, openalex_agent
```

라인 64-72의 `search_all_sources`를 아래로 교체:
```python
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
```

- [ ] **Step 4: 전체 search 테스트 통과 확인**

Run: `docker compose exec api pytest backend/tests/test_search_agent.py -v`
Expected: 신규 테스트 포함 모든 케이스 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/search_agent.py backend/tests/test_search_agent.py
git commit -m "feat(search): route 'openalex' source through openalex_agent"
```

---

## Task 6: 스키마 / 라벨에 openalex 허용

**Files:**
- Modify: `backend/app/schemas/tech_query.py:10`
- Modify: `backend/app/utils.py:35-36`

- [ ] **Step 1: Literal 확장**

`backend/app/schemas/tech_query.py` 라인 10:
```python
    search_source: Literal["semantic_scholar", "scopus"] = "semantic_scholar"
```
→
```python
    search_source: Literal["semantic_scholar", "scopus", "openalex"] = "semantic_scholar"
```

- [ ] **Step 2: 엔진 라벨 함수 업데이트**

`backend/app/utils.py` 라인 35-36의 `get_engine_label` 전체를 교체:
```python
def get_engine_label(search_source: str) -> str:
    if search_source == "scopus":
        return "Scopus (Elsevier) + Gemini"
    if search_source == "openalex":
        return "OpenAlex + Gemini"
    return "Semantic Scholar + Gemini"
```

- [ ] **Step 3: 라우터에 빠르게 POST해서 validation 확인**

Run:
```bash
docker compose exec api python -c "from app.schemas.tech_query import TechQueryCreate; print(TechQueryCreate(category='test', description='test', search_source='openalex'))"
```
Expected: 정상 출력 (ValidationError 없음). `search_source='invalid'` 일 때만 ValidationError 발생해야 함.

- [ ] **Step 4: 전체 단위 테스트 통과 재확인**

Run: `docker compose exec api pytest`
Expected: 전 항목 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/tech_query.py backend/app/utils.py
git commit -m "feat(api): accept 'openalex' as search_source value"
```

---

## Task 7: Frontend 소스 옵션 추가

**Files:**
- Modify: `frontend/src/pages/InputPage.tsx:7-10, 16, 39-41, 78-97`

- [ ] **Step 1: SOURCE_OPTIONS와 state 타입 확장**

라인 7-10:
```typescript
const SOURCE_OPTIONS = [
  { value: "semantic_scholar", label: "Semantic Scholar" },
  { value: "scopus",           label: "Scopus (Elsevier)" },
] as const;
```
→
```typescript
const SOURCE_OPTIONS = [
  { value: "semantic_scholar", label: "Semantic Scholar" },
  { value: "scopus",           label: "Scopus (Elsevier)" },
  { value: "openalex",         label: "OpenAlex" },
] as const;

type SearchSource = typeof SOURCE_OPTIONS[number]["value"];
```

라인 16의 useState 제네릭을 변경:
```typescript
  const [searchSource,  setSearchSource]  = useState<"semantic_scholar" | "scopus">("semantic_scholar");
```
→
```typescript
  const [searchSource,  setSearchSource]  = useState<SearchSource>("semantic_scholar");
```

- [ ] **Step 2: sourceLabel 분기 갱신**

라인 39-41:
```typescript
  const sourceLabel = searchSource === "scopus"
    ? "Scopus (Elsevier)"
    : "Semantic Scholar";
```
→
```typescript
  const sourceLabel =
    SOURCE_OPTIONS.find((o) => o.value === searchSource)?.label ?? "Semantic Scholar";
```

- [ ] **Step 3: 버튼 그룹의 borderRight 처리 일반화**

라인 78-97의 `<div className="flex rounded-lg ...">` 블록에서, `borderRight`가 `"semantic_scholar"` 하드코딩되어 있다. 마지막 옵션이 아닐 때 모두 구분선이 보이도록 일반화:

```jsx
                {SOURCE_OPTIONS.map((opt, i) => {
                  const active = searchSource === opt.value;
                  return (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => setSearchSource(opt.value)}
                      className="flex-1 py-2 text-sm font-medium transition-colors duration-150"
                      style={{
                        background: active ? "var(--color-navy-dark)" : "var(--color-surface-2)",
                        color: active ? "var(--color-text-inv)" : "var(--color-text-3)",
                        borderRight: i < SOURCE_OPTIONS.length - 1 ? "1px solid var(--color-border)" : undefined,
                      }}
                    >
                      {opt.label}
                    </button>
                  );
                })}
```

- [ ] **Step 4: TypeScript 빌드 검증**

Run: `cd frontend && npm run build`
Expected: 빌드 성공, 타입 에러 0건.

- [ ] **Step 5: 시각 검증**

`docker compose up`을 띄운 상태에서 브라우저로 `http://localhost:8098` 접속 → 입력 페이지의 "논문 데이터 소스" 토글에 3개 옵션이 보이고, OpenAlex를 선택하면 하단 안내 문구가 `"OpenAlex 논문 데이터 기반 · Gemini AI 수치 추출 · 분석 소요 5–15분"`으로 갱신되는지 확인.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/InputPage.tsx
git commit -m "feat(frontend): add OpenAlex option to source selector"
```

---

## Task 8: End-to-End 시연

**목적:** 실제 OpenAlex 호출을 한 번 실행해서 정상 동작과 무료 한도 사용량을 직접 확인.

- [ ] **Step 1: 서비스 기동 (또는 재기동)**

Run: `docker compose up --build -d`
Expected: api, frontend, redis, postgres, minio 컨테이너 모두 healthy.

- [ ] **Step 2: 입력 페이지에서 OpenAlex 선택 후 파이프라인 실행**

브라우저로 `http://localhost:8098` 접속 → 카테고리 임의 선택, 설명 입력 (예: `"HBM 고대역폭 메모리"`), 데이터 소스 = OpenAlex → 지표 1~2개로 축소해서 잡 실행.

- [ ] **Step 3: 로그에서 OpenAlex 호출 검증**

Run: `docker compose logs -f api 2>&1 | Select-String "OPENALEX"`
Expected: `[OPENALEX] keywords=... returned=N after_abstract_filter=M` 형태의 로그가 지표 수만큼 출력.

- [ ] **Step 4: 결과 페이지에서 데이터 확인**

브라우저 결과 페이지에서:
- 보고서가 정상 생성되었는지 확인.
- 데이터 탭에서 country, journal_name, doi가 채워졌는지 확인.

- [ ] **Step 5: 일일 사용량 확인 (선택)**

Run:
```bash
docker compose exec api python -c "import httpx; r=httpx.get('https://api.openalex.org/rate-limit', headers={'User-Agent':'TechSpec/1.0 (mailto:ilhwan.lee@gmail.com)'}); print(r.json())"
```
Expected: `daily_budgets`, `remaining` 등의 필드가 출력되며 full-text search 잔여 한도가 1,000에 가깝게 유지되어 있어야 함 (1회 실행 ≈ 지표 수만큼 차감).

- [ ] **Step 6: 통합 시연 결과 commit (테스트 코드 변경 없음, 수동 검증만)**

이 task에서는 코드 변경이 없으므로 commit 생략. 단, 시연 중에 발견한 버그가 있으면 별도 task로 분리해 수정 후 commit.

---

## Self-Review Notes

- **Spec coverage:** OpenAlex 추가의 모든 layer(설정 → 도메인 모듈 → 디스패처 → 스키마 → 프론트 → e2e) 커버 ✅.
- **Placeholder scan:** TBD / "handle edge cases" 같은 표현 없음. 모든 step에 실제 코드/명령어 포함 ✅.
- **Type consistency:** 신규 paper dict 구조는 `scopus_agent`/`search_agent`와 동일 키 셋(`paper_id, title, abstract, year, citation_count, doi, journal_name, country`) — pipeline의 `extract_node`가 기대하는 키와 일치 ✅.
- **누락 점검:** `tech_queries.search_source`는 `String(30)` 으로 이미 충분(`"openalex"`는 8자) → 마이그레이션 불필요 ✅. backend `get_engine_label`은 보고서/UI 라벨 양쪽에서 호출되므로 한 군데 수정으로 일관됨 ✅.

---

## 비용 / 한도 요약

- 인증: API key 없이 polite pool (`mailto`만으로 충분).
- 1회 파이프라인 (지표 10개, 30개 논문) → full-text search 약 **10 calls / 300 results**.
- 무료 한도: full-text search **1,000 calls/day** → **하루 약 100회 파이프라인 실행까지 무료**.
- Singleton (`/works/doi:...`, 현 extraction_agent 국가 보완용)은 **무제한**.
- 100 req/sec rate limit — 현재 search_node는 `Semaphore(1)`로 직렬 호출이라 안전.
