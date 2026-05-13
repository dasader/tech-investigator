import pytest
from unittest.mock import AsyncMock
from app.agents.openalex_agent import _reconstruct_abstract, search_papers_for_indicator

pytestmark = pytest.mark.no_db


def test_reconstruct_abstract_basic():
    inv_idx = {
        "We": [0],
        "present": [1],
        "HBM3E": [2],
        "memory": [3],
    }
    assert _reconstruct_abstract(inv_idx) == "We present HBM3E memory"


def test_reconstruct_abstract_repeated_words():
    inv_idx = {
        "the": [0, 4],
        "memory": [1, 5],
        "is": [2],
        "fast": [3],
    }
    assert _reconstruct_abstract(inv_idx) == "the memory is fast the memory"


def test_reconstruct_abstract_none_returns_empty():
    assert _reconstruct_abstract(None) == ""


def test_reconstruct_abstract_empty_dict_returns_empty():
    assert _reconstruct_abstract({}) == ""


def test_reconstruct_abstract_handles_gaps():
    inv_idx = {"word_a": [0], "word_b": [10]}
    assert _reconstruct_abstract(inv_idx) == "word_a word_b"


MOCK_OPENALEX_RESPONSE = {
    "results": [
        {
            "id": "https://openalex.org/W123",
            "doi": "https://doi.org/10.1109/test.2024.001",
            "title": "HBM3E High Bandwidth Memory",
            "publication_year": 2024,
            "cited_by_count": 45,
            "abstract_inverted_index": {"We": [0], "present": [1], "HBM3E": [2]},
            "primary_location": {"source": {"display_name": "IEEE JSSC"}},
            "authorships": [
                {"institutions": [{"country_code": "KR"}]}
            ],
        }
    ]
}


@pytest.mark.asyncio
async def test_search_returns_normalized_papers(httpx_mock_get):
    httpx_mock_get("app.agents.openalex_agent", json_body=MOCK_OPENALEX_RESPONSE)
    results = await search_papers_for_indicator("HBM bandwidth", max_results=5)

    assert len(results) == 1
    p = results[0]
    assert p["title"] == "HBM3E High Bandwidth Memory"
    assert p["abstract"] == "We present HBM3E"
    assert p["doi"] == "10.1109/test.2024.001"
    assert p["year"] == 2024
    assert p["citation_count"] == 45
    assert p["country"] == "South Korea"
    assert p["journal_name"] == "IEEE JSSC"


@pytest.mark.asyncio
async def test_search_filters_entries_without_abstract(httpx_mock_get):
    no_abs = {
        "results": [
            {
                "id": "https://openalex.org/W1",
                "doi": None,
                "title": "Empty Abstract Paper",
                "publication_year": 2023,
                "cited_by_count": 0,
                "abstract_inverted_index": None,
                "primary_location": None,
                "authorships": [],
            }
        ]
    }
    httpx_mock_get("app.agents.openalex_agent", json_body=no_abs)
    results = await search_papers_for_indicator("test", max_results=5)
    assert results == []


@pytest.mark.asyncio
async def test_search_raises_on_429(httpx_mock_get, monkeypatch):
    monkeypatch.setattr("app.agents.openalex_agent.asyncio.sleep", AsyncMock())
    httpx_mock_get("app.agents.openalex_agent", status_code=429)
    with pytest.raises(RuntimeError, match="OpenAlex API error 429"):
        await search_papers_for_indicator("HBM bandwidth")


@pytest.mark.asyncio
async def test_search_country_none_when_no_institutions(httpx_mock_get):
    no_inst = {
        "results": [
            {
                "id": "https://openalex.org/W2",
                "doi": "https://doi.org/10.x/y",
                "title": "Paper without country",
                "publication_year": 2024,
                "cited_by_count": 3,
                "abstract_inverted_index": {"Hello": [0], "world": [1]},
                "primary_location": {"source": None},
                "authorships": [{"institutions": []}],
            }
        ]
    }
    httpx_mock_get("app.agents.openalex_agent", json_body=no_inst)
    results = await search_papers_for_indicator("test", max_results=5)
    assert results[0]["country"] is None
    assert results[0]["journal_name"] is None


@pytest.mark.asyncio
async def test_search_uses_cited_by_count_sort(httpx_mock_get):
    mock_client = httpx_mock_get("app.agents.openalex_agent", json_body={"results": []})
    await search_papers_for_indicator("test", max_results=5)

    _, kwargs = mock_client.get.call_args
    assert kwargs.get("params", {}).get("sort") == "cited_by_count:desc"
