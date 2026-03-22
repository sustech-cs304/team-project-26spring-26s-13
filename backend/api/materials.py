"""
backend/api/materials.py
教材文件路由：列表查询、上传（触发向量化）、删除。
"""

import uuid
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.postgres import User, get_db
from backend.schemas.material import MaterialInfo
from backend.services import material_service
from backend.api.deps import get_current_user

router = APIRouter(prefix="/api/materials", tags=["materials"])


@router.get("", response_model=list[MaterialInfo])
async def list_materials(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MaterialInfo]:
    """
    返回当前用户上传的所有教材列表（按上传时间倒序）。
    用于前端侧边栏的材料列表展示。
    """
    # TODO: return await material_service.list_materials(db, current_user.user_id)
    raise NotImplementedError


@router.post("/upload", response_model=MaterialInfo, status_code=status.HTTP_201_CREATED)
async def upload_material(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MaterialInfo:
    """
    上传教材文件并立即触发向量化流程。
    支持的文件类型：PDF、PPT/PPTX、Markdown（.md）。

    流程：
    1. 校验文件类型和大小（≤ settings.MAX_UPLOAD_SIZE_MB）
    2. 保存文件到 settings.UPLOAD_DIR/{user_id}/{file_id}.{ext}
    3. 写入 materials 表（vectorized=False）
    4. 异步触发 material_service.vectorize_material（后台任务）
    5. 立即返回 MaterialInfo（vectorized=False，向量化在后台进行）

    Raises:
        400: 不支持的文件类型
        413: 文件超出大小限制
    """
    # TODO: return await material_service.upload_and_vectorize(db, current_user, file)
    raise NotImplementedError


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_material(
    file_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    删除教材文件。同时：
    1. 删除本地文件（UPLOAD_DIR 中）
    2. 删除 ChromaDB 中对应的所有 chunk
    3. 删除 materials 表记录

    Raises:
        403: file_id 不属于当前用户
        404: file_id 不存在
    """
    # TODO: await material_service.delete_material(db, current_user.user_id, file_id)
    raise NotImplementedError
