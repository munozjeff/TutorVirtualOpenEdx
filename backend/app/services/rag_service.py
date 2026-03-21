"""
RAG (Retrieval-Augmented Generation) service.

Retrieval runs 100% on this server using BM25 (pure Python, no external APIs).
The retrieved chunks are injected into the Gemini prompt as context.

Flow:
  1. ingest_pdf  → extract text → split into chunks → store in DB (no embeddings needed)
  2. retrieve_context → BM25 score chunks against query → return top-k as context string
  3. chat.py injects that context string into the Gemini system prompt
"""
from __future__ import annotations

import logging
import math
import re
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

CHUNK_SIZE = 1500       # characters per chunk
CHUNK_OVERLAP = 200     # overlap between consecutive chunks
TOP_K = 5               # chunks returned per query

# BM25 hyperparameters
BM25_K1 = 1.5
BM25_B = 0.75


# ─── Text utilities ────────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """Lowercase word tokenization."""
    return re.findall(r'\b\w+\b', text.lower())


def _split_text(text: str) -> list[str]:
    chunks, start = [], 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


# ─── BM25 scoring ──────────────────────────────────────────────────────────────

def _bm25_scores(
    query_tokens: list[str],
    corpus: list[list[str]],
) -> list[float]:
    """
    Compute BM25 score for each document in corpus against the query.
    Runs entirely in Python — no external services.
    """
    N = len(corpus)
    avgdl = sum(len(doc) for doc in corpus) / N if N else 1

    # Document frequency per term
    df: dict[str, int] = {}
    for doc in corpus:
        for term in set(doc):
            df[term] = df.get(term, 0) + 1

    scores: list[float] = []
    for doc in corpus:
        tf = Counter(doc)
        dl = len(doc)
        score = 0.0
        for term in query_tokens:
            if term not in tf:
                continue
            idf = math.log((N - df.get(term, 0) + 0.5) / (df.get(term, 0) + 0.5) + 1)
            tf_norm = (tf[term] * (BM25_K1 + 1)) / (
                tf[term] + BM25_K1 * (1 - BM25_B + BM25_B * dl / avgdl)
            )
            score += idf * tf_norm
        scores.append(score)

    return scores


# ─── Ingestion ─────────────────────────────────────────────────────────────────

async def ingest_pdf(db: AsyncSession, document_id: str, pdf_bytes: bytes) -> int:
    """
    Extract text from a PDF, split into chunks, and store in DB.
    No embeddings — BM25 retrieval works directly on the stored text.
    Returns the number of chunks created.
    """
    import io
    import pypdf
    from app.models import DocumentChunk

    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    pages = [page.extract_text() or "" for page in reader.pages]
    full_text = "\n\n".join(p for p in pages if p.strip())

    if not full_text.strip():
        log.warning("PDF document_id=%s produced no extractable text", document_id)
        return 0

    chunks = _split_text(full_text)
    log.info("Ingesting document_id=%s → %d chunks (BM25 mode)", document_id, len(chunks))

    for i, chunk in enumerate(chunks):
        db.add(DocumentChunk(
            document_id=document_id,
            chunk_index=i,
            content=chunk,
            embedding="[]",   # no vector embedding needed
        ))

    return len(chunks)


# ─── Retrieval ─────────────────────────────────────────────────────────────────

async def retrieve_context(
    db: AsyncSession,
    query: str,
    context_id: str,
    top_k: int = TOP_K,
) -> str:
    """
    BM25 retrieval: score all chunks for this course against the query,
    return the top-k concatenated as a context string.

    This runs entirely on the server — no external API calls.
    The returned context is then injected into the Gemini prompt.
    """
    from app.models import Document, DocumentChunk

    stmt = (
        select(DocumentChunk)
        .join(Document, DocumentChunk.document_id == Document.id)
        .where(Document.context_id == context_id)
    )
    result = await db.execute(stmt)
    chunks = result.scalars().all()

    if not chunks:
        return ""

    query_tokens = _tokenize(query)
    if not query_tokens:
        return ""

    corpus = [_tokenize(c.content) for c in chunks]
    scores = _bm25_scores(query_tokens, corpus)

    # Sort by score descending, take top-k with score > 0
    ranked = sorted(
        zip(scores, chunks),
        key=lambda x: x[0],
        reverse=True,
    )
    top_chunks = [c.content for score, c in ranked[:top_k] if score > 0]

    if not top_chunks:
        return ""

    log.info(
        "RAG retrieve: context_id=%s query='%s...' → %d chunks returned",
        context_id[:20], query[:40], len(top_chunks),
    )
    return "\n\n---\n\n".join(top_chunks)
