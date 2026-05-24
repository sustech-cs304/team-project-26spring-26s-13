"""
backend/services/material_service.py
教材文件业务逻辑：保存文件、触发向量化流程、删除清理。
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import gc
import hashlib
import mimetypes
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database.postgres import AsyncSessionLocal, Material, User
from backend.database.chromadb import SubjectType, add_chunks, delete_file_chunks
from backend.schemas.material import MaterialInfo
from backend.utils.document_parser import parse_document

from backend.utils.crypto import decrypt
from backend.services import rag_service
from backend.services.schedule_service.fetch_bb import (
    BlackboardMaterial,
    fetch_blackboard_course_materials,
)

logger = logging.getLogger(__name__)

from backend.services.schedule_service.log_utils import (
    _ensure_file_logging,
    _trace_filter,
    gen_trace_id,
    set_sync_job_id,
    get_trace_id,
    is_diag_mode,
)

_ensure_file_logging()

_sync_stderr = logging.StreamHandler()
_sync_stderr.setLevel(logging.INFO)
_sync_stderr.setFormatter(
    logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(funcName)s:%(lineno)d | trace=%(trace_id)s | %(message)s"
    )
)
_sync_stderr.addFilter(_trace_filter)
logger.addHandler(_sync_stderr)
logger.setLevel(logging.DEBUG)
logger.propagate = False

import threading

_file_name_index: dict[str, set[str]] = {}
_file_name_index_lock = threading.Lock()


def _tokenize_text(text: str) -> list[str]:
    tokens: list[str] = []
    t = (text or "").lower().strip()
    import re as _re

    en_parts = _re.split(r"[\s_.\-/,;:()\[\]{}'\"!@#$%^&*+=<>?|~`\\]+", t)
    for p in en_parts:
        p = p.strip()
        if not p:
            continue
        if p.isascii():
            if len(p) >= 2:
                tokens.append(p)
            continue
        for ci in range(len(p)):
            tokens.append(p[ci : ci + 1])
            if ci + 1 < len(p):
                tokens.append(p[ci : ci + 2])
            if ci + 2 < len(p):
                tokens.append(p[ci : ci + 3])
    return tokens


def _register_file_name(file_name: str, file_id: str) -> None:
    tokens = _tokenize_text(file_name or "")
    if not tokens:
        return
    with _file_name_index_lock:
        for tok in tokens:
            _file_name_index.setdefault(tok, set()).add(file_id)


def _unregister_file_name(file_name: str, file_id: str) -> None:
    tokens = _tokenize_text(file_name or "")
    if not tokens:
        return
    with _file_name_index_lock:
        for tok in tokens:
            s = _file_name_index.get(tok)
            if s:
                s.discard(file_id)


def search_by_file_name(keyword: str, limit: int = 30) -> list[str]:
    if not (keyword or "").strip():
        return []
    tokens = _tokenize_text(keyword)
    if not tokens:
        return []
    with _file_name_index_lock:
        candidates: set[str] | None = None
        for tok in tokens:
            ids = _file_name_index.get(tok, set())
            if candidates is None:
                candidates = set(ids)
            else:
                candidates = candidates.intersection(ids)
            if not candidates:
                return []
        return sorted(candidates or [])[:limit]


ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # pptx
    "application/vnd.ms-powerpoint",  # ppt
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # docx
    "application/msword",  # doc
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # xlsx
    "text/csv",
    "text/markdown",
    "text/plain",
}


async def list_materials(db: AsyncSession, user_id: uuid.UUID) -> list[MaterialInfo]:
    """
    查询某用户的所有教材，按上传时间倒序。

    Args:
        db:      数据库 Session
        user_id: 用户 UUID

    Returns:
        list[MaterialInfo]，可为空列表
    """
    rows = await db.scalars(
        select(Material)
        .where(Material.user_id == user_id)
        .order_by(Material.uploaded_at.desc())
    )
    return [_to_schema(m) for m in rows]


async def upload_and_vectorize(
    db: AsyncSession,
    user: User,
    file: UploadFile,
) -> MaterialInfo:
    """
    完整的文件上传 + 向量化流程（同步执行，可改为后台任务）。

    流程：
    1. 校验 MIME 类型和文件大小
    2. 保存原始文件到磁盘（settings.UPLOAD_DIR/{user_id}/{file_id}.ext）
    3. 解析文本（utils/document_parser.py）
    4. 调用 LLM 分类学科类型（agent/tools/rag.classify_subject）
    5. 切分文本为 chunks（按 settings.CHUNK_SIZE，步长 settings.CHUNK_OVERLAP）
    6. 写入 ChromaDB（database/chromadb.add_chunks）
    7. 更新 materials 表 vectorized=True
    """
    file_bytes = await file.read()
    return await _create_material_from_bytes(
        db=db,
        user=user,
        file_name=file.filename or "unknown",
        content_type=file.content_type or "",
        file_bytes=file_bytes,
    )


async def sync_blackboard_materials(
    db: AsyncSession,
    user: User,
    *,
    course_keyword: str | None = None,
    keyword: str | None = None,
    limit: int | None = None,
) -> list[MaterialInfo]:
    cas_account = (getattr(user, "cas_account", None) or "").strip()
    cas_password_encrypted = getattr(user, "cas_password_encrypted", None)
    if not cas_account or not cas_password_encrypted:
        raise PermissionError("CAS credentials not configured")

    try:
        cas_password = decrypt(cas_password_encrypted)
    except Exception as exc:
        raise PermissionError(f"CAS credentials invalid: {type(exc).__name__}") from exc

    def _match(item: BlackboardMaterial) -> bool:
        ck = (course_keyword or "").strip().lower()
        kw = (keyword or "").strip().lower()
        if ck:
            hay = " ".join(
                [
                    str(item.course_name or ""),
                    str(item.course_id or ""),
                ]
            ).lower()
            if ck not in hay:
                return False
        if kw:
            hay = " ".join([str(item.title or ""), str(item.file_name or "")]).lower()
            if kw not in hay:
                return False
        return True

    bb_materials = await fetch_blackboard_course_materials(
        cas_account,
        cas_password,
        course_keyword=course_keyword,
        keyword=keyword,
        limit=limit,
    )
    bb_materials, _skipped = bb_materials
    if course_keyword or keyword:
        bb_materials = [item for item in bb_materials if _match(item)]

    existing = await db.scalars(
        select(Material).where(Material.user_id == user.user_id)
    )
    existing_names = {material.file_name for material in existing}

    synced: list[MaterialInfo] = []
    skipped_existing = 0
    skipped_unsupported = 0
    failed_create = 0
    for item in bb_materials:
        if limit is not None and limit >= 0 and len(synced) >= limit:
            break
        if item.file_name in existing_names:
            skipped_existing += 1
            continue
        try:
            info = await _create_material_from_bytes(
                db=db,
                user=user,
                file_name=item.file_name,
                content_type=item.file_type,
                file_bytes=item.file_bytes,
            )
        except ValueError:
            logger.info(
                "跳过不支持的 Blackboard 课件: %s (%s)", item.file_name, item.file_type
            )
            skipped_unsupported += 1
            continue
        except Exception as exc:
            logger.error(
                "同步 Blackboard 课件失败: %s (%s) err=%s",
                item.file_name,
                item.file_type,
                type(exc).__name__,
                exc_info=True,
            )
            failed_create += 1
            continue
        synced.append(info)
        existing_names.add(info.file_name)
    logger.info(
        "bb.sync: fetched=%d synced=%d skipped_existing=%d skipped_unsupported=%d failed=%d",
        len(bb_materials),
        len(synced),
        skipped_existing,
        skipped_unsupported,
        failed_create,
    )
    return synced


@dataclass
class _BlackboardSyncJobState:
    job_id: str
    user_id: uuid.UUID
    status: str = "queued"
    stage: str = "queued"
    processed: int = 0
    total: int | None = None
    added: int = 0
    skipped_existing: int = 0
    skipped_unsupported: int = 0
    skipped_large: int = 0
    failed: int = 0
    message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cancel_requested: bool = False
    task: asyncio.Task | None = None


_BB_SYNC_JOBS: dict[str, _BlackboardSyncJobState] = {}
_BB_SYNC_JOBS_LOCK = asyncio.Lock()


def _job_to_dict(job: _BlackboardSyncJobState) -> dict[str, object]:
    return {
        "job_id": job.job_id,
        "status": job.status,
        "stage": job.stage,
        "processed": job.processed,
        "total": job.total,
        "added": job.added,
        "skipped_existing": job.skipped_existing,
        "skipped_unsupported": job.skipped_unsupported,
        "skipped_large": job.skipped_large,
        "failed": job.failed,
        "message": job.message,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }


async def start_blackboard_sync_job(
    user: User,
    *,
    course_keyword: str | None = None,
    keyword: str | None = None,
    limit: int | None = None,
) -> dict[str, object]:
    job_id = f"bb_{uuid.uuid4().hex}"
    state = _BlackboardSyncJobState(job_id=job_id, user_id=user.user_id)
    async with _BB_SYNC_JOBS_LOCK:
        _BB_SYNC_JOBS[job_id] = state
        state.task = asyncio.create_task(
            _run_blackboard_sync_job(
                job_id,
                user_id=user.user_id,
                course_keyword=course_keyword,
                keyword=keyword,
                limit=limit,
            )
        )
    return _job_to_dict(state)


async def get_blackboard_sync_job(user: User, job_id: str) -> dict[str, object]:
    async with _BB_SYNC_JOBS_LOCK:
        job = _BB_SYNC_JOBS.get(job_id)
        if job is None or job.user_id != user.user_id:
            raise FileNotFoundError("job not found")
        return _job_to_dict(job)


async def cancel_blackboard_sync_job(user: User, job_id: str) -> dict[str, object]:
    async with _BB_SYNC_JOBS_LOCK:
        job = _BB_SYNC_JOBS.get(job_id)
        if job is None or job.user_id != user.user_id:
            raise FileNotFoundError("job not found")
        job.cancel_requested = True
        if job.task is not None and not job.task.done():
            job.task.cancel()
        return _job_to_dict(job)


async def _run_blackboard_sync_job(
    job_id: str,
    *,
    user_id: uuid.UUID,
    course_keyword: str | None,
    keyword: str | None,
    limit: int | None,
) -> None:
    tid = gen_trace_id()
    set_sync_job_id(job_id[:16])
    logger.info("bb.sync: job_started trace=%s job=%s", tid, job_id[:16])

    async def _update(**kwargs) -> None:
        async with _BB_SYNC_JOBS_LOCK:
            job = _BB_SYNC_JOBS.get(job_id)
            if job is None:
                return
            for k, v in kwargs.items():
                setattr(job, k, v)

    await _update(
        status="running",
        stage="fetching",
        started_at=datetime.now(timezone.utc),
        message="fetching_blackboard",
    )

    async with AsyncSessionLocal() as db:
        user = await db.get(User, user_id)
        if user is None:
            await _update(
                status="failed",
                stage="failed",
                finished_at=datetime.now(timezone.utc),
                message="user_not_found",
            )
            return

        cas_account = (getattr(user, "cas_account", None) or "").strip()
        cas_password_encrypted = getattr(user, "cas_password_encrypted", None)
        if not cas_account or not cas_password_encrypted:
            await _update(
                status="failed",
                stage="failed",
                finished_at=datetime.now(timezone.utc),
                message="cas_credentials_not_configured",
            )
            return

        try:
            cas_password = decrypt(cas_password_encrypted)
        except Exception as exc:
            logger.exception(
                "bb.sync: fetch_failed trace=%s err=%s",
                get_trace_id(),
                type(exc).__name__,
            )
            await _update(
                status="failed",
                stage="failed",
                finished_at=datetime.now(timezone.utc),
                message=f"cas_credentials_invalid:{type(exc).__name__}",
            )
            return

        try:
            bb_materials, bb_skipped = await fetch_blackboard_course_materials(
                cas_account,
                cas_password,
                course_keyword=course_keyword,
                keyword=keyword,
                limit=limit,
            )
        except asyncio.CancelledError:
            await _update(
                status="cancelled",
                stage="cancelled",
                finished_at=datetime.now(timezone.utc),
                message="cancelled",
            )
            return
        except Exception as exc:
            await _update(
                status="failed",
                stage="failed",
                finished_at=datetime.now(timezone.utc),
                message=f"fetch_failed:{type(exc).__name__}",
            )
            return

        await _update(
            stage="importing",
            total=len(bb_materials),
            message="importing",
        )

        if not bb_materials:
            if bb_skipped:
                skipped_names = [s.file_name for s in bb_skipped[:20]]
                await _update(
                    status="done",
                    stage="done",
                    finished_at=datetime.now(timezone.utc),
                    added=0,
                    skipped_large=len(bb_skipped),
                    message=f"skipped_dl:{','.join(skipped_names)}",
                )
                return
            await _update(
                status="failed",
                stage="failed",
                finished_at=datetime.now(timezone.utc),
                message="no_files_found",
            )
            return

        existing = await db.scalars(select(Material).where(Material.user_id == user_id))
        existing_records: dict[str, Material] = {m.file_name: m for m in existing}
        existing_names = set(existing_records.keys())

        processed = 0
        skipped_large_count = 0
        skipped_unsupported_names: list[str] = []
        failed_names: list[str] = []
        for item in bb_materials:
            async with _BB_SYNC_JOBS_LOCK:
                job = _BB_SYNC_JOBS.get(job_id)
                if job is None:
                    return
                if job.cancel_requested:
                    job.status = "cancelled"
                    job.stage = "cancelled"
                    job.finished_at = datetime.now(timezone.utc)
                    job.message = "cancelled"
                    return
                current_skipped_existing = job.skipped_existing
                current_skipped_unsupported = job.skipped_unsupported
                current_failed = job.failed
                current_added = job.added
                current_skipped_large = job.skipped_large

            processed += 1
            if item.file_name in existing_names:
                stale = existing_records.get(item.file_name)
                if stale is not None:
                    disk_path = Path(stale.file_path)
                    if not disk_path.exists():
                        logger.warning(
                            "material: missing_on_disk deleting_stale "
                            "file_name=%s file_id=%s path=%s *** TERMINAL: WILL RE-DOWNLOAD ***",
                            item.file_name,
                            stale.file_id,
                            disk_path,
                        )
                        await db.delete(stale)
                        await db.flush()
                        existing_names.discard(item.file_name)
                    elif stale.file_hash:
                        fb_for_hash = item.file_bytes
                        tmp = getattr(item, "_tmp_path", "") or ""
                        if not fb_for_hash and tmp:
                            try:
                                hp = Path(tmp)
                                if hp.exists():
                                    fb_for_hash = hp.read_bytes()
                            except Exception:
                                pass
                        if fb_for_hash:
                            new_hash = hashlib.sha256(fb_for_hash).hexdigest()
                            if new_hash == stale.file_hash:
                                await _update(
                                    processed=processed,
                                    skipped_existing=current_skipped_existing + 1,
                                    message=item.file_name,
                                )
                                continue
                            else:
                                logger.info(
                                    "material: hash_changed overwriting "
                                    "file_name=%s old_hash=%s new_hash=%s",
                                    item.file_name,
                                    stale.file_hash,
                                    new_hash,
                                )
                                await db.delete(stale)
                                await db.flush()
                                existing_names.discard(item.file_name)
                        else:
                            await _update(
                                processed=processed,
                                skipped_existing=current_skipped_existing + 1,
                                message=item.file_name,
                            )
                            continue
                    else:
                        await _update(
                            processed=processed,
                            skipped_existing=current_skipped_existing + 1,
                            message=item.file_name,
                        )
                        continue
                else:
                    await _update(
                        processed=processed,
                        skipped_existing=current_skipped_existing + 1,
                        message=item.file_name,
                    )
                    continue

            try:
                fb = item.file_bytes
                tmp = getattr(item, "_tmp_path", "") or ""
                if not fb and tmp:
                    try:
                        tmp_path = Path(tmp)
                        if tmp_path.exists():
                            fb = tmp_path.read_bytes()
                            tmp_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                if not fb:
                    logger.warning(
                        "material: empty_bytes file_name=%s course=%s",
                        item.file_name,
                        item.course_id,
                    )
                    failed_names.append(item.file_name)
                    await _update(
                        processed=processed,
                        failed=current_failed + 1,
                        message=item.file_name,
                    )
                    continue
                logger.info(
                    "material: processing [%d/%d] file_name=%s size=%d course=%s",
                    processed,
                    len(bb_materials),
                    item.file_name,
                    len(fb) if fb else 0,
                    item.course_id,
                )
                info = await _create_material_from_bytes(
                    db=db,
                    user=user,
                    file_name=item.file_name,
                    content_type=item.file_type,
                    file_bytes=fb,
                )
            except ValueError:
                skipped_unsupported_names.append(item.file_name)
                await _update(
                    processed=processed,
                    skipped_unsupported=current_skipped_unsupported + 1,
                    message=item.file_name,
                )
                continue
            except Exception:
                try:
                    await db.rollback()
                except Exception:
                    pass
                logger.exception(
                    "material: import_failed file_name=%s course=%s trace=%s",
                    item.file_name,
                    getattr(item, "course_id", "?"),
                    get_trace_id(),
                )
                failed_names.append(item.file_name)
                await _update(
                    processed=processed,
                    failed=current_failed + 1,
                    message=item.file_name,
                )
                continue

            existing_names.add(info.file_name)
            await _update(
                processed=processed,
                added=current_added + 1,
                message=info.file_name,
            )
            logger.info(
                "material: file_done [%d/%d] file_name=%s",
                processed,
                len(bb_materials),
                item.file_name,
            )
            gc.collect()

        done_parts = ["done"]
        if bb_skipped:
            total_bb_skipped = len(bb_skipped)
            display_names = [s.file_name for s in bb_skipped[:20]]
            done_parts.append(
                f"skipped_dl:{','.join(display_names)} ({total_bb_skipped} total)"
            )
            skipped_large_count += total_bb_skipped
        if skipped_unsupported_names:
            done_parts.append(
                "skipped_unsupported:" + ",".join(skipped_unsupported_names[:20])
            )
        if failed_names:
            done_parts.append("failed:" + ",".join(failed_names[:20]))
        done_message = " | ".join(done_parts)
        logger.info(
            "bb.sync: job_done trace=%s added=%d existing=%d failed=%d skipped=%d unsupported=%d",
            get_trace_id(),
            current_added,
            current_skipped_existing,
            current_failed,
            skipped_large_count,
            len(skipped_unsupported_names),
        )

        await _update(
            status="done",
            stage="done",
            finished_at=datetime.now(timezone.utc),
            skipped_large=skipped_large_count,
            message=done_message,
        )


async def delete_material(
    db: AsyncSession,
    user_id: uuid.UUID,
    file_id: uuid.UUID,
) -> None:
    """
    完整删除流程：磁盘文件 + ChromaDB chunks + DB 记录。
    """
    material = await db.get(Material, file_id)
    if material is None:
        raise FileNotFoundError(f"Material {file_id} not found")
    if material.user_id != user_id:
        raise PermissionError("Not your file")

    try:
        delete_file_chunks(str(file_id), material.subject_type)
    except Exception:
        logger.warning(
            "material: delete_chunks_failed file_id=%s trace=%s",
            file_id,
            get_trace_id(),
            exc_info=True,
        )

    Path(material.file_path).unlink(missing_ok=True)
    await db.delete(material)
    await db.commit()


def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    if not (text or "").strip():
        return []
    chunks: list[str] = []
    start = 0
    step = max(1, chunk_size - overlap)
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += step
    return chunks


def _detect_mime_from_bytes(file_name: str, file_bytes: bytes) -> str:
    buf = bytes(file_bytes or b"")
    if not buf:
        return ""
    head = buf[:16]
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if head.startswith(b"PK\x03\x04"):
        guessed, _encoding = mimetypes.guess_type(file_name or "")
        guessed = (guessed or "").lower()
        if "presentation" in guessed:
            return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        if "wordprocessingml" in guessed or "word" in guessed or "document" in guessed:
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if "spreadsheet" in guessed or "sheet" in guessed:
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return ""
    if head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        guessed, _encoding = mimetypes.guess_type(file_name or "")
        guessed = (guessed or "").lower()
        if "powerpoint" in guessed:
            return "application/vnd.ms-powerpoint"
        if "word" in guessed or "msword" in guessed or "document" in guessed:
            return "application/msword"
        return ""
    if buf.startswith(b"---") or buf.startswith(b"#") or buf.startswith(b"*"):
        return "text/markdown"
    try:
        buf[:2048].decode("utf-8")
        return "text/plain"
    except Exception:
        return ""


def _normalize_content_type(file_name: str, content_type: str) -> str:
    normalized = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized in ALLOWED_MIME_TYPES:
        return normalized
    guessed, _encoding = mimetypes.guess_type(file_name)
    guessed = (guessed or "").lower()
    if guessed in ALLOWED_MIME_TYPES:
        return guessed
    return normalized


async def _create_material_from_bytes(
    db: AsyncSession,
    user: User,
    file_name: str,
    content_type: str,
    file_bytes: bytes,
) -> MaterialInfo:
    normalized_type = _normalize_content_type(file_name, content_type)
    if normalized_type not in ALLOWED_MIME_TYPES:
        detected = _detect_mime_from_bytes(file_name, file_bytes)
        if detected in ALLOWED_MIME_TYPES:
            normalized_type = detected
        else:
            head_hex = bytes(file_bytes[:16]).hex() if file_bytes else "empty"
            raise ValueError(
                f"Unsupported file type: raw_ct={content_type} "
                f"normalized={normalized_type} detected={detected} "
                f"head={head_hex} file={file_name}"
            )

    size_mb = len(file_bytes) / (1024 * 1024)
    if size_mb > settings.MAX_UPLOAD_SIZE_MB:
        raise ValueError(
            f"File size {size_mb:.1f}MB exceeds limit {settings.MAX_UPLOAD_SIZE_MB}MB"
        )

    file_id = uuid.uuid4()
    suffix = Path(file_name or "file").suffix
    user_dir = Path(settings.UPLOAD_DIR) / str(user.user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    file_path = user_dir / f"{file_id}{suffix}"
    file_path.write_bytes(file_bytes)

    logger.info(
        "material: saved_to_disk file_name=%s file_id=%s path=%s size=%d",
        file_name,
        file_id,
        file_path,
        len(file_bytes),
    )

    file_hash = hashlib.sha256(file_bytes).hexdigest()

    material = Material(
        file_id=file_id,
        user_id=user.user_id,
        file_name=file_name or "unknown",
        file_type=normalized_type[:64],
        file_path=str(file_path.resolve()),
        subject_type="other",
        file_hash=file_hash,
        vectorized=False,
    )
    db.add(material)
    await db.commit()
    await db.refresh(material)

    try:
        logger.info("material: parse_start file_name=%s", file_name)
        parsed = parse_document(str(file_path), normalized_type)
        logger.info(
            "material: parse_done file_name=%s chars=%d pages=%d",
            file_name,
            len(parsed.text),
            parsed.page_count,
        )
        chunks = _chunk_text(parsed.text, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP)
        logger.info("material: chunked file_name=%s chunks=%d", file_name, len(chunks))

        subject_type: SubjectType = "other"
        try:
            api_key = (
                decrypt(user.llm_api_key_encrypted)
                if user.llm_api_key_encrypted
                else settings.DEEPSEEK_API_KEY
            ) or None
            import time as _time

            _cls_start = _time.monotonic()
            logger.info("material: classify_start file_name=%s", file_name)
            subject_type = await rag_service.classify_subject_llm(
                parsed.text[:2000], api_key
            )
            logger.info(
                "material: classify_done file_name=%s subject=%s elapsed=%.1fs",
                file_name,
                subject_type,
                _time.monotonic() - _cls_start,
            )
            material.subject_type = subject_type
        except Exception as e:
            logger.warning(
                "material: classify_failed file_name=%s err=%s trace=%s",
                file_name,
                e,
                get_trace_id(),
            )

        if chunks:
            logger.info(
                "material: embedding_start file_name=%s chunks=%d subject=%s",
                file_name,
                len(chunks),
                subject_type,
            )
            await asyncio.to_thread(
                add_chunks, subject_type, str(file_id), material.file_name, chunks
            )
            logger.info(
                "material: embedding_done file_name=%s chunks=%d",
                file_name,
                len(chunks),
            )
            logger.info(
                "向量化完成: file=%s subject=%s chunks=%d",
                file_id,
                subject_type,
                len(chunks),
            )
            material.vectorized = True
        await db.commit()
        _register_file_name(material.file_name, str(file_id))
    except Exception as e:
        try:
            await db.rollback()
        except Exception:
            pass
        logger.exception(
            "material: vectorize_failed file_id=%s file_name=%s trace=%s",
            file_id,
            file_name,
            get_trace_id(),
        )
        if file_path.exists():
            file_path.unlink(missing_ok=True)
        return None

    return _to_schema(material)


def _to_schema(material: Material) -> MaterialInfo:
    """将 ORM Material 对象转换为 MaterialInfo Pydantic schema。"""
    return MaterialInfo(
        file_id=str(material.file_id),
        file_name=material.file_name,
        file_type=material.file_type,
        subject_type=material.subject_type,
        vectorized=material.vectorized,
        uploaded_at=material.uploaded_at,
    )
