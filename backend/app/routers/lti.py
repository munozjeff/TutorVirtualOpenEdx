"""
LTI 1.3 OIDC Launch Flow router.

KEY DESIGN: Each Open edX LTI Consumer block has a UNIQUE client_id and keyset_url.
Our tool uses `LtiPlatformRegistration` to map client_id → keyset_url per block,
so any number of blocks can launch the same tool without a hardcoded config.

Endpoints:
  GET/POST /lti/login   → OIDC initiation (Step 1) — Open edX redirects here first
  POST     /lti/launch  → JWT validation + session creation (Step 2)
  GET      /lti/jwks    → Public JWKS for Open edX to verify our signatures
"""
from __future__ import annotations

import base64
import logging
import secrets
import urllib.parse
from typing import Optional

import httpx
import jwt as pyjwt
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.services import key_service
from app.services.session_service import (
    get_or_create_instance,
    get_or_create_session,
    get_registration_by_client_id,
)

log = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/lti", tags=["LTI 1.3"])

INSTRUCTOR_KEYWORDS = ["Instructor", "Admin", "Staff", "instructor", "admin", "staff"]


def _cookie_opts(max_age: int = 300) -> dict:
    """
    Returns cookie kwargs compatible with the current environment.

    SameSite=None requires Secure=True (HTTPS). In development (HTTP) we fall
    back to SameSite=Lax so browsers accept the cookies. In production, always
    use HTTPS so SameSite=None + Secure=True works for cross-site iframe embedding.
    """
    if settings.is_development:
        # HTTP dev: Lax + not Secure — cookies still work for same-origin testing
        return dict(max_age=max_age, httponly=True, samesite="lax", secure=False)
    else:
        # HTTPS production: None + Secure — required for LTI iframe cross-origin
        return dict(max_age=max_age, httponly=True, samesite="none", secure=True)


def _detect_role(roles: list[str] | str | None) -> str:
    if not roles:
        return "student"
    if isinstance(roles, str):
        roles = [roles]
    for r in roles:
        if any(k in r for k in INSTRUCTOR_KEYWORDS):
            return "instructor"
    return "student"


# ─── JWKS ─────────────────────────────────────────────────────────────────────

@router.get("/jwks", summary="Public JWKS — paste the URL into Open edX 'Key Set URL'")
async def jwks():
    """
    This endpoint is what you enter as the 'Key Set URL' (or JWKS URL)
    in Open edX Studio for every LTI Consumer block pointing at this tool.
    ONE url for all blocks: https://your-domain/lti/jwks
    """
    return JSONResponse(content=key_service.get_jwks())


# ─── OIDC Initiation  Step 1 ──────────────────────────────────────────────────

