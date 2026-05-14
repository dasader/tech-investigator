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


import httpx  # noqa: E402  (httpx imported here only for AsyncMock spec)


@pytest.fixture
def mock_httpx_client():
    """Build a mock httpx.AsyncClient-shaped object for DI into agent functions.

    Either supply json_body/status_code for a single mocked response,
    or get_side_effect for sequential / exception scenarios.
    """
    def _make(*, status_code: int = 200, json_body=None, get_side_effect=None) -> AsyncMock:
        client = AsyncMock(spec=httpx.AsyncClient)
        if get_side_effect is not None:
            client.get.side_effect = get_side_effect
        else:
            response = MagicMock()
            response.status_code = status_code
            response.json.return_value = json_body if json_body is not None else {}
            response.raise_for_status = MagicMock()
            client.get.return_value = response
        return client
    return _make
