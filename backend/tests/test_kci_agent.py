import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
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


# 실제 KCI articleSearch.kci 응답 형식. 핵심 차이점:
# - 루트는 <MetaData>, articleInfo의 article-id는 element가 아닌 attribute
# - DOI는 <doi> element (URL prefix 포함)
# - title/abstract의 언어 속성은 lang="english" / lang="original" / lang="foreign"
# - journal-name과 pub-year는 <journalInfo> 안에 중첩 (articleInfo의 sibling)
# - articleSearch 단일 호출로 abstract까지 받음 — articleDetail 호출 불필요
MOCK_SEARCH_XML = """<?xml version="1.0" encoding="UTF-8"?>
<MetaData>
  <inputData>
    <key>test-key</key>
    <apiCode>articleSearch</apiCode>
    <keyword>HBM bandwidth</keyword>
  </inputData>
  <outputData>
    <result><total>1</total></result>
    <record>
      <journalInfo>
        <journal-name>Journal of Korean Semiconductor</journal-name>
        <publisher-name>Korean Semiconductor Society</publisher-name>
        <pub-year>2024</pub-year>
        <volume>15</volume>
      </journalInfo>
      <articleInfo article-id="ART003194268">
        <article-categories>전자공학</article-categories>
        <title-group>
          <article-title lang="original"><![CDATA[HBM 스택 수율 개선]]></article-title>
          <article-title lang="english"><![CDATA[High Bandwidth Memory Stack Yield]]></article-title>
        </title-group>
        <abstract-group>
          <abstract lang="original"><![CDATA[한국어 초록 내용]]></abstract>
          <abstract lang="english"><![CDATA[We report HBM3E stacking achieving 1.2 TB/s bandwidth.]]></abstract>
        </abstract-group>
        <doi><![CDATA[http://dx.doi.org/10.6117/kmeps.2024.15.1.013]]></doi>
        <citation-count kci="17" wos="3">17</citation-count>
      </articleInfo>
    </record>
  </outputData>
</MetaData>"""


def _make_kci_client(xml_text: str):
    """KCI 호출 1회 mock — articleSearch만 사용 (articleDetail 폐기)."""
    client = AsyncMock(spec=httpx.AsyncClient)
    captured_params: dict = {}

    async def fake_get(url, params=None, headers=None, timeout=None):
        captured_params.update(params or {})
        response = MagicMock()
        response.status_code = 200
        response.raise_for_status = MagicMock()
        response.text = xml_text
        return response

    client.get.side_effect = fake_get
    client.captured_params = captured_params  # 테스트에서 검증용
    return client


@pytest.mark.asyncio
async def test_kci_search_returns_papers(monkeypatch):
    monkeypatch.setattr("app.agents.kci_agent.settings.kci_api_key", "test-key")
    client = _make_kci_client(MOCK_SEARCH_XML)

    results = await kci_agent.search_papers_for_indicator(
        "HBM bandwidth", max_results=5, client=client,
    )

    # 요청 파라미터 검증 — 실제 KCI는 "keyword" param 사용 (searchQuery는 무시됨).
    assert client.captured_params.get("keyword") == "HBM bandwidth"
    assert client.captured_params.get("apiCode") == "articleSearch"
    assert client.captured_params.get("key") == "test-key"

    assert len(results) == 1
    paper = results[0]
    assert paper["paper_id"] == "ART003194268"
    # DOI URL prefix가 stripping되어 bare DOI 형식
    assert paper["doi"] == "10.6117/kmeps.2024.15.1.013"
    assert paper["title"] == "High Bandwidth Memory Stack Yield"  # english 우선
    assert paper["abstract"].startswith("We report HBM3E")  # english 우선
    assert paper["year"] == 2024
    assert paper["citation_count"] == 17
    assert paper["journal_name"] == "Journal of Korean Semiconductor"
    assert paper["country"] == "South Korea"
    assert paper["country_lookup_done"] is True


