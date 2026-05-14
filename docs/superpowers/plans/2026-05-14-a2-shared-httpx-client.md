# A2 Shared httpx.AsyncClient Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Share one `httpx.AsyncClient` across all HTTP calls within a single `run_pipeline` invocation via dependency injection, replacing the per-call instantiation pattern.

**Architecture:** `run_pipeline` opens an `async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:` block and passes the same `client` through `search_node` and `extract_node` down to every agent function and helper (`get_with_retry`, `_get_country_from_openalex`, `_batch_fetch_abstracts`). Lifecycle is bounded by the Celery task's `asyncio.run(run_pipeline(...))` invocation — each task gets a fresh client tied to its own event loop.

**Tech Stack:** Python 3.x, FastAPI, Celery, httpx, pytest + pytest-asyncio, Docker Compose. Spec: `docs/superpowers/specs/2026-05-14-a2-shared-httpx-client-design.md`.

**Test invocation:** Inside the api container's working directory (`/app/backend`), so pytest paths are `tests/...` NOT `backend/tests/...`. Always run via `docker compose exec api pytest tests/...`.

**Commit strategy:** All production-code and test-code changes land as **a single atomic commit**. Intermediate steps will fail tests (`TypeError: missing keyword argument 'client'`) — that is expected. Do not attempt to commit between tasks. Only Task 7 commits.

---

## Pre-flight

### Task 0: Branch setup

**Files:** none

- [ ] **Step 0.1: Verify clean repo state on master**

Run: `git status --short | grep -v '\.pyc' | grep -v dockerbuild.bat`
Expected: empty output (only pre-existing `.pyc` and `dockerbuild.bat` working-tree noise remains, no other modifications).

- [ ] **Step 0.2: Create implementation branch**

Run: `git checkout -b chore/a2-shared-httpx-client`
Expected: `Switched to a new branch 'chore/a2-shared-httpx-client'`

- [ ] **Step 0.3: Confirm Docker api container is up**

Run: `docker compose ps`
Expected: `api`, `db`, `redis` containers in `running` state. If not, run `docker compose up -d` and wait for healthchecks.

- [ ] **Step 0.4: Capture baseline test count**

Run: `docker compose exec api pytest tests/ 2>&1 | tail -3`
Expected: `39 passed`. Record this number — it must match the final regression after Task 6.

---

## Task 1: Update `_http_retry` helper signature

**Files:**
- Modify: `backend/app/agents/_http_retry.py` (entire `get_with_retry` body)

The helper no longer creates a client; it receives one and uses it. The `timeout` parameter moves to the per-call `client.get(..., timeout=timeout)` form so each service keeps its existing per-call timeout policy.

- [ ] **Step 1.1: Replace the helper file**

Overwrite `backend/app/agents/_http_retry.py` with:

```python
import asyncio
import httpx


async def get_with_retry(
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
) -> dict:
    """HTTP GET with retry/backoff, using a caller-supplied client.

    Behavior:
      - retry_status_codes: sleep(10 * (attempt+1)) and retry
      - TimeoutException / HTTPStatusError / RequestError → RuntimeError
        with the given service_name and context in the message
      - inter_attempt_sleep > 0: sleep that many seconds after every
        attempt (in finally) to respect per-service rate limits
      - All attempts exhausted on retry_status_codes: raise RuntimeError
    """
    for attempt in range(max_attempts):
        try:
            response = await client.get(url, params=params, headers=headers, timeout=timeout)
            if response.status_code in retry_status_codes:
                await asyncio.sleep(10 * (attempt + 1))
                continue
            response.raise_for_status()
            return response.json()
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

Key diffs vs current code:
- `client` added as required keyword arg
- `async with httpx.AsyncClient(timeout=timeout) as client:` block removed; indentation collapsed one level
- `client.get(url, params=params, headers=headers)` → `client.get(url, params=params, headers=headers, timeout=timeout)`

- [ ] **Step 1.2: Syntax-check the module**

Run: `docker compose exec api python -c "from app.agents._http_retry import get_with_retry; import inspect; print(inspect.signature(get_with_retry))"`
Expected: `(url: str, *, client: httpx.AsyncClient, params: dict | None = None, ...)` printed (no `SyntaxError` / `ImportError`).

No commit yet — production code is half-migrated, tests will fail. Continue to Task 2.

---

## Task 2: Update `pipeline.py` (client creation + node signatures)

**Files:**
- Modify: `backend/app/agents/pipeline.py` (top imports, `search_node`, `extract_node`, `run_pipeline`)

- [ ] **Step 2.1: Add `httpx` import**

Edit `backend/app/agents/pipeline.py`. Find the existing top imports:

```python
import asyncio
from typing import TypedDict, List
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session
from app.agents.search_agent import search_all_sources
from app.agents.extraction_agent import extract_metrics_from_paper
from app.agents.validation_agent import validate_and_rank
from app.agents.synthesis_agent import build_report_markdown
from app.models.indicator import Indicator
from app.models.metric_value import MetricValue
from app.models.job import Job
from app.config import settings
```

Add `import httpx` on its own line right after `import asyncio`:

```python
import asyncio
import httpx
from typing import TypedDict, List
...
```

- [ ] **Step 2.2: Update `search_node` signature and call site**

Replace the existing `search_node` function with:

```python
async def search_node(state: PipelineState, db: Session, client: httpx.AsyncClient) -> PipelineState:
    _update_job(db, state["job_id"], 10.0, "논문 검색 중")
    semaphore = asyncio.Semaphore(1)
    results = {}
    tasks = [
        search_all_sources(
            ind["search_keywords"] or ind["name"],
            source=state["search_source"],
            semaphore=semaphore,
            client=client,
        )
        for ind in state["indicators"]
    ]
    paper_lists = await asyncio.gather(*tasks)
    for ind, papers in zip(state["indicators"], paper_lists):
        results[ind["id"]] = papers
    return {**state, "search_results": results}
