import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.orm import Session
from app.agents.pipeline import SOURCE_PLAN, extract_node

pytestmark = pytest.mark.no_db


def test_source_plan_combined():
    assert SOURCE_PLAN["combined"] == {"semantic_scholar": 1, "openalex": 10, "kci": 3}


def test_source_plan_scopus():
    assert SOURCE_PLAN["scopus"] == {"scopus": 5}


def test_source_plan_keys_match_schema_literal():
    # SOURCE_PLAN 키가 search_source의 Literal 후보와 정확히 일치하는지 가드 —
    # 스키마에 source가 추가/제거되면 SOURCE_PLAN 불일치를 여기서 잡는다.
    from typing import get_args
    from app.schemas.tech_query import TechQueryCreate

    literal_sources = set(get_args(TechQueryCreate.model_fields["search_source"].annotation))
    assert set(SOURCE_PLAN) == literal_sources


@pytest.mark.asyncio
async def test_extract_node_passes_domain_context_to_extractor():
    """extract_node가 state의 category/description을 extract_metrics_from_paper에 전달한다."""
    captured: dict = {}

    async def fake_extract(paper, indicators, semaphore, *, client, category="", description=""):
        captured["category"] = category
        captured["description"] = description
        return []  # 빈 결과로 충분

    state = {
        "job_id": 1,
        "query_id": 1,
        "category": "HBM 고대역폭 메모리",
        "description": "이형접합 기판 기반의 적층 기술",
        "search_source": "combined",
        "indicators": [{"id": 1, "name": "대역폭", "unit": "GB/s",
                        "search_keywords": "HBM", "extraction_hint": None}],
        "search_results": {1: [{"title": "T", "abstract": "1000 GB/s", "doi": "10.1/x"}]},
        "extracted_values": {},
        "validated_values": {},
        "report_markdown": "",
    }
    db = MagicMock(spec=Session)
    db.get.return_value = MagicMock(progress_pct=0.0, current_step="")
    client = AsyncMock(spec=httpx.AsyncClient)

    async def fake_batch(dois, *, client):
        return {}

    with patch("app.agents.pipeline.extract_metrics_from_paper", new=fake_extract), \
         patch("app.agents.pipeline.openalex_agent.batch_resolve_countries", new=fake_batch):
        await extract_node(state, db, client)

    assert captured["category"] == "HBM 고대역폭 메모리"
    assert captured["description"] == "이형접합 기판 기반의 적층 기술"


@pytest.mark.asyncio
async def test_extract_node_batch_resolves_country_before_extract():
    """country 미상+DOI 논문은 일괄 OpenAlex 조회로 country가 채워지고,
    못 찾은 DOI는 country_lookup_done=True로 막혀 per-paper 조회를 스킵한다."""
    seen_papers: list[dict] = []

    async def fake_extract(paper, indicators, semaphore, *, client, category="", description=""):
        seen_papers.append(paper)
        return []

    async def fake_batch(dois, *, client):
        assert set(dois) == {"10.1/has", "10.2/none"}
        return {"10.1/has": "South Korea"}  # 두 번째는 미해결

    state = {
        "job_id": 1, "query_id": 1, "category": "C", "description": "D",
        "search_source": "combined",
        "indicators": [{"id": 1, "name": "지표", "unit": "u",
                        "search_keywords": "k", "extraction_hint": None}],
        "search_results": {1: [
            {"title": "P1", "abstract": "1 u", "doi": "10.1/has", "country": None},
            {"title": "P2", "abstract": "2 u", "doi": "10.2/none", "country": None},
            {"title": "P3", "abstract": "3 u", "doi": None, "country": "USA"},  # 조회 대상 아님
        ]},
        "extracted_values": {}, "validated_values": {}, "report_markdown": "",
    }
    db = MagicMock(spec=Session)
    db.get.return_value = MagicMock(progress_pct=0.0, current_step="")
    client = AsyncMock(spec=httpx.AsyncClient)

    with patch("app.agents.pipeline.extract_metrics_from_paper", new=fake_extract), \
         patch("app.agents.pipeline.openalex_agent.batch_resolve_countries", new=fake_batch):
        await extract_node(state, db, client)

    by_doi = {p.get("doi"): p for p in seen_papers}
    assert by_doi["10.1/has"]["country"] == "South Korea"
    assert by_doi["10.2/none"]["country"] is None
    assert by_doi["10.2/none"]["country_lookup_done"] is True   # 단건 fallback 차단
    assert by_doi[None]["country"] == "USA"                      # 손대지 않음
