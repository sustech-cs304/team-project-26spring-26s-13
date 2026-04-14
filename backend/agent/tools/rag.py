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

from pydantic_ai import RunContext

from backend.agent.core import AgentDeps, agent
from backend.services import rag_service
from backend.database.chromadb import SubjectType


@agent.tool
async def query_rag(
    ctx: RunContext[AgentDeps],
    query: str,
    subject_hint: str,
) -> str:
    """
    在向量数据库中检索与 query 相关的文档片段，用于增强 LLM 回答。

    Args:
        query:        用户的原始问题（或经过改写的检索 query）
        subject_hint: LLM 判断的学科分类，必须是以下之一：
                      "cs" | "electronics" | "materials" | "math" | "physics" |
                      "chemistry" | "biology" | "geography" | "philosophy" | "history" |
                      "literature" | "politics" | "finance" | "statistics" | "ocean" |
                      "economics" | "law" | "management" | "medicine" | "policy" | "other" | "unknown"
                      传 "unknown" 时查全部集合

    Returns:
        JSON 字符串，格式：
        {
          "chunks": [
            {"text": str, "file_name": str, "subject_type": str, "distance": float}
          ],
          "collections_queried": ["cs", "other"]
        }
        chunks 已按 distance 升序排列（最相关在前）。
        若无匹配结果，chunks 为空列表。
    """
    # TODO:
    # collections = rag_service.resolve_collections(subject_hint)
    # results = chromadb_module.query_collections(query, collections)
    # return json.dumps({"chunks": results, "collections_queried": [c for c in collections]})
    raise NotImplementedError


@agent.tool
async def classify_subject(
    ctx: RunContext[AgentDeps],
    text: str,
) -> str:
    """
    调用 LLM 判断一段文本（文件摘要或用户问题）属于哪个学科分类。
    用于两个场景：
      1. 文件上传时确定存入哪个 ChromaDB collection
      2. RAG 查询前确定查哪些 collection（剪枝）

    Args:
        text: 需要分类的文本（文件前几百字或用户问题）

    Returns:
        SubjectType 枚举字符串之一（共 20 类）：
        "cs" | "electronics" | "materials" | "math" | "physics" |
        "chemistry" | "biology" | "geography" | "philosophy" | "history" |
        "literature" | "politics" | "finance" | "statistics" | "ocean" |
        "economics" | "law" | "management" | "medicine" | "policy" | "other"
    """
    # TODO:
    # 使用轻量 LLM 调用（few-shot prompt）分类
    # 若置信度低则返回 "other"
    raise NotImplementedError
