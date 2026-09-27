import pytest

from pine.ingest.pdf import parse


def test_pdf_table_extracted(pdf_with_table: bytes) -> None:
    result = parse(pdf_with_table, "table_5x4.pdf")
    assert len(result.pages) == 1
    page = result.pages[0]
    assert not page.is_scanned
    assert "Quarterly Revenue Report" in page.text
    assert len(page.tables) == 1
    table = page.tables[0]
    assert table.n_rows == 5
    assert table.n_cols == 4
    texts = {(c.row, c.col): c.text for c in table.cells}
    assert texts[(0, 0)] == "Metric"
    assert texts[(4, 3)] == "30"
    assert texts[(1, 1)] == "100"


def test_pdf_blocks_have_bbox(pdf_with_table: bytes) -> None:
    result = parse(pdf_with_table, "doc.pdf")
    page = result.pages[0]
    assert page.blocks
    assert all(b.bbox is not None and len(b.bbox) == 4 for b in page.blocks)
    assert page.width > 0 and page.height > 0


def test_scanned_detection(
    scanned_pdf: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pine.ingest.pdf as pdf_mod

    monkeypatch.setattr(pdf_mod, "tesseract_available", lambda: False)
    result = parse(scanned_pdf, "scan.pdf")
    page = result.pages[0]
    assert page.is_scanned
    assert result.meta.get("ocr_skipped") is True
