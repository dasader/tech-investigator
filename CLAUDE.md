# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

TechSpec — 기술 분야(예: HBM, 양자컴퓨터)를 입력하면 Semantic Scholar에서 논문을 검색하고, Gemini로 수치를 추출해 글로벌 최고 달성치를 보고서로 생성하는 서비스.

## 실행 명령어

```bash
# 전체 스택 실행 (최초 또는 코드 변경 후)
docker compose up --build

# 마이그레이션 적용 (최초 실행 후 또는 모델 변경 후)
docker compose exec api alembic upgrade head

# 테스트 (Docker 내부에서만 실행 가능 — celery 등 인프라 의존성)
docker compose exec api pytest
docker compose exec api pytest backend/tests/test_validation_agent.py -v

# 마이그레이션 신규 생성
docker compose exec api alembic revision --autogenerate -m "설명"

# 프론트엔드 개발 서버 (Docker 없이)
cd frontend && npm install && npm run dev
```

## 포트

| 서비스 | 호스트 포트 |
|--------|-----------|
| API (FastAPI) | 8017 |
| Frontend | 8098 |
| PostgreSQL | 5439 |
| Redis | 6381 |
| MinIO API | 9000 |
| MinIO Console | 9001 |

## 아키텍처

### 전체 흐름

```
사용자 입력 (기술명 + 이메일)
  → POST /api/tech-queries         # TechQuery 생성
  → Gemini가 지표 목록 제안         # IndicatorAgent
  → 사용자 지표 확정
  → POST /api/queries/{id}/jobs    # Celery 태스크 큐잉
  → WebSocket /ws/jobs/{id}        # 실시간 진행 상태
  → GET /api/jobs/{id}/results     # 완료 후 결과 조회
  → GET /api/jobs/{id}/pdf         # 보고서 HTML (인쇄 → PDF)
```

### 파이프라인 (4단계, `backend/app/agents/pipeline.py`)

`run_pipeline_task` (Celery) → `asyncio.run(run_pipeline(...))` 순으로 실행:

1. **search_node** — Semantic Scholar API로 지표당 논문 검색 (`search_agent.py`)
2. **extract_node** — Gemini에게 각 논문 초록에서 수치 추출 (`extraction_agent.py`), 동시성 `Semaphore(10)`
3. **validate_node** — 신뢰도 필터링 + 상위 3개 선별, DB 저장 (`validation_agent.py`)
4. **synthesize_node** — Gemini로 마크다운 보고서 생성 (`synthesis_agent.py`)

### 핵심 패턴

**Gemini SDK 호출** — SDK가 동기 전용이므로 모두 `app/utils.py`의 `run_sync()`로 래핑:
```python
from app.utils import run_sync
response = await run_sync(lambda: genai_client.models.generate_content(...))
```

**국가 정보** — Semantic Scholar affiliations는 대부분 빈값. 대신 OpenAlex API를 DOI로 조회 (`_get_country_from_openalex` in `extraction_agent.py`). Gemini 호출과 `asyncio.gather()`로 병렬 실행.

**SQLAlchemy 모델 초기화 주의** — `main.py`와 `pipeline_task.py` 양쪽에 모든 모델을 명시적으로 import해야 FK 관계가 정상 작동. 모델 추가 시 두 파일 모두 업데이트 필요.

**보고서 PDF** — weasyprint 버그로 서버사이드 생성 불가. `/api/jobs/{id}/pdf`는 HTML을 반환하고 브라우저 `window.print()`로 저장.

### DB 스키마

```
tech_queries → indicators (query_id FK, confirmed_by_user)
tech_queries → jobs (query_id FK, status/progress_pct/current_step/report_markdown)
indicators   → metric_values (indicator_id FK, value/unit/year/country/confidence_score/doi)
```

### 프론트엔드

React SPA (Vite + Tailwind), 라우터 없이 `App.tsx`의 `step` 상태로 4단계 전환:
`input` → `indicators` → `status` → `results`

진행 상태는 WebSocket(`useJobStatus.ts`)으로 polling. 결과 페이지는 보고서/데이터 탭으로 구분되며, 데이터 탭에는 `TimeSeriesChart`(연도별)와 `CountryCompareChart`(국가별) 차트 포함.
