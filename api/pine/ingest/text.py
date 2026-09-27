from pine.ingest.types import ParsedBlock, ParsedPage, ParseResult
from pine.models.document import BlockKind


def parse(data: bytes, filename: str) -> ParseResult:
    text = data.decode("utf-8", errors="replace")
    blocks: list[ParsedBlock] = []
    cursor = 0
    order = 0
    for para in text.split("\n\n"):
        para = para.strip("\n")
        if not para.strip():
            continue
        kind = (
            BlockKind.heading
            if para.lstrip().startswith("#")
            else BlockKind.paragraph
        )
        blocks.append(
            ParsedBlock(
                order=order,
                kind=kind,
                text=para,
                char_start=cursor,
                char_end=cursor + len(para),
            )
        )
        cursor += len(para) + 1
        order += 1
    page = ParsedPage(page_no=1, width=0, height=0, text=text, blocks=blocks)
    return ParseResult(pages=[page])
