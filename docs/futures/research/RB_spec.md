# FUT-D0 · Research B (apertura de Nueva York) · especificación y borradores de prerregistro

**Fecha:** 2026-11-28 · **Autor:** Claude Code (skill `hypothesis-preregistration`) · **Estado:** BORRADORES.
**Nada de esto está registrado ni se ha ejecutado.** Registrar y ejecutar es decisión del operador
(`AGENTS.md`).
**Decisiones del operador (2026-11-28):**
- "Todo lo que no sea futuros, en segundo plano."
- "No ligues la data: solo futuros."

Por eso esta línea usa **solo datos de futuros CME** (Databento `GLBX.MDP3`). Ningún dato de CFD,
Dukascopy o MT5 entra en un cálculo, ni como sustituto ni como proxy.

## 0. Resumen

1. **Ocho hipótesis definidas** con reglas fijas y sin parámetros que ajustar: RB-01 a RB-08.
2. **NQ/MNQ: solo forward.** El EA ya miró toda su historia (FUT-11). El forward NQF-A/B/C (desde el
   2026-11-30) ya cubre ORB, barrido ON y VWAP.
3. **Familia primaria propuesta FUT-RB-1:** 5 pruebas únicas en **ES y GC**, M1 2010-06-07 →
   2023-12-31, con Bonferroni α = 0,05/5.
4. **Bloqueos:**
   - no hay M1 de ES ni de GC (FUT-12): hace falta la compra OP-4, ampliada;
   - comisiones de MES y MGC: **Sin datos**;
   - ~~partición del holdout de futuros (OP-8)~~: **aprobada el 2026-11-28**.
5. **Potencia:** con unas 3.300 sesiones, la MDE es ≈ 0,066-0,083 R. La ventaja mínima útil provisional
   es μ\* ≈ +0,08 R (`risk/01 §5`) y se sustituye por la de FUT-A7 cuando exista. Las hipótesis
   condicionadas con menos de 2.258 eventos **no se registran**.
6. **Paso previo permitido sin aprobación de registro:** contar eventos sin desenlaces (FUT-D2), en
   cuanto haya datos.

## 1. Reglas de esta línea

- Pruebas únicas prerregistradas, **no barridos**: el método aprobado por el operador el 2026-11-26
  (`docs/engineering/EDGE_RESEARCH_PLAN.md §0`).
- Cada regla se escribe entera **antes** de ver datos. Cambiarla después de ver un desenlace la
  invalida, y la variante nueva cuenta como otra prueba.
- Antes de registrar solo se permiten **conteos** de señales, stops y contratos (mecánica), nunca P&L,
  R, win rate ni PF. Es la misma regla que en `COLA-NQEDGE-FORWARD §2`.
- El OOS-2 sigue **sellado**. El código descarta las filas del holdout **antes** de calcular nada
  (como C1 y EDGE-1).
- Registrar suma K al contador global (`count_tests`, hoy 17.974). Lo hace el operador con
  `lab learning record-informal`; ningún agente lo hace.

## 2. Datos (solo futuros)

| Necesidad | Esquema Databento | Rango | Hoy | Para |
|---|---|---|---|---|
| Barras M1 de ES y GC | `ohlcv-1m` | 2010-06-07 → 2026-11 | **Sin datos** (FUT-12) | toda la familia primaria |
| Definiciones de contrato | `definition` | ídem | **Sin datos** | rolls exactos (FUT-06), `instrument_id` |
| Barras M1 de NQ | `ohlcv-1m` | 2010-06 → 2018-12 en el equipo del operador; 2019+ **Sin datos** | parcial | solo la réplica condicional (§9) |
| H1 de NQ, ES y GC | `ohlcv-1h` | 2010-06-07 → 2026-11-23 | en el equipo del operador (`data/cache/databento/`, F10c) | **no sirve**: las velas H1 empiezan en la hora en punto y mezclan 9:00-9:30 con la apertura |
| MES, MNQ, MGC | — | — | **no hacen falta en el histórico** | el subyacente es el mismo; los micros entran solo por costes y tamaño |

