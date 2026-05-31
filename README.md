# TechSpec

기술 분야명을 입력하면 학술 논문을 검색하고 Gemini로 정량 지표 수치를 추출해 **글로벌 최고 달성치 보고서**를 자동 생성하는 서비스.

예: `HBM` → "메모리 대역폭", "TSV 피치", "스택 적층 수" 등 지표 자동 제안 → 논문에서 수치 추출 → 보고서 마크다운/PDF 출력.

---

## 주요 기능

- **자동 지표 제안** — Gemini가 입력된 기술 분야에 적합한 정량 지표 5~10개와 검색 키워드·추출 단서를 제안. 사용자가 검토·수정·확정.
- **멀티 소스 논문 검색** — Semantic Scholar + OpenAlex 동시 검색(`combined` 모드) 또는 Scopus 단독(`scopus` 모드). DOI/title 기반 best-of 머지.
- **Gemini 수치 추출** — 논문 abstract에서 지표별 수치·단위·근거 문장을 JSON으로 추출. 단위 환산(예: TB/s → GB/s) 포함.
- **신뢰도 검증 + 순위화** — `confidence_score` 임계값 필터링 후 value 상위 N개 선별.
- **보고서 생성** — 마크다운 보고서 + 브라우저 인쇄로 PDF 저장. 연도별/국가별 차트 포함.
- **이메일 알림** — 작업 완료 시 사용자 이메일로 1회 발송 (선택).
- **실시간 진행 상태** — WebSocket으로 단계별 진행률 push.

---

## 기술 스택

| 영역 | 사용 기술 |
|------|----------|
| Backend | FastAPI, SQLAlchemy, Alembic, Celery, aiosmtplib |
| AI / 검색 | Google Gemini (`google-genai`), Semantic Scholar API, OpenAlex API, Scopus API |
| DB / 인프라 | PostgreSQL 16, Redis 7, MinIO (S3 호환) |
| Frontend | React + TypeScript, Vite, Tailwind CSS, Recharts |
| Orchestration | Docker Compose |

---

## 빠른 시작

### 사전 요구사항
- Docker Desktop
- Gemini API 키 ([Google AI Studio](https://aistudio.google.com/apikey) 발급)

### 실행

```bash
# 1. .env 파일 작성
cp backend/.env.example .env
# .env를 열어 GEMINI_API_KEY 입력 (최소 요건)
# 선택: SEMANTIC_SCHOLAR_API_KEY, ELSEVIER_API_KEY 등

# 2. 전체 스택 기동
docker compose up --build

# 3. (최초 1회) DB 마이그레이션
docker compose exec api alembic upgrade head
```

접속:
- 프론트엔드: <http://localhost:8098>
- API: <http://localhost:8017> (Swagger: `/docs`)

---

## 포트 매핑

| 서비스 | 호스트 포트 | 컨테이너 포트 |
|--------|-----------|--------------|
| API (FastAPI) | 8017 | 8000 |
| Frontend (Nginx) | 8098 | 80 |
| PostgreSQL | 5439 | 5432 |
| Redis | 6381 | 6379 |
| MinIO API | 9000 | 9000 |
| MinIO Console | 9001 | 9001 |

---

## 아키텍처

```
사용자 → Frontend (React)
            │
            ▼
        FastAPI API ─────┐
            │            │
            ▼            ▼
      Celery Worker   WebSocket (진행 상태)
            │
            ▼
    파이프라인 (4단계):
    1) search_node    — 논문 검색 (S2 + OpenAlex / Scopus)
    2) extract_node   — Gemini 수치 추출
    3) validate_node  — 신뢰도 필터 + 순위화 → DB 저장
    4) synthesize_node — 보고서 마크다운 생성
            │
            ▼
      이메일 알림 (옵션)
```

상세 설계와 운영 노트는 [CLAUDE.md](./CLAUDE.md) 참고.

---

## 주요 환경변수

`.env` 예시는 [`backend/.env.example`](./backend/.env.example) 참고.

| 변수 | 필수 | 설명 |
|------|:----:|-----|
| `GEMINI_API_KEY` | ✅ | Google Gemini API 키 |
| `DATABASE_URL` | ✅ | PostgreSQL 연결 문자열 |
| `GEMINI_MODEL_FAST` | | 빠른 단계용 모델 (기본: `gemini-3.1-flash-lite`) |
| `GEMINI_MODEL_COMPLEX` | | 합성 단계용 모델 (기본: `gemini-3.5-flash`) |
| `SEMANTIC_SCHOLAR_API_KEY` | | S2 rate limit 완화 (선택) |
| `ELSEVIER_API_KEY` | | Scopus 사용 시 필요 |
| `OPENALEX_API_KEY` | | OpenAlex polite pool용 (선택) |
| `MAX_PAPERS_PER_INDICATOR` | | 지표당 검색 논문 수 (기본: 50) |
| `MIN_CONFIDENCE_SCORE` | | 검증 신뢰도 임계값 (기본: 0.5) |
| `SMTP_USER`, `SMTP_PASSWORD` | | 이메일 알림 활성화 (선택) |

---

## 디렉터리 구조

```
.
├── backend/
│   ├── app/
│   │   ├── agents/        # 파이프라인 노드: search, extract, validate, synthesize, indicator
│   │   ├── models/        # SQLAlchemy 모델 (TechQuery, Indicator, Job, MetricValue)
│   │   ├── routers/       # FastAPI 라우터 (tech_input, indicators, jobs, results, websocket)
│   │   ├── services/      # email_service 등
│   │   ├── tasks/         # Celery 태스크 (pipeline_task)
│   │   ├── config.py      # pydantic-settings
│   │   └── main.py        # FastAPI 엔트리
│   ├── alembic/           # 마이그레이션
│   └── tests/             # pytest
├── frontend/
│   └── src/
│       ├── pages/         # InputPage, IndicatorEditorPage, JobStatusPage, ResultsPage
│       └── components/    # 차트, 진행률, 표 등
├── docker-compose.yml
└── CLAUDE.md              # 개발 가이드 (아키텍처·운영 노트)
```

---

## 개발

### 테스트

```bash
# 전체
docker compose exec api pytest

# 특정 파일
docker compose exec api pytest backend/tests/test_validation_agent.py -v
```

> 테스트는 Docker 컨테이너 안에서만 실행 가능 — Gemini SDK·DB·Redis 등 컨테이너 의존성이 있음.

### 마이그레이션 생성

```bash
docker compose exec api alembic revision --autogenerate -m "설명"
docker compose exec api alembic upgrade head
```

### 프론트엔드 핫리로드

```bash
cd frontend && npm install && npm run dev
```

Docker 없이 실행 가능. API는 `http://localhost:8017`을 가리키도록 설정되어 있어야 함.

---

## 참고

- 보고서 PDF는 weasyprint의 한글/CSS 이슈로 서버사이드 생성 대신 브라우저 `window.print()` 방식 사용.
- Semantic Scholar의 affiliations는 대부분 비어 있어 OpenAlex API를 DOI로 추가 조회해 국가 정보를 보강.
- `extraction_hint` 컬럼으로 지표별 단위 환산·혼동 가능 개념 단서를 Gemini에 전달.
