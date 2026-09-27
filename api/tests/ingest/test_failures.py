import zipfile

import pytest

from pine.ingest.pdf import parse
from pine.ingest.spreadsheet import parse as parse_sheet


def test_corrupt_pdf_raises() -> None:
    # pymupdf raises FileDataError (a RuntimeError subclass) on bad input
    with pytest.raises(RuntimeError):
        parse(b"%PDF-1.7 but actually garbage", "broken.pdf")


def test_corrupt_xlsx_raises() -> None:
    with pytest.raises(zipfile.BadZipFile):
        parse_sheet(b"not a zip at all", "bad.xlsx")
