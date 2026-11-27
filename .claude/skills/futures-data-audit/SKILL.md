---
name: futures-data-audit
description: "Auditar un dataset de futuros (NQ/MNQ, ES/MES, GC/MGC) antes de usarlo: identidad del contrato, esquema, zona horaria, sesiones CME, rolls, huecos, duplicados y hash. Usar antes de cualquier backtest o campaña con datos de futuros nuevos o cambiados."
---

# futures-data-audit

## Propósito
Que ningún dato de futuros entre en una investigación sin identidad, calidad y hash conocidos (`docs/futures/03_ARQUITECTURA_FUTURES.md §3`).

## Cuándo usarla
- Llega un dataset nuevo (descarga de Databento, export de NinjaTrader, caché antigua).
- Una campaña va a leer un fichero que no está en el manifiesto.

## Entradas
Ruta del fichero o carpeta, proveedor, esquema (`ohlcv-1m`, `trades`, `tbbo`, `mbp-10`, `mbo`, `definition`) y raíz.

## Procedimiento
1. Identidad: raíz, contrato (`NQZ6`), `instrument_id`, esquema y proveedor. Si el nombre es de CFD (`US100`) para un futuro, anotarlo (FUT-07).
2. Hash SHA-256 del fichero, filas, primera y última marca (UTC, ns).
3. Tiempo: monotonía de `ts_event`, duplicados, zona horaria; sesión CME (17:00 Chicago = inicio de sesión) y cambios de horario.
4. Rolls: desde `definition` y volumen por contrato; si no hay `instrument_id`, marcar "rolls inferidos" (FUT-06).
5. Calidad: huecos dentro de sesión (velas o trades perdidos), precios ≤ 0, OHLC incoherente, trades fuera del bid/ask (L1), lado agresor ausente.
6. Licencia: proveedor y restricciones de uso conocidas, o "Requiere confirmación del proveedor".

## Validación
El informe se puede reproducir: comando exacto, versión del código y hash.

## Salidas
`reports/futures/data/<id>.md` y una línea en el manifiesto (`data/futures/catalog/manifest.jsonl` cuando exista).

## Falla si
Falta el hash, la identidad o el rango; o el esquema no sirve para la hipótesis (order flow con OHLCV).

## Restricciones
Solo lectura. Nunca descarga datos de pago ni modifica la caché. Si falta algo: **Sin datos**.
