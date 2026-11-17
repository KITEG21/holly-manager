"""Contraseñas (scrypt) y tokens firmados (HMAC-SHA256), solo con la biblioteca estándar."""

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

from app.core.config import get_settings

_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt, expected = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    dk = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), **_SCRYPT)
    return hmac.compare_digest(dk.hex(), expected)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload: str) -> str:
    key = get_settings().secret_key.encode()
    return _b64(hmac.new(key, payload.encode(), hashlib.sha256).digest())


def create_token(user_id: int, role: str, ttl_seconds: int | None = None) -> str:
    ttl = ttl_seconds or get_settings().token_ttl_hours * 3600
    payload = _b64(json.dumps({"sub": user_id, "role": role, "exp": int(time.time()) + ttl}).encode())
    return f"{payload}.{_sign(payload)}"


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        payload, signature = token.split(".")
    except ValueError:
        return None
    if not hmac.compare_digest(signature, _sign(payload)):
        return None
    try:
        data = json.loads(_unb64(payload))
    except ValueError:
        return None
    if data.get("exp", 0) < time.time():
        return None
    return data
