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
