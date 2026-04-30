from __future__ import annotations

from dataclasses import dataclass
import os
import re
import sys
from typing import Any


@dataclass(frozen=True)
class PaddleOcrSettings:
    use_angle_cls: bool = True
    lang: str = "ch"
    det_model_dir: str | None = None
    rec_model_dir: str | None = None
    cls_model_dir: str | None = None
    use_gpu: bool = False


class PaddleOcrEngine:
    def __init__(self, settings: PaddleOcrSettings | None = None) -> None:
        self._settings = settings or _load_settings_from_env()
        self._langs = _split_langs(self._settings.lang)
        self._ocrs = [
            _create_paddle_ocr(_settings_for_lang(self._settings, lang))
            for lang in self._langs
        ]

    def ocr_image_array(self, img: Any) -> str:
        best = ""
        best_score = (-1, -1)
        for ocr in self._ocrs:
            text = _ocr_with_instance(ocr, img, self._settings)
            score = _score_ocr_text(text)
            if score > best_score:
                best = text
                best_score = score
        return best


def _load_settings_from_env() -> PaddleOcrSettings:
    use_angle_cls = (os.getenv("OCR_USE_ANGLE_CLS") or "1").strip() not in (
        "0",
        "false",
        "False",
    )
    use_gpu = (os.getenv("OCR_USE_GPU") or "0").strip() in ("1", "true", "True")
    lang = (os.getenv("OCR_LANG") or "ch").strip() or "ch"

    det_model_dir = (os.getenv("OCR_DET_MODEL_DIR") or "").strip() or None
    rec_model_dir = (os.getenv("OCR_REC_MODEL_DIR") or "").strip() or None
    cls_model_dir = (os.getenv("OCR_CLS_MODEL_DIR") or "").strip() or None

    return PaddleOcrSettings(
        use_angle_cls=use_angle_cls,
        lang=lang,
        det_model_dir=det_model_dir,
        rec_model_dir=rec_model_dir,
        cls_model_dir=cls_model_dir,
        use_gpu=use_gpu,
    )


def _create_paddle_ocr(settings: PaddleOcrSettings):
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    os.environ.setdefault("FLAGS_enable_pir_in_executor", "0")
    os.environ.setdefault("FLAGS_use_pir_api", "0")
    os.environ.setdefault("FLAGS_use_mkldnn", "0")
    os.environ.setdefault("FLAGS_use_onednn", "0")

    try:
        from paddleocr import PaddleOCR  # type: ignore[import-not-found]
    except Exception as exc:
        py = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        raise ModuleNotFoundError(
            "Missing dependency: paddleocr (and paddlepaddle). "
            f"Current Python={py}. "
            "Install with: python -m pip install -r requirements.txt "
            "or create the conda env from Guideline/environment.yml and then pip install paddleocr paddlepaddle."
        ) from exc

    kwargs: dict[str, object] = {
        "use_angle_cls": settings.use_angle_cls,
        "lang": settings.lang,
        "use_gpu": settings.use_gpu,
        "show_log": False,
    }
    if settings.det_model_dir:
        kwargs["det_model_dir"] = settings.det_model_dir
    if settings.rec_model_dir:
        kwargs["rec_model_dir"] = settings.rec_model_dir
    if settings.cls_model_dir:
        kwargs["cls_model_dir"] = settings.cls_model_dir

    last_exc: Exception | None = None
    for _ in range(8):
        try:
            return PaddleOCR(**kwargs)
        except TypeError as exc:
            last_exc = exc
            break
        except ValueError as exc:
            last_exc = exc
            msg = str(exc)
            if "Unknown argument" not in msg:
                break
            bad = msg.split("Unknown argument:", 1)[-1].strip()
            bad = bad.strip("'\" ")
            if not bad or bad not in kwargs:
                break
            del kwargs[bad]

    if last_exc is not None:
        raise last_exc
    return PaddleOCR(**kwargs)


def _split_langs(raw_lang: str) -> list[str]:
    text = (raw_lang or "").strip() or "ch"
    parts = re.split(r"[,+/|]", text)
    langs = [part.strip() for part in parts if part.strip()]
    return langs or ["ch"]


def _settings_for_lang(settings: PaddleOcrSettings, lang: str) -> PaddleOcrSettings:
    return PaddleOcrSettings(
        use_angle_cls=settings.use_angle_cls,
        lang=lang,
        det_model_dir=settings.det_model_dir,
        rec_model_dir=settings.rec_model_dir,
        cls_model_dir=settings.cls_model_dir,
        use_gpu=settings.use_gpu,
    )


def _ocr_with_instance(ocr: Any, img: Any, settings: PaddleOcrSettings) -> str:
    ocr_fn = getattr(ocr, "ocr", None)
    if callable(ocr_fn):
        try:
            result = ocr_fn(img, cls=settings.use_angle_cls)
        except TypeError:
            result = ocr_fn(img)
        return _flatten_ocr_result(result)

    predict_fn = getattr(ocr, "predict", None)
    if callable(predict_fn):
        result = predict_fn(img)
        return _flatten_ocr_result(result)

    raise TypeError(f"Unsupported PaddleOCR API: {type(ocr).__name__}")


def _score_ocr_text(text: str) -> tuple[int, int]:
    lines = [line for line in (text or "").splitlines() if line.strip()]
    useful_chars = sum(1 for ch in text if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")
    return useful_chars, len(lines)


def _flatten_ocr_result(result: Any) -> str:
    lines: list[str] = []
    if not result:
        return ""

    if isinstance(result, list) and len(result) == 1 and isinstance(result[0], list):
        candidates = result[0]
    else:
        candidates = result

    if not isinstance(candidates, list):
        return str(candidates)

    for item in candidates:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        text_box = item[1]
        if isinstance(text_box, (list, tuple)) and len(text_box) >= 1:
            text = str(text_box[0] or "").strip()
        else:
            text = str(text_box or "").strip()
        if text:
            lines.append(text)

    return "\n".join(lines).strip()
