"""File type detection: signature bytes first, extension allowlist as fallback."""

import zipfile
from io import BytesIO
from pathlib import PurePosixPath

ALLOWED_EXTS = {
    "pdf", "docx", "pptx", "xlsx", "xls", "csv", "tsv", "txt", "md",
    "eml", "png", "jpg", "jpeg", "zip",
}

_OFFICE_MEMBERS = {
    "word/document.xml": "docx",
    "xl/workbook.xml": "xlsx",
    "ppt/presentation.xml": "pptx",
}

_MIME_BY_EXT = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
    "tsv": "text/tab-separated-values",
    "txt": "text/plain",
    "md": "text/markdown",
    "eml": "message/rfc822",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
}


def ext_of(filename: str) -> str:
    return PurePosixPath(filename).suffix.lstrip(".").lower()


def _sniff_zip(data: bytes) -> str | None:
    try:
        with zipfile.ZipFile(BytesIO(data)) as zf:
            names = set(zf.namelist())
    except zipfile.BadZipFile:
        return None
    if "[Content_Types].xml" not in names:
        return "zip"
    for member, ext in _OFFICE_MEMBERS.items():
        if member in names:
            return ext
    return "zip"


def detect_type(filename: str, data: bytes) -> str | None:
    """Return the detected extension, or None if unrecognised/unsupported."""
    ext = ext_of(filename)

    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:4] == b"PK\x03\x04" or data[:4] == b"PK\x05\x06":
        sniffed = _sniff_zip(data)
        if sniffed is not None:
            return sniffed
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:2] == b"\xff\xd8":
        return "jpg"
    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "xls"  # OLE2 compound (legacy xls/msg)

    head = data[:4096]
    if ext == "eml" and (
        b"\nSubject:" in head or head.startswith(("Subject:", "From:", "Date:"))
    ):
        return "eml"
    if ext in {"csv", "tsv", "txt", "md"}:
        try:
            head.decode("utf-8")
            return ext
        except UnicodeDecodeError:
            pass

    return ext if ext in ALLOWED_EXTS else None


def mime_for(ext: str) -> str:
    return _MIME_BY_EXT.get(ext, "application/octet-stream")
