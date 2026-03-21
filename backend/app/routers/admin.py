"""
Admin router for LTI Platform Management.

Routes:
  Registrations (manual — one per LTI Consumer block in Open edX Studio):
    GET    /api/admin/registrations               → list all
    POST   /api/admin/registrations               → register a block
    PATCH  /api/admin/registrations/{id}          → update a block
    PATCH  /api/admin/registrations/{id}/toggle   → activate/deactivate
    DELETE /api/admin/registrations/{id}          → delete permanently

  Tool Info:
    GET /api/admin/registrations/tool-info → 4 URLs to paste in Open edX Studio
"""
from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import LtiInstance, LtiPlatformRegistration, LtiSession, Challenge, ChallengeAttempt, ChatMessage

log = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/api/admin", tags=["Admin — LTI Registrations"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class RegistrationCreate(BaseModel):
    label: str
    issuer: str
    client_id: str
    deployment_id: str = "1"
    keyset_url: str
    auth_endpoint: str
    token_endpoint: str = ""


class RegistrationOut(BaseModel):
    id: str
    label: str
    issuer: str
    client_id: str
    deployment_id: str
    keyset_url: str
    auth_endpoint: str
    token_endpoint: str
    is_active: bool
    created_at: str

    class Config:
        from_attributes = True


class ToolInfoOut(BaseModel):
    tool_launch_url: str
    tool_initiate_login_url: str
    registered_redirect_uri: str
    jwks_key_set_url: str


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _out(r: LtiPlatformRegistration) -> RegistrationOut:
    return RegistrationOut(
        id=r.id, label=r.label, issuer=r.issuer, client_id=r.client_id,
        deployment_id=r.deployment_id, keyset_url=r.keyset_url,
        auth_endpoint=r.auth_endpoint, token_endpoint=r.token_endpoint or "",
        is_active=r.is_active, created_at=r.created_at.isoformat(),
    )


# ─── Tool Info ─────────────────────────────────────────────────────────────────

@router.get("/registrations/tool-info", response_model=ToolInfoOut)
async def tool_info():
    """Returns the 4 URLs to paste in Open edX Studio (same for every block)."""
    base = settings.base_url
    return ToolInfoOut(
        tool_launch_url=f"{base}/lti/launch",
        tool_initiate_login_url=f"{base}/lti/login",
        registered_redirect_uri=f"{base}/lti/launch",
        jwks_key_set_url=f"{base}/lti/jwks",
    )


# ─── Registrations ─────────────────────────────────────────────────────────────

@router.get("/registrations", response_model=List[RegistrationOut])
async def list_registrations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(LtiPlatformRegistration).order_by(LtiPlatformRegistration.created_at.desc())
    )
    return [_out(r) for r in result.scalars().all()]


@router.post("/registrations", response_model=RegistrationOut, status_code=201)
async def create_registration(body: RegistrationCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(LtiPlatformRegistration).where(LtiPlatformRegistration.client_id == body.client_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Ya existe un registro con client_id '{body.client_id}'.")

    reg = LtiPlatformRegistration(
        label=body.label, issuer=body.issuer, client_id=body.client_id,
        deployment_id=body.deployment_id, keyset_url=body.keyset_url,
        auth_endpoint=body.auth_endpoint, token_endpoint=body.token_endpoint,
    )
    db.add(reg)
    await db.flush()
    log.info("Registered LTI block: %s client_id=%s", body.label, body.client_id[:16])
    return _out(reg)


@router.patch("/registrations/{registration_id}", response_model=RegistrationOut)
async def update_registration(registration_id: str, body: RegistrationCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(LtiPlatformRegistration).where(LtiPlatformRegistration.id == registration_id)
    )
    reg = result.scalar_one_or_none()
    if not reg:
        raise HTTPException(status_code=404, detail="Registro no encontrado.")
    reg.label = body.label
    reg.issuer = body.issuer
    reg.client_id = body.client_id
    reg.deployment_id = body.deployment_id
    reg.keyset_url = body.keyset_url
    reg.auth_endpoint = body.auth_endpoint
    reg.token_endpoint = body.token_endpoint
    db.add(reg)
    await db.flush()
    log.info("Updated registration: %s", reg.label)
    return _out(reg)


@router.patch("/registrations/{registration_id}/toggle", response_model=RegistrationOut)
async def toggle_registration(registration_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(LtiPlatformRegistration).where(LtiPlatformRegistration.id == registration_id)
    )
    reg = result.scalar_one_or_none()
    if not reg:
        raise HTTPException(status_code=404, detail="Registro no encontrado.")
    reg.is_active = not reg.is_active
    db.add(reg)
    await db.flush()
    log.info("Registration %s: %s", "activado" if reg.is_active else "desactivado", reg.label)
    return _out(reg)


@router.delete("/registrations/{registration_id}")
async def delete_registration(registration_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(LtiPlatformRegistration).where(LtiPlatformRegistration.id == registration_id)
    )
    reg = result.scalar_one_or_none()
    if not reg:
        raise HTTPException(status_code=404, detail="Registro no encontrado.")
    label = reg.label

    # Load all child instances and delete their dependents manually
    instances_res = await db.execute(
        select(LtiInstance).where(LtiInstance.registration_id == registration_id)
    )
    instances = instances_res.scalars().all()

    for inst in instances:
        # Delete sessions and their messages
        sessions_res = await db.execute(
            select(LtiSession).where(LtiSession.instance_id == inst.id)
        )
        for sess in sessions_res.scalars().all():
            msgs_res = await db.execute(
                select(ChatMessage).where(ChatMessage.session_id == sess.id)
            )
            for msg in msgs_res.scalars().all():
                await db.delete(msg)
            await db.delete(sess)

        # Delete challenges and their attempts
        challs_res = await db.execute(
            select(Challenge).where(Challenge.instance_id == inst.id)
        )
        for ch in challs_res.scalars().all():
            atts_res = await db.execute(
                select(ChallengeAttempt).where(ChallengeAttempt.challenge_id == ch.id)
            )
            for att in atts_res.scalars().all():
                await db.delete(att)
            await db.delete(ch)

        await db.delete(inst)

    await db.delete(reg)
    log.info("Registration deleted: %s (instances: %d)", label, len(instances))
    return {"message": f"Registro '{label}' eliminado."}
