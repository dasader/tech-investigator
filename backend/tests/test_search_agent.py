import pytest
import httpx
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


@pytest.mark.asyncio
async def test_search_raises_on_http_error():
    with patch("app.agents.search_agent.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get.side_effect = httpx.HTTPStatusError(
            "429 Too Many Requests",
            request=MagicMock(),
            response=MagicMock(status_code=429),
        )
        with pytest.raises(RuntimeError, match="Semantic Scholar API error 429"):
            await search_papers_for_indicator("HBM bandwidth")


@pytest.mark.asyncio
async def test_search_raises_on_timeout():
    with patch("app.agents.search_agent.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get.side_effect = httpx.TimeoutException("timeout")
        with pytest.raises(RuntimeError, match="timeout"):
            await search_papers_for_indicator("HBM bandwidth")