```

- [ ] **Step 2.3: Update `extract_node` signature and call site**

Replace the existing `extract_node` function with:

```python
async def extract_node(state: PipelineState, db: Session, client: httpx.AsyncClient) -> PipelineState:
    _update_job(db, state["job_id"], 40.0, "수치 추출 중")

    semaphore = asyncio.Semaphore(10)

    paper_groups: dict[str, dict] = {}
    for ind in state["indicators"]:
        papers = state["search_results"].get(ind["id"], [])[:settings.max_papers_per_indicator]
        for paper in papers:
            # doi → title → year+초록앞부분 순으로 중복 논문을 식별
            key = (paper.get("doi")
                   or paper.get("title")
                   or f"{paper.get('year','')}_{paper.get('abstract','')[:60]}")
            if key not in paper_groups:
                paper_groups[key] = {"paper": paper, "indicators": []}
            paper_groups[key]["indicators"].append(ind)

    tasks = [
        extract_metrics_from_paper(group["paper"], group["indicators"], semaphore, client=client)
        for group in paper_groups.values()
    ]
    batch_results = await asyncio.gather(*tasks, return_exceptions=True)

    extracted: dict = {ind["id"]: [] for ind in state["indicators"]}
    for batch in batch_results:
        if isinstance(batch, Exception):
            continue
        for ind_id, result in batch:
            if ind_id in extracted:
                extracted[ind_id].append(result)

    return {**state, "extracted_values": extracted}
```

Only changes from current: function signature (`+ client: httpx.AsyncClient`) and the `extract_metrics_from_paper(...)` call site (added `client=client`).

- [ ] **Step 2.4: Update `run_pipeline` to create and share the client**

Find the existing `run_pipeline` function's last block (the four sequential `state = await ...` calls). Replace:

```python
    state = await search_node(state, db)
    state = await extract_node(state, db)
    state = await validate_node(state, db)
    state = await synthesize_node(state, db)
    return state["report_markdown"]
```

with:

```python
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        state = await search_node(state, db, client)
        state = await extract_node(state, db, client)
        state = await validate_node(state, db)
        state = await synthesize_node(state, db)
    return state["report_markdown"]
```

`validate_node` and `synthesize_node` are unchanged — they do not perform HTTP.

- [ ] **Step 2.5: Syntax-check the module**

Run: `docker compose exec api python -c "from app.agents.pipeline import run_pipeline, search_node, extract_node; import inspect; print(inspect.signature(search_node)); print(inspect.signature(extract_node))"`
Expected: both signatures end with `client: httpx.AsyncClient)`. No SyntaxError/ImportError.

No commit yet. Continue to Task 3.

---

## Task 3: Update three search agents

**Files:**
- Modify: `backend/app/agents/search_agent.py` (`search_papers_for_indicator`, `search_all_sources`)
- Modify: `backend/app/agents/scopus_agent.py` (`search_papers_for_indicator`, `_batch_fetch_abstracts`)
- Modify: `backend/app/agents/openalex_agent.py` (`search_papers_for_indicator`)

- [ ] **Step 3.1: Update `search_agent.py` (Semantic Scholar)**

Replace `backend/app/agents/search_agent.py` entirely with:

```python
import asyncio
import httpx
from app.config import settings
from app.agents import scopus_agent, openalex_agent
from app.agents._http_retry import get_with_retry

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
            inter_attempt_sleep=1.1,
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
```

Key diffs:
- `import httpx` re-added (needed for `httpx.AsyncClient` type hint)
- `*, client: httpx.AsyncClient` added to both function signatures
- `get_with_retry` call gets `client=client` first kwarg
- `search_all_sources` passes `client=client` through to each branch

- [ ] **Step 3.2: Update `scopus_agent.py`**

Two functions change: `_batch_fetch_abstracts` and `search_papers_for_indicator`. Apply the following edits.

Edit 1 — `_batch_fetch_abstracts` (find the function, currently around lines 61-85). Replace the entire function with:

```python
async def _batch_fetch_abstracts(doi_list: list[str], *, client: httpx.AsyncClient) -> dict[str, str]:
    """Semantic Scholar batch API로 DOI → abstract 매핑 반환."""
    if not doi_list:
        return {}
    ids = [f"DOI:{doi}" for doi in doi_list]
    try:
        r = await client.post(
            S2_BATCH_URL,
            params={"fields": "abstract"},
            json={"ids": ids},
            timeout=20,
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
```

Key diffs:
- `*, client: httpx.AsyncClient` added
- `async with httpx.AsyncClient(timeout=20) as client:` block removed
- `client.post(..., timeout=20)` — timeout moved to call arg
- indentation collapsed one level

Edit 2 — `search_papers_for_indicator` (find the function, currently around line 88). Replace its signature and body up to the `papers = []` line. The current shape:

```python
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
        "count": min(max_results, 25),
        "field": "dc:title,dc:description,prism:doi,citedby-count,prism:coverDate,affiliation,prism:publicationName",
    }
    if settings.search_year_from:
        params["date"] = f"{settings.search_year_from}-{datetime.now().year}"

    sem = semaphore or asyncio.Semaphore(1)
    async with sem:
        payload = await get_with_retry(
            SCOPUS_API_URL,
            params=params,
            headers=headers,
            service_name="Scopus",
            context=keywords,
            inter_attempt_sleep=1.1,
        )
        entries = payload.get("search-results", {}).get("entry", [])
