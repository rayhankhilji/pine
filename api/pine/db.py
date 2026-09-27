from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from pine.config import get_settings


class Base(DeclarativeBase):
    pass


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def _make_engine(url: str) -> Engine:
    """Engine with sqlite pragmas for concurrent API/worker access."""
    kwargs: dict[str, object] = {}
    if _is_sqlite(url):
        # busy timeout: writers wait instead of erroring under concurrency;
        # check_same_thread=False: sessions may cross worker threads.
        kwargs["connect_args"] = {"timeout": 30, "check_same_thread": False}
    return create_engine(url, **kwargs)


engine = _make_engine(get_settings().DATABASE_URL)

if _is_sqlite(str(engine.url)):

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn: object, _record: object) -> None:
        cursor = dbapi_conn.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    @event.listens_for(engine, "begin")
    def _sqlite_begin_immediate(conn: object) -> None:
        # Deferred transactions that upgrade to writes fail instantly with
        # SQLITE_BUSY_SNAPSHOT (busy_timeout does not apply). BEGIN IMMEDIATE
        # acquires the write lock up front so writers queue on busy_timeout.
        conn.exec_driver_sql("BEGIN IMMEDIATE")  # type: ignore[attr-defined]


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_session_factory() -> sessionmaker[Session]:
    """Dependency for long-lived consumers (SSE) that open their own sessions."""
    return SessionLocal
