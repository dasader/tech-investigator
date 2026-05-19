import asyncio
import logging
import random
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


async def run_sync(fn):
    return await asyncio.get_running_loop().run_in_executor(None, fn)


async def run_sync_with_retry(fn, max_retries: int = 4, base_delay: float = 1.0):
    for attempt in range(max_retries + 1):
        try:
            return await asyncio.get_running_loop().run_in_executor(None, fn)
        except Exception as e:
            is_rate_limit = (
                type(e).__name__ in ("ResourceExhausted", "TooManyRequests", "RateLimitError")
                or getattr(e, "status_code", None) == 429
                or getattr(e, "code", None) == 429
                or "429" in type(e).__name__
            )
            if is_rate_limit and attempt < max_retries:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                logger.warning(
                    "Gemini rate limit (attempt %d/%d), %.1fs 후 재시도",
                    attempt + 1, max_retries, delay,
                )
                await asyncio.sleep(delay)
            else:
                raise


def get_engine_label(search_source: str) -> str:
    if search_source == "scopus":
        return "Scopus (Elsevier) + Gemini"
    # combined 및 기타 모든 값(마이그레이션 전 잔존 구값 포함) → 기본 라벨
    return "OpenAlex + Semantic Scholar + KCI + Gemini"


def get_search_source(db: Session, query_id: int) -> str:
    from app.models.tech_query import TechQuery
    query_obj = db.query(TechQuery).filter(TechQuery.id == query_id).first()
    return (query_obj.search_source if query_obj else None) or "combined"
