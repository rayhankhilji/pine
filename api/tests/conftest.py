from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pine.config import get_settings
from pine.db import Base, get_session, get_session_factory
from pine.main import create_app


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as s:
        yield s


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
    tmp_path: Path,
) -> Iterator[TestClient]:
    monkeypatch.delenv("PINE_API_KEY", raising=False)
    monkeypatch.setenv("WORKER_ENABLED", "0")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()

    testing_session = session_factory

    def override_get_session() -> Iterator[Session]:
        session = testing_session()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_session_factory] = lambda: session_factory

    test_client = TestClient(app)
    yield test_client
    test_client.close()
    get_settings.cache_clear()