**Nota de nombres.** En `data/cache/databento/` los ficheros de futuros llevan nombres heredados:
`US500_H1` = `ES.c.0`, `US100_H1` = `NQ.c.0`, `XAUUSD_H1` = `GC.c.0` (`TL3_REPORTS/data_manifest.md`).
Son futuros. Los ficheros nuevos se nombran por raíz (`ES`, `GC`), como en `03 §3.2`.

**Condiciones de los datos (si no se cumplen: Sin datos, y no se registra):**
- **D-1:** cobertura ≥ 95 % de los minutos de la ventana de cada hipótesis en cada año. Una sesión con
  un hueco dentro de su ventana se excluye y se cuenta.
- **D-2:** rolls desde `definition` y volumen diario (`03 §3.2`). Se excluyen el día del roll y la
  sesión anterior (política F10c).
- **D-3:** sesiones y festivos desde `status`/`statistics`. Si no existen, se derivan como en
  `derive-sessions`. Se excluyen los cierres anticipados.
- **D-4:** auditoría con la skill `futures-data-audit` y manifiesto con hash (FUT-B3).

**OP-8, APROBADA por el operador el 2026-11-28 («aprueba op8»):**
- **Muestra única:** 2010-06-07 → 2023-12-31, sin optimización, como C1.
- **OOS-2 de futuros:** 2024-01-01 → 2026-11-20, sellado, con la misma fecha que el resto del
  laboratorio.
- **Forward:** desde la fecha de aprobación.

## 3. Contaminación

**Regla de etiquetado (fijada aquí):**
- `contaminada`: la misma lógica, o su complemento, ya se miró sobre el mismo subyacente en el periodo.
- `parcial`: una lógica vecina, que comparte ventana, nivel o indicador, ya se miró sobre el mismo
  subyacente. O la misma lógica se miró en un subyacente muy correlacionado intradía (NQ ↔ ES).
- `limpia`: no consta ningún uso en el repositorio.

**Salvedad.** `data/lab.db` (`strategy_trials`) está en el equipo del operador y no en este checkout.
Antes de registrar, la tarea FUT-D2 lo consulta en solo lectura.

**Usos previos que cuentan:**
- **NQ futuros:** el EA `us100-ftmo1` sobre NQ 2010-2017 (`reports/ea/us100-ftmo1-nq-2010-2017.md`).
  Usa ORB-retest 9:30-9:45, barridos PD/ON, VWAP ±2σ, FVG, RVOL y la ventana 9:35-11:30
  (`COLA-NQEDGE-FORWARD §1`).
- **NQF-A/B/C:** forward de NQ desde el 2026-11-30. No tiene datos todavía, así que no contamina el
  histórico.
- **Mismos subyacentes en CFD:** solo como etiqueta; esos datos **no se usan**.
  - El subyacente del ES (US500) tuvo **el EA completo** (ORB-retest, barridos ON/PD, VWAP ±2σ, FVG),
    escalado por ATR, de 2017-12-28 a 2026-11-24 (`reports/ea/us100-ftmo1-fuera-de-instrumento.md`;
    `03 §7`). También tuvo el impulso H1 de 9:00 a 10:00 con continuación hasta las 16:00, con el IS de
    2011-2023 leído (`reports/edge1_h1_ny_impulse.md`).
  - El del NQ tuvo `orb_ny`, `trend_intraday`, `caja_ny` y `h1_orb`.
  - El del GC tuvo `h1_orb` (sesión NY), `overlap_breakout` y `asian_rev`, más `orb_5m`, `vwap_bounce`
    y `momentum_burst` en el forward de `ai_trader` (`src/tradinglab/intraday.py:71-81`,
    `docs/estado.md`).

| Hipótesis | NQ/MNQ | ES/MES | GC/MGC |
|---|---|---|---|
| RB-01 ORB 15 min | contaminada | contaminada (EA en el subyacente, 2017-12 → 2026-11) | parcial (`h1_orb`, `orb_5m`) |
| RB-02 Opening drive | contaminada (ventana 9:35 y ORB del EA) | parcial (ventana del EA; impulso H1 → 16:00) | **limpia** |
| RB-03 VWAP reclaim | contaminada (VWAP ±2σ; NQF-C) | contaminada (VWAP ±2σ del EA) | parcial (`vwap_bounce`) |
| RB-04 Barrido ON y vuelta | contaminada (`use_on`; NQF-B) | contaminada (`use_on` del EA) | **limpia** (vecina: `asian_rev`) |
| RB-05 ORB fallido | contaminada (complemento del ORB) | contaminada | parcial |
| RB-06 IB estrecho → expansión | contaminada (`h1_orb` con filtro ATR) | parcial (NQ) | contaminada (`h1_orb` NY) |
| RB-07 Momentum intradía (primera media hora → última) | parcial (`trend_intraday`) | parcial (impulso H1) | limpia, **mecanismo débil** |
| RB-08 Reversión del hueco de apertura | parcial (niveles PD del EA) | parcial (ventana del EA) | no aplica (el oro cotiza de noche sin hueco de apertura) |

