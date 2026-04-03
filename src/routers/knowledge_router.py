from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.database.models import User, get_db
from src.knowledge import (
    KnowledgeBaseError,
    KnowledgeDocumentNotFoundError,
    add_knowledge_document,
    delete_knowledge_document,
    get_knowledge_document_detail,
    list_knowledge_documents,
    search_knowledge_base,
)
from src.services import record_audit_event, require_permission

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class KnowledgeDocumentCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)
    source_uri: str | None = Field(default=None, max_length=500)
    metadata: dict | None = None


@router.get("/documents")
def list_documents(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("knowledge:view")),
):
    return list_knowledge_documents(db, page=page, page_size=page_size)


@router.post("/documents")
def create_document(
    req: KnowledgeDocumentCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("knowledge:manage")),
):
    try:
        payload = add_knowledge_document(
            db,
            title=req.title,
            content=req.content,
            source_uri=req.source_uri,
            metadata=req.metadata,
            created_by=current_user.username,
        )
    except KnowledgeBaseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    record_audit_event(
        db,
        actor=current_user.username,
        event_type="knowledge.document.create",
        object_type="knowledge_document",
        object_id=payload["document"]["document_id"],
        details={
            "title": req.title,
            "source_uri": req.source_uri,
            "created": payload["created"],
        },
    )
    return payload


@router.get("/documents/{document_id}")
def get_document(
    document_id: str,
    chunk_page: int = Query(default=1, ge=1),
    chunk_page_size: int = Query(default=8, ge=1, le=20),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("knowledge:view")),
):
    try:
        return get_knowledge_document_detail(
            db,
            document_id,
            chunk_page=chunk_page,
            chunk_page_size=chunk_page_size,
        )
    except KnowledgeDocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/documents/{document_id}")
def remove_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("knowledge:manage")),
):
    try:
        payload = delete_knowledge_document(db, document_id)
    except KnowledgeDocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KnowledgeBaseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    record_audit_event(
        db,
        actor=current_user.username,
        event_type="knowledge.document.delete",
        object_type="knowledge_document",
        object_id=document_id,
        details={"title": payload.get("title")},
    )
    return {"success": True, "document": payload}


@router.get("/search")
def search_documents(
    query: str = Query(..., min_length=1),
    limit: int = Query(default=4, ge=1, le=10),
    _: User = Depends(require_permission("knowledge:view")),
):
    try:
        return search_knowledge_base(query, limit=limit)
    except KnowledgeBaseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
