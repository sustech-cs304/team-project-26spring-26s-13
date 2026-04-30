"""
tests/conftest.py

The DATABASE trick: backend/database/postgres.py calls create_async_engine()
at *module import time*, which requires a live asyncpg driver + valid DSN.
We must patch os.environ BEFORE any backend module is imported so that
pydantic-settings picks up the test DSN via the environment.

SQLite in-memory is used so tests run with zero infrastructure.
JSONB columns are mapped to JSON in SQLite (transparent via SQLAlchemy).
UUID columns fall back to VARCHAR in SQLite.
"""

import os

# ─── Patch env BEFORE any backend import ──────────────────────────────────────
# Override the Postgres DSN with a local SQLite file so create_async_engine
# never tries to connect to a real Postgres server.
os.environ.setdefault("POSTGRES_DSN", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest")
os.environ.setdefault("FERNET_KEY", "dmFsaWRiYXNlNjRlbmNvZGVkZmVybmV0a2V5MDAwMDA=")

# ─── Teach SQLite compiler to handle PostgreSQL-specific column types ──────────
# The ORM models use postgresql.JSONB and postgresql.UUID which SQLite doesn't
# recognise.  We add visit_* methods to the SQLite type compiler before any
# backend module is imported so that Base.metadata.create_all works with SQLite.
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler  # noqa: E402

if not hasattr(SQLiteTypeCompiler, "visit_JSONB"):
    SQLiteTypeCompiler.visit_JSONB = lambda self, type_, **kw: "JSON"

if not hasattr(SQLiteTypeCompiler, "visit_UUID"):
    SQLiteTypeCompiler.visit_UUID = lambda self, type_, **kw: "VARCHAR(36)"

# ─── Fix UUID bind/result processors for SQLite ───────────────────────────────
# SQLAlchemy's Uuid type (which postgresql.UUID delegates to) calls value.hex in
# its bind_processor, expecting a uuid.UUID object.  Under SQLite, the app code
# often passes plain string UUIDs (e.g. decoded from a JWT), so we override the
# processors to accept both str and uuid.UUID.
import uuid as _uuid_mod
from sqlalchemy.sql import sqltypes as _sa_sqltypes

_orig_uuid_bind = _sa_sqltypes.Uuid.bind_processor
_orig_uuid_result = _sa_sqltypes.Uuid.result_processor


def _patched_uuid_bind(self, dialect):
    def process(value):
        if value is None:
            return None
        if isinstance(value, _uuid_mod.UUID):
            return str(value) if dialect.name == "sqlite" else value.hex
        # Already a string – pass through for SQLite, convert hex for Postgres
        return value if dialect.name == "sqlite" else _uuid_mod.UUID(str(value)).hex
    return process


def _patched_uuid_result(self, dialect, coltype):
    if not self.as_uuid:
        return None
    def process(value):
        if value is None:
            return None
        if isinstance(value, _uuid_mod.UUID):
            return value
        return _uuid_mod.UUID(str(value))
    return process


_sa_sqltypes.Uuid.bind_processor = _patched_uuid_bind
_sa_sqltypes.Uuid.result_processor = _patched_uuid_result
# ──────────────────────────────────────────────────────────────────────────────

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Now it is safe to import backend modules
from backend.database.postgres import Base, get_db
from backend.main import app

# ── Test Database Setup ────────────────────────────────────────────────────────
TEST_DB_URL = "sqlite+aiosqlite:///./test.db"

test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSessionLocal = async_sessionmaker(
    bind=test_engine, class_=AsyncSession, expire_on_commit=False
)


async def override_get_db():
    """Dependency override: use the in-memory test DB instead of Postgres."""
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="function", autouse=True)
async def setup_database():
    """Create all tables before each test, drop them after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def async_client() -> AsyncClient:
    """Async HTTP test client wired to the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


# ── Helper: create a registered + logged-in user ─────────────────────────────

SAMPLE_USER = {
    "username": "testuser",
    "password": "password123",
    "display_name": "Test User",
    "major": "Computer Science",
}


@pytest_asyncio.fixture
async def registered_user(async_client: AsyncClient) -> dict:
    """Register a sample user and return the full AuthResponse dict."""
    resp = await async_client.post("/api/auth/register", json=SAMPLE_USER)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def auth_headers(registered_user: dict) -> dict:
    """Return Authorization headers for an already-registered user."""
    token = registered_user["token"]
    return {"Authorization": f"Bearer {token}"}
