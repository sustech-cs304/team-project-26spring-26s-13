"""
backend/services/rag_service.py
RAG 检索服务：学科分类剪枝 + 多 Collection 查询。
"""

from backend.database.chromadb import SubjectType, ALL_SUBJECT_TYPES, query_collections
from backend.config import settings
import httpx


async def classify_text_subject(text: str, api_key: str = None) -> SubjectType:
    """
    调用 LLM 判断一段文本（文件摘要或用户问题）属于哪个学科分类。
    
    Args:
        text: 需要分类的文本
        api_key: 可选的 DeepSeek API Key。若不提供，将尝试使用 settings.DEEPSEEK_API_KEY。
        
    Returns:
        SubjectType 枚举字符串之一。若无法分类或报错，返回 "other"
    """
    valid_subjects = ", ".join(ALL_SUBJECT_TYPES)
    few_shot_prompt = f"""你是一个学科分类助手。根据输入文本，判断它属于哪个学科分类。
只能返回以下分类中的一个，不要输出任何其他内容：
{valid_subjects}

示例：
输入：二叉树的层序遍历算法
输出：cs

输入：南科大挂科政策是什么
输出：policy

输入：线性代数矩阵乘法
输出：math

输入：有机化学反应机理
输出：chemistry

输入：如何分析股票估值
输出：finance

输入：{text[:500]}
输出："""

    key = api_key or settings.DEEPSEEK_API_KEY
    if not key:
        return "other"
        
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.DEEPSEEK_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.DEEPSEEK_MODEL,
                    "messages": [{"role": "user", "content": few_shot_prompt}],
                    "max_tokens": 16,
                    "temperature": 0.0,
                },
            )
        resp.raise_for_status()
        result = resp.json()
        subject = result["choices"][0]["message"]["content"].strip().lower()
        if subject in ALL_SUBJECT_TYPES:
            return subject
    except Exception:
        pass

    return "other"


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
    if subject_hint == "unknown" or subject_hint not in ALL_SUBJECT_TYPES:
        return list(ALL_SUBJECT_TYPES)
    collections: set[SubjectType] = {subject_hint, "other"}  # type: ignore[arg-type]
    return list(collections)


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
    result: list[str] = []
    budget = max_tokens * 4  # 字符预算（1 token ≈ 4 chars）
    for chunk in sorted(chunks, key=lambda c: c["distance"]):
        entry = f"[Source: {chunk['file_name']}]\n{chunk['text']}\n\n"
        if len(entry) > budget:
            break
        result.append(entry)
        budget -= len(entry)
    return "".join(result)
