import pytest

from pine.ingest.ocr import ocr_pdf_page
from pine.ingest.pdf import parse


def test_ocr_scanned_page(
    scanned_pdf: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OCR_ENABLED", "1")
    import pine.ingest.ocr as ocr_mod

    ocr_mod.tesseract_available.cache_clear()
    if not ocr_mod.tesseract_available():
        pytest.skip("tesseract binary not installed")

    import pymupdf

    doc = pymupdf.open(stream=scanned_pdf, filetype="pdf")
    text = ocr_pdf_page(doc[0])
    assert text
    words = ["Balance", "confirmation", "December", "USD"]
    found = sum(1 for w in words if w.lower() in text.lower())
    assert found / len(words) >= 0.9


def test_ocr_skipped_when_disabled(
    scanned_pdf: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OCR_ENABLED", "0")
    import pine.ingest.ocr as ocr_mod
    import pine.ingest.pdf as pdf_mod
    from pine.config import get_settings

    get_settings.cache_clear()
    ocr_mod.tesseract_available.cache_clear()
    monkeypatch.setattr(pdf_mod, "tesseract_available", lambda: False)
    result = parse(scanned_pdf, "scan.pdf")
    assert result.meta.get("ocr_skipped") is True
    get_settings.cache_clear()
