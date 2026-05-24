"""
backend/utils/document_parser.py
统一文档解析器：将 PDF、图片、DOCX、PPT/PPTX、Markdown、TXT 转换为纯文本。
对外只暴露 parse_document()，上层不关心文件类型细节。
"""

from dataclasses import dataclass
import io
import logging
from pathlib import Path
import re

try:
    from backend.services.schedule_service.log_utils import (
        _ensure_file_logging,
        _trace_filter,
    )

    _ensure_file_logging()
except Exception:
    pass

logger = logging.getLogger(__name__)
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setLevel(logging.DEBUG)
    _h.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(funcName)s:%(lineno)d | %(message)s"
        )
    )
    logger.addHandler(_h)
    logger.setLevel(logging.DEBUG)


def _try_get_trace() -> str:
    try:
        from backend.services.schedule_service.log_utils import get_trace_id

        return get_trace_id()
    except Exception:
        return "-"


@dataclass
class ParsedDocument:
    """解析结果，携带原始元信息便于后续处理。"""

    text: str  # 提取的完整纯文本（已去除多余空行）
    page_count: int  # PDF 页数 / PPT 幻灯片数（TXT/MD 为 1）
    file_type: str  # MIME type


def parse_document(file_path: str, mime_type: str) -> ParsedDocument:
    """
    根据 MIME 类型选择对应解析器，提取文件全文。

    Args:
        file_path: 文件的绝对路径
        mime_type: 文件 MIME 类型，支持：
                   "application/pdf"
                   "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                   "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                   "application/vnd.ms-powerpoint"
                   "image/png"
                   "image/jpeg"
                   "image/webp"
                   "text/markdown"
                   "text/plain"

    Returns:
        ParsedDocument

    Raises:
        ValueError: 不支持的 MIME 类型
        IOError:    文件不可读
    """
    import time as _ptime

    _p0 = _ptime.monotonic()
    file_size = 0
    try:
        file_size = Path(file_path).stat().st_size
    except Exception:
        pass
    logger.info(
        "doc: parse_start file=%s mime=%s size=%d trace=%s",
        file_path,
        mime_type,
        file_size,
        _try_get_trace(),
    )
    result: ParsedDocument
    if mime_type == "application/pdf":
        result = _parse_pdf(file_path)
    elif (
        mime_type
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ):
        result = _parse_docx(file_path)
    elif "presentation" in mime_type or "powerpoint" in mime_type:
        result = _parse_pptx(file_path)
    elif mime_type in ("image/png", "image/jpeg", "image/webp"):
        result = _parse_image(file_path, mime_type)
    elif mime_type in (
        "application/msword",
        "application/vnd.ms-word",
    ):
        result = _parse_doc(file_path)
    elif mime_type in (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "text/csv",
    ):
        result = _parse_text(file_path, "text/plain")
    elif mime_type in ("text/markdown", "text/plain"):
        result = _parse_text(file_path, mime_type)
    else:
        raise ValueError(
            f"Unsupported MIME type: {mime_type} "
            f"file={file_path} trace={_try_get_trace()}"
        )
    elapsed = _ptime.monotonic() - _p0
    logger.info(
        "doc: parse_done file=%s mime=%s chars=%d pages=%d elapsed=%.2fs trace=%s",
        file_path,
        mime_type,
        len(result.text),
        result.page_count,
        elapsed,
        _try_get_trace(),
    )
    return result


def _parse_pdf(file_path: str) -> ParsedDocument:
    """
    使用 PyMuPDF（fitz）逐页提取文本。
    跳过纯图片页（text 为空的页），合并所有页文本。

    Args:
        file_path: PDF 文件绝对路径

    Returns:
        ParsedDocument
    """
    import fitz  # type: ignore[import-not-found]

    ocr_engine = None
    ocr_disabled = False

    doc = fitz.open(file_path)
    pages_text: list[str] = []
    for page in doc:
        t = (page.get_text("text") or "").strip()
        if len(t) >= 20:
            pages_text.append(t)
            continue

        if ocr_disabled:
            continue

        if ocr_engine is None:
            try:
                from backend.utils.OCR.paddle_ocr import PaddleOcrEngine

                ocr_engine = PaddleOcrEngine()
            except Exception:
                logger.exception(
                    "doc: ocr_init_failed file=%s trace=%s",
                    file_path,
                    _try_get_trace(),
                )
                ocr_disabled = True
                continue

        mat = fitz.Matrix(2, 2)
        pix = page.get_pixmap(matrix=mat, alpha=False)

        try:
            import numpy as np  # type: ignore[import-not-found]
        except Exception:
            continue

        channels = 3
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            (pix.height, pix.width, channels)
        )
        img = img[:, :, ::-1]
        ocr_t = (ocr_engine.ocr_image_array(img) or "").strip()
        if ocr_t:
            pages_text.append(ocr_t)

    text = _normalize_text("\n\n".join(pages_text))
    return ParsedDocument(text=text, page_count=len(doc), file_type="application/pdf")


