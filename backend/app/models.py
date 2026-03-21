"""
Database models for the LTI Virtual Tutor.

Tables:
 - lti_registrations : one per LTI Consumer block in Open edX (unique client_id)
 - lti_instances     : per-deployment tutor configuration (one per XBlock placement)
 - lti_sessions      : per (user × resource_link) session with isolation key
 - chat_messages     : chat history attached to a specific session key
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ─── Helper ───────────────────────────────────────────────────────────────────

def _uuid() -> str:
    return str(uuid.uuid4())


# ─── Trusted Issuer (register your Open edX platform ONCE) ────────────────────

class LtiTrustedIssuer(Base):
    """
    A trusted Open edX platform (issuer).

    Register each Open edX instance here ONCE. Two auto-registration strategies:

    1. OpenID Connect Discovery (preferred):
       Backend calls {issuer}/.well-known/openid-configuration automatically.

    2. Fallback JWKS URL (for Open edX Tutor which returns 404 on discovery):
       Provide fallback_jwks_url + fallback_auth_endpoint. These are used when
       the discovery endpoints return non-200 responses.
       In Open edX Tutor, the platform-wide JWKS URL is:
         http://local.openedx.io/api/lti_consumer/v1/public_keysets/
       Or use any per-block keyset URL — they all return the same platform key.
    """
    __tablename__ = "lti_trusted_issuers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    issuer: Mapped[str] = mapped_column(String(512), unique=True, index=True, nullable=False)
    label: Mapped[str] = mapped_column(String(256), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Fallback endpoints — used when OpenID Connect Discovery fails (e.g. Open edX Tutor)
    # These are optional: if set, they override failed discovery instead of raising an error.
    fallback_jwks_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    fallback_auth_endpoint: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    fallback_token_endpoint: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)



class LtiPlatformRegistration(Base):
    """
    Stores the Open edX credentials for each individual LTI Consumer block.

    Each block in Open edX Studio exposes:
      - Client ID       (unique per block)
      - Keyset URL      (unique per block — used to verify JWTs from that block)
      - Access Token URL
      - Login URL       (same for all blocks on the same platform)

    You register each block here before they can launch the tutor.
    """
    __tablename__ = "lti_registrations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    # ── Values from Open edX Studio / LMS ─────────────────────────────────
    client_id: Mapped[str] = mapped_column(String(512), unique=True, index=True, nullable=False)
    issuer: Mapped[str] = mapped_column(String(512), nullable=False)          # e.g. http://local.openedx.io
    deployment_id: Mapped[str] = mapped_column(String(128), default="1")

    # Platform-provided endpoints (all visible in Open edX Studio)
    keyset_url: Mapped[str] = mapped_column(String(1024), nullable=False)      # "Keyset URL" in Studio
    auth_endpoint: Mapped[str] = mapped_column(String(1024), nullable=False)   # "Login URL" in Studio
    token_endpoint: Mapped[str] = mapped_column(String(1024), nullable=False)  # "Access Token URL" in Studio

    # ── Human-readable label (optional, for admin UI) ─────────────────────
    label: Mapped[str] = mapped_column(String(256), default="")

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    instances: Mapped[list["LtiInstance"]] = relationship("LtiInstance", back_populates="registration")


# ─── LTI Instance (one per XBlock placement in a course) ──────────────────────

class LtiInstance(Base):
    """
    Represents a single LTI block placement (resource_link_id).
    Auto-created on first launch from a registered block.
    Instructors configure the tutor persona and sharing settings here.
    """
    __tablename__ = "lti_instances"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    resource_link_id: Mapped[str] = mapped_column(String(512), unique=True, index=True, nullable=False)
    context_id: Mapped[str] = mapped_column(String(512), nullable=False)          # course
    deployment_id: Mapped[str] = mapped_column(String(512), nullable=False)

    # FK to platform registration — identifies which Open edX block launched this
    registration_id: Mapped[str] = mapped_column(String(36), ForeignKey("lti_registrations.id"), nullable=False)
    client_id: Mapped[str] = mapped_column(String(512), nullable=False)  # denormalised for quick access

    # Tutor persona
    tutor_name: Mapped[str] = mapped_column(String(128), default="Tutor Virtual")
    topic: Mapped[str] = mapped_column(String(256), default="")
    system_prompt: Mapped[str] = mapped_column(Text, default="Eres un tutor virtual amigable y experto.")
    welcome_message: Mapped[str] = mapped_column(Text, default="¡Hola! ¿En qué puedo ayudarte hoy?")

    # Mode: libre (free chat) | rag (answers from uploaded documents)
    mode: Mapped[str] = mapped_column(String(16), default="libre")

    # Context sharing: if set, all instances with the same share_group_id
    # within the same context (course) AND user will share chat history.
    share_context: Mapped[bool] = mapped_column(Boolean, default=False)
    share_group_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    registration: Mapped["LtiPlatformRegistration"] = relationship("LtiPlatformRegistration", back_populates="instances")
    sessions: Mapped[list["LtiSession"]] = relationship("LtiSession", back_populates="instance")
    challenges: Mapped[list["Challenge"]] = relationship(
        "Challenge", back_populates="instance", cascade="all, delete-orphan",
        order_by="Challenge.order"
    )


# ─── LTI Session (one per user × instance launch) ────────────────────────────

class LtiSession(Base):
    """
    Records a user's session with a specific LTI instance.

    isolation_key = SHA256(user_id + resource_link_id)
    When context sharing is on:
    isolation_key = SHA256(user_id + context_id + share_group_id)
    """
    __tablename__ = "lti_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    isolation_key: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)

    instance_id: Mapped[str] = mapped_column(String(36), ForeignKey("lti_instances.id"), nullable=False)

    # LTI user data (from JWT claims)
    user_id: Mapped[str] = mapped_column(String(512), nullable=False)
    user_name: Mapped[str] = mapped_column(String(256), default="")
    user_email: Mapped[str] = mapped_column(String(256), default="")
    user_role: Mapped[str] = mapped_column(String(64), default="student")    # student | instructor | admin
    course_name: Mapped[str] = mapped_column(String(512), default="")

    # Cookie session token (signed, stored in browser)
    session_token: Mapped[str] = mapped_column(String(512), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    instance: Mapped["LtiInstance"] = relationship("LtiInstance", back_populates="sessions")
    messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage", back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.created_at"
    )


# ─── Chat Message ─────────────────────────────────────────────────────────────

class ChatMessage(Base):
    """
    A single chat turn in a tutor session.
    role: 'user' | 'assistant'
    """
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("lti_sessions.id", ondelete="CASCADE"), nullable=False)

    role: Mapped[str] = mapped_column(String(16), nullable=False)   # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tokens_used: Mapped[int | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    session: Mapped["LtiSession"] = relationship("LtiSession", back_populates="messages")


# ─── RAG Documents (course-scoped PDFs for RAG mode) ──────────────────────────

class Document(Base):
    """
    A PDF document uploaded by an instructor for RAG mode.
    Scoped to context_id (course) — shared across all LTI blocks in the same course.
    """
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    context_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size: Mapped[int] = mapped_column(default=0)
    chunk_count: Mapped[int] = mapped_column(default=0)
    uploaded_by: Mapped[str] = mapped_column(String(256), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        "DocumentChunk", back_populates="document", cascade="all, delete-orphan"
    )


class DocumentChunk(Base):
    """A text chunk from a Document with its embedding vector (JSON)."""
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[str] = mapped_column(Text, nullable=False)  # JSON float array

    document: Mapped["Document"] = relationship("Document", back_populates="chunks")


# ─── Challenges ───────────────────────────────────────────────────────────────

class Challenge(Base):
    """
    A challenge (desafío) configured per LTI instance.
    Can be created manually or generated by AI.
    """
    __tablename__ = "challenges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    instance_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("lti_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(512), default="")
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer_guide: Mapped[str] = mapped_column(Text, default="")  # AI evaluation guide (not shown to student)
    order: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    instance: Mapped["LtiInstance"] = relationship("LtiInstance", back_populates="challenges")
    attempts: Mapped[list["ChallengeAttempt"]] = relationship(
        "ChallengeAttempt", back_populates="challenge", cascade="all, delete-orphan"
    )


class ChallengeAttempt(Base):
    """
    Tracks a student's progress on a specific challenge.
    Keyed by user_id + challenge_id so it persists across sessions and shared blocks.
    """
    __tablename__ = "challenge_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    challenge_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | passed
    attempts_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    challenge: Mapped["Challenge"] = relationship("Challenge", back_populates="attempts")
