import hashlib
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pine.db import Base
from pine.models.document import Blob
from pine.storage.blobstore import BlobStore


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as s:
        yield s
    engine.dispose()


def test_put_and_get(session: Session, tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = BlobStore(tmp_path)
    blob = store.put(session, b"hello pine", "a.txt")
    session.commit()
    assert blob.sha256 == hashlib.sha256(b"hello pine").hexdigest()
    assert blob.size_bytes == 10
    assert blob.mime == "text/plain"
    assert store.get_bytes(blob) == b"hello pine"


def test_dedupe_same_content(session: Session, tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = BlobStore(tmp_path)
    a = store.put(session, b"same bytes", "a.bin")
    b = store.put(session, b"same bytes", "b.bin")
    session.commit()
    assert a.id == b.id
    assert session.scalars(select(Blob)).all().__len__() == 1


def test_paths_sharded(session: Session, tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = BlobStore(tmp_path)
    blob = store.put(session, b"x", "x.bin")
    assert blob.path.startswith(blob.sha256[:2] + "/")
    assert store.path_for(blob).exists()
