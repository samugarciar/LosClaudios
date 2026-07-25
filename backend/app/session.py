"""Sesión anónima sin login (README §10).

Dos garantías:

1. **El cliente nunca elige su `session_id`.** Llega dentro de un JWT firmado por
   el backend, en cookie httpOnly. Si el cliente pudiera enviar un id arbitrario,
   podría leer o contaminar la conversación de otro.
2. **La IP nunca se almacena en claro.** Se guarda un hash con sal de IP+UA.
   Sin sal el hash de una IPv4 es reversible por fuerza bruta en segundos, así
   que no sería anonimización.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Request, Response

from app.config import Settings

logger = logging.getLogger(__name__)

COOKIE_NAME = "sa_session"
_ALGORITHM = "HS256"


def new_session_id() -> str:
    return str(uuid.uuid4())


def issue_token(session_id: str, settings: Settings) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": session_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=settings.session_ttl_hours)).timestamp()),
    }
    return jwt.encode(payload, settings.resolved_session_secret(), algorithm=_ALGORITHM)


def read_session_id(request: Request, settings: Settings) -> str | None:
    """Extrae el `session_id` de la cookie. Devuelve None si no es válido."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        payload = jwt.decode(
            token,
            settings.resolved_session_secret(),
            algorithms=[_ALGORITHM],
        )
    except jwt.ExpiredSignatureError:
        logger.info("cookie de sesión caducada; se emitirá una nueva")
        return None
    except jwt.InvalidTokenError:
        # Firma inválida: o el secreto cambió (reinicio en dev) o alguien la
        # manipuló. En ambos casos se empieza una sesión nueva.
        logger.warning("cookie de sesión inválida; se emitirá una nueva")
        return None

    subject = payload.get("sub")
    return subject if isinstance(subject, str) else None


def set_session_cookie(response: Response, session_id: str, settings: Settings) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=issue_token(session_id, settings),
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )


def compute_anon_hash(request: Request, settings: Settings) -> str:
    """Hash con sal de IP + User-Agent. Nunca se guarda la IP en claro."""
    # `x-forwarded-for` puede venir con varias IPs; la primera es el cliente.
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() if forwarded else (
        request.client.host if request.client else "unknown"
    )
    user_agent = request.headers.get("user-agent", "")

    return hmac.new(
        settings.resolved_anon_salt().encode(),
        f"{ip}|{user_agent}".encode(),
        hashlib.sha256,
    ).hexdigest()


def client_key(request: Request, settings: Settings) -> str:
    """Clave de rate limit por cliente. Reutiliza el hash anónimo."""
    return compute_anon_hash(request, settings)
