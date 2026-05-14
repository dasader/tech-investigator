# A2 — Shared `httpx.AsyncClient` via DI (2026-05-14)

`docs/260513-further-jobs.md`의 **A2** 후속 항목 처리. `httpx.AsyncClient`를 호출당 새로 생성하는 패턴을 제거하고, 한 `run_pipeline` 호출 단위로 단일 client를 공유한다.

A3(source별 동시성 정책)는 별도 spec.

---

## 0. 결정 요약

| 결정 사항 | 값 | 근거 |
|---|---|---|
| Lifecycle 패턴 | **DI** (run_pipeline이 client 소유, agent에 keyword 인자로 전달) | event loop binding 문제 회피, 명시적, test 쉬움 |
| Client 단위 | **단일 공유 client** | host별 connection pool은 `httpx`가 자동 관리. timeout은 호출별 override. |
| Helper signature | **`client` required kwarg** | backward-compat fallback 없음 (DI 원칙 일관) |
| `_get_country_from_openalex`, `_batch_fetch_abstracts` 처리 | **그대로 두고 client만 DI** | retry 정책 다름. helper 통일은 변경 폭 대비 이점 적음 |
| 커밋 단위 | **단일 commit** | signature 변경이 cross-cutting. 중간 상태가 broken commit |

---

## 1. Client 생성 위치 — `run_pipeline`

### 변경 후 (`backend/app/agents/pipeline.py`)

```python
import httpx

async def run_pipeline(job_id: int, db: Session) -> str:
    # ... query/indicators 로드 ...
    state: PipelineState = {...}

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        state = await search_node(state, db, client)
        state = await extract_node(state, db, client)
        state = await validate_node(state, db)         # HTTP 없음
        state = await synthesize_node(state, db)       # Gemini만
    return state["report_markdown"]
```

### 핵심 결정

- `async with`로 client 생성 → 자동 close
- `timeout=httpx.Timeout(30.0)` 명시 (default가 None=무한이라 위험)
- HTTP 안 쓰는 node 2개(`validate`, `synthesize`)는 client 인자 안 받음 — 의존성 명료
- Celery worker entry point(`pipeline_task.py:26 asyncio.run(run_pipeline(...))`) 변경 없음
- 새 `asyncio.run`은 새 event loop + 새 client → multi-task 환경에서 closed-loop 문제 회피

---

## 2. `get_with_retry` signature 변경

### Before
```python
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
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(max_attempts):
            try:
                response = await client.get(url, params=params, headers=headers)
                ...
```

### After
```python
async def get_with_retry(
    url: str,
    *,
    client: httpx.AsyncClient,           # ← 신규 (required)
    params: dict | None = None,
    headers: dict | None = None,
    service_name: str,
    context: str = "",
    max_attempts: int = 3,
    timeout: float = 30.0,
    inter_attempt_sleep: float = 0.0,
    retry_status_codes: tuple[int, ...] = (429,),
) -> dict:
    for attempt in range(max_attempts):
        try:
            response = await client.get(url, params=params, headers=headers, timeout=timeout)
            ...
```

핵심 변화:
- `client`를 required kwarg로 추가
- `async with httpx.AsyncClient(...)` 블록 제거 — 들여쓰기 한 단계 풀림
- `timeout`은 `client.get(..., timeout=timeout)` 호출별 override로 이동
- caller가 항상 `client=client` 명시 전달

---

## 3. Agent 함수 signature 변경

### 호출 체인
```
run_pipeline
 ├── search_node(state, db, client)
 │    └── search_all_sources(keywords, source, max_results, semaphore, *, client)
 │         └── {S2|Scopus|OpenAlex}.search_papers_for_indicator(keywords, max_results, semaphore, *, client)
 │              ├── get_with_retry(..., client=client, ...)
 │              └── scopus._batch_fetch_abstracts(doi_list, *, client)   # scopus only
 └── extract_node(state, db, client)
      └── extract_metrics_from_paper(paper, indicators, semaphore, *, client)
           └── _get_country_from_openalex(doi, *, client)
```

### 변경 함수 (9개)

