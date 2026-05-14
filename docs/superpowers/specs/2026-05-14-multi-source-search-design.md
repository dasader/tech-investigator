# 스펙 A — 멀티소스 통합 검색 (2026-05-14)

검색 수율 개선의 첫 번째 사이클. `search_source`를 단일 소스 선택에서 **`combined`(OpenAlex + Semantic Scholar 병행) / `scopus`** 2지선다 구조로 재편한다.

`combined`은 두 소스를 동시에 검색해 DOI 기준 필드별 best-of로 병합하며, 한 소스가 실패해도 다른 소스 결과로 진행한다(그레이스풀 다운). Scopus는 현 수준을 유지한다(현재 효용은 낮으나 향후 유료 구독 대비).

키워드 프롬프트 개선 + 추출 힌트 분리는 **스펙 B**로 분리해 별도 사이클로 진행한다.

---

## 0. 결정 요약

| 결정 사항 | 값 | 근거 |
|---|---|---|
| `search_source` 값 | `Literal["combined", "scopus"]`, 기본 `combined` | 사용자가 원한 2지선다 구조 |
| 기존 DB 데이터 | Alembic 마이그레이션으로 `semantic_scholar`/`openalex` → `combined` | 깔끔한 2값 유지. scopus는 그대로 |
| 병합 전략 | DOI 기준 dedup + 필드별 best-of | recall 극대화, 소스별 강점 결합 |
| 병합 위치 | `search_agent.py`의 `merge_papers()` 순수 함수 | 검색 계층의 책임. DB·네트워크 무의존이라 단위 테스트 용이 |
| 동시 호출 | `search_combined()`이 `asyncio.gather(return_exceptions=True)` | 그레이스풀 다운을 한 곳에 캡슐화 |
| 부분 실패 | 한 소스 실패 → 나머지로 진행 + warning. 둘 다 실패 → `RuntimeError` | 수율/견고성 목적. S2는 429가 잦아 특히 유용 |
| 동시성 | `SOURCE_PLAN` nested dict가 `CONCURRENCY` + `_concurrency_for` 대체 | `combined`이 S2(1)·OpenAlex(10) 서로 다른 동시성을 동시에 써야 함 |
| Scopus | 변경 없음 | 현 수준 유지 (사용자 명시) |
| 커밋 단위 | 단일 commit (백엔드 + 마이그레이션 + 프론트엔드 + 테스트) | 한 기능의 일관된 변경 |

---

## 1. `search_agent.py` 변경

### 1.1 `merge_papers` — 순수 함수 (신규)

```python
def merge_papers(s2_papers: list[dict], openalex_papers: list[dict]) -> list[dict]:
    """OpenAlex + S2 검색 결과를 DOI 기준 필드별 best-of로 병합.

    - dedup 키: 정규화 DOI(소문자·공백제거) → 없으면 정규화 title → 둘 다 없으면 dedup 안 함
    - 결과는 citation_count 내림차순 정렬 (downstream 절단 시 인용수 높은 논문 생존)
    """
```

**필드별 병합 규칙** (같은 키의 두 레코드):

| 필드 | 규칙 |
|------|------|
| `abstract` | 더 긴 non-empty 값 (추출 정확도↑) |
| `country` | non-null 우선. S2는 항상 `None`이라 사실상 OpenAlex 값 |
| `country_lookup_done` | OpenAlex가 기여한 레코드면 `True` → `extraction_agent`의 OpenAlex 재조회 스킵 |
| `citation_count` | 두 값 중 max |
| `year` / `journal_name` / `title` | non-null·non-empty 우선 |
| `paper_id` / `doi` | 하나 유지 (downstream 미사용) |

**dedup 키 정규화**: DOI는 `.strip().lower()`, title은 `.strip().lower()`. DOI·title 둘 다 없는 논문은 dedup 대상에서 제외하고 그대로 유지한다.

### 1.2 `search_combined` — 동시 검색 + 병합 (신규)

```python
async def search_combined(
    keywords: str,
    *,
    s2_semaphore: asyncio.Semaphore,
    openalex_semaphore: asyncio.Semaphore,
    client: httpx.AsyncClient,
    max_results: int | None = None,
) -> list[dict]:
    s2_result, oa_result = await asyncio.gather(
        search_papers_for_indicator(keywords, max_results, s2_semaphore, client=client),
        openalex_agent.search_papers_for_indicator(keywords, max_results, openalex_semaphore, client=client),
        return_exceptions=True,
    )
    # 그레이스풀 다운: 둘 다 예외면 올림, 한쪽만 예외면 [] 취급 + warning
    ...
    return merge_papers(s2_papers, oa_papers)
```

