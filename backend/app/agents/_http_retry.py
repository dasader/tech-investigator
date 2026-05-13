import asyncio
import httpx


async def get_with_retry(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    service_name: str,
    context: str = "",
    max_attempts: int = 3,
    timeout: float = 30.0,
    inter_attempt_sleep: float = 0.0,
    retry_status_codes: tuple[int, ...] = (429,),
) -> dict:
    """HTTP GET with retry/backoff. Returns parsed JSON dict.

    Behavior:
      - retry_status_codes: sleep(10 * (attempt+1)) and retry
      - TimeoutException / HTTPStatusError / RequestError → RuntimeError
        with the given service_name and context in the message
      - inter_attempt_sleep > 0: sleep that many seconds after every
        attempt (in finally) to respect per-service rate limits
      - All attempts exhausted on retry_status_codes: raise RuntimeError
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(max_attempts):
            try:
                response = await client.get(url, params=params, headers=headers)
                if response.status_code in retry_status_codes:
                    await asyncio.sleep(10 * (attempt + 1))
                    continue
                response.raise_for_status()
                return response.json()
            except httpx.TimeoutException as e:
                raise RuntimeError(f"{service_name} API timeout for: {context}") from e
            except httpx.HTTPStatusError as e:
                raise RuntimeError(
                    f"{service_name} API error {e.response.status_code}: {context}"
                ) from e
            except httpx.RequestError as e:
                raise RuntimeError(f"{service_name} network error: {context}") from e
            finally:
                if inter_attempt_sleep:
                    await asyncio.sleep(inter_attempt_sleep)
        raise RuntimeError(f"{service_name} API error 429: {context}")
