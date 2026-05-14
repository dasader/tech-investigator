# Multi-Source Combined Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `search_source`를 단일 소스 선택에서 `combined`(OpenAlex + Semantic Scholar 병행) / `scopus` 2지선다로 재편하고, 두 소스 결과를 DOI 기준 필드별 best-of로 병합한다.

**Architecture:** 병합 로직은 `search_agent.py`의 순수 함수 `merge_papers`와 동시 호출 래퍼 `search_combined`에 둔다. `search_all_sources`가 `"combined"` 분기를 디스패치하고, `pipeline.py`의 `SOURCE_PLAN`이 소스별 동시성을 정의한다. 한 소스가 실패해도 다른 소스로 진행한다(그레이스풀 다운).

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, Alembic, pytest/pytest-asyncio, httpx, React/TypeScript (Vite)

**Spec:** `docs/superpowers/specs/2026-05-14-multi-source-search-design.md`

---

## File Structure

| 파일 | 책임 | 태스크 |
|------|------|--------|
| `backend/app/agents/search_agent.py` | `merge_papers`(병합), `search_combined`(동시 호출), `search_all_sources`(디스패치) | 1, 2, 4 |
| `backend/app/agents/pipeline.py` | `SOURCE_PLAN`(소스별 동시성), `search_node` | 4 |
| `backend/app/utils.py` | `get_engine_label`(소스 → 표시 라벨) | 3 |
| `backend/app/schemas/tech_query.py` | `search_source` Literal | 4 |
| `backend/app/models/tech_query.py` | `search_source` 컬럼 server_default | 5 |
| `backend/alembic/versions/<revision>.py` | 기존 행 마이그레이션 | 5 |
| `frontend/src/pages/InputPage.tsx` | 소스 선택 UI | 6 |
| `backend/tests/test_combined_search.py` (신규) | `merge_papers`, `search_combined` 테스트 | 1, 2 |
| `backend/tests/test_utils.py` (신규) | `get_engine_label` 테스트 | 3 |
| `backend/tests/test_search_agent.py` | `search_all_sources` 테스트 갱신 | 4 |
| `backend/tests/test_pipeline.py` | `SOURCE_PLAN` 테스트 (concurrency 테스트 대체) | 4 |

**테스트 실행 주의:** 컨테이너 내부 경로는 `/app`이므로 `docker compose exec api pytest tests/...` (앞에 `backend/` 없음).

---

## Task 1: `merge_papers` 순수 함수

DOI 기준 dedup + 필드별 best-of 병합. DB·네트워크 무의존 순수 함수.

**Files:**
- Modify: `backend/app/agents/search_agent.py` (함수 추가)
- Test: `backend/tests/test_combined_search.py` (신규)

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/test_combined_search.py` 생성:

```python
import pytest
from app.agents.search_agent import merge_papers

pytestmark = pytest.mark.no_db


def _s2(doi=None, title="", abstract="", year=None, citation=0, journal=None):
    return {
        "paper_id": "s2-id", "title": title, "abstract": abstract, "year": year,
        "citation_count": citation, "doi": doi, "journal_name": journal, "country": None,
    }


def _oa(doi=None, title="", abstract="", year=None, citation=0, journal=None, country=None):
    return {
        "paper_id": "oa-id", "title": title, "abstract": abstract, "year": year,
        "citation_count": citation, "doi": doi, "journal_name": journal, "country": country,
        "country_lookup_done": True,
    }


def test_same_doi_merges_field_level_best_of():
    s2 = _s2(doi="10.1/X", title="A", abstract="short", year=2024, citation=5)
    oa = _oa(doi="10.1/x", title="A", abstract="a much longer abstract", year=2024,
             citation=12, journal="Nature", country="South Korea")
    result = merge_papers([s2], [oa])
    assert len(result) == 1
    m = result[0]
    assert m["abstract"] == "a much longer abstract"   # 더 긴 abstract
    assert m["country"] == "South Korea"               # OpenAlex country
    assert m["country_lookup_done"] is True            # OpenAlex 기여 → 전파
    assert m["citation_count"] == 12                   # max
    assert m["journal_name"] == "Nature"               # non-null 우선


def test_dedup_by_title_when_no_doi():
    s2 = _s2(doi=None, title="Same Title", abstract="x", citation=1)
    oa = _oa(doi=None, title="same title", abstract="y", citation=2)
    result = merge_papers([s2], [oa])
    assert len(result) == 1


