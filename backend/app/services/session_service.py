"""
Session isolation service.

Handles the logic for computing isolation keys and managing
per-student, per-instance session boundaries.
"""
from __future__ import annotations

import hashlib
import secrets
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LtiInstance, LtiPlatformRegistration, LtiSession

log = logging.getLogger(__name__)


def compute_isolation_key(
    user_id: str,
    resource_link_id: str,
    context_id: str = "",
    share_context: bool = False,
    share_group_id: Optional[str] = None,
) -> str:
    """
    Compute the isolation key for a student session.

    Always scoped to user × block (resource_link_id).
    Each block keeps its own independent session and chat history.

    share_group_id is used ONLY to look up sibling challenge statuses,
    never to merge sessions between blocks.
    """
    raw = f"{user_id}:{resource_link_id}"
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_session_token() -> str:
    return secrets.token_urlsafe(48)


async def get_registration_by_client_id(
    db: AsyncSession,
    client_id: str,
) -> Optional[LtiPlatformRegistration]:
    """Fetch the platform registration for a given client_id."""
    stmt = select(LtiPlatformRegistration).where(
        LtiPlatformRegistration.client_id == client_id,
        LtiPlatformRegistration.is_active == True,  # noqa: E712
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_or_create_instance(
    db: AsyncSession,
    registration: LtiPlatformRegistration,
    resource_link_id: str,
    context_id: str,
    deployment_id: str,
) -> LtiInstance:
    """Get existing LTI instance config or create a new one."""
    stmt = select(LtiInstance).where(LtiInstance.resource_link_id == resource_link_id)
    result = await db.execute(stmt)
    instance = result.scalar_one_or_none()

    if not instance:
        instance = LtiInstance(
            resource_link_id=resource_link_id,
            context_id=context_id,
            deployment_id=deployment_id,
            registration_id=registration.id,
            client_id=registration.client_id,
        )
        db.add(instance)
        await db.flush()
        log.info(
            "Created new LTI instance resource_link_id=%s client_id=%s",
            resource_link_id[:16], registration.client_id[:16],
        )

    return instance


async def get_or_create_session(
    db: AsyncSession,
    instance: LtiInstance,
    user_id: str,
    user_name: str,
    user_email: str,
    user_role: str,
    course_name: str,
) -> tuple[LtiSession, bool]:
    """
    Get or create the LTI session for this user×instance combination.
    Returns (session, is_new).
    """
    isolation_key = compute_isolation_key(
        user_id=user_id,
        resource_link_id=instance.resource_link_id,
        context_id=instance.context_id,
        share_context=instance.share_context,
        share_group_id=instance.share_group_id,
    )

    stmt = select(LtiSession).where(LtiSession.isolation_key == isolation_key)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if session:
        # Verify the session belongs to the same user (safety check).
        # Isolation_key includes user_id so this should always match.
        if session.user_id != user_id:
            log.warning(
                "SECURITY: isolation_key collision! session.user_id=%s != jwt.user_id=%s — creating new session.",
                session.user_id[:12], user_id[:12],
            )
            session = None
        else:
            # Refresh user data. Always issue a fresh session_token so that
            # if a different user opens the same browser, their LTI launch
            # cookie overwrites the old one.
            session.user_name = user_name
            session.user_email = user_email
            session.user_role = user_role
            session.course_name = course_name
            session.session_token = generate_session_token()
            log.info("Refreshed session token for user=%s key=%s", user_id[:12], isolation_key[:12])
            return session, False

    session = LtiSession(
        isolation_key=isolation_key,
        instance_id=instance.id,
        user_id=user_id,
        user_name=user_name,
        user_email=user_email,
        user_role=user_role,
        course_name=course_name,
        session_token=generate_session_token(),
    )
    db.add(session)
    await db.flush()
    log.info("Created new LTI session key=%s user=%s", isolation_key[:12], user_id[:16])
    return session, True


async def resolve_session_by_token(
    db: AsyncSession,
    session_token: str,
) -> Optional[LtiSession]:
    """Look up a session by its cookie token. Returns None if not found."""
    stmt = (
        select(LtiSession)
        .options(selectinload(LtiSession.instance))
        .where(LtiSession.session_token == session_token)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
