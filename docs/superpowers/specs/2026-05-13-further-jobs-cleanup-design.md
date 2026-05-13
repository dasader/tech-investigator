# Further-Jobs Cleanup — Design Spec (2026-05-13)

`docs/260513-further-jobs.md`에 기록된 후속 작업 중 **안전 범위** 3개 항목(B1 + A1 + A4)을 단일 브랜치에서 처리하기 위한 설계.

A2(global `AsyncClient` + lifespan), A3(source별 동시성 정책)는 본 spec의 scope에서 의도적으로 제외한다.

---

## 0. 결정 요약

| 결정 사항 | 값 | 근거 |
|---|---|---|
| 작업 단위 | 단일 브랜치 `chore/further-jobs-cleanup`, 커밋 3개 분리 | 회귀 추적 용이, 리뷰 부담 적정 |
| 커밋 순서 | ① B1 → ② A4 → ③ A1 | B1이 통과해야 후속 회귀 검증 의미. A4 후 A1 적용 시 새 fixture로 헬퍼 검증 깔끔 |
| Retry 헬퍼 설계 | 서비스별 정책 파라미터화 | 기존 service별 차이(sleep 정책 등) 보존하면서 중복 제거 |
| Fixture 적용 범위 | 기존 10건 일괄 migrate | 중복 패턴이 한 곳에 모이고 헬퍼 도입 후 mock 대상이 명확해짐 |

---

## 1. B1 — `test_extraction_agent.py` 재작성

### 배경

테스트가 `extract_metric_from_paper`(단수형)를 import 하지만 실 구현은 `extract_metrics_from_paper`(복수형). 단순 rename이 아니라 시그니처 자체가 다름:

- 기존(예상): `extract_metric_from_paper(paper, indicator_name, unit) -> dict`
- 실제(현재): `extract_metrics_from_paper(paper, indicators: list[dict], semaphore) -> list[tuple[int, dict]]`

Gemini는 batch JSON(`[{"indicator_id": ..., "value": ..., "unit": ..., ...}, ...]`)을 반환하며, country는 `paper["country"]` → `paper["country_lookup_done"]` → `_get_country_from_openalex(doi)` 폴백 경로로 결정된다.

### 변경 파일

- `backend/tests/test_extraction_agent.py`

### 테스트 케이스 (4개)

| # | 이름 | 검증 내용 |
|---|---|---|
| 1 | `test_extracts_value_from_paper` | indicator 1개로 batch 호출, value/unit/confidence/quote 반환 |
| 2 | `test_returns_empty_when_no_value_found` | Gemini가 빈 list `[]` 반환 시 결과가 비어있음 |
| 3 | `test_skips_openalex_when_country_already_set` | `paper["country"]` 세팅 시 `_get_country_from_openalex` 호출되지 않음 |
| 4 | `test_skips_openalex_when_country_lookup_done` | `country_lookup_done=True`일 때도 호출되지 않음 (OpenAlex source 통합으로 신설된 분기) |

### Mock 전략

- `app.agents.extraction_agent.genai_client.models.generate_content` patch → `response.text`에 batch JSON 문자열 주입
- `app.agents.extraction_agent._get_country_from_openalex` patch (`AsyncMock`)
- `pytestmark = pytest.mark.no_db` 추가 (DB 불필요)

---

## 2. A4 — `httpx_mock_get` fixture

### 위치

`backend/tests/conftest.py`에 fixture 추가.

### 시그니처

```python
@pytest.fixture
def httpx_mock_get(monkeypatch):
    """
    Patch httpx.AsyncClient in the given agent module so that
    `client.get(...)` returns a mocked response.

    Returns the mock_client so tests can inspect call_args.
    """
    def _make(module_path: str, *, status_code: int = 200, json_body=None):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = status_code
        mock_response.json.return_value = json_body or {}
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        mock_client_class = MagicMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        monkeypatch.setattr(f"{module_path}.httpx.AsyncClient", mock_client_class)
        return mock_client
    return _make
```

### 핵심 결정

- `monkeypatch` 사용 → `with patch(...)` 들여쓰기 제거, 본문 가독성↑
- `mock_client` 반환 → `mock_client.get.call_args`로 params 검증 가능
- 429 테스트에서 `asyncio.sleep` patch는 각 테스트에서 `monkeypatch.setattr(...)` 한 줄로 처리 (fixture가 모든 사례를 흡수하지 않음)

### Migration 패턴 (Before/After)

```python
# Before (6줄 + with-block 들여쓰기)
with patch("app.agents.openalex_agent.httpx.AsyncClient") as mock_client_class:
    mock_client = AsyncMock()
    mock_client_class.return_value.__aenter__.return_value = mock_client
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_OPENALEX_RESPONSE
    mock_response.raise_for_status = MagicMock()
    mock_client.get.return_value = mock_response

    results = await search_papers_for_indicator("HBM bandwidth", max_results=5)

# After (1줄, 들여쓰기 없음)
httpx_mock_get("app.agents.openalex_agent", json_body=MOCK_OPENALEX_RESPONSE)
results = await search_papers_for_indicator("HBM bandwidth", max_results=5)
```

### Migration 범위 (일괄)

- `test_openalex_agent.py`: 5건
  - `test_search_returns_normalized_papers`
  - `test_search_filters_entries_without_abstract`
  - `test_search_raises_on_429`
  - `test_search_country_none_when_no_institutions`
  - `test_search_uses_cited_by_count_sort`
- `test_scopus_agent.py`: 5건
  - `test_search_returns_normalized_papers`
  - `test_search_country_none_when_no_affiliation`
  - `test_search_filters_entries_without_abstract`
  - `test_search_raises_on_429`
  - `test_search_handles_single_affiliation_as_dict`

