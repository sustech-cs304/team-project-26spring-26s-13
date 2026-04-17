"""
backend/services/audit_service.py
OS 操作审计日志服务，供 os_automation 工具调用。

每当 os_automation 工具（可能是某个 AI Agent 或自动化脚本）
在服务器上执行文件操作（如创建、删除、修改）时，这个服务就会把
“谁在什么时候做了什么”记录到数据库中
"""

import uuid
#导入 SQLAlchemy 的异步 Session 类型。这表明该服务支持并发处理，不会因为等待数据库响应而阻塞整个程序
from sqlalchemy.ext.asyncio import AsyncSession
#from backend.database.postgres import AuditLog: 导入定义的数据库模型类 AuditLog。这个类映射到数据库中的某张审计日志表
from backend.database.postgres import AuditLog


async def log(
    db: AsyncSession,
    user_id: uuid.UUID,
    session_id: str,
    action_type: str,
    target_path: str,
    description: str,
    hitl_required: bool,
    hitl_approved: bool | None = None,
) -> None:
    """
    写入一条 OS 操作审计记录。

    Args:
        db:            数据库 Session
        user_id:       执行操作的用户
        session_id:    所属 Agent 会话
        action_type:   操作类型："create" | "read" | "update" | "delete" | "rename"
        target_path:   操作目标的绝对路径
        description:   操作的自然语言描述
        hitl_required: 该操作是否需要 HITL 审批
        hitl_approved: 审批结果（None 表示无需审批或结果未知）

    Returns:
        None
    """
    record = AuditLog(
        user_id=user_id,
        session_id=session_id,
        action_type=action_type,
        target_path=target_path,
        description=description,
        hitl_required=hitl_required,
        hitl_approved=hitl_approved,
    )
    db.add(record)
    await db.commit()
