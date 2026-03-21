"""
LTI Key Management Service.

Generates an RSA key pair on first boot and persists it to disk.
Provides:
 - get_private_key()  → PEM string used to sign JWTs we send
 - get_jwks()         → JSON Web Key Set for Open edX to verify our tokens
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwcrypto import jwk

from app.config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()

_private_key_pem: str | None = None
_public_jwks: dict | None = None
_key_id: str = "tutor-lti-key-1"


def _generate_and_save() -> None:
    """Generate RSA-2048 key pair and write to disk."""
    global _private_key_pem, _public_jwks

    priv_path = settings.private_key_path
    pub_path = settings.public_key_path
    priv_path.parent.mkdir(parents=True, exist_ok=True)

    # Generate
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    priv_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    priv_path.write_bytes(priv_pem)
    pub_path.write_bytes(pub_pem)
    log.info("Generated new LTI RSA key pair → %s", priv_path)

    _private_key_pem = priv_pem.decode()
    _build_jwks(pub_pem.decode())


def _build_jwks(pub_pem: str) -> None:
    global _public_jwks
    key = jwk.JWK.from_pem(pub_pem.encode())
    key["kid"] = _key_id
    key["use"] = "sig"
    key["alg"] = "RS256"
    _public_jwks = {"keys": [json.loads(key.export_public())]}


def load_keys() -> None:
    """Load keys from disk, or generate them if missing."""
    global _private_key_pem

    priv_path = settings.private_key_path
    pub_path = settings.public_key_path

    if priv_path.exists() and pub_path.exists():
        _private_key_pem = priv_path.read_text()
        _build_jwks(pub_path.read_text())
        log.info("Loaded existing LTI keys from %s", priv_path)
    else:
        log.warning("LTI key files not found – generating new pair.")
        _generate_and_save()


def get_private_key() -> str:
    if _private_key_pem is None:
        load_keys()
    return _private_key_pem  # type: ignore[return-value]


def get_jwks() -> dict:
    if _public_jwks is None:
        load_keys()
    return _public_jwks  # type: ignore[return-value]


def get_key_id() -> str:
    return _key_id