El veredicto de una prueba `parcial` siempre se publica con su etiqueta. Nunca se cita como "limpia".

## 4. Convenciones comunes (todas las hipótesis)

- **Hora:** ET (`America/New_York` con `zoneinfo`).
- **Barras M1:** se etiquetan por su minuto de inicio (la vela 9:34 cubre 9:34:00-9:34:59); FUT-B2 lo
  confirma con `ts_event`.
- **Sesión NY:**
  - ES: 9:30-16:00. Cierre forzado al cierre de la vela 15:54, es decir, 15:55, como en NQF.
  - GC: 8:20-13:30. Cierre forzado a las 13:25.
  - La hora de apertura de COMEX y de la liquidación del oro (8:20 y 13:30 ET) es **No verificada**:
    se confirma con la documentación de CME antes de registrar. Si no coincide, la hipótesis de GC se
    reescribe **antes** de ver datos.
- **Sesión nocturna (ON):** de las 18:00 del día anterior hasta el minuto previo a la apertura NY.
- **Contrato:** el front sin ajustar de la tabla de rolls. Todas las operaciones son intradía, así que
  ninguna cruza un roll.
- **Señal y entrada:** la señal sale al cierre de una vela M1 y se entra en la apertura de la siguiente.
- **Fills:**
  - stop: al precio del stop o a la apertura si hay hueco, lo que sea peor;
  - objetivo límite: solo si el precio lo **atraviesa** en 1 tick (corrige FUT-04);
  - si la misma vela toca el stop y el objetivo, gana el stop;
  - salida por tiempo: al cierre de la vela.
- **Una operación por día e hipótesis**, la primera señal. Las hipótesis no se combinan.
- **R neta por evento**, con `pv` el valor del punto y `tick_v` el valor del tick del micro (§5):

  ```text
  R_net = (dir·(salida − entrada)·pv − 2·(comisión + slippage_ticks·tick_v)) / (|entrada − stop|·pv)
  ```

  El slippage solo entra en el término de coste, para no contarlo dos veces.
- **Filtro de coste (ex ante):**
  - si `2·(comisión + 1·tick_v) / (|entrada − stop|·pv) > 0,25`, el evento **no se opera** y se cuenta;
  - si el stop queda a menos de 2 ticks, tampoco se opera.
- **Sin filtros de noticias** en la prueba principal, para no depender de un calendario que no existe
  en el repo. FOMC y los datos de las 8:30 se informan como subgrupo **después** del veredicto, sin
  cambiarlo.
- **Referencias publicadas:** se citan como "por verificar" y **sin cifras**, como en C1.

## 5. Contratos y costes

| Contrato | Tick | Valor del tick | USD/punto | Comisión por lado | Estado |
|---|---:|---:|---:|---|---|
| MES | 0,25 | 1,25 | 5 | **Sin datos** | especificación conocida (CME), se confirma con `definition` |
| MGC | 0,10 | 1,00 | 10 | **Sin datos** | ídem |
| MNQ | 0,25 | 0,50 | 2 | 0,75 USD (dato del operador, 2026-11-25, NQF) | ídem |
| ES / GC / NQ | 0,25 / 0,10 / 0,25 | 12,50 / 10 / 5 | 50 / 100 / 20 | **Sin datos** | solo informativo |

- **Base:** costes del micro (MES, MGC), que es lo que se opera en prop con riesgo pequeño, con
  **1 tick de slippage por lado**.
- **Estrés:** 2 ticks por lado (criterio §8 b) y 4 ticks (informativo). La comisión se multiplica por
  1,5 (informativo).
