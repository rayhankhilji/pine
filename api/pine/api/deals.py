from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from pine.api.schemas.deal import Deal, DealCreate, DealSummary, DealUpdate
from pine.db import get_session
from pine.errors import AppError
from pine.models.deal import Deal as DealModel
from pine.repos import deals as deals_repo

router = APIRouter(prefix="/deals", tags=["deals"])


def _get_or_404(session: Session, deal_id: str) -> DealModel:
    deal = deals_repo.get_deal(session, deal_id)
    if deal is None:
        raise AppError("NOT_FOUND", "Deal not found", status=404)
    return deal


@router.post("", status_code=status.HTTP_201_CREATED)
def create_deal(
    data: DealCreate, session: Annotated[Session, Depends(get_session)]
) -> Deal:
    deal = deals_repo.create_deal(session, data)
    return Deal.model_validate(deal)


@router.get("")
def list_deals(
    session: Annotated[Session, Depends(get_session)],
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, object]:
    items, next_cursor = deals_repo.list_deals(session, cursor=cursor, limit=limit)
    return {
        "items": [
            DealSummary.model_validate(d).model_dump() for d in items
        ],
        "next_cursor": next_cursor,
    }


@router.get("/{deal_id}")
def get_deal(deal_id: str, session: Annotated[Session, Depends(get_session)]) -> Deal:
    return Deal.model_validate(_get_or_404(session, deal_id))


@router.patch("/{deal_id}")
def update_deal(
    deal_id: str,
    data: DealUpdate,
    session: Annotated[Session, Depends(get_session)],
) -> Deal:
    deal = _get_or_404(session, deal_id)
    return Deal.model_validate(deals_repo.update_deal(session, deal, data))


@router.delete("/{deal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deal(
    deal_id: str, session: Annotated[Session, Depends(get_session)]
) -> Response:
    deal = _get_or_404(session, deal_id)
    deals_repo.soft_delete_deal(session, deal)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
