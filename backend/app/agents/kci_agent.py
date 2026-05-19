import asyncio
import logging
import xml.etree.ElementTree as ET
import httpx

from app.config import settings
from app.agents._http_retry import get_text_with_retry

logger = logging.getLogger(__name__)

KCI_API_URL = "https://open.kci.go.kr/po/openapi/openApiSearch.kci"

# articleDetail.kci N+1 호출 throttle (process-wide, indicator 외 동시성과 별도).
_DETAIL_SEM = asyncio.Semaphore(5)


async def search_papers_for_indicator(
    keywords: str,
    max_results: int | None = None,
    semaphore: asyncio.Semaphore | None = None,
    *,
    client: httpx.AsyncClient,
) -> list[dict]:
    if not settings.kci_api_key:
        return []
    # 이후 단계에서 채워질 구현
    return []