def test_papers_without_doi_or_title_are_kept():
    s2 = _s2(doi=None, title="", abstract="x")
    oa = _oa(doi=None, title="", abstract="y")
    result = merge_papers([s2], [oa])
    assert len(result) == 2


def test_disjoint_papers_all_kept():
    s2 = _s2(doi="10.1/a", title="A")
    oa = _oa(doi="10.1/b", title="B")
    result = merge_papers([s2], [oa])
    assert len(result) == 2


def test_result_sorted_by_citation_desc():
    low = _s2(doi="10.1/low", title="low", citation=3)
    high = _oa(doi="10.1/high", title="high", citation=99)
    result = merge_papers([low], [high])
    assert [p["citation_count"] for p in result] == [99, 3]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `docker compose exec api pytest tests/test_combined_search.py -v`
Expected: FAIL — `ImportError: cannot import name 'merge_papers'`

- [ ] **Step 3: `merge_papers` 구현**

`backend/app/agents/search_agent.py`의 import 블록 바로 아래(7행 `SS_API_URL` 정의 위)에 추가:

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `docker compose exec api pytest tests/test_combined_search.py -v`
Expected: PASS — 5 passed

- [ ] **Step 5: 커밋**

```bash
git add backend/app/agents/search_agent.py backend/tests/test_combined_search.py
git commit -m "feat(search): add merge_papers for DOI-based field-level merge"
```

---

## Task 2: `search_combined` 동시 검색 + 병합

S2·OpenAlex agent를 동시 호출하고 `merge_papers`로 병합. 그레이스풀 다운.

**Files:**
- Modify: `backend/app/agents/search_agent.py` (함수 추가, `logging` import 추가)
- Test: `backend/tests/test_combined_search.py` (테스트 추가)

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/test_combined_search.py` 끝에 추가:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from app.agents.search_agent import search_combined


def _sem():
    return asyncio.Semaphore(1)


@pytest.mark.asyncio
async def test_search_combined_merges_both_sources():
    s2_papers = [{"paper_id": "s2", "title": "A", "abstract": "x", "year": 2024,
                  "citation_count": 5, "doi": "10.1/a", "journal_name": None, "country": None}]
    oa_papers = [{"paper_id": "oa", "title": "B", "abstract": "y", "year": 2024,
                  "citation_count": 9, "doi": "10.1/b", "journal_name": None,
                  "country": "Japan", "country_lookup_done": True}]
    with patch("app.agents.search_agent.search_papers_for_indicator",
               new=AsyncMock(return_value=s2_papers)), \
         patch("app.agents.search_agent.openalex_agent.search_papers_for_indicator",
               new=AsyncMock(return_value=oa_papers)):
        result = await search_combined(
            "kw", s2_semaphore=_sem(), openalex_semaphore=_sem(), client=MagicMock())
    assert {p["doi"] for p in result} == {"10.1/a", "10.1/b"}


@pytest.mark.asyncio
async def test_search_combined_degrades_when_s2_fails():
    oa_papers = [{"paper_id": "oa", "title": "B", "abstract": "y", "year": 2024,
                  "citation_count": 9, "doi": "10.1/b", "journal_name": None,
                  "country": "Japan", "country_lookup_done": True}]
    with patch("app.agents.search_agent.search_papers_for_indicator",
               new=AsyncMock(side_effect=RuntimeError("S2 down"))), \
         patch("app.agents.search_agent.openalex_agent.search_papers_for_indicator",
               new=AsyncMock(return_value=oa_papers)):
        result = await search_combined(
            "kw", s2_semaphore=_sem(), openalex_semaphore=_sem(), client=MagicMock())
    assert [p["doi"] for p in result] == ["10.1/b"]


@pytest.mark.asyncio
async def test_search_combined_degrades_when_openalex_fails():
    s2_papers = [{"paper_id": "s2", "title": "A", "abstract": "x", "year": 2024,
                  "citation_count": 5, "doi": "10.1/a", "journal_name": None, "country": None}]
    with patch("app.agents.search_agent.search_papers_for_indicator",
               new=AsyncMock(return_value=s2_papers)), \
         patch("app.agents.search_agent.openalex_agent.search_papers_for_indicator",
               new=AsyncMock(side_effect=RuntimeError("OpenAlex down"))):
        result = await search_combined(
            "kw", s2_semaphore=_sem(), openalex_semaphore=_sem(), client=MagicMock())
    assert [p["doi"] for p in result] == ["10.1/a"]


@pytest.mark.asyncio
async def test_search_combined_raises_when_both_fail():
    with patch("app.agents.search_agent.search_papers_for_indicator",
               new=AsyncMock(side_effect=RuntimeError("S2 down"))), \
         patch("app.agents.search_agent.openalex_agent.search_papers_for_indicator",
               new=AsyncMock(side_effect=RuntimeError("OpenAlex down"))):
        with pytest.raises(RuntimeError, match="combined search failed"):
            await search_combined(
                "kw", s2_semaphore=_sem(), openalex_semaphore=_sem(), client=MagicMock())
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `docker compose exec api pytest tests/test_combined_search.py -v`
Expected: FAIL — `ImportError: cannot import name 'search_combined'`

- [ ] **Step 3: `search_combined` 구현**

`backend/app/agents/search_agent.py` 상단 import에 `logging` 추가. 현재 import 블록:

```python
import asyncio
import httpx
from app.config import settings
from app.agents import scopus_agent, openalex_agent
from app.agents._http_retry import get_with_retry
```

다음으로 교체:

```python
import asyncio
import logging
import httpx
from app.config import settings
from app.agents import scopus_agent, openalex_agent
from app.agents._http_retry import get_with_retry

