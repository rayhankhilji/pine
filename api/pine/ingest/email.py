import email
import email.policy
from email.utils import parsedate_to_datetime

from pine.ingest.types import Attachment, ParsedBlock, ParsedPage, ParseResult
from pine.models.document import BlockKind


def parse(data: bytes, filename: str) -> ParseResult:
    msg = email.message_from_bytes(data, policy=email.policy.default)
    body_parts: list[str] = []
    attachments: list[Attachment] = []

    for part in msg.walk():
        disp = part.get_content_disposition()
        if disp == "attachment":
            payload = part.get_payload(decode=True)
            fname = part.get_filename() or "attachment.bin"
            if isinstance(payload, bytes) and payload:
                attachments.append(Attachment(filename=fname, data=payload))
        elif part.get_content_type() == "text/plain" and disp != "attachment":
            content = part.get_content()
            if isinstance(content, str) and content.strip():
                body_parts.append(content.strip())

    headers = [
        f"From: {msg.get('From', '')}",
        f"To: {msg.get('To', '')}",
        f"Date: {msg.get('Date', '')}",
        f"Subject: {msg.get('Subject', '')}",
    ]
    blocks = [
        ParsedBlock(order=0, kind=BlockKind.header, text="\n".join(headers)),
    ]
    cursor = len(blocks[0].text) + 1
    for i, body in enumerate(body_parts):
        blocks.append(
            ParsedBlock(
                order=i + 1,
                kind=BlockKind.paragraph,
                text=body,
                char_start=cursor,
                char_end=cursor + len(body),
            )
        )
        cursor += len(body) + 1

    doc_date = None
    if raw_date := msg.get("Date"):
        try:
            doc_date = parsedate_to_datetime(str(raw_date)).date()
        except (TypeError, ValueError):
            doc_date = None

    page = ParsedPage(
        page_no=1,
        width=0,
        height=0,
        text="\n".join(b.text for b in blocks),
        blocks=blocks,
    )
    meta = {
        "from": str(msg.get("From", "")),
        "to": str(msg.get("To", "")),
        "subject": str(msg.get("Subject", "")),
    }
    return ParseResult(pages=[page], meta=meta, doc_date=doc_date, attachments=attachments)
