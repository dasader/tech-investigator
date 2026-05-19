# KCI Open API 통합 설계

**Date:** 2026-05-19
**Status:** Approved (brainstorming)
**Scope:** `combined` 검색 모드에 KCI(한국학술지 인용색인) Open API를 자동 병합. `scopus` 모드는 변경하지 않는다.

## 1. 배경과 목표

이 서비스는 기술 분야를 입력하면 Semantic Scholar / OpenAlex / Scopus에서 논문을 검색하고 Gemini로 수치를 추출해 "글로벌 최고 달성치"를 보고서로 생성한다. 현재 `combined` 모드는 OpenAlex + Semantic Scholar 동시 검색 + best-of 머지로 운영된다.

한국 연구진의 SOTA는 대부분 영문 international venue로 발표되어 S2/OpenAlex에 인덱싱되지만, **국내 학술지에만 게재된 한국 연구**는 누락된다. KCI Open API(KISTI 운영, `open.kci.go.kr`)를 `combined`의 세 번째 소스로 추가하여 한국 연구 커버리지를 보강한다.

기대 효과:
- KCI 한정 한국 논문이 결과에 포함되어 보고서의 `CountryCompareChart`에서 한국 비중이 증가.
- 동일 논문이 KCI와 OpenAlex 양쪽에 있으면 best-of 머지가 한국 기관 메타데이터를 누락 없이 합침.

비목표:
- KCI 단독 모드 신설.
- `scopus` 모드에 KCI 통합.
- IndicatorAgent의 한/영 키워드 쌍 생성(현재 영문 단일 키워드 그대로 사용).
- DB schema 변경.

## 2. 사용자 결정 사항 (brainstorming 합의)

| 결정 항목 | 선택 | 근거 |
|-----------|------|------|
| 통합 모드 | `combined`에 자동 병합 | 사용자가 별도 토글을 만지지 않아도 한국 연구가 포함됨 |
| 질의 언어 | 영문 그대로 전송 (최소 구현) | 스키마/Indicator 단계 변경 0. KCI 영문 메타데이터에 한해 매칭되므로 recall은 낮지만 precision은 충분 |
| 통합 패턴 | 3-way 동시 검색 + best-of merge (Approach A) | Scopus의 S2-batch-abstract-보강 패턴과 동일한 캡슐화. 외부에서 KCI 내부 N+1 호출이 보이지 않음 |

## 3. 아키텍처

```
search_node (pipeline.py)
  └─ search_all_sources(source="combined")
       └─ search_combined  ← 3-way로 확장
            ├─ search_papers_for_indicator (S2)
            ├─ openalex_agent.search_papers_for_indicator
            └─ kci_agent.search_papers_for_indicator  ← 신규
                  ├─ articleSearch.kci   (메타데이터 + articleId 목록)
                  └─ articleDetail.kci × N (abstract 보강)
       └─ merge_papers  ← *paper_lists 가변 인자로 일반화
```

핵심 원칙:
- `kci_agent`의 공개 함수는 S2/OpenAlex와 **동일한 시그니처**(`keywords, max_results, semaphore, *, client` → `list[paper_dict]`). 호출자는 KCI 내부 N+1 호출을 의식하지 않는다.
- `asyncio.gather(..., return_exceptions=True)`로 3-way 부분 실패에 그레이스풀 다운. 셋 다 실패 시에만 `RuntimeError`.
- KCI key 미설정(`settings.kci_api_key == ""`) 시 `kci_agent`는 즉시 빈 리스트 반환(예외 없이). 기존 `.env`에 KCI 키 없는 환경도 깨지지 않는다.

## 4. `kci_agent` 모듈 (`backend/app/agents/kci_agent.py`)

### 4.1 공개 인터페이스

```python
async def search_papers_for_indicator(
    keywords: str,
    max_results: int | None = None,
    semaphore: asyncio.Semaphore | None = None,
    *,
    client: httpx.AsyncClient,
) -> list[dict]
```

S2/OpenAlex agent와 시그니처 호환.

### 4.2 내부 흐름

