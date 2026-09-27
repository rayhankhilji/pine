from pine.ingest.email import parse
from pine.ingest.text import parse as parse_text


def test_eml_body_and_attachment(eml_with_attachment: bytes) -> None:
    result = parse(eml_with_attachment, "email.eml")
    assert "Financials attached" in result.pages[0].text
    assert "cfo@northwind.example" in result.pages[0].text
    assert len(result.attachments) == 1
    assert result.attachments[0].filename == "02_Financials_summary.pdf"
    assert result.attachments[0].data[:5] == b"%PDF-"
    assert result.doc_date is not None
    assert result.meta["from"] == "cfo@northwind.example"


def test_txt() -> None:
    result = parse_text(b"# Title\n\nSome prose here.", "notes.md")
    page = result.pages[0]
    kinds = [b.kind.value for b in page.blocks]
    assert "heading" in kinds and "paragraph" in kinds
