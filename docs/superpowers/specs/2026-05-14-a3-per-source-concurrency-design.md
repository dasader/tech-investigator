# A3 — Per-Source Search Concurrency (2026-05-14)

`docs/260513-further-jobs.md`의 **A3** 후속 항목 처리. `search_node`가 모든 검색 source를 `Semaphore(1)`로 직렬화하던 것을 source별 동시성 한도로 교체한다.

이로써 `docs/260513-further-jobs.md`의 A1-A4 + B1이 모두 완료된다.

---

## 0. 결정 요약

| 결정 사항 | 값 | 근거 |
|---|---|---|
| 동시성 값 | static dict `{"semantic_scholar": 1, "scopus": 5, "openalex": 10}` | 문서 제안값. 외부 API rate limit 반영. env override 필요성 없음 |
| 위치 | `pipeline.py` module-level + `_concurrency_for` helper | source별 동시성은 pipeline의 책임. helper는 pure-function이라 단위 테스트 가능 |
| unknown source 처리 | `.get(source, 1)` fallback | 가장 보수적인 직렬 처리 |
| scope | search 단계만 (`search_node`) | extract는 Gemini 호출, rate limit 성격이 다름 |
| 커밋 단위 | 단일 commit | 변경 폭 작음 (1 파일 수정 + 1 테스트 신규) |

---

## 1. `pipeline.py` 변경

### module-level 추가

```python
# 외부 API rate limit에 맞춘 source별 검색 동시성.
# Semantic Scholar: 무키 ~1 req/s, Scopus: ~9 req/s, OpenAlex: ~100 req/s.
CONCURRENCY = {"semantic_scholar": 1, "scopus": 5, "openalex": 10}


def _concurrency_for(source: str) -> int:
    return CONCURRENCY.get(source, 1)
```

### `search_node` 변경

```python
# Before
async def search_node(state: PipelineState, db: Session, client: httpx.AsyncClient) -> PipelineState:
    _update_job(db, state["job_id"], 10.0, "논문 검색 중")
    semaphore = asyncio.Semaphore(1)
    ...

# After
async def search_node(state: PipelineState, db: Session, client: httpx.AsyncClient) -> PipelineState:
    _update_job(db, state["job_id"], 10.0, "논문 검색 중")
    semaphore = asyncio.Semaphore(_concurrency_for(state["search_source"]))
    ...
```

`search_node`의 나머지 본문(`tasks` 구성, `asyncio.gather`, 결과 매핑)은 변경 없음.

### 핵심 결정

- `.get(source, 1)` fallback — `search_source`는 schema에서 Literal 검증되지만 방어적으로 unknown source는 동시성 1로 처리
- helper는 `pipeline.py`에 위치 — source별 동시성 정책은 pipeline의 책임. `search_agent.py`로 옮기면 search_agent에 source별 지식이 새로 생겨 책임 경계가 흐려짐
- `extract_node`의 `Semaphore(10)`은 변경 없음 — A3 scope는 search 단계 한정
- `inter_attempt_sleep`(S2/Scopus 1.1s)은 그대로 — semaphore와 독립적으로 작동. semaphore가 동시 실행을 허용해도 각 task의 `finally` sleep은 유지되어 burst rate를 자연스럽게 억제

### 의도된 행동 변화

- **Scopus**: 기존 직렬 `N × (요청+1.1s)` → `Semaphore(5)`로 5개 동시. N=10이면 2 batch ≈ wall-clock 절반 이하
- **OpenAlex**: 기존 직렬 → `Semaphore(10)`로 사실상 전부 동시 (sleep 0)
- **Semantic Scholar**: `Semaphore(1)` 유지 — 변화 없음

---

## 2. 테스트

### 신규 파일: `backend/tests/test_pipeline.py`

`search_node`는 `db` 의존(`_update_job`)이라 직접 단위 테스트가 무겁고, `asyncio.Semaphore`의 크기는 외부에서 직접 읽기 어렵다. 검증 단위는 pure helper `_concurrency_for`.

