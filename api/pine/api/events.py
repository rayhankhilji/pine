"""Deal-scoped SSE stream: document.status + index.status events (§5)."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session, sessionmaker
from sse_starlette.sse import EventSourceResponse

from pine.db import get_session_factory
from pine.errors import AppError
from pine.index.status import index_status
from pine.repos import deals as deals_repo
from pine.repos import documents as docs_repo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/deals", tags=["events"])

POLL_SECONDS = 1.0
HEARTBEAT_SECONDS = 15.0


def _snapshot(
    factory: sessionmaker[Session], deal_id: str
) -> tuple[dict[str, str], dict[str, Any]]:
    """One DB poll: document statuses + index status for the deal."""
    with factory() as session:
        return (
            docs_repo.document_statuses(session, deal_id),
            index_status(session, deal_id),
        )


@router.get("/{deal_id}/events")
async def deal_events(
    deal_id: str,
    request: Request,
    factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> EventSourceResponse:
    with factory() as session:
        if deals_repo.get_deal(session, deal_id) is None:
            raise AppError("NOT_FOUND", "Deal not found", status=404)

    async def stream() -> AsyncIterator[dict[str, str]]:
        last_docs: dict[str, str] = {}
        last_index: dict[str, Any] | None = None
        last_beat = asyncio.get_running_loop().time()
        while True:
            if await request.is_disconnected():
                break
            docs, index = await asyncio.to_thread(_snapshot, factory, deal_id)
            for doc_id, status in docs.items():
                if last_docs.get(doc_id) != status:
                    yield {
                        "event": "document.status",
                        "data": json.dumps(
                            {"document_id": doc_id, "status": status}
                        ),
                    }
            last_docs = docs
            if index != last_index:
                yield {"event": "index.status", "data": json.dumps(index)}
                last_index = index
            now = asyncio.get_running_loop().time()
            if now - last_beat >= HEARTBEAT_SECONDS:
                yield {"event": "heartbeat", "data": "{}"}
                last_beat = now
            await asyncio.sleep(POLL_SECONDS)

    return EventSourceResponse(stream())
