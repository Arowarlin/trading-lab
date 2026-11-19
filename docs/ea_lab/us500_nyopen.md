# EA candidato · `us500-nyopen`

Estado: **FASE 1 · pre-registro**. Este documento se escribe **antes** de
ejecutar cualquier backtest. Cualquier cambio posterior en la hipótesis, la
ventana, el reescalado, la rejilla o los umbrales invalida el pre-registro y
debe documentarse como una prueba nueva.

## 1. Identidad y alcance

| Campo | Valor |
|---|---|
| Candidato | `us500-nyopen` |
| Origen | EA externo `us100-ftmo1` (v3.2) |
| Símbolo | `US500.cash` (S&P 500 CFD del bróker MT5) |
| Timeframe | M5 |
| Motor | `tradinglab.ea_us100_engine` (importado, sin editar) |
| Setfile base | `integrations/mt5/us100_ftmo1/US100_FTMO_v3_challenge.set` (solo lectura) |
| Cuenta / terminal | El terminal MT5 ya abierto, en solo lectura |
| Órdenes | Ninguna. El candidato no se instala en MT5 ni envía órdenes |

No se edita ningún archivo protegido (`ea_us100.py`, `ea_us100_engine.py`, el
EA MQL5, `config/mt5_eas.yaml`, `prop/`, `account_daily.py`, `execution/mt5*.py`).
El motor se importa tal cual.

## 2. Hipótesis con causa real

La apertura de Nueva York concentra el reajuste de cartera institucional, la
publicación de datos macro de EE. UU. y la entrada de volumen europeo/americano.
El EA `us100-ftmo1` explota ese flujo en el Nasdaq-100 con una confluencia de
barrido de liquidez, FVG, VWAP, estructura, volumen relativo y rango de
apertura. El **mismo flujo de apertura** existe en el S&P 500: es el otro índice
líquido de EE. UU., con una cesta más amplia y, por tanto, con menos riesgo
idiosincrático de un solo valor.

La hipótesis no es “US500 sube o baja”: es que **la microestructura de la
apertura NY que el EA ya captura en US100 también está presente en US500**, y
que el S&P 500 CFD tiene una relación movimiento/coste suficiente para que la
misma lógica tenga expectativa positiva después de costes.

No se cambia la estrategia para “hacerla funcionar” en US500. Si la misma
entrada, salida y riesgo no funcionan, el candidato **no pasa**.

## 3. Sistema completo que se porta

Se conserva **todo** el setfile v3.2:

- Entrada: confluencia de sweep, FVG, VWAP, estructura, RVOL y rango de apertura,
  con régimen SMA, filtro de gap, ventana 09:45–11:00 NY y `InpMinScore=55`.
- Salida: SL ATR/estructura, TP a `InpRR=3.5`, cierre por tiempo en `InpFlatAt`,
  cierre efectivo en cierres tempranos y bloqueo de festivos NYSE.
- Riesgo: escalera dinámica v3 `1,0 → 0,6 → 0,35 → 0,25 %` con DD estático
  2/4/6 %, respaldo `InpRiskPct=0.35`, `InpMaxTrades=3`,
  `InpMaxConsecLoss=1`, `InpDailyLossPct=1.5`, `InpMaxDDPct=8.0`.

Lo único que cambia es el símbolo y **cuatro parámetros expresados en puntos**,
reescalados por el cociente de ATR. El resto de inputs queda idéntico.

## 4. Regla de reescalado (pre-registrada)

### 4.1 Cociente

En la misma ventana de datos se calcula, para cada símbolo:

1. ATR de Wilder de 14 periodos sobre **todas** las velas M5, con la misma
   definición que `ea_us100_engine` (`atr_len=14`: media simple de los 14
   primeros TR y después `(atr·13 + TR)/14`).
2. Mediana del ATR de las velas cuya hora de Nueva York está en **09:30–15:59**
   (RTH), para no mezclar el ATR de la sesión con el de la noche.
