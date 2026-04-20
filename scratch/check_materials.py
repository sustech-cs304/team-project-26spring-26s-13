import asyncio
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, String, Boolean, DateTime

# Copied from backend/database/postgres.py (partial)
Base = declarative_base()
class Material(Base):
    __tablename__ = "materials"
    file_id = Column(String, primary_key=True)
    file_name = Column(String)
    subject_type = Column(String)
    vectorized = Column(Boolean)

DSN = "postgresql+asyncpg://postgres:password@localhost:5432/software-engineering"

async def check():
    engine = create_async_engine(DSN)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        result = await session.execute(select(Material))
        rows = result.scalars().all()
        print(f"Total materials: {len(rows)}")
        for m in rows:
            print(f"File: {m.file_name}, Subject: {m.subject_type}, Vectorized: {m.vectorized}")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check())
