from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from pine.api.schemas.document import Cell, Table, TableDetail
from pine.db import get_session
from pine.errors import AppError
from pine.models.document import Cell as CellModel
from pine.repos import documents as docs_repo

router = APIRouter(tags=["tables"])


@router.get("/tables/{table_id}")
def get_table(
    table_id: str, session: Annotated[Session, Depends(get_session)]
) -> TableDetail:
    found = docs_repo.table_with_page(session, table_id)
    if found is None:
        raise AppError("NOT_FOUND", "Table not found", status=404)
    table, _page = found
    cells = session.scalars(
        select(CellModel)
        .where(CellModel.table_id == table.id)
        .order_by(CellModel.row, CellModel.col)
    ).all()
    matrix: list[list[Cell | None]] = [
        [None] * table.n_cols for _ in range(table.n_rows)
    ]
    for cell in cells:
        if cell.row < table.n_rows and cell.col < table.n_cols:
            matrix[cell.row][cell.col] = Cell.model_validate(cell)
    return TableDetail(**Table.model_validate(table).model_dump(), cells=matrix)
