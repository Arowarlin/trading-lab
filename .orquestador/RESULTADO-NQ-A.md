# RESULTADO NQ-A · Preparación sin coste

- **Fecha:** 2026-11-25
- **Rama:** `feature/prop-fund-multifirm`
- **Commit:** `tl2: NQ-A - adaptador y prerregistro`
- **Tag:** `tl2-nq-a`

## COSTE EXACTO (A1)

| Concepto | Valor |
|---|---:|
| Dataset | GLBX.MDP3 |
| Schema | OHLCV-1m |
| Símbolo | NQ continuo por calendario (`NQ.c.0`) |
| Periodo solicitado | 2010-01-01 → 2018-12-31 |
| Inicio disponible | **2010-06-06** (antes no hay datos) |
| Periodo estimado | 2010-06-06 → 2019-01-01 |
| Registros | **2.720.203** |
| Tamaño facturable | **152.331.368 bytes** (152,33 MB / 145,27 MiB) |
| **Coste exacto** | **USD 9,930875** |

Estimación por año (el endpoint de metadata devolvía 504 con el rango
completo; la suma por año es exacta):

| Tramo | Registros | Bytes | USD |
|---|---:|---:|---:|
| 2010-06-06 → 2011-01-01 | 169.823 | 9.510.088 | 0,619987 |
| 2011 | 310.173 | 17.369.688 | 1,132375 |
| 2012 | 308.787 | 17.292.072 | 1,127315 |
| 2013 | 300.548 | 16.830.688 | 1,097236 |
| 2014 | 302.199 | 16.923.144 | 1,103263 |
| 2015 | 320.647 | 17.956.232 | 1,170613 |
| 2016 | 328.725 | 18.408.600 | 1,200104 |
| 2017 | 334.810 | 18.749.360 | 1,222319 |
| 2018 | 344.491 | 19.291.496 | 1,257662 |
| **Total** | **2.720.203** | **152.331.368** | **9,930875** |

### Alternativa 2010-2017 (sin solape)

| Concepto | Valor |
|---|---:|
| Periodo | 2010-06-06 → 2018-01-01 |
| Registros | 2.375.712 |
| Tamaño | 133.039.872 bytes (133,04 MB / 126,88 MiB) |
| Coste | **USD 8,673213** |

Sin el solape de 2018 **no hay prueba de validez** (el criterio exige
reproducir 2018); sería una prueba a ciegas y no se recomienda.

**Crédito restante:** **Sin datos** (el fetcher no expone el saldo).

No se descargó nada: solo `metadata.get_record_count`,
`metadata.get_billable_size` y `metadata.get_cost` por año.

## A2 · Motor y adaptador

### Lo que necesita `ea_us100_engine.py`

- **Columnas:** `open`, `high`, `low`, `close`, `tickvol`, `spread`.
- **Índice:** hora de Nueva York **sin zona** (`ny_offset_h=0`); el motor
  interpreta las 09:30-15:45 como NY.
- **Sesión:** OR 09:30-09:45, entradas 09:45-11:00, `flat_at=15:45`;
  festivos y cierres tempranos de `nyse_calendar`.
- **Overnight:** **no**. `flat_at=15:45` obliga a cerrar en la sesión; todas
  las operaciones son intradía. Por eso se usa el contrato activo sin ajustar
  y se descartan las operaciones que crucen un roll (el EA no debería tener
  ninguna; se cuentan).

### `src/tradinglab/ea_lab/nq_adapter.py`

- M1 → M5 alineado a NY, barras que empiezan en múltiplos de 5, OHLC y
  volumen exactos; `tickvol` = volumen.
- Perfil de spread por franja de 5 min NY desde la caché de US100.cash:
  `data/cache/ea/us100_spread_profile_ny5m.parquet` (288 franjas; 285 con
  datos, 3 rellenadas con la mediana global 145; mediana global 150).
- Asignación del spread por franja con conversión a `America/New_York`
  (DST incluido).
- `filter_crossing_rolls`: descarta y cuenta operaciones con un roll
  estrictamente entre entrada y salida.
- `match_validity`: empareja por lado y barra de entrada ±1 (5 min), calcula
  % emparejado y correlación de R.
- `weekly_lcb`: bootstrap semanal, 10.000 remuestreos, LCB = media − 1,645 ×
  sd.
- `atr_ratio`: ATR14 M5 del motor para decidir el escalado.

### Script de la parte B

`scripts/ea_nq_out_of_period.py`:

1. Calcula el ratio ATR14 M5 NQ/US100 en 2018; si está en [0,9; 1,1] no
   escala; si no, escala `min_sl`, `max_spread` y `be_off` por k (regla E2).
2. Valida 2018-01-02 → 2018-12-31 (≥80 % emparejadas y correlación ≥0,7).
   Si falla, escribe **NO VÁLIDA (Sin datos)** y no mira 2010-2017.
3. Si pasa, prueba 2010-06-06 → 2017-12-27: n ≥ 300, expectativa ≥ 0,10 R y
   LCB95 > 0.
4. Informe en `reports/ea/us100-ftmo1-nq-2010-2017.md`.
5. `--synthetic` genera datos falsos para probar el flujo; **no toca NQ real**.

Prueba sintética del script: validez 70/70, correlación 1,0; prueba 2016
75 ops, expectativa −0,4957 R, veredicto "no confirma" (es solo el flujo, no
la prueba real).

## Tests

- `tests/test_ea_nq_adapter.py` (5): remuestreo exacto, spread por franja con
  DST, roll con salto conocido, motor con barras del adaptador, validez.
- `tests/test_ea_nq_script.py` (1): el script corre con `--synthetic` y
  escribe el informe.
- `ruff check`: limpio.
- `pytest` dirigido: **6 passed**.

## Cumplimiento

- No se descargó ningún dato de pago.
- No se ejecutó el motor sobre NQ real.
- No se tocó el EA, el setfile ni `ai_trader`.
- Sin campañas, OOS, `confirm`, `record-informal`, push, borrado ni órdenes.
- `count_tests` = 1894.

## Estado

**PARA** a la espera de `OK DESCARGA <importe>`. Coste exacto del periodo
completo: **USD 9,930875** (≤ 60 USD).
