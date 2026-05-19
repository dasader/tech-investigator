import asyncio
import pytest
from unittest.mock import AsyncMock
import httpx

from app.agents import kci_agent

pytestmark = pytest.mark.no_db


@pytest.mark.asyncio
async def test_kci_search_skips_when_no_api_key(monkeypatch):
    monkeypatch.setattr("app.agents.kci_agent.settings.kci_api_key", "")
    client = AsyncMock(spec=httpx.AsyncClient)

    result = await kci_agent.search_papers_for_indicator(
        "HBM bandwidth", max_results=10, client=client,
    )

    assert result == []
    client.get.assert_not_called()


MOCK_SEARCH_XML = """<?xml version="1.0" encoding="UTF-8"?>
<resultList>
  <outputData>
    <record>
      <article-id pubidtype="kciid">ART001</article-id>
      <article-id pubidtype="doi">10.1234/foo.2024.001</article-id>
      <title-group>
        <article-title language="kor">한국어 제목</article-title>
        <article-title language="eng">High Bandwidth Memory Stack Yield</article-title>
      </title-group>
      <pub-year>2024</pub-year>
      <journal-name language="eng">Journal of Korean Semiconductor</journal-name>
      <journal-name language="kor">한국반도체학회지</journal-name>
      <citation-count>17</citation-count>
    </record>
  </outputData>
</resultList>"""

MOCK_DETAIL_XML = """<?xml version="1.0" encoding="UTF-8"?>
<resultList>
  <outputData>
    <record>
      <abstract-group>
        <abstract language="kor">한국어 초록 내용 1.2 마이크로미터.</abstract>
        <abstract language="eng">We report HBM3E stacking achieving 1.2 TB/s bandwidth.</abstract>
      </abstract-group>
    </record>
  </outputData>
</resultList>"""


def _make_xml_client(*, search_xml: str, detail_xml: str):
    """KCI 호출을 구분 — apiCode 파라미터로 search/detail mock 응답을 분기."""
    from unittest.mock import AsyncMock, MagicMock
    client = AsyncMock(spec=httpx.AsyncClient)

    async def fake_get(url, params=None, headers=None, timeout=None):
        api_code = (params or {}).get("apiCode")
        response = MagicMock()
        response.status_code = 200
        response.raise_for_status = MagicMock()
        response.text = detail_xml if api_code == "articleDetail" else search_xml
        return response

    client.get.side_effect = fake_get
    return client


@pytest.mark.asyncio
async def test_kci_search_returns_papers(monkeypatch):
    monkeypatch.setattr("app.agents.kci_agent.settings.kci_api_key", "test-key")
    client = _make_xml_client(search_xml=MOCK_SEARCH_XML, detail_xml=MOCK_DETAIL_XML)

    results = await kci_agent.search_papers_for_indicator(
        "HBM bandwidth", max_results=5, client=client,
    )

    assert len(results) == 1
    paper = results[0]
    assert paper["paper_id"] == "ART001"
    assert paper["doi"] == "10.1234/foo.2024.001"
    assert paper["title"] == "High Bandwidth Memory Stack Yield"  # 영문 우선
    assert paper["abstract"].startswith("We report HBM3E")  # 영문 우선
    assert paper["year"] == 2024
    assert paper["citation_count"] == 17
    assert paper["journal_name"] == "Journal of Korean Semiconductor"
    assert paper["country"] == "South Korea"
    assert paper["country_lookup_done"] is True
