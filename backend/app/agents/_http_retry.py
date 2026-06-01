import asyncio
import httpx


async def _request_with_retry(
    url: str,
    *,
    client: httpx.AsyncClient,
    params: dict | None,
    headers: dict | None,
    service_name: str,
    context: str,
    max_attempts: int,
    timeout: float,
    inter_attempt_sleep: float,
    retry_status_codes: tuple[int, ...],
) -> httpx.Response:
    """HTTP GET with retry/backoff. Returns the raw response for the caller to decode.

    Behavior:
      - retry_status_codes: sleep(10 * (attempt+1)) and retry
      - TimeoutException / HTTPStatusError / RequestError → RuntimeError
        with the given service_name and context in the message
      - inter_attempt_sleep > 0: sleep that many seconds after every
        attempt (in finally) to respect per-service rate limits
      - All attempts exhausted on retry_status_codes: raise RuntimeError
    """
    for attempt in range(max_attempts):
        try:
            response = await client.get(url, params=params, headers=headers, timeout=timeout)
            if response.status_code in retry_status_codes:
                await asyncio.sleep(10 * (attempt + 1))
                continue
            response.raise_for_status()
            return response
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


async def get_with_retry(
    url: str,
    *,
    client: httpx.AsyncClient,
    params: dict | None = None,
    headers: dict | None = None,
    service_name: str,
    context: str = "",
    max_attempts: int = 3,
    timeout: float = 30.0,
    inter_attempt_sleep: float = 0.0,
    retry_status_codes: tuple[int, ...] = (429,),
) -> dict:
    """JSON GET with retry/backoff (see `_request_with_retry`)."""
    response = await _request_with_retry(
        url, client=client, params=params, headers=headers,
        service_name=service_name, context=context, max_attempts=max_attempts,
        timeout=timeout, inter_attempt_sleep=inter_attempt_sleep,
        retry_status_codes=retry_status_codes,
    )
    return response.json()


async def get_text_with_retry(
    url: str,
    *,
    client: httpx.AsyncClient,
    params: dict | None = None,
    headers: dict | None = None,
    service_name: str,
    context: str = "",
    max_attempts: int = 3,
    timeout: float = 30.0,
    inter_attempt_sleep: float = 0.0,
    retry_status_codes: tuple[int, ...] = (429,),
) -> str:
    """Text GET with retry/backoff. For XML/non-JSON services (see `_request_with_retry`)."""
    response = await _request_with_retry(
        url, client=client, params=params, headers=headers,
        service_name=service_name, context=context, max_attempts=max_attempts,
        timeout=timeout, inter_attempt_sleep=inter_attempt_sleep,
        retry_status_codes=retry_status_codes,
    )
    return response.text
