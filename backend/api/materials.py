"""
backend/api/materials.py
教材文件路由：列表查询、上传（触发向量化）、删除。
"""

import uuid
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.postgres import User, get_db
from backend.schemas.material import (
    BlackboardSyncJobInfo,
    BlackboardSyncJobStartResponse,
    MaterialInfo,
)
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
    return await material_service.list_materials(db, current_user.user_id)


@router.post(
    "/upload", response_model=MaterialInfo, status_code=status.HTTP_201_CREATED
)
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
    try:
        return await material_service.upload_and_vectorize(db, current_user, file)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/sync-blackboard",
    response_model=list[MaterialInfo],
    status_code=status.HTTP_201_CREATED,
)
async def sync_blackboard_materials(
    course_keyword: str | None = Query(
        default=None, description="课程关键词过滤（匹配 course_name/course_id）"
    ),
    keyword: str | None = Query(
        default=None,
        description="文件关键词过滤（匹配 title/file_name，例如 lecture3）",
    ),
    limit: int | None = Query(
        default=None, ge=0, le=200, description="最多同步多少个匹配文件"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MaterialInfo]:
    """
    从 Blackboard 同步当前用户可访问的课件，并复用现有解析与向量化流程入库。
    """
    try:
        return await material_service.sync_blackboard_materials(
            db,
            current_user,
            course_keyword=course_keyword,
            keyword=keyword,
            limit=limit,
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY, detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/sync-blackboard/jobs",
    response_model=BlackboardSyncJobStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_sync_blackboard_job(
    course_keyword: str | None = Query(
        default=None, description="课程关键词过滤（匹配 course_name/course_id）"
    ),
    keyword: str | None = Query(
        default=None,
        description="文件关键词过滤（匹配 title/file_name，例如 lecture3）",
    ),
    limit: int | None = Query(
        default=None, ge=0, le=200, description="最多同步多少个匹配文件"
    ),
    current_user: User = Depends(get_current_user),
) -> BlackboardSyncJobStartResponse:
    job = await material_service.start_blackboard_sync_job(
        current_user,
        course_keyword=course_keyword,
        keyword=keyword,
        limit=limit,
    )
    return BlackboardSyncJobStartResponse(job_id=str(job.get("job_id", "")))


@router.get("/sync-blackboard/jobs/{job_id}", response_model=BlackboardSyncJobInfo)
async def get_sync_blackboard_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> BlackboardSyncJobInfo:
    try:
        payload = await material_service.get_blackboard_sync_job(current_user, job_id)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )
    return BlackboardSyncJobInfo(**payload)


@router.post(
    "/sync-blackboard/jobs/{job_id}/cancel", response_model=BlackboardSyncJobInfo
)
async def cancel_sync_blackboard_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> BlackboardSyncJobInfo:
    try:
        payload = await material_service.cancel_blackboard_sync_job(
            current_user, job_id
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )
    return BlackboardSyncJobInfo(**payload)


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
    try:
        await material_service.delete_material(db, current_user.user_id, file_id)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Material not found"
        )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not your file"
        )