| 함수 | 추가 인자 |
|---|---|
| `search_node` | `client: httpx.AsyncClient` |
| `extract_node` | `client: httpx.AsyncClient` |
| `search_all_sources` | `*, client: httpx.AsyncClient` |
| `search_agent.search_papers_for_indicator` | `*, client: httpx.AsyncClient` |
| `scopus_agent.search_papers_for_indicator` | `*, client: httpx.AsyncClient` |
| `openalex_agent.search_papers_for_indicator` | `*, client: httpx.AsyncClient` |
| `scopus_agent._batch_fetch_abstracts` | `*, client: httpx.AsyncClient` |
| `extraction_agent.extract_metrics_from_paper` | `*, client: httpx.AsyncClient` |
| `extraction_agent._get_country_from_openalex` | `*, client: httpx.AsyncClient` |

### `_get_country_from_openalex` 변경 예시

```python
# Before
async def _get_country_from_openalex(doi: str) -> str | None:
    try:
        url = f"https://api.openalex.org/works/doi:{doi}"
        headers = {"User-Agent": "TechSpec/1.0 (mailto:ilhwan.lee@gmail.com)"}
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, headers=headers)
            if r.status_code != 200:
                return None
            data = r.json()
        ...

# After
async def _get_country_from_openalex(doi: str, *, client: httpx.AsyncClient) -> str | None:
    try:
        url = f"https://api.openalex.org/works/doi:{doi}"
        headers = {"User-Agent": "TechSpec/1.0 (mailto:ilhwan.lee@gmail.com)"}
        r = await client.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        ...
```

### `_batch_fetch_abstracts` 변경 예시

```python
# Before
async def _batch_fetch_abstracts(doi_list: list[str]) -> dict[str, str]:
    if not doi_list:
        return {}
    ids = [f"DOI:{doi}" for doi in doi_list]
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(S2_BATCH_URL, params={...}, json={...})
            ...

# After
async def _batch_fetch_abstracts(doi_list: list[str], *, client: httpx.AsyncClient) -> dict[str, str]:
    if not doi_list:
        return {}
    ids = [f"DOI:{doi}" for doi in doi_list]
    try:
        r = await client.post(S2_BATCH_URL, params={...}, json={...}, timeout=20)
        ...
```

---

## 4. Test 영향

A2 적용 후 helper도 agent도 `httpx.AsyncClient`를 더 이상 생성하지 않음 → 기존 monkeypatch 기반 mock(`httpx_mock_get`, `_patch_client`)이 의미 상실. **mock client object를 직접 만들어 `client=` 인자로 전달**하는 패턴으로 전환.

### 4.1 `conftest.py` fixture 교체

```python
# Before — httpx_mock_get (Task 2에서 도입)
@pytest.fixture
def httpx_mock_get(monkeypatch):
    def _make(module_path: str, *, status_code: int = 200, json_body=None):
        ...
        monkeypatch.setattr(f"{module_path}.httpx.AsyncClient", mock_client_class)
        return mock_client
    return _make
```

```python
# After — mock_httpx_client
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

핵심 차이:
- monkeypatch 사용 안 함 → 객체만 반환
- 테스트가 `client` 객체를 받아 `client=client` 인자로 전달
- POST mock이 필요한 테스트(예: scopus의 `_batch_fetch_abstracts`)는 반환된 client에 `client.post.return_value = ...` 직접 설정

### 4.2 호출 패턴 (Before/After)

```python
# Before
@pytest.mark.asyncio
async def test_search_returns_normalized_papers(httpx_mock_get):
    httpx_mock_get("app.agents._http_retry", json_body=MOCK_OPENALEX_RESPONSE)
    results = await search_papers_for_indicator("HBM bandwidth", max_results=5)

# After
@pytest.mark.asyncio
async def test_search_returns_normalized_papers(mock_httpx_client):
    client = mock_httpx_client(json_body=MOCK_OPENALEX_RESPONSE)
    results = await search_papers_for_indicator("HBM bandwidth", max_results=5, client=client)