@router.get("/login", summary="OIDC Login Initiation")
@router.post("/login", summary="OIDC Login Initiation")
async def lti_login(
    request: Request,
    db: AsyncSession = Depends(get_db),
    # Parameters sent by Open edX (GET query string or POST form body)
    iss: Optional[str] = None,
    login_hint: Optional[str] = None,
    target_link_uri: Optional[str] = None,
    lti_message_hint: Optional[str] = None,
    client_id: Optional[str] = None,
):
    """
    Step 1: Open edX hits this URL first (the 'Tool Initiate Login URL').
    We receive the client_id, look up the registered platform config,
    then redirect back to Open edX's auth endpoint with a nonce.

    This same URL handles ALL blocks — the client_id tells us which one.
    """
    if request.method == "POST":
        form = await request.form()
        iss = iss or form.get("iss")
        login_hint = login_hint or form.get("login_hint")
        target_link_uri = target_link_uri or form.get("target_link_uri")
        lti_message_hint = lti_message_hint or form.get("lti_message_hint")
        client_id = client_id or form.get("client_id")

    if not iss or not login_hint:
        raise HTTPException(status_code=400, detail="Missing required LTI OIDC params (iss, login_hint).")

    # ── Look up registration. If unknown, try auto-discovery from trusted issuer ──
    if not client_id:
        raise HTTPException(status_code=400, detail="client_id is required for LTI 1.3 OIDC launch.")

    registration = await get_registration_by_client_id(db, client_id)

    if not registration:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Bloque no registrado (client_id='{client_id}'). "
                f"Regístralo manualmente en {settings.base_url}/?admin=1"
            ),
        )

    # ── Stateless OIDC: Encode client_id (+ lti_message_hint) in 'state' ─────
    # We avoid cookies for state/nonce because SameSite=Lax (HTTP) blocks them
    # in iframes. Instead, we use the 'state' parameter which the platform
    # MUST return to us in the final POST.
    # Format: "{client_id}:{nonce}:{base64url(lti_message_hint)}"
    # lti_message_hint in Open edX = block usage key → used to build per-block JWKS URL
    hint_b64 = ""
    if lti_message_hint:
        hint_b64 = base64.urlsafe_b64encode(lti_message_hint.encode()).decode().rstrip("=")
    state = f"{client_id}:{secrets.token_urlsafe(16)}:{hint_b64}"
    nonce = secrets.token_urlsafe(32)

    params = {
        "scope": "openid",
        "response_type": "id_token",
        "client_id": client_id,
        "redirect_uri": f"{settings.base_url}/lti/launch",
        "login_hint": login_hint,
        "state": state,
        "response_mode": "form_post",
        "nonce": nonce,
        "prompt": "none",
    }
    if lti_message_hint:
        params["lti_message_hint"] = lti_message_hint

    log.info(
        "LTI OIDC Step 1: client_id=%s → auth_endpoint=%s redirect_uri=%s",
        client_id[:16], registration.auth_endpoint, params["redirect_uri"],
    )

    # ── OIDC redirect stays inside the iframe ────────────────────────────────
    # Do NOT use target="_top". The entire OIDC flow (login → Open edX auth →
    # launch → frontend) runs within the iframe. Firefox blocks cross-origin
    # top-level navigation from iframes even with allow-top-navigation sandbox.
    # Staying in the iframe works because:
    #   - Open edX session cookies are same-site (top frame = local.openedx.io,
    #     request goes to local.openedx.io) → SameSite=Lax cookies are sent.
    #   - Our session cookie uses SameSite=None; Secure → works cross-origin.
    auth_endpoint = registration.auth_endpoint

    def _input(name: str, value: str) -> str:
        escaped = value.replace('"', "&quot;")
        return f'<input type="hidden" name="{name}" value="{escaped}">'

    hidden_inputs = "\n".join(_input(k, v) for k, v in params.items())

    html = f"""<!DOCTYPE html>
<html><head><title>LTI Login</title></head>
<body>
<form id="f" method="GET" action="{auth_endpoint}">
{hidden_inputs}
</form>
<script>document.getElementById('f').submit();</script>
<noscript><p>Redirigiendo... <a href="{auth_endpoint}">Haz clic aquí</a></p></noscript>
</body></html>"""
    return HTMLResponse(content=html)


# ─── Launch / JWT Validation  Step 2 ─────────────────────────────────────────