logger = logging.getLogger(__name__)
```

그리고 `search_all_sources` 함수 정의 바로 위에 `search_combined` 추가:

```python
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
        )
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `docker compose exec api pytest tests/test_combined_search.py -v`
Expected: PASS — 9 passed (Task 1의 5개 + Task 2의 4개)

- [ ] **Step 5: 커밋**

```bash
git add backend/app/agents/search_agent.py backend/tests/test_combined_search.py
git commit -m "feat(search): add search_combined with graceful degradation"
```

---

## Task 3: `get_engine_label` 멀티소스 라벨

`get_engine_label`을 `combined`/`scopus` 2값 기준으로 갱신.

**Files:**
- Modify: `backend/app/utils.py:35-40`
- Test: `backend/tests/test_utils.py` (신규)

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/test_utils.py` 생성:

```python
import pytest
from app.utils import get_engine_label

pytestmark = pytest.mark.no_db


def test_engine_label_combined():
    assert get_engine_label("combined") == "OpenAlex + Semantic Scholar + Gemini"


def test_engine_label_scopus():
    assert get_engine_label("scopus") == "Scopus (Elsevier) + Gemini"


def test_engine_label_unknown_defaults_to_combined():
    assert get_engine_label("anything_else") == "OpenAlex + Semantic Scholar + Gemini"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `docker compose exec api pytest tests/test_utils.py -v`
Expected: FAIL — `test_engine_label_combined`이 `"Semantic Scholar + Gemini"`를 반환받아 실패

- [ ] **Step 3: `get_engine_label` 구현**

`backend/app/utils.py:35-40`의 현재 함수:

```python
def get_engine_label(search_source: str) -> str:
    if search_source == "scopus":
        return "Scopus (Elsevier) + Gemini"
    if search_source == "openalex":
        return "OpenAlex + Gemini"
    return "Semantic Scholar + Gemini"
```

다음으로 교체:

