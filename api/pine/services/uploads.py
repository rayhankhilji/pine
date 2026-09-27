"""Upload ingestion service: multipart files, zip expansion, dedupe, enqueue.

ARCHITECTURE §5/§11 guards:
- per-file cap MAX_FILE_MB (direct uploads -> 413 FILE_TOO_LARGE; zip members
  are skipped and reported instead)
- zip-bomb guards: max 5 000 members, 2 GB expanded total, no path traversal
- __MACOSX/ and dotfiles are skipped and reported
- sha256 dedupe: identical content shares one Blob; identical
  (deal, blob, path) is skipped as a duplicate
- deal quota MAX_DEAL_GB -> 413 DEAL_QUOTA_EXCEEDED
"""

import hashlib
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import PurePosixPath

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pine.api.schemas.document import SkippedFile
from pine.config import get_settings
from pine.errors import AppError
from pine.ingest.detect import detect_type, ext_of, mime_for
from pine.ingest.registry import get_parser
from pine.jobs.queue import enqueue
from pine.models.deal import Deal
from pine.models.document import Blob, DocStatus, Document
from pine.models.job import JobKind
from pine.storage.blobstore import BlobStore

MAX_ZIP_MEMBERS = 5000


@dataclass
class UploadItem:
    path: str
    filename: str
    data: bytes


@dataclass
class UploadResult:
    documents: list[Document] = field(default_factory=list)
    skipped: list[SkippedFile] = field(default_factory=list)


def _safe_member_name(name: str) -> str | None:
    """Normalise a zip member path; None if it escapes the archive root."""
    if not name or name.startswith(("/", "\\")):
        return None
    norm = str(PurePosixPath(name.replace("\\", "/")))
    parts = PurePosixPath(norm).parts
    if not parts or ".." in parts:
        return None
    return norm


def _is_junk(path: str) -> bool:
    parts = PurePosixPath(path).parts
    return "__MACOSX" in parts or parts[-1].startswith(".")


def _expand_zip(data: bytes, result: UploadResult, max_file_bytes: int) -> list[UploadItem]:
    max_deal_bytes = get_settings().MAX_DEAL_GB * 1024**3
    try:
        zf = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise AppError(
            "VALIDATION", "Uploaded zip archive is corrupt", status=422
        ) from exc
    with zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        if len(infos) > MAX_ZIP_MEMBERS:
            raise AppError(
                "DEAL_QUOTA_EXCEEDED",
                f"Zip archive has more than {MAX_ZIP_MEMBERS} members",
                status=413,
            )
        total = sum(i.file_size for i in infos)
        if total > max_deal_bytes:
            raise AppError(
                "DEAL_QUOTA_EXCEEDED",
                "Zip archive expands beyond the 2 GB limit",
                status=413,
            )
        items: list[UploadItem] = []
        for info in infos:
            path = _safe_member_name(info.filename)
            if path is None:
                result.skipped.append(
                    SkippedFile(filename=info.filename, reason="unsafe path")
                )
                continue
            if _is_junk(path):
                result.skipped.append(
                    SkippedFile(filename=info.filename, reason="system file")
                )
                continue
            if info.file_size > max_file_bytes:
                result.skipped.append(
                    SkippedFile(filename=info.filename, reason="file too large")
                )
                continue
            items.append(
                UploadItem(
                    path=path,
                    filename=PurePosixPath(path).name,
                    data=zf.read(info),
                )
            )
        return items


def _deal_bytes(session: Session, deal_id: str) -> int:
    """Total bytes already stored under this deal (distinct blobs)."""
    total = session.scalar(
        select(func.coalesce(func.sum(Blob.size_bytes), 0))
        .select_from(Blob)
        .join(Document, Document.blob_id == Blob.id)
        .where(Document.deal_id == deal_id)
    )
    return int(total or 0)


def ingest_upload(
    session: Session,
    store: BlobStore,
    deal: Deal,
    files: list[tuple[str, bytes]],
    paths: list[str] | None = None,
) -> UploadResult:
    """Store uploaded files (expanding zips) as Documents; enqueue parsing."""
    settings = get_settings()
    max_file_bytes = settings.MAX_FILE_MB * 1024**2
    max_deal_bytes = settings.MAX_DEAL_GB * 1024**3

    result = UploadResult()
    items: list[UploadItem] = []
    for i, (filename, data) in enumerate(files):
        if len(data) > max_file_bytes:
            raise AppError(
                "FILE_TOO_LARGE",
                f"{filename} exceeds the {settings.MAX_FILE_MB} MB file limit",
                status=413,
            )
        if detect_type(filename, data) == "zip":
            items.extend(_expand_zip(data, result, max_file_bytes))
        else:
            path = paths[i] if paths and i < len(paths) and paths[i] else filename
            safe = _safe_member_name(path)
            if safe is None:
                result.skipped.append(
                    SkippedFile(filename=filename, reason="unsafe path")
                )
                continue
            items.append(UploadItem(path=safe, filename=PurePosixPath(safe).name, data=data))

    # deal quota: bytes already stored + bytes of new (unique) blobs
    existing_sha = {
        row
        for row in session.scalars(
            select(Blob.sha256)
            .join(Document, Document.blob_id == Blob.id)
            .where(Document.deal_id == deal.id)
        )
    }
    new_bytes = 0
    seen_new: set[str] = set()
    for item in items:
        sha = hashlib.sha256(item.data).hexdigest()
        if sha in existing_sha or sha in seen_new:
            continue
        seen_new.add(sha)
        new_bytes += len(item.data)
    if _deal_bytes(session, deal.id) + new_bytes > max_deal_bytes:
        raise AppError(
            "DEAL_QUOTA_EXCEEDED",
            f"Deal storage exceeds the {settings.MAX_DEAL_GB} GB quota",
            status=413,
        )

    for item in items:
        ext = detect_type(item.filename, item.data)
        blob = store.put(session, item.data, item.filename)
        existing = session.scalar(
            select(Document)
            .where(Document.deal_id == deal.id)
            .where(Document.blob_id == blob.id)
            .where(Document.path == item.path)
        )
        if existing is not None:
            result.skipped.append(
                SkippedFile(filename=item.filename, reason="duplicate")
            )
            continue

        final_ext = ext or ext_of(item.filename) or "bin"
        blob.mime = mime_for(final_ext) if ext else blob.mime
        supported = ext is not None and get_parser(ext) is not None
        doc = Document(
            deal_id=deal.id,
            blob_id=blob.id,
            filename=item.filename,
            path=item.path,
            ext=final_ext,
            status=DocStatus.queued if supported else DocStatus.unsupported,
        )
        session.add(doc)
        session.flush()
        result.documents.append(doc)
        if supported:
            enqueue(
                session,
                JobKind.parse_document,
                {"document_id": doc.id},
                deal_id=deal.id,
                idempotency_key=f"parse:{doc.id}",
            )
    session.commit()
    return result
