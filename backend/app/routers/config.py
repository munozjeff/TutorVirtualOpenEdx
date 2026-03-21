"""
Instructor configuration router.

Endpoints:
  GET    /api/config          → Get current instance config (instructor/student)
  PUT    /api/config          → Update instance config (instructor only)
  POST   /api/config/sharing  → Toggle context sharing (instructor only)
  GET    /api/config/me       → Get current user info from session
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_session, require_instructor
from app.models import LtiInstance, LtiSession

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/config", tags=["Configuration"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class InstanceConfigOut(BaseModel):
    instance_id: str
    tutor_name: str
    topic: str
    system_prompt: str
    welcome_message: str
    mode: str
    share_context: bool
    share_group_id: Optional[str]
    resource_link_id: str
    context_id: str

    class Config:
        from_attributes = True


class InstanceConfigUpdate(BaseModel):
    tutor_name: Optional[str] = None
    topic: Optional[str] = None
    system_prompt: Optional[str] = None
    welcome_message: Optional[str] = None
    mode: Optional[str] = None  # libre | rag


class SharingUpdate(BaseModel):
    share_context: bool
    share_group_id: Optional[str] = None


class UserInfoOut(BaseModel):
    user_id: str
    user_name: str
    user_email: str
    user_role: str
    course_name: str
    instance_id: str
    tutor_name: str


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserInfoOut, summary="Get current user info")
async def get_me(session: LtiSession = Depends(get_current_session)):
    return UserInfoOut(
        user_id=session.user_id,
        user_name=session.user_name,
        user_email=session.user_email,
        user_role=session.user_role,
        course_name=session.course_name,
        instance_id=session.instance_id,
        tutor_name=session.instance.tutor_name,
    )


@router.get("", response_model=InstanceConfigOut, summary="Get instance configuration")
async def get_config(session: LtiSession = Depends(get_current_session)):
    inst = session.instance
    return InstanceConfigOut(
        instance_id=inst.id,
        tutor_name=inst.tutor_name,
        topic=inst.topic,
        system_prompt=inst.system_prompt,
        welcome_message=inst.welcome_message,
        mode=inst.mode,
        share_context=inst.share_context,
        share_group_id=inst.share_group_id,
        resource_link_id=inst.resource_link_id,
        context_id=inst.context_id,
    )


@router.put("", response_model=InstanceConfigOut, summary="Update instance configuration (instructor)")
async def update_config(
    body: InstanceConfigUpdate,
    session: LtiSession = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    inst = session.instance

    if body.tutor_name is not None:
        inst.tutor_name = body.tutor_name
    if body.topic is not None:
        inst.topic = body.topic
    if body.system_prompt is not None:
        inst.system_prompt = body.system_prompt
    if body.welcome_message is not None:
        inst.welcome_message = body.welcome_message
    if body.mode is not None and body.mode in ("libre", "rag"):
        inst.mode = body.mode

    db.add(inst)

    return InstanceConfigOut(
        instance_id=inst.id,
        tutor_name=inst.tutor_name,
        topic=inst.topic,
        system_prompt=inst.system_prompt,
        welcome_message=inst.welcome_message,
        mode=inst.mode,
        share_context=inst.share_context,
        share_group_id=inst.share_group_id,
        resource_link_id=inst.resource_link_id,
        context_id=inst.context_id,
    )


@router.post("/sharing", response_model=InstanceConfigOut, summary="Toggle context sharing (instructor)")
async def update_sharing(
    body: SharingUpdate,
    session: LtiSession = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    """
    Enable or disable context sharing between LTI instances for the same user.
    When share_context=True and share_group_id is set, all instances with the same
    share_group_id in this course will share chat history per student.
    """
    inst = session.instance
    inst.share_context = body.share_context
    inst.share_group_id = body.share_group_id if body.share_context else None
    db.add(inst)

    log.info(
        "Context sharing updated: instance=%s share=%s group=%s",
        inst.id[:8], inst.share_context, inst.share_group_id,
    )

    return InstanceConfigOut(
        instance_id=inst.id,
        tutor_name=inst.tutor_name,
        topic=inst.topic,
        system_prompt=inst.system_prompt,
        welcome_message=inst.welcome_message,
        mode=inst.mode,
        share_context=inst.share_context,
        share_group_id=inst.share_group_id,
        resource_link_id=inst.resource_link_id,
        context_id=inst.context_id,
    )
