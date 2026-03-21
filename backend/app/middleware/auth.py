"""
Auth middleware / dependencies.

Provides:
 - get_current_session()  – FastAPI dependency that reads the session cookie
                            and returns the matching LtiSession from DB.
 - require_instructor()   – Same but raises 403 if user is not an instructor.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import LtiSession
from app.services.session_service import resolve_session_by_token

log = logging.getLogger(__name__)
settings = get_settings()

INSTRUCTOR_ROLES = {"instructor", "admin", "staff", "urn:lti:role:ims/lis/Instructor"}


async def get_current_session(
    db: AsyncSession = Depends(get_db),
    lti_session: Optional[str] = Cookie(default=None, alias=settings.session_cookie_name),
) -> LtiSession:
    if not lti_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No session cookie found. Please launch the tool from Open edX.",
        )

    session = await resolve_session_by_token(db, lti_session)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid. Please re-launch from Open edX.",
        )
    return session


async def require_instructor(
    session: LtiSession = Depends(get_current_session),
) -> LtiSession:
    if session.user_role not in INSTRUCTOR_ROLES and not any(
        r in session.user_role for r in ["Instructor", "Admin", "Staff"]
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires instructor privileges.",
        )
    return session
