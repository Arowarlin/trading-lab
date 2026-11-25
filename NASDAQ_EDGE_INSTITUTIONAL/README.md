# NASDAQ EDGE INSTITUTIONAL · MNQ / NQ / US100

Investigación paper/demo. No hay ejecución automática ni cuentas reales. Las
reglas de `AGENTS.md` aplican.

## Estado por fase

| Fase | Estado | Entregables |
|---|---|---|
| A · Mercado, noticias y firmas | hecha y aprobada (2026-11-25) | `01_RESEARCH/*` |
| B · Datos históricos | hecha (2026-11-25) | `02_DATA/*`, `tools/`, `tests/` |
| C · Seis familias | **ejecutada y registrada, sustituida por forward** (decisión del operador 2026-11-25). Las 22 variantes históricas se ejecutaron en `03_BACKTEST` (16:43-16:51) y el operador las registró (`informal_trials` 6-7: n=7 y n=22); los resultados históricos están **contaminados por el EA** (`COLA-NQEDGE-FORWARD §1`). El forward NQF-A/B/C sigue siendo el prerregistrado, sin cambios | `03_BACKTEST/*` (histórico contaminado) |
| D · Selección | **sin candidatas**: no existe una ventaja demostrada | `03_BACKTEST/Strategy_Comparison.md` |
| E · Indicador (Pine v6) | **escrito sin señales (NO EDGE VALIDATED); compilación pendiente**; sin Strategy Tester | `04_PINE_SCRIPT/*` |
| F · OOS y auditoría de riesgo | OOS-2 no aplica (sin candidatas); auditoría de riesgo hecha | `05_RISK/*`, `07_AUDIT/*` |
| G · Documentación | hecha | `06_DOCUMENTATION/*`, `07_AUDIT/Final_Research_Report.md` |

## Conclusión de la Fase A

- **Edge: Sin datos.** No se ha medido nada todavía. Ningún porcentaje del
  proyecto existe aún.
- Datos: el laboratorio tiene NQ M1 de CME solo para 2010-06 → 2018-12, y un
  proxy CFD (Dukascopy) M1 de 2011 a 2026. Falta NQ/MNQ M1 de 2019 en adelante.
- Reglas verificadas de Topstep 50K, Apex 50K (EOD e Intraday, por separado) y
  Tradeify 50K (Growth, Select, Lightning). Las discrepancias están marcadas.
- Noticias: Topstep impone una ventana oficial de ±5 min para CPI, PPI, NFP y
  FOMC (NQ bloqueado, MNQ ≤ 3). Apex y Tradeify no bloquean.
- Pine no puede leer un calendario externo. Se usará una tabla embebida generada
  desde fuentes oficiales, con fecha de caducidad y estado STALE.
- Apex prohíbe la automatización. La V1 emite solo alertas.

## Conclusión de la Fase B

- OOS-2 sellado: 2024-01-01 → 2026-11-20 (`02_DATA/SEAL.md`).
- NQ M1 2010–2018 es apto: 0 duplicados, alineación DST verificada, rolls excluidos por ventana fija.
- Dukascopy solo sirve como proxy de precio: no tiene ask ni volumen útil.
- Descriptivas DEV en `01_RESEARCH/Nasdaq_Intraday_Research.md` §5 y `Economic_News_Research.md` §4.
- Ninguna es un resultado de estrategia; el edge sigue en **Sin datos**.

## Forward (2026-11-25)

- NQF-A/B/C congeladas en `04_FORWARD/prerregistro.md`; inicio 2026-11-30, comisión MNQ 0,75 USD por contrato y lado (operador, 2026-11-25); sin resultados **forward** hasta n = 200 por variante.

## Conclusión de la Fase C

- 22 variantes preregistradas (A–E), registradas por el operador (`informal_trials` ids 6–7; `count_tests` 1926).
- Bruto ≈ 0 en todas.
- Neto en DEV de −0,14R a −0,51R: el coste se come stops de ~5 pt en NQ 2010–2018.
- OOS-1 casi neutro.
- **Ninguna pasa. No existe una ventaja demostrada.** OOS-2 sigue sellado.

> **Corrección de la contradicción (2026-11-25):** la Fase C histórica **sí se ejecutó**
> (`03_BACKTEST`, 16:43-16:51) y el operador la **registró** (`informal_trials` fila 7,
> n=22; fila 6, n=7). Esos resultados históricos están **contaminados por el EA**
> `us100-ftmo1` (`COLA-NQEDGE-FORWARD §1`, bloque F1): no son una prueba limpia ni fuera
> de muestra. El forward NQF-A/B/C sigue siendo el prerregistrado, sin cambios.
