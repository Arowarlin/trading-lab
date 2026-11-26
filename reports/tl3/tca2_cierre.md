# TL2-TCA2 · cierre T6

**Fecha:** 2026-11-26
**Tag previo:** `tl2-tca2-pre` = `6fa4d2f`.
**Locks:** `proyecto-prod-tca2`, `changelog-produccion`, `protected-manifest`
(propios) y `readme-plan` **ocupado por `opencode-tl3-f3`** (<2 h), no robado.

## 1. Bloques

| Bloque | Estado | Commit |
|---|---|---|
| T0 · cola, locks, tag y baseline | hecho | `6fa4d2f` |
| T1 · `tca_version` sin tocar filas | hecho | `c48430e` |
| T2 · `signal_price` en ai_trader, forward y paper | hecho | `d0ce608` |
| T3 · lectores solo v2 | hecho | `32c0513` |
| T4 · tests de ejecución y frontera SL | hecho | `d2904f3` |
| T5 · CHANGELOG y baseline posterior | hecho | `f981ed6` |
| T6 · cierre | en curso | este documento |
| T7 · aviso | pendiente | — |

## 2. Ficheros tocados

Producción (manifiesto protegido):

- `src/tradinglab/ai_trader.py`
- `src/tradinglab/ai_distill.py`
- `src/tradinglab/forward_intraday.py`
- `src/tradinglab/execution/mt5.py`

Soporte TCA (no protegido):

- `src/tradinglab/db.py`
- `src/tradinglab/tca.py`
- `src/tradinglab/execution/paper.py`
- `src/tradinglab/discovery/slippage_measured.py`
- `docs/CHANGELOG-produccion.md`
- `config/propfund/protected_manifest.json`

Tests:

- `tests/test_tca_v2.py`
- `tests/test_tca_v2_readers.py`
- `tests/test_tca2_callers.py`
- `tests/test_mt5_tca.py`
- `tests/test_forward_intraday.py`
- `tests/test_ai_shadows.py`
- `tests/test_discovery_slippage.py`
- `tests/test_discovery_count.py` (solo por BOM ajeno)

## 3. Cambio de ejecución de `e02ad7e`

- La orden usa el tick releído antes de `order_send`.
- SL exactamente en `stop_distance`: pasa.
- SL a un punto menos: `MT5Error`.
- Mismo tick de señal y envío: coincide con `tl2-tca-pre`.

**Riesgo corregido:** la comparación estricta `<` rechazaba por coma flotante
un SL exactamente en la distancia mínima (0,1000000000000085 frente a 0,1). Se
añadió `+ 1e-9`; la regla no cambia.

## 4. Filas TCA

`data/lab.db`:

| Versión | Filas |
|---|---:|
| v1 (`tca_version IS NULL`) | 68 |
| v2 (`tca_version >= 2`) | 0 |

No se ha enviado ninguna orden, así que no hay filas v2 nuevas. Las 68
antiguas siguen intactas (mismo contenido, solo se añadió la columna).

## 5. Suite y entorno

- `ruff check`: **limpio** (se corrigió un import sin usar de
  `scripts/edge2_x0.py`, ajeno).
- `pytest -q`: **2050 passed, 1 skipped** (34 min 11 s) en la pasada
  definitiva. La primera pasada dio 2044 passed + 1 skipped y 6 fallos: 3
  fixtures con filas TCA sin `tca_version` (`test_ai_shadows`,
  `test_discovery_slippage`) y 2 BOM de EDGE2 (`edge2_register.py`,
  `edge2_x0_synthetic.py`). Corregidos; los 8 tests afectados pasan y la
  suite completa quedó verde.
- `lab doctor`: 1 FAIL de frescura de datos (US100 M1/M5/M15 y XAUUSD M1),
  externo; resto OK/WARN.
- `lab propfund verify`: 4/4 OK tras el baseline posterior.
- `count_tests`: 8.526 en la comprobación intermedia; sube por pruebas ajenas.

## 6. Contador §2

| Medida | Inicio | Cierre |
|---|---:|---:|
| `informal_trials` suma | 52 | 52 |
| `informal_trials` filas | 7 | 7 |
| Campañas totales | 46 | 64 |
| `n_total` campañas | 13.718 | 21.638 |
| `edge1-` | 28 | 28 |
| `edge2-` | 0 | 18 |
| Otras | 18 | 18 |

La condición de §2 se cumple: ni `informal_trials` ni las campañas no
`edge1-`/`edge2-` cambian por esta cola. El aumento de campañas es de EDGE-2,
que corre en paralelo.

## 7. Documentación (enmienda del operador)

El cierre anterior declaró `readme-plan` «huérfano» porque el PID 15896 ya no
existía. La enmienda de `COLA-ROBUST-1.md §R6` aclara que el `pid` de
`owner.json` es el del comando `scripts/orq_lock.py`, que termina al instante:
**no** es evidencia de orfandad. Solo cuenta la antigüedad (> 2 h) y lo decide
el operador. El lock se liberó y la línea de TL2-TCA2 se añadió a
README/PLAN/ESTADO en el bloque de enmienda.

## 8. Reinicio y rollback

- **Reinicio pendiente del operador:** `ai_trader` y el forward en marcha
  cargaron el código antiguo; este cambio no les afecta hasta reiniciarlos.
- **Rollback:** `git checkout tl2-tca2-pre -- <ruta>`; el tag es `6fa4d2f`.
