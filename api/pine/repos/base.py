from typing import Any

from sqlalchemy import Select


def scoped(stmt: Select[Any], model: Any, deal_id: str) -> Select[Any]:
    """Restrict a query to one deal — all deal-scoped access goes through here."""
    return stmt.where(model.deal_id == deal_id)