3. `ratio = mediana_atr(US500) / mediana_atr(US100)`.

El ratio se congela al terminar la Fase 2 y se escribe en el informe de datos.
No se recalcula después de ver resultados.

### 4.2 Parámetros que se multiplican por el ratio

Solo estos cuatro, todos en unidades de precio/puntos:

| Input del setfile | Parámetro del motor | Valor base | Tratamiento |
|---|---|---:|---|
| `InpSlBufAtr` | `sl_buf` | 0,1 | `× ratio` |
| `InpMinSlPts` | `min_sl` | 2,0 | `× ratio` |
| `InpMaxSpreadPts` | `max_spread` (`×0,01`) | 300 pts = 3,0 | `× ratio` |
| — (constante del motor) | `slip` | 0,5 | `× ratio` |

Todo lo demás queda **idéntico**: `sl_atr`, `max_sl_atr`, `rr`, `gap_min`,
`fvg_*`, `vwap_*`, `rvol_*`, `piv_*`, `cooldown`, `max_trades`,
`max_consec`, la escalera de riesgo, el calendario NYSE y la ventana horaria.

Se guardan los valores sin redondear a la baja; el informe muestra el ratio y
los cuatro valores con 6 decimales. No se hace ninguna optimización.

## 5. Datos

| Campo | Regla |
|---|---|
| Símbolo | `US500.cash` |
| Timeframe | M5 |
| Fuente | `AttachOnlyBroker` de `propfund.snapshots` (sin credenciales, sin re-login, sin `shutdown`, sin arrancar MT5) |
| Caché propia | `data/cache/ea_lab/us500_m5.parquet` |
| Caché US100 | `data/cache/ea/US100_CASH_M5_NY.parquet`, **solo lectura**, nunca se sobrescribe |
| Zona horaria | Índice en `America/New_York` sin tz, como la caché del US100 |
| Ventana pre-registrada | **2021-09-15 → 2026-11-13** (misma ventana registrada para `us100-ftmo1`) |
| Ventana efectiva | La que cubran realmente los datos; si empieza después del 2021-09-15 o termina antes del 2026-11-13, la Fase 2 se detiene y se pide decisión. No se mueve la ventana en silencio |

### 5.1 Comprobaciones obligatorias de la Fase 2

- Rango real de fechas y número de velas.
- Duplicados de índice: 0.
- Huecos: se listan por año y por sesión; no se rellenan ni se interpolan.
- Zona horaria: la sesión NY debe empezar a las 09:30 y cerrar a las 16:00;
  se comprueba contra los límites de sesión del bróker.
- `point`, `digits` y `trade_tick_size` del símbolo: si `point != 0.01`, el
  motor no se ejecuta (el setfile asume puntos de 0,01).
- Spread por barra: mediana y percentil 75; se contrastan con la medición de
  ticks de `broker_spreads`.
- Cobertura de la ventana y densidad mínima (≥ 300 velas RTH por año).

Si alguna comprobación falla, la Fase 2 se detiene; no se “arreglan” los datos
recortando la ventana ni rellenando huecos.

## 6. Coste

El motor cobra el spread de cada barra M5 (`df.spread`, en puntos) más el
slippage configurado. Para no simular un coste irreal:

1. Se lee la tabla `broker_spreads` con `symbol="US500.cash"` y
   `source="broker"` (medición de ticks, no la caché de velas).
2. Si **no hay filas**, la validación **no se ejecuta**. El operador debe
   ejecutar antes:

   ```powershell
   lab ticks broker-spread US500.cash --days 7
   ```

3. La mediana horaria (`median_bps`) se convierte a precio con el cierre de
   cada barra (`close × median_bps / 10 000`) y se aplica como **suelo**:
   `spread_barra = max(spread_barra, spread_medido_horario)`. Así una barra con
   spread 0 no abarata la simulación.
4. La medición debe tener `to_ts` a menos de **7 días** de la fecha de la
   Fase 2. Si está caducada, se pide una medición nueva; no se usa la vieja.
