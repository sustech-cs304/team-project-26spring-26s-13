from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from backend.services.schedule_service.constants import logger
from backend.utils.OCR.paddle_ocr import PaddleOcrEngine
from backend.utils.document_parser import parse_document


@dataclass(frozen=True)
class ExtractedCalendarText:
    text: str
    page_count: int


async def extract_calendar_text_from_pdf(pdf_path: Path) -> ExtractedCalendarText:
    if not pdf_path.exists():
        raise FileNotFoundError(str(pdf_path))

    def _work() -> ExtractedCalendarText:
        suffix = pdf_path.suffix.lower()
        if suffix == ".pdf":
            parsed = parse_document(str(pdf_path), "application/pdf")
            return ExtractedCalendarText(text=parsed.text or "", page_count=int(parsed.page_count or 0))
        if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
            from PIL import Image
            import numpy as np

            img = Image.open(pdf_path).convert("RGB")
            arr = np.asarray(img)[:, :, ::-1]
            text = PaddleOcrEngine().ocr_image_array(arr) or ""
            return ExtractedCalendarText(text=text, page_count=1)
        raise ValueError(f"Unsupported calendar asset type: {suffix or '<none>'}")

    logger.info("calendar.extract: start path=%s", pdf_path)
    out = await asyncio.to_thread(_work)
    logger.info("calendar.extract: done pages=%d chars=%d path=%s", out.page_count, len(out.text), pdf_path)
    return out
