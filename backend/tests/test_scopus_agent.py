import pytest
from unittest.mock import AsyncMock
from app.agents.scopus_agent import search_papers_for_indicator

pytestmark = pytest.mark.no_db


MOCK_SCOPUS_RESPONSE = {
    "search-results": {
        "entry": [
            {
                "dc:identifier": "SCOPUS_ID:85123456",
                "dc:title": "HBM3E High Bandwidth Memory",
                "dc:description": "We present HBM3E achieving 1.2 TB/s bandwidth in 2024.",
                "prism:doi": "10.1109/scopus.2024.001",
                "citedby-count": "30",
                "prism:coverDate": "2024-03-01",
                "affiliation": [
                    {
                        "affiliation-country": "South Korea",
                        "affilname": "SK Hynix",
                    }
                ],
            }
        ]
    }
}

MOCK_SCOPUS_NO_AFFILIATION = {
    "search-results": {
        "entry": [
            {
                "dc:identifier": "SCOPUS_ID:85000001",
                "dc:title": "Paper Without Affiliation",
                "dc:description": "Some abstract text here.",
                "prism:doi": "10.1109/test.2024.002",
                "citedby-count": "5",
                "prism:coverDate": "2024-01-01",
                "affiliation": [],
            }
        ]
    }
}


@pytest.mark.asyncio
async def test_search_returns_normalized_papers(httpx_mock_get):
    httpx_mock_get("app.agents.scopus_agent", json_body=MOCK_SCOPUS_RESPONSE)
    results = await search_papers_for_indicator("HBM bandwidth", max_results=5)

    assert isinstance(results, list)
    assert len(results) == 1
    paper = results[0]
    assert paper["title"] == "HBM3E High Bandwidth Memory"
    assert paper["abstract"] == "We present HBM3E achieving 1.2 TB/s bandwidth in 2024."
    assert paper["doi"] == "10.1109/scopus.2024.001"
    assert paper["year"] == 2024
    assert paper["citation_count"] == 30
    assert paper["country"] == "South Korea"


@pytest.mark.asyncio
async def test_search_country_none_when_no_affiliation(httpx_mock_get):
    httpx_mock_get("app.agents.scopus_agent", json_body=MOCK_SCOPUS_NO_AFFILIATION)
    results = await search_papers_for_indicator("test keyword", max_results=5)
    assert results[0]["country"] is None


@pytest.mark.asyncio
async def test_search_filters_entries_without_abstract(httpx_mock_get):
    no_abstract_response = {
        "search-results": {
            "entry": [
                {
                    "dc:identifier": "SCOPUS_ID:1",
                    "dc:title": "No Abstract Paper",
                    "dc:description": "",
                    "prism:doi": "10.1/test",
                    "citedby-count": "0",
                    "prism:coverDate": "2023-01-01",
                    "affiliation": [],
                }
            ]
        }
    }
    httpx_mock_get("app.agents.scopus_agent", json_body=no_abstract_response)
    results = await search_papers_for_indicator("test", max_results=5)
    assert results == []


@pytest.mark.asyncio
async def test_search_raises_on_429(httpx_mock_get, monkeypatch):
    monkeypatch.setattr("app.agents.scopus_agent.asyncio.sleep", AsyncMock())
    httpx_mock_get("app.agents.scopus_agent", status_code=429)
    with pytest.raises(RuntimeError, match="Scopus API error 429"):
        await search_papers_for_indicator("HBM bandwidth")


@pytest.mark.asyncio
async def test_search_handles_single_affiliation_as_dict(httpx_mock_get, monkeypatch):
    monkeypatch.setattr("app.agents.scopus_agent.asyncio.sleep", AsyncMock())
    single_aff_response = {
        "search-results": {
            "entry": [
                {
                    "dc:identifier": "SCOPUS_ID:2",
                    "dc:title": "Single Affiliation Paper",
                    "dc:description": "Abstract content here.",
                    "prism:doi": "10.1/single",
                    "citedby-count": "5",
                    "prism:coverDate": "2024-01-01",
                    "affiliation": {
                        "affiliation-country": "Japan",
                        "affilname": "RIKEN",
                    },
                }
            ]
        }
    }
    httpx_mock_get("app.agents.scopus_agent", json_body=single_aff_response)
    results = await search_papers_for_indicator("test", max_results=5)
    assert results[0]["country"] == "Japan"
