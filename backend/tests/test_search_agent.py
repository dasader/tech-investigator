import asyncio
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch
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
async def test_search_all_sources_scopus_dispatches(mock_httpx_client, monkeypatch):
    captured = {}
    async def fake_scopus(*args, **kwargs):
        captured["called"] = True
        captured["client"] = kwargs.get("client")
        return [{"title": "Scopus Paper", "abstract": "abstract", "doi": None,
                 "year": 2024, "citation_count": 10, "paper_id": "S1", "country": "USA"}]
    from app.agents import search_agent
    monkeypatch.setattr(search_agent.scopus_agent, "search_papers_for_indicator", fake_scopus)
    client = mock_httpx_client()
    results = await search_all_sources(
        "HBM", source="scopus", max_results=5,
        semaphores={"scopus": asyncio.Semaphore(5)}, client=client)

    assert captured["called"] is True
    assert captured["client"] is client
    assert results[0]["title"] == "Scopus Paper"


@pytest.mark.asyncio
async def test_search_all_sources_combined_dispatches(monkeypatch):
    captured = {}
    async def fake_combined(keywords, *, s2_semaphore, openalex_semaphore, client, max_results=None):
        captured["s2_sem"] = s2_semaphore
        captured["oa_sem"] = openalex_semaphore
        return [{"title": "merged"}]
    from app.agents import search_agent
    monkeypatch.setattr(search_agent, "search_combined", fake_combined)
    s2_sem, oa_sem = asyncio.Semaphore(1), asyncio.Semaphore(10)
    results = await search_all_sources(
        "HBM", source="combined",
        semaphores={"semantic_scholar": s2_sem, "openalex": oa_sem},
        client=MagicMock())

    assert captured["s2_sem"] is s2_sem
    assert captured["oa_sem"] is oa_sem
    assert results[0]["title"] == "merged"


@pytest.mark.asyncio
async def test_search_all_sources_unknown_raises():
    with pytest.raises(ValueError, match="unknown search_source"):
        await search_all_sources("HBM", source="bogus", semaphores={}, client=MagicMock())
