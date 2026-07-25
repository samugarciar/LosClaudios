"""Configuración tipada.

Principio de este módulo: **degradación explícita, nunca silenciosa**. Sin clave
de API el agente usa un modelo simulado; sin `DATABASE_URL` no hay persistencia.
Ambas cosas se registran en el log al arrancar, con nivel WARNING, para que
nadie descubra en producción que llevaba una semana sin guardar conversaciones.
"""

from __future__ import annotations

import logging
import secrets
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    env: Literal["dev", "production"] = "dev"

    # --- Modelo -------------------------------------------------------------
    anthropic_api_key: str | None = None
    model: str = "claude-opus-5"
    effort: Literal["low", "medium", "high", "xhigh", "max"] = "high"

    # --- Base de datos ------------------------------------------------------
    database_url: str | None = None

    # --- Sesión -------------------------------------------------------------
    session_secret: str | None = None
    anon_hash_salt: str | None = None
    session_ttl_hours: int = Field(default=720, ge=1)

    allowed_origin: str = "http://localhost:3000"
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    # --- Límites de abuso ---------------------------------------------------
    rate_limit_per_minute: int = Field(default=20, ge=1)
    max_turns_per_session: int = Field(default=40, ge=1)
    max_tokens_per_session: int = Field(default=300_000, ge=1_000)

    # ------------------------------------------------------------------------
    @property
    def persistence_enabled(self) -> bool:
        return bool(self.database_url)

    @property
    def model_enabled(self) -> bool:
        return bool(self.anthropic_api_key)

    def resolved_session_secret(self) -> str:
        """Secreto de firma. Efímero en dev, obligatorio en producción."""
        if self.session_secret:
            return self.session_secret
        if self.env == "production":
            raise RuntimeError(
                "SESSION_SECRET es obligatorio en producción: sin él, las sesiones "
                "se invalidan en cada despliegue."
            )
        return _EPHEMERAL_SECRET

    def resolved_anon_salt(self) -> str:
        if self.anon_hash_salt:
            return self.anon_hash_salt
        if self.env == "production":
            raise RuntimeError(
                "ANON_HASH_SALT es obligatorio en producción: sin sal, el hash de IP "
                "es reversible por fuerza bruta y deja de ser anonimización."
            )
        return _EPHEMERAL_SALT

    def log_degradations(self) -> None:
        """Deja constancia en el log de todo lo que NO está activo."""
        if not self.model_enabled:
            logger.warning(
                "ANTHROPIC_API_KEY no definida: el agente responderá con un modelo "
                "SIMULADO. Las recomendaciones no son reales."
            )
        if not self.persistence_enabled:
            logger.warning(
                "DATABASE_URL no definida: SIN PERSISTENCIA. Checkpointer en memoria "
                "y repositorios no-op; nada sobrevive a un reinicio."
            )
        if self.env != "production":
            if not self.session_secret:
                logger.warning(
                    "SESSION_SECRET no definida: se usa un secreto efímero. Las "
                    "sesiones se invalidan al reiniciar el proceso."
                )
            if not self.anon_hash_salt:
                logger.warning("ANON_HASH_SALT no definida: se usa una sal efímera.")
        if self.cookie_samesite == "none" and not self.cookie_secure:
            logger.error(
                "COOKIE_SAMESITE=none exige COOKIE_SECURE=true; el navegador "
                "descartará la cookie de sesión."
            )


# Generados una sola vez por proceso. Deliberadamente no persistidos.
_EPHEMERAL_SECRET = secrets.token_urlsafe(48)
_EPHEMERAL_SALT = secrets.token_urlsafe(24)


@lru_cache
def get_settings() -> Settings:
    return Settings()
