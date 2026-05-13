import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.database import Base, get_db

_db_host = os.environ.get("DB_HOST", "db")
_db_port = os.environ.get("DB_PORT", "5432")
TEST_DB_URL = f"postgresql://techspec:techspec@{_db_host}:{_db_port}/techspec_test"
engine = create_engine(TEST_DB_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(autouse=True)
def setup_db(request):
    # Skip DB setup for tests that don't need it (pure unit tests using mocks)
    if request.node.get_closest_marker("no_db"):
        yield
        return
    try:
        Base.metadata.create_all(bind=engine)
        yield
        Base.metadata.drop_all(bind=engine)
    except Exception:
        yield

@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()

@pytest.fixture
def client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def httpx_mock_get(monkeypatch):
    """Patch httpx.AsyncClient in the given agent module so client.get(...)
    returns a mocked response. Returns the mock_client for call_args inspection.

    Usage:
        client = httpx_mock_get("app.agents.openalex_agent",
                                json_body={"results": [...]})
        # ...run code under test...
        client.get.assert_called_once()
    """
    def _make(module_path: str, *, status_code: int = 200, json_body=None):
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = status_code
        mock_response.json.return_value = json_body if json_body is not None else {}
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        mock_client_class = MagicMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        monkeypatch.setattr(f"{module_path}.httpx.AsyncClient", mock_client_class)
        return mock_client
    return _make
