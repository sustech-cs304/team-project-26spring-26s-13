"""
一键迁移脚本：为 knowledge base 隔离 + 公有知识库做准备。

用法：
  python backend/migrate_kb.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from backend.database.postgres import AsyncSessionLocal


async def _migrate() -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "ALTER TABLE materials "
                "ADD COLUMN IF NOT EXISTS is_public BOOLEAN DEFAULT FALSE;"
            )
        )
        await db.commit()
        print("✅ materials.is_public 列已添加")

    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO users (user_id, username, password_hash, display_name, major, cas_account, working_dir) "
                "VALUES ("
                "  '00000000-0000-4000-8000-000000000000', "
                "  'system', '', '系统', '', 'system', '') "
                "ON CONFLICT (user_id) DO NOTHING;"
            )
        )
        await db.commit()
        print("✅ system 用户已创建（如缺失）")


if __name__ == "__main__":
    asyncio.run(_migrate())
