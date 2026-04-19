"""
backend/agent/tools/study_copilot.py
学习辅助工具：总结、概念提取、练习题生成。
依赖 materials 表中已向量化的文件，通过 file_id 索引。
"""

import json
import uuid
from pydantic_ai import RunContext
from sqlalchemy import select

from backend.agent.core import AgentDeps, agent
from backend.database.postgres import Material
from backend.database.chromadb import get_all_file_chunks


@agent.tool
async def generate_summary(
    ctx: RunContext[AgentDeps],
    file_id: str,
) -> str:
    """
    为指定教材文件生成结构化摘要（章节要点 + 核心概念）。
    """
    try:
        file_uuid = uuid.UUID(file_id)
    except ValueError:
        return "ERROR:INVALID_FILE_ID"

    # 1. 验证所有权和状态
    stmt = select(Material).where(Material.file_id == file_uuid, Material.user_id == ctx.deps.user.user_id)
    material = (await ctx.deps.db.execute(stmt)).scalar_one_or_none()
    
    if not material:
        return "ERROR:FILE_NOT_FOUND"
    if not material.vectorized:
        return "ERROR:NOT_VECTORIZED"

    # 2. 从 ChromaDB 取出所有 chunk
    chunks = get_all_file_chunks(str(file_uuid), material.subject_type)
    if not chunks:
        return "ERROR:NO_CONTENT_FOUND"

    # 3. 简单的汇总（目前先返回前几个 chunk 作为演示，实际应调用 LLM）
    # TODO: 接入真正的大模型摘要逻辑
    full_text = "\n\n".join(chunks[:10]) # 限制长度
    return f"### Summary of {material.file_name}\n\n{full_text[:5000]}"


@agent.tool
async def generate_quiz(
    ctx: RunContext[AgentDeps],
    file_id: str,
    num_questions: int,
    question_types: list[str],
) -> str:
    """
    基于指定教材文件生成练习题。
    """
    try:
        file_uuid = uuid.UUID(file_id)
    except ValueError:
        return json.dumps({"error": "INVALID_FILE_ID"})

    stmt = select(Material).where(Material.file_id == file_uuid, Material.user_id == ctx.deps.user.user_id)
    material = (await ctx.deps.db.execute(stmt)).scalar_one_or_none()
    
    if not material:
        return json.dumps({"error": "FILE_NOT_FOUND"})

    chunks = get_all_file_chunks(str(file_uuid), material.subject_type)
    if not chunks:
        return json.dumps({"error": "NO_CONTENT_FOUND"})

    # TODO: 接入真正的大模型出题逻辑
    # 模拟数据
    questions = [
        {
            "type": question_types[0] if question_types else "mcq",
            "question": f"Based on {material.file_name}, what is the core concept discussed in the first chapter?",
            "options": ["Option A", "Option B", "Option C", "Option D"],
            "answer": "Option A",
            "explanation": "This is a placeholder explanation based on the retrieved document content."
        }
    ]
    return json.dumps({"questions": questions}, ensure_ascii=False)


@agent.tool
async def extract_key_concepts(
    ctx: RunContext[AgentDeps],
    file_id: str,
) -> str:
    """
    从教材文件中提取核心概念及其简要定义。
    """
    try:
        file_uuid = uuid.UUID(file_id)
    except ValueError:
        return json.dumps({"error": "INVALID_FILE_ID"})

    stmt = select(Material).where(Material.file_id == file_uuid, Material.user_id == ctx.deps.user.user_id)
    material = (await ctx.deps.db.execute(stmt)).scalar_one_or_none()
    
    if not material:
        return json.dumps({"error": "FILE_NOT_FOUND"})

    chunks = get_all_file_chunks(str(file_uuid), material.subject_type)
    if not chunks:
        return json.dumps({"error": "NO_CONTENT_FOUND"})

    # TODO: 接入真正的大模型概念提取逻辑
    concepts = [
        {"term": "Sample Concept", "definition": "A placeholder definition extracted for demonstration.", "source_chunk": 0}
    ]
    return json.dumps({"concepts": concepts}, ensure_ascii=False)
