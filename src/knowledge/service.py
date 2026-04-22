"""
知识库服务。

职责拆分：
1. SQLite 负责文档与切片元数据。
2. Chroma 负责向量持久化与近邻检索。
3. OpenAI embeddings 只在入库与查询时按需调用。
"""
from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from src.config import config
from src.database.models import KnowledgeChunk, KnowledgeDocument, SessionLocal
from src.services.system_settings_service import get_knowledge_settings


class KnowledgeBaseError(RuntimeError):
    """知识库通用错误。"""


class KnowledgeDocumentNotFoundError(KnowledgeBaseError):
    """知识库文档不存在。"""


class KnowledgeBaseService:
    """封装知识库的元数据管理、向量写入与检索。"""

    def __init__(self):
        self._workspace_dir = Path(__file__).resolve().parents[2] / ".hydro_workspace" / "knowledge"
        self._workspace_dir.mkdir(parents=True, exist_ok=True)
        self._vector_dir = self._workspace_dir / "chroma"
        self._vector_dir.mkdir(parents=True, exist_ok=True)
        self._client = None
        self._collection = None

    def list_documents(self, db: Session, *, page: int = 1, page_size: int = 10) -> dict[str, Any]:
        normalized_page = max(page, 1)
        normalized_page_size = max(1, min(page_size, 50))
        query = db.query(KnowledgeDocument)
        total = query.count()
        items = (
            query.order_by(KnowledgeDocument.updated_at.desc(), KnowledgeDocument.id.desc())
            .offset((normalized_page - 1) * normalized_page_size)
            .limit(normalized_page_size)
            .all()
        )
        return {
            "documents": [item.to_dict() for item in items],
            "pagination": self._build_pagination(total=total, page=normalized_page, page_size=normalized_page_size),
        }

    def get_document_detail(
        self,
        db: Session,
        document_id: str,
        *,
        chunk_page: int = 1,
        chunk_page_size: int = 8,
    ) -> dict[str, Any]:
        document = db.query(KnowledgeDocument).filter(KnowledgeDocument.document_id == document_id).first()
        if not document:
            raise KnowledgeDocumentNotFoundError(f"知识文档不存在: {document_id}")

        normalized_page = max(chunk_page, 1)
        normalized_page_size = max(1, min(chunk_page_size, 20))
        chunk_query = db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == document_id)
        total_chunks = chunk_query.count()
        chunks = (
            chunk_query.order_by(KnowledgeChunk.chunk_index.asc())
            .offset((normalized_page - 1) * normalized_page_size)
            .limit(normalized_page_size)
            .all()
        )
        payload = document.to_dict()
        payload["metadata"] = document.metadata_json or {}
        payload["preview"] = document.content[:240] + ("..." if len(document.content) > 240 else "")
        return {
            "document": payload,
            "chunks": [chunk.to_dict() for chunk in chunks],
            "pagination": self._build_pagination(total=total_chunks, page=normalized_page, page_size=normalized_page_size),
        }

    def add_document(
        self,
        db: Session,
        *,
        title: str,
        content: str,
        source_uri: str | None = None,
        metadata: dict[str, Any] | None = None,
        created_by: str = "system",
    ) -> dict[str, Any]:
        normalized_title = (title or "").strip()
        normalized_content = self._normalize_content(content)
        if not normalized_title:
            raise KnowledgeBaseError("知识文档标题不能为空。")
        if not normalized_content:
            raise KnowledgeBaseError("知识文档内容不能为空。")

        checksum = hashlib.sha256(normalized_content.encode("utf-8")).hexdigest()
        existing = db.query(KnowledgeDocument).filter(KnowledgeDocument.checksum == checksum).first()
        if existing:
            return {"created": False, "document": existing.to_dict()}

        _, chunk_size, chunk_overlap = get_knowledge_settings(db)
        chunks = self._chunk_text(
            normalized_content,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        embeddings = self._embed_texts(chunks)
        collection = self._get_collection()

        document = KnowledgeDocument(
            title=normalized_title,
            source_uri=(source_uri or "").strip() or None,
            content=normalized_content,
            checksum=checksum,
            status="indexing",
            chunk_count=0,
            metadata_json=metadata or {},
            created_by=created_by,
        )
        db.add(document)
        db.flush()

        chunk_ids: list[str] = []
        vector_metadatas: list[dict[str, Any]] = []

        try:
            for index, chunk_text in enumerate(chunks):
                chunk = KnowledgeChunk(
                    document_id=document.document_id,
                    chunk_index=index,
                    content=chunk_text,
                    metadata_json={
                        "title": normalized_title,
                        "source_uri": document.source_uri,
                        "chunk_index": index,
                    },
                )
                db.add(chunk)
                db.flush()
                chunk_ids.append(chunk.chunk_id)
                vector_metadatas.append(
                    {
                        "document_id": document.document_id,
                        "title": normalized_title,
                        "source_uri": document.source_uri or "",
                        "chunk_index": index,
                    }
                )

            collection.upsert(
                ids=chunk_ids,
                documents=chunks,
                embeddings=embeddings,
                metadatas=vector_metadatas,
            )

            document.status = "ready"
            document.chunk_count = len(chunks)
            db.commit()
            db.refresh(document)
            return {"created": True, "document": document.to_dict()}
        except Exception:
            db.rollback()
            if chunk_ids:
                try:
                    collection.delete(ids=chunk_ids)
                except Exception:
                    pass
            raise

    def delete_document(self, db: Session, document_id: str) -> dict[str, Any]:
        document = db.query(KnowledgeDocument).filter(KnowledgeDocument.document_id == document_id).first()
        if not document:
            raise KnowledgeDocumentNotFoundError(f"知识文档不存在: {document_id}")

        payload = document.to_dict()
        chunk_ids = [chunk.chunk_id for chunk in document.chunks]
        if chunk_ids:
            self._get_collection().delete(ids=chunk_ids)
        db.delete(document)
        db.commit()
        return payload

    def search(self, query: str, *, limit: int | None = None) -> dict[str, Any]:
        normalized_query = (query or "").strip()
        if not normalized_query:
            raise KnowledgeBaseError("检索语句不能为空。")

        collection = self._get_collection()
        top_k, _, _ = self._load_knowledge_settings()
        requested_limit = max(1, min(limit or top_k, 10))
        if collection.count() == 0:
            return {"query": normalized_query, "results": []}

        query_embedding = self._embed_texts([normalized_query])[0]
        raw = collection.query(
            query_embeddings=[query_embedding],
            n_results=requested_limit,
            include=["documents", "metadatas", "distances"],
        )

        documents = raw.get("documents", [[]])
        metadatas = raw.get("metadatas", [[]])
        distances = raw.get("distances", [[]])
        results = []
        for index, document_text in enumerate(documents[0] if documents else []):
            metadata = (metadatas[0] if metadatas else [])[index] if metadatas else {}
            distance = (distances[0] if distances else [])[index] if distances else None
            results.append(
                {
                    "rank": index + 1,
                    "document_id": metadata.get("document_id"),
                    "title": metadata.get("title"),
                    "source_uri": metadata.get("source_uri") or None,
                    "chunk_index": metadata.get("chunk_index"),
                    "score": self._distance_to_score(distance),
                    "content": document_text,
                }
            )
        return {"query": normalized_query, "results": results}

    def _get_collection(self):
        if self._collection is not None:
            return self._collection

        try:
            import chromadb
        except ModuleNotFoundError as exc:
            raise KnowledgeBaseError("缺少 chromadb 依赖，请先安装 requirements.txt。") from exc

        if self._client is None:
            self._client = chromadb.PersistentClient(path=str(self._vector_dir))
        self._collection = self._client.get_or_create_collection(
            name="hydro_knowledge_base",
            metadata={"hnsw:space": "cosine"},
        )
        return self._collection

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        api_key = config.EMBEDDING_API_KEY or config.OPENAI_API_KEY
        if not api_key:
            raise KnowledgeBaseError("尚未配置 embeddings API Key，无法构建知识库向量。")

        try:
            from openai import OpenAI
        except ModuleNotFoundError as exc:
            raise KnowledgeBaseError("缺少 openai 依赖，请先安装 requirements.txt。") from exc

        client = OpenAI(api_key=api_key, base_url=config.OPENAI_BASE_URL)
        vectors: list[list[float]] = []
        for start in range(0, len(texts), 32):
            batch = texts[start:start + 32]
            response = client.embeddings.create(
                model=config.EMBEDDING_MODEL_NAME,
                input=batch,
            )
            vectors.extend([item.embedding for item in response.data])
        return vectors

    def _chunk_text(self, content: str, *, chunk_size: int, chunk_overlap: int) -> list[str]:
        normalized_size = max(300, chunk_size)
        normalized_overlap = max(0, min(chunk_overlap, normalized_size // 2))
        chunks: list[str] = []
        start = 0

        while start < len(content):
            hard_end = min(len(content), start + normalized_size)
            soft_break = content.rfind("\n\n", start + normalized_size // 2, hard_end)
            end = soft_break if soft_break > start else hard_end
            candidate = content[start:end].strip()

            # 避免切片落在纯空白位置，保证每次写入向量库的文本都是可检索的正文。
            if not candidate:
                candidate = content[start:hard_end].strip()
                end = hard_end

            if candidate:
                chunks.append(candidate)

            if end >= len(content):
                break

            next_start = max(0, end - normalized_overlap)
            if next_start <= start:
                next_start = end
            start = next_start

        return chunks or [content.strip()]

    def _normalize_content(self, content: str) -> str:
        return (content or "").replace("\r\n", "\n").strip()

    def _load_knowledge_settings(self) -> tuple[int, int, int]:
        """知识库查询路径没有显式 db，会话按需创建以读取全局业务配置。"""
        db = SessionLocal()
        try:
            return get_knowledge_settings(db)
        finally:
            db.close()

    def _build_pagination(self, *, total: int, page: int, page_size: int) -> dict[str, Any]:
        total_pages = max(1, math.ceil(total / page_size)) if total else 1
        return {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "has_prev": page > 1,
            "has_next": page < total_pages,
        }

    def _distance_to_score(self, distance: Any) -> float | None:
        if distance is None:
            return None
        try:
            value = float(distance)
        except (TypeError, ValueError):
            return None
        return round(max(0.0, 1.0 - value), 4)


_knowledge_service: KnowledgeBaseService | None = None


def get_knowledge_service() -> KnowledgeBaseService:
    global _knowledge_service
    if _knowledge_service is None:
        _knowledge_service = KnowledgeBaseService()
    return _knowledge_service


def list_knowledge_documents(db: Session, *, page: int = 1, page_size: int = 10) -> dict[str, Any]:
    return get_knowledge_service().list_documents(db, page=page, page_size=page_size)


def get_knowledge_document_detail(
    db: Session,
    document_id: str,
    *,
    chunk_page: int = 1,
    chunk_page_size: int = 8,
) -> dict[str, Any]:
    return get_knowledge_service().get_document_detail(
        db,
        document_id,
        chunk_page=chunk_page,
        chunk_page_size=chunk_page_size,
    )


def add_knowledge_document(
    db: Session,
    *,
    title: str,
    content: str,
    source_uri: str | None = None,
    metadata: dict[str, Any] | None = None,
    created_by: str = "system",
) -> dict[str, Any]:
    return get_knowledge_service().add_document(
        db,
        title=title,
        content=content,
        source_uri=source_uri,
        metadata=metadata,
        created_by=created_by,
    )


def delete_knowledge_document(db: Session, document_id: str) -> dict[str, Any]:
    return get_knowledge_service().delete_document(db, document_id)


def search_knowledge_base(query: str, *, limit: int | None = None) -> dict[str, Any]:
    return get_knowledge_service().search(query, limit=limit)
