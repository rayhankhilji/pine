from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Body, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from pine.config import get_settings
from pine.db import get_session
from pine.services.demo import load_demo
from pine.storage.blobstore import BlobStore

router = APIRouter(tags=["demo"])


class DemoRequest(BaseModel):
    name: str | None = None


class DemoResponse(BaseModel):
    deal_id: str
    run_id: str | None


@router.post("/demo", status_code=status.HTTP_202_ACCEPTED)
def create_demo(
    session: Annotated[Session, Depends(get_session)],
    data: Annotated[DemoRequest | None, Body()] = None,
) -> DemoResponse:
    store = BlobStore(Path(get_settings().STORAGE_DIR))
    deal = load_demo(session, store, data.name if data else None)
    return DemoResponse(deal_id=deal.id, run_id=None)
