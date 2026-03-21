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
) -> tuple[Challenge | None, ChallengeAttempt | None, str, bool, list[tuple[Challenge, str]]]:
    """
    Returns (current_challenge, attempt, shared_summary, is_from_sibling, all_sibling_pending).
    current_challenge   = first pending for this instance, OR first pending from a sibling.
    is_from_sibling     = True when the active challenge belongs to a sibling block.
    all_sibling_pending = list of (challenge, block_name) for every pending sibling challenge.
    """
    instance = session.instance

    chall_res = await db.execute(
        select(Challenge)
        .where(Challenge.instance_id == instance.id)
        .order_by(Challenge.order)
    )
    challenges = chall_res.scalars().all()

    current_challenge: Challenge | None = None
    current_attempt: ChallengeAttempt | None = None
    is_from_sibling = False
    all_sibling_pending: list[tuple[Challenge, str]] = []

    for challenge in challenges:
        attempt = await _get_or_create_attempt(db, challenge.id, session.user_id)
        if attempt.status != "passed":
            current_challenge = challenge
            current_attempt = attempt
            break

    shared_summary = ""
    if instance.share_context and instance.share_group_id:
        siblings_res = await db.execute(
            select(LtiInstance).where(
                LtiInstance.context_id == instance.context_id,
                LtiInstance.share_group_id == instance.share_group_id,
                LtiInstance.id != instance.id,
            )
        )
        siblings = siblings_res.scalars().all()

        if siblings:
            first_sibling_pending: tuple[Challenge, ChallengeAttempt, str] | None = None

            for sib in siblings:
                # Only consider blocks the student has actually opened
                sib_sess_res = await db.execute(
                    select(LtiSession).where(
                        LtiSession.instance_id == sib.id,
                        LtiSession.user_id == session.user_id,
                    )
                )
                if not sib_sess_res.scalars().first():
                    continue

                sib_challs_res = await db.execute(
                    select(Challenge).where(Challenge.instance_id == sib.id).order_by(Challenge.order)
                )
                block_name = sib.tutor_name or sib.topic or "Bloque anterior"

                for sc in sib_challs_res.scalars().all():
                    att_res = await db.execute(
                        select(ChallengeAttempt).where(
                            ChallengeAttempt.challenge_id == sc.id,
                            ChallengeAttempt.user_id == session.user_id,
                        )
                    )
                    att = att_res.scalars().first()
                    status = att.status if att else "pending"

                    if status != "passed":
                        all_sibling_pending.append((sc, block_name))
                        if first_sibling_pending is None:
                            sib_attempt = att if att else await _get_or_create_attempt(db, sc.id, session.user_id)
                            first_sibling_pending = (sc, sib_attempt, block_name)

            if current_challenge is None and first_sibling_pending:
                current_challenge, current_attempt, sib_block_name = first_sibling_pending
                is_from_sibling = True
                # Remove it from all_sibling_pending (it's now the active one)
                all_sibling_pending = [(c, b) for c, b in all_sibling_pending if c.id != current_challenge.id]
                shared_summary = f"\n\n[CONTEXTO]: Este desafío proviene del bloque '{sib_block_name}'."

    return current_challenge, current_attempt, shared_summary, is_from_sibling, all_sibling_pending


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/greeting", response_model=MessageOut, summary="Generate and save AI greeting as first message")
async def generate_greeting(
    session: LtiSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
):
    """
    Generates a personalized AI greeting based on challenge state and saves it
    as the first message in the session. Called when the block opens with no history.
    """
    instance = session.instance
    provider = get_ai_provider()

    current_challenge, current_attempt, _, _, _ = await _load_challenge_context(db, session)

    tutor_name = instance.tutor_name or "Tutor Virtual"
    course_name = session.course_name or "el curso"
    topic = instance.topic or ""

    # Build state description for AI
    if current_challenge:
        attempt_count = current_attempt.attempts_count if current_attempt else 0
        if attempt_count > 0:
            state_info = (
                f"El estudiante ya intentó el desafío '{current_challenge.title or current_challenge.question[:60]}' "
                f"{attempt_count} vez/veces pero aún no lo ha superado."
            )
        else:
            state_info = (
                f"El estudiante tiene un desafío pendiente titulado '{current_challenge.title or 'Desafío'}'."
            )
        challenge_text = current_challenge.question
    else:
        # Check if there were challenges that are all passed
        chall_res = await db.execute(
            select(Challenge).where(Challenge.instance_id == instance.id)
        )
        has_challenges = chall_res.scalars().first() is not None
        if has_challenges:
            state_info = "El estudiante ya completó todos los desafíos de este bloque exitosamente."
        else:
            state_info = "Este bloque no tiene desafíos configurados."
        challenge_text = None

    system = (
        f"Eres {tutor_name}, un tutor virtual amigable y motivador en el curso '{course_name}'. "
        + (f"El tema de este bloque es: {topic}. " if topic else "")
        + "Genera un saludo inicial cálido, natural y conciso (máximo 4 oraciones) para el estudiante. "
        "No uses listas ni encabezados. Escribe en prosa fluida."
    )

    if current_challenge:
        user_prompt = (
            f"Contexto: {state_info}\n"
            "Saluda al estudiante, menciónale que tienes un desafío para él que le ayudará a reforzar "
            "el tema estudiado, y preséntale el siguiente desafío de forma motivadora:\n\n"
            f"{challenge_text}\n\n"
            "Invítalo a responder cuando esté listo."
        )
    elif challenge_text is None and "completó" in state_info:
        user_prompt = (
            f"Contexto: {state_info}\n"
            "Felicita al estudiante por haber completado el desafío y ofrécete a responder cualquier "
            "pregunta adicional sobre el tema o a profundizar en lo que necesite."
        )
    else:
        user_prompt = (
            "Saluda al estudiante, preséntate brevemente y ofrécete a ayudarle con el tema del bloque. "
            "Muéstrate disponible y entusiasta."
        )

    try:
        greeting_text = await provider.chat(system_prompt=system, history=[], user_message=user_prompt)
    except Exception as e:
        log.error("Failed to generate greeting: %s", e)
        greeting_text = f"¡Hola! Soy {tutor_name}. Estoy aquí para ayudarte. ¿En qué puedo asistirte hoy?"

    # Delete any existing AI-only messages (stale greetings) before saving the new one
    existing_res = await db.execute(
        select(ChatMessage).where(ChatMessage.session_id == session.id).order_by(ChatMessage.created_at)
    )
    existing = existing_res.scalars().all()
    for m in existing:
        await db.delete(m)

    msg = ChatMessage(session_id=session.id, role="assistant", content=greeting_text)
    db.add(msg)
    await db.flush()

    log.info("Greeting regenerated for session=%s", session.id[:8])
    return MessageOut(role="assistant", content=greeting_text, created_at=msg.created_at.isoformat())


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

    current_challenge, current_attempt, shared_summary, is_from_sibling, all_sibling_pending = await _load_challenge_context(db, session)

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

        # Build pending sibling info for post-completion flow
        pending_info = ""
        if all_sibling_pending:
            titles = [f'"{c.title or c.question[:50]}…" ({b})' for c, b in all_sibling_pending]
            pending_info = (
                f"\n\nDESAFÍOS PENDIENTES DE OTROS BLOQUES ({len(all_sibling_pending)}):\n"
                + "\n".join(f"- {t}" for t in titles)
                + "\n[INSTRUCCIÓN POST-CORRECTO]: Si el estudiante acaba de responder correctamente "
                "y comienzas con [CORRECTO], DESPUÉS de felicitarlo menciona que tiene desafíos "
                "pendientes de otros bloques y pregúntale si quiere intentarlos ahora. "
                "Si responde afirmativamente, presenta el primero de la lista. "
                "Si aún hay más después de completarlo, vuelve a recordárselo y pregunta de nuevo."
            )

        eval_instructions = (
            "\nINSTRUCCIONES PARA EVALUAR LA RESPUESTA:\n"
            "PASO 1 — DETECTA SI ES UNA RESPUESTA AL DESAFÍO O UN MENSAJE CONVERSACIONAL:\n"
            "- Si el mensaje del estudiante es conversacional ('sí', 'no', 'ok', 'claro', 'hola', "
            "'gracias', 'de acuerdo', etc.) en respuesta a algo que TÚ preguntaste (como '¿quieres "
            "intentar un desafío pendiente?'), NO lo evalúes como intento al desafío. Responde "
            "apropiadamente: si dijo 'sí' a intentar un desafío pendiente, PRESÉNTALE ese desafío "
            "de la lista DESAFÍOS PENDIENTES DE OTROS BLOQUES. Si dijo 'no', respeta su decisión.\n"
            "- Solo evalúa como intento al desafío cuando el estudiante claramente intenta responder "
            "la pregunta del desafío.\n\n"
            "PASO 2 — EVALÚA LA RESPUESTA AL DESAFÍO:\n"
            "- COPIA LITERAL DETECTADA: Si la respuesta del estudiante es una copia casi exacta "
            "de texto que aparece en el historial de esta conversación o es una cita directa sin "
            "elaboración propia, NO la aceptes como correcta. Pídele que explique el concepto "
            "CON SUS PROPIAS PALABRAS para verificar su comprensión real. NO uses [CORRECTO].\n"
            "- Evalúa si TODOS los datos factuales requeridos son correctos.\n"
            "- Acepta paráfrasis y sinónimos ÚNICAMENTE si los hechos son correctos y el "
            "estudiante demuestra comprensión propia (no copia textual).\n"
            "- RECHAZA si cualquier dato factual clave es erróneo: siglo/fecha equivocada, "
            "lugar incorrecto, concepto opuesto, etc.\n"
            "- Si la respuesta ES CORRECTA y demuestra comprensión genuina: incluye el marcador "
            "exacto [CORRECTO] y felicita al estudiante.\n"
            "- Si la respuesta NO ES CORRECTA: usa el método socrático. Haz preguntas guía, "
            "pide que reformule. NUNCA des la respuesta directamente.\n"
        )

        if is_from_sibling:
            system_prompt += (
                "\nINSTRUCCIONES PARA EL DESAFÍO PENDIENTE DE BLOQUE ANTERIOR:\n"
                "- El estudiante tiene este desafío pendiente de un bloque anterior.\n"
                "- Recuérdale amigablemente: 'Tienes un desafío pendiente. ¡Vamos a intentarlo!'\n"
                "- Formula el desafío claramente y espera su respuesta.\n"
                "- NO muestres historial de chat de otros bloques.\n"
            ) + eval_instructions + pending_info
        else:
            system_prompt += (
                "\n- Si el estudiante NO ha respondido aún y solo saluda o pregunta algo general, "
                "presenta el desafío claramente y espera su respuesta.\n"
            ) + eval_instructions + pending_info

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
        # Detect [CORRECTO] anywhere in the reply (AI may add "¡" or text before the tag)
        import re as _re
        if _re.search(r'\[CORRECTO\]', reply, _re.IGNORECASE):
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
