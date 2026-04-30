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
    在向量数据库中检索与 query 相关的文档片段，用于增强 LLM 回答。

    Args:
        query:        用户的原始问题（或经过改写的检索 query），用于向量语义搜索
        subject_hint: 学科分类，建议不确定时传 "unknown" 查全部集合。可选值：
                      "cs" | "electronics" | "materials" | "math" | "physics" |
                      "chemistry" | "biology" | "geography" | "philosophy" | "history" |
                      "literature" | "politics" | "finance" | "statistics" | "ocean" |
                      "economics" | "law" | "management" | "medicine" | "policy" |
                      "other" | "unknown"
        keyword:      从问题中提取的核心关键词（1-8 字，例如"贝加尔湖"、"挂科"、
                      "binary tree"），用于向量检索无果时的关键词兜底匹配。
                      中文问题**必须**填写；英文问题可留空。

    Returns:
        JSON 字符串：{"chunks": [...], "collections_queried": [...]}
        chunks 按 distance 升序；若向量检索无果，会回退到关键词兜底。
    """
    # 第一步：按学科剪枝做向量语义检索
    collections = rag_service.resolve_collections(subject_hint)
    try:
        results = chromadb_module.query_collections(query, collections)
    except Exception:
        results = []

    # 第二步兜底：猜错学科 → 扩展到全部集合再向量检索一次
    if not results and subject_hint != "unknown":
        from backend.database.chromadb import ALL_SUBJECT_TYPES

        collections = list(ALL_SUBJECT_TYPES)
        try:
            results = chromadb_module.query_collections(query, collections)
        except Exception:
            results = []

    # 第三步兜底：向量检索仍无果 → 用 keyword 做字面子串匹配
    # 这是中文场景的关键兜底（默认英文 embedding 对中文语义差）
    if not results and keyword.strip():
        try:
            results = chromadb_module.keyword_search(keyword.strip())
        except Exception:
            results = []

    return json.dumps(
        {
            "chunks": [
                {
                    "text": r["text"],
                    "file_name": r["file_name"],
                    "subject_type": r["subject_type"],
                    "distance": r["distance"],
                }
                for r in results
            ],
            "collections_queried": collections,
        },
        ensure_ascii=False,
    )


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
