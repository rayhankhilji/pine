import io
import logging
from datetime import date

import pymupdf

from pine.ingest.ocr import ocr_pdf_page, tesseract_available
from pine.ingest.types import (
    ParsedBlock,
    ParsedCell,
    ParsedPage,
    ParsedTable,
    ParseResult,
)
from pine.models.document import BlockKind

logger = logging.getLogger(__name__)

SCANNED_TEXT_THRESHOLD = 50
SCANNED_IMAGE_COVERAGE = 0.5


def _is_scanned(page: pymupdf.Page, text: str) -> bool:
    if len(text.strip()) >= SCANNED_TEXT_THRESHOLD:
        return False
    page_area: float = abs(page.rect)
    if page_area <= 0:
        return False
    image_area = 0.0
    for info in page.get_image_info():
        image_area += float(abs(pymupdf.Rect(info["bbox"])))
    return image_area / page_area > SCANNED_IMAGE_COVERAGE


def _tables_for_page(path_data: bytes, page_no: int) -> list[ParsedTable]:
    """pdfplumber tables for one 0-based page index."""
    import pdfplumber

    tables: list[ParsedTable] = []
    with pdfplumber.open(io.BytesIO(path_data)) as pdf:
        if page_no >= len(pdf.pages):
            return tables
        pl_page = pdf.pages[page_no]
        for order, tbl in enumerate(pl_page.extract_tables()):
            if not tbl:
                continue
            n_rows = len(tbl)
            n_cols = max(len(r) for r in tbl)
            cells: list[ParsedCell] = []
            for r, row in enumerate(tbl):
                for c, val in enumerate(row):
                    cells.append(
                        ParsedCell(row=r, col=c, text="" if val is None else str(val))
                    )
            tables.append(
                ParsedTable(order=order, n_rows=n_rows, n_cols=n_cols, cells=cells)
            )
    return tables


def parse(data: bytes, filename: str) -> ParseResult:
    doc = pymupdf.open(stream=data, filetype="pdf")
    pages: list[ParsedPage] = []
    ocr_available = tesseract_available()
    ocr_skipped = False

    for i, page in enumerate(doc):
        raw_text = page.get_text("text")
        scanned = _is_scanned(page, raw_text)
        blocks: list[ParsedBlock] = []
        cursor = 0
        for order, b in enumerate(page.get_text("blocks")):
            x0, y0, x1, y1, btext = b[0], b[1], b[2], b[3], b[4]
            btext = btext.strip()
            if not btext:
                continue
            blocks.append(
                ParsedBlock(
                    order=order,
                    kind=BlockKind.paragraph,
                    text=btext,
                    bbox=[x0, y0, x1, y1],
                    char_start=cursor,
                    char_end=cursor + len(btext),
                )
            )
            cursor += len(btext) + 1

        text = raw_text
        if scanned:
            ocr_text = ocr_pdf_page(page) if ocr_available else None
            if ocr_text:
                text = ocr_text
                scanned = True
            else:
                ocr_skipped = True

        pages.append(
            ParsedPage(
                page_no=i + 1,
                width=page.rect.width,
                height=page.rect.height,
                is_scanned=scanned,
                text=text,
                blocks=blocks,
                tables=_tables_for_page(data, i),
            )
        )

    meta: dict[str, object] = {
        "author": doc.metadata.get("author"),
        "title": doc.metadata.get("title"),
    }
    if ocr_skipped:
        meta["ocr_skipped"] = True
    doc_date: date | None = None
    if raw := doc.metadata.get("creationDate"):
        try:
            doc_date = date.fromisoformat(raw[2:10].replace("'", ""))
        except ValueError:
            doc_date = None
    doc.close()
    return ParseResult(pages=pages, meta=meta, doc_date=doc_date)
