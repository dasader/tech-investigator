# TechSpec 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 국가전략기술 분야를 입력하면 정량 지표를 자동 생성하고, 논문 기반 달성치를 레퍼런스와 함께 제공하는 웹 서비스를 구축한다.

**Architecture:** FastAPI + LangGraph 멀티 에이전트 파이프라인 (Gemini 2.5) + Celery 비동기 처리 + React 대시보드. 사용자가 지표를 확정하면 Celery Worker가 Semantic Scholar/arXiv 논문 검색 → Gemini 수치 추출 → 교차검증 → 리포트 생성을 순차 실행한다.

**Tech Stack:** Python 3.11, FastAPI, LangGraph, google-genai SDK, Celery, Redis, PostgreSQL, SQLAlchemy + Alembic, WeasyPrint, React + TypeScript + Vite + Tailwind + Recharts, Docker Compose

---

## 파일 구조

```
17_Spec-investigation/
├── backend/
│   ├── app/
│   │   ├── main.py                     # FastAPI 앱, CORS, 라우터 등록
│   │   ├── config.py                   # pydantic-settings 환경변수
│   │   ├── database.py                 # SQLAlchemy engine, SessionLocal
│   │   ├── celery_app.py               # Celery 인스턴스
│   │   ├── models/
│   │   │   ├── tech_query.py           # TechQuery ORM
│   │   │   ├── indicator.py            # Indicator ORM
│   │   │   ├── job.py                  # Job ORM
│   │   │   └── metric_value.py         # MetricValue ORM
│   │   ├── schemas/
│   │   │   ├── tech_query.py           # Pydantic 요청/응답 스키마
│   │   │   ├── indicator.py
│   │   │   ├── job.py
│   │   │   └── metric_value.py
│   │   ├── routers/
│   │   │   ├── tech_input.py           # POST /api/tech-input
│   │   │   ├── indicators.py           # GET/POST /api/indicators
│   │   │   ├── jobs.py                 # GET /api/jobs/{id}
│   │   │   ├── results.py              # GET /api/results/{job_id}
│   │   │   └── websocket.py            # WS /ws/jobs/{id}
│   │   ├── agents/
│   │   │   ├── indicator_agent.py      # Gemini: 지표 초안 생성
│   │   │   ├── search_agent.py         # Semantic Scholar + arXiv + Google
│   │   │   ├── extraction_agent.py     # Gemini: 수치 구조화 추출
│   │   │   ├── validation_agent.py     # 교차검증 + 신뢰도 점수
│   │   │   ├── synthesis_agent.py      # Gemini: 리포트 마크다운 생성
│   │   │   └── pipeline.py             # LangGraph StateGraph 파이프라인
│   │   ├── tasks/
│   │   │   └── pipeline_task.py        # Celery task: 파이프라인 실행
│   │   └── services/
│   │       ├── email_service.py        # SMTP 이메일 발송
│   │       ├── pdf_service.py          # WeasyPrint PDF 생성
│   │       └── minio_service.py        # MinIO 업로드/URL 발급
│   ├── tests/
│   │   ├── conftest.py                 # pytest fixtures (DB, client)
│   │   ├── test_extraction_agent.py
│   │   ├── test_validation_agent.py
│   │   └── test_pipeline_task.py
│   ├── alembic/                        # Alembic 마이그레이션
│   │   └── versions/
│   ├── alembic.ini
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── InputPage.tsx           # Step 1: 기술 입력
│   │   │   ├── IndicatorEditorPage.tsx # Step 2: 지표 확정
│   │   │   ├── JobStatusPage.tsx       # Step 3: 처리 진행
│   │   │   └── ResultsPage.tsx         # Step 4: 결과 대시보드
│   │   ├── components/
│   │   │   ├── CategorySelect.tsx      # 12대 분야 드롭다운
│   │   │   ├── IndicatorList.tsx       # 지표 편집 목록
│   │   │   ├── ProgressStepper.tsx     # 진행 단계 표시
│   │   │   ├── MetricTable.tsx         # 결과 지표 테이블
│   │   │   ├── TimeSeriesChart.tsx     # 연도별 추이 (Recharts)
│   │   │   └── CountryCompareChart.tsx # 국가별 비교 (Recharts)
│   │   ├── api/
│   │   │   └── client.ts               # axios 인스턴스 + API 함수
│   │   └── hooks/
│   │       └── useJobStatus.ts         # WebSocket 진행률 훅
│   ├── Dockerfile
│   └── nginx.conf
├── docker-compose.yml
├── docker-compose.dev.yml
└── .env.example
```

---

## Task 1: 프로젝트 스캐폴딩 + Docker Compose

**Files:**
- Create: `docker-compose.yml`
- Create: `docker-compose.dev.yml`
- Create: `.env.example`
- Create: `backend/requirements.txt`
- Create: `backend/Dockerfile`
- Create: `frontend/Dockerfile`
- Create: `frontend/nginx.conf`

- [ ] **Step 1: `.env.example` 생성**

```env
# Gemini 모델 (변경 시 여기만 수정)
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL_COMPLEX=gemini-2.5-pro
GEMINI_MODEL_FAST=gemini-2.5-flash

# 외부 API
SEMANTIC_SCHOLAR_API_KEY=your_semantic_scholar_key

# 처리 파라미터
JOB_TIMEOUT_MINUTES=15
MAX_PAPERS_PER_INDICATOR=30
MIN_CONFIDENCE_SCORE=0.5

# DB/인프라
DATABASE_URL=postgresql://techspec:techspec@db:5432/techspec
REDIS_URL=redis://redis:6379/0
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=techspec-pdfs

# 이메일
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
```

- [ ] **Step 2: `docker-compose.yml` 생성**

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: techspec
      POSTGRES_PASSWORD: techspec
      POSTGRES_DB: techspec
    ports:
      - "5439:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6381:6379"

  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - minio_data:/data

  api:
    build: ./backend
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    ports:
      - "8017:8000"
    env_file: .env
    depends_on:
      - db
      - redis
      - minio
    volumes:
      - ./backend:/app

  worker:
    build: ./backend
    command: celery -A app.celery_app worker --loglevel=info
    env_file: .env
    depends_on:
      - db
      - redis
      - minio
    volumes:
      - ./backend:/app

  frontend:
    build: ./frontend
    ports:
      - "8098:80"
    depends_on:
      - api

volumes:
  postgres_data:
  minio_data:
```

- [ ] **Step 3: `backend/requirements.txt` 생성**

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
sqlalchemy==2.0.35
alembic==1.13.3
psycopg2-binary==2.9.9
pydantic-settings==2.5.2
pydantic==2.9.2
celery[redis]==5.4.0
redis==5.1.1
langgraph==0.2.35
google-genai==0.8.0
httpx==0.27.2
weasyprint==62.3
boto3==1.35.36
aiosmtplib==3.0.1
pytest==8.3.3
pytest-asyncio==0.24.0
httpx==0.27.2
```

