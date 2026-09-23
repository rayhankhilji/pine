from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pine.config import get_settings
from pine.db import Base, get_session
from pine.main import create_app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.delenv("PINE_API_KEY", raising=False)
    monkeypatch.setenv("WORKER_ENABLED", "0")
    get_settings.cache_clear()

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    app = create_app()
    app.dependency_overrides[get_session] = lambda: iter(testing_session())

    test_client = TestClient(app)
    yield test_client
    test_client.close()
    get_settings.cache_clear()
