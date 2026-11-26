# ENG-M1 · Correcciones del motor Discovery (`discovery` 0.2.0 → 0.3.0)

**Fecha:** 2026-11-26 · **Rama:** `claude/upbeat-pasteur-nz8e0u` · **Estado:** en la rama, pendiente de
la aprobación del operador para integrarla (cambia resultados **futuros**).

`discovery/` no es un componente de producción de `AGENTS.md`: ningún grupo de
`protected_manifest.json` lo incluye. Se sigue el mismo criterio que MOTOR-FLAT: tests de antes y
después, versión nueva del motor y esta documentación. **No se modifica ningún resultado guardado**
en `discovery.db` ni en `lab.db`.

## 1. Qué cambia

| Hallazgo | Antes | Ahora | Sesgo que se corrige |
|---|---|---|---|
| **A-01 / A-02** | El stop y el objetivo solo se evaluaban en velas `allowed` (sesión × `weekdays`). Una posición que dormía fuera de la sesión, o la vela del domingo 17:00 NY en D1/H4, no tenía stop | Stop y objetivo se evalúan en **todas** las velas con posición abierta, como el SL/TP del EA en el servidor. La salida forzada (`flat_at`), la de tiempo y BE/trailing siguen limitadas a la sesión | A favor de las estrategias (pérdidas que no se veían) |
| **A-04** | En `_calendar_core` (turn_of_month, etc.) la salida de calendario al cierre iba antes que el stop dentro de la vela | Primero stop/objetivo, en todas las velas con posición; después la salida de calendario | A favor |
| **B-01** | Comisión por lote en USD dividida por `precio × contrato` en la divisa cotizada: en USDJPY ≈150 veces menor | Si el USD es la divisa base (USDJPY, USDCAD, USDCHF), el nocional en USD es el contrato | A favor en USDJPY (≈0,037 R por operación con stop de 20 pips) |
| **D-07** | `daily_r` solo tenía los días con alguna salida; `sharpe_daily` (×√252) y el DSR de `confirm` se inflaban en baja frecuencia | `daily_r` incluye con 0 los días hábiles del tramo evaluado (más los días con salida que no sean hábiles) | A favor (Sharpe ×1,5 a ×2,6) |

**No cambia:** qué velas pueden **abrir** una operación. La parte de A-01 sobre las entradas (la sesión
del lunes en D1, etiquetada en domingo) es una decisión de definición de la estrategia y afecta a la
paridad con el EA exportado (`export_mql5`). Queda como decisión separada.

## 2. Pruebas

| Prueba | Resultado |
|---|---|
| `tests/test_eng1_regressions.py` (A-01, A-02, A-04, B-01, D-07) | Con el motor anterior: **5 fallan**; con el nuevo: **5 pasan** |
| Paridad Python/Numba (script del Worker A, 300 casos `_core` + 100 `_calendar_core`) | **0 discrepancias** |
| Suite completa (Linux, marcadores de CI) | 38 failed (todos de entorno, ya conocidos) / 2072 passed; **ningún fallo nuevo** respecto a antes del cambio |

## 3. Qué hay que saber al integrarlo

- Las campañas **nuevas** guardan `engine_version = 0.3.0`.
- **Volver a ejecutar** una campaña antigua (retest, robustez, `confirm`) con 0.3.0 da cifras
  distintas: costes de USDJPY más altos, Sharpe diario más bajo y algunas operaciones que ahora salen
  por stop. Es lo correcto para juzgarlas, pero ya no reproduce bit a bit la cifra guardada. Para
  reproducir una cifra antigua: `git checkout motor-flat` (0.2.0).
- Los finalistas de EDGE-1 y EDGE-2 **no** pasaban las puertas con el motor anterior, que era
  optimista. Con 0.3.0 la comisión de USDJPY y el Sharpe solo pueden empeorar sus cifras. El stop
  evaluado en todas las velas suele empeorarlas, pero en algún caso concreto evita una pérdida mayor.
  No se espera que ninguno pase a aprobar, pero **no se ha comprobado** con datos reales.
