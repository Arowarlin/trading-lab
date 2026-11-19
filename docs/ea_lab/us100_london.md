# EA candidato · `us100-london`

Estado: **PAUSADO por el operador antes de la Fase 3 (sin backtests, sin trials)**.
Pre-registro cerrado en Fase 1; documento escrito antes de cualquier backtest de
Londres. Cualquier cambio en hipótesis, anclajes, ventana, GRID o umbrales
invalida el pre-registro.

## 1. Identidad

| Campo | Valor |
|---|---|
| Candidato | `us100-london` |
| Origen | EA externo `us100-ftmo1` v3.2 |
| Símbolo | `US100.cash` |
| Timeframe | M5 |
| Motor | `tradinglab.ea_lab.session_engine` (copia de `ea_us100_engine.run`) |
| Setfile | `integrations/mt5/us100_ftmo1/US100_FTMO_v3_challenge.set` (solo lectura) |
| Parámetros | Los del setfile v3, **sin reescalar**: mismo símbolo |
| Órdenes | Ninguna. No se instala en MT5 ni se envía nada |

## 2. Hipótesis con causa real

La apertura de Londres (08:00 Europe/London) concentra el flujo institucional
europeo y la primera hora de liquidez del CFD de US100 antes de la sesión de
Nueva York. La hipótesis es que **la misma subasta de confluencia** que el EA
explota en la apertura de Nueva York —barrido de liquidez, FVG, VWAP,
estructura, RVOL y rango de apertura— también está presente en la apertura de
Londres del mismo instrumento.

No se cambia la estrategia para “hacerla funcionar”. Si la misma lógica no
funciona con los anclajes de Londres, el candidato **no pasa**.

## 3. Anclajes pre-registrados (Europe/London)

| Anclaje | Valor |
|---|---|
| Zona horaria | `Europe/London` |
| Rango de apertura | 08:00–08:15 |
| Sesión principal (VWAP, régimen, gap) | 08:00–16:30 |
| Sesión nocturna previa | 00:00–07:00 |
| Premarket | **sin premarket** |
| Ventana de entradas | 08:05–10:00 |
| Cierre forzado | 14:15 |
| Calendario | días hábiles L–V (sin festivos locales) |
| Margen mínimo hasta el cierre | 60 minutos |

`flat_at` es posterior a `trade_end`; no hay cruce de medianoche en el cierre.
La sesión nocturna no cruza medianoche en Londres, pero el motor soporta cruces
mediante `in_sess`.

## 4. Sistema completo que se porta

Se conserva **todo** el setfile v3.2: entrada por confluencia, SL ATR/estructura,
TP a `InpRR=3.5`, cierre por tiempo, cierre efectivo en cierres tempranos,
festivos NYSE para el modo NY, escalera de riesgo dinámico
`1,0 → 0,6 → 0,35 → 0,25 %` con DD 2/4/6 %, `InpMaxTrades=3`,
`InpMaxConsecLoss=1`, `InpDailyLossPct=1.5`, `InpMaxDDPct=8.0`.

Lo único que cambia son los anclajes de sesión. **No se reescala ningún
parámetro**: el símbolo es el mismo.

## 5. Datos

| Campo | Regla |
|---|---|
| Símbolo | `US100.cash` |
| Fuente | `AttachOnlyBroker` de `propfund.snapshots` (sin credenciales, sin re-login, sin `shutdown`, sin arrancar MT5) |
| Caché propia | `data/cache/ea_lab/us100_m5.parquet` |
| Caché del EA | `data/cache/ea/US100_CASH_M5_NY.parquet`, **solo lectura**, nunca se sobrescribe |
| Zona horaria | Índice en `America/New_York` sin tz |
| Ventana | **2021-09-15 → 2026-11-13** |
| Comprobaciones | rango, duplicados, OHLC inválidas, huecos, sesión NY 09:30–16:00, `point`, spread por hora |

Si la ventana no está cubierta o el `point` no es 0,01, la Fase 2 se detiene.

## 6. Coste

- `broker_spreads` con `symbol="US100.CASH"` y `source="broker"`.
- Medición de referencia: 23 horas, mediana **0,7061 bps**, antigüedad 0,1 h
  (2026-11-19). Debe tener menos de 7 días en la Fase 2.
- El spread medido se convierte a precio con el cierre de cada barra y se aplica
  como suelo: `max(spread_barra, close × median_bps / 10.000)`.
- Sensibilidad: slippage base + **1 y +2 puntos**; se exige expectativa positiva
  con +2 puntos (mismo filtro que `ea_us100.validate`).

## 7. Vecindario de variantes

Exactamente el `GRID` de `ea_us100.validate`, sin añadir combinaciones:

```python
GRID = {
    "min_score": [55],
    "rr": [3.0, 3.5],
    "gap_min": [0.5, 0.7],
    "max_consec": [1, 2],
}
```

**8 variantes**. La base del setfile es `55 / 3.5 / 0.7 / 1` (índice 6). No se
busca el máximo fuera de esta rejilla ni se cambia el score 55.

## 8. Validación y umbrales (idénticos a `lab ea validate`)

