"""
backend/agent/tools/study_copilot.py
学习辅助工具：总结、概念提取、练习题生成。
依赖 materials 表中已向量化的文件，通过 file_id 索引。
"""

import json
import uuid
from pathlib import Path

import httpx
from pydantic_ai import RunContext
from sqlalchemy import select

from backend.agent.core import AgentDeps, agent
from backend.config import settings
from backend.database import chromadb as chromadb_module
from backend.database.chromadb import ALL_SUBJECT_TYPES, SubjectType
from backend.database.postgres import Material


def _as_int(value: object, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        try:
            return int(value)
        except Exception:
            return default
    try:
        s = str(value).strip()
    except Exception:
        return default
    if not s:
        return default
    try:
        return int(float(s))
    except Exception:
        return default


def _meta_get(meta: object, key: str) -> object | None:
    if isinstance(meta, dict):
        return meta.get(key)
    return None


def _coerce_subject_type(value: str | None) -> SubjectType:
    v = (value or "").strip().lower()
    if v in ALL_SUBJECT_TYPES:
        return v
    return "other"


def _normalize_file_ref(value: str) -> str:
    ref = (value or "").strip()
    if not ref:
        return ""
    if ref.endswith("...") or ref.endswith("…"):
        ref = ref.rstrip(".… ").strip()
    try:
        ref = Path(ref).name
    except Exception:
        pass
    return ref.strip()


async def _load_material(ctx: RunContext[AgentDeps], file_id: str) -> Material | None:
    raw = _normalize_file_ref(str(file_id))
    if not raw:
        return None

    try:
        file_uuid = uuid.UUID(raw)
    except Exception:
        file_uuid = None

    if file_uuid is not None:
        stmt = select(Material).where(
            Material.file_id == file_uuid, Material.user_id == ctx.deps.user.user_id
        )
        return await ctx.deps.db.scalar(stmt)

    user_id = ctx.deps.user.user_id
    exact = await ctx.deps.db.scalar(
        select(Material)
        .where(Material.user_id == user_id, Material.file_name.ilike(raw))
        .order_by(Material.uploaded_at.desc())
        .limit(1)
    )
    if exact is not None:
        return exact

    stem = Path(raw).stem.strip().lower()
    if stem:
        by_stem = await ctx.deps.db.scalar(
            select(Material)
            .where(Material.user_id == user_id, Material.file_name.ilike(f"{stem}.%"))
            .order_by(Material.uploaded_at.desc())
            .limit(1)
        )
        if by_stem is not None:
            return by_stem
        by_stem_prefix = await ctx.deps.db.scalar(
            select(Material)
            .where(Material.user_id == user_id, Material.file_name.ilike(f"{stem}%"))
            .order_by(Material.uploaded_at.desc())
            .limit(1)
        )
        if by_stem_prefix is not None:
            return by_stem_prefix

    fuzzy = await ctx.deps.db.scalar(
        select(Material)
        .where(Material.user_id == user_id, Material.file_name.ilike(f"%{raw}%"))
        .order_by(Material.uploaded_at.desc())
        .limit(1)
    )
    return fuzzy


def _get_file_chunks(file_id: str, subject_type: SubjectType) -> list[dict]:
    collection = chromadb_module.get_collection(subject_type)
    got = collection.get(where={"file_id": file_id})
    docs = got.get("documents") or []
    metas = got.get("metadatas") or [{}] * len(docs)
    chunks: list[dict] = []
    for doc, meta in zip(docs, metas):
        chunks.append(
            {
                "text": str(doc or ""),
                "chunk_index": _as_int(_meta_get(meta, "chunk_index")),
            }
        )
    chunks.sort(key=lambda c: c["chunk_index"])
    return chunks


def _pack_chunks(chunks: list[dict], *, max_chars: int) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    current_len = 0
    for c in chunks:
        idx = int(c.get("chunk_index", 0) or 0)
        text = str(c.get("text") or "").strip()
        if not text:
            continue
        entry = f"[Chunk {idx}]\n{text}\n"
        if current and current_len + len(entry) > max_chars:
            blocks.append("\n".join(current).strip())
            current = []
            current_len = 0
        current.append(entry)
        current_len += len(entry)
    if current:
        blocks.append("\n".join(current).strip())
    return blocks


async def _chat_complete(
    api_key: str, *, system: str, user: str, max_tokens: int
) -> str:
    if not (api_key or "").strip():
        raise ValueError("missing api key")
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{settings.DEEPSEEK_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key.strip()}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.2,
                "max_tokens": int(max_tokens),
            },
        )
    resp.raise_for_status()
    return str(resp.json()["choices"][0]["message"]["content"] or "").strip()


