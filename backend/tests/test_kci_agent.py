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