### 부수 정리

- `test_scopus_agent.py`에 `pytestmark = pytest.mark.no_db` 추가 (현재 누락, `test_openalex_agent.py`만 보유)
- 두 테스트 파일의 `from unittest.mock import AsyncMock, patch, MagicMock` 제거 — fixture가 책임

---

## 3. A1 — `get_with_retry` 헬퍼

### 위치

`backend/app/agents/_http_retry.py` (신규)

`utils.py` 대신 `agents/` 하위에 두는 이유: agent 전용 utility임이 모듈 구조로 명시되고, 다른 영역(API 라우터 등)이 우연히 사용할 가능성을 줄임.

### 시그니처

```python
async def get_with_retry(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    service_name: str,                       # "Semantic Scholar" | "Scopus" | "OpenAlex"
    context: str = "",                        # keywords 등 디버깅 정보 (에러 메시지에 포함)
    max_attempts: int = 3,
    timeout: float = 30.0,
    inter_attempt_sleep: float = 0.0,         # S2/Scopus는 1.1, OpenAlex는 0(기본)
    retry_status_codes: tuple[int, ...] = (429,),
) -> dict:
    """HTTP GET with retry/backoff. Returns parsed JSON dict."""
```

### 구현 골자

```python
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
            raise RuntimeError(f"{service_name} API error {e.response.status_code}: {context}") from e
        except httpx.RequestError as e:
            raise RuntimeError(f"{service_name} network error: {context}") from e
        finally:
            if inter_attempt_sleep:
                await asyncio.sleep(inter_attempt_sleep)
    raise RuntimeError(f"{service_name} API error 429: {context}")
```

### 호출부 변경 (3개 agent)

```python
# search_agent.py (Semantic Scholar)
async with sem:
    payload = await get_with_retry(
        SS_API_URL, params=params, headers=headers,
        service_name="Semantic Scholar", context=keywords,
        inter_attempt_sleep=1.1,
    )
    data = payload.get("data", [])

# scopus_agent.py
async with sem:
    payload = await get_with_retry(
        SCOPUS_API_URL, params=params, headers=headers,
        service_name="Scopus", context=keywords,
        inter_attempt_sleep=1.1,
    )
    entries = payload.get("search-results", {}).get("entry", [])

# openalex_agent.py
async with sem:
    data = await get_with_retry(
        OPENALEX_API_URL, params=params,
        service_name="OpenAlex", context=keywords,
    )
```

### 의도된 행동 변화

1. **`scopus_agent`가 이제 `HTTPStatusError`를 wrap** — 기존엔 raw `httpx.HTTPStatusError`가 호출자에 전파됨. 헬퍼 일관 처리로 `RuntimeError("Scopus API error {code}")`로 변환. `pipeline.py`의 `search_node`는 `asyncio.gather(*tasks)`(return_exceptions 없음)로 호출하므로 외부 효과는 job 실패 메시지가 일관되어지는 것뿐.
2. **`httpx.AsyncClient` 인스턴스화 횟수**: attempt당 1회 → 함수당 1회. 같은 함수 호출 내 connection pool 재사용. A2 본질(global client + lifespan)은 그대로 남아 별도 PR 여지 유지.

### 헬퍼 단위 테스트 (`backend/tests/test_http_retry.py` 신규)

- `test_get_with_retry_returns_json_on_200`
- `test_get_with_retry_raises_on_max_attempts_429` (asyncio.sleep patch)
- `test_get_with_retry_wraps_http_status_error`
- `test_get_with_retry_wraps_timeout`

기존 10건의 agent 테스트(특히 `*_raises_on_429` 2건)는 그대로 통과해야 함 → 간접 회귀 검증.

---

## 4. 커밋 및 검증 순서

| # | 커밋 메시지 | 변경 파일 | 검증 명령 |
|---|---|---|---|
| 1 | `fix(tests): repair extraction_agent test imports and batch signature` | `backend/tests/test_extraction_agent.py` | `docker compose exec api pytest backend/tests/test_extraction_agent.py -v` |
| 2 | `refactor(tests): extract httpx_mock_get fixture` | `backend/tests/conftest.py`, `test_openalex_agent.py`, `test_scopus_agent.py` | `docker compose exec api pytest backend/tests/test_openalex_agent.py backend/tests/test_scopus_agent.py -v` |
| 3 | `refactor(agents): extract get_with_retry helper` | `backend/app/agents/_http_retry.py` (신규), `search_agent.py`, `scopus_agent.py`, `openalex_agent.py`, `backend/tests/test_http_retry.py` (신규) | `docker compose exec api pytest backend/tests/test_http_retry.py backend/tests/test_openalex_agent.py backend/tests/test_scopus_agent.py -v` |

**최종 회귀 검증**:
```bash
docker compose exec api pytest backend/tests/ -v
```

---

## 5. Scope 제외 (별도 PR)

- **A2** — module-level `httpx.AsyncClient` + lifespan 관리. `main.py` 및 Celery worker 초기화 영향.
- **A3** — source별 동시성 정책. `pipeline.py:36` 추상화 수준 변경 필요.
- 헬퍼의 `backoff_initial` 파라미터화 — 현재 10초 고정으로 충분(YAGNI).
- 헬퍼의 POST 메서드 지원 — 현재 모든 호출이 GET. `scopus_agent._batch_fetch_abstracts`의 POST는 별개의 작은 try/except 패턴이라 헬퍼화 효용 낮음.

---

## 6. 후속 작업

이 spec이 완료되면 `docs/260513-further-jobs.md`의 A1/A4/B1 섹션에 처리 완료 표기를 추가하거나 해당 섹션을 제거한다. A2/A3는 그대로 유지.
