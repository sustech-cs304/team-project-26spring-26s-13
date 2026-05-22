"""
backend/services/material_service.py
教材文件业务逻辑：保存文件、触发向量化流程、删除清理。
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
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
from backend.agent.tools.rag import infer_subject_type

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # pptx
    "application/vnd.ms-powerpoint",  # ppt
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
            await _update(
                status="failed",
                stage="failed",
                finished_at=datetime.now(timezone.utc),
                message=f"cas_credentials_invalid:{type(exc).__name__}",
            )
            return

        try:
            bb_materials = await fetch_blackboard_course_materials(
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
            await _update(
                status="failed",
                stage="failed",
                finished_at=datetime.now(timezone.utc),
                message="no_files_found",
            )
            return

        existing = await db.scalars(select(Material).where(Material.user_id == user_id))
        existing_names = {material.file_name for material in existing}

        processed = 0
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

            processed += 1
            if item.file_name in existing_names:
                await _update(
                    processed=processed,
                    skipped_existing=current_skipped_existing + 1,
                    message=item.file_name,
                )
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
                await _update(
                    processed=processed,
                    skipped_unsupported=current_skipped_unsupported + 1,
                    message=item.file_name,
                )
                continue
            except Exception:
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

        await _update(
            status="done",
            stage="done",
            finished_at=datetime.now(timezone.utc),
            message="done",
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
        pass

    Path(material.file_path).unlink(missing_ok=True)
    await db.delete(material)
    await db.commit()


def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """
    将长文本切分为固定大小的 chunk，相邻 chunk 有 overlap 字符重叠。
    """
    if not (text or "").strip():
        return []
    chunks: list[str] = []
    start = 0
    step = max(1, int(chunk_size) - int(overlap))
    chunk_size = max(1, int(chunk_size))
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
        return ""
    if head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        guessed, _encoding = mimetypes.guess_type(file_name or "")
        guessed = (guessed or "").lower()
        if "powerpoint" in guessed:
            return "application/vnd.ms-powerpoint"
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
            raise ValueError(f"Unsupported file type: {content_type or normalized_type}")

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

    material = Material(
        file_id=file_id,
        user_id=user.user_id,
        file_name=file_name or "unknown",
        file_type=normalized_type,
        file_path=str(file_path.resolve()),
        subject_type="other",
        vectorized=False,
    )
    db.add(material)
    await db.commit()
    await db.refresh(material)

    try:
        parsed = parse_document(str(file_path), normalized_type)
        chunks = _chunk_text(parsed.text, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP)

        subject_type: SubjectType = "other"
        try:
            api_key = (
                decrypt(user.llm_api_key_encrypted)
                if user.llm_api_key_encrypted
                else settings.DEEPSEEK_API_KEY
            ) or None
            subject_type = await rag_service.classify_subject_llm(
                parsed.text[:2000], api_key
            )
            material.subject_type = subject_type
        except Exception as e:
            logger.warning("学科分类失败，回退到 other: %s", e)

        if chunks:
            add_chunks(subject_type, str(file_id), material.file_name, chunks)
            logger.info(
                "向量化完成: file=%s subject=%s chunks=%d",
                file_id,
                subject_type,
                len(chunks),
            )
            material.vectorized = True
        await db.commit()
    except Exception as e:
        logger.error("向量化流程失败 (file=%s): %s", file_id, e, exc_info=True)

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