- 각 agent는 `get_with_retry` 소진 시 `RuntimeError`를 던짐 → 그것을 잡는다
- **둘 다 예외** → `RuntimeError("combined search failed: ...")` 재발생 (pipeline이 가시적으로 실패, Celery 재시도)
- **한쪽만 예외** → `logger.warning`으로 어느 소스가 실패했는지 기록, 그 소스는 `[]`

### 1.3 `search_all_sources` 변경

- `"combined"` 분기 추가
- `semaphore: asyncio.Semaphore | None` 파라미터를 `semaphores: dict[str, asyncio.Semaphore]`로 변경

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
    raise ValueError(f"unknown search_source: {source}")
```

`search_papers_for_indicator`(S2), `openalex_agent.search_papers_for_indicator`, `scopus_agent.search_papers_for_indicator`의 시그니처는 **변경 없음** — 기존 테스트 유지.

---

## 2. `pipeline.py` 변경

### 2.1 `SOURCE_PLAN` — `CONCURRENCY` + `_concurrency_for` 대체

```python
# search_source → {하위 소스: 동시성 한도}.
# 외부 API rate limit 기반: Semantic Scholar ~1 req/s, OpenAlex ~100 req/s, Scopus ~9 req/s.
SOURCE_PLAN: dict[str, dict[str, int]] = {
    "combined": {"semantic_scholar": 1, "openalex": 10},
    "scopus":   {"scopus": 5},
}
```

### 2.2 `search_node` 변경

```python
async def search_node(state: PipelineState, db: Session, client: httpx.AsyncClient) -> PipelineState:
    _update_job(db, state["job_id"], 10.0, "논문 검색 중")
    plan = SOURCE_PLAN[state["search_source"]]
    semaphores = {src: asyncio.Semaphore(n) for src, n in plan.items()}
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
    ...
```

세마포어는 지표 간 공유 → S2 호출은 전역 1개씩 직렬, OpenAlex는 최대 10개 동시.

### 2.3 데이터 흐름 (`combined` 기준)

```
search_node
  → SOURCE_PLAN["combined"] → {semantic_scholar: Sem(1), openalex: Sem(10)}
  → 지표별 search_all_sources(kw, source="combined", semaphores=...)
      → search_combined(kw, s2_sem, oa_sem, client)
          → gather( s2.search(...), openalex.search(...), return_exceptions=True )
          → merge_papers(s2_result, oa_result)        # 한쪽 예외 → [] 취급
      → 정규화 dict 리스트 반환
  → search_results[ind_id] = papers
  → (이후 extract_node가 기존대로 [:max_papers_per_indicator] 절단 후 처리)