```

Change to:

```python
async def search_papers_for_indicator(
    keywords: str,
    max_results: int | None = None,
    semaphore: asyncio.Semaphore | None = None,
    *,
    client: httpx.AsyncClient,
) -> list[dict]:
    max_results = max_results if max_results is not None else settings.max_papers_per_indicator
    headers = {
        "X-ELS-APIKey": settings.elsevier_api_key,
        "Accept": "application/json",
    }
    params: dict = {
        "query": keywords,
        "count": min(max_results, 25),
        "field": "dc:title,dc:description,prism:doi,citedby-count,prism:coverDate,affiliation,prism:publicationName",
    }
    if settings.search_year_from:
        params["date"] = f"{settings.search_year_from}-{datetime.now().year}"

    sem = semaphore or asyncio.Semaphore(1)
    async with sem:
        payload = await get_with_retry(
            SCOPUS_API_URL,
            client=client,
            params=params,
            headers=headers,
            service_name="Scopus",
            context=keywords,
            inter_attempt_sleep=1.1,
        )
        entries = payload.get("search-results", {}).get("entry", [])
```

Also update the existing call to `_batch_fetch_abstracts` further down in the function. Find:

```python
    if doi_missing:
        abstracts = await _batch_fetch_abstracts(doi_missing)
```

Replace with:

```python
    if doi_missing:
        abstracts = await _batch_fetch_abstracts(doi_missing, client=client)
```

(Only `, client=client` added.)

The rest of the function (papers list construction, ABSTRACT-STAT logger calls, S2 batch recovery loop, final filter return) stays unchanged.

- [ ] **Step 3.3: Update `openalex_agent.py`**

Find the `search_papers_for_indicator` function (around line 53). Replace its signature and the `async with sem:` block. Current shape:

```python
async def search_papers_for_indicator(
    keywords: str,
    max_results: int | None = None,
    semaphore: asyncio.Semaphore | None = None,
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
            params=params,
            service_name="OpenAlex",
            context=keywords,
        )
```

Change to:

```python
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
```

Also restore `import httpx` at the top (currently removed). Find:

```python
import asyncio
import logging
from app.config import settings
from app.agents.country_codes import COUNTRY_CODES
from app.agents._http_retry import get_with_retry
```

Change to:

```python
import asyncio
import logging
import httpx
from app.config import settings
from app.agents.country_codes import COUNTRY_CODES
from app.agents._http_retry import get_with_retry
```

- [ ] **Step 3.4: Syntax-check the three agents**

Run: `docker compose exec api python -c "from app.agents.search_agent import search_papers_for_indicator, search_all_sources; from app.agents.scopus_agent import search_papers_for_indicator as scopus_search; from app.agents.openalex_agent import search_papers_for_indicator as oa_search; print('imports ok')"`
Expected: `imports ok` (no SyntaxError/ImportError).

No commit yet. Continue to Task 4.

---

## Task 4: Update `extraction_agent.py`

**Files:**
- Modify: `backend/app/agents/extraction_agent.py` (`_get_country_from_openalex`, `extract_metrics_from_paper`)

- [ ] **Step 4.1: Update `_get_country_from_openalex`**

Find the function (currently around line 35). Replace its signature and the `async with httpx.AsyncClient(timeout=10) as client:` block. Current:

```python
async def _get_country_from_openalex(doi: str) -> str | None:
    try:
        url = f"https://api.openalex.org/works/doi:{doi}"
        headers = {"User-Agent": "TechSpec/1.0 (mailto:ilhwan.lee@gmail.com)"}
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, headers=headers)
            if r.status_code != 200:
                return None
            data = r.json()
        authorships = data.get("authorships") or []
```

Change to:

```python
async def _get_country_from_openalex(doi: str, *, client: httpx.AsyncClient) -> str | None:
    try:
        url = f"https://api.openalex.org/works/doi:{doi}"
        headers = {"User-Agent": "TechSpec/1.0 (mailto:ilhwan.lee@gmail.com)"}
        r = await client.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        authorships = data.get("authorships") or []
```

Key diffs:
- `*, client: httpx.AsyncClient` added to signature
- `async with httpx.AsyncClient(timeout=10) as client:` block removed
- `client.get(url, headers=headers)` → `client.get(url, headers=headers, timeout=10)`
- indentation of `authorships = data.get(...)` (and everything below it inside the `try`) collapsed one level

The rest of the function body (institutions/country_code extraction, `except Exception: return None`) stays the same — only verify the indentation is consistent throughout.

- [ ] **Step 4.2: Update `extract_metrics_from_paper`**

Find the function (currently around line 58). Replace its signature:

```python
async def extract_metrics_from_paper(
    paper: dict,
    indicators: list[dict],
    semaphore: asyncio.Semaphore | None = None,
) -> list[tuple[int, dict]]:
```

with:

```python
async def extract_metrics_from_paper(
    paper: dict,
    indicators: list[dict],
    semaphore: asyncio.Semaphore | None = None,
    *,
    client: httpx.AsyncClient,
) -> list[tuple[int, dict]]:
```

Then find the inner `_country_coro` helper (currently around line 87):

```python
        async def _country_coro() -> str | None:
            if paper.get("country") is not None:
                return paper["country"]
            if paper.get("country_lookup_done"):
                return None
            return await _get_country_from_openalex(doi) if doi else None
```

Change the last line to pass `client`:

```python
        async def _country_coro() -> str | None:
            if paper.get("country") is not None:
                return paper["country"]
            if paper.get("country_lookup_done"):
                return None
            return await _get_country_from_openalex(doi, client=client) if doi else None