```python
def get_engine_label(search_source: str) -> str:
    if search_source == "scopus":
        return "Scopus (Elsevier) + Gemini"
    # combined 및 기타 모든 값(마이그레이션 전 잔존 구값 포함) → 기본 라벨
    return "OpenAlex + Semantic Scholar + Gemini"
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `docker compose exec api pytest tests/test_utils.py -v`
Expected: PASS — 3 passed

- [ ] **Step 5: 커밋**

```bash
git add backend/app/utils.py backend/tests/test_utils.py
git commit -m "feat(utils): combined engine label for multi-source search"
```

---

## Task 4: 인터페이스 스위치오버 (스키마 + `search_all_sources` + `pipeline.py`)

`search_source` Literal, `search_all_sources` 시그니처, `pipeline.py`의 `SOURCE_PLAN`/`search_node`를 한 번에 전환한다. 이 셋은 `test_pipeline.py`의 가드 테스트(`set(SOURCE_PLAN) == literal_sources`)와 `search_all_sources` 호출부(`search_node`)로 서로 결박돼 있어 한 커밋이어야 한다.

**Files:**
- Modify: `backend/app/schemas/tech_query.py:10`
- Modify: `backend/app/agents/search_agent.py:57-69` (`search_all_sources`)
- Modify: `backend/app/agents/pipeline.py:28-60` (`CONCURRENCY`/`_concurrency_for`/`search_node`)
- Test: `backend/tests/test_pipeline.py` (전체 재작성)
- Test: `backend/tests/test_search_agent.py:65-107` (`search_all_sources` 테스트 3개 교체)

- [ ] **Step 1: `test_pipeline.py` 재작성 (실패 테스트)**

`backend/tests/test_pipeline.py` 전체를 다음으로 교체:

```python
import pytest
from app.agents.pipeline import SOURCE_PLAN

pytestmark = pytest.mark.no_db


def test_source_plan_combined():
    assert SOURCE_PLAN["combined"] == {"semantic_scholar": 1, "openalex": 10}


def test_source_plan_scopus():
    assert SOURCE_PLAN["scopus"] == {"scopus": 5}


def test_source_plan_keys_match_schema_literal():
    # SOURCE_PLAN 키가 search_source의 Literal 후보와 정확히 일치하는지 가드 —
    # 스키마에 source가 추가/제거되면 SOURCE_PLAN 불일치를 여기서 잡는다.
    from typing import get_args
    from app.schemas.tech_query import TechQueryCreate

    literal_sources = set(get_args(TechQueryCreate.model_fields["search_source"].annotation))
    assert set(SOURCE_PLAN) == literal_sources
```

- [ ] **Step 2: `test_search_agent.py`의 `search_all_sources` 테스트 교체 (실패 테스트)**

`backend/tests/test_search_agent.py`의 import 줄(3행)을 다음으로 교체:

```python
import asyncio
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch
from app.agents.search_agent import search_papers_for_indicator, search_all_sources
```

그리고 65행부터 끝까지(`test_search_all_sources_uses_scopus_when_specified`, `test_search_all_sources_uses_semantic_scholar_by_default`, `test_search_all_sources_uses_openalex_when_specified` 3개)를 다음으로 교체:

```python
@pytest.mark.asyncio
async def test_search_all_sources_scopus_dispatches(mock_httpx_client, monkeypatch):
    captured = {}
    async def fake_scopus(*args, **kwargs):
        captured["called"] = True
        captured["client"] = kwargs.get("client")
        return [{"title": "Scopus Paper", "abstract": "abstract", "doi": None,
                 "year": 2024, "citation_count": 10, "paper_id": "S1", "country": "USA"}]
    from app.agents import search_agent
    monkeypatch.setattr(search_agent.scopus_agent, "search_papers_for_indicator", fake_scopus)
    client = mock_httpx_client()
    results = await search_all_sources(
        "HBM", source="scopus", max_results=5,
        semaphores={"scopus": asyncio.Semaphore(5)}, client=client)

    assert captured["called"] is True
    assert captured["client"] is client
    assert results[0]["title"] == "Scopus Paper"


@pytest.mark.asyncio
async def test_search_all_sources_combined_dispatches(monkeypatch):
    captured = {}
    async def fake_combined(keywords, *, s2_semaphore, openalex_semaphore, client, max_results=None):
        captured["s2_sem"] = s2_semaphore
        captured["oa_sem"] = openalex_semaphore
        return [{"title": "merged"}]
    from app.agents import search_agent
    monkeypatch.setattr(search_agent, "search_combined", fake_combined)
    s2_sem, oa_sem = asyncio.Semaphore(1), asyncio.Semaphore(10)
    results = await search_all_sources(
        "HBM", source="combined",
        semaphores={"semantic_scholar": s2_sem, "openalex": oa_sem},
        client=MagicMock())

    assert captured["s2_sem"] is s2_sem
    assert captured["oa_sem"] is oa_sem
    assert results[0]["title"] == "merged"


