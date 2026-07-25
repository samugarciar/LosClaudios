"""Prompts y opciones sugeridas.

`SYSTEM_PROMPT` es **estable e invariante por sesión**: es el prefijo cacheado.
Nada de fecha, `session_id` ni perfil interpolado aquí dentro — eso rompería la
caché en cada petición y multiplicaría el coste. El contexto que cambia viaja
como mensaje aparte (ver `model.py`).

Los guardrails están redactados en positivo y con el motivo, no como una lista de
prohibiciones sueltas: un modelo cumple mejor una regla cuyo porqué entiende.
"""

from __future__ import annotations

from app.protocol import Chip, Locale, Slot

# ---------------------------------------------------------------------------
# Prompt del sistema (prefijo cacheable)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
Eres un asesor de preselección de producto de seguridad SICK para protección fija \
de zonas de peligro. Hablas con clientes que NO son técnicos: describen su planta, \
no especificaciones.

TU TRABAJO
Traduces lo que cuenta el cliente en requisitos técnicos, acotas el catálogo y \
preparas la conversación con un ingeniero de seguridad de SICK. No cierras la \
selección: la preparas.

LÍMITES QUE NO PUEDES CRUZAR
1. No determinas el nivel de prestaciones (PL) requerido ni afirmas que una \
configuración cumple PL o SIL. Eso sale de la evaluación de riesgos del \
integrador, no de una conversación.
2. No das la distancia mínima de seguridad como cifra. Depende del tiempo de \
parada de la máquina, que se mide en la instalación (ISO 13855). Puedes explicar \
de qué depende y qué datos faltan.
3. Toda especificación numérica que menciones debe venir de una ficha que te \
hayan pasado en el contexto. Si no la tienes, dilo: "no está en la ficha". No la \
deduces, no la estimas y no la infieres del código de tipo del producto.
4. Un campo ausente en una ficha significa "no aplica" o "no publicado", nunca \
cero. Un PFHd que la ficha no publica no es un PFHd de cero.
5. No generalizas entre familias ni entre partes de un sistema. Dos referencias \
del mismo producto pueden tener valores de seguridad distintos.

CÓMO CONVERSAS
- Una sola pregunta por turno, en lenguaje de planta. Nada de jerga sin explicar.
- Si el cliente ya te ha dado un dato, no lo vuelvas a preguntar.
- Cuando propongas producto, propón dos o tres opciones y di siempre qué hay que \
vigilar en cada una, no solo qué encaja. Un listado de solo ventajas es un \
catálogo, no un asesoramiento.
- Cita las referencias por su número de artículo. Los marcadores de cita se \
escriben entre corchetes: [1], [2].
- Responde en el idioma del cliente. La documentación puede estar en inglés; tú \
respondes en el idioma en que te hablan.
- Sé breve. Frases cortas, sin preámbulo y sin repetir lo que el cliente acaba \
de decir.

CIERRE
Toda recomendación termina recordando que es una preselección para acelerar la \
conversación con un ingeniero de seguridad de SICK.\
"""


# ---------------------------------------------------------------------------
# Instrucciones por nodo (contexto dinámico, fuera del prefijo cacheado)
# ---------------------------------------------------------------------------

ASK_INSTRUCTION = """\
Formula UNA pregunta al cliente para averiguar: {slot_description}

No preguntes nada más. No enumeres opciones en el texto: la interfaz ya muestra \
botones con las opciones. Máximo dos frases.\
"""

EXPLAIN_INSTRUCTION = """\
Explica al cliente por qué estas opciones encajan con lo que te ha contado, y qué \
hay que vigilar en cada una. Usa los marcadores de cita [n] que acompañan a cada \
referencia.

Restricciones de este turno:
- No inventes ninguna cifra que no esté abajo.
- Si abajo aparece que un dato no está publicado en la ficha, dilo tal cual.
- Recuerda que la distancia de montaje depende del tiempo de parada.
- Máximo un párrafo corto por opción.\
"""

OUT_OF_SCOPE_INSTRUCTION = """\
El caso del cliente queda fuera de lo que puedes cubrir, porque {reason}.