```

- [ ] **Step 4.3: Syntax-check the module**

Run: `docker compose exec api python -c "from app.agents.extraction_agent import extract_metrics_from_paper, _get_country_from_openalex; import inspect; print(inspect.signature(extract_metrics_from_paper)); print(inspect.signature(_get_country_from_openalex))"`
Expected: both signatures end with `client: httpx.AsyncClient)`. No SyntaxError/ImportError.

No commit yet. Continue to Task 5.

---

## Task 5: Replace `httpx_mock_get` fixture with `mock_httpx_client`

**Files:**
- Modify: `backend/tests/conftest.py` (remove `httpx_mock_get`, add `mock_httpx_client`)

- [ ] **Step 5.1: Remove `httpx_mock_get` fixture**

Edit `backend/tests/conftest.py`. Find the existing `httpx_mock_get` fixture (currently at the bottom of the file, starting with `@pytest.fixture` followed by `def httpx_mock_get(monkeypatch):`). Delete the entire fixture (the decorator, the function, and the inner `_make` definition) — typically the last ~24 lines of the file.

- [ ] **Step 5.2: Add `mock_httpx_client` fixture**

Append to the end of `backend/tests/conftest.py`:

```python
import httpx  # noqa: E402  (httpx imported here only for AsyncMock spec)


@pytest.fixture
def mock_httpx_client():
    """Build a mock httpx.AsyncClient-shaped object for DI into agent functions.

    Either supply json_body/status_code for a single mocked response,
    or get_side_effect for sequential / exception scenarios.
    """
    def _make(*, status_code: int = 200, json_body=None, get_side_effect=None) -> AsyncMock:
        client = AsyncMock(spec=httpx.AsyncClient)
        if get_side_effect is not None:
            client.get.side_effect = get_side_effect
        else:
            response = MagicMock()
            response.status_code = status_code
            response.json.return_value = json_body if json_body is not None else {}
            response.raise_for_status = MagicMock()
            client.get.return_value = response
        return client
    return _make
```

Note: `AsyncMock` and `MagicMock` are already imported at the top of `conftest.py` (from Task 2 of the previous cleanup branch). `httpx` is imported here so the fixture's docstring `AsyncMock(spec=httpx.AsyncClient)` can resolve the spec class.

- [ ] **Step 5.3: Verify fixture is discoverable**

Run: `docker compose exec api pytest tests/ --fixtures 2>&1 | grep mock_httpx_client`
Expected: `mock_httpx_client -- tests/conftest.py:...` line printed.

Also verify the old fixture is gone:
Run: `docker compose exec api pytest tests/ --fixtures 2>&1 | grep httpx_mock_get | head -1`
Expected: empty output (no match).

No commit yet. Continue to Task 6.

---

## Task 6: Migrate all test files to new pattern

**Files:**
- Modify: `backend/tests/test_http_retry.py` (6 tests)
- Modify: `backend/tests/test_openalex_agent.py` (5 search tests + 5 unaffected reconstruct tests)
- Modify: `backend/tests/test_scopus_agent.py` (5 tests)
- Modify: `backend/tests/test_search_agent.py` (5 of 7 tests)
- Modify: `backend/tests/test_extraction_agent.py` (4 tests)

Each file becomes a focused step.

- [ ] **Step 6.1: Rewrite `test_http_retry.py`**

Overwrite `backend/tests/test_http_retry.py` with:

```python
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock

from app.agents._http_retry import get_with_retry

pytestmark = pytest.mark.no_db


@pytest.mark.asyncio
async def test_get_with_retry_returns_json_on_200(mock_httpx_client):
    client = mock_httpx_client(json_body={"hello": "world"})

    result = await get_with_retry(
        "http://example.test/api",
        client=client,
        service_name="TestSvc",
        context="kw",
    )
    assert result == {"hello": "world"}


@pytest.mark.asyncio
async def test_get_with_retry_raises_on_max_attempts_429(monkeypatch, mock_httpx_client):
    client = mock_httpx_client(status_code=429)
    monkeypatch.setattr("app.agents._http_retry.asyncio.sleep", AsyncMock())

    with pytest.raises(RuntimeError, match="TestSvc API error 429"):
        await get_with_retry(
            "http://example.test/api",
            client=client,
            service_name="TestSvc",
            context="kw",
        )


@pytest.mark.asyncio
async def test_get_with_retry_wraps_http_status_error(mock_httpx_client):
    response = MagicMock()
    response.status_code = 500
    err = httpx.HTTPStatusError("boom", request=MagicMock(), response=response)
    response.raise_for_status = MagicMock(side_effect=err)
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get.return_value = response

    with pytest.raises(RuntimeError, match="TestSvc API error 500"):
        await get_with_retry(
            "http://example.test/api",
            client=client,
            service_name="TestSvc",
            context="kw",
        )


@pytest.mark.asyncio
async def test_get_with_retry_wraps_timeout(mock_httpx_client):
    client = mock_httpx_client(get_side_effect=httpx.TimeoutException("slow"))

    with pytest.raises(RuntimeError, match="TestSvc API timeout for: kw"):
        await get_with_retry(
            "http://example.test/api",
            client=client,
            service_name="TestSvc",
            context="kw",
        )