Pipeline: DSR local/global, PBO (16 bloques, seed 0), walk-forward
(train 252 / test 63), regímenes 2021–2026 (≥ 20 obs/año, retorno > 0), Monte
Carlo FTMO 100k (5.000 rutas, 21 días, seed 42), riesgo dinámico v3 y costes
+1/+2 puntos. Las 8 variantes se registran en `strategy_trials` con
`family="US100_LONDON_CONFLUENCE"` y `counted=1`.

| Criterio | Umbral | ¿Gate? |
|---|---|---:|
| Operaciones | ≥ 100 | Sí |
| DSR local (N=8) | ≥ 0,90 | No (informativo) |
| DSR global (N real) | ≥ 0,90 | **Sí** |
| PBO | ≤ 0,30 | Sí |
| Walk-forward | `ok` | Sí |
| Regímenes 2021–2026 | todos > 0 y ≥ 20 obs | Sí |
| Spread mediano | > 0 | Sí |
| Coste con +2 puntos | > 0 | Sí |

## 9. Veredicto de tres niveles

| Nivel | Condición | Qué autoriza |
|---|---|---|
| **PASA** | Todos los criterios, incluido DSR global ≥ 0,90 | Forward demo y, solo con decisión posterior, challenge |
| **PASA SALVO DSR GLOBAL** | Todos salvo el DSR global | Solo forward en demo; nunca challenge |
| **NO PASA** | Falla cualquier otro criterio o el DSR global está `Sin datos` | Se archiva; no se reintenta |

## 10. Protocolo de un solo disparo

- La Fase 3a solo se ejecuta con `APRUEBO VALIDACION US100 LONDRES`.
- Antes de calcular se escribe un marcador con el hash de este pre-registro y
  el SHA-256 de la caché. Si el marcador existe, el comando se niega a ejecutar.
- No se ejecutan backtests de prueba de Londres antes de la Fase 3a.
- Si el resultado es NO PASA, se archiva y no se prueban otras variantes.

## 11. Equivalencia con el motor original (Fase 1)

`session_engine.run` con los anclajes de Nueva York (America/New_York, OR
09:30–09:45, RTH 09:30–16:00, nocturna 18:00–09:30, premarket 08:00, entradas
09:35–11:30, cierre 15:45) produce **exactamente las mismas operaciones** que
`ea_us100_engine.run`:

- Datos sintéticos: **27 operaciones**, idénticas.
- Caché real del US100: **647 operaciones**, idénticas.

El test está en `tests/test_ea_lab_session_equivalence.py` y falla si aparece
cualquier diferencia.

## 12. Hash del pre-registro

```text
9393728b1243f047ba97300fb38c7d55c692617e340cc177c71816f231959ec9
```

Calculado antes de cualquier backtest de Londres e incluye el setfile, el
SHA-256 de `session_engine.py`, los anclajes, el GRID, la ventana, los umbrales
y el veredicto de tres niveles.

## 13. Archivos previstos

- `src/tradinglab/ea_lab/session_engine.py` (nuevo).
- `src/tradinglab/ea_lab/sessions.py` (anclajes y pre-registro).
- `tests/test_ea_lab_session_equivalence.py`.
- `docs/ea_lab/us100_london.md` (este documento).
- Fase 2: `src/tradinglab/ea_lab/session_data.py` y
  `reports/research/ea_us100_london/data.*`.
- Fase 3a: `reports/research/ea_us100_london/validation.*` y `verdict.md`.

Sin commit ni push hasta que el operador lo autorice.

## 14. Resultado de la Fase 2 (datos y spread)

Ejecutado el **2026-11-19** con `python -m tradinglab.ea_lab sessions-data`, sin
backtests.

- Caché propia: 367.939 velas M5, 361.984 en la ventana, 0 duplicados, 0 OHLC
  inválidas, 423 velas RTH faltantes en días de trading (0,418 %), `point=0,01`,
  cobertura de la ventana OK.
- Ventana de Londres (08:05–10:00): 30.694 velas, 1.335 días, mediana
  **190 pts** (p75 210, bruta 180).
- Referencia NY (09:35–11:30): 30.659 velas, 1.333 días, mediana **110,24 pts**
  (p75 144,25, bruta 90).
- **Ratio Londres / NY: 1,7235** (+79,76 pts). El spread de Londres es un 72 %
  más ancho que el de Nueva York en la ventana de entradas.
- Cobertura de la ventana de Londres: 1.335 de 1.348 días hábiles (99,04 %).
- `broker_spreads` US100.CASH: 0,7061 bps, 23 horas, 2,35 h de antigüedad.

No se ha ejecutado ningún backtest de Londres.

## 15. Viabilidad de costes previa (no es un backtest)

Cálculo sobre datos M5, sin ejecutar el motor, sin mirar retornos y sin registrar
trials. ATR Wilder 14 mediano dentro de la ventana de entradas y spread mediano
con suelo horario.

| Sesión | Ventana | ATR Wilder 14 | Spread medio | Spread / ATR | Cociente vs NY |
|---|---|---:|---:|---:|---:|
| **Londres** | 08:05–10:00 | 12,2152 | 1,9000 | **0,155544** | **3,9361** |
| Nueva York | 09:35–11:30 | 27,8967 | 1,1024 | 0,039517 | 1,0000 |

El coste relativo de Londres es **~3,94 veces** el de Nueva York: el spread es
un 72 % más ancho y el ATR de la ventana es menos de la mitad. Es una desventaja
estructural que la validación tendrá que superar; este cálculo no decide el
veredicto por sí solo.