```

### 4.3 영향 받는 테스트

| 파일 | 변경 건수 | 변경 내용 |
|---|---|---|
| `test_http_retry.py` | 6건 | `_patch_client(monkeypatch, ...)` → `client = mock_httpx_client(...)`; `get_with_retry(..., client=client, ...)`. `_patch_client` 헬퍼는 fixture가 흡수해서 제거. |
| `test_openalex_agent.py` | 5건 | fixture 교체 + `client=client` 전달 |
| `test_scopus_agent.py` | 5건 | 동일 |
| `test_search_agent.py` | 5건 | `with patch("_http_retry.httpx.AsyncClient")` 블록 제거, mock client DI로 전환 |
| `test_extraction_agent.py` | 4건 | `client=AsyncMock(spec=httpx.AsyncClient)` 전달 (`_get_country_from_openalex`는 patch되어 client 인자는 무시되지만 호출 signature 만족 필요) |

`asyncio.sleep` patch target은 그대로 (`app.agents._http_retry.asyncio.sleep`).

### 4.4 `httpx_mock_get` 제거

사용처는 `test_openalex_agent.py`(5건) + `test_scopus_agent.py`(5건) + `conftest.py`(정의)뿐. 외부 사용처 0 — 같은 commit에서 제거 후 `mock_httpx_client`로 대체.

---

## 5. 커밋 / 검증

### 단일 commit

`refactor(agents): share httpx.AsyncClient across pipeline via DI`

변경 파일 총 12개:
- `backend/app/agents/pipeline.py`
- `backend/app/agents/_http_retry.py`
- `backend/app/agents/search_agent.py`
- `backend/app/agents/scopus_agent.py`
- `backend/app/agents/openalex_agent.py`
- `backend/app/agents/extraction_agent.py`
- `backend/tests/conftest.py`
- `backend/tests/test_http_retry.py`
- `backend/tests/test_search_agent.py`
- `backend/tests/test_openalex_agent.py`
- `backend/tests/test_scopus_agent.py`
- `backend/tests/test_extraction_agent.py`

### 검증 명령

```bash
# 단계별 부분 검증
docker compose exec api pytest tests/test_http_retry.py -v        # 6 passed
docker compose exec api pytest tests/test_openalex_agent.py -v    # 10 passed
docker compose exec api pytest tests/test_scopus_agent.py -v      # 5 passed
docker compose exec api pytest tests/test_search_agent.py -v      # 7 passed
docker compose exec api pytest tests/test_extraction_agent.py -v  # 4 passed

# 전체 회귀
docker compose exec api pytest tests/ -v                           # 39 passed
```

### 의도된 행동 변화

1. **Single connection pool across one pipeline run**: 같은 host(예: `api.openalex.org`)에 paper당 한 번씩 호출하던 `_get_country_from_openalex`가 한 번의 TCP+TLS handshake로 전부 처리.
2. **Client lifecycle은 `asyncio.run(run_pipeline(...))` 단위**: Celery task 종료 시 자동 close. multi-task 시나리오에서 closed-loop 문제 회피.
3. **`_batch_fetch_abstracts`도 공유 client 사용**: scopus의 S2 batch POST. 기존 호출당 새 client → 공유 client + `timeout=20` 호출별 override.

### 위험 요소 및 완화

| 위험 | 완화 |
|---|---|
| signature 변경 누락된 caller | pytest 전체 회귀가 즉시 잡음 (`TypeError: missing required keyword argument 'client'`) |
| event loop binding (다중 `asyncio.run`) | client lifecycle을 `run_pipeline` 안으로 한정 → 자동 해결 |
| `httpx.AsyncClient()` default timeout이 None (무한) | `run_pipeline`에서 `timeout=httpx.Timeout(30.0)` 명시. 호출별 override(`timeout=10`, `timeout=20`)는 그대로 적용 |
| `email_service.send_completion_email`에 httpx? | grep 확인 완료 — `app/services` 하위에 httpx 사용 0. 영향 없음. |
| FastAPI request handler에서 agent 호출 시 client? | 현재 FastAPI는 httpx 사용 0 (IndicatorAgent는 Gemini만). 영향 없음. |
| `httpx_mock_get` 외부 사용처? | grep 확인 완료 — `test_openalex_agent`, `test_scopus_agent`, `conftest.py` 외 0건. 안전 제거 가능. |

---

## 6. Scope 제외 (별도 후속 작업)

- **A3** — source별 동시성 정책 (`Semaphore(1)` → `CONCURRENCY = {"semantic_scholar": 1, "scopus": 5, "openalex": 10}`)
- **FastAPI lifespan-managed client** — 현재 FastAPI는 httpx 사용 0. 도입 이유 없음.
- **서비스별 분리 client** — 단일 client + host별 자동 pool로 충분
- **`get_with_retry` client optional fallback** — backward compat 불필요
- **`email_service`도 같은 client 공유** — 별도 `asyncio.run`이라 자연스럽지 않음

---

## 7. 후속 작업

본 spec 완료 후 `docs/260513-further-jobs.md`의 A2 섹션에 완료 표기 추가. A3는 그대로 유지.
