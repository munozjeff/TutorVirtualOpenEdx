"""
Chat API router.

Endpoints:
  POST /api/chat         → Send a message, get AI reply
  GET  /api/chat/history → Retrieve chat history for current session
  DELETE /api/chat/history → Clear chat history for current session
"""
from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_session
from app.models import Challenge, ChallengeAttempt, ChatMessage, LtiInstance, LtiSession
from app.services.ai_service import get_ai_provider
from app.services.rag_service import retrieve_context

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["Chat"])

MAX_HISTORY_MESSAGES = 40


# ─── Schemas ──────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str


class MessageOut(BaseModel):
    role: str
    content: str
    created_at: str

    class Config:
        from_attributes = True


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    instance_name: str
    challenge_passed: bool = False      # True if this message passed a challenge
    next_challenge_id: str | None = None


# ─── Challenge helpers ─────────────────────────────────────────────────────────

async def _get_or_create_attempt(
    db: AsyncSession, challenge_id: str, user_id: str
) -> ChallengeAttempt:
    res = await db.execute(
        select(ChallengeAttempt).where(
            ChallengeAttempt.challenge_id == challenge_id,
            ChallengeAttempt.user_id == user_id,
        )
    )
    attempt = res.scalars().first()
    if not attempt:
        attempt = ChallengeAttempt(
            challenge_id=challenge_id,
            user_id=user_id,
            status="pending",
            attempts_count=0,
        )
        db.add(attempt)
        await db.flush()
    return attempt


async def _load_challenge_context(
    db: AsyncSession, session: LtiSession
) -> tuple[Challenge | None, ChallengeAttempt | None, str]:
    """
    Returns (current_challenge, attempt, shared_summary).
    current_challenge = first pending challenge for this instance.
    shared_summary = text about sibling block challenge status (if shared group).
    """
    instance = session.instance

    # Load challenges for this instance ordered by order
    chall_res = await db.execute(
        select(Challenge)
        .where(Challenge.instance_id == instance.id)
        .order_by(Challenge.order)
    )
    challenges = chall_res.scalars().all()

    current_challenge: Challenge | None = None
    current_attempt: ChallengeAttempt | None = None

    for challenge in challenges:
        attempt = await _get_or_create_attempt(db, challenge.id, session.user_id)
        if attempt.status != "passed":
            current_challenge = challenge
            current_attempt = attempt
            break

    # Build shared group summary (other blocks in same share_group)
    shared_summary = ""
    if instance.share_context and instance.share_group_id:
        # Get all instances with same group in same course (excluding current)
        siblings_res = await db.execute(
            select(LtiInstance).where(
                LtiInstance.context_id == instance.context_id,
                LtiInstance.share_group_id == instance.share_group_id,
                LtiInstance.id != instance.id,
            )
        )
        siblings = siblings_res.scalars().all()

        if siblings:
            lines = []
            for sib in siblings:
                sib_challs_res = await db.execute(
                    select(Challenge).where(Challenge.instance_id == sib.id).order_by(Challenge.order)
                )
                sib_challenges = sib_challs_res.scalars().all()
                for sc in sib_challenges:
                    att_res = await db.execute(
                        select(ChallengeAttempt).where(
                            ChallengeAttempt.challenge_id == sc.id,
                            ChallengeAttempt.user_id == session.user_id,
                        )
                    )
                    att = att_res.scalars().first()
                    status = att.status if att else "pending"
                    attempts_n = att.attempts_count if att else 0
                    label = "✅ SUPERADO" if status == "passed" else f"⏳ PENDIENTE ({attempts_n} intento(s))"
                    block_name = sib.tutor_name or sib.topic or "Bloque anterior"
                    lines.append(f'- Desafío "{sc.title or sc.question[:60]}…" en "{block_name}": {label}')

            if lines:
                shared_summary = (
                    "\n\n[HISTORIAL DE DESAFÍOS DEL GRUPO COMPARTIDO]:\n"
                    + "\n".join(lines)
                    + "\nTen en cuenta este historial al orientar al estudiante."
                )

    return current_challenge, current_attempt, shared_summary


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/history", response_model=List[MessageOut], summary="Get chat history")
async def get_history(
    session: LtiSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at)
    )
    result = await db.execute(stmt)
    messages = result.scalars().all()
    return [
        MessageOut(
            role=m.role,
            content=m.content,
            created_at=m.created_at.isoformat(),
        )
        for m in messages
    ]


