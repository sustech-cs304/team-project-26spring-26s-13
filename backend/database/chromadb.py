"""
backend/database/chromadb.py
ChromaDB 向量数据库客户端封装。
每个学科类型对应一个独立 Collection，用于 RAG 检索时的剪枝。

Collection 命名规则："{subject_type}"
  - cs          计算机科学与技术
  - electronics 电子与电气工程
  - materials   材料科学与工程
  - math        数学
  - physics     物理
  - chemistry   化学
  - biology     生物
  - geography   地理
  - philosophy  哲学
  - history     历史
  - literature  文学
  - politics    政治
  - finance     金融
  - statistics  统计
  - ocean       海洋科学
  - economics   经济
  - law         法律
  - management  管理
  - medicine    医学
  - policy      学校政策与规章制度
  - other       未分类（每次 RAG 必查）

向量 Metadata schema（每个 chunk）：
  {
    "file_id":    str,   # 对应 materials.file_id
    "file_name":  str,
    "chunk_index": int,  # 该文件第几个 chunk
    "subject_type": str
  }
"""

from typing import Literal
from pathlib import Path

import chromadb
from chromadb import Collection

from backend.config import settings

SubjectType = Literal[
    "cs", "electronics", "materials", "math", "physics",
    "chemistry", "biology", "geography", "philosophy", "history",
    "literature", "politics", "finance", "statistics", "ocean",
    "economics", "law", "management", "medicine", "policy", "other"
]
ALL_SUBJECT_TYPES: list[SubjectType] = [
    "cs", "electronics", "materials", "math", "physics",
    "chemistry", "biology", "geography", "philosophy", "history",
    "literature", "politics", "finance", "statistics", "ocean",
    "economics", "law", "management", "medicine", "policy", "other"
]


# ── Client singleton ──────────────────────────────────────────────────────────

_client: chromadb.ClientAPI | None = None


def get_chroma_client() -> chromadb.ClientAPI:
    """
    返回持久化的 ChromaDB 客户端单例。
    数据持久化路径由 settings.CHROMA_PERSIST_DIR 控制。
    """
    global _client
    if _client is None:
        Path(settings.CHROMA_PERSIST_DIR).mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
    return _client


def get_collection(subject_type: SubjectType) -> Collection:
    """
    获取或创建指定学科类型的 Collection。
    Collection 不存在时自动创建（get_or_create 语义）。

    Args:
        subject_type: 学科分类枚举值

    Returns:
        对应的 ChromaDB Collection 对象
    """
    client = get_chroma_client()
    return client.get_or_create_collection(name=subject_type)


# ── Write Operations ──────────────────────────────────────────────────────────

def add_chunks(
    subject_type: SubjectType,
    file_id: str,
    file_name: str,
    chunks: list[str],
) -> None:
    """
    将文件的所有文本 chunk 写入对应 Collection。
    ID 格式："{file_id}_{chunk_index}"，保证全局唯一且可按文件批量删除。

    Args:
        subject_type: 该文件的学科分类
        file_id:      materials.file_id（UUID 字符串）
        file_name:    原始文件名，写入 metadata 供引用显示
        chunks:       已切好的文本块列表

    Returns:
        None（写入失败抛出异常）
    """
    collection = get_collection(subject_type)
    normalized_chunks = [chunk.strip() for chunk in chunks if chunk and chunk.strip()]
    if not normalized_chunks:
        return

    ids = [f"{file_id}_{i}" for i in range(len(normalized_chunks))]
    metadatas = [
        {
            "file_id": file_id,
            "file_name": file_name,
            "chunk_index": i,
            "subject_type": subject_type,
        }
        for i in range(len(normalized_chunks))
    ]
    collection.add(ids=ids, documents=normalized_chunks, metadatas=metadatas)


def delete_file_chunks(file_id: str, subject_type: SubjectType) -> None:
    """
    删除某个文件的所有向量 chunk（用于文件删除时的清理）。

    Args:
        file_id:      materials.file_id
        subject_type: 文件所在的 Collection

    Returns:
        None
    """
    collection = get_collection(subject_type)
    collection.delete(where={"file_id": file_id})


# ── Read / Query Operations ───────────────────────────────────────────────────

def query_collections(
    query_text: str,
    subject_types: list[SubjectType],
    n_results_per_collection: int = 5,
) -> list[dict]:
    """
    在指定的多个 Collection 中并行查询，合并返回最相关的 chunk 列表。
    调用方（rag_service.py）负责决定查询哪些 Collection（剪枝逻辑在那里）。

    Args:
        query_text:                用户查询的原始文本
        subject_types:             要查询的 Collection 列表
        n_results_per_collection:  每个 Collection 返回的 top-k 数量

    Returns:
        list[dict]，每项格式：
        {
            "text":         str,   # chunk 原文
            "file_id":      str,
            "file_name":    str,
            "chunk_index":  int,
            "subject_type": str,
            "distance":     float  # 越小越相关
        }
    """
    merged: list[dict] = []
    seen_ids: set[str] = set()

    for subject_type in dict.fromkeys(subject_types):
        collection = get_collection(subject_type)
        if collection.count() <= 0:
            continue

        result = collection.query(
            query_texts=[query_text],
            n_results=n_results_per_collection,
        )
        ids = result.get("ids", [[]])
        documents = result.get("documents", [[]])
        metadatas = result.get("metadatas", [[]])
        distances = result.get("distances", [[]])

        for item_id, document, metadata, distance in zip(
            ids[0] if ids else [],
            documents[0] if documents else [],
            metadatas[0] if metadatas else [],
            distances[0] if distances else [],
        ):
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)
            metadata = metadata or {}
            merged.append(
                {
                    "text": document or "",
                    "file_id": str(metadata.get("file_id", "")),
                    "file_name": str(metadata.get("file_name", "")),
                    "chunk_index": int(metadata.get("chunk_index", 0)),
                    "subject_type": str(metadata.get("subject_type", subject_type)),
                    "distance": float(distance if distance is not None else 999999.0),
                }
            )

    return sorted(merged, key=lambda item: item["distance"])
