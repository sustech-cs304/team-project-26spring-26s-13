"""
backend/utils/document_parser.py
统一文档解析器：将 PDF、PPT/PPTX、Markdown、TXT 转换为纯文本。
对外只暴露 parse_document()，上层不关心文件类型细节。
"""

from dataclasses import dataclass
from pathlib import Path


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
    # TODO:
    # if mime_type == "application/pdf":
    #     return _parse_pdf(file_path)
    # elif "presentation" in mime_type or "powerpoint" in mime_type:
    #     return _parse_pptx(file_path)
    # elif mime_type in ("text/markdown", "text/plain"):
    #     return _parse_text(file_path, mime_type)
    # else:
    #     raise ValueError(f"Unsupported MIME type: {mime_type}")
    raise NotImplementedError


def _parse_pdf(file_path: str) -> ParsedDocument:
    """
    使用 PyMuPDF（fitz）逐页提取文本。
    跳过纯图片页（text 为空的页），合并所有页文本。

    Args:
        file_path: PDF 文件绝对路径

    Returns:
        ParsedDocument
    """
    # TODO:
    # import fitz
    # doc = fitz.open(file_path)
    # pages = [page.get_text() for page in doc]
    # text = "\n\n".join(p for p in pages if p.strip())
    # return ParsedDocument(text=text, page_count=len(doc), file_type="application/pdf")
    raise NotImplementedError


def _parse_pptx(file_path: str) -> ParsedDocument:
    """
    使用 python-pptx 提取每张幻灯片的文本框内容。
    保留幻灯片标题，按顺序拼接。

    Args:
        file_path: PPTX 文件绝对路径

    Returns:
        ParsedDocument
    """
    # TODO:
    # from pptx import Presentation
    # prs = Presentation(file_path)
    # slides_text = []
    # for slide in prs.slides:
    #     slide_texts = [shape.text for shape in slide.shapes if shape.has_text_frame]
    #     slides_text.append("\n".join(slide_texts))
    # return ParsedDocument(text="\n\n".join(slides_text), page_count=len(prs.slides), ...)
    raise NotImplementedError


def _parse_text(file_path: str, mime_type: str) -> ParsedDocument:
    """
    直接读取 Markdown 或纯文本文件内容。

    Args:
        file_path: 文件绝对路径
        mime_type: "text/markdown" 或 "text/plain"

    Returns:
        ParsedDocument
    """
    # TODO:
    # text = Path(file_path).read_text(encoding="utf-8")
    # return ParsedDocument(text=text, page_count=1, file_type=mime_type)
    raise NotImplementedError