@router.post("/launch", summary="LTI 1.3 Launch — validates JWT and creates session")
async def lti_launch(
    request: Request,
    db: AsyncSession = Depends(get_db),
    id_token: str = Form(...),
    state: Optional[str] = Form(default=None),
):
    """
    Step 2: Open edX POSTs the signed id_token JWT here.
    We peek at the 'aud' claim to get the client_id, look up THAT block's
    keyset_url, verify the JWT with the correct key, then build the session.
    """
    # ── Extract client_id from JWT or state ──────────────────────────────────
    client_id = None
    try:
        unverified = pyjwt.decode(id_token, options={"verify_signature": False})
        client_id = unverified.get("aud")
        if isinstance(client_id, list):
            client_id = client_id[0]
    except Exception:
        pass

    # ── Stateless Fallback: extract client_id (and lti_message_hint) from state ─
    # Format: "client_id:nonce:hint_b64"  (hint_b64 may be empty for old states)
    lti_message_hint_from_state = ""
    if state and ":" in state:
        parts = state.split(":", 2)
        if not client_id:
            client_id = parts[0]
        if len(parts) >= 3 and parts[2]:
            try:
                padded = parts[2] + "=" * (-len(parts[2]) % 4)
                lti_message_hint_from_state = base64.urlsafe_b64decode(padded).decode()
            except Exception:
                pass

    if not client_id:
        raise HTTPException(status_code=400, detail="Cannot determine client_id from token or state.")

    # ── Fetch the registration for this specific block ─────────────────────────
    registration = await get_registration_by_client_id(db, client_id)
    if not registration:
        raise HTTPException(
            status_code=403,
            detail=f"No registration found for client_id '{client_id}'. Register this block first.",
        )

    log.info("LTI Launch Step 2: client_id=%s keyset_url=%s hint=%s",
             client_id[:16], registration.keyset_url, lti_message_hint_from_state[:32] if lti_message_hint_from_state else "")

    # ── Verify JWT signature (try multiple JWKS URLs if needed) ───────────────
    # Open edX uses per-block RSA keys. Auto-registered blocks may have a generic
    # JWKS URL. If lti_message_hint is available, also try the per-block JWKS URL.
    from jwt import PyJWKClient

    keyset_urls_to_try = [registration.keyset_url]
    if lti_message_hint_from_state:
        per_block_url = (
            f"{registration.issuer.rstrip('/')}"
            f"/api/lti_consumer/v1/public_keysets/{lti_message_hint_from_state}"
        )
        if per_block_url != registration.keyset_url:
            keyset_urls_to_try.append(per_block_url)

    claims = None
    last_error: Exception | None = None
    working_keyset_url = None
    for keyset_url in keyset_urls_to_try:
        try:
            jwks_client = PyJWKClient(keyset_url, headers={"User-Agent": "TutorVirtualLTI/1.0"})
            signing_key = jwks_client.get_signing_key_from_jwt(id_token)
            claims = pyjwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=client_id,
                options={"verify_exp": True},
            )
            working_keyset_url = keyset_url
            break
        except Exception as e:
            last_error = e
            log.debug("JWT verify failed with keyset_url=%s: %s", keyset_url, e)

    if claims is None:
        log.error("JWT validation failed for client_id=%s: %s", client_id[:16], last_error)
        raise HTTPException(status_code=401, detail=f"Invalid LTI token: {last_error}")

    # If a fallback keyset URL worked, persist it so future launches are fast
    if working_keyset_url and working_keyset_url != registration.keyset_url:
        log.info("Updating keyset_url for client_id=%s → %s", client_id[:16], working_keyset_url)
        registration.keyset_url = working_keyset_url

    # ── Extract LTI claims ────────────────────────────────────────────────────
    resource_link = claims.get("https://purl.imsglobal.org/spec/lti/claim/resource_link", {})
    context     = claims.get("https://purl.imsglobal.org/spec/lti/claim/context", {})
    deployment_id = claims.get("https://purl.imsglobal.org/spec/lti/claim/deployment_id", registration.deployment_id)
    roles       = claims.get("https://purl.imsglobal.org/spec/lti/claim/roles", [])

    resource_link_id = resource_link.get("id", "")
    context_id       = context.get("id", "")
    course_name      = context.get("title", "")
    user_id          = claims.get("sub", "")
    user_name        = claims.get("name", claims.get("given_name", "Student"))
    user_email       = claims.get("email", "")
    user_role        = _detect_role(roles)

    if not resource_link_id or not user_id:
        raise HTTPException(status_code=400, detail="Missing required claims (sub, resource_link_id).")

    # ── Get or create instance + session ──────────────────────────────────────
    instance = await get_or_create_instance(
        db, registration, resource_link_id, context_id, deployment_id
    )
    lti_session, is_new = await get_or_create_session(
        db, instance, user_id, user_name, user_email, user_role, course_name
    )

    # ── Redirect to frontend with session cookie ───────────────────────────────
    redirect = RedirectResponse(url=settings.frontend_url, status_code=302)
    ck = _cookie_opts(max_age=settings.session_max_age)
    redirect.set_cookie(
        key=settings.session_cookie_name,
        value=lti_session.session_token,
        path="/",
        **ck,
    )
    log.info(
        "✅ LTI launch OK: user=%s role=%s client_id=%s resource=%s new=%s",
        user_id[:12], user_role, client_id[:16], resource_link_id[:16], is_new,
    )
    return redirect
