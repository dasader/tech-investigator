# Further-Jobs Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve the safe-scope follow-ups (B1 + A1 + A4) from `docs/260513-further-jobs.md` on branch `chore/further-jobs-cleanup` as three commits.

**Architecture:** Three independent refactors landed sequentially on one branch — (1) repair an outdated test file, (2) extract a shared httpx mock fixture, (3) extract an HTTP retry helper with per-service policy parameters.

**Tech Stack:** Python 3.x, FastAPI, pytest + pytest-asyncio, httpx, Celery, Docker Compose. Spec: `docs/superpowers/specs/2026-05-13-further-jobs-cleanup-design.md`.

**Test invocation:** All pytest commands run inside the API container — `docker compose exec api pytest ...`. The host machine cannot import the app (celery + DB deps).

---

## Pre-flight

### Task 0: Branch setup

**Files:** none (git operation)

- [ ] **Step 0.1: Verify clean repo state on master**

Run: `git status --short`
Expected: only pre-existing `.pyc` / `dockerbuild.bat` / `backend/app/agents/scopus_agent.py` noise (untouched). No staged or working-tree changes in files this plan will modify.

- [ ] **Step 0.2: Create implementation branch**

Run: `git checkout -b chore/further-jobs-cleanup`
Expected: `Switched to a new branch 'chore/further-jobs-cleanup'`

- [ ] **Step 0.3: Confirm Docker services are up**

Run: `docker compose ps`
Expected: `api`, `db`, `redis` containers in `running` state. If not, run `docker compose up -d` and wait for healthchecks.

---

## Task 1: B1 — Repair `test_extraction_agent.py`

**Files:**
- Modify: `backend/tests/test_extraction_agent.py` (full rewrite, 4 cases)

The current test file imports a non-existent symbol (`extract_metric_from_paper`); the real function is `extract_metrics_from_paper` with a different signature (`paper, indicators: list[dict], semaphore`) returning `list[tuple[int, dict]]`. Country is resolved via `paper["country"]` → `paper["country_lookup_done"]` → `_get_country_from_openalex(doi)`.

- [ ] **Step 1.1: Run the existing tests to confirm the import failure**

Run: `docker compose exec api pytest backend/tests/test_extraction_agent.py -v`
Expected: collection error — `ImportError: cannot import name 'extract_metric_from_paper' from 'app.agents.extraction_agent'`.

- [ ] **Step 1.2: Replace the test file with the new batch-signature tests**

Overwrite `backend/tests/test_extraction_agent.py` with:

```python
import json
import pytest
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
        results = await extract_metrics_from_paper(PAPER_WITH_VALUE, [INDICATOR_BANDWIDTH])

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
        results = await extract_metrics_from_paper(PAPER_WITHOUT_VALUE, [INDICATOR_BANDWIDTH])

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
        results = await extract_metrics_from_paper(paper_with_country, [INDICATOR_BANDWIDTH])

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
        results = await extract_metrics_from_paper(paper_lookup_done, [INDICATOR_BANDWIDTH])

    mock_openalex.assert_not_called()
    _, payload = results[0]
    assert payload["country"] is None
```

- [ ] **Step 1.3: Run the new tests**

Run: `docker compose exec api pytest backend/tests/test_extraction_agent.py -v`
Expected: 4 passed.

- [ ] **Step 1.4: Commit**

```bash
git add backend/tests/test_extraction_agent.py
git commit -m "fix(tests): repair extraction_agent test imports and batch signature

The tests still referenced extract_metric_from_paper (singular) after the
function was renamed and reshaped into extract_metrics_from_paper(paper,
indicators: list[dict], semaphore) -> list[tuple[int, dict]]. Rewrite the
four cases against the current batch signature and add coverage for the
country_lookup_done shortcut introduced by the OpenAlex integration."
```

---

## Task 2: A4 — Add `httpx_mock_get` fixture and migrate tests

**Files:**
- Modify: `backend/tests/conftest.py` (add fixture + imports)
- Modify: `backend/tests/test_openalex_agent.py` (5 cases use new fixture, drop mock imports)
- Modify: `backend/tests/test_scopus_agent.py` (5 cases use new fixture, add `no_db` marker, drop mock imports)

- [ ] **Step 2.1: Run agent tests to capture the green baseline before refactoring**