1. **빈 키 가드** — `if not settings.kci_api_key: return []`.
2. **articleSearch.kci 호출** — `searchQuery=keywords`, `displayCount=min(max_results, 100)`. 외부 `semaphore`로 indicator 간 동시성 제한. 응답 XML에서 `articleId`, `title (ko/eng)`, `year`, `doi`, `journalName (ko/eng)`, `citationCount`를 추출.
3. **articleDetail.kci × N** — articleId별 abstract(한/영) 보강. 모듈 내부 `_DETAIL_SEM = asyncio.Semaphore(5)`로 detail 호출 throttling. 개별 detail 실패는 warning 로깅 후 해당 paper drop (전체 실패로 처리하지 않음).
4. **정규화** — paper dict 변환:
   ```python
   {
     "paper_id": article_id,
     "title":    en_title or ko_title,
     "abstract": en_abstract or ko_abstract,
     "year": int,
     "citation_count": int,
     "doi": doi or None,
     "journal_name": en_journal or ko_journal,
     "country": "South Korea",
     "country_lookup_done": True,
   }
   ```
5. **abstract 필터** — 한/영 모두 비어 있으면 drop.
6. **로깅** — `[KCI] keywords=%r returned=%d after_detail_fetch=%d after_abstract_filter=%d`.

### 4.3 HTTP / XML 처리

- HTTP 재시도: 기존 `app.agents._http_retry.get_with_retry`를 articleSearch와 articleDetail 양쪽에 재사용.
- `inter_attempt_sleep=0.2`로 KCI 일일 호출량 보호.
- XML 파싱: `xml.etree.ElementTree` (stdlib). 새 의존성 없음.
- XML `ParseError`는 `RuntimeError`로 변환해 재시도 흐름과 일관성 유지(예: KCI가 일시적으로 HTML 오류 페이지를 반환할 때).

### 4.4 구현 시 확정 사항

다음 항목은 사용자가 발급받은 KCI API 문서로 구현 시 확정한다. 외부 인터페이스가 동일하므로 설계 영향은 없다.

- 정확한 base URL과 `apiCode` 명칭 (예: `articleSearch` vs `openApiSearch`).
- 응답 XML element 이름 (`<articleId>`, `<title language="kor">` 등).
- 인증 방식 (query param `key` vs 헤더).

## 5. `merge_papers` 일반화 (`backend/app/agents/search_agent.py`)

### 5.1 시그니처 변경

```python
def merge_papers(*paper_lists: list[dict]) -> list[dict]:
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

`_merge_two`는 변경 없음 — 이미 필드별 best-of(citation max, abstract longer, country/title/doi first-truthy, `country_lookup_done` OR) 이라 N-way에 자연 확장된다.

### 5.2 호출 순서가 만드는 동작

`search_combined`는 `merge_papers(s2_papers, oa_papers, kci_papers)` 순서로 호출한다.

- 동일 DOI가 OpenAlex와 KCI 양쪽에 있는 경우: `_first_truthy(existing.country, kci.country)`로 OA 기관 affiliation이 우선, KCI default "South Korea"가 fallback. 의도된 동작.
- KCI-only 한국 논문은 country="South Korea"로 살아남는다.

## 6. `search_combined` 변경

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
    results = await asyncio.gather(
        search_papers_for_indicator(keywords, max_results, s2_semaphore, client=client),
        openalex_agent.search_papers_for_indicator(keywords, max_results, openalex_semaphore, client=client),
        kci_agent.search_papers_for_indicator(keywords, max_results, kci_semaphore, client=client),
        return_exceptions=True,
    )
    names = ("S2", "OpenAlex", "KCI")
    failed = [n for n, r in zip(names, results) if isinstance(r, BaseException)]
    if len(failed) == 3:
        raise RuntimeError(f"all sources failed for {keywords!r}: {results}")
    for name, r in zip(names, results):
        if isinstance(r, BaseException):
            logger.warning("combined search: %s failed for %r (%s)", name, keywords, r)
    papers_lists = [[] if isinstance(r, BaseException) else r for r in results]
    return merge_papers(*papers_lists)
```

`search_all_sources`에서 `semaphores["kci"]`를 `kci_semaphore=`로 전달.

## 7. `SOURCE_PLAN` 변경 (`pipeline.py`)

```python
SOURCE_PLAN: dict[str, dict[str, int]] = {
    "combined": {"semantic_scholar": 1, "openalex": 10, "kci": 3},
    "scopus":   {"scopus": 5},
}
```