- **Comisiones de las firmas:** Topstep y otras son **Sin datos** (`config/propfund/costs.yaml:139-140`).
  El motor EV las aplica aparte.
- **Bloqueo:** la prueba de MES y MGC no se registra hasta que el operador fije su comisión, como hizo
  con MNQ.

**Coste en R** (1 tick por lado, solo slippage; la comisión se suma cuando exista):

| Stop | MES (5 USD/pt) | MGC (10 USD/pt) |
|---|---:|---:|
| 3 pt | 0,167 R | 0,067 R |
| 5 pt | 0,100 R | 0,040 R |
| 8 pt | 0,063 R | 0,025 R |
| 12 pt | 0,042 R | 0,017 R |

## 6. Hipótesis

Formato de cada ficha:
- **mecanismo:** quién paga y por qué;
- **regla:** fija;
- **eventos esperados:** se cuentan en FUT-D2 sin desenlaces;
- **decisión.**

`mR20` es la mediana del rango RTH (máximo − mínimo de la ventana NY) de las 20 sesiones anteriores,
**solo pasado**.

### RB-01 · ORB de 15 minutos con continuación
- **Mecanismo:** la información acumulada de noche y las órdenes de apertura se ejecutan en la primera
  hora. La ruptura del rango inicial señala un desequilibrio que sigue.
- **Regla:**
  - rango OR: 9:30-9:44;
  - señal: el primer cierre M1 entre 9:45 y 10:59 por encima de ORH + 1 tick o por debajo de ORL − 1 tick;
  - stop en el lado opuesto del OR;
  - salida a las 15:55.
- **Decisión:** **no se registra**:
  - es la lógica más minada, dentro y fuera del laboratorio;
  - en ES está `contaminada` y en GC es `parcial`;
  - en NQ la cubre NQF-A en forward.

### RB-02 · Opening drive
- **Mecanismo:** los desequilibrios de la subasta de apertura y los algoritmos de ejecución que reparten
  órdenes grandes en la primera hora persisten a corto plazo. El flujo de órdenes tiene memoria larga
  por el troceo de órdenes (literatura de microestructura, por verificar).
- **Regla, ES:**
  - impulso `d = close(9:34) − open(9:30)`; si `d = 0`, no se opera;
  - entrada en la apertura de las 9:35 en la dirección de `d`;
  - stop al otro extremo de las velas 9:30-9:34 ± 1 tick (para un largo, el mínimo − 1 tick);
  - salida al cierre de la vela 10:29, es decir, 10:30.
- **Regla, GC:** la misma, con 8:20-8:24, entrada a las 8:25 y salida a las 9:20.
- **Eventos:** casi todas las sesiones (≈ 3.300 por instrumento).
- **Decisión:** **familia primaria**:
  - ES, `parcial`;
  - GC, `limpia`.

### RB-03 · VWAP reclaim
- **Mecanismo (débil):** el VWAP de la sesión es la referencia de ejecución institucional. Recuperarlo
  tras mucho tiempo al otro lado señalaría un cambio de control.
- **Regla:**
  - VWAP desde las 9:30 con el precio típico de M1 y su volumen (`ohlcv`);
  - señal: el primer cierre M1 entre 10:00 y 11:30 al otro lado del VWAP tras ≥ 30 cierres seguidos en
    el lado contrario;
  - stop en el extremo de esas 30 velas ± 1 tick;
  - salida a las 15:55.
- **Decisión:** **no se registra**:
  - el mecanismo es débil;
  - en NQ y ES está `contaminada`, y en GC es `parcial`;
  - su complemento (el rechazo) tampoco se registra.

### RB-04 · Barrido del rango nocturno y vuelta (sweep & reject)
- **Mecanismo:** las órdenes stop se agrupan justo fuera de los extremos nocturnos. En la apertura, la
  liquidez de NY absorbe el flujo de esos stops y el precio vuelve (agrupación de stops: Osler, 2003,
  por verificar).
- **Regla, ES:**
  - condición: la apertura de las 9:30 cae estrictamente dentro de (ONL, ONH);
  - barrido: la primera vela entre 9:30 y 11:29 cuyo máximo llega a ONH + 1 tick (o cuyo mínimo llega a
    ONL − 1 tick); si en la misma vela se tocan los dos extremos, no se opera;
  - señal: dentro de las 5 velas siguientes, contando la del barrido, un cierre M1 vuelve dentro del
    rango;
  - entrada en contra del barrido en la apertura siguiente;
  - stop en el extremo del barrido ± 1 tick;
  - objetivo en el punto medio de ON (límite);
  - salida por tiempo a las 15:55.
