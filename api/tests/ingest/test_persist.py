from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from pine.ingest.persist import persist_result
from pine.ingest.types import (
    Attachment,
    ParsedBlock,
    ParsedCell,
    ParsedPage,
    ParsedTable,
    ParseResult,
)
from pine.models.deal import Deal
from pine.models.document import Block as BlockModel
from pine.models.document import (
    BlockKind,
    Cell,
    Document,
    Page,
    Table,
)
from pine.models.job import Job, JobKind
from pine.storage.blobstore import BlobStore


def _deal(session: Session) -> Deal:
    deal = Deal(name="d", company_name="c")
    session.add(deal)
    session.flush()
    return deal


def _document(
    session: Session, deal: Deal, tmp_path: Path, data: bytes = b"x"
) -> Document:
    store = BlobStore(tmp_path)
    blob = store.put(session, data, "f.bin")
    doc = Document(
        deal_id=deal.id, blob_id=blob.id, filename="f.bin", path="f.bin", ext="bin"
    )
    session.add(doc)
    session.flush()
    return doc


def test_persist_writes_rows(session: Session, tmp_path: Path) -> None:
    deal = _deal(session)
    doc = _document(session, deal, tmp_path)
    result = ParseResult(
        pages=[
            ParsedPage(
                page_no=1,
                width=612,
                height=792,
                text="hello world",
                blocks=[
                    ParsedBlock(
                        order=0,
                        kind=BlockKind.paragraph,
                        text="hello world",
                        char_start=0,
                        char_end=11,
                    )
                ],
                tables=[
                    ParsedTable(
                        order=0,
                        n_rows=2,
                        n_cols=1,
                        cells=[
                            ParsedCell(row=0, col=0, text="h"),
                            ParsedCell(row=1, col=0, text="v"),
                        ],
                    )
                ],
            )
        ],
        meta={"title": "t"},
    )
    persist_result(session, BlobStore(tmp_path), doc, result)
    session.commit()

    page = session.scalar(select(Page).where(Page.document_id == doc.id))
    assert page is not None and page.text == "hello world"
    assert session.scalar(select(BlockModel).where(BlockModel.page_id == page.id))
    table = session.scalar(select(Table).where(Table.page_id == page.id))
    assert table is not None and table.n_rows == 2
    cells = session.scalars(select(Cell).where(Cell.table_id == table.id)).all()
    assert len(cells) == 2
    session.refresh(doc)
    assert doc.page_count == 1
    assert doc.meta["title"] == "t"


def test_attachments_become_child_documents(
    session: Session, tmp_path: Path
) -> None:
    deal = _deal(session)
    doc = _document(session, deal, tmp_path)
    result = ParseResult(
        pages=[ParsedPage(page_no=1, width=0, height=0, text="x")],
        attachments=[Attachment(filename="a.pdf", data=b"%PDF-1.4 fake")],
    )
    persist_result(session, BlobStore(tmp_path), doc, result)
    session.commit()

    child = session.scalar(
        select(Document).where(Document.parent_document_id == doc.id)
    )
    assert child is not None
    assert child.ext == "pdf"
    assert child.deal_id == deal.id
    job = session.scalar(
        select(Job).where(Job.payload["document_id"].as_string() == child.id)
    )
    assert job is not None and job.kind == JobKind.parse_document


def test_registry_maps_known_exts() -> None:
    from pine.ingest import registry

    for ext in ("pdf", "xlsx", "csv", "docx", "pptx", "eml", "txt", "png"):
        assert registry.get_parser(ext) is not None
    assert registry.get_parser("xyz") is None


def test_fake_parser_result_persists(session: Session, tmp_path: Path) -> None:
    """A fake parser's ParseResult round-trips through persist_result."""
    deal = _deal(session)
    doc = _document(session, deal, tmp_path)

    def fake_parser(data: bytes, filename: str) -> ParseResult:
        return ParseResult(
            pages=[ParsedPage(page_no=1, width=0, height=0, text="fake")]
        )

    persist_result(session, BlobStore(tmp_path), doc, fake_parser(b"", doc.filename))
    session.commit()
    page = session.scalar(select(Page).where(Page.document_id == doc.id))
    assert page is not None and page.text == "fake"