def _parse_pptx(file_path: str) -> ParsedDocument:
    """
    使用 python-pptx 提取每张幻灯片的文本框内容。
    保留幻灯片标题，按顺序拼接。

    Args:
        file_path: PPTX 文件绝对路径

    Returns:
        ParsedDocument
    """
    from pptx import Presentation  # type: ignore[import-not-found]

    prs = Presentation(file_path)
    slides_text: list[str] = []
    for index, slide in enumerate(prs.slides, start=1):
        slide_texts: list[str] = []
        for shape in slide.shapes:
            slide_texts.extend(_extract_pptx_shape_texts(shape))
        slide_texts.extend(_extract_pptx_notes_text(slide))
        if slide_texts:
            block = "\n".join(slide_texts).strip()
            if block:
                slides_text.append(f"[Slide {index}]\n{block}")

    text = _normalize_text("\n\n".join(slides_text))
    return ParsedDocument(
        text=text,
        page_count=len(prs.slides),
        file_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )


def _parse_docx(file_path: str) -> ParsedDocument:
    from docx import Document  # type: ignore[import-not-found]

    doc = Document(file_path)
    blocks: list[str] = []

    for para in doc.paragraphs:
        txt = str(para.text or "").strip()
        if txt:
            blocks.append(txt)

    for table in doc.tables:
        rows: list[str] = []
        for row in table.rows:
            cells = [str(cell.text or "").strip() for cell in row.cells]
            cells = [cell for cell in cells if cell]
            if cells:
                rows.append(" | ".join(cells))
        if rows:
            blocks.append("\n".join(rows))

    text = _normalize_text("\n\n".join(blocks))
    return ParsedDocument(
        text=text,
        page_count=max(1, len(blocks) or len(doc.paragraphs) or len(doc.tables) or 1),
        file_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


def _parse_doc(file_path: str) -> ParsedDocument:
    """
    Attempt to parse .doc (OLE2) files.
    First tries docx path (many .doc files are actually mislabeled .docx).
    Falls back to plain text read.
    """
    try:
        return _parse_docx(file_path)
    except Exception:
        pass
    return _parse_text(file_path, "text/plain")


def _parse_image(file_path: str, mime_type: str) -> ParsedDocument:
    from PIL import Image  # type: ignore[import-not-found]

    with Image.open(file_path) as img:
        text = _ocr_pil_image(img.convert("RGB"))
    return ParsedDocument(text=_normalize_text(text), page_count=1, file_type=mime_type)


def _parse_text(file_path: str, mime_type: str) -> ParsedDocument:
    """
    直接读取 Markdown 或纯文本文件内容。

    Args:
        file_path: 文件绝对路径
        mime_type: "text/markdown" 或 "text/plain"

    Returns:
        ParsedDocument
    """
    text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
    return ParsedDocument(text=_normalize_text(text), page_count=1, file_type=mime_type)


def _extract_pptx_shape_texts(shape) -> list[str]:
    texts: list[str] = []

    if getattr(shape, "has_text_frame", False):
        txt = str(getattr(shape, "text", "") or "").strip()
        if txt:
            texts.append(txt)

    if getattr(shape, "has_table", False):
        table = getattr(shape, "table", None)
        if table is not None:
            for row in table.rows:
                cells = [str(cell.text or "").strip() for cell in row.cells]
                cells = [cell for cell in cells if cell]
                if cells:
                    texts.append(" | ".join(cells))

    image = getattr(shape, "image", None)
    blob = getattr(image, "blob", None)
    if isinstance(blob, (bytes, bytearray)) and blob:
        ocr_text = _ocr_image_bytes(bytes(blob))
        if ocr_text:
            texts.append(ocr_text)

    return texts


def _extract_pptx_notes_text(slide) -> list[str]:
    texts: list[str] = []
    notes_slide = getattr(slide, "notes_slide", None)
    if notes_slide is None:
        return texts
    for shape in getattr(notes_slide, "shapes", []):
        if not getattr(shape, "has_text_frame", False):
            continue
        txt = str(getattr(shape, "text", "") or "").strip()
        if txt:
            texts.append(f"[Notes]\n{txt}")
    return texts


def _ocr_image_bytes(blob: bytes) -> str:
    from PIL import Image  # type: ignore[import-not-found]

    with Image.open(io.BytesIO(blob)) as img:
        return _ocr_pil_image(img.convert("RGB"))


def _ocr_pil_image(img) -> str:
    try:
        from backend.utils.OCR.paddle_ocr import PaddleOcrEngine
        import numpy as np  # type: ignore[import-not-found]
    except Exception:
        return ""

    arr = np.asarray(img)[:, :, ::-1]
    try:
        return (PaddleOcrEngine().ocr_image_array(arr) or "").strip()
    except Exception:
        logger.exception("doc: ocr_failed trace=%s", _try_get_trace())
        return ""


def _normalize_text(text: str) -> str:
    s = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    s = "\n".join(line.rstrip() for line in s.split("\n"))
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()