- **Regla, GC:** la misma con ON hasta las 8:19, ventana 8:20-11:29 y salida a las 13:25.
- **Eventos:** condicionados; **Sin datos** hasta el conteo.
- **Decisión:** **familia primaria solo en GC** (`limpia`), si el conteo da n ≥ 2.258 (§7). En ES no
  se registra: el EA ya aplicó `use_on` a su subyacente.
- **Diferencia con NQF-B:** NQF-B usa velas M5, un barrido de ≥ 2 ticks, 3 velas y objetivo en el VWAP.
  No se comparan entre sí porque son instrumentos distintos.

### RB-05 · ORB fallido (desvanecimiento)
- **Regla:**
  - tras una ruptura RB-01, un cierre M1 vuelve dentro del OR en ≤ 10 velas;
  - entrada en contra;
  - stop en el extremo de la ruptura ± 1 tick;
  - objetivo en el lado opuesto del OR;
  - salida a las 15:55.
- **Decisión:** **no se registra**:
  - es el complemento de RB-01, así que hereda su contaminación;
  - los eventos están condicionados a dos sucesos.

### RB-06 · IB estrecho → expansión
- **Mecanismo:** la volatilidad se agrupa y la compresión del primer tramo tiende a expandirse.
- **Regla:**
  - IB: 9:30-10:29; es estrecho si su ancho es menor que la mediana de las 20 sesiones anteriores;
  - señal: el primer cierre M1 fuera del IB ± 1 tick entre 10:30 y 13:59;
  - stop en el punto medio del IB;
  - salida a las 15:55.
- **Decisión:** **no se registra**:
  - está `contaminada` en NQ y en GC;
  - en ES solo es `parcial` y el filtro reduce los eventos a ≈ 50 %.

### RB-07 · Momentum intradía: primera media hora → última media hora
- **Mecanismo:** el rebalanceo poco frecuente, los operadores que se informan tarde y la cobertura gamma
  de los dealers de opciones sobre el índice empujan el final de la sesión en la dirección del principio.
  Referencias por verificar: Gao, Han, Li y Zhou (2018), *Market intraday momentum*; Baltussen, Da,
  Lammers y Martens (2021), *Hedging demand and market intraday momentum*.
- **Regla, ES:**
  - señal: `s = signo(close(9:59) − close(15:59 de la sesión anterior))`; si `s = 0`, no se opera;
  - entrada a la apertura de las 15:30 en la dirección de `s`;
  - stop a `0,25·mR20` de la entrada (fijo, sin optimizar);
  - salida al cierre de la vela 15:59.
  - Excepción: la salida forzada de las 15:55 **no** aplica a esta hipótesis; su ventana es
    15:30-16:00. Las firmas que exigen cerrar antes (Topstep: 15:10 CT = 16:10 ET) lo permiten.
- **Eventos:** casi todas las sesiones.
- **Decisión:** **familia primaria** en ES (`parcial`). En GC no se registra porque el mecanismo de
  cobertura gamma es del índice.

### RB-08 · Reversión del hueco de apertura
- **Mecanismo:** con poca liquidez nocturna, el hueco se pasa de rosca. En la apertura, la liquidez de NY
  lo corrige en parte. Hay literatura sobre la oposición entre el rendimiento nocturno y el intradía,
  por verificar.
- **Regla, ES:**
  - hueco: `g = open(9:30) − close(15:59 de la sesión anterior)`;
  - condición: `|g| ≥ 0,25·mR20`;
  - entrada en la apertura de las 9:31, contra el hueco;
  - objetivo en `close(15:59)` de la sesión anterior (límite);
  - stop a `|g|` de la entrada;
  - salida por tiempo al cierre de las 11:29.
- **Eventos:** condicionados; **Sin datos** hasta el conteo.
- **Decisión:** **familia primaria** en ES (`parcial`), si n ≥ 2.258.

## 7. Potencia frente a la ventaja mínima útil

