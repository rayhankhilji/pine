import base64
from datetime import UTC, datetime

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from pine.api.schemas.deal import DealCreate, DealUpdate
from pine.models.deal import Deal


def create_deal(session: Session, data: DealCreate) -> Deal:
    deal = Deal(**data.model_dump())
    session.add(deal)
    session.commit()
    session.refresh(deal)
    return deal


def get_deal(session: Session, deal_id: str) -> Deal | None:
    return session.scalar(
        select(Deal).where(Deal.id == deal_id, Deal.deleted_at.is_(None))
    )


def _encode_cursor(deal: Deal) -> str:
    raw = f"{deal.created_at.isoformat()}|{deal.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, str] | None:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        created_at, deal_id = raw.rsplit("|", 1)
        return datetime.fromisoformat(created_at), deal_id
    except (ValueError, IndexError):
        return None


def _keyset(stmt: Select[tuple[Deal]], cursor: str | None) -> Select[tuple[Deal]]:
    if not cursor:
        return stmt
    decoded = _decode_cursor(cursor)
    if decoded is None:
        return stmt
    created_at, deal_id = decoded
    return stmt.where(
        or_(
            Deal.created_at > created_at,
            (Deal.created_at == created_at) & (Deal.id > deal_id),
        )
    )


def list_deals(
    session: Session, cursor: str | None = None, limit: int = 50
) -> tuple[list[Deal], str | None]:
    stmt = select(Deal).where(Deal.deleted_at.is_(None)).order_by(
        Deal.created_at, Deal.id
    )
    stmt = _keyset(stmt, cursor).limit(limit + 1)
    items = list(session.scalars(stmt).all())
    next_cursor = _encode_cursor(items[limit - 1]) if len(items) > limit else None
    return items[:limit], next_cursor


def update_deal(session: Session, deal: Deal, data: DealUpdate) -> Deal:
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(deal, key, value)
    session.commit()
    session.refresh(deal)
    return deal


def soft_delete_deal(session: Session, deal: Deal) -> None:
    deal.deleted_at = datetime.now(UTC)
    session.commit()