`"kci": 3` 근거 — KCI는 indicator 1개당 articleSearch×1 + articleDetail×N 호출이라 가장 무거운 소스. 지표 3개까지만 병렬화하여 KCI 일일 호출량을 보호한다. 모듈 내부 `_DETAIL_SEM=5`와 곱하면 약 15 detail/sec가 상한.

## 8. 설정 변경

### 8.1 `backend/app/config.py`

```python
class Settings(BaseSettings):
    ...
    kci_api_key: str = ""
```

### 8.2 `.env.example` (루트)

```
KCI_API_KEY=your_kci_open_api_key
```

기존 패턴(`SEMANTIC_SCHOLAR_API_KEY`, `OPENALEX_API_KEY` 등)과 동일.

**중요**: 실제 사용되는 환경변수 파일은 **루트 `.env`** 한 곳뿐이다. `docker-compose.yml`의 `env_file: .env`가 compose 파일이 위치한 루트 기준이라, 거기서 읽어 컨테이너에 환경변수로 주입한다. `backend/.env.example`(과 그 짝인 `backend/.env`)는 과거 잔존 파일로, 빌드 컨텍스트(`./backend`) 안에 있을 뿐 Docker나 Pydantic이 우선적으로 읽지 않는다(루트 `.env`의 환경변수가 이미 주입돼 있어 덮어쓰임). 이번 task의 `backend/.env.example` 갱신은 일관성 유지를 위한 것이며 실제 키 설정은 루트 `.env`에 한다.

## 9. 국가·abstract·downstream 동작

### 9.1 KCI 논문의 country

- 항상 `"South Korea"` default. KCI는 한국학술지 인용색인이라 99%+ 한국 기관 논문. 예외(공동저자 1순위가 외국 기관)는 무시 — 보고서 맥락상 "한국 연구"로 분류되는 게 자연스럽다.
- `country_lookup_done=True`로 set → `extraction_agent._country_coro`의 OpenAlex 재조회 분기를 차단(KCI DOI로 OpenAlex 조회해도 결과 없을 가능성이 높음).

### 9.2 abstract 언어 우선순위

- `en_abstract`가 비어있지 않으면 사용 → 없으면 `ko_abstract` 사용.
- 둘 다 비어있으면 paper drop (S2/OA와 동일 정책).
- 근거: Gemini는 한/영 모두 처리 가능하나, 영문 abstract가 수치 표기(SI 단위·숫자 표기)가 더 표준화되어 추출 정확도가 미세하게 높다.

### 9.3 title 언어 우선순위

abstract와 같은 언어 매칭이 자연스러움. `en_title` 우선 → 없으면 `ko_title`.

### 9.4 downstream 영향

- Gemini 추출 결과의 `quote` 필드는 abstract의 언어를 그대로 따른다. 보고서는 한국어이므로 한글 quote가 섞여도 자연스럽다. 추가 후처리 없음.
- `validate_and_rank`의 confidence ≥ 0.5 + value 큰 순 + top 5 필터는 그대로 둔다. KCI-only 한국 논문이 글로벌 SOTA 대비 작은 값이면 자연스럽게 잘려나간다 — top 5는 수치 우수성으로 선별돼야지 출신 소스로 우대받지 않는다.

## 10. 오류 처리·graceful degrade

- **3-way 부분 실패**: 1~2개 소스가 raise → warning 로깅 후 나머지 소스만으로 merge. 셋 다 실패 시 `RuntimeError`(기존 `combined`와 동일 정책).
- **KCI key 미설정**: `kci_agent`가 빈 리스트 즉시 반환. S2+OA 결과만으로 정상 동작.
- **articleSearch.kci 실패**: KCI 전체 실패로 처리 → `search_combined`에서 graceful degrade.
- **articleDetail.kci 일부 실패**: 해당 paper만 drop, warning 로깅. 나머지 paper는 정상 반환.
- **XML ParseError**: `RuntimeError`로 변환.

## 11. 테스트

### 11.1 신규 — `backend/tests/test_kci_agent.py`

