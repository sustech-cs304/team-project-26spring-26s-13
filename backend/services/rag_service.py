"""
backend/services/rag_service.py
RAG 检索服务：学科分类剪枝 + 多 Collection 查询。
"""

from backend.database.chromadb import SubjectType, ALL_SUBJECT_TYPES, query_collections
from backend.config import settings


def resolve_collections(subject_hint: str) -> list[SubjectType]:
    """
    根据 subject_hint 决定查询哪些 ChromaDB Collection。

    剪枝策略：
    - subject_hint == "unknown"：查全部 Collection
    - subject_hint 是合法 SubjectType：查该 Collection + "other"（other 必查）
    - subject_hint 不合法：回退到查全部

    Args:
        subject_hint: LLM 返回的学科分类，来自 tools/rag.classify_subject

    Returns:
        要查询的 Collection 名称列表（去重）
    """
    # TODO:
    # if subject_hint == "unknown" or subject_hint not in ALL_SUBJECT_TYPES:
    #     return list(ALL_SUBJECT_TYPES)
    # collections = {subject_hint, "other"}  # other 必查
    # return list(collections)
    raise NotImplementedError


def format_rag_context(chunks: list[dict], max_tokens: int = 4000) -> str:
    """
    将 ChromaDB 返回的 chunk 列表格式化为注入 LLM prompt 的上下文字符串。
    按 distance 排序，截断至 max_tokens 估算字符数以避免超出上下文窗口。

    Args:
        chunks:     query_collections 返回的 chunk 列表
        max_tokens: 估算的 token 上限（按 1 token ≈ 4 字符估算）

    Returns:
        格式化后的上下文字符串，每个 chunk 带来源标注：
        "[Source: {file_name}]\n{text}\n\n"
    """
    # TODO:
    # result = []
    # budget = max_tokens * 4  # 字符预算
    # for chunk in sorted(chunks, key=lambda c: c["distance"]):
    #     entry = f"[Source: {chunk['file_name']}]\n{chunk['text']}\n\n"
    #     if len(entry) > budget: break
    #     result.append(entry); budget -= len(entry)
    # return "".join(result)
    raise NotImplementedError
