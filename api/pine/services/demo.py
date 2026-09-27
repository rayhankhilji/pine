"""Demo data-room loader (F-14): build fixtures, create deal, ingest files."""

from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pine.api.schemas.deal import DealCreate
from pine.config import get_settings
from pine.demo.build import build_demo
from pine.errors import AppError
from pine.models.deal import Deal, DealStage
from pine.models.document import DocStatus, Document
from pine.repos import deals as deals_repo
from pine.services.uploads import ingest_upload
from pine.storage.blobstore import BlobStore

DEMO_DEAL_NAME = "Northwind SaaS — Series B"
DEMO_COMPANY = "Northwind"
NON_TERMINAL = (DocStatus.queued, DocStatus.parsing)


def demo_fixtures_dir() -> Path:
    """Demo room lives under STORAGE_DIR/demo; build once if absent."""
    demo_dir = Path(get_settings().STORAGE_DIR) / "demo"
    if not (demo_dir / "ground_truth.json").exists():
        build_demo(demo_dir, force=True)
    return demo_dir


def demo_ingest_running(session: Session) -> bool:
    """True if a demo-created deal still has queued/parsing documents."""
    count = session.scalar(
        select(func.count())
        .select_from(Document)
        .join(Deal, Document.deal_id == Deal.id)
        .where(Deal.company_name == DEMO_COMPANY)
        .where(Document.status.in_(NON_TERMINAL))
    )
    return bool(count)


def load_demo(session: Session, store: BlobStore, name: str | None) -> Deal:
    """Create the demo deal and ingest the fixture room. 409 if already loading."""
    if demo_ingest_running(session):
        raise AppError(
            "CONFLICT", "A demo ingest is already running", status=409
        )
    deal = deals_repo.create_deal(
        session,
        DealCreate(
            name=name or DEMO_DEAL_NAME,
            company_name=DEMO_COMPANY,
            stage=DealStage.series_b,
            proposed_round_usd=Decimal(25_000_000),
            proposed_pre_money_usd=Decimal(150_000_000),
        ),
    )
    room = demo_fixtures_dir()
    files: list[tuple[str, bytes]] = []
    paths: list[str] = []
    for path in sorted(room.rglob("*")):
        if not path.is_file() or path.name == "ground_truth.json":
            continue
        rel = path.relative_to(room).as_posix()
        files.append((path.name, path.read_bytes()))
        paths.append(rel)
    ingest_upload(session, store, deal, files, paths)
    return deal