def _query_file_chunks(
    *,
    file_id: str,
    subject_type: SubjectType,
    query: str,
    limit: int = 8,
) -> list[dict]:
    if not (query or "").strip():
        return []
    collection = chromadb_module.get_collection(subject_type)
    try:
        total = int(collection.count())
    except Exception:
        total = 0
    if total <= 0:
        return []
    try:
        result = collection.query(
            query_texts=[query],
            n_results=min(int(limit), total),
            where={"file_id": file_id},
        )
    except Exception:
        return []
    docs = (result.get("documents") or [[]])[0] or []
    metas = (result.get("metadatas") or [[]])[0] or [{}] * len(docs)
    dists = (result.get("distances") or [[]])[0] or [0.0] * len(docs)
    out: list[dict] = []
    for doc, meta, dist in zip(docs, metas, dists):
        out.append(
            {
                "text": str(doc or ""),
                "chunk_index": _as_int(_meta_get(meta, "chunk_index")),
                "distance": float(dist or 0.0),
            }
        )
    out.sort(key=lambda x: (x["distance"], x["chunk_index"]))
    return out


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
    material = await _load_material(ctx, file_id)
    if material is None:
        return "ERROR:FILE_NOT_FOUND"
    if not material.vectorized:
        return "ERROR:NOT_VECTORIZED"

    subject_type = _coerce_subject_type(material.subject_type)
    chunks = _get_file_chunks(str(material.file_id), subject_type)
    if not chunks:
        return "ERROR:NOT_VECTORIZED"

    blocks = _pack_chunks(chunks, max_chars=12000)
    api_key = ctx.deps.llm_api_key
    try:
        per_block_summaries: list[str] = []
        system = "你是严谨的学习助手。只能基于给定讲义内容总结，不允许补充未出现的知识点。输出使用中文 Markdown。"
        for block in blocks[:6]:
            prompt = (
                "请阅读下面讲义片段，输出：\n"
                "1) 本段要点（3-8条）\n"
                "2) 关键术语及定义（最多8个）\n"
                "3) 可能的易错点/考试点（最多5条）\n"
                "要求：每条后标注引用的 Chunk 编号，例如“...（Chunk 12）”。\n\n"
                f"{block}"
            )
            per_block_summaries.append(
                await _chat_complete(
                    api_key, system=system, user=prompt, max_tokens=900
                )
            )

        merge_prompt = (
            f"文件名：{material.file_name}\n\n"
            "下面是多个片段的摘要草稿，请合并为一份结构化讲义总结，包含：\n"
            "- 概览（1段）\n"
            "- 章节要点（分点）\n"
            "- 核心概念表（术语：定义，保持简洁）\n"
            "- 复习清单（行动建议）\n"
            "要求：仍然只基于草稿内容，不要新增知识点；保留 Chunk 引用。\n\n"
            + "\n\n---\n\n".join(per_block_summaries)
        )
        merged = await _chat_complete(
            api_key, system=system, user=merge_prompt, max_tokens=1400
        )
        return merged
    except Exception:
        return "ERROR:LLM_UNAVAILABLE"


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
    material = await _load_material(ctx, file_id)
    if material is None:
        return "ERROR:FILE_NOT_FOUND"
    if not material.vectorized:
        return "ERROR:NOT_VECTORIZED"

    subject_type = _coerce_subject_type(material.subject_type)
    chunks = _get_file_chunks(str(material.file_id), subject_type)
    if not chunks:
        return "ERROR:NOT_VECTORIZED"

    n = max(1, min(int(num_questions or 5), 30))
    types = [str(t).strip() for t in (question_types or []) if str(t).strip()]
    allowed = {"mcq", "true_false", "short_answer"}
    types = [t for t in types if t in allowed] or ["mcq", "short_answer"]

    sample = chunks
    if len(sample) > 12:
        step = max(1, len(sample) // 12)
        sample = sample[::step][:12]
    context = "\n\n".join(
        f"[Chunk {c['chunk_index']}]\n{str(c['text'] or '').strip()}" for c in sample
    ).strip()

    api_key = ctx.deps.llm_api_key
    system = "你是严谨的出题助手。只能根据给定讲义片段出题，不允许引入片段之外的信息。输出必须是 JSON，不能包含其他文本。"
    prompt = (
        f"请基于下面讲义片段生成 {n} 道题，题型仅从 {types} 中选择。\n"
        "输出 JSON 格式：\n"
        '{ "questions": [ { "type": "mcq|true_false|short_answer", "question": "...", "options": ["A. ...","B. ...","C. ...","D. ..."], "answer": "...", "explanation": "...", "source_chunks": [12, 13] } ] }\n'
        "规则：\n"
        "- mcq 必须有 options 且 4 个选项\n"
        "- true_false 的 answer 只能是 true 或 false\n"
        "- short_answer 的 answer 为简短要点\n"
        "- 每题必须提供 source_chunks（引用 Chunk 编号列表）\n\n"
        f"{context}"
    )
    try:
        raw = await _chat_complete(api_key, system=system, user=prompt, max_tokens=1800)
    except Exception:
        return "ERROR:LLM_UNAVAILABLE"

    try:
        payload = json.loads(raw)
    except Exception:
        return "ERROR:LLM_OUTPUT_INVALID"
    return json.dumps(payload, ensure_ascii=False)


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
    material = await _load_material(ctx, file_id)
    if material is None:
        return "ERROR:FILE_NOT_FOUND"
    if not material.vectorized:
        return "ERROR:NOT_VECTORIZED"

    subject_type = _coerce_subject_type(material.subject_type)
    chunks = _get_file_chunks(str(material.file_id), subject_type)
    if not chunks:
        return "ERROR:NOT_VECTORIZED"

    sample = chunks
    if len(sample) > 10:
        step = max(1, len(sample) // 10)
        sample = sample[::step][:10]
    context = "\n\n".join(
        f"[Chunk {c['chunk_index']}]\n{str(c['text'] or '').strip()}" for c in sample
    ).strip()

    api_key = ctx.deps.llm_api_key
    system = "你是严谨的概念提取助手。只能基于给定片段提取概念，不允许补充外部知识。输出必须是 JSON。"
    prompt = (
        "请从讲义片段中提取 10-30 个核心概念，每个概念包含 term 与 definition，并附 source_chunk（单个编号）。\n"
        '输出 JSON：{ "concepts": [ { "term": "...", "definition": "...", "source_chunk": 12 } ] }\n\n'
        f"{context}"
    )
    try:
        raw = await _chat_complete(api_key, system=system, user=prompt, max_tokens=1400)
    except Exception:
        return "ERROR:LLM_UNAVAILABLE"

    try:
        payload = json.loads(raw)
    except Exception:
        return "ERROR:LLM_OUTPUT_INVALID"
    return json.dumps(payload, ensure_ascii=False)


@agent.tool
async def explain_material(
    ctx: RunContext[AgentDeps],
    file_id: str,
    question: str,
    keyword: str = "",
) -> str:
    """
    针对单个教材/课件文件做“RAG 检索 + LLM 讲解”。

    - 检索只在该 file_id 的 chunks 内进行，避免被其他材料干扰。
    - 若语义检索无果且 keyword 非空，回退到字面子串匹配。

    Returns:
        Markdown 字符串（中文），带 Chunk 引用。
        若文件不存在或未向量化，返回 "ERROR:FILE_NOT_FOUND" / "ERROR:NOT_VECTORIZED"。
    """
    material = await _load_material(ctx, file_id)
    if material is None:
        return "ERROR:FILE_NOT_FOUND"
    if not material.vectorized:
        return "ERROR:NOT_VECTORIZED"

    question = (question or "").strip()
    if not question:
        return "ERROR:EMPTY_QUESTION"

    subject_type = _coerce_subject_type(material.subject_type)
    results = _query_file_chunks(
        file_id=str(material.file_id),
        subject_type=subject_type,
        query=question,
        limit=10,
    )

    if not results and keyword.strip():
        all_chunks = _get_file_chunks(str(material.file_id), subject_type)
        kw = keyword.strip()
        hits = [
            c
            for c in all_chunks
            if kw in str(c.get("text") or "") and str(c.get("text") or "").strip()
        ]
        results = hits[:10]

    if not results:
        return "ERROR:NO_RELEVANT_CHUNKS"

    context = "\n\n".join(
        f"[Chunk {r.get('chunk_index', 0)}]\n{str(r.get('text') or '').strip()}"
        for r in results
        if str(r.get("text") or "").strip()
    ).strip()
    if not context:
        return "ERROR:NO_RELEVANT_CHUNKS"

    system = (
        "你是严谨的课程助教。只能基于给定讲义片段回答，不允许补充片段之外的知识。"
        "如果片段不足以回答，直接说明无法从讲义中确定。"
        "输出中文 Markdown，并在每个关键结论后标注引用 Chunk 编号，例如“...（Chunk 12）”。"
    )
    prompt = (
        f"文件名：{material.file_name}\n"
        f"问题：{question}\n\n"
        "讲义片段：\n"
        f"{context}\n\n"
        "请给出解释：\n"
        "- 直接回答\n"
        "- 关键推导/依据（引用 Chunk）\n"
        "- 若有定义或公式，单独列出\n"
        "- 最后给 3 个复习问题（同样只基于片段）\n"
    )
    try:
        return await _chat_complete(
            ctx.deps.llm_api_key,
            system=system,
            user=prompt,
            max_tokens=1400,
        )
    except Exception:
        return "ERROR:LLM_UNAVAILABLE"