`MDE = (z_{1−α/K} + z_{0,8})·σ/√n`, unilateral, potencia del 80 %.
- σ supuesta = 1,5 R. Es conservadora: las reglas con salida por tiempo no tienen techo.
- 1,2 R se da como referencia para las reglas con objetivo.

| n eventos | K = 5, σ = 1,2 | K = 5, σ = 1,4 | K = 5, σ = 1,5 |
|---:|---:|---:|---:|
| 200 (forward de un año) | 0,269 R | 0,314 R | 0,336 R |
| 1.000 | 0,120 R | 0,140 R | 0,150 R |
| 1.650 (≈ 50 % de las sesiones) | 0,094 R | 0,109 R | 0,117 R |
| 2.640 | 0,074 R | 0,086 R | 0,092 R |
| 3.300 (≈ todas las sesiones 2010-06 → 2023-12) | **0,066 R** | 0,077 R | **0,083 R** |

**Ventaja mínima útil:**
- Provisional: μ\* ≈ **+0,08 R** neta, según la regla de `risk/01 §5`. Es la primera fila que justifica
  comprar evaluaciones en Topstep 50K con presupuesto de 1.500 USD.
- Se sustituye por el μ\* de FUT-A7 por programa en cuanto exista.

**Reglas de potencia (fijadas aquí):**
- **n mínimo para registrar** = 2.258, el n con el que la MDE es ≤ 0,10 R con σ = 1,5 y K = 5. Las
  hipótesis condicionadas (RB-04, RB-08) que no lleguen, **no se registran**.
- **"Rechazada" no descarta una ventaja útil** si la MDE de su n es mayor que 0,08 R. El informe lo
  escribe.
- **El forward por sí solo no descubre ventajas de +0,08 R:** con n = 200 la MDE es ≈ 0,3 R. El
  forward sirve para confirmar, no para descubrir.

## 8. Familia primaria FUT-RB-1 y criterio de rechazo (escrito antes de ver datos)

| # | Prueba | Instrumento | Contaminación | Eventos |
|---|---|---|---|---|
| 1 | RB-02 Opening drive | ES (costes MES) | parcial | ≈ 3.300 |
| 2 | RB-02 Opening drive | GC (costes MGC) | limpia | ≈ 3.300 |
| 3 | RB-04 Barrido ON y vuelta | GC | limpia | conteo |
| 4 | RB-07 Momentum intradía | ES | parcial | ≈ 3.300 |
| 5 | RB-08 Reversión del hueco | ES | parcial | conteo |

- **K** es el número de pruebas que pasan las condiciones D-1…D-4 y el n mínimo, con **K ≤ 5**.
  - Se fija **al registrar**, antes de calcular ningún desenlace.
  - α = 0,05/K; con K = 5, el t crítico es 2,326.
- **IDs:**
  - campaña `FUT-RB-1`;
  - hipótesis `H-2026-NNN`, asignadas al registrar;
  - etiquetas internas `RB-02-ES`, `RB-02-GC`, etc.

**Estadístico.** Media de `R_net` por evento. t HAC de Newey-West con 5 retardos sobre la serie de
eventos (uno por sesión). Unilateral.

| Criterio | Regla | Si falla |
|---|---|---|
| (a) | t ≥ t crítico de Bonferroni (2,326 con K = 5) | **rechazada** |
| (b) | Media de `R_net` con 2 ticks por lado > 0 | **rechazada por costes** |
| (c) | Mismo signo de la media en 2010-06-07 → 2016-12-31 y en 2017-01-01 → 2023-12-31 | **inconclusa** |
| (d) informativo | Media ≥ μ\* (0,08 R provisional) | "candidata, no monetizable todavía en prop" |

- **Si pasa (a)-(c):** queda como **candidata**, no validada.
- **Siguiente control:** una sola lectura del OOS-2 de futuros (2024-01-01 → 2026-11-20), con
  autorización del operador y Bonferroni sobre las lecturas de OOS-2 de la línea (ADR-F10). Confirma si
  se cumplen las dos condiciones:
  - la media de `R_net` es > 0;
  - la media de la muestra principal cae dentro del IC al 95 % del OOS-2.
- **Después:**
  - motor EV (FUT-A) con la **cota inferior** de la ventaja;
  - forward en paper con MES/MGC, n ≥ 200, que sirve de confirmación.
