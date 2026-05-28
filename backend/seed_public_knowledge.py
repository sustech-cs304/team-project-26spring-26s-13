"""
backend/seed_public_knowledge.py

播种公有知识库：扫描 data/campus_handbook/ 目录，
将校园手册、政策文件等向量化存入向量库，标记 is_public=True，
所有用户均可检索。

用法：
  python backend/seed_public_knowledge.py                # 扫描并播种
  python backend/seed_public_knowledge.py --clear         # 清除后重新播种
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from backend.config import settings
from backend.database.chromadb import delete_file_chunks
from backend.database.postgres import AsyncSessionLocal, Material, User
from backend.services.material_service import _create_material_from_bytes

logger = logging.getLogger(__name__)

SYSTEM_USER_ID = "00000000-0000-4000-8000-000000000000"
SYSTEM_CAS_ACCOUNT = "system"
PUBLIC_DIR = Path(__file__).resolve().parent.parent / "data" / "campus_handbook"


async def _ensure_system_user() -> User:
    async with AsyncSessionLocal() as db:
        stmt = select(User).where(User.cas_account == SYSTEM_CAS_ACCOUNT)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            logger.info("seed: system_user_exists id=%s", user.user_id)
            return user

        user = User(
            user_id=SYSTEM_USER_ID,
            username="system",
            password_hash="",
            display_name="系统",
            major="",
            cas_account=SYSTEM_CAS_ACCOUNT,
            cas_password_encrypted=None,
            llm_api_key_encrypted=None,
            working_dir=str(Path.home()),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info("seed: system_user_created id=%s", user.user_id)
        return user


def _list_public_files() -> list[Path]:
    if not PUBLIC_DIR.exists():
        logger.warning("seed: public_dir_not_found path=%s", PUBLIC_DIR)
        return []
    files: list[Path] = []
    for ext in ("*.pdf", "*.txt", "*.docx", "*.doc"):
        for f in PUBLIC_DIR.glob(ext):
            if f.is_file():
                files.append(f)
    return sorted(files)


async def seed_public_knowledge(clear: bool = False) -> int:
    print(f"=== 公有知识库播种 ===\n")
    print(f"目录: {PUBLIC_DIR}")
    files = _list_public_files()
    if not files:
        print("未找到文件。请将 PDF/TXT/DOCX 放入 data/campus_handbook/ 后重试。")
        print(f"\n示例: mkdir {PUBLIC_DIR}")
        print(f"      cp ~/Downloads/学生手册.pdf {PUBLIC_DIR}/")
        return 0

    print(f"找到 {len(files)} 个文件:\n")
    for fp in files:
        print(f"  📄 {fp.name}  ({fp.stat().st_size // 1024} KB)")

    user = await _ensure_system_user()
    print(f"\n系统用户: {user.user_id}")

    if clear:
        print("清除旧索引...")
        async with AsyncSessionLocal() as db:
            stmt = select(Material).where(Material.is_public == True)
            result = await db.execute(stmt)
            for m in result.scalars().all():
                delete_file_chunks(str(m.file_id), m.subject_type)
                await db.delete(m)
                print(f"  已删除: {m.file_name}")
            await db.commit()

    seeded = 0
    for fp in files:
        print(f"\n播种: {fp.name} ...")
        file_bytes = fp.read_bytes()

        content_type_map = {
            ".pdf": "application/pdf",
            ".txt": "text/plain",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".doc": "application/msword",
        }
        content_type = content_type_map.get(fp.suffix.lower(), "application/octet-stream")

        try:
            async with AsyncSessionLocal() as db:
                info = await _create_material_from_bytes(
                    db=db,
                    user=user,
                    file_name=fp.name,
                    content_type=content_type,
                    file_bytes=file_bytes,
                    is_public=True,
                )
            if info:
                print(f"  ✅ 已播种: {fp.name} → {info.subject_type}")
                seeded += 1
            else:
                print(f"  ⚠️ 跳过（可能不支持）")
        except Exception as e:
            print(f"  ❌ 失败: {e}")

    print(f"\n=== 完成: {seeded}/{len(files)} 个文件已播种 ===")
    return seeded


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    clear = "--clear" in sys.argv
    asyncio.run(seed_public_knowledge(clear=clear))