1. `test_kci_search_returns_papers` — 정상 articleSearch + articleDetail mock 응답. paper dict 정규화 검증 (title/abstract 영문 우선, country="South Korea", country_lookup_done=True).
2. `test_kci_search_korean_abstract_fallback` — 영문 abstract 빈 응답 → 한글 abstract로 fallback.
3. `test_kci_search_filters_no_abstract` — 한/영 모두 빈 abstract는 drop.
4. `test_kci_search_skips_when_no_api_key` — `settings.kci_api_key=""` → 빈 리스트 즉시 반환, HTTP 호출 0건.
5. `test_kci_detail_partial_failure` — articleSearch 5건 성공, articleDetail 중 2건 500 → 3건만 반환, warning 로깅.

### 11.2 갱신 — `backend/tests/test_search_agent.py`

6. `test_search_combined_3way_merge` — S2/OA/KCI 셋 다 정상 → merge 결과에 세 소스 모두 기여.
7. `test_search_combined_kci_failure_continues` — KCI만 raise → S2+OA로 정상 반환.
8. `test_search_all_sources_combined_passes_kci_semaphore` — `semaphores` dict에 `"kci"` 키가 전달되는지 검증.

### 11.3 갱신 — `backend/tests/test_utils.py`

9. `get_engine_label("combined")` 기댓값을 `"OpenAlex + Semantic Scholar + KCI + Gemini"`로 수정.

## 12. 프론트엔드·라벨 변경

### 12.1 `frontend/src/pages/InputPage.tsx`

```diff
- { value: "combined", label: "OpenAlex + Semantic Scholar" },
+ { value: "combined", label: "OpenAlex + Semantic Scholar + KCI" },
```

같은 파일의 `sourceLabel` fallback 문자열도 동일 변경.

### 12.2 `backend/app/utils.py`

```diff
- return "OpenAlex + Semantic Scholar + Gemini"
+ return "OpenAlex + Semantic Scholar + KCI + Gemini"
```

`ResultsPage`의 "분석 엔진" 표시에 반영됨.

### 12.3 타입·API 응답

`frontend/src/api/client.ts`의 `search_source?: "combined" | "scopus"` — 변경 없음.

## 13. DB·migration·API 응답

- `search_source` 컬럼 enum 변동 없음 → migration 불필요.
- API 응답 스키마(`/api/jobs/{id}`, `/api/jobs/{id}/results`) 변경 없음.
- 기존 데이터 호환성 유지.

## 14. 문서

- `CLAUDE.md` (루트): "검색 소스 모드" 섹션의 `combined` 설명을 `"Semantic Scholar + OpenAlex + KCI 동시 검색, DOI/title 기반 best-of 머지. 동시성 S2=1 / OpenAlex=10 / KCI=3"`로 갱신. 환경변수 설명에 `KCI_API_KEY` 1줄 추가.
- 본 spec 문서: `docs/superpowers/specs/2026-05-19-kci-integration-design.md`.

## 15. 변경 표면 요약

| 영역 | 파일 | 변경 |
|------|------|------|
| 신규 모듈 | `backend/app/agents/kci_agent.py` | 신규 |
| Search 통합 | `backend/app/agents/search_agent.py` | `search_combined` 3-way, `merge_papers` *args 시그니처 |
| Pipeline | `backend/app/agents/pipeline.py` | `SOURCE_PLAN["combined"]`에 `"kci": 3` |
| Config | `backend/app/config.py` | `kci_api_key: str = ""` |
| Engine label | `backend/app/utils.py` | combined 라벨에 "+ KCI" 추가 |
| .env | `.env.example`, `backend/.env.example` | `KCI_API_KEY=` 1줄 |
| Frontend | `frontend/src/pages/InputPage.tsx` | combined 라벨 텍스트 |
| 테스트 신규 | `backend/tests/test_kci_agent.py` | 5개 |
| 테스트 갱신 | `test_search_agent.py`, `test_utils.py` | 3+1개 |
| CLAUDE.md | 루트 | combined 설명 갱신 |

**DB/schema/API 응답 형식 변경 없음.**

## 16. 가정과 미해결 사항

- KCI Open API 엔드포인트의 정확한 URL과 응답 XML 구조는 사용자가 발급받은 문서로 구현 시 확정. 본 spec의 외부 인터페이스 설계는 영향받지 않음.
- KCI 일일 호출 한도가 매우 낮은 경우 `SOURCE_PLAN["combined"]["kci"]`와 `_DETAIL_SEM` 값을 사후 튜닝.
- `max_papers_per_indicator`가 50이지만 KCI 검색 풀이 작아 실제 반환은 그보다 적을 수 있음. 정상.
