"""
backend/services/material_service.py
教材文件业务逻辑：保存文件、触发向量化流程、删除清理。
"""

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
from backend.agent.tools.rag import classify_subject   # 直接调用分类逻辑（非 tool 调用）


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
    # TODO:
    # rows = await db.scalars(select(Material).where(Material.user_id == user_id).order_by(Material.uploaded_at.desc()))
    # return [_to_schema(m) for m in rows]
    raise NotImplementedError


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

    Args:
        db:   数据库 Session
        user: 当前用户 ORM 对象
        file: FastAPI UploadFile 对象

    Returns:
        MaterialInfo（vectorized=True，向量化已完成）

    Raises:
        ValueError: 不支持的文件类型或超出大小限制
    """
    # TODO: 实现上述 7 步流程
    raise NotImplementedError


async def delete_material(
    db: AsyncSession,
    user_id: uuid.UUID,
    file_id: uuid.UUID,
) -> None:
    """
    完整删除流程：磁盘文件 + ChromaDB chunks + DB 记录。

    Args:
        db:      数据库 Session
        user_id: 必须是文件的所有者（用于权限验证）
        file_id: materials.file_id

    Raises:
        PermissionError: file_id 不属于 user_id
        FileNotFoundError: file_id 不存在
    """
    # TODO:
    # 1. 查询 Material，验证 user_id 归属
    # 2. delete_file_chunks(str(file_id), material.subject_type)
    # 3. Path(material.file_path).unlink(missing_ok=True)
    # 4. await db.delete(material); await db.commit()
    raise NotImplementedError


def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """
    将长文本切分为固定大小的 chunk，相邻 chunk 有 overlap 字符重叠。

    Args:
        text:       原始文本
        chunk_size: 每个 chunk 的最大字符数
        overlap:    相邻 chunk 的重叠字符数

    Returns:
        list[str]（至少一个元素）
    """
    # TODO: 滑动窗口切分
    raise NotImplementedError


def _to_schema(material: Material) -> MaterialInfo:
    """将 ORM Material 对象转换为 MaterialInfo Pydantic schema。"""
    # TODO: return MaterialInfo(file_id=str(material.file_id), ...)
    raise NotImplementedError