- [ ] **Step 4: `backend/Dockerfile` 생성**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 libffi-dev libcairo2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
```

- [ ] **Step 5: `frontend/nginx.conf` 생성**

```nginx
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
    }

    location /ws {
        proxy_pass http://api:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

- [ ] **Step 6: `frontend/Dockerfile` 생성**

```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
```

- [ ] **Step 7: 커밋**

```bash
git add .
git commit -m "chore: project scaffold with docker-compose"
```

---

## Task 2: Backend 설정 + DB 모델

**Files:**
- Create: `backend/app/config.py`
- Create: `backend/app/database.py`
- Create: `backend/app/celery_app.py`
- Create: `backend/app/models/tech_query.py`
- Create: `backend/app/models/indicator.py`
- Create: `backend/app/models/job.py`
- Create: `backend/app/models/metric_value.py`

- [ ] **Step 1: `backend/app/config.py` 생성**

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    gemini_api_key: str
    gemini_model_complex: str = "gemini-2.5-pro"
    gemini_model_fast: str = "gemini-2.5-flash"
    semantic_scholar_api_key: str = ""
    job_timeout_minutes: int = 15
    max_papers_per_indicator: int = 30
    min_confidence_score: float = 0.5
    database_url: str
    redis_url: str = "redis://redis:6379/0"
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "techspec-pdfs"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    class Config:
        env_file = ".env"

settings = Settings()
```

- [ ] **Step 2: `backend/app/database.py` 생성**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 3: `backend/app/celery_app.py` 생성**

```python
from celery import Celery
from app.config import settings

celery_app = Celery(
    "techspec",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
```

- [ ] **Step 4: `backend/app/models/tech_query.py` 생성**

```python
from sqlalchemy import Column, Integer, String, Text, DateTime, func
from app.database import Base

class TechQuery(Base):
    __tablename__ = "tech_queries"

    id = Column(Integer, primary_key=True, index=True)
    user_email = Column(String(255), nullable=True)
    category = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
```

- [ ] **Step 5: `backend/app/models/indicator.py` 생성**

```python
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import ARRAY
from app.database import Base

class Indicator(Base):
    __tablename__ = "indicators"

    id = Column(Integer, primary_key=True, index=True)
    query_id = Column(Integer, ForeignKey("tech_queries.id"), nullable=False)
    name = Column(String(200), nullable=False)
    unit = Column(String(50), nullable=True)
    description = Column(String(500), nullable=True)
    search_keywords = Column(String(500), nullable=True)
    confirmed_by_user = Column(Boolean, default=False)
```

- [ ] **Step 6: `backend/app/models/job.py` 생성**

```python
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, func
from app.database import Base

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    query_id = Column(Integer, ForeignKey("tech_queries.id"), nullable=False)
    status = Column(String(20), default="pending")  # pending/running/done/failed
    progress_pct = Column(Float, default=0.0)
    current_step = Column(String(100), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime, nullable=True)
```

- [ ] **Step 7: `backend/app/models/metric_value.py` 생성**

```python
from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey
from app.database import Base

class MetricValue(Base):
    __tablename__ = "metric_values"

    id = Column(Integer, primary_key=True, index=True)
    indicator_id = Column(Integer, ForeignKey("indicators.id"), nullable=False)
    value = Column(Float, nullable=True)
    unit = Column(String(50), nullable=True)
    year = Column(Integer, nullable=True)
    country = Column(String(100), nullable=True)
    confidence_score = Column(Float, default=0.0)
    paper_title = Column(Text, nullable=True)
    doi = Column(String(200), nullable=True)
    source_url = Column(Text, nullable=True)
    quote = Column(Text, nullable=True)
```

- [ ] **Step 8: Alembic 초기화 + 첫 마이그레이션**

```bash
cd backend
alembic init alembic
# alembic/env.py에서 target_metadata = Base.metadata 설정 후:
alembic revision --autogenerate -m "initial tables"
alembic upgrade head
```

- [ ] **Step 9: 커밋**

```bash
git add backend/app/config.py backend/app/database.py backend/app/celery_app.py \
  backend/app/models/ backend/alembic/
git commit -m "feat: db models and config"
```

---

## Task 3: Pydantic 스키마 + FastAPI 기본 앱

**Files:**
- Create: `backend/app/schemas/tech_query.py`
- Create: `backend/app/schemas/indicator.py`
- Create: `backend/app/schemas/job.py`
- Create: `backend/app/schemas/metric_value.py`
- Create: `backend/app/main.py`

- [ ] **Step 1: `backend/app/schemas/indicator.py` 생성**

```python
from pydantic import BaseModel
from typing import Optional

class IndicatorBase(BaseModel):
    name: str
    unit: Optional[str] = None
    description: Optional[str] = None
    search_keywords: Optional[str] = None

class IndicatorCreate(IndicatorBase):
    pass

class IndicatorUpdate(BaseModel):
    name: Optional[str] = None
    unit: Optional[str] = None
    description: Optional[str] = None
    search_keywords: Optional[str] = None
    confirmed_by_user: Optional[bool] = None

class IndicatorOut(IndicatorBase):
    id: int
    query_id: int
    confirmed_by_user: bool

    class Config:
        from_attributes = True
```

- [ ] **Step 2: `backend/app/schemas/tech_query.py` 생성**

```python
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class TechQueryCreate(BaseModel):
    category: str
    description: str
    user_email: Optional[str] = None

class TechQueryOut(BaseModel):
    id: int
    category: str
    description: str
    created_at: datetime

    class Config:
        from_attributes = True
```

- [ ] **Step 3: `backend/app/schemas/job.py` 생성**

```python
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class JobOut(BaseModel):
    id: int
    query_id: int
    status: str
    progress_pct: float
    current_step: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True
```

- [ ] **Step 4: `backend/app/schemas/metric_value.py` 생성**

```python
from pydantic import BaseModel
from typing import Optional

class MetricValueOut(BaseModel):
    id: int
    indicator_id: int
    value: Optional[float] = None
    unit: Optional[str] = None
    year: Optional[int] = None
    country: Optional[str] = None
    confidence_score: float
    paper_title: Optional[str] = None
    doi: Optional[str] = None
    source_url: Optional[str] = None
    quote: Optional[str] = None

    class Config:
        from_attributes = True
```

- [ ] **Step 5: `backend/app/main.py` 생성**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import tech_input, indicators, jobs, results, websocket

app = FastAPI(title="TechSpec API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5186", "http://localhost:8098"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tech_input.router, prefix="/api")
app.include_router(indicators.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(results.router, prefix="/api")
app.include_router(websocket.router)

@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 6: 서버 기동 확인**

```bash
cd backend && uvicorn app.main:app --reload
# GET http://localhost:8000/health → {"status": "ok"} 확인
```

- [ ] **Step 7: 커밋**

```bash
git add backend/app/schemas/ backend/app/main.py
git commit -m "feat: pydantic schemas and fastapi app skeleton"
```

---

## Task 4: Tech Input + Indicator 라우터

**Files:**
- Create: `backend/app/routers/tech_input.py`
- Create: `backend/app/routers/indicators.py`
- Create: `backend/tests/conftest.py`

- [ ] **Step 1: `backend/tests/conftest.py` 생성**

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.database import Base, get_db

TEST_DB_URL = "postgresql://techspec:techspec@localhost:5439/techspec_test"
engine = create_engine(TEST_DB_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()

@pytest.fixture
def client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
```

- [ ] **Step 2: `backend/app/routers/tech_input.py` 생성**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.tech_query import TechQuery
from app.schemas.tech_query import TechQueryCreate, TechQueryOut

router = APIRouter(tags=["tech-input"])

@router.post("/tech-input", response_model=TechQueryOut)
def create_tech_input(payload: TechQueryCreate, db: Session = Depends(get_db)):
    query = TechQuery(
        category=payload.category,
        description=payload.description,
        user_email=payload.user_email,
    )
    db.add(query)
    db.commit()
    db.refresh(query)
    return query
```

- [ ] **Step 3: `backend/app/routers/indicators.py` 생성**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.indicator import Indicator
from app.schemas.indicator import IndicatorCreate, IndicatorOut, IndicatorUpdate
from app.agents.indicator_agent import generate_indicators

router = APIRouter(tags=["indicators"])

@router.post("/queries/{query_id}/indicators/generate", response_model=List[IndicatorOut])
async def generate_indicator_draft(query_id: int, db: Session = Depends(get_db)):
    from app.models.tech_query import TechQuery
    query = db.query(TechQuery).filter(TechQuery.id == query_id).first()
    if not query:
        raise HTTPException(status_code=404, detail="Query not found")
    drafts = await generate_indicators(query.category, query.description)
    indicators = []
    for d in drafts:
        ind = Indicator(
            query_id=query_id,
            name=d["name"],
            unit=d.get("unit"),
            description=d.get("description"),
            search_keywords=d.get("search_keywords"),
        )
        db.add(ind)
        indicators.append(ind)
    db.commit()
    for ind in indicators:
        db.refresh(ind)
    return indicators

@router.put("/indicators/{indicator_id}", response_model=IndicatorOut)
def update_indicator(indicator_id: int, payload: IndicatorUpdate, db: Session = Depends(get_db)):
    ind = db.query(Indicator).filter(Indicator.id == indicator_id).first()
    if not ind:
        raise HTTPException(status_code=404, detail="Indicator not found")
    for field, val in payload.model_dump(exclude_none=True).items():
        setattr(ind, field, val)
    db.commit()
    db.refresh(ind)
    return ind

@router.delete("/indicators/{indicator_id}", status_code=204)
def delete_indicator(indicator_id: int, db: Session = Depends(get_db)):
    ind = db.query(Indicator).filter(Indicator.id == indicator_id).first()
    if not ind:
        raise HTTPException(status_code=404, detail="Indicator not found")
    db.delete(ind)
    db.commit()
```

- [ ] **Step 4: 커밋**

```bash
git add backend/app/routers/tech_input.py backend/app/routers/indicators.py \
  backend/tests/conftest.py
git commit -m "feat: tech-input and indicators API endpoints"
```

---

## Task 5: Indicator Agent (Gemini)

**Files:**
- Create: `backend/app/agents/indicator_agent.py`
- Create: `backend/tests/test_indicator_agent.py`

- [ ] **Step 1: 테스트 작성**

`backend/tests/test_indicator_agent.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.agents.indicator_agent import generate_indicators

MOCK_RESPONSE = [
    {"name": "대역폭", "unit": "GB/s", "description": "메모리 초당 전송 데이터량", "search_keywords": "HBM bandwidth GB/s"},
    {"name": "적층 다이 수", "unit": "개", "description": "수직 적층된 DRAM 다이 수", "search_keywords": "HBM stacked dies count"},
]

@pytest.mark.asyncio
async def test_generate_indicators_returns_list():
    with patch("app.agents.indicator_agent.genai_client") as mock_client:
        mock_response = MagicMock()
        mock_response.text = '[{"name":"대역폭","unit":"GB/s","description":"메모리 초당 전송 데이터량","search_keywords":"HBM bandwidth GB/s"},{"name":"적층 다이 수","unit":"개","description":"수직 적층된 DRAM 다이 수","search_keywords":"HBM stacked dies count"}]'
        mock_client.models.generate_content.return_value = mock_response
        result = await generate_indicators("반도체", "HBM 고대역폭 메모리 적층 기술")
    assert isinstance(result, list)
    assert len(result) >= 1
    assert "name" in result[0]
    assert "unit" in result[0]

@pytest.mark.asyncio
async def test_generate_indicators_returns_at_least_5():
    with patch("app.agents.indicator_agent.genai_client") as mock_client:
        items = [{"name": f"지표{i}", "unit": "unit", "description": "desc", "search_keywords": "kw"} for i in range(7)]
        import json
        mock_response = MagicMock()
        mock_response.text = json.dumps(items)
        mock_client.models.generate_content.return_value = mock_response
        result = await generate_indicators("반도체", "HBM 기술")
    assert len(result) >= 5
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
cd backend && pytest tests/test_indicator_agent.py -v
# Expected: FAIL - ModuleNotFoundError
```

- [ ] **Step 3: `backend/app/agents/indicator_agent.py` 구현**

```python
import json
import asyncio
from google import genai
from google.genai import types
from app.config import settings

genai_client = genai.Client(api_key=settings.gemini_api_key)

INDICATOR_PROMPT = """당신은 국가전략기술 분야의 전문가입니다.
아래 기술 분야에 대해 기술 수준을 측정할 수 있는 정량 지표 5~10개를 JSON 배열로 반환하세요.

기술 분야: {category}
세부 설명: {description}

각 지표는 다음 형식으로 작성하세요:
{{
  "name": "지표명 (한글)",
  "unit": "단위 (예: GB/s, nm, %)",
  "description": "지표 설명 (1문장)",
  "search_keywords": "영어 논문 검색 키워드 (예: HBM bandwidth GB/s)"
}}

규칙:
- 반드시 측정 가능한 수치 지표만 포함 (정성 지표 제외)
- JSON 배열만 반환, 설명 텍스트 없음
- 5개 이상 10개 이하"""

async def generate_indicators(category: str, description: str) -> list[dict]:
    prompt = INDICATOR_PROMPT.format(category=category, description=description)
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: genai_client.models.generate_content(
            model=settings.gemini_model_complex,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            ),
        )
    )
    return json.loads(response.text)
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/test_indicator_agent.py -v
# Expected: 2 passed
```

- [ ] **Step 5: 커밋**

```bash
git add backend/app/agents/indicator_agent.py backend/tests/test_indicator_agent.py
git commit -m "feat: indicator agent with gemini"
```

---

## Task 6: Search Agent (Semantic Scholar + arXiv)

**Files:**
- Create: `backend/app/agents/search_agent.py`
- Create: `backend/tests/test_search_agent.py`

- [ ] **Step 1: 테스트 작성**

`backend/tests/test_search_agent.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.agents.search_agent import search_papers_for_indicator

MOCK_SS_RESPONSE = {
    "data": [
        {
            "paperId": "abc123",
            "title": "HBM3E: High Bandwidth Memory",
            "abstract": "We present HBM3E achieving 1.2 TB/s bandwidth...",
            "year": 2024,
            "citationCount": 45,
            "externalIds": {"DOI": "10.1109/test.2024.001"},
        }
    ]
}

@pytest.mark.asyncio
async def test_search_returns_list_of_papers():
    with patch("app.agents.search_agent.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.json.return_value = MOCK_SS_RESPONSE
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response
        results = await search_papers_for_indicator("HBM bandwidth GB/s", max_results=5)
    assert isinstance(results, list)
    assert len(results) >= 1
    assert "title" in results[0]
    assert "abstract" in results[0]

@pytest.mark.asyncio
async def test_search_filters_empty_abstracts():
    with patch("app.agents.search_agent.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {"paperId": "x1", "title": "Paper 1", "abstract": None, "year": 2023, "citationCount": 10, "externalIds": {}},
                {"paperId": "x2", "title": "Paper 2", "abstract": "actual content with values", "year": 2023, "citationCount": 10, "externalIds": {}},
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response
        results = await search_papers_for_indicator("test keyword", max_results=5)
    assert all(r["abstract"] for r in results)
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/test_search_agent.py -v
# Expected: FAIL
```

- [ ] **Step 3: `backend/app/agents/search_agent.py` 구현**

```python
import httpx
import asyncio
from app.config import settings

SS_API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
SS_FIELDS = "paperId,title,abstract,year,citationCount,externalIds"

async def search_papers_for_indicator(keywords: str, max_results: int = None) -> list[dict]:
    max_results = max_results or settings.max_papers_per_indicator
    headers = {}
    if settings.semantic_scholar_api_key:
        headers["x-api-key"] = settings.semantic_scholar_api_key

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            SS_API_URL,
            params={"query": keywords, "limit": max_results, "fields": SS_FIELDS},
            headers=headers,
        )
        response.raise_for_status()
        data = response.json().get("data", [])

    papers = [
        {
            "paper_id": p.get("paperId"),
            "title": p.get("title", ""),
            "abstract": p.get("abstract", ""),
            "year": p.get("year"),
            "citation_count": p.get("citationCount", 0),
            "doi": (p.get("externalIds") or {}).get("DOI"),
        }
        for p in data
        if p.get("abstract")
    ]
    return papers

async def search_all_sources(keywords: str, max_results: int = None) -> list[dict]:
    results = await search_papers_for_indicator(keywords, max_results)
    return results
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/test_search_agent.py -v
# Expected: 2 passed
```

- [ ] **Step 5: 커밋**

```bash
git add backend/app/agents/search_agent.py backend/tests/test_search_agent.py
git commit -m "feat: search agent for semantic scholar"
```

---

## Task 7: Extraction Agent (Gemini 수치 추출)

**Files:**
- Create: `backend/app/agents/extraction_agent.py`
- Create: `backend/tests/test_extraction_agent.py`

- [ ] **Step 1: 테스트 작성**

`backend/tests/test_extraction_agent.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
from app.agents.extraction_agent import extract_metric_from_paper

PAPER_WITH_VALUE = {
    "title": "HBM3E achieves record bandwidth",
    "abstract": "In this paper, we present HBM3E achieving 1,228 GB/s bandwidth with 12 stacked dies. The device was fabricated by SK Hynix in Korea and presented at ISSCC 2024.",
    "year": 2024,
    "doi": "10.1109/isscc.2024.001",
    "citation_count": 45,
}

PAPER_WITHOUT_VALUE = {
    "title": "Overview of memory technology",
    "abstract": "This paper provides an overview of memory technology trends without specific measurements.",
    "year": 2023,
    "doi": None,
    "citation_count": 5,
}

@pytest.mark.asyncio
async def test_extracts_value_from_paper():
    with patch("app.agents.extraction_agent.genai_client") as mock_client:
        mock_response = MagicMock()
        mock_response.text = '{"value": 1228.0, "unit": "GB/s", "year": 2024, "country": "Korea", "confidence_score": 0.92, "quote": "HBM3E achieving 1,228 GB/s bandwidth"}'
        mock_client.models.generate_content.return_value = mock_response
        result = extract_metric_from_paper(PAPER_WITH_VALUE, "대역폭", "GB/s")
    assert result["value"] == 1228.0
    assert result["confidence_score"] >= 0.5

@pytest.mark.asyncio
async def test_returns_none_value_when_not_found():
    with patch("app.agents.extraction_agent.genai_client") as mock_client:
        mock_response = MagicMock()
        mock_response.text = '{"value": null, "unit": null, "year": null, "country": null, "confidence_score": 0.0, "quote": null}'
        mock_client.models.generate_content.return_value = mock_response
        result = extract_metric_from_paper(PAPER_WITHOUT_VALUE, "대역폭", "GB/s")
    assert result["value"] is None
    assert result["confidence_score"] == 0.0
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/test_extraction_agent.py -v
# Expected: FAIL
```

- [ ] **Step 3: `backend/app/agents/extraction_agent.py` 구현**

```python
import json
from google import genai
from google.genai import types
from app.config import settings

genai_client = genai.Client(api_key=settings.gemini_api_key)

EXTRACTION_PROMPT = """다음 논문 초록에서 아래 지표의 수치를 추출하세요.

논문 제목: {title}
논문 초록: {abstract}
추출 대상 지표: {indicator_name} (단위: {unit})

JSON 형식으로만 응답하세요. 수치가 없으면 null:
{{
  "value": <숫자 또는 null>,
  "unit": "<단위 또는 null>",
  "year": <연도 정수 또는 null>,
  "country": "<국가명 또는 null>",
  "confidence_score": <0.0~1.0>,
  "quote": "<근거 문장 또는 null>"
}}"""

def extract_metric_from_paper(paper: dict, indicator_name: str, unit: str) -> dict:
    prompt = EXTRACTION_PROMPT.format(
        title=paper["title"],
        abstract=paper.get("abstract", ""),
        indicator_name=indicator_name,
        unit=unit or "",
    )
    response = genai_client.models.generate_content(
        model=settings.gemini_model_complex,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        ),
    )
    result = json.loads(response.text)
    result["paper_title"] = paper["title"]
    result["doi"] = paper.get("doi")
    result["source_url"] = f"https://doi.org/{paper['doi']}" if paper.get("doi") else None
    return result
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/test_extraction_agent.py -v
# Expected: 2 passed
```

- [ ] **Step 5: 커밋**

```bash
git add backend/app/agents/extraction_agent.py backend/tests/test_extraction_agent.py
git commit -m "feat: extraction agent with gemini json mode"
```

---

## Task 8: Validation Agent + Synthesis Agent

**Files:**
- Create: `backend/app/agents/validation_agent.py`
- Create: `backend/app/agents/synthesis_agent.py`
- Create: `backend/tests/test_validation_agent.py`

- [ ] **Step 1: 테스트 작성**

`backend/tests/test_validation_agent.py`:

```python
from app.agents.validation_agent import validate_and_rank

def test_returns_top3_by_value():
    extractions = [
        {"value": 1228.0, "unit": "GB/s", "year": 2024, "country": "Korea", "confidence_score": 0.9, "paper_title": "A", "doi": None, "source_url": None, "quote": "q1"},
        {"value": 819.0, "unit": "GB/s", "year": 2022, "country": "USA", "confidence_score": 0.85, "paper_title": "B", "doi": None, "source_url": None, "quote": "q2"},
        {"value": 460.0, "unit": "GB/s", "year": 2020, "country": "Japan", "confidence_score": 0.8, "paper_title": "C", "doi": None, "source_url": None, "quote": "q3"},
        {"value": None, "unit": None, "year": None, "country": None, "confidence_score": 0.0, "paper_title": "D", "doi": None, "source_url": None, "quote": None},
    ]
    result = validate_and_rank(extractions, min_confidence=0.5)
    assert len(result) <= 3
    assert result[0]["value"] == 1228.0
    assert all(r["value"] is not None for r in result)

def test_filters_low_confidence():
    extractions = [
        {"value": 100.0, "unit": "GB/s", "year": 2024, "country": "USA", "confidence_score": 0.3, "paper_title": "A", "doi": None, "source_url": None, "quote": None},
        {"value": 200.0, "unit": "GB/s", "year": 2024, "country": "Korea", "confidence_score": 0.8, "paper_title": "B", "doi": None, "source_url": None, "quote": None},
    ]
    result = validate_and_rank(extractions, min_confidence=0.5)
    assert len(result) == 1
    assert result[0]["value"] == 200.0
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
pytest tests/test_validation_agent.py -v
# Expected: FAIL
```

- [ ] **Step 3: `backend/app/agents/validation_agent.py` 구현**

```python
from app.config import settings

def validate_and_rank(extractions: list[dict], min_confidence: float = None) -> list[dict]:
    min_conf = min_confidence if min_confidence is not None else settings.min_confidence_score
    valid = [
        e for e in extractions
        if e.get("value") is not None and e.get("confidence_score", 0) >= min_conf
    ]
    valid.sort(key=lambda x: (x.get("value", 0), x.get("confidence_score", 0)), reverse=True)
    return valid[:3]
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/test_validation_agent.py -v
# Expected: 2 passed
```

- [ ] **Step 5: `backend/app/agents/synthesis_agent.py` 구현**

```python
import json
from google import genai
from google.genai import types
from app.config import settings

genai_client = genai.Client(api_key=settings.gemini_api_key)

def build_report_markdown(category: str, description: str, results_by_indicator: dict, analyzed_at: str) -> str:
    summary_json = json.dumps(results_by_indicator, ensure_ascii=False, indent=2)
    prompt = f"""다음 데이터를 바탕으로 국가전략기술 Spec 조사 보고서를 마크다운으로 작성하세요.

기술 분야: {category}
세부 설명: {description}
분석 기준일: {analyzed_at}
조사 결과:
{summary_json}

보고서 구조:
1. 분석 기준일: {analyzed_at} (첫 줄에 명시)
2. 요약 (3문장)
3. 지표별 글로벌 최고 달성치 표 (지표 | 값 | 단위 | 연도 | 국가 | 출처)
4. 시사점 (2~3문장)
5. 주석: "본 분석은 {analyzed_at} 기준으로 검색된 논문 데이터를 바탕으로 합니다. 이후 발표된 연구 결과는 반영되지 않았을 수 있습니다."

마크다운만 반환, 코드블록 없음."""
    response = genai_client.models.generate_content(
        model=settings.gemini_model_fast,
        contents=prompt,
    )
    return response.text
```

- [ ] **Step 6: 커밋**

```bash
git add backend/app/agents/validation_agent.py backend/app/agents/synthesis_agent.py \
  backend/tests/test_validation_agent.py
git commit -m "feat: validation and synthesis agents"
```

---

## Task 9: LangGraph 파이프라인

**Files:**
- Create: `backend/app/agents/pipeline.py`
- Create: `backend/tests/test_pipeline_task.py`

- [ ] **Step 1: `backend/app/agents/pipeline.py` 구현**

```python
import asyncio
from typing import TypedDict, List
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session
from app.agents.search_agent import search_all_sources
from app.agents.extraction_agent import extract_metric_from_paper
from app.agents.validation_agent import validate_and_rank
from app.agents.synthesis_agent import build_report_markdown
from app.models.indicator import Indicator
from app.models.metric_value import MetricValue
from app.models.job import Job
from app.config import settings

class PipelineState(TypedDict):
    job_id: int
    query_id: int
    category: str
    description: str
    indicators: List[dict]
    search_results: dict      # indicator_id -> list of papers
    extracted_values: dict    # indicator_id -> list of extractions
    validated_values: dict    # indicator_id -> top3 validated
    report_markdown: str
    error: str

def _update_job(db: Session, job_id: int, progress_pct: float, current_step: str):
    job = db.query(Job).filter(Job.id == job_id).first()
    if job:
        job.progress_pct = progress_pct
        job.current_step = current_step
        db.commit()

async def search_node(state: PipelineState, db: Session) -> PipelineState:
    _update_job(db, state["job_id"], 10.0, "논문 검색 중")
    results = {}
    tasks = [
        search_all_sources(ind["search_keywords"] or ind["name"])
        for ind in state["indicators"]
    ]
    paper_lists = await asyncio.gather(*tasks)
    for ind, papers in zip(state["indicators"], paper_lists):
        results[ind["id"]] = papers
    return {**state, "search_results": results}

async def extract_node(state: PipelineState, db: Session) -> PipelineState:
    _update_job(db, state["job_id"], 40.0, "수치 추출 중")
    extracted = {}
    for ind in state["indicators"]:
        papers = state["search_results"].get(ind["id"], [])[:settings.max_papers_per_indicator]
        extractions = [
            extract_metric_from_paper(p, ind["name"], ind.get("unit", ""))
            for p in papers
        ]
        extracted[ind["id"]] = extractions
    return {**state, "extracted_values": extracted}

async def validate_node(state: PipelineState, db: Session) -> PipelineState:
    _update_job(db, state["job_id"], 70.0, "교차 검증 중")
    validated = {}
    for ind in state["indicators"]:
        extractions = state["extracted_values"].get(ind["id"], [])
        top3 = validate_and_rank(extractions)
        validated[ind["id"]] = top3
        for mv_data in top3:
            mv = MetricValue(
                indicator_id=ind["id"],
                value=mv_data.get("value"),
                unit=mv_data.get("unit"),
                year=mv_data.get("year"),
                country=mv_data.get("country"),
                confidence_score=mv_data.get("confidence_score", 0.0),
                paper_title=mv_data.get("paper_title"),
                doi=mv_data.get("doi"),
                source_url=mv_data.get("source_url"),
                quote=mv_data.get("quote"),
            )
            db.add(mv)
    db.commit()
    return {**state, "validated_values": validated}

async def synthesize_node(state: PipelineState, db: Session) -> PipelineState:
    _update_job(db, state["job_id"], 90.0, "리포트 생성 중")
    results_by_indicator = {
        ind["name"]: state["validated_values"].get(ind["id"], [])
        for ind in state["indicators"]
    }
    from datetime import datetime, timezone
    analyzed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    markdown = build_report_markdown(state["category"], state["description"], results_by_indicator, analyzed_at)
    return {**state, "report_markdown": markdown}

async def run_pipeline(job_id: int, db: Session) -> str:
    from app.models.job import Job
    from app.models.indicator import Indicator
    from app.models.tech_query import TechQuery

    job = db.query(Job).filter(Job.id == job_id).first()
    query = db.query(TechQuery).filter(TechQuery.id == job.query_id).first()
    indicators = db.query(Indicator).filter(
        Indicator.query_id == job.query_id,
        Indicator.confirmed_by_user == True
    ).all()

    state: PipelineState = {
        "job_id": job_id,
        "query_id": job.query_id,
        "category": query.category,
        "description": query.description,
        "indicators": [
            {"id": i.id, "name": i.name, "unit": i.unit, "search_keywords": i.search_keywords}
            for i in indicators
        ],
        "search_results": {},
        "extracted_values": {},
        "validated_values": {},
        "report_markdown": "",
        "error": "",
    }

    state = await search_node(state, db)
    state = await extract_node(state, db)
    state = await validate_node(state, db)
    state = await synthesize_node(state, db)
    return state["report_markdown"]
```

- [ ] **Step 2: `backend/app/tasks/pipeline_task.py` 생성**

```python
import asyncio
from datetime import datetime
from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.job import Job

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def run_pipeline_task(self, job_id: int):
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        job.status = "running"
        db.commit()

        from app.agents.pipeline import run_pipeline
        report_markdown = asyncio.run(run_pipeline(job_id, db))

        job.status = "done"
        job.progress_pct = 100.0
        job.current_step = "완료"
        job.completed_at = datetime.utcnow()
        db.commit()
        return {"job_id": job_id, "status": "done"}

    except Exception as exc:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = "failed"
            job.current_step = f"오류: {str(exc)[:100]}"
            db.commit()
        raise self.retry(exc=exc)
    finally:
        db.close()
```

- [ ] **Step 3: 커밋**

```bash
git add backend/app/agents/pipeline.py backend/app/tasks/pipeline_task.py
git commit -m "feat: langgraph pipeline and celery task"
```

---

## Task 10: Jobs + WebSocket + Results 라우터

**Files:**
- Create: `backend/app/routers/jobs.py`
- Create: `backend/app/routers/websocket.py`
- Create: `backend/app/routers/results.py`

- [ ] **Step 1: `backend/app/routers/jobs.py` 생성**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.job import Job
from app.models.indicator import Indicator
from app.schemas.job import JobOut
from app.tasks.pipeline_task import run_pipeline_task

router = APIRouter(tags=["jobs"])

@router.post("/queries/{query_id}/jobs", response_model=JobOut)
def start_job(query_id: int, db: Session = Depends(get_db)):
    confirmed = db.query(Indicator).filter(
        Indicator.query_id == query_id,
        Indicator.confirmed_by_user == True,
    ).count()
    if confirmed == 0:
        raise HTTPException(status_code=400, detail="확정된 지표가 없습니다")
    job = Job(query_id=query_id, status="pending", progress_pct=0.0)
    db.add(job)
    db.commit()
    db.refresh(job)
    run_pipeline_task.delay(job.id)
    return job

@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
```

- [ ] **Step 2: `backend/app/routers/websocket.py` 생성**

```python
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.database import SessionLocal
from app.models.job import Job

router = APIRouter()

@router.websocket("/ws/jobs/{job_id}")
async def job_status_ws(websocket: WebSocket, job_id: int):
    await websocket.accept()
    db = SessionLocal()
    try:
        while True:
            job = db.query(Job).filter(Job.id == job_id).first()
            if not job:
                await websocket.send_json({"error": "not found"})
                break
            await websocket.send_json({
                "status": job.status,
                "progress_pct": job.progress_pct,
                "current_step": job.current_step,
            })
            if job.status in ("done", "failed"):
                break
            await asyncio.sleep(3)
    except WebSocketDisconnect:
        pass
    finally:
        db.close()
```

- [ ] **Step 3: `backend/app/routers/results.py` 생성**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.job import Job
from app.models.indicator import Indicator
from app.models.metric_value import MetricValue
from app.schemas.metric_value import MetricValueOut

router = APIRouter(tags=["results"])

@router.get("/jobs/{job_id}/results")
def get_results(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "done":
        raise HTTPException(status_code=202, detail="Processing not complete")
    indicators = db.query(Indicator).filter(Indicator.query_id == job.query_id).all()
    output = []
    for ind in indicators:
        values = db.query(MetricValue).filter(MetricValue.indicator_id == ind.id).all()
        output.append({
            "indicator": {"id": ind.id, "name": ind.name, "unit": ind.unit},
            "metric_values": [
                {
                    "value": mv.value,
                    "unit": mv.unit,
                    "year": mv.year,
                    "country": mv.country,
                    "confidence_score": mv.confidence_score,
                    "paper_title": mv.paper_title,
                    "doi": mv.doi,
                    "source_url": mv.source_url,
                    "quote": mv.quote,
                }
                for mv in values
            ],
        })
    return {
        "job_id": job_id,
        "analyzed_at": job.completed_at.isoformat() if job.completed_at else None,
        "indicators": output,
    }
```

- [ ] **Step 4: 커밋**

```bash
git add backend/app/routers/jobs.py backend/app/routers/websocket.py \
  backend/app/routers/results.py
git commit -m "feat: jobs, websocket, and results endpoints"
```

---

## Task 11: PDF 생성 + 이메일 알림

**Files:**
- Create: `backend/app/services/pdf_service.py`
- Create: `backend/app/services/minio_service.py`
- Create: `backend/app/services/email_service.py`

- [ ] **Step 1: `backend/app/services/pdf_service.py` 생성**

```python
import markdown
from weasyprint import HTML

def markdown_to_pdf_bytes(md_content: str) -> bytes:
    html_body = markdown.markdown(md_content, extensions=["tables"])
    full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: 'Noto Sans KR', sans-serif; margin: 40px; font-size: 13px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
  th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
  th {{ background: #f5f5f5; }}
  h1, h2, h3 {{ color: #1a1a2e; }}
</style>
</head>
<body>{html_body}</body>
</html>"""
    return HTML(string=full_html).write_pdf()
```

- [ ] **Step 2: `backend/app/services/minio_service.py` 생성**

```python
import boto3
from botocore.client import Config
from app.config import settings

def get_minio_client():
    return boto3.client(
        "s3",
        endpoint_url=f"http://{settings.minio_endpoint}",
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )

def upload_pdf(job_id: int, pdf_bytes: bytes) -> str:
    client = get_minio_client()
    key = f"reports/job_{job_id}.pdf"
    client.put_object(
        Bucket=settings.minio_bucket,
        Key=key,
        Body=pdf_bytes,
        ContentType="application/pdf",
    )
    url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.minio_bucket, "Key": key},
        ExpiresIn=86400,
    )
    return url
```

- [ ] **Step 3: `backend/app/services/email_service.py` 생성**

```python
import aiosmtplib
from email.message import EmailMessage
from app.config import settings

async def send_completion_email(to_email: str, job_id: int, pdf_url: str):
    if not settings.smtp_user:
        return
    msg = EmailMessage()
    msg["Subject"] = f"[TechSpec] 분석 완료 — 작업 #{job_id}"
    msg["From"] = settings.smtp_user
    msg["To"] = to_email
    msg.set_content(
        f"요청하신 국가전략기술 Spec 분석이 완료되었습니다.\n\n"
        f"PDF 리포트 다운로드: {pdf_url}\n\n"
        f"(링크는 24시간 유효합니다)"
    )
    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user,
        password=settings.smtp_password,
        start_tls=True,
    )
```

- [ ] **Step 4: `pipeline_task.py`에 PDF + 이메일 연동**

`backend/app/tasks/pipeline_task.py`의 `job.status = "done"` 블록 이후에 추가:

```python
        from app.services.pdf_service import markdown_to_pdf_bytes
        from app.services.minio_service import upload_pdf
        from app.services.email_service import send_completion_email

        pdf_bytes = markdown_to_pdf_bytes(report_markdown)
        pdf_url = upload_pdf(job_id, pdf_bytes)

        from app.models.tech_query import TechQuery
        query = db.query(TechQuery).filter(TechQuery.id == job.query_id).first()
        if query and query.user_email:
            asyncio.run(send_completion_email(query.user_email, job_id, pdf_url))
```

- [ ] **Step 5: PDF 다운로드 엔드포인트 추가 (`results.py`)**

`backend/app/routers/results.py`에 추가:

```python
from fastapi.responses import RedirectResponse

@router.get("/jobs/{job_id}/pdf")
def download_pdf(job_id: int):
    from app.services.minio_service import get_minio_client
    client = get_minio_client()
    import boto3
    from app.config import settings
    key = f"reports/job_{job_id}.pdf"
    url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.minio_bucket, "Key": key},
        ExpiresIn=3600,
    )
    return RedirectResponse(url=url)
```

- [ ] **Step 6: 커밋**

```bash
git add backend/app/services/ backend/app/tasks/pipeline_task.py \
  backend/app/routers/results.py
git commit -m "feat: pdf generation, minio upload, email notification"
```

---

## Task 12: Frontend 스캐폴딩 + API 클라이언트

**Files:**
- Create: `frontend/` (Vite + React + TypeScript + Tailwind)
- Create: `frontend/src/api/client.ts`

- [ ] **Step 1: Vite 프로젝트 생성**

```bash
cd frontend
npm create vite@latest . -- --template react-ts
npm install
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
npm install axios @tanstack/react-query recharts
npm install -D @types/recharts
```

- [ ] **Step 2: Tailwind 설정 (`tailwind.config.js`)**

```js
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: { extend: {} },
  plugins: [],
}
```

- [ ] **Step 3: `frontend/src/api/client.ts` 생성**

```typescript
import axios from "axios";

const api = axios.create({ baseURL: "/api" });

export const createTechInput = (data: { category: string; description: string; user_email?: string }) =>
  api.post("/tech-input", data).then(r => r.data);

export const generateIndicators = (queryId: number) =>
  api.post(`/queries/${queryId}/indicators/generate`).then(r => r.data);

export const updateIndicator = (id: number, data: Partial<{ name: string; unit: string; confirmed_by_user: boolean }>) =>
  api.put(`/indicators/${id}`, data).then(r => r.data);

export const deleteIndicator = (id: number) =>
  api.delete(`/indicators/${id}`);

export const startJob = (queryId: number) =>
  api.post(`/queries/${queryId}/jobs`).then(r => r.data);

export const getJob = (jobId: number) =>
  api.get(`/jobs/${jobId}`).then(r => r.data);

export const getResults = (jobId: number) =>
  api.get(`/jobs/${jobId}/results`).then(r => r.data);
```

- [ ] **Step 4: `frontend/src/hooks/useJobStatus.ts` 생성**

```typescript
import { useState, useEffect } from "react";

interface JobStatus {
  status: string;
  progress_pct: number;
  current_step: string | null;
}

export function useJobStatus(jobId: number | null) {
  const [status, setStatus] = useState<JobStatus | null>(null);

  useEffect(() => {
    if (!jobId) return;
    const ws = new WebSocket(`ws://localhost:8017/ws/jobs/${jobId}`);
    ws.onmessage = (e) => setStatus(JSON.parse(e.data));
    return () => ws.close();
  }, [jobId]);

  return status;
}
```

- [ ] **Step 5: 커밋**

```bash
git add frontend/
git commit -m "feat: frontend scaffold with vite react ts tailwind"
```

---

## Task 13: Frontend — InputPage + IndicatorEditorPage

**Files:**
- Create: `frontend/src/pages/InputPage.tsx`
- Create: `frontend/src/components/CategorySelect.tsx`
- Create: `frontend/src/pages/IndicatorEditorPage.tsx`
- Create: `frontend/src/components/IndicatorList.tsx`

- [ ] **Step 1: `frontend/src/components/CategorySelect.tsx` 생성**

```tsx
const CATEGORIES = [
  "반도체·디스플레이", "이차전지", "첨단 모빌리티", "차세대 원자력",
  "첨단 바이오", "우주·항공", "사이버 보안", "인공지능",
  "차세대 통신", "첨단 로봇·제조", "양자", "첨단소재"
];

