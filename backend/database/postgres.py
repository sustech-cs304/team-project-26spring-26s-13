"""
backend/database/postgres.py
SQLAlchemy 2.0 异步引擎 + Session 工厂 + ORM 模型基类。
所有 ORM 模型定义在此，通过 Base 注册后由 Alembic 迁移。
"""

import uuid
from datetime import datetime
from typing import AsyncGenerator

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    LargeBinary,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from backend.config import settings

# ── Engine & Session ─────────────────────────────────────────────────────────

engine = create_async_engine(settings.POSTGRES_DSN, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def ensure_tables_exist() -> None:
    """
    在本地开发环境中补齐缺失的 ORM 表。

    该操作只会创建不存在的表，不会修改已存在表结构，
    因此可安全用于补上后续新增的 `personal_tasks` 等表。
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for sql in [
            "ALTER TABLE materials ADD COLUMN IF NOT EXISTS file_hash VARCHAR(64)",
        ]:
            try:
                await conn.execute(text(sql))
            except Exception:
                pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency：提供一个请求范围的数据库 Session，请求结束后自动关闭。"""
    async with AsyncSessionLocal() as session:
        yield session


# ── Declarative Base ─────────────────────────────────────────────────────────


class Base(DeclarativeBase):
    pass


# ── ORM Models ───────────────────────────────────────────────────────────────


class User(Base):
    """
    用户主表。
    CAS 密码和 LLM API Key 以加密字节串存储，
    读写必须经过 utils/crypto.py 的 encrypt/decrypt 函数。
    """

    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    major: Mapped[str] = mapped_column(String(128), nullable=False)

    # CAS 账号密码（用于爬取 Blackboard/教务系统）
    cas_account: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cas_password_encrypted: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True
    )

    # 用户自己的 DeepSeek API Key（加密存储）
    llm_api_key_encrypted: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True
    )

    # 用户自定义的工作目录（明文存储）
    working_dir: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # 前端偏好（主题、语言等），JSONB 自由扩展
    preferences: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    sessions: Mapped[list["ChatSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    materials: Mapped[list["Material"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    personal_tasks: Mapped[list["PersonalTask"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class ChatSession(Base):
    """
    对话会话表。一个 session 对应一次完整的多轮对话。
    session_id 由前端生成并传入，格式建议 "sess_{timestamp}_{random}"。
    """

    __tablename__ = "chat_sessions"

    session_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="sessions")
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session",
        order_by=lambda: (
            ChatMessage.timestamp,
            ChatMessage.role == "assistant",
        ),
        cascade="all, delete-orphan",
    )


class ChatMessage(Base):
    """
    单条对话消息。role 只允许 'user' 或 'assistant'。
    """

    __tablename__ = "chat_messages"

    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("chat_sessions.session_id"), nullable=False
    )
    # Keep this aligned with the README's manual schema, which uses VARCHAR + CHECK
    # instead of a PostgreSQL enum type.
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    session: Mapped["ChatSession"] = relationship(back_populates="messages")


class Material(Base):
    """
    用户上传的教材/文件表。
    上传后立即触发向量化流程（vectorized=False → True）。
    subject_type 由 LLM 分类，用于 RAG 检索时的向量库剪枝。
    """

    __tablename__ = "materials"

    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(256), nullable=False)
    file_type: Mapped[str] = mapped_column(
        String(128), nullable=False
    )  # MIME type, e.g. "application/pdf"
    file_path: Mapped[str] = mapped_column(
        String(512), nullable=False
    )  # 服务器本地绝对路径
    # The current bootstrap SQL creates this as VARCHAR(32), so use String here
    # to avoid requiring a native PostgreSQL enum type in local setups.
    subject_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="other"
    )
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vectorized: Mapped[bool] = mapped_column(Boolean, default=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="materials")


class PersonalTask(Base):
    """
    个人事务清单表。
    由 Agent 在对话中提取用户意图后写入，用于日程冲突检测。
    """

    __tablename__ = "personal_tasks"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    title: Mapped[str] = mapped_column(
        String(256), nullable=False
    )  # 事务标题，如"组会"
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # 详细说明（可选）
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    end_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    location: Mapped[str | None] = mapped_column(String(256), nullable=True)
    is_done: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="personal_tasks")


class AuditLog(Base):
    """
    OS 自动化操作审计日志。
    每次 Agent 执行文件系统操作（包含 HITL 批准/拒绝）均写入此表。
    """

    __tablename__ = "audit_logs"

    log_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    session_id: Mapped[str] = mapped_column(String(128), nullable=False)
    action_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # create/read/update/delete/rename
    target_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    hitl_required: Mapped[bool] = mapped_column(Boolean, default=False)
    hitl_approved: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="audit_logs")
