from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import tech_input, indicators, jobs, results

# 모든 모델을 먼저 임포트해야 SQLAlchemy relationship이 올바르게 초기화됨
import app.models.tech_query  # noqa: F401
import app.models.indicator   # noqa: F401
import app.models.metric_value  # noqa: F401
import app.models.job         # noqa: F401

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


@app.get("/health")
def health():
    return {"status": "ok"}
