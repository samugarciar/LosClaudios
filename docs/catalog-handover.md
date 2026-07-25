> **Documento de traspaso — recibido 2026-07-25 del equipo de extracción de datos.**
>
> Reproducido **íntegro y sin editar**: es la especificación del dato y su autoría
> no es nuestra. Nuestras decisiones de integración van en un bloque al final, no
> intercaladas en su texto.
>
> - Fichero de datos en el repo: `data/catalog/sick_datasheets.2026-07-25.json`
> - Implementación de las reglas del §5: `backend/app/agent/catalog.py`
> - Aserciones de los límites del §6: `backend/tests/test_catalog.py`

---

# README — Datasheet SICK para agente de IA

**Archivo de datos:** `sick_datasheets.json`
**Fecha de extracción:** 2026-07-25
**Estado:** 15 fichas completas / 5 pendientes (ver §6)

Este documento explica qué hay dentro del JSON, qué **no** hay, y qué reglas debe
seguir un agente que lo use como fuente. Está escrito para que cualquier persona
—o cualquier conversación nueva— pueda retomar el trabajo sin contexto previo.

---

## 1. Qué es este archivo

Fichas técnicas oficiales de SICK, extraídas de los PDF publicados por el
fabricante, normalizadas a un esquema común en español. Cubre productos de
seguridad para **protección fija de zonas de peligro**.

Cada registro corresponde a **una referencia de artículo** (número de 7 dígitos
de SICK), no a un producto genérico. Dos variantes del mismo producto pueden
tener valores de seguridad distintos.

---

## 2. Estructura del JSON

```
{
  "meta":       { ...información sobre la extracción... },
  "registros":  [ ...15 fichas completas... ],
  "pendientes": { ...5 referencias sin extraer, agrupadas por producto... }
}
```

**Un agente solo debe responder a partir de `registros`.** Las entradas de
`pendientes` contienen únicamente el nombre y la referencia: no son fichas, y
tratarlas como tales produciría respuestas incompletas presentadas como completas.

---

## 3. Contenido de `registros`

15 referencias, de 5 familias muy distintas:

| Ref. | Variante | Producto | Familia |
|---|---|---|---|
| 1085349 | FLX3-CPUC100 | Flexi Compact | Controlador de seguridad |
| 1085351 | FLX3-CPUC200 | Flexi Compact | Controlador de seguridad |
| 1100333 | NANS3-AAAZ30AN1 | nanoScan3 | Escáner láser |
| 1100334 | NANS3-CAAZ30AN1 | nanoScan3 | Escáner láser |
| 1126792 | NANS3-CAAZ30AA1 | nanoScan3 + Safe EFI-pro | Escáner láser |
| 1126793 | NANS3-CAAZ30ZA1 | nanoScan3 + Safe EFI-pro | Escáner láser |
| 1126794 | NANS3-CAAZ30IZ1 | nanoScan3 | Escáner láser |
| 1116398 | V3SA2-ABBABBAAN1 | safeVisionary2 | Cámara 3D |
| 6080599 | SRA3-AAR150BKZI | safeRS3 | Radar — sensor |
| 6082806 | SRA3-AAR190BKZI | safeRS3 | Radar — sensor |
| 6080600 | SRA3-AAC100ZANI | safeRS3 | Radar — unidad de control |
| 6080601 | SRA3-AAC100ZPUI | safeRS3 | Radar — unidad de control |
| 1091037 | MICS3-CBAZ40ZA1P01 | Safe EFI-pro | Escáner láser |
| 1091038 | MICS3-CBAZ55ZA1P01 | Safe EFI-pro | Escáner láser |
| 1092539 | MICS3-ABAZ40ZA1P01 | Safe EFI-pro | Escáner láser |

---

## 4. Campos del esquema

### Identificación (siempre presentes)
| Campo | Descripción |
|---|---|
| `referencia` | Nº de artículo SICK. **Clave primaria.** |
| `variante` | Código de tipo (ej. `MICS3-CBAZ40ZA1P01`) |
| `productos` | Lista. Puede tener más de un valor (ver §5.2) |
| `familia` | Tipo de dispositivo |
| `version` | Subfamilia comercial (ej. "microScan3 Pro - EFI-pro") |

### Trazabilidad (siempre presentes — críticos)
| Campo | Descripción |
|---|---|
| `url_fuente` | PDF exacto del que salió el dato |
| `idioma_fuente` | `es` o `en` |
| `fecha_revision` | Fecha de revisión del PDF. Va de 2020 a 2026. |