Run: `docker compose exec api pytest backend/tests/test_openalex_agent.py backend/tests/test_scopus_agent.py -v`
Expected: all currently-passing tests pass (5 openalex search + 5 scopus + 5 openalex pure-unit reconstruct = 15 total green). Note the count for the post-migration comparison.

- [ ] **Step 2.2: Add the fixture to `conftest.py`**

Edit `backend/tests/conftest.py` — add at the bottom of the file:

```python
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def httpx_mock_get(monkeypatch):
    """Patch httpx.AsyncClient in the given agent module so client.get(...)
    returns a mocked response. Returns the mock_client for call_args inspection.

    Usage:
        client = httpx_mock_get("app.agents.openalex_agent",
                                json_body={"results": [...]})
        # ...run code under test...
        client.get.assert_called_once()
    """
    def _make(module_path: str, *, status_code: int = 200, json_body=None):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = status_code
        mock_response.json.return_value = json_body if json_body is not None else {}
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        mock_client_class = MagicMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        monkeypatch.setattr(f"{module_path}.httpx.AsyncClient", mock_client_class)
        return mock_client
    return _make
```

- [ ] **Step 2.3: Verify the fixture is discoverable**

Run: `docker compose exec api pytest backend/tests/test_openalex_agent.py --fixtures 2>&1 | grep httpx_mock_get`
Expected: `httpx_mock_get -- conftest.py:...` line printed. (No-match means the fixture isn't picked up — re-check the edit.)

- [ ] **Step 2.4: Migrate `test_openalex_agent.py` to the fixture**

Replace the contents of `backend/tests/test_openalex_agent.py` with:

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
async def test_search_returns_normalized_papers(httpx_mock_get):
    httpx_mock_get("app.agents.openalex_agent", json_body=MOCK_OPENALEX_RESPONSE)
    results = await search_papers_for_indicator("HBM bandwidth", max_results=5)

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
async def test_search_filters_entries_without_abstract(httpx_mock_get):
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
    httpx_mock_get("app.agents.openalex_agent", json_body=no_abs)
    results = await search_papers_for_indicator("test", max_results=5)
    assert results == []


@pytest.mark.asyncio
async def test_search_raises_on_429(httpx_mock_get, monkeypatch):
    monkeypatch.setattr("app.agents.openalex_agent.asyncio.sleep", AsyncMock())
    httpx_mock_get("app.agents.openalex_agent", status_code=429)
    with pytest.raises(RuntimeError, match="OpenAlex API error 429"):
        await search_papers_for_indicator("HBM bandwidth")


@pytest.mark.asyncio
async def test_search_country_none_when_no_institutions(httpx_mock_get):
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
    httpx_mock_get("app.agents.openalex_agent", json_body=no_inst)
    results = await search_papers_for_indicator("test", max_results=5)
    assert results[0]["country"] is None
    assert results[0]["journal_name"] is None


@pytest.mark.asyncio
async def test_search_uses_cited_by_count_sort(httpx_mock_get):
    mock_client = httpx_mock_get("app.agents.openalex_agent", json_body={"results": []})
    await search_papers_for_indicator("test", max_results=5)

    _, kwargs = mock_client.get.call_args
    assert kwargs.get("params", {}).get("sort") == "cited_by_count:desc"
```

- [ ] **Step 2.5: Verify openalex tests pass**

Run: `docker compose exec api pytest backend/tests/test_openalex_agent.py -v`
Expected: 10 passed (5 reconstruct + 5 search).

- [ ] **Step 2.6: Migrate `test_scopus_agent.py` to the fixture (and add `no_db` marker)**

Replace the contents of `backend/tests/test_scopus_agent.py` with:

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
async def test_search_returns_normalized_papers(httpx_mock_get):
    httpx_mock_get("app.agents.scopus_agent", json_body=MOCK_SCOPUS_RESPONSE)
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
async def test_search_country_none_when_no_affiliation(httpx_mock_get):
    httpx_mock_get("app.agents.scopus_agent", json_body=MOCK_SCOPUS_NO_AFFILIATION)
    results = await search_papers_for_indicator("test keyword", max_results=5)
    assert results[0]["country"] is None


@pytest.mark.asyncio
async def test_search_filters_entries_without_abstract(httpx_mock_get):
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
    httpx_mock_get("app.agents.scopus_agent", json_body=no_abstract_response)
    results = await search_papers_for_indicator("test", max_results=5)
    assert results == []


@pytest.mark.asyncio
async def test_search_raises_on_429(httpx_mock_get, monkeypatch):
    monkeypatch.setattr("app.agents.scopus_agent.asyncio.sleep", AsyncMock())
    httpx_mock_get("app.agents.scopus_agent", status_code=429)
    with pytest.raises(RuntimeError, match="Scopus API error 429"):
        await search_papers_for_indicator("HBM bandwidth")


@pytest.mark.asyncio
async def test_search_handles_single_affiliation_as_dict(httpx_mock_get, monkeypatch):
    monkeypatch.setattr("app.agents.scopus_agent.asyncio.sleep", AsyncMock())
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
    httpx_mock_get("app.agents.scopus_agent", json_body=single_aff_response)
    results = await search_papers_for_indicator("test", max_results=5)
    assert results[0]["country"] == "Japan"
```

- [ ] **Step 2.7: Run both migrated test files together**

Run: `docker compose exec api pytest backend/tests/test_openalex_agent.py backend/tests/test_scopus_agent.py -v`
Expected: 15 passed (5 reconstruct + 5 openalex search + 5 scopus search). Counts match Step 2.1 baseline.

- [ ] **Step 2.8: Commit**

```bash
git add backend/tests/conftest.py backend/tests/test_openalex_agent.py backend/tests/test_scopus_agent.py
git commit -m "refactor(tests): extract httpx_mock_get fixture

Move the six-line httpx.AsyncClient mock setup duplicated across ten
search tests into a single conftest fixture. Tests now patch via
monkeypatch and a one-line factory call, and inspect call_args through
the returned mock_client."
```

---

## Task 3: A1 — Extract `get_with_retry` helper and adopt in three agents

**Files:**
- Create: `backend/app/agents/_http_retry.py`
- Create: `backend/tests/test_http_retry.py`
- Modify: `backend/app/agents/search_agent.py:24-45` (retry loop → helper call)
- Modify: `backend/app/agents/scopus_agent.py:105-129` (retry loop → helper call)
- Modify: `backend/app/agents/openalex_agent.py:69-89` (retry loop → helper call)

- [ ] **Step 3.1: Write the failing helper tests**

Create `backend/tests/test_http_retry.py`:

```python
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock

from app.agents._http_retry import get_with_retry

pytestmark = pytest.mark.no_db


def _patch_client(monkeypatch, *, get_side_effect):
    """Patch httpx.AsyncClient in the helper module. `get_side_effect` can be a
    mock_response, a list/iter of responses, or an Exception subclass to raise."""
    mock_client = AsyncMock()
    if isinstance(get_side_effect, list):
        mock_client.get.side_effect = get_side_effect
    elif isinstance(get_side_effect, Exception):
        mock_client.get.side_effect = get_side_effect
    else:
        mock_client.get.return_value = get_side_effect
    mock_client_class = MagicMock()
    mock_client_class.return_value.__aenter__.return_value = mock_client
    monkeypatch.setattr("app.agents._http_retry.httpx.AsyncClient", mock_client_class)
    return mock_client


@pytest.mark.asyncio
async def test_get_with_retry_returns_json_on_200(monkeypatch):
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"hello": "world"}
    response.raise_for_status = MagicMock()
    _patch_client(monkeypatch, get_side_effect=response)

    result = await get_with_retry(
        "http://example.test/api",
        service_name="TestSvc",
        context="kw",
    )
    assert result == {"hello": "world"}


@pytest.mark.asyncio
async def test_get_with_retry_raises_on_max_attempts_429(monkeypatch):
    response = MagicMock()
    response.status_code = 429
    _patch_client(monkeypatch, get_side_effect=response)
    monkeypatch.setattr("app.agents._http_retry.asyncio.sleep", AsyncMock())

    with pytest.raises(RuntimeError, match="TestSvc API error 429"):
        await get_with_retry(
            "http://example.test/api",
            service_name="TestSvc",
            context="kw",
        )


@pytest.mark.asyncio
async def test_get_with_retry_wraps_http_status_error(monkeypatch):
    response = MagicMock()
    response.status_code = 500
    err = httpx.HTTPStatusError("boom", request=MagicMock(), response=response)
    response.raise_for_status = MagicMock(side_effect=err)
    _patch_client(monkeypatch, get_side_effect=response)

    with pytest.raises(RuntimeError, match="TestSvc API error 500"):
        await get_with_retry(
            "http://example.test/api",
            service_name="TestSvc",
            context="kw",
        )


@pytest.mark.asyncio
async def test_get_with_retry_wraps_timeout(monkeypatch):
    _patch_client(monkeypatch, get_side_effect=httpx.TimeoutException("slow"))

    with pytest.raises(RuntimeError, match="TestSvc API timeout for: kw"):
        await get_with_retry(
            "http://example.test/api",
            service_name="TestSvc",
            context="kw",
        )
```

- [ ] **Step 3.2: Run the new tests to confirm they fail (helper missing)**

Run: `docker compose exec api pytest backend/tests/test_http_retry.py -v`
Expected: collection error — `ModuleNotFoundError: No module named 'app.agents._http_retry'`.

- [ ] **Step 3.3: Implement the helper**

Create `backend/app/agents/_http_retry.py`:

```python
import asyncio
import httpx


async def get_with_retry(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    service_name: str,
    context: str = "",
    max_attempts: int = 3,
    timeout: float = 30.0,
    inter_attempt_sleep: float = 0.0,
    retry_status_codes: tuple[int, ...] = (429,),
) -> dict:
    """HTTP GET with retry/backoff. Returns parsed JSON dict.

    Behavior:
      - retry_status_codes: sleep(10 * (attempt+1)) and retry
      - TimeoutException / HTTPStatusError / RequestError → RuntimeError
        with the given service_name and context in the message
      - inter_attempt_sleep > 0: sleep that many seconds after every
        attempt (in finally) to respect per-service rate limits
      - All attempts exhausted on retry_status_codes: raise RuntimeError
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(max_attempts):
            try:
                response = await client.get(url, params=params, headers=headers)
                if response.status_code in retry_status_codes:
                    await asyncio.sleep(10 * (attempt + 1))
                    continue
                response.raise_for_status()
                return response.json()
            except httpx.TimeoutException:
                raise RuntimeError(f"{service_name} API timeout for: {context}")
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

- [ ] **Step 3.4: Run the helper tests**

Run: `docker compose exec api pytest backend/tests/test_http_retry.py -v`
Expected: 4 passed.

- [ ] **Step 3.5: Adopt the helper in `openalex_agent.py`**

Edit `backend/app/agents/openalex_agent.py`.

Replace the import block at the top (currently lines 1-5):
```python
import asyncio
import logging
import httpx
from app.config import settings
from app.agents.country_codes import COUNTRY_CODES
```
with:
```python
import asyncio
import logging
from app.config import settings
from app.agents.country_codes import COUNTRY_CODES
from app.agents._http_retry import get_with_retry
```

Replace the retry loop in `search_papers_for_indicator` (currently the `async with sem: ...else: raise` block at lines 69-89):
```python
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
        else:
            raise RuntimeError(f"OpenAlex API error 429: {keywords}")
```
with:
```python
    sem = semaphore or asyncio.Semaphore(1)
    async with sem:
        data = await get_with_retry(
            OPENALEX_API_URL,
            params=params,
            service_name="OpenAlex",
            context=keywords,
        )
```

- [ ] **Step 3.6: Update the openalex 429 test to patch sleep in the helper module instead of the agent**

The openalex `test_search_raises_on_429` test currently patches `app.agents.openalex_agent.asyncio.sleep`. After adoption, the sleep happens inside `app.agents._http_retry`. Also, the test's `httpx_mock_get` fixture patches `app.agents.openalex_agent.httpx.AsyncClient`, but the helper now calls `httpx.AsyncClient` from `_http_retry`'s namespace — so the mock needs to point at the helper module instead.

Edit `backend/tests/test_openalex_agent.py` — replace the `test_search_raises_on_429` function with:
```python
@pytest.mark.asyncio
async def test_search_raises_on_429(httpx_mock_get, monkeypatch):
    monkeypatch.setattr("app.agents._http_retry.asyncio.sleep", AsyncMock())
    httpx_mock_get("app.agents._http_retry", status_code=429)
    with pytest.raises(RuntimeError, match="OpenAlex API error 429"):
        await search_papers_for_indicator("HBM bandwidth")
```

Update the four remaining openalex search tests so the fixture patches the helper module (this is the location `httpx.AsyncClient` is now invoked from for every openalex call):
- `test_search_returns_normalized_papers`: change `httpx_mock_get("app.agents.openalex_agent", ...)` → `httpx_mock_get("app.agents._http_retry", ...)`
- `test_search_filters_entries_without_abstract`: same change
- `test_search_country_none_when_no_institutions`: same change
- `test_search_uses_cited_by_count_sort`: same change

- [ ] **Step 3.7: Run openalex tests against the adopted helper**

Run: `docker compose exec api pytest backend/tests/test_openalex_agent.py -v`
Expected: 10 passed.

- [ ] **Step 3.8: Adopt the helper in `scopus_agent.py`**

Edit `backend/app/agents/scopus_agent.py`.

Replace the top imports (currently lines 1-5):
```python
import asyncio
from datetime import datetime
import logging
import httpx
from app.config import settings
```
with:
```python
import asyncio
from datetime import datetime
import logging
import httpx
from app.config import settings
from app.agents._http_retry import get_with_retry
```

Replace the retry loop in `search_papers_for_indicator` (currently lines 105-129):
```python
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
```
with:
```python
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

The remaining `httpx.AsyncClient` use inside `_batch_fetch_abstracts` (S2 batch POST) stays untouched — it's a POST with its own try/except shape and a separate concern (see spec §5).

- [ ] **Step 3.9: Update the scopus tests to patch the helper module**

Edit `backend/tests/test_scopus_agent.py` — change every `httpx_mock_get("app.agents.scopus_agent", ...)` to `httpx_mock_get("app.agents._http_retry", ...)`. Five occurrences (all five tests).

For `test_search_raises_on_429`, also change the sleep patch target — replace:
```python
    monkeypatch.setattr("app.agents.scopus_agent.asyncio.sleep", AsyncMock())
```
with:
```python
    monkeypatch.setattr("app.agents._http_retry.asyncio.sleep", AsyncMock())
```

The `test_search_handles_single_affiliation_as_dict` test patches the agent's `asyncio.sleep` to bypass the 1.1s `inter_attempt_sleep` between attempts. After adoption that sleep also moves into the helper. Replace:
```python
    monkeypatch.setattr("app.agents.scopus_agent.asyncio.sleep", AsyncMock())
```
with:
```python
    monkeypatch.setattr("app.agents._http_retry.asyncio.sleep", AsyncMock())
```

- [ ] **Step 3.10: Run scopus tests against the adopted helper**

Run: `docker compose exec api pytest backend/tests/test_scopus_agent.py -v`
Expected: 5 passed.

- [ ] **Step 3.11: Adopt the helper in `search_agent.py`**

Edit `backend/app/agents/search_agent.py`.

Replace the top imports (currently lines 1-4):
```python
import asyncio
import httpx
from app.config import settings
from app.agents import scopus_agent, openalex_agent
```
with:
```python
import asyncio
from app.config import settings
from app.agents import scopus_agent, openalex_agent
from app.agents._http_retry import get_with_retry
```

Replace the retry loop in `search_papers_for_indicator` (currently lines 24-45):
```python
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
            except httpx.HTTPStatusError as e:
                raise RuntimeError(f"Semantic Scholar API error {e.response.status_code}: {keywords}") from e
            except httpx.RequestError as e:
                raise RuntimeError(f"Semantic Scholar network error: {keywords}") from e
            finally:
                await asyncio.sleep(1.1)
        else:
            raise RuntimeError(f"Semantic Scholar API error 429: {keywords}")
```
with:
```python
    sem = semaphore or asyncio.Semaphore(1)
    async with sem:
        payload = await get_with_retry(
            SS_API_URL,
            params=params,
            headers=headers,
            service_name="Semantic Scholar",
            context=keywords,
            inter_attempt_sleep=1.1,
        )
        data = payload.get("data", [])
```

- [ ] **Step 3.12: Migrate `test_search_agent.py` patch targets**

`backend/tests/test_search_agent.py` has 7 tests. Five of them (`test_search_returns_list_of_papers`, `test_search_filters_empty_abstracts`, `test_search_raises_on_http_error`, `test_search_raises_on_timeout`, `test_search_all_sources_uses_semantic_scholar_by_default`) patch `app.agents.search_agent.httpx.AsyncClient` directly. After Task 3 adoption, `httpx.AsyncClient` is invoked from inside `app.agents._http_retry`, so those patches must point at the helper module.

In each of those five tests, change every occurrence of:
```python
with patch("app.agents.search_agent.httpx.AsyncClient") as mock_client_class:
```
to:
```python
with patch("app.agents._http_retry.httpx.AsyncClient") as mock_client_class:
```

For `test_search_raises_on_http_error` and `test_search_raises_on_timeout`, the `mock_client.get.side_effect` setup is unchanged — only the patch target moves.

The other two tests (`test_search_all_sources_uses_scopus_when_specified`, `test_search_all_sources_uses_openalex_when_specified`) patch the agent modules directly and don't hit the helper. Leave them untouched.

Run: `docker compose exec api pytest backend/tests/test_search_agent.py -v`
Expected: 7 passed.

- [ ] **Step 3.13: Full regression sweep**

Run: `docker compose exec api pytest backend/tests/ -v`
Expected: all tests green. Compare totals against pre-Task-3 baseline; the new test_http_retry.py should add 4 passing tests, no regressions elsewhere.

- [ ] **Step 3.14: Commit**

```bash
git add backend/app/agents/_http_retry.py \
        backend/app/agents/search_agent.py \
        backend/app/agents/scopus_agent.py \
        backend/app/agents/openalex_agent.py \
        backend/tests/test_http_retry.py \
        backend/tests/test_search_agent.py \
        backend/tests/test_openalex_agent.py \
        backend/tests/test_scopus_agent.py
git commit -m "refactor(agents): extract get_with_retry helper

Hoist the duplicated 3-attempt httpx.AsyncClient retry loop out of the
three search agents into backend/app/agents/_http_retry.py. The helper
takes service_name, context, and inter_attempt_sleep parameters so each
agent keeps its existing rate-limit cadence (S2/Scopus: 1.1s,
OpenAlex: 0). Side effect: scopus_agent now wraps HTTPStatusError into
RuntimeError consistently with the other two agents (previously it
escaped unwrapped). httpx.AsyncClient is now constructed once per
helper call instead of once per attempt — see follow-up A2 in
docs/260513-further-jobs.md for the next step (module-level client +
lifespan)."
```

---

## Wrap-up

### Task 4: Update follow-up document

**Files:**
- Modify: `docs/260513-further-jobs.md`

- [ ] **Step 4.1: Mark A1, A4, B1 as done in the follow-up log**

Edit `docs/260513-further-jobs.md`.

Replace the section header `## A. Skipped from \`/simplify\` (별도 PR 권장)` with:
```markdown
## A. Skipped from `/simplify` (별도 PR 권장)

> **Status (2026-05-13):** A1 and A4 done on branch `chore/further-jobs-cleanup`. A2 and A3 remain.
```

Replace the section header `## B. 사전 버그 (master 시점부터 존재)` with:
```markdown
## B. 사전 버그 (master 시점부터 존재)

> **Status (2026-05-13):** B1 done on branch `chore/further-jobs-cleanup`.
```

- [ ] **Step 4.2: Commit the status update**

```bash
git add docs/260513-further-jobs.md
git commit -m "docs: mark B1, A1, A4 as completed on cleanup branch"
```

- [ ] **Step 4.3: Final verification**

Run: `git log --oneline master..HEAD`
Expected: exactly 4 commits — `fix(tests): repair extraction_agent test ...`, `refactor(tests): extract httpx_mock_get fixture`, `refactor(agents): extract get_with_retry helper`, `docs: mark B1, A1, A4 as completed ...`.

Run: `docker compose exec api pytest backend/tests/ -v`
Expected: all tests pass, +8 net new (4 extraction + 4 http_retry).

---

## Notes for the executing engineer

- **Working directory**: `C:\Users\ilhwa\Downloads\_cursors\17_Spec-investigation`. All pytest commands run inside the `api` container — never on the host, the host doesn't have celery/postgres deps installed.
- **Pre-existing noise**: `git status` will show modified `.pyc` files and an unrelated `M backend/app/agents/scopus_agent.py` from the user's working tree before Task 0. Don't stage them in your commits; only stage the files this plan touches.
- **Mock target rule**: after Task 3, any test that needs to short-circuit the HTTP retry must patch in `app.agents._http_retry` (both `httpx.AsyncClient` and `asyncio.sleep`), not in the agent module. This is the single biggest source of confusion in Task 3.
- **If a step's `Expected` doesn't match**, stop and report — do not patch-and-continue. The plan assumes each green checkpoint before moving on.
