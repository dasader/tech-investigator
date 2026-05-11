# Elsevier Scopus API 통합 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Semantic Scholar 외에 Elsevier Scopus Search API를 선택적으로 사용할 수 있도록 통합하고, 초기화면에서 API를 선택할 수 있는 UI를 추가한다.

**Architecture:** `tech_queries.search_source` 컬럼에 선택된 API 소스를 저장한다. 파이프라인 실행 시 이 값을 읽어 `search_agent.py`가 Scopus 또는 Semantic Scholar 에이전트로 라우팅한다. Scopus 응답에는 affiliation country가 포함되므로 해당 필드가 있으면 OpenAlex API 호출을 생략한다.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, httpx, React (Vite + Tailwind)

---

## 파일 맵

| 파일 | 변경 종류 | 역할 |
|------|---------|------|
| `backend/app/config.py` | 수정 | `elsevier_api_key` 필드 추가 |
| `backend/app/models/tech_query.py` | 수정 | `search_source` 컬럼 추가 |
| `backend/alembic/versions/<hash>_add_search_source_to_tech_queries.py` | 신규 | DB 마이그레이션 |
| `backend/app/agents/scopus_agent.py` | 신규 | Scopus Search API 호출 + 응답 정규화 |
| `backend/app/agents/search_agent.py` | 수정 | `source` 파라미터로 에이전트 라우팅 |
| `backend/app/agents/extraction_agent.py` | 수정 | `paper.country` 있으면 OpenAlex 스킵 |
| `backend/app/agents/pipeline.py` | 수정 | `search_source` state 주입 |
| `backend/app/schemas/tech_query.py` | 수정 | `search_source` 필드 추가 |
| `backend/app/routers/tech_input.py` | 수정 | `search_source` 저장 |
| `backend/tests/test_scopus_agent.py` | 신규 | Scopus 에이전트 단위 테스트 |
| `frontend/src/pages/InputPage.tsx` | 수정 | API 선택 세그먼트 컨트롤 |
| `frontend/src/api/client.ts` | 수정 | `search_source` 전달 |

---

### Task 1: config에 elsevier_api_key 추가

**Files:**
- Modify: `backend/app/config.py`
- Modify: `.env`

- [ ] **Step 1: `config.py`에 `elsevier_api_key` 필드 추가**

`backend/app/config.py` 전체를 아래로 교체:

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    gemini_api_key: str
    gemini_model_complex: str = "gemini-2.5-pro"
    gemini_model_fast: str = "gemini-2.5-flash"
    semantic_scholar_api_key: str = ""
    elsevier_api_key: str = ""
    job_timeout_minutes: int = 15
    max_papers_per_indicator: int = 30
    min_confidence_score: float = 0.5
    search_year_from: int | None = None
    frontend_url: str = "http://localhost:8098"
    database_url: str
    redis_url: str = "redis://redis:6379/0"
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "techspec-pdfs"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    class Config:
        env_file = ".env"

settings = Settings()
```

- [ ] **Step 2: `.env`에 `ELSEVIER_API_KEY` 추가**

`.env` 파일에 아래 줄 추가 (실제 키 값으로 교체):

```
ELSEVIER_API_KEY=여기에_실제_키_입력
```

- [ ] **Step 3: 커밋**

```bash
git add backend/app/config.py .env
git commit -m "feat: add elsevier_api_key to settings"
```

---

### Task 2: DB 모델 + Alembic 마이그레이션

**Files:**
- Modify: `backend/app/models/tech_query.py`
- Create: `backend/alembic/versions/<자동생성hash>_add_search_source_to_tech_queries.py`

- [ ] **Step 1: `tech_query.py` 모델에 `search_source` 컬럼 추가**

`backend/app/models/tech_query.py` 전체를 아래로 교체:

```python
from sqlalchemy import Column, Integer, String, Text, DateTime, func
from app.database import Base

class TechQuery(Base):
    __tablename__ = "tech_queries"

    id = Column(Integer, primary_key=True, index=True)
    user_email = Column(String(255), nullable=True)
    category = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    search_source = Column(String(30), nullable=False, server_default="semantic_scholar")
    created_at = Column(DateTime, server_default=func.now())
