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
from backend.database import chromadb as chromadb_module
from backend.database.chromadb import SubjectType


def infer_subject_type(text: str) -> SubjectType:
    """
    用轻量关键词启发式做学科分类，供非 Agent 场景复用。

    material_service 在文件上传时需要一个同步 helper，
    不能直接依赖异步的 `classify_subject` tool。
    """
    lowered = text.lower()

    keyword_map: list[tuple[SubjectType, tuple[str, ...]]] = [
        (
            "cs",
            (
                "algorithm",
                "binary tree",
                "database",
                "python",
                "java",
                "代码",
                "编程",
                "算法",
                "数据结构",
                "计算机",
            ),
        ),
        (
            "electronics",
            ("circuit", "signal", "semiconductor", "电路", "模电", "数电", "信号"),
        ),
        ("materials", ("material", "alloy", "polymer", "材料", "合金", "高分子")),
        (
            "math",
            (
                "matrix",
                "calculus",
                "linear algebra",
                "probability",
                "矩阵",
                "微积分",
                "线代",
                "数学",
            ),
        ),
        (
            "physics",
            (
                "quantum",
                "mechanics",
                "thermodynamics",
                "物理",
                "量子",
                "力学",
                "热力学",
            ),
        ),
        (
            "chemistry",
            ("organic", "inorganic", "reaction", "chemistry", "化学", "有机", "反应"),
        ),
        ("biology", ("cell", "gene", "biology", "生物", "细胞", "基因")),
        ("geography", ("climate", "terrain", "geography", "地理", "气候")),
        ("philosophy", ("ethics", "metaphysics", "philosophy", "哲学", "伦理")),
        ("history", ("dynasty", "war", "history", "历史", "朝代")),
        ("literature", ("novel", "poetry", "literature", "文学", "小说", "诗歌")),
        ("politics", ("government", "election", "politics", "政治", "政府", "选举")),
        ("finance", ("stock", "valuation", "finance", "投资", "金融", "估值", "股票")),
        (
            "statistics",
            ("regression", "variance", "statistics", "统计", "回归", "方差"),
        ),
        ("ocean", ("marine", "ocean", "sea", "海洋", "海水")),
        (
            "economics",
            ("economics", "gdp", "inflation", "economics", "经济", "通货膨胀"),
        ),
        ("law", ("law", "contract", "legal", "法律", "合同", "法条")),
        ("management", ("management", "operation", "hr", "管理", "运营", "组织行为")),
        ("medicine", ("disease", "clinical", "medicine", "医学", "临床", "疾病")),
        (
            "policy",
            (
                "policy",
                "handbook",
                "guideline",
                "规定",
                "政策",
                "学位要求",
                "手册",
                "南科大",
            ),
        ),
    ]

    for subject, keywords in keyword_map:
        if any(keyword in lowered for keyword in keywords):
            return subject
    return "other"


@agent.tool
async def query_rag(
    ctx: RunContext[AgentDeps],
    query: str,
    subject_hint: str,
    keyword: str = "",
) -> str:
    """
    在知识库中检索与 query 相关的文档片段。

    检索策略（自动路由）：
      1. 文件名精确匹配 —— 从 query 和 keyword 中提取关键词查倒排索引，
         命中后只在匹配文件中向量检索。适合"温铁军的材料""中国城镇化.pdf"。
      2. 学科剪枝向量检索 —— 在相关学科 collection 中语义搜索。
      3. 全局向量检索 —— 学科不明确时查全部 collection。
      4. 关键词字面搜索 —— 向量检索无果时的最后兜底。

    Args:
        query:        用户的原始问题，用于向量语义搜索和关键词提取
        subject_hint: 学科分类，不确定时传 "unknown"
        keyword:      【重要】用户明确提到的人名（温铁军、费孝通）、书名、
                      文件名关键词（中国城镇化、CS302、课件），请务必填写。
                      这将触发精确文件匹配，速度极快。中文问题强烈建议填写。

    Returns:
        JSON：{"chunks": [...], "collections_queried": [...], "mode": "..."}
        mode 取值：single_file（命中单一文件，可深度解读）|
                  multi_file（多文件拼合）| fallback（降级结果）
    """
    import re as _re
    from backend.services.material_service import search_by_file_name

    results: list[dict] = []

    search_keyword = (keyword or "").strip()
    if not search_keyword:
        search_keyword = _extract_search_keyword(query)

    if search_keyword:
        candidate_ids: list[str] = search_by_file_name(search_keyword, limit=30)
        if candidate_ids:
            try:
                results = chromadb_module.query_collections_by_file_ids(
                    query,
                    candidate_ids,
                    n_results=10,
                )
            except Exception:
                results = []
            if results:
                unique_files = len({r["file_id"] for r in results})
                mode = "single_file" if unique_files <= 2 else "multi_file"
                return json.dumps(
                    {
                        "chunks": _format_chunks(results),
                        "collections_queried": ["filename_index"],
                        "search_method": "filename_lookup",
                        "mode": mode,
                    },
                    ensure_ascii=False,
                )

    collections = rag_service.resolve_collections(subject_hint)
    try:
        results = chromadb_module.query_collections(query, collections)
    except Exception:
        results = []

    if not results and subject_hint != "unknown":
        from backend.database.chromadb import ALL_SUBJECT_TYPES

        collections = list(ALL_SUBJECT_TYPES)
        try:
            results = chromadb_module.query_collections(query, collections)
        except Exception:
            results = []

    if not results:
        fallback_kw = (keyword or "").strip() or _extract_search_keyword(query)
        if fallback_kw:
            try:
                results = chromadb_module.keyword_search(fallback_kw)
            except Exception:
                results = []

    mode = "fallback" if not results else "multi_file"
    return json.dumps(
        {
            "chunks": _format_chunks(results),
            "collections_queried": collections,
            "mode": mode,
        },
        ensure_ascii=False,
    )


def _extract_search_keyword(text: str) -> str:
    import re as _re

    t = (text or "").strip()
    if not t:
        return ""
    cjk_names = _re.findall(r"[\u4e00-\u9fff]{2,3}(?:[·•.][\u4e00-\u9fff]{1,3})?", t)
    if cjk_names:
        return " ".join(cjk_names[:3])
    codes = _re.findall(r"[A-Z]{2,5}\d{2,4}", t)
    if codes:
        return codes[0]
    en_words = _re.findall(r"[A-Z][a-z]{2,}", t)
    if en_words:
        return " ".join(en_words[:3])
    return t[:16]


def _format_chunks(results: list[dict]) -> list[dict]:
    return [
        {
            "text": r["text"],
            "file_name": r["file_name"],
            "subject_type": r["subject_type"],
            "distance": r["distance"],
        }
        for r in results
    ]


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
    return await rag_service.classify_subject_llm(text, ctx.deps.llm_api_key)