5. Sensibilidad de coste: además del slippage base reescalado, se ejecutan las
   variantes con **+1 y +2 puntos de precio** de slippage absoluto, y se exige
   que la expectativa con **+2 puntos** siga siendo positiva (mismo filtro que
   `ea_us100.validate`).

Hoy `broker_spreads` no tiene filas de `US500.cash`, por lo que la Fase 2 está
bloqueada hasta que el operador ejecute el comando anterior.

## 7. Vecindario de variantes

Se usa **exactamente** el `GRID` de `ea_us100.validate`, sin añadir ni quitar
combinaciones:

```python
GRID = {
    "min_score": [55],
    "rr": [3.0, 3.5],
    "gap_min": [0.5, 0.7],
    "max_consec": [1, 2],
}
```

Son **8 variantes**. La base del setfile es
`min_score=55, rr=3.5, gap_min=0.7, max_consec=1` (índice 6), y se reporta como
base; las otras 7 son vecindad, no candidatos nuevos. No se busca el máximo
fuera de esta rejilla ni se cambia el umbral de score 55.

## 8. Validación (una sola ejecución)

La Fase 3 se ejecutará **una única vez**, solo tras la aprobación explícita
`APRUEBO VALIDACION US500`, con este pipeline y estos parámetros:

| Paso | Implementación | Parámetros |
|---|---|---|
| Barrido | `ea_us100.validate` / misma lógica | 8 variantes del GRID |
| Retornos | base diaria RTH × `RISK_PCT/100` | `RISK_PCT = 0.35` |
| DSR local | `stats.dsr_local_global` | 8 variantes, informativo |
| DSR global | `count_tests` + `global_srs` de la BD | N global real del laboratorio, **gate** |
| PBO | `validation.cscv_pbo` | 16 bloques, seed 0 |
| Walk-forward | `walkforward.walk_forward` | train 252, test 63, veredicto por defecto |
| Regímenes | `regime_report` + `regime_gate` | 2021–2026, mínimo 20 obs/año, retorno > 0 |
| Monte Carlo | `prop.simulator.monte_carlo` | FTMO challenge 100k, 5.000 rutas, 21 días, seed 42 |
| Riesgo dinámico | escalera v3 | misma simulación que `us100-ftmo1` |
| Costes | slippage base + 1,0 y 2,0 puntos | expectativa con +2 > 0 |

Todas las variantes se registrarán en `strategy_trials` con
`family="US500_NYOPEN_CONFLUENCE"`, `counted=True`, su `sr_period` y la ventana
`2021-09-15 → 2026-11-13`. No se registra ninguna variante antes de la Fase 3.

### 8.1 Protocolo de un solo disparo

- Antes de ejecutar se escribe un marcador con el hash del setfile, los
  parámetros reescalados, la ventana y la medición de spread.
- Si el marcador ya existe, el comando **se niega a ejecutar** otra validación.
- No se ejecutan backtests “de prueba” antes de la Fase 3.
- Si el resultado es NO PASA, se archiva y no se reintenta con otros parámetros.

## 9. Criterios de aprobación (idénticos a `lab ea validate`)

Los umbrales salen de `config/profiles.yaml` (`intraday_fx`) y de
`ea_us100.validate`; **no se inventan ni se relajan**. `us100-ftmo1` no superó
el DSR global (0,634 < 0,90), así que este candidato debe superar el mismo
listón, no el resultado histórico del US100.

| Criterio | Umbral | ¿Gate? |
|---|---|---:|
| Operaciones de la base | ≥ 100 | Sí |
| DSR local (N=8) | ≥ 0,90 | No (informativo) |
| DSR global (N real del laboratorio) | ≥ 0,90 | **Sí** |
| PBO | ≤ 0,30 | Sí |
| Walk-forward | veredicto `ok` | Sí |
| Regímenes 2021–2026 | todos con retorno > 0 y ≥ 20 obs | Sí |
| Spread mediano de barras | > 0 | Sí |
| Expectativa con slippage +2 puntos | > 0 | Sí |
| Monte Carlo FTMO 21 d | se reporta; sin gate adicional | No |

