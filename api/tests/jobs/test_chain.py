"""Full ingest→index→extract→graph→contradictions chain on the demo room.

The demo room is ingested against the in-memory DB and every queued job is
drained via the real `Worker.run_once` loop — parse, classify, index,
extract_facts, build_graph and the detect_contradictions stub all chain via
enqueue calls inside each handler.
"""

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import pine.contradictions.jobs  # noqa: F401 — registers detect_contradictions
import pine.facts.jobs  # noqa: F401 — registers extract_facts
import pine.graph.jobs  # noqa: F401 — registers build_graph
import pine.index.jobs  # noqa: F401 — registers index_deal
import pine.ingest.jobs  # noqa: F401 — registers parse/classify
from pine.config import get_settings
from pine.demo.build import build_demo
from pine.jobs.worker import Worker
from pine.models.entity import Entity
from pine.models.fact import Fact
from pine.models.job import Job
from pine.services.uploads import ingest_upload
from pine.storage.blobstore import BlobStore
from tests.facts.conftest import mk_deal

if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker


async def _drain(
    session_factory: "sessionmaker[Session]", max_rounds: int = 300
) -> None:
    worker = Worker(session_factory, concurrency=1)
    for _ in range(max_rounds):
        if await worker.run_once() == 0:
            return
    raise AssertionError("job queue did not drain")


async def test_ingest_chain_end_to_end(
    session: Session,
    session_factory: "sessionmaker[Session]",
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    room = build_demo(tmp_path / "room")
    deal = mk_deal(session, "Northwind")
    store = BlobStore(tmp_path / "storage")
    files: list[tuple[str, bytes]] = []
    paths: list[str] = []
    for path in sorted(room.rglob("*")):
        if not path.is_file() or path.name == "ground_truth.json":
            continue
        files.append((path.name, path.read_bytes()))
        paths.append(path.relative_to(room).as_posix())
    ingest_upload(session, store, deal, files, paths)

    await _drain(session_factory)

    # every job in the chain ran and succeeded
    rows = session.execute(
        select(Job.kind, Job.status, Job.error).where(Job.deal_id == deal.id)
    ).all()
    by_kind: dict[str, list[tuple[str, str | None]]] = {}
    for kind, status, error in rows:
        by_kind.setdefault(str(kind), []).append((str(status), error))
    for kind in (
        "parse_document",
        "classify_document",
        "index_deal",
        "extract_facts",
        "build_graph",
        "detect_contradictions",
    ):
        assert kind in by_kind, f"missing job kind {kind}"
        assert all(s == "succeeded" for s, _ in by_kind[kind]), by_kind[kind]

    # facts exist (tables + llm prose + derived)
    facts = session.scalar(
        select(func.count()).select_from(Fact).where(Fact.deal_id == deal.id)
    )
    assert facts and facts > 0

    # ≥ 20 live customer entities, all under the company via has_customer
    customers = session.scalar(
        select(func.count())
        .select_from(Entity)
        .where(Entity.deal_id == deal.id)
        .where(Entity.type == "customer")
        .where(Entity.merged_into_id.is_(None))
    )
    assert customers and customers >= 20
