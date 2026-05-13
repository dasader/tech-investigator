import pytest
from app.agents.openalex_agent import _reconstruct_abstract

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
    # positions: 0=the 1=memory 2=is 3=fast 4=the 5=memory
    assert _reconstruct_abstract(inv_idx) == "the memory is fast the memory"


def test_reconstruct_abstract_none_returns_empty():
    assert _reconstruct_abstract(None) == ""


def test_reconstruct_abstract_empty_dict_returns_empty():
    assert _reconstruct_abstract({}) == ""


def test_reconstruct_abstract_handles_gaps():
    # OpenAlex 인덱스는 일반적으로 gap 없음. gap이 있어도 sort된 키 순서로 처리해야 함.
    inv_idx = {"word_a": [0], "word_b": [10]}
    result = _reconstruct_abstract(inv_idx)
    assert result == "word_a word_b"


from unittest.mock import AsyncMock, patch, MagicMock
from app.agents.openalex_agent import search_papers_for_indicator

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
async def test_search_returns_normalized_papers():
    with patch("app.agents.openalex_agent.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = MOCK_OPENALEX_RESPONSE
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        results = await search_papers_for_indicator("HBM bandwidth", max_results=5)

    assert len(results) == 1
    p = results[0]
    assert p["title"] == "HBM3E High Bandwidth Memory"
    assert p["abstract"] == "We present HBM3E"
    assert p["doi"] == "10.1109/test.2024.001"   # https://doi.org/ 접두사 제거
    assert p["year"] == 2024
    assert p["citation_count"] == 45
    assert p["country"] == "South Korea"           # KR → South Korea 매핑
    assert p["journal_name"] == "IEEE JSSC"


@pytest.mark.asyncio
async def test_search_filters_entries_without_abstract():
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
    with patch("app.agents.openalex_agent.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = no_abs
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        results = await search_papers_for_indicator("test", max_results=5)
    assert results == []


@pytest.mark.asyncio
async def test_search_raises_on_429():
    with patch("app.agents.openalex_agent.asyncio.sleep"), \
         patch("app.agents.openalex_agent.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_client.get.return_value = mock_response

        with pytest.raises(RuntimeError, match="OpenAlex API error 429"):
            await search_papers_for_indicator("HBM bandwidth")


@pytest.mark.asyncio
async def test_search_country_none_when_no_institutions():
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
    with patch("app.agents.openalex_agent.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = no_inst
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        results = await search_papers_for_indicator("test", max_results=5)
    assert results[0]["country"] is None
    assert results[0]["journal_name"] is None
