"""Límites de abuso para un endpoint sin autenticación (README §10).

El endpoint es público y cada turno cuesta tokens de modelo. Tres barreras
independientes:

  1. peticiones por minuto y cliente  → ráfagas
  2. turnos por sesión                → conversaciones interminables
  3. tokens por sesión                → coste

⚠️ LIMITACIÓN CONOCIDA: el estado vive en memoria del proceso. Con varias
réplicas cada una lleva su propia cuenta, y un reinicio lo borra todo. Los
contadores 2 y 3 se persisten en `sessions` y sobreviven; el 1 no. Para
producción con réplicas, mover el contador de ráfaga a Redis.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class RateLimitVerdict:
    allowed: bool
    reason: str | None = None
    retry_after_seconds: int | None = None


@dataclass
class SlidingWindowLimiter:
    """Ventana deslizante por clave. Precisa y suficiente a esta escala."""

    max_events: int
    window_seconds: float = 60.0
    _events: dict[str, deque[float]] = field(
        default_factory=lambda: defaultdict(deque)
    )
    _lock: Lock = field(default_factory=Lock)

    def check(self, key: str) -> RateLimitVerdict:
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            bucket = self._events[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()

            if len(bucket) >= self.max_events:
                oldest = bucket[0]
                retry_after = max(1, int(self.window_seconds - (now - oldest)) + 1)
                return RateLimitVerdict(
                    allowed=False,
                    reason="rate_limited",
                    retry_after_seconds=retry_after,
                )

            bucket.append(now)
            return RateLimitVerdict(allowed=True)

    def forget(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)


def check_session_budget(
    *,
    turn_count: int,
    tokens_used: int,
    max_turns: int,
    max_tokens: int,
) -> RateLimitVerdict:
    """Topes acumulados de la sesión. Los valores vienen de `sessions`."""
    if turn_count >= max_turns:
        return RateLimitVerdict(allowed=False, reason="session_turn_limit")
    if tokens_used >= max_tokens:
        return RateLimitVerdict(allowed=False, reason="session_token_limit")
    return RateLimitVerdict(allowed=True)
