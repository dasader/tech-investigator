# Elsevier Scopus API 통합 설계

**날짜:** 2026-05-11  
**상태:** 승인됨

## 개요

기존 Semantic Scholar 기반 논문 검색에 더해 Elsevier Scopus Search API를 선택적으로 사용할 수 있도록 통합한다. 초기화면에서 사용자가 분석에 사용할 API를 선택하고, 선택 정보는 `tech_queries.search_source` 컬럼에 저장되어 파이프라인 실행 시 라우팅에 활용된다.

## 아키텍처

### 데이터 흐름

```
InputPage (search_source 선택)
  → POST /api/tech-input  (search_source 포함)
  → tech_queries.search_source 저장
  → Job 생성 → Celery 태스크
  → run_pipeline() → query.search_source 읽음
  → search_node: search_all_sources(source=search_source)
      → "semantic_scholar": 기존 search_agent.py
      → "scopus": 새 scopus_agent.py
  → extract_node: 기존 extraction_agent.py
      → paper.country 있으면 OpenAlex 스킵 (Scopus 경우)
      → paper.country 없으면 OpenAlex 호출 (Semantic Scholar 경우)
```

### 컴포넌트 경계

| 컴포넌트 | 책임 |
|---------|------|
| `scopus_agent.py` | Scopus API 호출, 응답 정규화 (country 포함) |
| `search_agent.py` | source 파라미터로 적절한 에이전트에 위임 |
| `extraction_agent.py` | paper.country 선결정 여부에 따라 OpenAlex 스킵 |
| `pipeline.py` | query.search_source를 PipelineState에 주입 |

## 상세 설계

### 1. DB 스키마 변경

**`tech_queries` 테이블에 컬럼 추가:**
```sql
ALTER TABLE tech_queries ADD COLUMN search_source VARCHAR(30) DEFAULT 'semantic_scholar' NOT NULL;
```

Alembic 마이그레이션으로 처리. 기존 레코드는 `semantic_scholar`로 자동 채워짐.

### 2. Scopus Search API 연동 (`agents/scopus_agent.py`)

- **엔드포인트:** `https://api.elsevier.com/content/search/scopus`
- **인증:** `X-ELS-APIKey: {elsevier_api_key}` 헤더
- **요청 파라미터:**
  - `query`: 키워드
  - `count`: max_results
  - `field`: `dc:title,dc:description,prism:doi,citedby-count,prism:coverDate,affiliation`
  - `date`: `{search_year_from}-` (설정된 경우)
- **Rate limit:** `asyncio.sleep(1.1)` + 429 시 최대 3회 재시도 (Semantic Scholar와 동일)
- **응답 정규화:** Scopus 응답을 기존 파이프라인과 호환되는 dict 구조로 변환

```python
{
    "paper_id": entry["dc:identifier"],
    "title": entry["dc:title"],
    "abstract": entry.get("dc:description", ""),
    "year": int(entry["prism:coverDate"][:4]) if entry.get("prism:coverDate") else None,
    "citation_count": int(entry.get("citedby-count", 0)),
    "doi": entry.get("prism:doi"),
    "country": _resolve_country(entry.get("affiliation", [])),
}
```

**국가 결정 (`_resolve_country`):**
- Scopus `affiliation` 배열의 첫 번째 항목 `affiliation-country` 필드 사용
- `_COUNTRY_CODES` 매핑 적용 (extraction_agent.py의 기존 매핑과 동일한 형태)
- affiliation 없으면 `None` 반환

### 3. 검색 라우팅 (`agents/search_agent.py`)

`search_all_sources()` 시그니처 변경:
```python
async def search_all_sources(
    keywords: str,
    source: str = "semantic_scholar",
    max_results: int | None = None,
    semaphore: asyncio.Semaphore | None = None,
) -> list[dict]:
```

내부에서 `source` 값에 따라 분기:
- `"scopus"` → `scopus_agent.search_papers_for_indicator()` 호출
- 그 외 → 기존 `search_papers_for_indicator()` 호출 (Semantic Scholar)

