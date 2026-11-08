# Datacheck

`lab datacheck <símbolo> [--timeframe 1d] [--cache-dir ...] [--json]` valida la
caché parquet local. No descarga datos ni modifica la caché.

## Controles

| Control | ok | aviso | falla |
|---|---|---|---|
| Caché | parquet legible | — | Sin datos / vacío |
| Duplicados | 0 | — | ≥1 timestamp duplicado |
| Orden | índice creciente | — | barras fuera de orden |
| Zona horaria | declarada en serie/metadatos/catálogo | no declarada | — |
| OHLC | high ≥ max(open, close), low ≤ min(open, close), precios > 0 | — | cualquier inconsistencia |
| Calendario 1d | huecos ≤2% | huecos 2–10% | huecos >10% |
| Saltos | sin retornos >25% | retornos 25–90% | retorno ≥90% |
| Ajuste | metadatos `adjusted: true` | sin declarar / no ajustado | — |
| Bid/ask | columnas presentes | forex/CFD/futuros sin ellas | — |
| Histórico 1d | ≥260 barras | — | <260 barras |

`aviso` se muestra pero no bloquea. `falla` impide que `lab research` genere
resultados o propuestas para ese activo; no se relaja ningún umbral.

## Salida

- CLI: tabla con estado, barras, rango, caché, motivos y cada control.
- JSON: `--json`.
- Research: `latest.json`, `proposals.json` y cada propuesta incluyen
  `datachecks` / `datacheck_status` / `datacheck_reasons`.
- Consola: panel **Research → Calidad de datos** y modal **Run Detail**.

## Look-ahead

`tests/test_lookahead.py` calcula la señal de cada estrategia e indicador con la
serie completa y con la serie truncada en `t`. La señal en `t` debe ser idéntica:
si cambia al añadir datos posteriores, hay fuga de futuro.

## Cachés nuevas

`data/yahoo.py` escribe un sidecar `<cache>.meta.json` con proveedor,
`auto_adjust=True`, tiempo `date-only` y fecha de descarga. Las cachés antiguas
sin sidecar aparecen como `aviso` de ajuste.