@pytest.mark.asyncio
async def test_search_all_sources_unknown_raises():
    with pytest.raises(ValueError, match="unknown search_source"):
        await search_all_sources("HBM", source="bogus", semaphores={}, client=MagicMock())
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `docker compose exec api pytest tests/test_pipeline.py tests/test_search_agent.py -v`
Expected: FAIL — `test_pipeline.py`는 `ImportError: cannot import name 'SOURCE_PLAN'`, `test_search_agent.py`의 신규 3개는 `search_all_sources`가 `semaphores` 키워드를 모름 (`TypeError`)

- [ ] **Step 4: `schemas/tech_query.py` Literal 변경**

`backend/app/schemas/tech_query.py:10`:

```python
    search_source: Literal["semantic_scholar", "scopus", "openalex"] = "semantic_scholar"
```

다음으로 교체:

```python
    search_source: Literal["combined", "scopus"] = "combined"
```

- [ ] **Step 5: `search_all_sources` 시그니처 변경**

`backend/app/agents/search_agent.py`의 `search_all_sources` 함수(현재 57-69행) 전체를 다음으로 교체:

```python
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
            client=client,
            max_results=max_results,
        )
    raise ValueError(f"unknown search_source: {source!r}")
```

- [ ] **Step 6: `pipeline.py`의 `CONCURRENCY`/`_concurrency_for`를 `SOURCE_PLAN`으로 교체**

`backend/app/agents/pipeline.py`의 현재 28-34행:

```python
# source별 검색 동시성. 각 외부 API의 rate limit보다 보수적으로 잡은
# 운영 목표값이며, 정확한 계약상 한도가 아니다 (한도는 변동될 수 있음).
CONCURRENCY = {"semantic_scholar": 1, "scopus": 5, "openalex": 10}


def _concurrency_for(source: str) -> int:
    return CONCURRENCY.get(source, 1)
```

다음으로 교체:

```python
# search_source → {하위 소스: 동시성 한도}.
# 외부 API rate limit 기반: Semantic Scholar ~1 req/s, OpenAlex ~100 req/s, Scopus ~9 req/s.
SOURCE_PLAN: dict[str, dict[str, int]] = {
    "combined": {"semantic_scholar": 1, "openalex": 10},
    "scopus": {"scopus": 5},
}
```

- [ ] **Step 7: `pipeline.py`의 `search_node` 변경**

`backend/app/agents/pipeline.py`의 `search_node` 함수(현재 44-60행) 전체를 다음으로 교체:

```python
async def search_node(state: PipelineState, db: Session, client: httpx.AsyncClient) -> PipelineState:
    _update_job(db, state["job_id"], 10.0, "논문 검색 중")
    plan = SOURCE_PLAN[state["search_source"]]
    semaphores = {src: asyncio.Semaphore(n) for src, n in plan.items()}
    results = {}
    tasks = [
        search_all_sources(
            ind["search_keywords"] or ind["name"],
            source=state["search_source"],
            semaphores=semaphores,
            client=client,
        )
        for ind in state["indicators"]
    ]
    paper_lists = await asyncio.gather(*tasks)
    for ind, papers in zip(state["indicators"], paper_lists):
        results[ind["id"]] = papers
    return {**state, "search_results": results}
```

- [ ] **Step 8: 테스트 통과 확인**

Run: `docker compose exec api pytest tests/test_pipeline.py tests/test_search_agent.py tests/test_combined_search.py -v`
Expected: PASS — `test_pipeline.py` 3 passed, `test_search_agent.py` 7 passed (기존 S2 테스트 4개 + 신규 3개), `test_combined_search.py` 9 passed

- [ ] **Step 9: 커밋**

```bash
git add backend/app/schemas/tech_query.py backend/app/agents/search_agent.py backend/app/agents/pipeline.py backend/tests/test_pipeline.py backend/tests/test_search_agent.py
git commit -m "feat(search): switch search_source to combined/scopus model"
```

---

## Task 5: 모델 server_default + Alembic 마이그레이션

`search_source` 컬럼의 server_default를 `combined`로 바꾸고, 기존 행(`semantic_scholar`/`openalex`)을 `combined`로 마이그레이션한다.

**주의:** Task 4와 연속으로 실행할 것 — 그 사이에 파이프라인 job을 실행하면 구값(`semantic_scholar` 등) job이 `SOURCE_PLAN[...]`에서 `KeyError`를 낸다.

**Files:**
- Modify: `backend/app/models/tech_query.py:11`
- Create: `backend/alembic/versions/<revision>.py` (alembic이 revision id 생성)