```python
import pytest
from app.agents.pipeline import _concurrency_for, CONCURRENCY

pytestmark = pytest.mark.no_db


def test_concurrency_semantic_scholar_is_serial():
    assert _concurrency_for("semantic_scholar") == 1


def test_concurrency_scopus():
    assert _concurrency_for("scopus") == 5


def test_concurrency_openalex():
    assert _concurrency_for("openalex") == 10


def test_concurrency_unknown_source_falls_back_to_serial():
    assert _concurrency_for("some_future_source") == 1


def test_concurrency_dict_covers_all_known_sources():
    # search_source의 Literal 후보와 CONCURRENCY 키가 어긋나지 않도록 가드
    assert set(CONCURRENCY) == {"semantic_scholar", "scopus", "openalex"}
```

### 테스트 케이스 (5개)

| # | 이름 | 검증 |
|---|---|---|
| 1 | `test_concurrency_semantic_scholar_is_serial` | S2 = 1 |
| 2 | `test_concurrency_scopus` | Scopus = 5 |
| 3 | `test_concurrency_openalex` | OpenAlex = 10 |
| 4 | `test_concurrency_unknown_source_falls_back_to_serial` | unknown → 1 (fallback) |
| 5 | `test_concurrency_dict_covers_all_known_sources` | dict 키 집합이 알려진 3개와 정확히 일치 (드리프트 가드) |

### `search_node` 자체 테스트는 추가하지 않음

`search_node`가 `_concurrency_for`의 결과로 semaphore를 만드는 한 줄 연결은 코드 리뷰로 충분. semaphore 크기를 런타임에 검증하는 테스트는 `asyncio.Semaphore` 내부(`._value`)에 의존해야 해서 brittle. YAGNI.

### 기존 테스트 영향 없음

`test_pipeline_task.py`의 `test_full_flow`는 Celery task를 통째 mock하므로 `search_node` 미실행 → 영향 없음. 회귀 후 `39 + 5 = 44 passed` 예상.

---

## 3. 커밋 / 검증

### 단일 commit

`perf(pipeline): per-source search concurrency`

변경 파일:
- `backend/app/agents/pipeline.py` (수정)
- `backend/tests/test_pipeline.py` (신규)

### 검증 명령

```bash
docker compose exec api pytest tests/test_pipeline.py -v   # 5 passed
docker compose exec api pytest tests/ -v                    # 44 passed (39 baseline + 5 신규)
```

### 위험 요소 및 완화

| 위험 | 완화 |
|---|---|
| Scopus/OpenAlex 동시 호출이 rate limit 초과 | `inter_attempt_sleep`(S2/Scopus 1.1s)이 semaphore와 독립으로 유지 → burst 억제. Scopus `Semaphore(5)` + 1.1s sleep ≈ 4.5 req/s (한도 9 이내). OpenAlex `Semaphore(10)` sleep 0 (한도 100 이내) |
| 공유 `httpx.AsyncClient` connection pool 포화 | httpx 기본 pool은 host당 충분 (기본 max_connections 100). 동시 10개는 문제 없음 |
| `search_source` Literal 후보와 dict 키 불일치 (스키마 변경 시) | 테스트 #5가 드리프트 가드 — dict 키 집합 ≠ 알려진 3개면 실패 |
| unknown source 유입 | `.get(source, 1)` fallback — 가장 보수적인 직렬 처리 |

---

## 4. Scope 제외 (YAGNI)

- **`extract_node`의 `Semaphore(10)` 변경** — extract는 Gemini 호출, rate limit 성격이 다름. A3 scope는 search 단계 한정
- **config.py로 동시성 노출** — env override 필요성 없음
- **API key 유무 반영** — 분기 로직 추가 대비 이점 적음
- **`inter_attempt_sleep` 재설계** — A1 PR의 별도 follow-up으로 기록됨, A3 scope 아님

---

## 5. 후속 작업

본 spec 완료 후 `docs/260513-further-jobs.md`의 A3 섹션에 완료 표기 추가. 이로써 A1-A4 + B1 전부 완료 — `docs/260513-further-jobs.md`의 모든 항목 처리 완료.
