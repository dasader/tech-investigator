import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock

from app.agents._http_retry import get_with_retry, get_text_with_retry

pytestmark = pytest.mark.no_db


@pytest.mark.asyncio
async def test_get_with_retry_returns_json_on_200(mock_httpx_client):
    client = mock_httpx_client(json_body={"hello": "world"})

    result = await get_with_retry(
        "http://example.test/api",
        client=client,
        service_name="TestSvc",
        context="kw",
    )
    assert result == {"hello": "world"}


@pytest.mark.asyncio
async def test_get_with_retry_raises_on_max_attempts_429(mock_httpx_client):
    client = mock_httpx_client(status_code=429)

    with pytest.raises(RuntimeError, match="TestSvc API error 429"):
        await get_with_retry(
            "http://example.test/api",
            client=client,
            service_name="TestSvc",
            context="kw",
        )


@pytest.mark.asyncio
async def test_get_with_retry_wraps_http_status_error():
    response = MagicMock()
    response.status_code = 500
    err = httpx.HTTPStatusError("boom", request=MagicMock(), response=response)
    response.raise_for_status = MagicMock(side_effect=err)
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get.return_value = response

    with pytest.raises(RuntimeError, match="TestSvc API error 500"):
        await get_with_retry(
            "http://example.test/api",
            client=client,
            service_name="TestSvc",
            context="kw",
        )


@pytest.mark.asyncio
async def test_get_with_retry_wraps_timeout(mock_httpx_client):
    client = mock_httpx_client(get_side_effect=httpx.TimeoutException("slow"))

    with pytest.raises(RuntimeError, match="TestSvc API timeout for: kw"):
        await get_with_retry(
            "http://example.test/api",
            client=client,
            service_name="TestSvc",
            context="kw",
        )


@pytest.mark.asyncio
async def test_get_with_retry_succeeds_after_429(mock_httpx_client):
    r429 = MagicMock()
    r429.status_code = 429
    r200 = MagicMock()
    r200.status_code = 200
    r200.json.return_value = {"ok": True}
    r200.raise_for_status = MagicMock()
    client = mock_httpx_client(get_side_effect=[r429, r200])

    result = await get_with_retry(
        "http://example.test/api",
        client=client,
        service_name="TestSvc",
        context="kw",
    )
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_get_with_retry_wraps_request_error(mock_httpx_client):
    client = mock_httpx_client(get_side_effect=httpx.ConnectError("dns fail"))

    with pytest.raises(RuntimeError, match="TestSvc network error: kw"):
        await get_with_retry(
            "http://example.test/api",
            client=client,
            service_name="TestSvc",
            context="kw",
        )


@pytest.mark.asyncio
async def test_get_text_returns_response_text():
    client = AsyncMock(spec=httpx.AsyncClient)
    response = MagicMock()
    response.status_code = 200
    response.text = "<resultList><record>hello</record></resultList>"
    response.raise_for_status = MagicMock()
    client.get.return_value = response

    text = await get_text_with_retry(
        "https://example.invalid/api",
        client=client,
        service_name="TestService",
        context="kw",
    )
    assert text.startswith("<resultList>")
    assert "hello" in text


@pytest.mark.asyncio
async def test_get_text_raises_runtime_on_http_status_error():
    client = AsyncMock(spec=httpx.AsyncClient)
    err = httpx.HTTPStatusError(
        "500", request=MagicMock(),
        response=MagicMock(status_code=500),
    )
    client.get.side_effect = err

    with pytest.raises(RuntimeError, match="TestService API error 500"):
        await get_text_with_retry(
            "https://example.invalid/api",
            client=client,
            service_name="TestService",
            context="kw",
        )
