"""
backend/agent/tools/study_copilot.py
学习辅助工具：总结、概念提取、练习题生成。
依赖 materials 表中已向量化的文件，通过 file_id 索引。
"""

from pydantic_ai import RunContext

from backend.agent.core import AgentDeps, agent


@agent.tool
async def generate_summary(
    ctx: RunContext[AgentDeps],
    file_id: str,
) -> str:
    """
    为指定教材文件生成结构化摘要（章节要点 + 核心概念）。

    Args:
        file_id: materials.file_id（UUID 字符串），文件必须属于当前用户且已向量化

    Returns:
        Markdown 格式的摘要字符串，可直接展示在聊天区。
        若文件不存在或未向量化，返回 "ERROR:FILE_NOT_FOUND" 或 "ERROR:NOT_VECTORIZED"
    """
    # TODO:
    # 1. 验证 file_id 属于 ctx.deps.user 且 vectorized=True
    # 2. 从 ChromaDB 取出该文件所有 chunk（按 chunk_index 排序）
    # 3. 分批调用 LLM 生成 per-chunk 要点，最后合并为结构化摘要
    # 4. 返回 Markdown 字符串
    raise NotImplementedError


@agent.tool
async def generate_quiz(
    ctx: RunContext[AgentDeps],
    file_id: str,
    num_questions: int,
    question_types: list[str],
) -> str:
    """
    基于指定教材文件生成练习题。

    Args:
        file_id:        materials.file_id
        num_questions:  题目数量（建议 5~20）
        question_types: 题型列表，可选值：["mcq", "true_false", "short_answer"]
                        可多选，如 ["mcq", "true_false"]

    Returns:
        JSON 字符串，格式：
        {
          "questions": [
            {
              "type": "mcq",
              "question": str,
              "options": ["A. ...", "B. ...", "C. ...", "D. ..."],  # mcq only
              "answer": str,
              "explanation": str
            }
          ]
        }
        题目内容必须完全来源于文件内容（不得 hallucinate）。
    """
    # TODO:
    # 1. 验证 file_id 归属和向量化状态
    # 2. 从 ChromaDB 随机采样 N 个 chunk 作为出题素材
    # 3. 构造 few-shot prompt 调用 LLM 生成题目，要求 LLM 仅基于给定 chunk 出题
    # 4. 解析 LLM 输出为结构化 JSON 并返回
    raise NotImplementedError


@agent.tool
async def extract_key_concepts(
    ctx: RunContext[AgentDeps],
    file_id: str,
) -> str:
    """
    从教材文件中提取核心概念及其简要定义，用于快速复习。

    Args:
        file_id: materials.file_id

    Returns:
        JSON 字符串，格式：
        {
          "concepts": [
            {"term": str, "definition": str, "source_chunk": int}
          ]
        }
    """
    # TODO:
    # 1. 取出所有 chunk
    # 2. LLM 逐 chunk 提取 term-definition 对
    # 3. 去重合并后返回
    raise NotImplementedError
