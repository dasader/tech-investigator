import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock

from app.agents._http_retry import get_with_retry

pytestmark = pytest.mark.no_db


def _patch_client(monkeypatch, *, get_side_effect):
    """Patch httpx.AsyncClient in the helper module. `get_side_effect` can be a
    mock_response, a list/iter of responses, or an Exception subclass to raise."""
    mock_client = AsyncMock()
    if isinstance(get_side_effect, list):
        mock_client.get.side_effect = get_side_effect
    elif isinstance(get_side_effect, Exception):
        mock_client.get.side_effect = get_side_effect
    else:
        mock_client.get.return_value = get_side_effect
    mock_client_class = MagicMock()
    mock_client_class.return_value.__aenter__.return_value = mock_client
    monkeypatch.setattr("app.agents._http_retry.httpx.AsyncClient", mock_client_class)
    return mock_client


@pytest.mark.asyncio
async def test_get_with_retry_returns_json_on_200(monkeypatch):
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"hello": "world"}
    response.raise_for_status = MagicMock()
    _patch_client(monkeypatch, get_side_effect=response)

    result = await get_with_retry(
        "http://example.test/api",
        service_name="TestSvc",
        context="kw",
    )
    assert result == {"hello": "world"}


@pytest.mark.asyncio
async def test_get_with_retry_raises_on_max_attempts_429(monkeypatch):
    response = MagicMock()
    response.status_code = 429
    _patch_client(monkeypatch, get_side_effect=response)
    monkeypatch.setattr("app.agents._http_retry.asyncio.sleep", AsyncMock())

    with pytest.raises(RuntimeError, match="TestSvc API error 429"):
        await get_with_retry(
            "http://example.test/api",
            service_name="TestSvc",
            context="kw",
        )


@pytest.mark.asyncio
async def test_get_with_retry_wraps_http_status_error(monkeypatch):
    response = MagicMock()
    response.status_code = 500
    err = httpx.HTTPStatusError("boom", request=MagicMock(), response=response)
    response.raise_for_status = MagicMock(side_effect=err)
    _patch_client(monkeypatch, get_side_effect=response)

    with pytest.raises(RuntimeError, match="TestSvc API error 500"):
        await get_with_retry(
            "http://example.test/api",
            service_name="TestSvc",
            context="kw",
        )


@pytest.mark.asyncio
async def test_get_with_retry_wraps_timeout(monkeypatch):
    _patch_client(monkeypatch, get_side_effect=httpx.TimeoutException("slow"))

    with pytest.raises(RuntimeError, match="TestSvc API timeout for: kw"):
        await get_with_retry(
            "http://example.test/api",
            service_name="TestSvc",
            context="kw",
        )


@pytest.mark.asyncio
async def test_get_with_retry_succeeds_after_429(monkeypatch):
    r429 = MagicMock()
    r429.status_code = 429
    r200 = MagicMock()
    r200.status_code = 200
    r200.json.return_value = {"ok": True}
    r200.raise_for_status = MagicMock()
    _patch_client(monkeypatch, get_side_effect=[r429, r200])
    monkeypatch.setattr("app.agents._http_retry.asyncio.sleep", AsyncMock())

    result = await get_with_retry(
        "http://example.test/api",
        service_name="TestSvc",
        context="kw",
    )
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_get_with_retry_wraps_request_error(monkeypatch):
    _patch_client(monkeypatch, get_side_effect=httpx.ConnectError("dns fail"))

    with pytest.raises(RuntimeError, match="TestSvc network error: kw"):
        await get_with_retry(
            "http://example.test/api",
            service_name="TestSvc",
            context="kw",
        )
