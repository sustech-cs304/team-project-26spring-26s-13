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
        # TODO: 初始化 PersistentClient，路径 = settings.CHROMA_PERSIST_DIR
        _client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
    return _client


def get_collection(subject_type: SubjectType) -> Collection:
    """
    获取或创建指定学科类型的 Collection。
    Collection 不存在时自动创建（get_or_create 语义）。
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
    """
    if not chunks:
        return
    collection = get_collection(subject_type)
    ids = [f"{file_id}_{i}" for i in range(len(chunks))]
    metadatas = [
        {
            "file_id": file_id,
            "file_name": file_name,
            "chunk_index": i,
            "subject_type": subject_type
        }
        for i in range(len(chunks))
    ]
    collection.add(ids=ids, documents=chunks, metadatas=metadatas)


def delete_file_chunks(file_id: str, subject_type: SubjectType) -> None:
    """
    删除某个文件的所有向量 chunk（用于文件删除时的清理）。
    """
    try:
        collection = get_collection(subject_type)
        collection.delete(where={"file_id": file_id})
    except Exception:
        # If collection doesn't exist yet, it's fine
        pass


# ── Read / Query Operations ───────────────────────────────────────────────────

def query_collections(
    query_text: str,
    subject_types: list[SubjectType],
    n_results_per_collection: int = 5,
) -> list[dict]:
    """
    在指定的多个 Collection 中并行查询，合并返回最相关的 chunk 列表。
    """
    results: list[dict] = []
    for st in subject_types:
        try:
            collection = get_collection(st)
            q_res = collection.query(query_texts=[query_text], n_results=n_results_per_collection)
            
            # Chroma returns lists of lists for query_texts
            if not q_res or not q_res["documents"]:
                continue
                
            docs = q_res["documents"][0]
            metas = q_res["metadatas"][0]
            dists = q_res["distances"][0] if q_res.get("distances") else [0.0] * len(docs)
            
            for i in range(len(docs)):
                results.append({
                    "text": docs[i],
                    "file_id": metas[i].get("file_id"),
                    "file_name": metas[i].get("file_name"),
                    "chunk_index": metas[i].get("chunk_index"),
                    "subject_type": st,
                    "distance": dists[i]
                })
        except Exception:
            # Collection might not exist
            continue
            
    # Sort by distance (lower is better)
    results.sort(key=lambda x: x["distance"])
    return results


def get_all_file_chunks(file_id: str, subject_type: SubjectType) -> list[str]:
    """
    获取某个文件的所有文本 chunk，按 chunk_index 排序。
    """
    try:
        collection = get_collection(subject_type)
        res = collection.get(where={"file_id": file_id}, include=["documents", "metadatas"])
        if not res or not res["documents"]:
            return []
        
        # Combine and sort by chunk_index
        combined = []
        for doc, meta in zip(res["documents"], res["metadatas"]):
            combined.append((meta.get("chunk_index", 0), doc))
        
        combined.sort(key=lambda x: x[0])
        return [doc for _, doc in combined]
    except Exception:
        return []
