"""Notificación del lead.

Persistir el lead ya lo hace `Store.add_lead`. Esto es lo otro: que alguien se
entere. Un lead guardado del que nadie recibe aviso es, comercialmente, un lead
perdido — con el agravante de que parece que el sistema funciona.

El destino va detrás de un puerto porque todavía no está decidido (README §13:
HubSpot / Salesforce / ninguno). Hoy el MVP escribe un registro estructurado en
el log, que es suficiente para conectar un reenvío por Slack o email sin tocar
el grafo ni el endpoint.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from app.protocol import Lead

logger = logging.getLogger(__name__)


class LeadNotifier(Protocol):
    async def notify(self, lead: Lead, summary: dict[str, Any]) -> bool:
        """Devuelve True si la notificación salió. False no debe reintentarse aquí."""
        ...


class LogNotifier:
    """Registro estructurado. Destino provisional del MVP.

    Emite una línea JSON en un logger propio (`leads`) para que sea trivial
    enrutarla a un fichero, a Slack o a un colector sin tocar código.

    **No incluye el email ni el nombre en el cuerpo del log**: son datos
    personales y los logs suelen acabar en sitios con menos control que la base
    de datos. Para contactar, el equipo consulta la tabla `leads`; esto solo
    avisa de que hay uno nuevo y da la referencia para encontrarlo.
    """

    def __init__(self) -> None:
        self._log = logging.getLogger("leads")

    async def notify(self, lead: Lead, summary: dict[str, Any]) -> bool:
        payload = {
            "event": "lead.created",
            "company": lead.company,
            "country": lead.country,
            "consent_text_version": lead.consent_text_version,
            "candidates": [
                c.get("partNumber") for c in summary.get("candidates", []) if c
            ],
            "missing": summary.get("missing", []),
            "reason": summary.get("reason"),
        }
        self._log.info(json.dumps(payload, ensure_ascii=False))
        return True


class NullNotifier:
    """No notifica, y lo dice a nivel ERROR."""

    async def notify(self, lead: Lead, summary: dict[str, Any]) -> bool:
        logger.error(
            "LEAD SIN NOTIFICAR: no hay canal configurado. El lead está en la "
            "base de datos pero nadie ha recibido aviso."
        )
        return False


def build_notifier() -> LeadNotifier:
    # Cuando exista un canal real (Slack, email, CRM), se elige aquí según
    # configuración. El resto del sistema no se entera del cambio.
    return LogNotifier()