El veredicto es **PASA** solo si todos los gates son verdaderos. Cualquier
`Sin datos` en un gate cuenta como fallo, no como aprobado.

### 9.1 Veredicto de tres niveles (pre-registrado)

El DSR global se mantiene en **0,90** y no se relaja. Al cierre de la Fase 3, el
resultado se clasifica en uno de estos tres niveles, sin matices intermedios:

| Nivel | Condición | Qué autoriza |
|---|---|---|
| **PASA** | Cumple **todos** los criterios, incluido DSR global ≥ 0,90 | Forward en demo y, solo si el operador lo decide después, un challenge |
| **PASA SALVO DSR GLOBAL** | Cumple todos los demás criterios y **solo** falla el DSR global | Únicamente un forward en **demo**; **nunca** un challenge |
| **NO PASA** | Falla cualquier otro criterio (ops, PBO, walk-forward, regímenes, spread, coste o `Sin datos`) | Se archiva; no se reintenta ni se prueba otra variante |

`Sin datos` en el DSR global **no** se interpreta como “PASA SALVO DSR GLOBAL”:
cuenta como fallo y lleva a **NO PASA**. El nivel se escribe en
`reports/research/ea_us500_nyopen/verdict.md` junto a la tabla de criterios.

### 9.2 Hash del pre-registro

El pre-registro canónico se construye en `ea_lab.candidate.pre_registration()`:
candidato, setfile y su SHA-256, ventana, GRID, regla de reescalado, regla de
coste, veredicto de tres niveles y umbrales. Su SHA-256 es:

```text
53ba72a23910c0e744ede96ce8412378945ef12e5bfb512ac0bfe5b79887b8aa
```

Este hash se calculó **después** de añadir el veredicto de tres niveles y
**antes** de descargar o mirar los datos de US500 de la Fase 2. Cualquier cambio
en esos términos invalida el pre-registro. El ratio de ATR se congela en la
Fase 2 como medición de datos, no como decisión discrecional.

## 10. Fase 2 · datos y ratio congelado

Ejecutado el **2026-11-19** con `python -m tradinglab.ea_lab data`, sin
backtests. Informe completo: `reports/research/ea_us500_nyopen/data.{json,md}`.

| Dato | Valor |
|---|---:|
| Velas M5 en la caché | 367.892 |
| Rango real | 2017-12-28 18:00 → 2026-11-19 16:20 NY |
| Velas en la ventana pre-registrada | 361.902 |
| Duplicados / OHLC inválidas | 0 / 0 |
| Días RTH en la ventana | 1.333 |
| Faltantes en días de trading | 423 (0,418 %) |
| Cierres tempranos detectados | 10 |
| Festivos NYSE con datos | 36 |
| Punto del símbolo | 0,01 (OK) |
| Spread medido (`broker_spreads`) | 0,8104 bps (23 horas, 0,1 h de antigüedad) |
| Spread de barra RTH (mediana) | 47,075 pts (0,4708 de precio) |
| Mediana tras el suelo medido | 50 pts |
| ATR mediano US500 (RTH) | 5,0553 |
| ATR mediano US100 (RTH) | 24,4662 |
| **Ratio US500/US100 congelado** | **0,20662301** |

Valores reescalados que usará la Fase 3:

| Parámetro | Base | Escalado |
|---|---:|---:|
| `sl_buf` | 0,1 | 0,020662 |
| `min_sl` | 2,0 | 0,413246 |
| `max_spread` | 3,0 | 0,619869 |
| `slip` | 0,5 | 0,103312 |

El ratio queda congelado. No se ha ejecutado ningún backtest.

## 11. Archivos que se crearán

Código nuevo, solo en `src/tradinglab/ea_lab/`:

- `__init__.py`
- `data.py` — lectura M5 US500 con `AttachOnlyBroker`, caché propia, validación
  de rango/huecos/duplicados/zona horaria y spread medido.
- `atr.py` — ATR Wilder 14, mediana RTH y ratio US500/US100.
- `candidate.py` — carga del setfile v3, reescalado de los cuatro parámetros,
  hash del pre-registro y parámetros del motor.
- `validation.py` — ejecución única del pipeline, registro en `strategy_trials`
  y marcador de no reintento.
- `report.py` — informes JSON/Markdown de datos, validación y veredicto.
- `__main__.py` — comandos `python -m tradinglab.ea_lab data|validate`.

Tests nuevos, solo en `tests/test_ea_lab*.py`:

- `tests/test_ea_lab_atr.py` — ATR, mediana RTH y reescalado sintético.
- `tests/test_ea_lab_data.py` — caché, carga y validación de velas sintéticas.
- `tests/test_ea_lab_candidate.py` — setfile y hash.
- `tests/test_ea_lab_validation.py` — llamada al motor y filtros con datos
  sintéticos, sin MT5 real.

Informes:

- `reports/research/ea_us500_nyopen/data.json` y `data.md` (Fase 2).
- `reports/research/ea_us500_nyopen/validation.json`, `validation.md` y
  `verdict.md` (Fases 3–4).
- `reports/research/ea_us500_nyopen/.validated` (marcador de un solo disparo).

No se modifica `src/tradinglab/cli.py`: los comandos se ejecutan con
`python -m tradinglab.ea_lab`. No hay commit ni push hasta que el operador lo
autorice.

## 12. Condiciones que invalidan el pre-registro

- Cambiar la ventana, el ratio de ATR, los cuatro parámetros reescalados, el
  GRID o cualquier umbral después de ver resultados.
- Usar la caché del US100 como datos de US500 o sobrescribirla.
- Ejecutar la validación sin spread medido de `US500.cash`.
- Ejecutar más de una validación o probar variantes fuera del GRID.
- Cambiar el setfile v3 o el motor durante la validación.

Si algo de esto ocurre, el resultado no cuenta como validación del candidato.

## 13. Resultado final (2026-11-19)

La validación se ejecutó **una sola vez** con la aprobación del operador y el
hash `53ba72a2…`. El marcador `.validated` quedó en estado `completed` y las 8
variantes se registraron en `strategy_trials` con la familia
`US500_NYOPEN_CONFLUENCE` (8 filas, `counted=1`).

**Veredicto: NO PASA.**

| Criterio | Valor | Umbral | Estado |
|---|---:|---:|---:|
| Operaciones | 401 | ≥ 100 | OK |
| DSR local | 0,1997 | ≥ 0,90 | INFO |
| DSR global | 0,0016 | ≥ 0,90 | FALLO |
| PBO | 0,1490 | ≤ 0,30 | OK |
| Walk-forward | fallido | `ok` | FALLO |
| Regímenes 2021–2026 | no | todos > 0 | FALLO |
| Spread mediano | 50 pts | > 0 | OK |
| Coste con +2 puntos | −0,292R | > 0 | FALLO |

Base del setfile: **401 operaciones, PF 0,99, expectativa −0,009R, total −3,6R,
DD máximo 40,5R**. La rejilla tiene variantes positivas (0–4), pero se miraron
después del barrido; elegirlas sería una selección post-hoc prohibida por el
pre-registro. El Monte Carlo FTMO da P(pasar) 0,02 % y el riesgo dinámico v3
termina en −8,19 % con kill switch. El coste relativo medido es 0,1209 en US500
frente a 0,0803 en US100 (referencia del pre-registro: ~0,099 vs ~0,078).

El candidato se archiva. **No se reintenta con otros parámetros ni se prueba
otra variante.** Informes: `reports/research/ea_us500_nyopen/validation.md` y
`verdict.md`.

