import shutil
from functools import lru_cache

from pine.config import get_settings


@lru_cache
def tesseract_available() -> bool:
    """True when OCR is enabled and the tesseract binary exists."""
    settings = get_settings()
    if not settings.OCR_ENABLED:
        return False
    cmd = settings.TESSERACT_CMD or "tesseract"
    return shutil.which(cmd) is not None


def ocr_image_bytes(data: bytes, lang: str = "eng") -> str | None:
    """OCR raw image bytes; None when unavailable."""
    if not tesseract_available():
        return None
    import io

    import pytesseract
    from PIL import Image

    settings = get_settings()
    if settings.TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
    image = Image.open(io.BytesIO(data))
    return str(pytesseract.image_to_string(image, lang=lang))


def ocr_pdf_page(page: object, lang: str = "eng") -> str | None:
    """OCR a PyMuPDF page by rendering to PNG bytes first."""
    if not tesseract_available():
        return None
    pix = page.get_pixmap(dpi=200)  # type: ignore[attr-defined]
    return ocr_image_bytes(pix.tobytes("png"), lang=lang)
