import io
import zipfile

from pine.ingest.detect import detect_type, ext_of


def _zip_with(*names: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name in names:
            zf.writestr(name, "x")
    return buf.getvalue()


def test_pdf_by_signature() -> None:
    assert detect_type("mystery.bin", b"%PDF-1.7 rest") == "pdf"


def test_docx_by_zip_member() -> None:
    data = _zip_with("[Content_Types].xml", "word/document.xml")
    assert detect_type("file.zip", data) == "docx"


def test_xlsx_and_pptx() -> None:
    assert (
        detect_type("a.bin", _zip_with("[Content_Types].xml", "xl/workbook.xml"))
        == "xlsx"
    )
    assert (
        detect_type(
            "a.bin", _zip_with("[Content_Types].xml", "ppt/presentation.xml")
        )
        == "pptx"
    )


def test_plain_zip_stays_zip() -> None:
    assert detect_type("a.zip", _zip_with("readme.txt")) == "zip"


def test_png_jpeg_magic() -> None:
    assert detect_type("a.bin", b"\x89PNG\r\n\x1a\n" + b"0" * 20) == "png"
    assert detect_type("a.bin", b"\xff\xd8\xff\xe0" + b"0" * 20) == "jpg"


def test_eml_headers() -> None:
    eml = b"From: a@b.com\nSubject: Hi\n\nbody"
    assert detect_type("note.eml", eml) == "eml"


def test_extension_fallback() -> None:
    assert detect_type("data.csv", b"a,b\n1,2\n") == "csv"
    assert detect_type("notes.md", b"# hi") == "md"


def test_unknown_ext_rejected() -> None:
    assert detect_type("evil.xyz", b"whatever") is None
    assert detect_type("noext", b"\x00\x01\x02binary") is None


def test_ext_of() -> None:
    assert ext_of("Folder/File.PDF") == "pdf"
    assert ext_of("noext") == ""
