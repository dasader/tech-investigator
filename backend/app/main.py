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
