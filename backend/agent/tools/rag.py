"""
backend/agent/tools/rag.py
RAG 检索工具：根据查询内容进行学科剪枝后查询向量数据库，返回增强上下文。

剪枝策略：
  - LLM 先判断问题属于哪个学科（cs/electronics/materials/math/physics/chemistry/
    biology/geography/philosophy/history/literature/politics/finance/statistics/
    ocean/economics/law/management/medicine/other）
  - "other" 集合必查（存放未能分类的内容）
  - 若明确属于某学科，则查该学科集合 + other
  - 若无法判断，则查全部集合
"""

import json
from pydantic_ai import RunContext

from backend.agent.core import AgentDeps, agent
from backend.services import rag_service
from backend.database.chromadb import SubjectType, query_collections


@agent.tool
async def query_rag(
    ctx: RunContext[AgentDeps],
    query: str,
    subject_hint: str,
) -> str:
    """
    在向量数据库中检索与 query 相关的文档片段，用于增强 LLM 回答。
    """
    collections = rag_service.resolve_collections(subject_hint)
    results = query_collections(query, collections)
    return json.dumps({
        "chunks": results,
        "collections_queried": [str(c) for c in collections]
    }, ensure_ascii=False)


@agent.tool
async def classify_subject(
    ctx: RunContext[AgentDeps],
    text: str,
) -> str:
    """
    调用 LLM 判断一段文本（文件摘要或用户问题）属于哪个学科分类。
    """
    return await classify_subject_standalone(text)


async def classify_subject_standalone(text: str) -> str:
    """
    独立版本，不依赖 AgentDeps，供 material_service 调用。
    简化版：目前只返回 other，或者可以接一个简单的正则表达式判断。
    TODO: 接入真正的轻量 LLM 分类器
    """
    # 简单的关键词启发式判断
    text_lower = text.lower()
    if any(k in text_lower for k in ["python", "java", "algorithm", "software", "code", "programming"]):
        return "cs"
    if any(k in text_lower for k in ["integral", "derivative", "theorem", "math", "equation"]):
        return "math"
    if any(k in text_lower for k in ["policy", "rule", "standard", "requirement", "student handbook"]):
        return "policy"
    return "other"