- **No se repite** con otros parámetros pase lo que pase. Una variante nueva es otra prueba, con otro
  registro y su +1.
- **Placebo temporal, que no suma:** RB-02 con la misma regla desplazada a una hora sin apertura (ES:
  impulso 12:30-12:34, entrada 12:35, salida 13:30; GC: 11:30-11:34, entrada 11:35, salida 12:30). Sirve
  para ver si el efecto es propio de la apertura. Se informa y no decide; no se elige entre la principal
  y el placebo. (Invertir la dirección no sería un placebo: solo cambia el signo menos los costes.)

## 9. NQ/MNQ

- **Histórico:** no se registra nada nuevo.
  - 2010-2018 está `contaminada` para las lógicas del EA y `parcial` para RB-07 y RB-08.
  - 2019+ es **Sin datos** en M1.
- **Forward:** NQF-A/B/C, ya congelados, cubren RB-01, RB-04 y RB-03 en NQ. No se tocan.
- **Réplica condicional (propuesta, no se registra ahora):**
  - Solo si RB-07-ES o RB-08-ES pasan §8 **y** su lectura de OOS-2, se ejecuta la misma regla en NQ M1
    2010-06 → 2018-12 (≈ 2.150 sesiones, `parcial`) como prueba nueva, con +1 cada una.
  - La MDE es ≈ 0,08 R con σ = 1,5 y α = 0,05 (prueba única): sirve como réplica, no como
    descubrimiento.
- **Operar NQ con una ventaja validada en ES no está permitido:** hay que validar la regla en NQ.
  Mientras tanto, la ejecución de una ventaja de ES es en MES.

## 10. Orden de trabajo y tareas

| Paso | Qué | Quién | Estado |
|---|---|---|---|
| 1 | Verificar con la documentación de CME las horas de apertura y liquidación de GC (§4) y las especificaciones del §5 | Claude (FUT-E1 o una sesión aparte) | READY |
| 2 | OP-8: partición del holdout de futuros (§2) | operador | **aprobada (2026-11-28)** |
| 3 | OP-4 ampliada: `ohlcv-1m` + `definition` de ES y GC de 2010-06 a 2026-11, con el coste exacto de FUT-B1 | operador | pendiente |
| 4 | Comisión por lado de MES y MGC | operador | **Sin datos** |
| 5 | **FUT-D2:** conteo de eventos **sin desenlaces** y consulta de contaminación en `lab.db` (solo lectura) | OpenCode (DeepSeek V4.1 Flash), en el equipo del operador | BLOCKED (3: compra de datos) |
| 6 | Fijar K y registrar `FUT-RB-1` (+K) | operador | BLOCKED (2-5) |
| 7 | **FUT-D3:** evaluador único RB (calcula `R_net` una sola vez y escribe el informe con los criterios del §8) | OpenCode | BLOCKED (6) |

**Aceptación de FUT-D2:**
- La salida no tiene ninguna columna de P&L, R, salida, objetivo alcanzado ni stop tocado; un test lo
  comprueba sobre los nombres de las columnas.
- Cuenta, por hipótesis, instrumento y año:
  - sesiones válidas;
  - eventos;
  - eventos excluidos por el filtro de coste;
  - stops por debajo de 2 ticks;
  - sesiones excluidas por D-1, D-2 y D-3.
- Abre `lab.db` con `mode=ro` y lista `strategy_trials` cuyo `symbol` sea `ES`, `GC`, `US500` o
  `XAUUSD`. Los dos últimos son los alias de los ficheros Databento de futuros y también pueden ser CFD:
  se listan **solo** para la etiqueta de contaminación. Se agrupan por `family` y por ventana.
- No lee ninguna fila con fecha ≥ 2024-01-01: lo comprueba un test con un fichero sintético.

**Aceptación de FUT-D3:** cifras exactas sobre un conjunto sintético con desenlaces conocidos:
- `R_net` de un largo con stop y objetivo;
- relleno con hueco;
- misma vela con stop y objetivo → stop;
- objetivo tocado sin atravesar → no se llena;
- t HAC sobre una serie conocida.

Los prompts pegables de D2 y D3 se escriben cuando se desbloquee el paso 3, porque necesitan el
esquema real de los ficheros M1.