### 4. 파이프라인 변경 (`agents/pipeline.py`)

`PipelineState`에 필드 추가:
```python
search_source: str  # "semantic_scholar" | "scopus"
```

`run_pipeline()`에서 `query.search_source` 읽어 state 주입:
```python
"search_source": query.search_source or "semantic_scholar",
```

`search_node`에서 source 전달:
```python
search_all_sources(keywords, source=state["search_source"], semaphore=semaphore)
```

### 5. 국가 정보 처리 (`agents/extraction_agent.py`)

`_country_coro()` 수정:
```python
async def _country_coro() -> str | None:
    if paper.get("country"):       # Scopus에서 이미 채워진 경우
        return paper["country"]
    return await _get_country_from_openalex(doi) if doi else None
```

Scopus 사용 시 OpenAlex API 호출 완전 생략 → 추출 단계 속도 향상.

### 6. 설정 (`config.py`)

```python
elsevier_api_key: str = ""
```

`.env`에 `ELSEVIER_API_KEY=<키값>` 추가 필요.

### 7. API 스키마/라우터

`TechQueryCreate` 스키마:
```python
search_source: str = "semantic_scholar"  # "semantic_scholar" | "scopus"
```

`tech_input.py` 라우터:
```python
query = TechQuery(
    category=payload.category,
    description=payload.description,
    user_email=payload.user_email,
    search_source=payload.search_source,
)
```

### 8. 프론트엔드 (`InputPage.tsx`)

"분석 설정" 카드 안에 API 선택 세그먼트 컨트롤 추가 (기술 분야 섹션 아래):

```
[ Semantic Scholar ]  [ Scopus (Elsevier) ]
```

- 기본값: `semantic_scholar`
- 상태: `const [searchSource, setSearchSource] = useState("semantic_scholar")`
- `createTechInput()` 호출 시 `search_source: searchSource` 포함
- 하단 안내 문구 동적 변경:
  - Semantic Scholar: `"Semantic Scholar 논문 데이터 기반 · Gemini AI 수치 추출 · 분석 소요 5–15분"`
  - Scopus: `"Scopus (Elsevier) 논문 데이터 기반 · Gemini AI 수치 추출 · 분석 소요 5–15분"`

`api/client.ts`:
```typescript
export const createTechInput = (data: {
  category: string;
  description: string;
  user_email?: string;
  search_source?: string;
}) => api.post("/tech-input", data).then(r => r.data);
```

## 변경 파일 목록

| 파일 | 변경 종류 |
|------|---------|
| `backend/app/config.py` | `elsevier_api_key` 필드 추가 |
| `backend/app/models/tech_query.py` | `search_source` 컬럼 추가 |
| `backend/alembic/versions/<hash>_add_search_source.py` | 신규 마이그레이션 |
| `backend/app/agents/scopus_agent.py` | 신규 파일 — Scopus 검색 에이전트 |
| `backend/app/agents/search_agent.py` | `source` 파라미터 추가, 라우팅 |
| `backend/app/agents/extraction_agent.py` | `country` 선결정 로직 |
| `backend/app/agents/pipeline.py` | `search_source` state 주입 |
| `backend/app/schemas/tech_query.py` | `search_source` 필드 |
| `backend/app/routers/tech_input.py` | `search_source` 저장 |
| `frontend/src/pages/InputPage.tsx` | API 선택 UI |
| `frontend/src/api/client.ts` | `search_source` 전달 |
| `.env` | `ELSEVIER_API_KEY` 추가 |

## 제약 사항

- Scopus API 키 없이 `search_source=scopus` 설정 시 파이프라인 실패 → 설정 누락 시 명확한 에러 메시지 필요
- Scopus affiliation 데이터가 없는 논문은 `country=None`으로 처리 (OpenAlex 대체 호출 없음)
- ScienceDirect, OpenAlex 등 추가 소스는 이 설계의 범위 밖