@pytest.mark.asyncio
async def test_get_with_retry_succeeds_after_429(monkeypatch, mock_httpx_client):
    r429 = MagicMock()
    r429.status_code = 429
    r200 = MagicMock()
    r200.status_code = 200
    r200.json.return_value = {"ok": True}
    r200.raise_for_status = MagicMock()
    client = mock_httpx_client(get_side_effect=[r429, r200])
    monkeypatch.setattr("app.agents._http_retry.asyncio.sleep", AsyncMock())

    result = await get_with_retry(
        "http://example.test/api",
        client=client,
        service_name="TestSvc",
        context="kw",
    )
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_get_with_retry_wraps_request_error(mock_httpx_client):
    client = mock_httpx_client(get_side_effect=httpx.ConnectError("dns fail"))

    with pytest.raises(RuntimeError, match="TestSvc network error: kw"):
        await get_with_retry(
            "http://example.test/api",
            client=client,
            service_name="TestSvc",
            context="kw",
        )
```

Key diffs vs current:
- `_patch_client` helper removed — `mock_httpx_client` fixture replaces it for the simple cases.
- The HTTPStatusError test builds its mock client inline because the response needs a non-default `raise_for_status` side_effect that the fixture doesn't expose.
- Every call to `get_with_retry` now passes `client=client`.

- [ ] **Step 6.2: Rewrite `test_openalex_agent.py`**

Overwrite `backend/tests/test_openalex_agent.py` with:

```python
import pytest
from unittest.mock import AsyncMock
from app.agents.openalex_agent import _reconstruct_abstract, search_papers_for_indicator

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
    assert _reconstruct_abstract(inv_idx) == "the memory is fast the memory"


def test_reconstruct_abstract_none_returns_empty():
    assert _reconstruct_abstract(None) == ""


def test_reconstruct_abstract_empty_dict_returns_empty():
    assert _reconstruct_abstract({}) == ""


def test_reconstruct_abstract_handles_gaps():
    inv_idx = {"word_a": [0], "word_b": [10]}
    assert _reconstruct_abstract(inv_idx) == "word_a word_b"


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
async def test_search_returns_normalized_papers(mock_httpx_client):
    client = mock_httpx_client(json_body=MOCK_OPENALEX_RESPONSE)
    results = await search_papers_for_indicator("HBM bandwidth", max_results=5, client=client)

    assert len(results) == 1
    p = results[0]
    assert p["title"] == "HBM3E High Bandwidth Memory"
    assert p["abstract"] == "We present HBM3E"
    assert p["doi"] == "10.1109/test.2024.001"
    assert p["year"] == 2024
    assert p["citation_count"] == 45
    assert p["country"] == "South Korea"
    assert p["journal_name"] == "IEEE JSSC"


@pytest.mark.asyncio
async def test_search_filters_entries_without_abstract(mock_httpx_client):
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
    client = mock_httpx_client(json_body=no_abs)
    results = await search_papers_for_indicator("test", max_results=5, client=client)
    assert results == []


@pytest.mark.asyncio
async def test_search_raises_on_429(monkeypatch, mock_httpx_client):
    monkeypatch.setattr("app.agents._http_retry.asyncio.sleep", AsyncMock())
    client = mock_httpx_client(status_code=429)
    with pytest.raises(RuntimeError, match="OpenAlex API error 429"):
        await search_papers_for_indicator("HBM bandwidth", client=client)


@pytest.mark.asyncio
async def test_search_country_none_when_no_institutions(mock_httpx_client):
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
    client = mock_httpx_client(json_body=no_inst)
    results = await search_papers_for_indicator("test", max_results=5, client=client)
    assert results[0]["country"] is None
    assert results[0]["journal_name"] is None


@pytest.mark.asyncio
async def test_search_uses_cited_by_count_sort(mock_httpx_client):
    client = mock_httpx_client(json_body={"results": []})
    await search_papers_for_indicator("test", max_results=5, client=client)

    _, kwargs = client.get.call_args
    assert kwargs.get("params", {}).get("sort") == "cited_by_count:desc"
```

Key diffs vs current:
- `httpx_mock_get` fixture replaced with `mock_httpx_client`
- Each search test now creates a client locally and passes `client=client` to `search_papers_for_indicator`
- The sort-param test inspects `client.get.call_args` (same pattern as before, against the mock client object)
- `monkeypatch.setattr("app.agents._http_retry.asyncio.sleep", ...)` unchanged — sleep still happens in `_http_retry`

- [ ] **Step 6.3: Rewrite `test_scopus_agent.py`**

Overwrite `backend/tests/test_scopus_agent.py` with:

```python
import pytest
from unittest.mock import AsyncMock
from app.agents.scopus_agent import search_papers_for_indicator

pytestmark = pytest.mark.no_db


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
async def test_search_returns_normalized_papers(mock_httpx_client):
    client = mock_httpx_client(json_body=MOCK_SCOPUS_RESPONSE)
    results = await search_papers_for_indicator("HBM bandwidth", max_results=5, client=client)

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
async def test_search_country_none_when_no_affiliation(mock_httpx_client):
    client = mock_httpx_client(json_body=MOCK_SCOPUS_NO_AFFILIATION)
    results = await search_papers_for_indicator("test keyword", max_results=5, client=client)
    assert results[0]["country"] is None


@pytest.mark.asyncio
async def test_search_filters_entries_without_abstract(mock_httpx_client):
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
    client = mock_httpx_client(json_body=no_abstract_response)
    results = await search_papers_for_indicator("test", max_results=5, client=client)
    assert results == []


@pytest.mark.asyncio
async def test_search_raises_on_429(monkeypatch, mock_httpx_client):
    monkeypatch.setattr("app.agents._http_retry.asyncio.sleep", AsyncMock())
    client = mock_httpx_client(status_code=429)
    with pytest.raises(RuntimeError, match="Scopus API error 429"):
        await search_papers_for_indicator("HBM bandwidth", client=client)


