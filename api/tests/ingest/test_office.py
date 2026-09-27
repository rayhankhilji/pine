from pine.ingest.office import parse_docx, parse_pptx
from pine.models.document import BlockKind


def test_docx(docx_file: bytes) -> None:
    result = parse_docx(docx_file, "agreement.docx")
    assert len(result.pages) == 1
    page = result.pages[0]
    assert "between the parties" in page.text
    headings = [b for b in page.blocks if b.kind == BlockKind.heading]
    assert headings and headings[0].text == "Service Agreement"


def test_pptx(pptx_file: bytes) -> None:
    result = parse_pptx(pptx_file, "deck.pptx")
    assert len(result.pages) == 2
    assert result.pages[0].text.find("Northwind Series B") >= 0
    assert "$12.0M" in result.pages[1].text