@router.post("", response_model=ChatResponse, summary="Send a chat message")
async def send_message(
    body: ChatRequest,
    session: LtiSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
):
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    # Load recent history
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(MAX_HISTORY_MESSAGES)
    )
    result = await db.execute(stmt)
    recent = list(reversed(result.scalars().all()))
    history = [{"role": m.role, "content": m.content} for m in recent]

    instance = session.instance
    system_prompt = instance.system_prompt
    if instance.topic:
        system_prompt += f"\n\nTema del tutor: {instance.topic}"
    system_prompt += f"\n\nEstás hablando con {session.user_name} ({session.user_role}) del curso: {session.course_name}."

    # ── RAG mode ──────────────────────────────────────────────────────────────
    if instance.mode == "rag":
        from app.models import Document
        from sqlalchemy import select as sa_select
        docs_check = await db.execute(
            sa_select(Document).where(Document.context_id == instance.context_id).limit(1)
        )
        has_documents = docs_check.scalars().first() is not None

        if not has_documents:
            system_prompt += (
                "\n\n[MODO RAG ACTIVO - SIN DOCUMENTOS]: No hay material cargado para este curso todavía. "
                "Informa al estudiante que el instructor aún no ha subido documentos y que por ahora "
                "no puedes responder preguntas del curso. Sé amable pero no inventes información."
            )
        else:
            context = await retrieve_context(db, body.message, instance.context_id)
            if context:
                system_prompt += (
                    "\n\n[DOCUMENTACIÓN DEL CURSO]:\n"
                    + context
                    + "\n\n[INSTRUCCIÓN IMPORTANTE]: Responde ÚNICAMENTE basándote en la documentación "
                    "proporcionada arriba. No uses conocimiento externo. "
                    "Si la pregunta no está relacionada con el contenido de esa documentación, "
                    "indica amablemente que esa pregunta no corresponde al tema estudiado en este curso "
                    "y pide al estudiante que haga preguntas sobre el material del curso."
                )
            else:
                system_prompt += (
                    "\n\n[INSTRUCCIÓN IMPORTANTE]: La pregunta del estudiante no corresponde al contenido "
                    "de los documentos de este curso. Debes indicar amablemente que no puedes responder "
                    "esa pregunta porque no está relacionada con el tema estudiado. "
                    "Invítalo a preguntar sobre el material del curso."
                )

    # ── Challenge mode ────────────────────────────────────────────────────────
    challenge_passed = False
    next_challenge_id: str | None = None

    current_challenge, current_attempt, shared_summary = await _load_challenge_context(db, session)

    if current_challenge and current_attempt:
        all_challs_res = await db.execute(
            select(Challenge).where(Challenge.instance_id == instance.id).order_by(Challenge.order)
        )
        all_challs = all_challs_res.scalars().all()
        total_count = len(all_challs)

        passed_count = 0
        for _c in all_challs:
            _att_res = await db.execute(
                select(ChallengeAttempt).where(
                    ChallengeAttempt.challenge_id == _c.id,
                    ChallengeAttempt.user_id == session.user_id,
                )
            )
            _att = _att_res.scalars().first()
            if _att and _att.status == "passed":
                passed_count += 1

        system_prompt += (
            f"\n\n[MODO DESAFÍO ACTIVO - Desafío {passed_count + 1} de {total_count}]\n"
            f"Título: {current_challenge.title}\n"
            f"Pregunta del desafío: {current_challenge.question}\n"
            f"Intentos previos del estudiante: {current_attempt.attempts_count}\n"
        )
        if current_challenge.answer_guide:
            system_prompt += f"Guía de evaluación (SOLO para ti, NO la reveles): {current_challenge.answer_guide}\n"

        system_prompt += (
            "\nINSTRUCCIONES PARA EL DESAFÍO:\n"
            "- Evalúa si la respuesta del estudiante demuestra comprensión correcta del desafío.\n"
            "- Si la respuesta ES CORRECTA: comienza tu respuesta con exactamente '[CORRECTO]' "
            "y felicita al estudiante de forma motivadora.\n"
            "- Si la respuesta NO ES CORRECTA: usa el método socrático. "
            "Haz preguntas guía, usa analogías, descompón el concepto. "
            "NO des la respuesta directamente. NO empieces con '[CORRECTO]'.\n"
            "- Si el estudiante NO ha respondido aún y solo saluda o pregunta algo general, "
            "presenta el desafío claramente y espera su respuesta.\n"
        )

    if shared_summary:
        system_prompt += shared_summary

    # ── Get AI response ───────────────────────────────────────────────────────
    provider = get_ai_provider()
    try:
        reply = await provider.chat(
            system_prompt=system_prompt,
            history=history,
            user_message=body.message,
        )
    except Exception as e:
        log.error("AI provider error: %s", e)
        raise HTTPException(status_code=503, detail=f"AI service unavailable: {e}")

    # ── Process challenge result ───────────────────────────────────────────────
    if current_challenge and current_attempt:
        current_attempt.attempts_count += 1
        if reply.startswith("[CORRECTO]"):
            current_attempt.status = "passed"
            challenge_passed = True
            log.info("Challenge passed: challenge_id=%s user=%s", current_challenge.id[:8], session.user_id[:16])

            # Find next challenge
            all_challs = (await db.execute(
                select(Challenge).where(Challenge.instance_id == instance.id).order_by(Challenge.order)
            )).scalars().all()
            found_current = False
            for c in all_challs:
                if found_current:
                    next_challenge_id = c.id
                    break
                if c.id == current_challenge.id:
                    found_current = True

        db.add(current_attempt)

    # Persist messages
    db.add(ChatMessage(session_id=session.id, role="user", content=body.message))
    db.add(ChatMessage(session_id=session.id, role="assistant", content=reply))

    return ChatResponse(
        reply=reply,
        session_id=session.id,
        instance_name=instance.tutor_name,
        challenge_passed=challenge_passed,
        next_challenge_id=next_challenge_id,
    )


@router.delete("/history", summary="Clear chat history for this session")
async def clear_history(
    session: LtiSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ChatMessage).where(ChatMessage.session_id == session.id)
    result = await db.execute(stmt)
    for msg in result.scalars().all():
        await db.delete(msg)
    return {"message": "Chat history cleared."}
