"""
backend/utils/document_parser.py
统一文档解析器：将 PDF、PPT/PPTX、Markdown、TXT 转换为纯文本。
对外只暴露 parse_document()，上层不关心文件类型细节。
"""

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass
class ParsedDocument:
    """解析结果，携带原始元信息便于后续处理。"""
    text: str           # 提取的完整纯文本（已去除多余空行）
    page_count: int     # PDF 页数 / PPT 幻灯片数（TXT/MD 为 1）
    file_type: str      # MIME type


def parse_document(file_path: str, mime_type: str) -> ParsedDocument:
    """
    根据 MIME 类型选择对应解析器，提取文件全文。

    Args:
        file_path: 文件的绝对路径
        mime_type: 文件 MIME 类型，支持：
                   "application/pdf"
                   "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                   "application/vnd.ms-powerpoint"
                   "text/markdown"
                   "text/plain"

    Returns:
        ParsedDocument

    Raises:
        ValueError: 不支持的 MIME 类型
        IOError:    文件不可读
    """
    if mime_type == "application/pdf":
        return _parse_pdf(file_path)
    if "presentation" in mime_type or "powerpoint" in mime_type:
        return _parse_pptx(file_path)
    if mime_type in ("text/markdown", "text/plain"):
        return _parse_text(file_path, mime_type)
    raise ValueError(f"Unsupported MIME type: {mime_type}")


def _parse_pdf(file_path: str) -> ParsedDocument:
    """
    使用 PyMuPDF（fitz）逐页提取文本。
    跳过纯图片页（text 为空的页），合并所有页文本。

    Args:
        file_path: PDF 文件绝对路径

    Returns:
        ParsedDocument
    """
    from backend.utils.OCR.paddle_ocr import PaddleOcrEngine

    import fitz  # type: ignore[import-not-found]

    ocr_engine: PaddleOcrEngine | None = None

    doc = fitz.open(file_path)
    pages_text: list[str] = []
    for page in doc:
        t = (page.get_text("text") or "").strip()
        if len(t) >= 20:
            pages_text.append(t)
            continue

        if ocr_engine is None:
            ocr_engine = PaddleOcrEngine()

        mat = fitz.Matrix(2, 2)
        pix = page.get_pixmap(matrix=mat, alpha=False)

        import numpy as np  # type: ignore[import-not-found]

        channels = 3
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, channels))
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
    for slide in prs.slides:
        slide_texts: list[str] = []
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False):
                txt = str(getattr(shape, "text", "") or "").strip()
                if txt:
                    slide_texts.append(txt)
        if slide_texts:
            slides_text.append("\n".join(slide_texts))

    text = _normalize_text("\n\n".join(slides_text))
    return ParsedDocument(text=text, page_count=len(prs.slides), file_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")


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


def _normalize_text(text: str) -> str:
    s = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    s = "\n".join(line.rstrip() for line in s.split("\n"))
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()
