import hashlib
import mimetypes
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from pine.models.document import Blob


class BlobStore:
    """Content-addressed blob storage under STORAGE_DIR (sha256 paths)."""

    def __init__(self, storage_dir: str | Path) -> None:
        self.root = Path(storage_dir)

    def _path_for(self, sha256: str) -> Path:
        return self.root / sha256[:2] / sha256[2:]

    def put(
        self, session: Session, data: bytes, filename: str = ""
    ) -> Blob:
        sha256 = hashlib.sha256(data).hexdigest()
        blob = session.scalar(select(Blob).where(Blob.sha256 == sha256))
        if blob is not None:
            return blob
        path = self._path_for(sha256)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        mime = (
            mimetypes.guess_type(filename)[0] or "application/octet-stream"
        )
        blob = Blob(
            sha256=sha256,
            size_bytes=len(data),
            mime=mime,
            path=str(path.relative_to(self.root)),
        )
        session.add(blob)
        session.flush()
        return blob

    def get_bytes(self, blob: Blob) -> bytes:
        return (self.root / blob.path).read_bytes()

    def path_for(self, blob: Blob) -> Path:
        return self.root / blob.path
