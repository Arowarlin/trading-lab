# FUT-B1 · Coste exacto de datos Databento (solo metadatos)

**Ejecutado:** 2026-11-28 por Claude (sesión local en el PC del operador), worktree `E:\tl-fut-s`,
rama `claude/vibrant-mayer-r46s0o`. Script sin modificar.

## Hecho

1. `.\.venv\Scripts\python.exe scripts\futures_data_cost.py` (clave desde Credential Manager; no se imprimió).
   Solo `metadata.get_record_count`, `get_billable_size` y `get_cost`. Ninguna descarga.
2. `docs/futures/evidencia/databento_costes_2026-11.md`: 34 filas (una por esquema y raíz), 0 errores
   «Sin datos», y la tabla de totales.

## Totales (literal)

| Total por esquema y uso | USD |
|---|---:|
| definition (Research B) | 0.00 |
| definition (rolls) | 0.01 |
| mbo (muestra) | 70.12 |
| mbp-1 (muestra) | 1422.22 |
| mbp-10 (muestra) | 422.96 |
| ohlcv-1m (Research B (RB_spec §2)) | 21.61 |
| ohlcv-1m (base) | 59.68 |
| tbbo (Research A (fills)) | 7088.02 |
| tbbo (Research A, opción) | 187.78 |
| trades (Research A) | 4680.24 |
| trades (Research A, opción (RA_spec §2)) | 112.67 |

## Ficheros

- `docs/futures/evidencia/databento_costes_2026-11.json` y `.md` (escritos por el script).
- Este informe.

## Aviso

- Son precios por uso devueltos por la API el 2026-11-28; no incluyen créditos ni suscripciones.
- No es una recomendación de compra: decide el operador (OP-4).
- El script tardó más de 10 minutos (tres llamadas por fila).

## Siguiente

FUT-B3 (manifiesto).
