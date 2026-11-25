# NASDAQ EDGE INSTITUTIONAL · MNQ / NQ / US100

Investigación paper/demo. No hay ejecución automática ni cuentas reales. Las
reglas de `AGENTS.md` aplican.

## Estado por fase

| Fase | Estado | Entregables |
|---|---|---|
| A · Mercado, noticias y firmas | hecha y aprobada (2026-11-25) | `01_RESEARCH/*` |
| B · Datos históricos | **hecha 2026-11-25. Pendiente de revisión** | `02_DATA/*`, `tools/`, `tests/` |
| C · Seis familias | **sustituida por forward** (decisión del operador 2026-11-25). Las 22 variantes históricas no se ejecutan ni se registran | `03_BACKTEST/*` (histórico, sin usar) |
| D · Selección | — | — |
| E · Indicador y Strategy Tester (Pine v6) | — | `04_PINE_SCRIPT/*` |
| F · OOS y auditoría de riesgo | — | `05_RISK/*`, `07_AUDIT/*` |
| G · Documentación | — | `06_DOCUMENTATION/*` |

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
