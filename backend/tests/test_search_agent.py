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
    with patch("app.agents._http_retry.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 200
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
    with patch("app.agents._http_retry.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 200
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
    with patch("app.agents._http_retry.httpx.AsyncClient") as mock_client_class:
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
    with patch("app.agents._http_retry.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.get.side_effect = httpx.TimeoutException("timeout")
        with pytest.raises(RuntimeError, match="timeout"):
            await search_papers_for_indicator("HBM bandwidth")


@pytest.mark.asyncio
async def test_search_all_sources_uses_scopus_when_specified():
    with patch("app.agents.search_agent.scopus_agent") as mock_scopus:
        mock_scopus.search_papers_for_indicator = AsyncMock(return_value=[
            {"title": "Scopus Paper", "abstract": "abstract", "doi": None,
             "year": 2024, "citation_count": 10, "paper_id": "S1", "country": "USA"}
        ])
        from app.agents.search_agent import search_all_sources
        results = await search_all_sources("HBM", source="scopus", max_results=5)

    mock_scopus.search_papers_for_indicator.assert_called_once()
    assert results[0]["title"] == "Scopus Paper"


@pytest.mark.asyncio
async def test_search_all_sources_uses_semantic_scholar_by_default():
    with patch("app.agents._http_retry.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = MOCK_SS_RESPONSE
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response
        from app.agents.search_agent import search_all_sources
        results = await search_all_sources("HBM", max_results=5)

    assert results[0]["title"] == "HBM3E: High Bandwidth Memory"


@pytest.mark.asyncio
async def test_search_all_sources_uses_openalex_when_specified():
    with patch("app.agents.search_agent.openalex_agent") as mock_openalex:
        mock_openalex.search_papers_for_indicator = AsyncMock(return_value=[
            {"title": "OpenAlex Paper", "abstract": "abstract", "doi": "10.x/y",
             "year": 2024, "citation_count": 12, "paper_id": "OA1", "country": "South Korea",
             "journal_name": "Nature"}
        ])
        from app.agents.search_agent import search_all_sources
        results = await search_all_sources("HBM", source="openalex", max_results=5)

    mock_openalex.search_papers_for_indicator.assert_called_once()
    assert results[0]["title"] == "OpenAlex Paper"
