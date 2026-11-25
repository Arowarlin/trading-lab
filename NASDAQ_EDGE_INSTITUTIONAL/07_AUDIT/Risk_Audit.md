# Auditoría de riesgo (checklist de la Fase 10)

| # | Verificación | Resultado | Evidencia |
|---|---|---|---|
| 1 | Compilar los scripts | **Pendiente** (hace falta una cuenta de TradingView) | `Pine_Compilation_Report.md` |
| 2 | Corregir errores de Pine | 2 correcciones estáticas; el resto, pendiente del compilador | ídem |
| 3 | Verificar señales históricas | No aplica: no hay señales | `03_BACKTEST/Strategy_Comparison.md` |
| 4 | Sin repintado | Revisado | `Non_Repainting_Audit.md` |
| 5 | Cálculo monetario MNQ/NQ | OK: tick MNQ $0,50 y NQ $5; casos de referencia | `tests/test_risk_math.py` (6/6) |
| 6 | Reglas de cada perfil | Verificadas en las webs oficiales el 2026-11-25; huecos marcados como Sin datos | `05_RISK/*`, `01_RESEARCH/Prop_Firm_Rules.md` |
| 7 | Cambio de horario de verano | OK en datos: pico de volumen a las 9:30 ET con DST y sin DST. En Pine se usan zonas IANA | `02_DATA/Data_Quality.md` §2.1 |
| 8 | Bloqueos de noticias | Lógica implementada. Ventanas basadas en la medición DEV (Tier 1 +20 min, FOMC +60 min / resto de sesión) | `01_RESEARCH/Economic_News_Research.md` §4 |
| 9 | Límite diario | OK en el espejo Python | `test_daily_loss_and_streak_budget` |
| 10 | Pérdidas consecutivas | Implementado (NO TRADE con ≥ máximo); en el motor de backtest, test de parada tras 2 | `test_daily_stop_after_two_losses` |
| 11 | Resultados con comisiones | Fase C con 5 escenarios de coste | `03_BACKTEST/phase_c_results.json` |
| 12 | Indicador y tester con las mismas reglas | No aplica: no hay Strategy Tester (ver `Limitations.md`) | — |

## Errores encontrados y su resolución en todo el proyecto

| Error | Fase | Resolución |
|---|---|---|
| FRED `release/dates` mezclaba fechas de revisión (13 CPI al año; "FOMC Press Release" con 250 fechas) | B | Primera publicación ALFRED `output_type=4` + fechas de la Fed |
| Dukascopy sin ask: el mid salía NaN en el 100 % de las filas | B | Precio = bid; el spread de Dukascopy pasa a Sin datos |
| Dukascopy sin volumen útil | B | RVOL y perfil solo con NQ |
| Arrays de solo lectura y registro de dataclass en los tests | C | Copias en el test; `sys.modules` antes de `exec_module` |
| Registro DSR lanzado desde `C:\windows\system32` | C | Comando con ruta absoluta y `--db` |
| `var` múltiple en una línea y `ta.sma` condicional | E | Separados y sacados a nivel global |
