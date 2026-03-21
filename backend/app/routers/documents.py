"""
Documents router — RAG document management.

Endpoints:
  GET    /api/documents          → list PDFs uploaded for this course
  POST   /api/documents/upload   → upload and ingest a PDF (instructor only)
  DELETE /api/documents/{id}     → delete document + chunks (instructor only)
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_session, require_instructor
from app.models import Document, LtiSession
from app.services.rag_service import ingest_pdf

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["Documents — RAG"])

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


class DocumentOut(BaseModel):
    id: str
    filename: str
    file_size: int
    chunk_count: int
    uploaded_by: str
    created_at: str


# ─── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=list[DocumentOut])
async def list_documents(
    session: LtiSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
):
    """List all PDFs uploaded for this course (shared across all blocks)."""
    result = await db.execute(
        select(Document)
        .where(Document.context_id == session.instance.context_id)
        .order_by(Document.created_at.desc())
    )
    return [
        DocumentOut(
            id=d.id, filename=d.filename, file_size=d.file_size,
            chunk_count=d.chunk_count, uploaded_by=d.uploaded_by,
            created_at=d.created_at.isoformat(),
        )
        for d in result.scalars().all()
    ]


@router.post("/upload", response_model=DocumentOut, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    session: LtiSession = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload and ingest a PDF for RAG mode.
    Documents are course-scoped: all blocks in the same course share them.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se permiten archivos PDF.")

    pdf_bytes = await file.read()

    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")
    if len(pdf_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Archivo demasiado grande (máximo 20 MB).")

    # Create document record to get its ID
    doc = Document(
        context_id=session.instance.context_id,
        filename=file.filename,
        file_size=len(pdf_bytes),
        uploaded_by=session.user_name,
        chunk_count=0,
    )
    db.add(doc)
    await db.flush()

    # Ingest: extract text, chunk, embed, store
    try:
        chunk_count = await ingest_pdf(db, doc.id, pdf_bytes)
    except Exception as exc:
        log.error("PDF ingestion failed for '%s': %s", file.filename, exc)
        raise HTTPException(status_code=500, detail=f"Error al procesar el PDF: {exc}")

    doc.chunk_count = chunk_count
    db.add(doc)

    log.info(
        "Document uploaded: '%s' (%d chunks) course=%s by %s",
        file.filename, chunk_count, session.instance.context_id[:16], session.user_name,
    )
    return DocumentOut(
        id=doc.id, filename=doc.filename, file_size=doc.file_size,
        chunk_count=chunk_count, uploaded_by=doc.uploaded_by,
        created_at=doc.created_at.isoformat(),
    )


@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    session: LtiSession = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    """Delete a document and all its chunks."""
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.context_id == session.instance.context_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")

    await db.delete(doc)
    log.info("Document deleted: '%s'", doc.filename)
    return {"message": f"Documento '{doc.filename}' eliminado."}
