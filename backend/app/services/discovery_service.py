"""
OpenID Connect Discovery service.

Two strategies for auto-registration of new LTI Consumer blocks:

Strategy 1 — OpenID Connect Discovery (standard):
  Backend calls {issuer}/.well-known/openid-configuration to discover
  jwks_uri, authorization_endpoint, and token_endpoint automatically.
  Works when the platform supports OIDC Discovery.

Strategy 2 — Fallback (for Open edX Tutor, which returns 404 on Discovery):
  Admin provides fallback_jwks_url + fallback_auth_endpoint in the
  LtiTrustedIssuer record. These are used when all discovery paths fail.
  In Open edX Tutor, the fallback JWKS URL is:
    http://local.openedx.io/api/lti_consumer/v1/public_keysets/
  (All per-block keyset URLs return the same platform key.)
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LtiPlatformRegistration, LtiTrustedIssuer
from app.services.session_service import get_registration_by_client_id

log = logging.getLogger(__name__)

# Standard OIDC discovery paths (tried in order)
_DISCOVERY_PATHS = [
    "/.well-known/openid-configuration",
    "/o/.well-known/openid-configuration",
    "/oauth2/.well-known/openid-configuration",
]


async def _try_openid_discovery(issuer: str) -> Optional[dict]:
    """
    Attempt to fetch the OpenID Connect Discovery document.
    Returns parsed config dict on success, or None if all paths fail.
    """
    import httpx

    issuer = issuer.rstrip("/")
    async with httpx.AsyncClient(timeout=8, verify=False) as client:
        for path in _DISCOVERY_PATHS:
            url = f"{issuer}{path}"
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    config = resp.json()
                    if "jwks_uri" in config:
                        log.info("OIDC discovery succeeded: %s", url)
                        return config
                    log.debug("OIDC discovery at %s returned 200 but missing jwks_uri", url)
                else:
                    log.debug("OIDC discovery at %s → HTTP %s", url, resp.status_code)
            except Exception as e:
                log.debug("OIDC discovery at %s failed: %s", url, e)

    return None


async def get_trusted_issuer(db: AsyncSession, issuer: str) -> Optional[LtiTrustedIssuer]:
    """Return the active trusted issuer record matching this URL, or None."""
    from sqlalchemy import select

    issuer_normalized = issuer.rstrip("/")
    stmt = select(LtiTrustedIssuer).where(
        LtiTrustedIssuer.issuer == issuer_normalized,
        LtiTrustedIssuer.is_active == True,  # noqa: E712
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def auto_register_from_trusted_issuer(
    db: AsyncSession,
    issuer: str,
    client_id: str,
    deployment_id: str = "1",
) -> LtiPlatformRegistration:
    """
    Auto-create a LtiPlatformRegistration for a new block from a trusted issuer.

    Tries OIDC Discovery first. If it fails, falls back to the issuer's stored
    fallback_jwks_url and fallback_auth_endpoint.

    Raises RuntimeError if both strategies fail.
    """
    # Guard against race condition (already registered)
    existing = await get_registration_by_client_id(db, client_id)
    if existing:
        log.info("client_id=%s already registered (race guard)", client_id[:16])
        return existing

    trusted = await get_trusted_issuer(db, issuer)

    # ── Strategy 1: OpenID Connect Discovery ─────────────────────────────────
    config = await _try_openid_discovery(issuer)

    jwks_uri: Optional[str] = None
    auth_endpoint: Optional[str] = None
    token_endpoint: Optional[str] = None
    source = ""

    if config:
        jwks_uri = config.get("jwks_uri")
        auth_endpoint = config.get("authorization_endpoint")
        token_endpoint = config.get("token_endpoint", "")
        source = "OIDC Discovery"

    # ── Strategy 2: Fallback endpoints from the trusted issuer record ─────────
    if not jwks_uri and trusted:
        if trusted.fallback_jwks_url:
            jwks_uri = trusted.fallback_jwks_url
            auth_endpoint = auth_endpoint or trusted.fallback_auth_endpoint or f"{issuer.rstrip('/')}/api/lti_consumer/v1/launch/"
            token_endpoint = token_endpoint or trusted.fallback_token_endpoint or ""
            source = "Fallback URLs from trusted issuer"
            log.info(
                "OIDC discovery failed — using fallback jwks_url from trusted issuer: %s",
                jwks_uri,
            )

    # ── Fail if nothing worked ────────────────────────────────────────────────
    if not jwks_uri or not auth_endpoint:
        hint = (
            " Tip: Para Open edX Tutor, en el panel admin → Issuers, "
            "agrega 'Fallback JWKS URL': http://local.openedx.io/api/lti_consumer/v1/public_keysets/ "
            "y 'Fallback Auth Endpoint': http://local.openedx.io/api/lti_consumer/v1/launch/"
            if trusted and not trusted.fallback_jwks_url
            else ""
        )
        raise RuntimeError(
            f"Auto-registration for client_id='{client_id[:16]}…' failed: "
            f"OpenID Discovery returned no results and no fallback URLs are configured.{hint}"
        )

    # ── Create the registration ───────────────────────────────────────────────
    label = f"Auto ({source}): {trusted.label or issuer} — {client_id[:12]}…" if trusted else f"Auto: {issuer}"

    reg = LtiPlatformRegistration(
        label=label,
        issuer=issuer.rstrip("/"),
        client_id=client_id,
        deployment_id=deployment_id,
        keyset_url=jwks_uri,
        auth_endpoint=auth_endpoint,
        token_endpoint=token_endpoint or "",
    )
    db.add(reg)
    await db.flush()

    log.info(
        "✅ Auto-registered LTI block [%s]: client_id=%s keyset=%s",
        source, client_id[:24], jwks_uri,
    )
    return reg