@pytest.mark.asyncio
async def test_search_handles_single_affiliation_as_dict(monkeypatch, mock_httpx_client):
    monkeypatch.setattr("app.agents._http_retry.asyncio.sleep", AsyncMock())
    single_aff_response = {
        "search-results": {
            "entry": [
                {
                    "dc:identifier": "SCOPUS_ID:2",
                    "dc:title": "Single Affiliation Paper",
                    "dc:description": "Abstract content here.",
                    "prism:doi": "10.1/single",
                    "citedby-count": "5",
                    "prism:coverDate": "2024-01-01",
                    "affiliation": {
                        "affiliation-country": "Japan",
                        "affilname": "RIKEN",
                    },
                }
            ]
        }
    }
    client = mock_httpx_client(json_body=single_aff_response)
    results = await search_papers_for_indicator("test", max_results=5, client=client)
    assert results[0]["country"] == "Japan"
```

Same migration pattern as 6.2. Note that scopus's `_batch_fetch_abstracts` is invoked only when there are abstracts to recover; these tests use abstracts already populated in the mock response, so the POST path is not exercised. No additional `client.post` mocking needed.

- [ ] **Step 6.4: Rewrite `test_search_agent.py`**

Overwrite `backend/tests/test_search_agent.py` with:

```python
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock
from app.agents.search_agent import search_papers_for_indicator, search_all_sources

pytestmark = pytest.mark.no_db

MOCK_SS_RESPONSE = {
    "data": [
        {
            "paperId": "abc123",
            "title": "HBM3E: High Bandwidth Memory",
            "abstract": "We present HBM3E achieving 1.2 TB/s bandwidth...",
            "year": 2024,
            "citationCount": 45,
            "externalIds": {"DOI": "10.1109/test.2024.001"},
        }
    ]
}


@pytest.mark.asyncio
async def test_search_returns_list_of_papers(mock_httpx_client):
    client = mock_httpx_client(json_body=MOCK_SS_RESPONSE)
    results = await search_papers_for_indicator("HBM bandwidth GB/s", max_results=5, client=client)

    assert isinstance(results, list)
    assert len(results) >= 1
    assert "title" in results[0]
    assert "abstract" in results[0]


@pytest.mark.asyncio
async def test_search_filters_empty_abstracts(mock_httpx_client):
    payload = {
        "data": [
            {"paperId": "x1", "title": "Paper 1", "abstract": None, "year": 2023, "citationCount": 10, "externalIds": {}},
            {"paperId": "x2", "title": "Paper 2", "abstract": "actual content with values", "year": 2023, "citationCount": 10, "externalIds": {}},
        ]
    }
    client = mock_httpx_client(json_body=payload)
    results = await search_papers_for_indicator("test keyword", max_results=5, client=client)
    assert all(r["abstract"] for r in results)


@pytest.mark.asyncio
async def test_search_raises_on_http_error(monkeypatch, mock_httpx_client):
    monkeypatch.setattr("app.agents._http_retry.asyncio.sleep", AsyncMock())
    err = httpx.HTTPStatusError(
        "429 Too Many Requests",
        request=MagicMock(),
        response=MagicMock(status_code=429),
    )
    client = mock_httpx_client(get_side_effect=err)
    with pytest.raises(RuntimeError, match="Semantic Scholar"):
        await search_papers_for_indicator("HBM bandwidth", client=client)


@pytest.mark.asyncio
async def test_search_raises_on_timeout(monkeypatch, mock_httpx_client):
    monkeypatch.setattr("app.agents._http_retry.asyncio.sleep", AsyncMock())
    client = mock_httpx_client(get_side_effect=httpx.TimeoutException("timeout"))
    with pytest.raises(RuntimeError, match="timeout"):
        await search_papers_for_indicator("HBM bandwidth", client=client)


@pytest.mark.asyncio
async def test_search_all_sources_uses_scopus_when_specified(mock_httpx_client, monkeypatch):
    captured = {}
    async def fake_scopus(*args, **kwargs):
        captured["called"] = True
        captured["client"] = kwargs.get("client")
        return [{"title": "Scopus Paper", "abstract": "abstract", "doi": None,
                 "year": 2024, "citation_count": 10, "paper_id": "S1", "country": "USA"}]
    from app.agents import search_agent
    monkeypatch.setattr(search_agent.scopus_agent, "search_papers_for_indicator", fake_scopus)
    client = mock_httpx_client()
    results = await search_all_sources("HBM", source="scopus", max_results=5, client=client)

    assert captured["called"] is True
    assert captured["client"] is client
    assert results[0]["title"] == "Scopus Paper"


@pytest.mark.asyncio
async def test_search_all_sources_uses_semantic_scholar_by_default(mock_httpx_client):
    client = mock_httpx_client(json_body=MOCK_SS_RESPONSE)
    results = await search_all_sources("HBM", max_results=5, client=client)
    assert results[0]["title"] == "HBM3E: High Bandwidth Memory"


@pytest.mark.asyncio
async def test_search_all_sources_uses_openalex_when_specified(mock_httpx_client, monkeypatch):
    captured = {}
    async def fake_openalex(*args, **kwargs):
        captured["called"] = True
        captured["client"] = kwargs.get("client")
        return [{"title": "OpenAlex Paper", "abstract": "abstract", "doi": "10.x/y",
                 "year": 2024, "citation_count": 12, "paper_id": "OA1", "country": "South Korea",
                 "journal_name": "Nature"}]
    from app.agents import search_agent
    monkeypatch.setattr(search_agent.openalex_agent, "search_papers_for_indicator", fake_openalex)
    client = mock_httpx_client()
    results = await search_all_sources("HBM", source="openalex", max_results=5, client=client)

    assert captured["called"] is True
    assert captured["client"] is client
    assert results[0]["title"] == "OpenAlex Paper"