```

- [ ] **Step 2: Alembic 마이그레이션 자동 생성 (Docker 필요)**

```bash
docker compose exec api alembic revision --autogenerate -m "add search_source to tech_queries"
```

생성된 파일 (`backend/alembic/versions/<hash>_add_search_source_to_tech_queries.py`)을 열어 `upgrade()`와 `downgrade()`가 아래와 같은지 확인. 자동 생성 내용이 다르면 수동으로 수정:

```python
def upgrade() -> None:
    op.add_column('tech_queries', sa.Column(
        'search_source', sa.String(30),
        nullable=False,
        server_default='semantic_scholar'
    ))

def downgrade() -> None:
    op.drop_column('tech_queries', 'search_source')
```

- [ ] **Step 3: 마이그레이션 적용**

```bash
docker compose exec api alembic upgrade head
```

Expected output: `Running upgrade 0bb20f2510f4 -> <newhash>, add search_source to tech_queries`

- [ ] **Step 4: 커밋**

```bash
git add backend/app/models/tech_query.py backend/alembic/versions/
git commit -m "feat: add search_source column to tech_queries"
```

---

### Task 3: Scopus 검색 에이전트

**Files:**
- Create: `backend/app/agents/scopus_agent.py`
- Create: `backend/tests/test_scopus_agent.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_scopus_agent.py` 신규 생성:

```python
import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from app.agents.scopus_agent import search_papers_for_indicator

MOCK_SCOPUS_RESPONSE = {
    "search-results": {
        "entry": [
            {
                "dc:identifier": "SCOPUS_ID:85123456",
                "dc:title": "HBM3E High Bandwidth Memory",
                "dc:description": "We present HBM3E achieving 1.2 TB/s bandwidth in 2024.",
                "prism:doi": "10.1109/scopus.2024.001",
                "citedby-count": "30",
                "prism:coverDate": "2024-03-01",
                "affiliation": [
                    {
                        "affiliation-country": "South Korea",
                        "affilname": "SK Hynix",
                    }
                ],
            }
        ]
    }
}

MOCK_SCOPUS_NO_AFFILIATION = {
    "search-results": {
        "entry": [
            {
                "dc:identifier": "SCOPUS_ID:85000001",
                "dc:title": "Paper Without Affiliation",
                "dc:description": "Some abstract text here.",
                "prism:doi": "10.1109/test.2024.002",
                "citedby-count": "5",
                "prism:coverDate": "2024-01-01",
                "affiliation": [],
            }
        ]
    }
}