### Seguridad funcional
`sil`, `categoria_iso13849`, `performance_level`, `pfhd`, `tm_anios`,
`mttfd_anios`, `tipo_iec61496`, `estado_seguro_fallo`

### Detección
`campo_proteccion_m`, `campo_aviso_m`, `alcance_medida_m`, `angulo_escaneo`,
`angulo_abertura`, `resolucion_configurable_mm`, `resolucion_angular`,
`tiempo_respuesta_ms`, `num_campos`, `num_casos_monitorizacion`,
`campos_simultaneos`, `suplemento_campo_mm`

### E/S y comunicaciones
`entradas_seguridad`, `salidas_seguridad`, `salidas_test`, `pares_ossd`,
`salidas_seguridad_red`, `io_universales`, `entradas_universales`, `bus_campo`,
`interfaz_config`, `interfaz_datos`, `rpi`, `protocolo`

### Eléctrico / mecánico / ambiental
`tension_alimentacion`, `consumo_w`, `clase_proteccion`, `dimensiones_mm`,
`peso_kg` / `peso_g`, `material_carcasa`, `grado_proteccion_ip`,
`temp_servicio`, `temp_almacenamiento`, `inmunidad_luz_klx`

### Otros
`tipo_luz`, `longitud_onda_nm`, `clase_laser`, `funciones`, `certificados`,
`eclass_12`, `etim_8`, `unspsc`, `accesorios_recomendados`

---

## 5. Reglas que el agente DEBE seguir

### 5.1 Un campo ausente no es cero
El esquema es una unión de campos de familias distintas. Un controlador no tiene
`campo_proteccion_m`; un escáner no tiene `salidas_test`. Si el campo no está,
la respuesta correcta es *"ese dato no aplica / no está en la ficha"*, nunca 0
ni "no tiene".

### 5.2 No generalizar entre familias
Es el error más peligroso posible con este archivo. Ejemplos reales:

- **safeRS3 no tiene un único grado de protección.** El sensor es IP67; la unidad
  de control es **IP20**. Responder "safeRS3 es IP67" puede llevar a montar en
  intemperie un equipo de armario. Distinguir siempre por `parte_sistema`.
- **safeVisionary2 es el único con PL c** (SIL 1, Cat. 2). Todos los demás son
  PL d o PL e. No es sustituto de un escáner en la misma categoría de riesgo.
- Los escáneres nanoScan3 y microScan3 se parecen pero **no comparten óptica**:
  905 nm y 0,17° frente a 845 nm y 0,39°.

### 5.3 Citar siempre la referencia y la fuente
Cada respuesta debe incluir `variante` + `referencia`, y `url_fuente` cuando se
cite un valor de seguridad. Sin eso no hay forma de auditar la respuesta.

### 5.4 Nunca inferir valores por el código de tipo
La nomenclatura es legible (ver §7) y tienta a deducir. **No hacerlo.** Si una
referencia no está en `registros`, el agente no conoce sus datos.

### 5.5 Funciones con condiciones
`funciones` es una lista de strings, y algunos llevan la condición incrustada.
Ejemplo real en `6082806`:
`"Bloqueo de rearme (solo con campo de proteccion 0,2-5 m)"`.
El agente no puede reportar la función sin su condición: ese sensor pierde el
bloqueo de rearme si se configura a 9 m.

### 5.6 Este archivo no sustituye a las instrucciones de uso
Las fichas de SICK son resúmenes. Para dimensionar distancias de seguridad,
cálculos de PL o cableado, la fuente válida es el manual de instrucciones.
El agente debe decirlo cuando la pregunta entre en ese terreno.

---

## 6. Límites conocidos del archivo

### 6.1 Faltan 5 referencias
No fueron extraídas. Están en `pendientes`:

| Ref. | Variante | Nota |
|---|---|---|
| 1094455 | MICS3-ABAZ90ZA1P01 | Core – EFI-pro, 9 m |
| 1110035 | MICS3-CCAZ40AA1P01 | Pro I/O – EFI-pro, 4 m |
| 1110033 | MICS3-CCAZ55AA1P01 | Pro I/O – EFI-pro, 5,5 m |
| 1094465 | MICS3-CBAZ90ZA1P01 | Pro – EFI-pro, 9 m |
| 1092538 | MICS3-ABAZ55ZA1P01 | Core – EFI-pro, 5,5 m |