MOCK_SEARCH_XML_KO_ONLY = """<?xml version="1.0" encoding="UTF-8"?>
<MetaData>
  <outputData>
    <record>
      <journalInfo>
        <journal-name>한국반도체학회지</journal-name>
        <pub-year>2024</pub-year>
      </journalInfo>
      <articleInfo article-id="ART002">
        <title-group>
          <article-title lang="original"><![CDATA[한국어 전용 논문]]></article-title>
        </title-group>
        <abstract-group>
          <abstract lang="original"><![CDATA[한국어 초록입니다. 대역폭 1.2 TB/s를 달성하였다.]]></abstract>
        </abstract-group>
        <citation-count kci="3" wos="0">3</citation-count>
      </articleInfo>
    </record>
  </outputData>
</MetaData>"""


@pytest.mark.asyncio
async def test_kci_search_korean_abstract_fallback(monkeypatch):
    """영문 abstract 부재 → 한글 abstract (lang="original")로 fallback."""
    monkeypatch.setattr("app.agents.kci_agent.settings.kci_api_key", "test-key")
    client = _make_kci_client(MOCK_SEARCH_XML_KO_ONLY)

    results = await kci_agent.search_papers_for_indicator(
        "HBM bandwidth", max_results=5, client=client,
    )

    assert len(results) == 1
    assert results[0]["abstract"].startswith("한국어 초록")
    # title도 동일 fallback
    assert results[0]["title"] == "한국어 전용 논문"


MOCK_SEARCH_XML_EMPTY_ABSTRACTS = """<?xml version="1.0" encoding="UTF-8"?>
<MetaData>
  <outputData>
    <record>
      <journalInfo><pub-year>2024</pub-year></journalInfo>
      <articleInfo article-id="ART003">
        <title-group><article-title lang="english">Title Only</article-title></title-group>
        <abstract-group>
          <abstract lang="original"></abstract>
          <abstract lang="english"></abstract>
        </abstract-group>
      </articleInfo>
    </record>
  </outputData>
</MetaData>"""


@pytest.mark.asyncio
async def test_kci_search_filters_no_abstract(monkeypatch):
    """한/영 abstract 모두 비어있는 paper는 drop (Gemini 추출 불가)."""
    monkeypatch.setattr("app.agents.kci_agent.settings.kci_api_key", "test-key")
    client = _make_kci_client(MOCK_SEARCH_XML_EMPTY_ABSTRACTS)

    results = await kci_agent.search_papers_for_indicator(
        "HBM bandwidth", max_results=5, client=client,
    )

    assert results == []


MOCK_SEARCH_XML_MIXED_RECORDS = """<?xml version="1.0" encoding="UTF-8"?>
<MetaData>
  <outputData>
    <record>
      <journalInfo><pub-year>2024</pub-year></journalInfo>
      <articleInfo article-id="ART100">
        <title-group><article-title lang="english">Good Paper</article-title></title-group>
        <abstract-group><abstract lang="english">Valid abstract.</abstract></abstract-group>
      </articleInfo>
    </record>
    <record>
      <journalInfo><pub-year>2024</pub-year></journalInfo>
      <articleInfo>
        <title-group><article-title lang="english">Missing ID</article-title></title-group>
        <abstract-group><abstract lang="english">Has abstract but no article-id.</abstract></abstract-group>
      </articleInfo>
    </record>
  </outputData>
</MetaData>"""


@pytest.mark.asyncio
async def test_kci_search_skips_records_without_article_id(monkeypatch):
    """article-id 속성 없는 record는 skip — 식별 불가."""
    monkeypatch.setattr("app.agents.kci_agent.settings.kci_api_key", "test-key")
    client = _make_kci_client(MOCK_SEARCH_XML_MIXED_RECORDS)

    results = await kci_agent.search_papers_for_indicator(
        "HBM bandwidth", max_results=5, client=client,
    )

    assert len(results) == 1
    assert results[0]["paper_id"] == "ART100"


@pytest.mark.asyncio
async def test_kci_search_raises_on_http_error(monkeypatch):
    """KCI 호출 자체 실패(500 등) → RuntimeError. search_combined에서 graceful degrade."""
    monkeypatch.setattr("app.agents.kci_agent.settings.kci_api_key", "test-key")
    client = AsyncMock(spec=httpx.AsyncClient)
    err = httpx.HTTPStatusError(
        "500", request=MagicMock(),
        response=MagicMock(status_code=500),
    )
    client.get.side_effect = err

    with pytest.raises(RuntimeError, match="KCI"):
        await kci_agent.search_papers_for_indicator(
            "HBM bandwidth", max_results=5, client=client,
        )