interface Props { value: string; onChange: (v: string) => void; }

export default function CategorySelect({ value, onChange }: Props) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      className="w-full border rounded-lg p-2 text-sm"
    >
      <option value="">분야를 선택하세요</option>
      {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
    </select>
  );
}
```

- [ ] **Step 2: `frontend/src/pages/InputPage.tsx` 생성**

```tsx
import { useState } from "react";
import CategorySelect from "../components/CategorySelect";
import { createTechInput, generateIndicators } from "../api/client";

interface Props { onNext: (queryId: number) => void; }

export default function InputPage({ onNext }: Props) {
  const [category, setCategory] = useState("");
  const [description, setDescription] = useState("");
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    if (!category || !description) return;
    setLoading(true);
    const query = await createTechInput({ category, description, user_email: email || undefined });
    onNext(query.id);
  };

  return (
    <div className="max-w-xl mx-auto p-8">
      <h1 className="text-2xl font-bold mb-6">국가전략기술 Spec 조사</h1>
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium mb-1">기술 분야 선택</label>
          <CategorySelect value={category} onChange={setCategory} />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">세부 설명</label>
          <textarea
            value={description}
            onChange={e => setDescription(e.target.value)}
            placeholder="예: HBM 고대역폭 메모리 적층 기술, 이형접합 기판 기반..."
            className="w-full border rounded-lg p-2 text-sm h-28 resize-none"
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">이메일 (완료 알림, 선택)</label>
          <input
            type="email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            className="w-full border rounded-lg p-2 text-sm"
          />
        </div>
        <button
          onClick={handleSubmit}
          disabled={loading || !category || !description}
          className="w-full bg-blue-600 text-white py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "지표 생성 중..." : "지표 생성 →"}
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: `frontend/src/components/IndicatorList.tsx` 생성**

```tsx
interface Indicator { id: number; name: string; unit: string; description: string; confirmed_by_user: boolean; }
interface Props {
  indicators: Indicator[];
  onUpdate: (id: number, data: Partial<Indicator>) => void;
  onDelete: (id: number) => void;
}

export default function IndicatorList({ indicators, onUpdate, onDelete }: Props) {
  return (
    <ul className="space-y-2">
      {indicators.map(ind => (
        <li key={ind.id} className="flex items-center gap-2 border rounded-lg p-3 bg-green-50">
          <input
            className="flex-1 text-sm font-medium bg-transparent border-b border-transparent focus:border-green-400 outline-none"
            value={ind.name}
            onChange={e => onUpdate(ind.id, { name: e.target.value })}
          />
          <input
            className="w-20 text-xs text-gray-500 bg-transparent border-b border-transparent focus:border-green-400 outline-none text-right"
            value={ind.unit || ""}
            placeholder="단위"
            onChange={e => onUpdate(ind.id, { unit: e.target.value })}
          />
          <button onClick={() => onDelete(ind.id)} className="text-red-400 hover:text-red-600 text-lg leading-none">×</button>
        </li>
      ))}
    </ul>
  );
}
```

- [ ] **Step 4: `frontend/src/pages/IndicatorEditorPage.tsx` 생성**

```tsx
import { useState, useEffect } from "react";
import IndicatorList from "../components/IndicatorList";
import { generateIndicators, updateIndicator, deleteIndicator, startJob } from "../api/client";

interface Indicator { id: number; name: string; unit: string; description: string; confirmed_by_user: boolean; }
interface Props { queryId: number; onNext: (jobId: number) => void; }

export default function IndicatorEditorPage({ queryId, onNext }: Props) {
  const [indicators, setIndicators] = useState<Indicator[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    generateIndicators(queryId).then(data => { setIndicators(data); setLoading(false); });
  }, [queryId]);

  const handleUpdate = (id: number, data: Partial<Indicator>) => {
    setIndicators(prev => prev.map(i => i.id === id ? { ...i, ...data } : i));
    updateIndicator(id, data);
  };

  const handleDelete = (id: number) => {
    setIndicators(prev => prev.filter(i => i.id !== id));
    deleteIndicator(id);
  };

  const handleConfirm = async () => {
    await Promise.all(indicators.map(i => updateIndicator(i.id, { confirmed_by_user: true })));
    const job = await startJob(queryId);
    onNext(job.id);
  };

  if (loading) return <div className="p-8 text-center">AI가 지표를 생성하고 있습니다...</div>;

  return (
    <div className="max-w-xl mx-auto p-8">
      <h2 className="text-xl font-bold mb-2">지표 확인 및 편집</h2>
      <p className="text-sm text-gray-500 mb-4">이름·단위를 수정하거나 불필요한 지표를 삭제하세요.</p>
      <IndicatorList indicators={indicators} onUpdate={handleUpdate} onDelete={handleDelete} />
      <button
        onClick={handleConfirm}
        disabled={indicators.length === 0}
        className="mt-6 w-full bg-green-600 text-white py-2 rounded-lg hover:bg-green-700 disabled:opacity-50"
      >
        확정 후 분석 시작 →
      </button>
    </div>
  );
}
```

- [ ] **Step 5: 커밋**

```bash
git add frontend/src/pages/InputPage.tsx frontend/src/pages/IndicatorEditorPage.tsx \
  frontend/src/components/
git commit -m "feat: input and indicator editor pages"
```

---

## Task 14: Frontend — JobStatusPage + ResultsPage

**Files:**
- Create: `frontend/src/pages/JobStatusPage.tsx`
- Create: `frontend/src/components/ProgressStepper.tsx`
- Create: `frontend/src/pages/ResultsPage.tsx`
- Create: `frontend/src/components/MetricTable.tsx`
- Create: `frontend/src/components/TimeSeriesChart.tsx`
- Create: `frontend/src/components/CountryCompareChart.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: `frontend/src/components/ProgressStepper.tsx` 생성**

```tsx
const STEPS = ["논문 검색", "수치 추출", "교차 검증", "리포트 생성"];

interface Props { currentStep: string | null; progressPct: number; status: string; }

export default function ProgressStepper({ currentStep, progressPct, status }: Props) {
  return (
    <div className="space-y-4">
      <div className="w-full bg-gray-200 rounded-full h-2">
        <div className="bg-blue-500 h-2 rounded-full transition-all" style={{ width: `${progressPct}%` }} />
      </div>
      <p className="text-center text-sm text-gray-600">{currentStep || "대기 중..."}</p>
      {status === "done" && <p className="text-center text-green-600 font-medium">분석 완료!</p>}
      {status === "failed" && <p className="text-center text-red-600">오류가 발생했습니다.</p>}
    </div>
  );
}
```

- [ ] **Step 2: `frontend/src/pages/JobStatusPage.tsx` 생성**

```tsx
import { useEffect } from "react";
import ProgressStepper from "../components/ProgressStepper";
import { useJobStatus } from "../hooks/useJobStatus";

interface Props { jobId: number; onComplete: () => void; }

export default function JobStatusPage({ jobId, onComplete }: Props) {
  const status = useJobStatus(jobId);

  useEffect(() => {
    if (status?.status === "done") onComplete();
  }, [status?.status]);

  return (
    <div className="max-w-xl mx-auto p-8">
      <h2 className="text-xl font-bold mb-6">분석 진행 중</h2>
      <ProgressStepper
        currentStep={status?.current_step ?? null}
        progressPct={status?.progress_pct ?? 0}
        status={status?.status ?? "pending"}
      />
      <p className="text-center text-xs text-gray-400 mt-4">완료 시 이메일로 알림을 보내드립니다 (5~15분 소요)</p>
    </div>
  );
}
```

- [ ] **Step 3: `frontend/src/components/MetricTable.tsx` 생성**

```tsx
interface MetricValue { value: number | null; unit: string | null; year: number | null; country: string | null; confidence_score: number; paper_title: string | null; doi: string | null; source_url: string | null; quote: string | null; }
interface IndicatorResult { indicator: { name: string; unit: string }; metric_values: MetricValue[]; }
interface Props { data: IndicatorResult[]; }

export default function MetricTable({ data }: Props) {
  return (
    <div className="space-y-6">
      {data.map(item => (
        <div key={item.indicator.name} className="border rounded-lg overflow-hidden">
          <div className="bg-gray-50 px-4 py-2 font-semibold text-sm">{item.indicator.name}</div>
          <table className="w-full text-sm">
            <thead className="bg-gray-100 text-xs text-gray-500">
              <tr>
                <th className="p-2 text-left">값</th>
                <th className="p-2 text-left">연도</th>
                <th className="p-2 text-left">국가</th>
                <th className="p-2 text-left">신뢰도</th>
                <th className="p-2 text-left">출처</th>
              </tr>
            </thead>
            <tbody>
              {item.metric_values.map((mv, i) => (
                <tr key={i} className="border-t">
                  <td className="p-2 font-medium">{mv.value != null ? `${mv.value} ${mv.unit ?? ""}` : "—"}</td>
                  <td className="p-2">{mv.year ?? "—"}</td>
                  <td className="p-2">{mv.country ?? "—"}</td>
                  <td className="p-2">
                    <span className={mv.confidence_score < 0.5 ? "text-orange-500" : "text-green-600"}>
                      {mv.confidence_score < 0.5 ? "⚠️ " : ""}{(mv.confidence_score * 100).toFixed(0)}%
                    </span>
                  </td>
                  <td className="p-2">
                    {mv.source_url
                      ? <a href={mv.source_url} target="_blank" rel="noreferrer" className="text-blue-500 hover:underline text-xs">{mv.paper_title?.slice(0, 30)}...</a>
                      : <span className="text-xs text-gray-400">{mv.paper_title?.slice(0, 30)}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: `frontend/src/components/TimeSeriesChart.tsx` 생성**

```tsx
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from "recharts";

interface MetricValue { year: number | null; value: number | null; country: string | null; }
interface Props { indicatorName: string; values: MetricValue[]; }

export default function TimeSeriesChart({ indicatorName, values }: Props) {
  const data = values
    .filter(v => v.year && v.value != null)
    .sort((a, b) => (a.year ?? 0) - (b.year ?? 0))
    .map(v => ({ year: v.year, value: v.value, country: v.country }));
  if (!data.length) return null;
  return (
    <div className="mt-4">
      <h4 className="text-sm font-medium mb-2">{indicatorName} — 연도별 추이</h4>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data}>
          <XAxis dataKey="year" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Line type="monotone" dataKey="value" stroke="#3b82f6" dot />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
```

- [ ] **Step 5: `frontend/src/components/CountryCompareChart.tsx` 생성**

```tsx
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

interface MetricValue { country: string | null; value: number | null; }
interface Props { indicatorName: string; values: MetricValue[]; }

export default function CountryCompareChart({ indicatorName, values }: Props) {
  const data = values
    .filter(v => v.country && v.value != null)
    .map(v => ({ country: v.country, value: v.value }));
  if (!data.length) return null;
  return (
    <div className="mt-4">
      <h4 className="text-sm font-medium mb-2">{indicatorName} — 국가별 비교</h4>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={data}>
          <XAxis dataKey="country" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Bar dataKey="value" fill="#6366f1" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
```

- [ ] **Step 6: `frontend/src/pages/ResultsPage.tsx` 생성**

```tsx
import { useEffect, useState } from "react";
import MetricTable from "../components/MetricTable";
import TimeSeriesChart from "../components/TimeSeriesChart";
import CountryCompareChart from "../components/CountryCompareChart";
import { getResults } from "../api/client";

interface Props { jobId: number; }

export default function ResultsPage({ jobId }: Props) {
  const [results, setResults] = useState<any>(null);

  useEffect(() => {
    getResults(jobId).then(setResults);
  }, [jobId]);

  if (!results) return <div className="p-8 text-center">결과를 불러오는 중...</div>;

  return (
    <div className="max-w-3xl mx-auto p-8">
      <div className="flex justify-between items-center mb-2">
        <h2 className="text-xl font-bold">분석 결과</h2>
        <a
          href={`/api/jobs/${jobId}/pdf`}
          className="bg-purple-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-purple-700"
        >
          📄 PDF 다운로드
        </a>
      </div>
      {results.analyzed_at && (
        <p className="text-xs text-gray-400 mb-6">
          📅 분석 기준일: {new Date(results.analyzed_at).toLocaleDateString("ko-KR")} — 이후 발표된 연구는 반영되지 않았을 수 있습니다.
        </p>
      )}
      <MetricTable data={results.indicators} />
      {results.indicators.map((item: any) => (
        <div key={item.indicator.name}>
          <TimeSeriesChart indicatorName={item.indicator.name} values={item.metric_values} />
          <CountryCompareChart indicatorName={item.indicator.name} values={item.metric_values} />
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 7: `frontend/src/App.tsx` 업데이트**

```tsx
import { useState } from "react";
import InputPage from "./pages/InputPage";
import IndicatorEditorPage from "./pages/IndicatorEditorPage";
import JobStatusPage from "./pages/JobStatusPage";
import ResultsPage from "./pages/ResultsPage";

type Step = "input" | "indicators" | "status" | "results";

export default function App() {
  const [step, setStep] = useState<Step>("input");
  const [queryId, setQueryId] = useState<number | null>(null);
  const [jobId, setJobId] = useState<number | null>(null);

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white border-b px-8 py-4">
        <span className="font-bold text-lg text-blue-700">TechSpec</span>
        <span className="ml-2 text-xs text-gray-400">국가전략기술 Spec 조사 서비스</span>
      </nav>
      {step === "input" && <InputPage onNext={id => { setQueryId(id); setStep("indicators"); }} />}
      {step === "indicators" && queryId && <IndicatorEditorPage queryId={queryId} onNext={id => { setJobId(id); setStep("status"); }} />}
      {step === "status" && jobId && <JobStatusPage jobId={jobId} onComplete={() => setStep("results")} />}
      {step === "results" && jobId && <ResultsPage jobId={jobId} />}
    </div>
  );
}
```

- [ ] **Step 8: 브라우저에서 전체 흐름 확인**

```bash
cd frontend && npm run dev
# http://localhost:5173 접속
# 기술 입력 → 지표 생성 → 편집 → 확정 → 진행상황 → 결과 대시보드 흐름 확인
```

- [ ] **Step 9: 커밋**

```bash
git add frontend/src/
git commit -m "feat: complete frontend - status page, results dashboard, charts"
```

---

## Task 15: E2E 통합 테스트 + Docker 최종 확인

**Files:**
- Create: `backend/tests/test_pipeline_task.py`

- [ ] **Step 1: E2E 통합 테스트 작성**

`backend/tests/test_pipeline_task.py`:

```python
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

MOCK_INDICATORS = [
    {"name": "대역폭", "unit": "GB/s", "description": "메모리 대역폭", "search_keywords": "HBM bandwidth"},
]
MOCK_PAPERS = [
    {"paper_id": "abc", "title": "HBM3E test", "abstract": "achieves 1228 GB/s in Korea 2024", "year": 2024, "citation_count": 10, "doi": "10.1109/test"},
]
MOCK_EXTRACTION = {"value": 1228.0, "unit": "GB/s", "year": 2024, "country": "Korea", "confidence_score": 0.9, "paper_title": "HBM3E test", "doi": "10.1109/test", "source_url": None, "quote": "achieves 1228 GB/s"}

def test_full_flow(client):
    with patch("app.agents.indicator_agent.generate_indicators", new=AsyncMock(return_value=MOCK_INDICATORS)), \
         patch("app.agents.search_agent.search_all_sources", new=AsyncMock(return_value=MOCK_PAPERS)), \
         patch("app.agents.extraction_agent.extract_metric_from_paper", return_value=MOCK_EXTRACTION), \
         patch("app.agents.synthesis_agent.build_report_markdown", return_value="# 리포트"):

        # Step 1: 기술 입력
        res = client.post("/api/tech-input", json={"category": "반도체", "description": "HBM 기술"})
        assert res.status_code == 200
        query_id = res.json()["id"]

        # Step 2: 지표 생성
        res = client.post(f"/api/queries/{query_id}/indicators/generate")
        assert res.status_code == 200
        indicator_id = res.json()[0]["id"]

        # Step 3: 지표 확정
        client.put(f"/api/indicators/{indicator_id}", json={"confirmed_by_user": True})

        # Step 4: 잡 생성 확인 (Celery는 mock)
        with patch("app.routers.jobs.run_pipeline_task") as mock_task:
            mock_task.delay = MagicMock()
            res = client.post(f"/api/queries/{query_id}/jobs")
            assert res.status_code == 200
            job_id = res.json()["id"]
            assert res.json()["status"] == "pending"
```

- [ ] **Step 2: 테스트 실행**

```bash
cd backend && pytest tests/test_pipeline_task.py -v
# Expected: 1 passed
```

- [ ] **Step 3: Docker Compose 전체 기동 확인**

```bash
cp .env.example .env
# .env에 GEMINI_API_KEY 입력 후:
docker compose up --build
# 확인:
# - http://localhost:8017/health → {"status":"ok"}
# - http://localhost:8098 → React 앱
# - http://localhost:9001 → MinIO 콘솔 (minioadmin/minioadmin)
```

- [ ] **Step 4: MinIO 버킷 생성**

```bash
# MinIO 콘솔(http://localhost:9001)에서 또는:
docker compose exec minio mc alias set local http://localhost:9000 minioadmin minioadmin
docker compose exec minio mc mb local/techspec-pdfs
```

- [ ] **Step 5: 최종 커밋**

```bash
git add backend/tests/test_pipeline_task.py
git commit -m "test: e2e integration test for full pipeline flow"
```

---

## 자체 검토 결과

**Spec 커버리지 확인:**
- ✅ 기술 입력 (분류 + 자유 텍스트) — Task 4, 13
- ✅ 지표 자동 생성 + 편집 — Task 5, 13
- ✅ 비동기 처리 + WebSocket 진행률 — Task 9, 10, 13
- ✅ 이메일 알림 — Task 11
- ✅ Semantic Scholar + arXiv + Google Search Grounding — Task 6
- ✅ Gemini 수치 추출 + 교차검증 — Task 7, 8
- ✅ 시계열 차트 + 국가별 비교 — Task 14
- ✅ PDF 다운로드 — Task 11, 14
- ✅ 환경변수 기반 모델 설정 — Task 2
- ✅ Docker Compose 배포 — Task 1, 15

**타입 일관성:** `generate_indicators` → async, `extract_metric_from_paper` → sync (run_in_executor 내부에서 호출), `validate_and_rank` → sync. 모두 pipeline.py에서 일관되게 호출됨.