- [ ] **Step 1: 모델 server_default 변경**

`backend/app/models/tech_query.py:11`:

```python
    search_source = Column(String(30), nullable=False, server_default="semantic_scholar")
```

다음으로 교체:

```python
    search_source = Column(String(30), nullable=False, server_default="combined")
```

- [ ] **Step 2: 마이그레이션 파일 스캐폴드 생성**

Run: `docker compose exec api alembic revision -m "migrate search_source to combined"`
Expected: `backend/alembic/versions/<revision>_migrate_search_source_to_combined.py` 생성됨. 출력된 파일 경로를 확인한다.

- [ ] **Step 3: 마이그레이션 `upgrade`/`downgrade` 작성**

Step 2가 생성한 파일의 `upgrade()`/`downgrade()` 함수 본문(보통 `pass`)을 다음으로 교체. 파일 상단에 `import sqlalchemy as sa`가 없으면 추가:

```python
def upgrade() -> None:
    # 기존 단일 소스 값(semantic_scholar/openalex)을 combined로 통합.
    # downgrade 시 둘의 구분은 복원되지 않는다 — search_source는 표시·라우팅용이라 무방.
    op.execute(
        "UPDATE tech_queries SET search_source = 'combined' "
        "WHERE search_source IN ('semantic_scholar', 'openalex')"
    )
    op.alter_column(
        "tech_queries", "search_source",
        server_default="combined",
        existing_type=sa.String(length=30),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "tech_queries", "search_source",
        server_default="semantic_scholar",
        existing_type=sa.String(length=30),
        existing_nullable=False,
    )
    op.execute(
        "UPDATE tech_queries SET search_source = 'semantic_scholar' "
        "WHERE search_source = 'combined'"
    )
```

- [ ] **Step 4: 마이그레이션 적용 및 검증**

Run: `docker compose exec api alembic upgrade head`
Expected: `Running upgrade ... -> <revision>, migrate search_source to combined` 출력, 에러 없음

Run: `docker compose exec -T db psql -U techspec -d techspec -c "SELECT search_source, count(*) FROM tech_queries GROUP BY search_source;"`
Expected: `combined`과 `scopus`만 존재 (`semantic_scholar`/`openalex` 행 0건)

- [ ] **Step 5: 커밋**

```bash
git add backend/app/models/tech_query.py backend/alembic/versions/
git commit -m "feat(db): migrate search_source values to combined"
```

---

## Task 6: 프론트엔드 `InputPage.tsx`

소스 선택 UI를 `combined`/`scopus` 2개로 교체.

**Files:**
- Modify: `frontend/src/pages/InputPage.tsx:7-11` (`SOURCE_OPTIONS`), `:19` (기본 state), `:42-43` (`sourceLabel` fallback)

- [ ] **Step 1: `SOURCE_OPTIONS` 교체**

`frontend/src/pages/InputPage.tsx:7-11`의 현재:

```tsx
const SOURCE_OPTIONS = [
  { value: "semantic_scholar", label: "Semantic Scholar" },
  { value: "scopus",           label: "Scopus (Elsevier)" },
  { value: "openalex",         label: "OpenAlex" },
] as const;
```

다음으로 교체:

```tsx
const SOURCE_OPTIONS = [
  { value: "combined", label: "OpenAlex + Semantic Scholar" },
  { value: "scopus",   label: "Scopus (Elsevier)" },
] as const;
```

- [ ] **Step 2: 기본 state 값 교체**

`frontend/src/pages/InputPage.tsx:19`의 현재:

```tsx
  const [searchSource,  setSearchSource]  = useState<SearchSource>("semantic_scholar");
```

다음으로 교체:

```tsx
  const [searchSource,  setSearchSource]  = useState<SearchSource>("combined");
```

- [ ] **Step 3: `sourceLabel` fallback 교체**

`frontend/src/pages/InputPage.tsx:42-43`의 현재:

```tsx
  const sourceLabel =
    SOURCE_OPTIONS.find((o) => o.value === searchSource)?.label ?? "Semantic Scholar";
```

다음으로 교체:

```tsx
  const sourceLabel =
    SOURCE_OPTIONS.find((o) => o.value === searchSource)?.label ?? "OpenAlex + Semantic Scholar";
```

- [ ] **Step 4: 빌드/타입체크 확인**