```

Key diffs vs current:
- `with patch("app.agents._http_retry.httpx.AsyncClient") as mock_client_class:` blocks removed entirely.
- HTTP-error and timeout tests use `mock_httpx_client(get_side_effect=...)` instead of patching the client class.
- The two dispatcher tests (`uses_scopus`, `uses_openalex`) replace `with patch("app.agents.search_agent.scopus_agent") as mock_scopus:` with `monkeypatch.setattr` against the module's attribute, and they additionally verify that the dispatcher correctly threads the `client` argument through to the dispatched agent (`captured["client"] is client`). This is new coverage that protects the DI plumbing.
- `pytestmark = pytest.mark.no_db` added at module level (was missing from the pre-A2 file).

- [ ] **Step 6.5: Rewrite `test_extraction_agent.py`**

Overwrite `backend/tests/test_extraction_agent.py` with:

```python
import json
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.extraction_agent import extract_metrics_from_paper

pytestmark = pytest.mark.no_db


PAPER_WITH_VALUE = {
    "title": "HBM3E achieves record bandwidth",
    "abstract": "In this paper, we present HBM3E achieving 1,228 GB/s bandwidth with 12 stacked dies. Fabricated by SK Hynix in Korea, presented at ISSCC 2024.",
    "year": 2024,
    "doi": "10.1109/isscc.2024.001",
    "citation_count": 45,
}

PAPER_WITHOUT_VALUE = {
    "title": "Overview of memory technology",
    "abstract": "This paper provides an overview of memory technology trends without specific measurements in 2023.",
    "year": 2023,
    "doi": None,
    "citation_count": 5,
}

INDICATOR_BANDWIDTH = {"id": 1, "name": "대역폭", "unit": "GB/s"}


def _gemini_response(payload: list[dict]) -> MagicMock:
    response = MagicMock()
    response.text = json.dumps(payload)
    return response


def _client() -> AsyncMock:
    return AsyncMock(spec=httpx.AsyncClient)


@pytest.mark.asyncio
async def test_extracts_value_from_paper():
    gemini_payload = [{
        "indicator_id": 1,
        "value": 1228.0,
        "unit": "GB/s",
        "confidence_score": 0.92,
        "quote": "HBM3E achieving 1,228 GB/s bandwidth",
    }]
    with patch("app.agents.extraction_agent.genai_client") as mock_client, \
         patch("app.agents.extraction_agent._get_country_from_openalex",
               new=AsyncMock(return_value="South Korea")):
        mock_client.models.generate_content.return_value = _gemini_response(gemini_payload)
        results = await extract_metrics_from_paper(PAPER_WITH_VALUE, [INDICATOR_BANDWIDTH], client=_client())

    assert len(results) == 1
    ind_id, payload = results[0]
    assert ind_id == 1
    assert payload["value"] == 1228.0
    assert payload["unit"] == "GB/s"
    assert payload["confidence_score"] == 0.92
    assert payload["country"] == "South Korea"


@pytest.mark.asyncio
async def test_returns_empty_when_no_value_found():
    with patch("app.agents.extraction_agent.genai_client") as mock_client, \
         patch("app.agents.extraction_agent._get_country_from_openalex",
               new=AsyncMock(return_value=None)):
        mock_client.models.generate_content.return_value = _gemini_response([])
        results = await extract_metrics_from_paper(PAPER_WITHOUT_VALUE, [INDICATOR_BANDWIDTH], client=_client())

    mock_client.models.generate_content.assert_called_once()
    assert results == []


@pytest.mark.asyncio
async def test_skips_openalex_when_country_already_set():
    paper_with_country = {
        **PAPER_WITH_VALUE,
        "country": "South Korea",
    }
    gemini_payload = [{
        "indicator_id": 1,
        "value": 1228.0,
        "unit": "GB/s",
        "confidence_score": 0.9,
        "quote": "1.2 TB/s",
    }]
    with patch("app.agents.extraction_agent.genai_client") as mock_client, \
         patch("app.agents.extraction_agent._get_country_from_openalex",
               new=AsyncMock()) as mock_openalex:
        mock_client.models.generate_content.return_value = _gemini_response(gemini_payload)
        results = await extract_metrics_from_paper(paper_with_country, [INDICATOR_BANDWIDTH], client=_client())

    mock_openalex.assert_not_called()
    _, payload = results[0]
    assert payload["country"] == "South Korea"


@pytest.mark.asyncio
async def test_skips_openalex_when_country_lookup_done():
    paper_lookup_done = {
        **PAPER_WITH_VALUE,
        "country": None,
        "country_lookup_done": True,
    }
    gemini_payload = [{
        "indicator_id": 1,
        "value": 1228.0,
        "unit": "GB/s",
        "confidence_score": 0.9,
        "quote": "1.2 TB/s",
    }]
    with patch("app.agents.extraction_agent.genai_client") as mock_client, \
         patch("app.agents.extraction_agent._get_country_from_openalex",
               new=AsyncMock()) as mock_openalex:
        mock_client.models.generate_content.return_value = _gemini_response(gemini_payload)
        results = await extract_metrics_from_paper(paper_lookup_done, [INDICATOR_BANDWIDTH], client=_client())

    mock_openalex.assert_not_called()
    _, payload = results[0]
    assert payload["country"] is None
