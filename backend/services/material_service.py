"""
backend/services/material_service.py
教材文件业务逻辑：保存文件、触发向量化流程、删除清理。
"""

import logging
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database.postgres import Material, User
from backend.database.chromadb import SubjectType, add_chunks, delete_file_chunks
from backend.schemas.material import MaterialInfo
from backend.utils.document_parser import parse_document

from backend.utils.crypto import decrypt
from backend.services import rag_service

logger = logging.getLogger(__name__)
from backend.agent.tools.rag import infer_subject_type

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # pptx
    "application/vnd.ms-powerpoint",                                               # ppt
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
    content_type = file.content_type or ""
    if content_type not in ALLOWED_MIME_TYPES:
        raise ValueError(f"Unsupported file type: {content_type}")

    file_bytes = await file.read()
    size_mb = len(file_bytes) / (1024 * 1024)
    if size_mb > settings.MAX_UPLOAD_SIZE_MB:
        raise ValueError(f"File size {size_mb:.1f}MB exceeds limit {settings.MAX_UPLOAD_SIZE_MB}MB")

    file_id = uuid.uuid4()
    suffix = Path(file.filename or "file").suffix
    user_dir = Path(settings.UPLOAD_DIR) / str(user.user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    file_path = user_dir / f"{file_id}{suffix}"
    file_path.write_bytes(file_bytes)

    material = Material(
        file_id=file_id,
        user_id=user.user_id,
        file_name=file.filename or "unknown",
        file_type=content_type,
        file_path=str(file_path.resolve()),
        subject_type="other",
        vectorized=False,
    )
    db.add(material)
    await db.commit()
    await db.refresh(material)

    try:
        parsed = parse_document(str(file_path), content_type)
        chunks = _chunk_text(parsed.text, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP)

        # 学科分类：直接调 LLM，不依赖 Agent 工具框架
        subject_type: SubjectType = "other"
        try:
            api_key = (
                decrypt(user.llm_api_key_encrypted)
                if user.llm_api_key_encrypted
                else settings.DEEPSEEK_API_KEY
            ) or None
            subject_type = await rag_service.classify_subject_llm(parsed.text[:2000], api_key)
            material.subject_type = subject_type
        except Exception as e:
            logger.warning("学科分类失败，回退到 other: %s", e)

        if chunks:
            add_chunks(subject_type, str(file_id), material.file_name, chunks)
            logger.info("向量化完成: file=%s subject=%s chunks=%d", file_id, subject_type, len(chunks))

        material.vectorized = True
        await db.commit()
    except Exception as e:
        # 向量化失败不影响文件上传成功，仅保持 vectorized=False
        logger.error("向量化流程失败 (file=%s): %s", file_id, e, exc_info=True)

    return _to_schema(material)


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
    if not text:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks if chunks else [text]


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
