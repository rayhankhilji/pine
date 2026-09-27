from collections.abc import Callable

from pine.ingest.types import ParseResult

Parser = Callable[[bytes, str], ParseResult]  # (data, filename) -> result


def get_parser(ext: str) -> Parser | None:
    """Return the parser for an extension, or None if unsupported."""
    from pine.ingest import email, image, office, pdf, spreadsheet, text

    parsers: dict[str, Parser] = {
        "pdf": pdf.parse,
        "xlsx": spreadsheet.parse,
        "csv": spreadsheet.parse,
        "tsv": spreadsheet.parse,
        "docx": office.parse_docx,
        "pptx": office.parse_pptx,
        "eml": email.parse,
        "txt": text.parse,
        "md": text.parse,
        "png": image.parse,
        "jpg": image.parse,
        "jpeg": image.parse,
    }
    return parsers.get(ext)