@pytest.mark.asyncio
async def test_search_returns_normalized_papers():
    with patch("app.agents.scopus_agent.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = MOCK_SCOPUS_RESPONSE
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        results = await search_papers_for_indicator("HBM bandwidth", max_results=5)

    assert isinstance(results, list)
    assert len(results) == 1
    paper = results[0]
    assert paper["title"] == "HBM3E High Bandwidth Memory"
    assert paper["abstract"] == "We present HBM3E achieving 1.2 TB/s bandwidth in 2024."
    assert paper["doi"] == "10.1109/scopus.2024.001"
    assert paper["year"] == 2024
    assert paper["citation_count"] == 30
    assert paper["country"] == "South Korea"


@pytest.mark.asyncio
async def test_search_country_none_when_no_affiliation():
    with patch("app.agents.scopus_agent.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = MOCK_SCOPUS_NO_AFFILIATION
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        results = await search_papers_for_indicator("test keyword", max_results=5)

    assert results[0]["country"] is None


@pytest.mark.asyncio
async def test_search_filters_entries_without_abstract():
    no_abstract_response = {
        "search-results": {
            "entry": [
                {
                    "dc:identifier": "SCOPUS_ID:1",
                    "dc:title": "No Abstract Paper",
                    "dc:description": "",
                    "prism:doi": "10.1/test",
                    "citedby-count": "0",
                    "prism:coverDate": "2023-01-01",
                    "affiliation": [],
                }
            ]
        }
    }
    with patch("app.agents.scopus_agent.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = no_abstract_response
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        results = await search_papers_for_indicator("test", max_results=5)

    assert results == []


@pytest.mark.asyncio
async def test_search_raises_on_429():
    with patch("app.agents.scopus_agent.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_client.get.return_value = mock_response

        with pytest.raises(RuntimeError, match="Scopus API error 429"):
            await search_papers_for_indicator("HBM bandwidth")
```

- [ ] **Step 2: 테스트 실행 — FAIL 확인**

```bash
docker compose exec api pytest backend/tests/test_scopus_agent.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` (파일 없음)

- [ ] **Step 3: `scopus_agent.py` 구현**

`backend/app/agents/scopus_agent.py` 신규 생성:

```python
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
```

- [ ] **Step 4: 테스트 실행 — PASS 확인**

```bash
docker compose exec api pytest backend/tests/test_scopus_agent.py -v
```

Expected:
```
test_search_returns_normalized_papers PASSED
test_search_country_none_when_no_affiliation PASSED
test_search_filters_entries_without_abstract PASSED
test_search_raises_on_429 PASSED
```

- [ ] **Step 5: 커밋**

```bash
git add backend/app/agents/scopus_agent.py backend/tests/test_scopus_agent.py
git commit -m "feat: add Scopus Search API agent with country resolution"
```

---

### Task 4: search_agent — source 파라미터 라우팅

**Files:**
- Modify: `backend/app/agents/search_agent.py`
- Modify: `backend/tests/test_search_agent.py`

- [ ] **Step 1: 실패하는 테스트 추가**

`backend/tests/test_search_agent.py` 파일 끝에 아래 두 테스트를 추가:

```python
@pytest.mark.asyncio
async def test_search_all_sources_uses_scopus_when_specified():
    with patch("app.agents.search_agent.scopus_agent") as mock_scopus:
        mock_scopus.search_papers_for_indicator = AsyncMock(return_value=[
            {"title": "Scopus Paper", "abstract": "abstract", "doi": None,
             "year": 2024, "citation_count": 10, "paper_id": "S1", "country": "USA"}
        ])
        from app.agents.search_agent import search_all_sources
        results = await search_all_sources("HBM", source="scopus", max_results=5)

    mock_scopus.search_papers_for_indicator.assert_called_once()
    assert results[0]["title"] == "Scopus Paper"


@pytest.mark.asyncio
async def test_search_all_sources_uses_semantic_scholar_by_default():
    with patch("app.agents.search_agent.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.json.return_value = MOCK_SS_RESPONSE
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response
        from app.agents.search_agent import search_all_sources
        results = await search_all_sources("HBM", max_results=5)

    assert results[0]["title"] == "HBM3E: High Bandwidth Memory"
```

- [ ] **Step 2: 테스트 실행 — FAIL 확인**

```bash
docker compose exec api pytest backend/tests/test_search_agent.py::test_search_all_sources_uses_scopus_when_specified backend/tests/test_search_agent.py::test_search_all_sources_uses_semantic_scholar_by_default -v
```

Expected: FAIL (`search_all_sources` 시그니처에 `source` 파라미터 없음)

- [ ] **Step 3: `search_agent.py` 수정**

`backend/app/agents/search_agent.py` 전체를 아래로 교체:

```python
import asyncio
import httpx
from app.config import settings
from app.agents import scopus_agent

SS_API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
SS_FIELDS = "paperId,title,abstract,year,citationCount,externalIds"


async def search_papers_for_indicator(
    keywords: str,
    max_results: int | None = None,
    semaphore: asyncio.Semaphore | None = None,
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
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.get(SS_API_URL, params=params, headers=headers)
                    if response.status_code == 429:
                        await asyncio.sleep(10 * (attempt + 1))
                        continue
                    response.raise_for_status()
                    data = response.json().get("data", [])
                    break
            except httpx.TimeoutException:
                raise RuntimeError(f"Semantic Scholar API timeout for: {keywords}")
            except httpx.RequestError as e:
                raise RuntimeError(f"Semantic Scholar network error: {keywords}") from e
            finally:
                await asyncio.sleep(1.1)
        else:
            raise RuntimeError(f"Semantic Scholar API error 429: {keywords}")

    papers = [
        {
            "paper_id": p.get("paperId"),
            "title": p.get("title", ""),
            "abstract": p.get("abstract", ""),
            "year": p.get("year"),
            "citation_count": p.get("citationCount", 0),
            "doi": (p.get("externalIds") or {}).get("DOI"),
            "country": None,
        }
        for p in data
        if p.get("abstract")
    ]
    return papers


async def search_all_sources(
    keywords: str,
    source: str = "semantic_scholar",
    max_results: int | None = None,
    semaphore: asyncio.Semaphore | None = None,
) -> list[dict]:
    if source == "scopus":
        return await scopus_agent.search_papers_for_indicator(keywords, max_results, semaphore)
    return await search_papers_for_indicator(keywords, max_results, semaphore)
```

> **주의:** Semantic Scholar 응답 dict에 `"country": None` 필드를 추가했다. 이후 extraction_agent가 이 필드를 체크하므로 반드시 포함해야 한다.

- [ ] **Step 4: 테스트 실행 — 전체 PASS 확인**

```bash
docker compose exec api pytest backend/tests/test_search_agent.py -v
```

Expected: 기존 4개 + 신규 2개 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add backend/app/agents/search_agent.py backend/tests/test_search_agent.py
git commit -m "feat: route search_all_sources by source param (scopus / semantic_scholar)"
```

---

### Task 5: extraction_agent — country 선결정 시 OpenAlex 스킵

**Files:**
- Modify: `backend/app/agents/extraction_agent.py`
- Modify: `backend/tests/test_extraction_agent.py`

- [ ] **Step 1: 실패하는 테스트 추가**

`backend/tests/test_extraction_agent.py` 파일 끝에 아래 테스트를 추가:

```python
@pytest.mark.asyncio
async def test_skips_openalex_when_country_already_set():
    paper_with_country = {
        "title": "Scopus Paper",
        "abstract": "We present HBM3E achieving 1.2 TB/s bandwidth.",
        "year": 2024,
        "doi": "10.1109/test.2024.003",
        "citation_count": 20,
        "country": "South Korea",
    }
    with patch("app.agents.extraction_agent.genai_client") as mock_client, \
         patch("app.agents.extraction_agent._get_country_from_openalex") as mock_openalex:
        mock_response = MagicMock()
        mock_response.text = '{"value": 1228.0, "unit": "GB/s", "confidence_score": 0.9, "quote": "1.2 TB/s"}'
        mock_client.models.generate_content.return_value = mock_response

        result = await extract_metric_from_paper(paper_with_country, "대역폭", "GB/s")

    mock_openalex.assert_not_called()
    assert result["country"] == "South Korea"
```

- [ ] **Step 2: 테스트 실행 — FAIL 확인**

```bash
docker compose exec api pytest backend/tests/test_extraction_agent.py::test_skips_openalex_when_country_already_set -v
```

Expected: FAIL (현재 구현은 항상 OpenAlex를 호출함)

- [ ] **Step 3: `extraction_agent.py`의 `_country_coro` 수정**

`backend/app/agents/extraction_agent.py` 의 `extract_metric_from_paper` 함수 내부 `_country_coro` 정의 부분을 아래로 교체:

```python
        async def _country_coro() -> str | None:
            if paper.get("country") is not None:
                return paper["country"]
            return await _get_country_from_openalex(doi) if doi else None
```

교체 전:
```python
        async def _country_coro() -> str | None:
            return await _get_country_from_openalex(doi) if doi else None
```

- [ ] **Step 4: 테스트 실행 — 전체 PASS 확인**

```bash
docker compose exec api pytest backend/tests/test_extraction_agent.py -v
```

Expected: 기존 2개 + 신규 1개 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add backend/app/agents/extraction_agent.py backend/tests/test_extraction_agent.py
git commit -m "feat: skip OpenAlex lookup when paper.country already set (Scopus path)"
```

---

### Task 6: pipeline.py — search_source state 주입

**Files:**
- Modify: `backend/app/agents/pipeline.py`

- [ ] **Step 1: `PipelineState`에 `search_source` 필드 추가 및 `search_node`, `run_pipeline` 수정**

`backend/app/agents/pipeline.py` 전체를 아래로 교체:

```python
import asyncio
from typing import TypedDict, List
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session
from app.agents.search_agent import search_all_sources
from app.agents.extraction_agent import extract_metric_from_paper
from app.agents.validation_agent import validate_and_rank
from app.agents.synthesis_agent import build_report_markdown
from app.models.indicator import Indicator
from app.models.metric_value import MetricValue
from app.models.job import Job
from app.config import settings

class PipelineState(TypedDict):
    job_id: int
    query_id: int
    category: str
    description: str
    search_source: str
    indicators: List[dict]
    search_results: dict
    extracted_values: dict
    validated_values: dict
    report_markdown: str
    error: str

def _update_job(db: Session, job_id: int, progress_pct: float, current_step: str):
    job = db.query(Job).filter(Job.id == job_id).first()
    if job:
        job.progress_pct = progress_pct
        job.current_step = current_step
        db.commit()

async def search_node(state: PipelineState, db: Session) -> PipelineState:
    _update_job(db, state["job_id"], 10.0, "논문 검색 중")
    semaphore = asyncio.Semaphore(1)
    results = {}
    tasks = [
        search_all_sources(
            ind["search_keywords"] or ind["name"],
            source=state["search_source"],
            semaphore=semaphore,
        )
        for ind in state["indicators"]
    ]
    paper_lists = await asyncio.gather(*tasks)
    for ind, papers in zip(state["indicators"], paper_lists):
        results[ind["id"]] = papers
    return {**state, "search_results": results}

async def extract_node(state: PipelineState, db: Session) -> PipelineState:
    _update_job(db, state["job_id"], 40.0, "수치 추출 중")

    semaphore = asyncio.Semaphore(10)

    tasks_meta = []
    for ind in state["indicators"]:
        papers = state["search_results"].get(ind["id"], [])[:settings.max_papers_per_indicator]
        for paper in papers:
            tasks_meta.append((ind, paper))

    tasks = [
        extract_metric_from_paper(paper, ind["name"], ind.get("unit", ""), semaphore)
        for ind, paper in tasks_meta
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    extracted: dict = {ind["id"]: [] for ind in state["indicators"]}
    for (ind, _), result in zip(tasks_meta, results):
        if not isinstance(result, Exception):
            extracted[ind["id"]].append(result)

    return {**state, "extracted_values": extracted}

async def validate_node(state: PipelineState, db: Session) -> PipelineState:
    _update_job(db, state["job_id"], 70.0, "교차 검증 중")
    validated = {}
    for ind in state["indicators"]:
        extractions = state["extracted_values"].get(ind["id"], [])
        top3 = validate_and_rank(extractions)
        validated[ind["id"]] = top3
        for mv_data in top3:
            v = mv_data.get("value")
            try:
                numeric_value = float(v) if v is not None else None
            except (TypeError, ValueError):
                numeric_value = None
            mv = MetricValue(
                indicator_id=ind["id"],
                value=numeric_value,
                unit=mv_data.get("unit"),
                year=mv_data.get("year"),
                country=mv_data.get("country"),
                confidence_score=mv_data.get("confidence_score", 0.0),
                paper_title=mv_data.get("paper_title"),
                doi=mv_data.get("doi"),
                source_url=mv_data.get("source_url"),
                quote=mv_data.get("quote"),
            )
            db.add(mv)
    db.commit()
    return {**state, "validated_values": validated}

async def synthesize_node(state: PipelineState, db: Session) -> PipelineState:
    _update_job(db, state["job_id"], 90.0, "리포트 생성 중")
    results_by_indicator = {
        ind["name"]: state["validated_values"].get(ind["id"], [])
        for ind in state["indicators"]
    }
    from datetime import datetime, timezone
    analyzed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    markdown = await build_report_markdown(state["category"], state["description"], results_by_indicator, analyzed_at)
    return {**state, "report_markdown": markdown}

async def run_pipeline(job_id: int, db: Session) -> str:
    from app.models.job import Job
    from app.models.indicator import Indicator
    from app.models.tech_query import TechQuery

    job = db.query(Job).filter(Job.id == job_id).first()
    query = db.query(TechQuery).filter(TechQuery.id == job.query_id).first()
    indicators = db.query(Indicator).filter(
        Indicator.query_id == job.query_id,
        Indicator.confirmed_by_user == True
    ).all()

    state: PipelineState = {
        "job_id": job_id,
        "query_id": job.query_id,
        "category": query.category,
        "description": query.description,
        "search_source": query.search_source or "semantic_scholar",
        "indicators": [
            {"id": i.id, "name": i.name, "unit": i.unit, "search_keywords": i.search_keywords}
            for i in indicators
        ],
        "search_results": {},
        "extracted_values": {},
        "validated_values": {},
        "report_markdown": "",
        "error": "",
    }

    state = await search_node(state, db)
    state = await extract_node(state, db)
    state = await validate_node(state, db)
    state = await synthesize_node(state, db)
    return state["report_markdown"]
```

- [ ] **Step 2: 기존 파이프라인 테스트가 깨지지 않는지 확인**

```bash
docker compose exec api pytest backend/tests/test_pipeline_task.py -v
```

Expected: 기존 테스트 모두 PASS

- [ ] **Step 3: 커밋**

```bash
git add backend/app/agents/pipeline.py
git commit -m "feat: inject search_source from TechQuery into pipeline state"
```

---

### Task 7: 백엔드 스키마 + 라우터

**Files:**
- Modify: `backend/app/schemas/tech_query.py`
- Modify: `backend/app/routers/tech_input.py`

- [ ] **Step 1: `TechQueryCreate` 스키마에 `search_source` 추가**

`backend/app/schemas/tech_query.py` 전체를 아래로 교체:

```python
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class TechQueryCreate(BaseModel):
    category: str
    description: str
    user_email: Optional[str] = None
    search_source: str = "semantic_scholar"


class TechQueryOut(BaseModel):
    id: int
    category: str
    description: str
    search_source: str
    created_at: datetime

    class Config:
        from_attributes = True
```

- [ ] **Step 2: `tech_input.py` 라우터에서 `search_source` 저장**

`backend/app/routers/tech_input.py` 전체를 아래로 교체:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.tech_query import TechQuery
from app.schemas.tech_query import TechQueryCreate, TechQueryOut

router = APIRouter(tags=["tech-input"])

@router.post("/tech-input", response_model=TechQueryOut)
def create_tech_input(payload: TechQueryCreate, db: Session = Depends(get_db)):
    query = TechQuery(
        category=payload.category,
        description=payload.description,
        user_email=payload.user_email,
        search_source=payload.search_source,
    )
    db.add(query)
    db.commit()
    db.refresh(query)
    return query
```

- [ ] **Step 3: API 동작 확인 (Docker 필요)**

```bash
docker compose up --build -d
curl -s -X POST http://localhost:8017/api/tech-input \
  -H "Content-Type: application/json" \
  -d '{"category":"HBM","description":"test","search_source":"scopus"}' | python -m json.tool
```

Expected: `"search_source": "scopus"` 포함된 JSON 응답

- [ ] **Step 4: 커밋**

```bash
git add backend/app/schemas/tech_query.py backend/app/routers/tech_input.py
git commit -m "feat: accept and persist search_source in tech-input API"
```

---

### Task 8: 프론트엔드 — API 선택 UI

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/InputPage.tsx`

- [ ] **Step 1: `client.ts`에 `search_source` 파라미터 추가**

`frontend/src/api/client.ts` 전체를 아래로 교체:

```typescript
import axios from "axios";

const api = axios.create({ baseURL: "/api" });

export const createTechInput = (data: {
  category: string;
  description: string;
  user_email?: string;
  search_source?: string;
}) => api.post("/tech-input", data).then(r => r.data);

export const generateIndicators = (queryId: number) =>
  api.post(`/queries/${queryId}/indicators/generate`).then(r => r.data);

export const updateIndicator = (id: number, data: Partial<{ name: string; unit: string; confirmed_by_user: boolean }>) =>
  api.put(`/indicators/${id}`, data).then(r => r.data);

export const deleteIndicator = (id: number) =>
  api.delete(`/indicators/${id}`);

export const startJob = (queryId: number) =>
  api.post(`/queries/${queryId}/jobs`).then(r => r.data);

export const getJob = (jobId: number) =>
  api.get(`/jobs/${jobId}`).then(r => r.data);

export const getResults = (jobId: number) =>
  api.get(`/jobs/${jobId}/results`).then(r => r.data);
```

- [ ] **Step 2: `InputPage.tsx`에 API 선택 UI 추가**

`frontend/src/pages/InputPage.tsx` 전체를 아래로 교체:

```tsx
import { useState } from "react";
import CategorySelect from "../components/CategorySelect";
import { createTechInput } from "../api/client";

interface Props { onNext: (queryId: number) => void; }

const SOURCE_OPTIONS = [
  { value: "semantic_scholar", label: "Semantic Scholar" },
  { value: "scopus",           label: "Scopus (Elsevier)" },
] as const;

export default function InputPage({ onNext }: Props) {
  const [category,      setCategory]      = useState("");
  const [description,   setDescription]   = useState("");
  const [email,         setEmail]         = useState("");
  const [searchSource,  setSearchSource]  = useState<"semantic_scholar" | "scopus">("semantic_scholar");
  const [loading,       setLoading]       = useState(false);
  const [error,         setError]         = useState("");

  const handleSubmit = async () => {
    if (!category || !description) return;
    setLoading(true);
    setError("");
    try {
      const query = await createTechInput({
        category,
        description,
        user_email: email || undefined,
        search_source: searchSource,
      });
      onNext(query.id);
    } catch {
      setError("입력 저장에 실패했습니다. 다시 시도해 주세요.");
    } finally {
      setLoading(false);
    }
  };

  const sourceLabel = searchSource === "scopus"
    ? "Scopus (Elsevier)"
    : "Semantic Scholar";

  return (
    <div className="min-h-[calc(100vh-61px)] flex items-center justify-center px-4 py-16">
      <div className="w-full max-w-xl fade-up">
        <div className="mb-10 text-center">
          <h1
            className="text-3xl font-bold tracking-tight mb-3"
            style={{ fontFamily: "var(--font-heading)", color: "var(--color-navy-dark)" }}
          >
            국가전략기술 Spec 조사
          </h1>
          <p className="text-sm" style={{ color: "var(--color-text-3)" }}>
            기술 분야와 세부 설명을 입력하면 AI가 핵심 지표를 추출하고 논문 기반 수치를 분석합니다
          </p>
        </div>

        <div
          className="rounded-2xl shadow-sm overflow-hidden"
          style={{ background: "var(--color-surface)", border: "1px solid var(--color-border-subtle)" }}
        >
          <div
            className="px-7 py-4 text-xs font-semibold tracking-widest uppercase"
            style={{ background: "var(--color-navy-dark)", color: "rgba(180,205,240,0.6)" }}
          >
            분석 설정
          </div>
          <div className="px-7 py-7 space-y-5">

            {/* 논문 데이터 소스 선택 */}
            <div>
              <label
                className="block text-xs font-semibold mb-2 uppercase tracking-widest"
                style={{ color: "var(--color-text-3)" }}
              >
                논문 데이터 소스
              </label>
              <div className="flex rounded-lg overflow-hidden" style={{ border: "1.5px solid var(--color-border)" }}>
                {SOURCE_OPTIONS.map((opt) => {
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
                        borderRight: opt.value === "semantic_scholar" ? "1px solid var(--color-border)" : undefined,
                      }}
                    >
                      {opt.label}
                    </button>
                  );
                })}
              </div>
            </div>

            <div>
              <label
                className="block text-xs font-semibold mb-2 uppercase tracking-widest"
                style={{ color: "var(--color-text-3)" }}
              >
                기술 분야
              </label>
              <CategorySelect value={category} onChange={setCategory} />
            </div>

            <div>
              <label
                className="block text-xs font-semibold mb-2 uppercase tracking-widest"
                style={{ color: "var(--color-text-3)" }}
              >
                세부 설명
              </label>
              <textarea
                value={description}
                onChange={e => setDescription(e.target.value)}
                placeholder="예: HBM 고대역폭 메모리 적층 기술, 이형접합 기판 기반의 글로벌 Spec 조사"
                className="w-full rounded-lg px-3 py-2.5 text-sm resize-none focus:outline-none focus:ring-2 transition-shadow"
                style={{
                  background: "var(--color-surface-2)",
                  border: "1.5px solid var(--color-border)",
                  color: "var(--color-text)",
                  fontFamily: "var(--font-body)",
                  lineHeight: "1.6",
                  minHeight: "120px",
                }}
              />
            </div>

            <div>
              <label
                className="block text-xs font-semibold mb-2 uppercase tracking-widest"
                style={{ color: "var(--color-text-3)" }}
              >
                이메일 <span className="normal-case font-normal">(완료 알림, 선택)</span>
              </label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="example@email.com"
                className="w-full rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 transition-shadow"
                style={{
                  background: "var(--color-surface-2)",
                  border: "1.5px solid var(--color-border)",
                  color: "var(--color-text)",
                  fontFamily: "var(--font-body)",
                }}
              />
            </div>

            {error && (
              <p className="text-sm px-3 py-2 rounded-lg" style={{ background: "#fff1f0", color: "#c0392b", border: "1px solid #ffd0cc" }}>
                {error}
              </p>
            )}

            <button
              onClick={handleSubmit}
              disabled={loading || !category || !description}
              className="w-full py-3 rounded-xl text-sm font-semibold transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed"
              style={{
                background: loading || !category || !description
                  ? undefined
                  : "var(--color-navy-dark)",
                color: "var(--color-text-inv)",
                letterSpacing: "0.02em",
              }}
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  저장 중...
                </span>
              ) : "지표 생성하기 →"}
            </button>
          </div>
        </div>

        <p className="text-center text-xs mt-6" style={{ color: "var(--color-text-3)" }}>
          {sourceLabel} 논문 데이터 기반 · Gemini AI 수치 추출 · 분석 소요 5–15분
        </p>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: 프론트엔드 빌드 확인**

```bash
cd frontend && npm run build
```

Expected: 빌드 오류 없음

- [ ] **Step 4: 커밋**

```bash
git add frontend/src/api/client.ts frontend/src/pages/InputPage.tsx
git commit -m "feat: add API source selector (Semantic Scholar / Scopus) on input page"
```

---

### Task 9: 전체 통합 확인

- [ ] **Step 1: 전체 테스트 실행**

```bash
docker compose exec api pytest -v
```

Expected: 모든 테스트 PASS

- [ ] **Step 2: Docker 재빌드 + 마이그레이션**

```bash
docker compose up --build -d
docker compose exec api alembic upgrade head
```

- [ ] **Step 3: 브라우저에서 동작 확인**

`http://localhost:8098` 접속 후:
1. 초기화면에 "논문 데이터 소스" 세그먼트 컨트롤 표시 확인
2. Scopus 선택 후 폼 제출 → 하단 문구 "Scopus (Elsevier) 논문 데이터 기반" 확인
3. `.env`에 `ELSEVIER_API_KEY` 설정 후 Scopus로 실제 분석 실행

- [ ] **Step 4: 최종 커밋**

```bash
git add -A
git commit -m "chore: Scopus integration complete — all tests pass"
```
