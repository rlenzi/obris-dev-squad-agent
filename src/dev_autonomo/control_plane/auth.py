"""Auth: hashing de password (bcrypt) + JWT (HS256).

Para dev local. Em producao, recomendamos SSO/OAuth + JWT assinado com chave
gerenciada via secret manager.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import bcrypt
import jwt

from dev_autonomo.config import get_settings

JWT_ALGORITHM = "HS256"
JWT_TTL_HOURS = 12

# bcrypt tem limite de 72 bytes na senha; truncamos pra evitar erro
_BCRYPT_MAX_BYTES = 72


def hash_password(plain: str) -> str:
    secret = plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(secret, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        secret = plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]
        return bcrypt.checkpw(secret, hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def _get_secret_key() -> bytes:
    settings = get_settings()
    if settings.SECRET_KEY is None:
        raise RuntimeError(
            "SECRET_KEY ausente no .env. JWT precisa de uma chave de assinatura."
        )
    return settings.SECRET_KEY.get_secret_value().encode()


def create_access_token(
    *,
    user_id: UUID,
    email: str,
    is_system_admin: bool,
    extra_claims: dict[str, Any] | None = None,
    ttl: timedelta | None = None,
) -> str:
    if ttl is None:
        ttl = timedelta(hours=JWT_TTL_HOURS)
    now = datetime.now(tz=timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "is_system_admin": is_system_admin,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, _get_secret_key(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decodifica e valida o JWT. Levanta jwt.InvalidTokenError em falha."""
    return jwt.decode(token, _get_secret_key(), algorithms=[JWT_ALGORITHM])