Run: `cd frontend && npm run build`
Expected: 타입 에러 없이 빌드 성공 (`SearchSource` 타입이 `SOURCE_OPTIONS`에서 파생되므로 자동 갱신)

- [ ] **Step 5: 브라우저 수동 확인**

`docker compose up -d --build frontend api` 후 `http://localhost:8098` 접속:
- 입력 페이지 "논문 데이터 소스" 토글에 "OpenAlex + Semantic Scholar"와 "Scopus (Elsevier)" 2개만 표시
- 기본 선택이 "OpenAlex + Semantic Scholar"
- 하단 안내 문구에 선택한 라벨이 반영

- [ ] **Step 6: 커밋**

```bash
git add frontend/src/pages/InputPage.tsx
git commit -m "feat(frontend): combined/scopus source selection"
```

---

## Task 7: 전체 회귀 검증

전체 테스트 스위트와 엔드투엔드 흐름을 검증한다. 코드 변경 없음 — 검증만.

**Files:** 없음 (검증 태스크)

- [ ] **Step 1: 전체 백엔드 테스트**

Run: `docker compose exec api pytest tests/ -v`
Expected: 전부 PASS. 기준선 47개 + 신규 (`test_combined_search.py` 9, `test_utils.py` 3) − 폐기 (`test_pipeline.py` 5→3, `test_search_agent.py` 7→7) ⇒ 약 57개 통과, 실패 0

- [ ] **Step 2: 마이그레이션 상태 확인**

Run: `docker compose exec api alembic current`
Expected: head revision이 Task 5에서 만든 revision과 일치

- [ ] **Step 3: 엔드투엔드 스모크 (선택, 권장)**

`docker compose up -d` 후 `http://localhost:8098`에서 `combined` 소스로 기술 분야 1건 분석을 실행:
- WebSocket 진행 상태가 "논문 검색 중" → 완료까지 진행
- 결과 페이지의 분석 데이터 탭에 metric_value가 표시됨 (단일 소스 대비 수율 향상 기대)
- worker 로그에 OpenAlex·Semantic Scholar 양쪽 호출이 보이고, 한쪽 실패 시 `combined search: ... failed` warning만 남고 job은 완료

---

## Self-Review

**1. Spec coverage:**
- 스펙 §1.1 `merge_papers` → Task 1 ✓
- 스펙 §1.2 `search_combined` → Task 2 ✓
- 스펙 §1.3 `search_all_sources` → Task 4 (Step 5) ✓
- 스펙 §2.1 `SOURCE_PLAN` → Task 4 (Step 6) ✓
- 스펙 §2.2 `search_node` → Task 4 (Step 7) ✓
- 스펙 §3.1 schema Literal → Task 4 (Step 4) ✓
- 스펙 §3.2 model server_default → Task 5 (Step 1) ✓
- 스펙 §3.3 Alembic 마이그레이션 → Task 5 (Step 2-4) ✓
- 스펙 §3.4 `get_engine_label` → Task 3 ✓
- 스펙 §4 프론트엔드 → Task 6 ✓
- 스펙 §5.1 `merge_papers` 테스트 → Task 1 (5개) ✓
- 스펙 §5.2 `search_combined` 테스트 → Task 2 (4개) ✓
- 스펙 §5.3 `test_pipeline.py` 수정 → Task 4 (Step 1) ✓
- 스펙 §5.4 회귀 확인 → Task 7 ✓

**2. Placeholder scan:** `<revision>`은 alembic이 Task 5 Step 2에서 생성하는 실제 값의 자리표시 — 정상. 그 외 TBD/TODO 없음.

**3. Type consistency:** `merge_papers(s2_papers, openalex_papers)`, `search_combined(keywords, *, s2_semaphore, openalex_semaphore, client, max_results)`, `search_all_sources(keywords, source, max_results, *, semaphores, client)`, `SOURCE_PLAN` — Task 1·2·4 전반에서 시그니처·이름 일관. `search_combined`의 키워드 인자명(`s2_semaphore`/`openalex_semaphore`)이 Task 2 정의와 Task 4 호출부, Task 4 테스트 mock에서 일치.

**4. Scope:** 단일 서브시스템(멀티소스 검색). 키워드 프롬프트/추출 힌트는 스펙 B로 분리됨 — 범위 밖.
