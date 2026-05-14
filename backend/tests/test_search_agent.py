import pytest
import httpx
from unittest.mock import MagicMock
from app.agents.search_agent import search_papers_for_indicator, search_all_sources

pytestmark = pytest.mark.no_db

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
async def test_search_returns_list_of_papers(mock_httpx_client):
    client = mock_httpx_client(json_body=MOCK_SS_RESPONSE)
    results = await search_papers_for_indicator("HBM bandwidth GB/s", max_results=5, client=client)

    assert isinstance(results, list)
    assert len(results) >= 1
    assert "title" in results[0]
    assert "abstract" in results[0]


@pytest.mark.asyncio
async def test_search_filters_empty_abstracts(mock_httpx_client):
    payload = {
        "data": [
            {"paperId": "x1", "title": "Paper 1", "abstract": None, "year": 2023, "citationCount": 10, "externalIds": {}},
            {"paperId": "x2", "title": "Paper 2", "abstract": "actual content with values", "year": 2023, "citationCount": 10, "externalIds": {}},
        ]
    }
    client = mock_httpx_client(json_body=payload)
    results = await search_papers_for_indicator("test keyword", max_results=5, client=client)
    assert all(r["abstract"] for r in results)


@pytest.mark.asyncio
async def test_search_raises_on_http_error(mock_httpx_client):
    err = httpx.HTTPStatusError(
        "429 Too Many Requests",
        request=MagicMock(),
        response=MagicMock(status_code=429),
    )
    client = mock_httpx_client(get_side_effect=err)
    with pytest.raises(RuntimeError, match="Semantic Scholar"):
        await search_papers_for_indicator("HBM bandwidth", client=client)


@pytest.mark.asyncio
async def test_search_raises_on_timeout(mock_httpx_client):
    client = mock_httpx_client(get_side_effect=httpx.TimeoutException("timeout"))
    with pytest.raises(RuntimeError, match="timeout"):
        await search_papers_for_indicator("HBM bandwidth", client=client)


@pytest.mark.asyncio
async def test_search_all_sources_uses_scopus_when_specified(mock_httpx_client, monkeypatch):
    captured = {}
    async def fake_scopus(*args, **kwargs):
        captured["called"] = True
        captured["client"] = kwargs.get("client")
        return [{"title": "Scopus Paper", "abstract": "abstract", "doi": None,
                 "year": 2024, "citation_count": 10, "paper_id": "S1", "country": "USA"}]
    from app.agents import search_agent
    monkeypatch.setattr(search_agent.scopus_agent, "search_papers_for_indicator", fake_scopus)
    client = mock_httpx_client()
    results = await search_all_sources("HBM", source="scopus", max_results=5, client=client)

    assert captured["called"] is True
    assert captured["client"] is client
    assert results[0]["title"] == "Scopus Paper"


@pytest.mark.asyncio
async def test_search_all_sources_uses_semantic_scholar_by_default(mock_httpx_client):
    client = mock_httpx_client(json_body=MOCK_SS_RESPONSE)
    results = await search_all_sources("HBM", max_results=5, client=client)
    assert results[0]["title"] == "HBM3E: High Bandwidth Memory"


@pytest.mark.asyncio
async def test_search_all_sources_uses_openalex_when_specified(mock_httpx_client, monkeypatch):
    captured = {}
    async def fake_openalex(*args, **kwargs):
        captured["called"] = True
        captured["client"] = kwargs.get("client")
        return [{"title": "OpenAlex Paper", "abstract": "abstract", "doi": "10.x/y",
                 "year": 2024, "citation_count": 12, "paper_id": "OA1", "country": "South Korea",
                 "journal_name": "Nature"}]
    from app.agents import search_agent
    monkeypatch.setattr(search_agent.openalex_agent, "search_papers_for_indicator", fake_openalex)
    client = mock_httpx_client()
    results = await search_all_sources("HBM", source="openalex", max_results=5, client=client)

    assert captured["called"] is True
    assert captured["client"] is client
    assert results[0]["title"] == "OpenAlex Paper"