```

`extract_node` 이후 단계는 **변경 없음**.

---

## 3. 스키마 / 모델 / 마이그레이션

### 3.1 `schemas/tech_query.py`

```python
search_source: Literal["combined", "scopus"] = "combined"
```

### 3.2 `models/tech_query.py`

컬럼은 `String(30)` 그대로, `server_default="semantic_scholar"` → `server_default="combined"`.

### 3.3 Alembic 마이그레이션 (신규 revision)

- **upgrade**:
  - `UPDATE tech_queries SET search_source='combined' WHERE search_source IN ('semantic_scholar','openalex')`
  - 컬럼 `server_default`를 `'combined'`로 변경
- **downgrade**:
  - `UPDATE tech_queries SET search_source='semantic_scholar' WHERE search_source='combined'`
  - `server_default` 복원
  - ※ downgrade는 기존 `openalex`/`semantic_scholar` 구분을 복원하지 못함 — 마이그레이션 docstring에 명시

### 3.4 `utils.py` `get_engine_label`

- `"combined"` → `"OpenAlex + Semantic Scholar + Gemini"`
- `"scopus"` → `"Scopus (Elsevier) + Gemini"` (유지)
- 기본값을 `combined`로. 기존 job은 모두 마이그레이션돼 `combined`/`scopus`만 존재

---

## 4. 프론트엔드 (`InputPage.tsx`)

```tsx
const SOURCE_OPTIONS = [
  { value: "combined", label: "OpenAlex + Semantic Scholar" },
  { value: "scopus",   label: "Scopus (Elsevier)" },
] as const;
```

- 기본 state `useState<SearchSource>("combined")`
- `SearchSource` 타입은 `SOURCE_OPTIONS`에서 파생 → 자동 갱신
- 토글 UI는 `SOURCE_OPTIONS.map`이라 2개로 자동 적응 — 추가 변경 없음

---

## 5. 테스트

### 5.1 `merge_papers` 단위 테스트 (`test_search_agent.py` 또는 신규 파일)

| # | 검증 |
|---|---|
| 1 | 같은 DOI → 필드별 best-of (긴 abstract 채택, OpenAlex country 채택, `country_lookup_done` 전파, citation max) |
| 2 | DOI 없는 논문 → 정규화 title로 dedup |
| 3 | DOI·title 둘 다 없는 논문 → dedup 안 하고 유지 |
| 4 | 겹치지 않는 논문 → 전부 유지 |
| 5 | 결과가 `citation_count` 내림차순 정렬 |

### 5.2 `search_combined` 테스트 (agent mock)

| # | 검증 |
|---|---|
| 1 | 둘 다 성공 → 병합 결과 반환 |
| 2 | S2 예외 → OpenAlex 결과만 반환 + warning 로그 |
| 3 | OpenAlex 예외 → S2 결과만 반환 |
| 4 | 둘 다 예외 → `RuntimeError` |

### 5.3 `test_pipeline.py` 수정

- 기존 `test_concurrency_*` 5개는 `_concurrency_for`/`CONCURRENCY` 제거로 전부 폐기. `SOURCE_PLAN` 기반 테스트로 교체:
  - `SOURCE_PLAN["combined"] == {"semantic_scholar": 1, "openalex": 10}`
  - `SOURCE_PLAN["scopus"] == {"scopus": 5}`
- 가드 테스트: `set(SOURCE_PLAN) == literal_sources` (= `{"combined", "scopus"}`) — Literal과 plan 키 드리프트 방지
- 기존 `test_concurrency_unknown_source_falls_back_to_serial`은 폐기 — `_concurrency_for` fallback이 사라지고 `search_node`가 `SOURCE_PLAN[...]`로 직접 조회. unknown source는 schema의 Literal 검증에서 이미 차단되므로 fallback 자체가 불필요

### 5.4 회귀 확인

- `test_search_agent.py`의 기존 S2 `search_papers_for_indicator` 테스트 (시그니처 불변 → 통과 유지)
- `test_pipeline_task.py` 풀 플로우 (Celery task mock → 영향 없음 예상)

---

## 6. 커밋 / 검증

### 단일 commit

`feat(search): combined OpenAlex + Semantic Scholar source`

변경 파일:
- `backend/app/agents/search_agent.py` (수정 — `merge_papers`, `search_combined`, `search_all_sources`)
- `backend/app/agents/pipeline.py` (수정 — `SOURCE_PLAN`, `search_node`)
- `backend/app/schemas/tech_query.py` (수정)
- `backend/app/models/tech_query.py` (수정)
- `backend/app/utils.py` (수정 — `get_engine_label`)
- `backend/alembic/versions/<revision>.py` (신규 마이그레이션)
- `frontend/src/pages/InputPage.tsx` (수정)
- `backend/tests/test_search_agent.py` 및/또는 신규 테스트 파일 (수정/신규)
- `backend/tests/test_pipeline.py` (수정)

### 검증 명령

```bash
docker compose exec api pytest tests/ -v          # 전체 통과
docker compose exec api alembic upgrade head      # 마이그레이션 적용
```

### 위험 요소 및 완화

| 위험 | 완화 |
|---|---|
| OpenAlex + S2 동시 호출이 rate limit 초과 | S2는 `Semaphore(1)` + `inter_attempt_sleep=1.3` 유지. OpenAlex는 `Semaphore(10)`, 한도 ~100 req/s 이내 |
| `search_all_sources` 시그니처 변경(`semaphore`→`semaphores`)이 호출처 깨뜨림 | 호출처는 `search_node` 한 곳. 기존 테스트는 agent 함수를 직접 호출하므로 영향 없음 — 구현 시 확인 |
| `SOURCE_PLAN` 키와 `search_source` Literal 불일치 | 테스트 5.3의 가드가 드리프트 감지 |
| 마이그레이션 downgrade가 비가역(openalex/semantic_scholar 구분 손실) | docstring에 명시. 운영상 문제 없음 (search_source는 표시·라우팅용) |
| 병합 후 논문 수가 늘어 extract 비용 증가 | `extract_node`가 `[:max_papers_per_indicator]`(30)로 절단 — citation 정렬로 상위 30 생존. 비용 상한 동일 |

---

## 7. Scope 제외 (YAGNI / 별도 사이클)

- **키워드 프롬프트 개선 + 추출 힌트 분리** — 스펙 B, 별도 사이클
- **`SEARCH_YEAR_FROM` 완화, abstract 보강** — 다른 수율 요인, 이 스펙 범위 밖
- **`max_papers_per_indicator` 상향** — 30 유지. 소스별 30씩 받아 병합 후 downstream 절단
- **`Source` 전략 객체 추상화** — 선택지 2개뿐, 함수 디스패치로 충분
- **Scopus + combined 동시 사용** — 사용자가 2지선다로 명시. composite는 `combined` 하나

---

## 8. 후속 작업

본 스펙 완료 후 **스펙 B** (키워드 프롬프트 개선 + 추출 힌트 분리) 브레인스토밍 사이클 진행.
