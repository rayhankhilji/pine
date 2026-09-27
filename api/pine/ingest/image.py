import io

from pine.ingest.ocr import ocr_image_bytes
from pine.ingest.types import ParsedBlock, ParsedPage, ParseResult
from pine.models.document import BlockKind


def parse(data: bytes, filename: str) -> ParseResult:
    width = height = 0
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as img:
            width, height = img.size
    except ImportError:
        pass

    ocr_text = ocr_image_bytes(data)
    blocks: list[ParsedBlock] = []
    if ocr_text:
        blocks.append(
            ParsedBlock(
                order=0, kind=BlockKind.paragraph, text=ocr_text,
                char_start=0, char_end=len(ocr_text),
            )
        )
    meta = {"ocr_skipped": True} if ocr_text is None else {}
    page = ParsedPage(
        page_no=1,
        width=width,
        height=height,
        is_scanned=True,
        text=ocr_text or "",
        blocks=blocks,
    )
    return ParseResult(pages=[page], meta=meta)