```

Key diffs vs current:
- Added `import httpx` and the `_client()` helper that returns a `AsyncMock(spec=httpx.AsyncClient)`.
- Each call to `extract_metrics_from_paper` now passes `client=_client()`.
- `_get_country_from_openalex` is still patched, so the `client` arg passed into it is ignored — but the outer function signature requires `client` to be present, hence `_client()`.

---

## Task 7: Full regression + atomic commit

**Files:** none (verification + commit only)

- [ ] **Step 7.1: Full test sweep**

Run: `docker compose exec api pytest tests/ -v 2>&1 | tail -10`
Expected: **39 passed** (matches Task 0 baseline). If any test fails, STOP and diagnose — do not commit broken work.

- [ ] **Step 7.2: Confirm working tree contains only this plan's files**

Run: `git status --short | grep -v '\.pyc' | grep -v dockerbuild.bat`
Expected: exactly these 12 lines (order may vary):
```
 M backend/app/agents/_http_retry.py
 M backend/app/agents/extraction_agent.py
 M backend/app/agents/openalex_agent.py
 M backend/app/agents/pipeline.py
 M backend/app/agents/scopus_agent.py
 M backend/app/agents/search_agent.py
 M backend/tests/conftest.py
 M backend/tests/test_extraction_agent.py
 M backend/tests/test_http_retry.py
 M backend/tests/test_openalex_agent.py
 M backend/tests/test_scopus_agent.py
 M backend/tests/test_search_agent.py
```

If anything else appears (other than pre-existing `scopus_agent.py` user changes — which should already be on master from the previous merge), STOP and reconcile.

- [ ] **Step 7.3: Stage exactly the 12 files**

```bash
git add backend/app/agents/_http_retry.py \
        backend/app/agents/extraction_agent.py \
        backend/app/agents/openalex_agent.py \
        backend/app/agents/pipeline.py \
        backend/app/agents/scopus_agent.py \
        backend/app/agents/search_agent.py \
        backend/tests/conftest.py \
        backend/tests/test_extraction_agent.py \
        backend/tests/test_http_retry.py \
        backend/tests/test_openalex_agent.py \
        backend/tests/test_scopus_agent.py \
        backend/tests/test_search_agent.py
```

- [ ] **Step 7.4: Commit**

```bash
git commit -m "refactor(agents): share httpx.AsyncClient across pipeline via DI

run_pipeline now opens a single httpx.AsyncClient and threads it through
search_node, extract_node, the three search agents, get_with_retry,
_batch_fetch_abstracts, extract_metrics_from_paper, and
_get_country_from_openalex. Client lifecycle is bounded by the Celery
task's asyncio.run(run_pipeline(...)) invocation, so each task gets a
fresh client tied to its own event loop. Largest win is the OpenAlex DOI
lookup in extraction_agent, where one TCP+TLS handshake now serves every
paper in a pipeline run.

Tests migrated from monkeypatching module-level httpx.AsyncClient to
constructing AsyncMock(spec=httpx.AsyncClient) clients and passing them
as keyword arguments. Replaces httpx_mock_get fixture with
mock_httpx_client. Adds coverage that search_all_sources threads the
client argument through to the dispatched agent."
```

- [ ] **Step 7.5: Verify the commit**

Run: `git show HEAD --stat`
Expected: 12 files changed, the commit message visible.

Run: `docker compose exec api pytest tests/ -v 2>&1 | tail -3`
Expected: **39 passed**.

---

## Task 8: Update follow-up document

**Files:**
- Modify: `docs/260513-further-jobs.md`

- [ ] **Step 8.1: Update A section status**

Edit `docs/260513-further-jobs.md`. Find the existing line:

```markdown
> **Status (2026-05-14):** A1, A4 완료 — `chore/further-jobs-cleanup` 브랜치. A2, A3은 미해결.
```

Replace with:

```markdown
> **Status (2026-05-14):** A1, A2, A4 완료 — A2는 `chore/a2-shared-httpx-client` 브랜치. A3은 미해결.
```

- [ ] **Step 8.2: Commit the status update**

```bash
git add docs/260513-further-jobs.md
git commit -m "docs: mark A2 done in follow-up status"
```

- [ ] **Step 8.3: Final verification**

Run: `git log --oneline master..HEAD`
Expected: exactly 2 commits — `refactor(agents): share httpx.AsyncClient ...` and `docs: mark A2 done ...`.

Run: `docker compose exec api pytest tests/ -v 2>&1 | tail -3`
Expected: 39 passed.

---

## Notes for the executing engineer

- **Working directory**: `C:\Users\ilhwa\Downloads\_cursors\17_Spec-investigation`. pytest runs inside the api container with paths relative to `/app/backend` — use `tests/...` not `backend/tests/...`.
- **No intermediate commits**: Tasks 1-6 leave the tree in a broken state. Only Task 7 commits. If you must pause and resume, leave the working tree dirty — do not commit a partial migration.
- **Pre-existing scopus_agent.py changes**: The merged `master` already contains the user's `[ABSTRACT-STAT]` logger.info additions in `scopus_agent.py`. They are part of `_batch_fetch_abstracts` and `search_papers_for_indicator` callers but not inside the retry loop. When you edit `search_papers_for_indicator` per Step 3.2, leave the logger calls intact.
- **Keyword-only signatures**: Every new `client` parameter is placed after `*,` so callers must use `client=client`. Existing positional callers (e.g., `extract_metrics_from_paper(paper, indicators, semaphore)`) need only add the kwarg, not reorder.
- **Pyright noise**: The host's Pyright will report false-positive `app.agents.* could not be resolved` errors during this work. Ignore — only pytest output is authoritative.
- **If `pytest` fails at Step 7.1**: read the first failure carefully. The most likely cause is a forgotten `client=client` somewhere in the call chain — grep for `_get_country_from_openalex(`, `_batch_fetch_abstracts(`, `get_with_retry(`, `extract_metrics_from_paper(`, `search_papers_for_indicator(` across the modified files and verify each call site passes `client=client`.