Cuidado con **1110035**: al buscarlo aparece el `MICS3-CCAZ40AA1` **referencia
1110034**, sin sufijo P01. Es un artículo distinto y no debe usarse en su lugar.

Para completarlas: ejecutar `descargar_fichas_sick.py`, que ya apunta solo a estas 5.

### 6.2 Un registro tiene revisión antigua
`1100334` (NANS3-CAAZ30AN1) proviene de un mirror de distribuidor con **revisión
de 2020**; el resto son de 2026. Lleva un campo `advertencia`. Verificar contra
la revisión actual antes de usarlo en decisiones de diseño.

### 6.3 PFHd ausente en safeRS3
Las fichas de safeRS3 (`6080599`, `6080600`, `6080601`, `6082806`) **no publican
PFHd numérico**; remiten a las instrucciones de uso. El valor está literal como
texto, no como número. Sí traen `mttfd_anios: 42`.

### 6.4 Idiomas mezclados en origen
Los nombres de campo están normalizados en español, pero los valores de texto
libre pueden venir en inglés según `idioma_fuente`. Los valores numéricos y de
norma son idénticos en ambos idiomas.

### 6.5 Referencias en dos productos
`1126792` y `1126793` aparecen tanto en nanoScan3 como en Safe EFI-pro System.
Hay **un solo registro** por referencia, con ambos productos en `productos`.
Un agente que cuente registros por producto los contará dos veces si no deduplica.

### 6.6 Productos excluidos a petición
Se eliminaron del alcance 12 referencias: **outdoorScan3** (6), el resto de
**safeRS3** (4), **Flexi Gateway** (1) y **Flexi Net** (1). Quedan listadas en
`meta.excluidos_por_peticion`. El archivo **no cubre** el catálogo completo del
filtro original de SICK.

### 6.7 Es una foto de un momento
SICK revisa sus fichas. Contrastar `fecha_revision` antes de dar un dato por
vigente en aplicaciones críticas.

---

## 7. Nomenclatura (solo para entender, no para inferir)

**microScan3 / nanoScan3** — `MICS3-[X][G]AZ[RR][II]1P01`

- 2ª letra: `A` = Core, `C` = Pro
- Dígitos `RR`: alcance del campo de protección → `30`=3 m, `40`=4 m, `55`=5,5 m, `90`=9 m
- `II`: integración → `ZA`=EFI-pro, `AA`=E/S local + EFI-pro, `IZ`=EtherNet/IP, `AN`=E/S local

Diferencia Core vs Pro (verificada en 1092539 vs 1091037): 8 campos / 8 casos /
≤4 simultáneos / 4 salidas de red, frente a 128 / 128 / ≤8 / 8. El resto idéntico.

**safeRS3** — `SRA3-AA[C/R]...`: `C` = unidad de control, `R` = sensor radar.

---

## 8. Fragmento sugerido para el prompt del agente

```
Respondes sobre productos de seguridad SICK usando exclusivamente
sick_datasheets.json.

REGLAS:
1. Identifica siempre el producto por su `referencia` (nº de artículo).
   Si el usuario da un nombre ambiguo, pide la referencia.
2. Cita `variante` y `referencia` en cada respuesta. Para datos de
   seguridad funcional (SIL, PL, PFHd, categoría), añade `url_fuente`.
3. Si un campo no existe en el registro, di que no está en la ficha.
   No infieras, no pongas 0, no deduzcas del código de tipo.
4. Nunca extrapoles de una referencia a otra, ni siquiera dentro del
   mismo producto. Cada referencia tiene sus propios valores.
5. Distingue `parte_sistema` en safeRS3: sensor (IP67) y unidad de
   control (IP20) tienen datos ambientales distintos.
6. Si la referencia está en `pendientes` y no en `registros`, indica
   que no dispones de su ficha técnica.
7. Para distancias de seguridad, cálculos de PL o cableado, remite a
   las instrucciones de uso de SICK: la ficha es un resumen.
8. Menciona `fecha_revision` si el usuario pregunta por vigencia.
```

---

## 9. Archivos del paquete

| Archivo | Uso |
|---|---|
| `sick_datasheets.json` | Fuente para el agente |
| `sick_datasheets.csv` | Tabla plana, mismas 15 filas |
| `sick_datasheets.md` | Lectura humana: resumen de seguridad + ficha por variante |
| `descargar_fichas_sick.py` | Completa las 5 pendientes (Playwright + pdfplumber) |
| `README_agente.md` | Este documento |
