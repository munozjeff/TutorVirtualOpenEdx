"""
Challenges router.

Endpoints:
  GET    /api/challenges          → List challenges for current instance
  POST   /api/challenges          → Create challenge (instructor)
  POST   /api/challenges/generate → Generate challenge via AI (instructor)
  GET    /api/challenges/status   → Get student's progress for this instance + shared group
  PUT    /api/challenges/{id}     → Update challenge (instructor)
  DELETE /api/challenges/{id}     → Delete challenge (instructor)
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_session, require_instructor
from app.models import Challenge, ChallengeAttempt, LtiInstance, LtiSession

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/challenges", tags=["Challenges"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class ChallengeOut(BaseModel):
    id: str
    instance_id: str
    title: str
    question: str
    answer_guide: str
    order: int

    class Config:
        from_attributes = True


class ChallengeCreate(BaseModel):
    title: str = ""
    question: str
    answer_guide: str = ""
    order: int = 0


class ChallengeUpdate(BaseModel):
    title: Optional[str] = None
    question: Optional[str] = None
    answer_guide: Optional[str] = None
    order: Optional[int] = None


class GenerateRequest(BaseModel):
    topic: str
    difficulty: str = "medio"   # fácil | medio | difícil
    count: int = 1


class AttemptOut(BaseModel):
    challenge_id: str
    status: str
    attempts_count: int


class ChallengeStatusOut(BaseModel):
    challenges: List[ChallengeOut]
    attempts: List[AttemptOut]
    current_challenge_id: Optional[str]   # first pending, None if all passed
    all_passed: bool


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _out(c: Challenge) -> ChallengeOut:
    return ChallengeOut(
        id=c.id,
        instance_id=c.instance_id,
        title=c.title,
        question=c.question,
        answer_guide=c.answer_guide,
        order=c.order,
    )


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("", response_model=List[ChallengeOut], summary="List challenges for current instance")
async def list_challenges(
    session: LtiSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Challenge)
        .where(Challenge.instance_id == session.instance_id)
        .order_by(Challenge.order)
    )
    return [_out(c) for c in result.scalars().all()]


@router.post("", response_model=ChallengeOut, summary="Create a challenge (instructor)")
async def create_challenge(
    body: ChallengeCreate,
    session: LtiSession = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    challenge = Challenge(
        instance_id=session.instance_id,
        title=body.title,
        question=body.question,
        answer_guide=body.answer_guide,
        order=body.order,
    )
    db.add(challenge)
    await db.flush()
    return _out(challenge)


@router.post("/generate", response_model=List[ChallengeOut], summary="Generate challenges via AI (instructor)")
async def generate_challenges(
    body: GenerateRequest,
    session: LtiSession = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    from app.services.ai_service import get_ai_provider

    count = max(1, min(body.count, 5))
    provider = get_ai_provider()

    system = (
        "Eres un experto en diseño de actividades educativas. "
        "Genera desafíos pedagógicos en español en formato JSON exacto."
    )
    user_msg = (
        f"Genera {count} desafío(s) educativo(s) sobre el tema: '{body.topic}'. "
        f"Dificultad: {body.difficulty}.\n\n"
        "Responde ÚNICAMENTE con un array JSON con este formato exacto (sin markdown, sin explicaciones):\n"
        '[\n'
        '  {\n'
        '    "title": "Título corto del desafío",\n'
        '    "question": "Pregunta completa que se le hará al estudiante",\n'
        '    "answer_guide": "Criterios para evaluar si la respuesta es correcta (para uso interno)"\n'
        '  }\n'
        ']\n'
    )

    try:
        raw = await provider.chat(system_prompt=system, history=[], user_message=user_msg)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"AI service error: {e}")

    # Parse JSON from response
    import json, re
    match = re.search(r'\[.*\]', raw, re.DOTALL)
    if not match:
        raise HTTPException(status_code=500, detail="AI did not return valid JSON array")
    try:
        items = json.loads(match.group())
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Failed to parse AI response as JSON")

    # Get current max order
    res = await db.execute(
        select(Challenge).where(Challenge.instance_id == session.instance_id).order_by(Challenge.order.desc())
    )
    existing = res.scalars().all()
    next_order = (existing[-1].order + 1) if existing else 0

    created = []
    for i, item in enumerate(items):
        c = Challenge(
            instance_id=session.instance_id,
            title=item.get("title", ""),
            question=item.get("question", ""),
            answer_guide=item.get("answer_guide", ""),
            order=next_order + i,
        )
        db.add(c)
        await db.flush()
        created.append(_out(c))

    log.info("Generated %d challenges for instance=%s", len(created), session.instance_id[:8])
    return created


@router.get("/status", response_model=ChallengeStatusOut, summary="Get student challenge progress")
async def get_challenge_status(
    session: LtiSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns challenges for current instance + student's attempt status.
    Used by frontend to show current challenge card.
    """
    challenges_res = await db.execute(
        select(Challenge)
        .where(Challenge.instance_id == session.instance_id)
        .order_by(Challenge.order)
    )
    challenges = challenges_res.scalars().all()

    if not challenges:
        return ChallengeStatusOut(
            challenges=[], attempts=[], current_challenge_id=None, all_passed=True
        )

    challenge_ids = [c.id for c in challenges]
    attempts_res = await db.execute(
        select(ChallengeAttempt).where(
            ChallengeAttempt.challenge_id.in_(challenge_ids),
            ChallengeAttempt.user_id == session.user_id,
        )
    )
    attempts = attempts_res.scalars().all()
    attempt_map = {a.challenge_id: a for a in attempts}

    attempt_outs = [
        AttemptOut(
            challenge_id=c.id,
            status=attempt_map.get(c.id, ChallengeAttempt(challenge_id=c.id, user_id=session.user_id, status="pending", attempts_count=0)).status,
            attempts_count=attempt_map[c.id].attempts_count if c.id in attempt_map else 0,
        )
        for c in challenges
    ]

    current = next(
        (c.id for c in challenges if attempt_map.get(c.id, None) is None or attempt_map[c.id].status != "passed"),
        None
    )
    all_passed = current is None

    return ChallengeStatusOut(
        challenges=[_out(c) for c in challenges],
        attempts=attempt_outs,
        current_challenge_id=current,
        all_passed=all_passed,
    )


@router.put("/{challenge_id}", response_model=ChallengeOut, summary="Update a challenge (instructor)")
async def update_challenge(
    challenge_id: str,
    body: ChallengeUpdate,
    session: LtiSession = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(Challenge).where(Challenge.id == challenge_id, Challenge.instance_id == session.instance_id))
    challenge = res.scalars().first()
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")

    if body.title is not None:
        challenge.title = body.title
    if body.question is not None:
        challenge.question = body.question
    if body.answer_guide is not None:
        challenge.answer_guide = body.answer_guide
    if body.order is not None:
        challenge.order = body.order

    db.add(challenge)
    return _out(challenge)


@router.delete("/{challenge_id}", summary="Delete a challenge (instructor)")
async def delete_challenge(
    challenge_id: str,
    session: LtiSession = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(Challenge).where(Challenge.id == challenge_id, Challenge.instance_id == session.instance_id))
    challenge = res.scalars().first()
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")
    await db.delete(challenge)
    return {"message": "Challenge deleted"}
