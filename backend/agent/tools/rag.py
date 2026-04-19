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
from backend.database.chromadb import ALL_SUBJECT_TYPES, SubjectType


def infer_subject_type(text: str) -> SubjectType:
    lowered = text.lower()

    keyword_groups: list[tuple[SubjectType, tuple[str, ...]]] = [
        ("policy", ("南科大", "sustech", "校园", "食堂", "宿舍", "校历", "选课", "教务", "奖学金", "学位", "培养方案", "规章", "政策")),
        ("cs", ("计算机", "程序", "编程", "算法", "数据结构", "python", "java", "c++", "操作系统", "数据库")),
        ("math", ("数学", "微积分", "线性代数", "概率论", "统计学", "离散数学")),
        ("physics", ("物理", "力学", "电磁", "量子", "热学", "光学")),
        ("chemistry", ("化学", "有机", "无机", "分析化学", "物化")),
        ("biology", ("生物", "细胞", "遗传", "生态", "分子生物")),
        ("economics", ("经济", "宏观", "微观", "供给", "需求")),
        ("management", ("管理", "项目管理", "运营", "组织行为", "管理学")),
        ("law", ("法律", "法学", "条例", "合同", "侵权")),
        ("medicine", ("医学", "临床", "药理", "解剖", "病理")),
        ("literature", ("文学", "小说", "诗歌", "散文", "文艺")),
        ("history", ("历史", "近代史", "古代史", "世界史")),
        ("philosophy", ("哲学", "伦理", "形而上", "认识论", "逻辑学")),
        ("politics", ("政治", "马克思", "思政", "党史", "治理")),
        ("finance", ("金融", "投资", "证券", "基金", "期权")),
        ("electronics", ("电子", "电路", "单片机", "信号", "通信")),
        ("materials", ("材料", "金属", "高分子", "晶体", "纳米材料")),
        ("statistics", ("统计", "回归", "方差", "抽样", "假设检验")),
        ("ocean", ("海洋", "海洋科学", "海水", "海岸", "海洋生态")),
        ("geography", ("地理", "地图", "气候", "地貌", "地理信息")),
    ]

    for subject_type, keywords in keyword_groups:
        if any(keyword in lowered for keyword in keywords):
            return subject_type
    return "other"


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
    try:
        normalized_hint = subject_hint.strip().lower() if subject_hint else "unknown"
        if normalized_hint not in ALL_SUBJECT_TYPES and normalized_hint != "unknown":
            normalized_hint = infer_subject_type(query)

        collections = rag_service.resolve_collections(normalized_hint)
        results = rag_service.query_collections(query, collections)
        return json.dumps(
            {
                "chunks": results,
                "collections_queried": [c for c in collections],
            },
            ensure_ascii=False,
        )
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: RAG query failed: {exc}"


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
    return infer_subject_type(text)