Dilo con claridad y sin rodeos en dos frases, y explica que le pones en contacto \
con un ingeniero. No propongas ningún producto del catálogo como sustituto.\
"""

SLOT_DESCRIPTIONS: dict[Slot, str] = {
    "application_type": "si quiere impedir que alguien entre en una zona, que pase "
    "por un acceso, o que meta la mano en un punto concreto de la máquina",
    "body_part": "si por la zona pasa una persona entera, un brazo, una mano o dedos",
    "area_geometry": "qué tamaño tiene la zona a proteger, en metros aproximados",
    "mounting": "si el sensor se puede montar a ras de suelo en horizontal o "
    "tiene que ir en vertical",
    "environment": "cómo es el entorno: interior limpio, interior con polvo, o exterior",
    "access_frequency": "con qué frecuencia entra alguien en la zona",
    "material_passthrough": "si pasa material por la zona durante el ciclo de la máquina",
    "existing_control": "si ya tienen un PLC de seguridad, un relé, o nada",
    "region": "en qué país o región se instala la máquina",
    "stopping_time": "si conocen el tiempo que tarda la máquina en pararse",
}

#: Orden de preguntas: primero lo que más acota el catálogo.
SLOT_PRIORITY: tuple[Slot, ...] = (
    "application_type",
    "body_part",
    "environment",
    "area_geometry",
    "material_passthrough",
    "access_frequency",
    "mounting",
    "existing_control",
    "stopping_time",
    "region",
)


# ---------------------------------------------------------------------------
# Opciones sugeridas
# ---------------------------------------------------------------------------
# Deterministas a propósito: si las generara el modelo, el valor enviado podría
# no corresponder a ningún valor válido del perfil.


def _chip(chip_id: str, label: str, value: str, slot: Slot) -> Chip:
    return Chip(id=chip_id, label=label, value=value, slot=slot)


_CHIPS_ES: dict[Slot, list[Chip]] = {
    "application_type": [
        _chip("app-area", "Una zona alrededor de la máquina",
              "Quiero proteger una zona alrededor de la máquina.", "application_type"),
        _chip("app-access", "Un paso de acceso",
              "Quiero proteger un paso por el que se accede.", "application_type"),
        _chip("app-point", "Un punto concreto de la máquina",
              "Quiero evitar que se meta la mano en un punto de la máquina.",
              "application_type"),
    ],
    "body_part": [
        _chip("bp-body", "Una persona entera", "Pasa una persona entera.", "body_part"),
        _chip("bp-arm", "Un brazo o una pierna", "Puede entrar un brazo o una pierna.",
              "body_part"),
        _chip("bp-hand", "Una mano", "Puede entrar una mano.", "body_part"),
        _chip("bp-finger", "Dedos", "Hay riesgo de que entren dedos.", "body_part"),
    ],
    "environment": [
        _chip("env-clean", "Interior limpio", "Es interior y limpio.", "environment"),
        _chip("env-dusty", "Interior con polvo", "Es interior con bastante polvo.",
              "environment"),
        _chip("env-outdoor", "Exterior", "Está a la intemperie, en exterior.",
              "environment"),
    ],
    "area_geometry": [
        _chip("geo-2", "Unos 2 metros", "La zona mide unos 2 metros.", "area_geometry"),
        _chip("geo-4", "Unos 4 metros", "La zona mide unos 4 metros.", "area_geometry"),
        _chip("geo-6", "Más de 5 metros", "La zona mide más de 5 metros.",
              "area_geometry"),
        _chip("geo-unknown", "No lo sé todavía", "Todavía no sé la medida exacta.",
              "area_geometry"),
    ],
    "material_passthrough": [
        _chip("mat-yes", "Sí, pasa material", "Sí, pasa material durante el ciclo.",
              "material_passthrough"),
        _chip("mat-no", "No, solo personas", "No, por ahí solo pasan personas.",
              "material_passthrough"),
    ],
    "access_frequency": [
        _chip("freq-rare", "Casi nunca", "Casi nunca entra nadie.", "access_frequency"),
        _chip("freq-occ", "De vez en cuando", "Entra alguien de vez en cuando.",
              "access_frequency"),
        _chip("freq-often", "Constantemente", "Entra gente constantemente.",
              "access_frequency"),
    ],
    "mounting": [
        _chip("mnt-h", "A ras de suelo", "Se puede montar a ras de suelo.", "mounting"),
        _chip("mnt-v", "En vertical", "Tiene que ir montado en vertical.", "mounting"),
        _chip("mnt-u", "No lo sé", "No sé cómo se podrá montar.", "mounting"),
    ],
    "existing_control": [
        _chip("ctl-plc", "Sí, un PLC de seguridad", "Ya tenemos un PLC de seguridad.",
              "existing_control"),
        _chip("ctl-relay", "Un relé de seguridad", "Tenemos un relé de seguridad.",
              "existing_control"),
        _chip("ctl-none", "Nada todavía", "No tenemos nada de control de seguridad.",
              "existing_control"),
    ],
    "stopping_time": [
        _chip("stop-yes", "Sí, lo conocemos", "Sí, conocemos el tiempo de parada.",
              "stopping_time"),
        _chip("stop-no", "No, no lo sabemos", "No sabemos el tiempo de parada.",
              "stopping_time"),
    ],
    "region": [
        _chip("reg-eu", "Unión Europea", "Se instala en la Unión Europea.", "region"),
        _chip("reg-us", "Estados Unidos", "Se instala en Estados Unidos.", "region"),
        _chip("reg-other", "Otro país", "Se instala en otro país.", "region"),
    ],
}

_CHIP_LABELS_EN: dict[str, str] = {
    "app-area": "An area around the machine",
    "app-access": "An access passage",
    "app-point": "A specific point on the machine",
    "bp-body": "A whole person",
    "bp-arm": "An arm or a leg",
    "bp-hand": "A hand",
    "bp-finger": "Fingers",
    "env-clean": "Clean indoor",
    "env-dusty": "Dusty indoor",
    "env-outdoor": "Outdoor",
    "geo-2": "About 2 metres",
    "geo-4": "About 4 metres",
    "geo-6": "More than 5 metres",
    "geo-unknown": "I don't know yet",
    "mat-yes": "Yes, material passes through",
    "mat-no": "No, only people",
    "freq-rare": "Almost never",
    "freq-occ": "Occasionally",
    "freq-often": "Constantly",
    "mnt-h": "At floor level",
    "mnt-v": "Vertically",
    "mnt-u": "I don't know",
    "ctl-plc": "Yes, a safety PLC",
    "ctl-relay": "A safety relay",
    "ctl-none": "Nothing yet",
    "stop-yes": "Yes, we know it",
    "stop-no": "No, we don't know",
    "reg-eu": "European Union",
    "reg-us": "United States",
    "reg-other": "Another country",
}


def chips_for(slot: Slot, locale: Locale) -> list[Chip]:
    """Opciones del slot. El `value` se mantiene en español a propósito.

    `value` es lo que se envía al agente como mensaje del usuario y alimenta la
    extracción del perfil; mantenerlo estable en un idioma evita que el
    extractor tenga que lidiar con dos vocabularios. `label` sí se traduce.
    """
    chips = _CHIPS_ES.get(slot, [])
    if locale == "es":
        return list(chips)
    return [
        Chip(
            id=chip.id,
            label=_CHIP_LABELS_EN.get(chip.id, chip.label),
            value=chip.value,
            slot=chip.slot,
        )
        for chip in chips
    ]
