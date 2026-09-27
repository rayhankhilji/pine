from sqlalchemy.orm import Session

from pine.ingest.classify import classify_document
from pine.models.deal import Deal
from pine.models.document import DocType, Document, Page


def _doc(
    session: Session, filename: str, ext: str, text: str = ""
) -> Document:
    deal = Deal(name="d", company_name="c")
    session.add(deal)
    session.flush()
    doc = Document(
        deal_id=deal.id,
        blob_id="b1",
        filename=filename,
        path=filename,
        ext=ext,
    )
    session.add(doc)
    session.flush()
    if text:
        session.add(
            Page(document_id=doc.id, page_no=1, width=0, height=0, text=text)
        )
        session.flush()
    return doc


def test_filename_rules(session: Session) -> None:
    doc = _doc(session, "Cap_Table_Final.xlsx", "xlsx")
    assert classify_document(session, doc) == (DocType.cap_table, 0.9)
    doc = _doc(session, "MSA_Acme.pdf", "pdf")
    assert classify_document(session, doc)[0] == DocType.contract
    doc = _doc(session, "Bank_Statement_2025.csv", "csv")
    assert classify_document(session, doc)[0] == DocType.bank_statement
    doc = _doc(session, "Board_Deck_Q4.pdf", "pdf")
    assert classify_document(session, doc)[0] == DocType.board_deck


def test_eml_always_email(session: Session) -> None:
    doc = _doc(session, "random.eml", "eml")
    assert classify_document(session, doc) == (DocType.email, 1.0)


def test_pptx_deck(session: Session) -> None:
    doc = _doc(session, "slides.pptx", "pptx")
    assert classify_document(session, doc)[0] == DocType.deck


def test_content_customer_list(session: Session) -> None:
    doc = _doc(
        session,
        "export.csv",
        "csv",
        "customer,mrr,segment\nAcme,1000,smb\nBeta,2000,mid",
    )
    assert classify_document(session, doc)[0] == DocType.customer_list


def test_content_financial_statement(session: Session) -> None:
    doc = _doc(
        session,
        "numbers.xlsx",
        "xlsx",
        "revenue cogs ebitda gross profit opex",
    )
    assert classify_document(session, doc)[0] == DocType.financial_statement


def test_unknown_empty(session: Session) -> None:
    doc = _doc(session, "mystery.bin", "bin")
    assert classify_document(session, doc) == (DocType.unknown, 0.0)
