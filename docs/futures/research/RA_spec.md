# FUT-C0 · Research A (microestructura y order flow) · especificación y borradores de prerregistro

**Fecha:** 2026-11-28 · **Autor:** Claude Code (skills `hypothesis-preregistration` y
`backtest-leakage-audit`) · **Estado:** BORRADORES.
**Nada de esto está registrado ni se ha ejecutado.** Solo datos de futuros CME (decisión del operador
del 2026-11-28).
**Independencia (ADR-F07):** contador, campañas, informes y decisiones separados de Research B
(`RB_spec.md`). Un híbrido solo se estudia cuando las dos líneas hayan validado algo cada una.

## 0. Resumen

1. **Diez hipótesis A-J** con fórmulas y umbrales fijados ahora. Ninguna se ajusta después.
2. **Ninguna hipótesis de order flow se evalúa con barras** (ADR-F05). El mínimo es L1a `trades` (lado
   agresor) más L1b `tbbo`/`mbp-1` para los fills. B y J necesitan L2 `mbp-10`.
3. **Familia primaria FUT-RA-1:**
   - 6 pruebas (A, C, D, E, H, I);
   - señales con los trades de **NQ** y ejecución con las cotizaciones y costes de **MNQ**;
   - periodo 2019-06-03 → 2023-12-29;
   - Bonferroni α = 0,05/6.
4. **Los datos de ticks de futuros nunca se han visto en el laboratorio:** el campo es limpio. La
   excepción es B, que es una lógica vecina del barrido de niveles del EA (`parcial` en NQ).
5. **Los costes mandan:**
   - con un stop de 5 puntos en MNQ, el coste es **0,25 R** (1 tick por lado) o 0,35 R (2 ticks);
   - para llegar a μ\* ≈ +0,08 R neta hace falta una ventaja bruta ≥ 0,33-0,43 R;
   - los stops por debajo de 4,2 puntos no se operan (filtro ex ante).
6. **Bloqueos:**
   - compra de datos (OP-4), con el coste exacto de FUT-B1;
   - OP-7 (qué incluye la comisión de MNQ);
   - OP-8 (sello del holdout de futuros): **aprobada el 2026-11-28**.

## 1. Reglas de esta línea

Son las mismas que en `RB_spec.md §1`:
- pruebas únicas;
- reglas escritas antes de ver datos;
- antes de registrar, solo conteos sin desenlaces;
- OOS-2 sellado: el código descarta las filas ≥ 2024-01-01 **antes** de construir rasgos;
- registrar suma K a `count_tests`, y lo hace el operador.

**Periodo de ingeniería.** El código de rasgos (footprint, delta, profundidad) se depura **solo** con
datos sintéticos y con el periodo de ingeniería 2019-05-06 → 2019-05-31: el primer mes de MNQ, que
queda fuera de la muestra.
- **No verificado:** que MNQ empezó a cotizar el 2019-05-06. Se confirma con `definition` en FUT-B2; si
  no coincide, el periodo se desplaza al primer mes real **antes** de ver datos.
- Ningún desenlace se calcula en el periodo de ingeniería; solo se comprueba la mecánica.

## 2. Datos (solo futuros, Databento `GLBX.MDP3`)

| Nivel | Esquema | Uso | Raíz | Rango |
|---|---|---|---|---|
| L1a | `trades` | lado agresor, delta, CVD, footprint | NQ (señal) | 2019-05-06 → 2026-11 (OOS-2 sellado) |
| L1b | `tbbo` (o `mbp-1`) | spread, fills de entradas, stops y salidas | MNQ (ejecución) y NQ (control) | ídem |
| L2 | `mbp-10` | profundidad, reposición (B, J) | NQ | ídem (familia RA-2, más tarde) |
| L3 | `mbo` | icebergs, cola de límites (A3, versiones con límites) | NQ, MNQ | familia RA-3, más tarde |
| Ref. | `definition`, `status` | contratos, `instrument_id`, rolls, festivos | NQ, MNQ | ídem |

- **Hoy:** **Sin datos** en todos los niveles (FUT-12).
- **Coste:** **Sin datos**; FUT-B1 lo calcula solo con metadatos.
- **Si el presupuesto lo permite:** ampliar la muestra hacia atrás desde 2017-01 con señales de NQ y
  ejecución en NQ, mientras no exista MNQ. Se decide **antes** de comprar, nunca después de ver datos.
- **Lado agresor:** en `trades`, `side = B` es compra agresora (+1), `side = A` es venta agresora (−1) y
  `N` se excluye y se cuenta. Es la documentación de Databento, **por confirmar** en FUT-B2.
- **Compra (lectura de FUT-B1, 2026-11-28):** `tbbo` trae cada trade (precio, tamaño, lado agresor) con
  el mejor bid/ask previo; en B1 tiene los mismos registros que `trades` en NQ, MNQ, ES y MES. Para L1a
  y L1b basta `tbbo`: `trades` no se compra aparte (`evidencia/OP4_lectura_costes_2026-11.md`).
- **Condiciones** (si no se cumplen: Sin datos, no se registra):
  - cobertura ≥ 99 % de los segundos de RTH con al menos un mensaje en `tbbo` por sesión;
  - las sesiones con huecos > 5 s en RTH se excluyen y se cuentan;
  - rolls desde `definition` (se excluyen el día del roll y el anterior);
  - auditoría `futures-data-audit` y manifiesto con hash.

## 3. Notación (todas las hipótesis)

- Cada trade `i` tiene hora `τ_i`, precio `p_i` (en ticks), tamaño `q_i` y agresor `a_i ∈ {+1, −1}`.
- Velas de 1 minuto en ET (`America/New_York`), RTH 9:30-15:59. Para la vela `t`:
  - volumen `V_t = Σ q_i`;
  - delta `Δ_t = Σ a_i·q_i`;
  - `CVD_t = Σ_{s ≤ t} Δ_s`, que se reinicia a las 9:30;
  - OHLC de los trades.
- **Footprint** de la vela `t` en el nivel `k`:
  - `B_t(k) = Σ q_i` con `a_i = +1` y `p_i = k` (compras agresoras);
  - `S_t(k)` igual con `a_i = −1`.
- **Referencias móviles, solo pasado,** sobre las 20 sesiones anteriores en el mismo minuto del día `m`:
  - `medV(m)`: mediana de `V`;
  - `sΔ(m) = 1,4826·MAD(Δ)`, una escala robusta;
  - `medRng(m)`: mediana del rango high − low;
  - `medL`: mediana de los volúmenes `B + S` no nulos por nivel en la RTH de esas 20 sesiones.
- `zΔ_t = Δ_t / sΔ(m_t)`.
- `R30_t`: máximo y mínimo de las velas `t−30 … t−1`.

## 4. Convenciones comunes

- **Ventana de señales:** 9:45-15:30 ET. Cierre forzado a las 15:55.
  - Aclaración del 2026-11-28, antes de ver datos: `R30` exige las 30 velas RTH anteriores, así que C, E
    y H no pueden saltar antes de las 10:00. A, D e I sí pueden desde las 9:45.
  - El objetivo de 1,5 R se pone en la rejilla de ticks, redondeado hacia fuera de la entrada.
- **Eventos:** como máximo 3 por sesión e hipótesis, separados ≥ 15 minutos desde la entrada anterior.
  Solo una posición a la vez por hipótesis.
- **Latencia base:** L = 500 ms desde el cierre de la vela de la señal. Estrés: +1 s (criterio) y +5 s
  (informativo). La latencia real de las plataformas de las firmas es **Sin datos** (FUT-E1).
- **Fills con L1b (MNQ):**
  - **Entrada a mercado:** al mejor ask (largo) o al mejor bid (corto) en `τ_señal + L`. Si el tamaño
    supera el que hay en el mejor nivel, 1 tick más.
  - **Stop a mercado:** se dispara con el primer trade en el stop o más allá. Se llena al mejor bid
    (largo) en `τ_disparo + L`.
  - **Objetivo límite:** solo se llena si un trade lo **atraviesa** en 1 tick (sin cola; la cola llega
    con L3).
  - **Salida por tiempo:** a mercado a los 15 minutos de la entrada (5 en J).
  - Si en el mismo segundo se tocan el stop y el objetivo, gana el stop.
- **Objetivo:** 1,5 R en todas las hipótesis que lo usan. Es fijo y no se ajusta.
- **R neta**, con 1 R = `|entrada − stop|·2 USD` por MNQ:

  ```text
  R_net = (dir·(salida − entrada)·2 − 2·comisión) / (|entrada − stop|·2)
  ```

  Los precios ya son los de cotización (spread incluido). El estrés añade ticks a los precios.
- **Filtro de coste (ex ante):** con `coste_R = (2·0,75 + 2·0,50) / (|entrada − stop|·2) > 0,30`
  (stop < 4,2 puntos), no se opera y se cuenta.
- **Comisión:** 0,75 USD por lado en MNQ (dato del operador, 2026-11-25). OP-7 debe aclarar si incluye
  exchange, clearing y NFA. Si no los incluye, se suman **antes** de registrar.

| Stop | MNQ, 1 tick por lado | MNQ, 2 ticks por lado | NQ, solo slippage | NQ con el todo incluido de Tradeify (5,76 USD ida y vuelta) |
|---:|---:|---:|---:|---:|
| 5 pt | **0,250 R** | 0,350 R | 0,100 R | 0,158 R |
| 10 pt | 0,125 R | 0,175 R | 0,050 R | 0,079 R |
| 15 pt | 0,083 R | 0,117 R | 0,033 R | 0,053 R |
| 20 pt | 0,063 R | 0,088 R | 0,025 R | 0,039 R |

**Lectura:**
- Con stops cortos, el micro es caro en R.
- El mini cuesta menos de la mitad en R, pero 1 NQ con un stop de 5 puntos son 100 USD de riesgo.
- La prueba usa los costes de MNQ (lo conservador) e informa de los de NQ.

## 5. Hipótesis

### A · Absorción
- **Mecanismo:** un comprador pasivo grande (límites, icebergs) absorbe la venta agresiva sin que el
  precio baje. La liquidez pasiva motivada revela interés institucional. Cuando los vendedores se
  agotan, el precio sube.
- **Señal de compra en la vela `t`:**
  - `zΔ_t ≤ −3`;
  - `close_t ≥ open_t`;
  - `V_t ≥ 2·medV(m_t)`.
- **Entrada:** largo. **Stop:** `low_t − 1 tick`. Es simétrica para la venta.
- **Datos:** L1a + L1b. La versión **A3** con L3 (reposiciones en el mismo precio = iceberg) es otra
  prueba, en RA-3.
- **Decisión:** **RA-1**.

### B · Barrido de liquidez
- **Mecanismo:** las órdenes stop y la liquidez visible se acumulan más allá del extremo de la sesión.
  Los participantes grandes usan esa liquidez para llenarse y el precio se da la vuelta.
- **Nivel:** `X` = máximo RTH de la sesión hasta `t−1`, con señales solo después de las 10:00.
- **Condición L2:** la profundidad del ask en los 4 ticks por encima de `X`, justo antes del barrido, es
  ≥ 2 veces su mediana en las 20 sesiones anteriores.
- **Señal:**
  - un trade en `X + 1 tick` o más arriba;
  - en ≤ 60 s el precio vuelve a `X − 1 tick` o más abajo;
  - el delta de esos 60 s es < 0.
- **Entrada:** corto. **Stop:** máximo del barrido + 1 tick. Es simétrica.
- **Datos:** L2 `mbp-10`; L3 para distinguir órdenes canceladas de ejecutadas.
- **Contaminación:** `parcial` en NQ. Es una lógica vecina del barrido de niveles ON/PD del EA, aunque
  aquí el nivel es otro (el extremo RTH en curso).
- **Decisión:** **RA-2** (cuando haya L2).

### C · Divergencia de delta
- **Mecanismo:** un máximo nuevo sin compra agresora detrás significa que lo empujan órdenes pasivas o
  stops, no compradores. No se sostiene.
- **Señal de venta:**
  - `t0` = argmax del high en `[t−30, t−1]`;
  - `high_t > high_{t0}`;
  - `CVD_t < CVD_{t0} − sC`, donde `sC = 1,4826·MAD` de las variaciones de CVD a 30 minutos en las
    20 sesiones anteriores.
- **Entrada:** corto. **Stop:** `high_t + 1 tick`. Es simétrica.
- **Datos:** L1a + L1b.
- **Decisión:** **RA-1**.

### D · Desequilibrios apilados
- **Mecanismo:** compradores que levantan ofertas en varios niveles seguidos muestran urgencia, a menudo
  informada. El flujo de órdenes persiste.
- **Desequilibrio diagonal de compra en `k`:**
  - `B_t(k) ≥ 3·S_t(k−1)`;
  - `B_t(k) ≥ medL`.
- **Señal de compra:**
  - al menos 3 niveles consecutivos con desequilibrio;
  - `close_t ≥ (high_t + low_t)/2`.
- **Entrada:** largo. **Stop:** nivel más bajo del apilamiento − 1 tick. Es simétrica.
- **Datos:** L1a + L1b.
- **Decisión:** **RA-1**.

### E · Ruptura sin confirmación (fallida)
- **Mecanismo:** si una ruptura no tiene compra agresora, la hacen stops y no compradores nuevos, y
  vuelve.
- **Señal de venta:**
  - `close_t > max(R30_t) + 1 tick`;
  - `Δ_t < 0`.
- **Entrada:** corto. **Stop:** `high_t + 1 tick`. Es simétrica.
- **Datos:** L1a + L1b.
- **Contaminación:** limpia. El rango es móvil de 30 minutos, no el OR de la apertura (RB-05).
- **Decisión:** **RA-1**.

### F · Subasta inacabada en el extremo
- **Medida:** un máximo nuevo de la sesión cuya vela tiene compras **y** ventas en el tick superior
  (`B_t(top) > 0` y `S_t(top) > 0`), es decir, sin exceso. La hipótesis es que vuelve a visitarse
  (`top + 1 tick`) en ≤ 60 minutos con más frecuencia que un máximo con exceso.
- **Decisión:** **no se registra.** Es una medida de frecuencia, no una regla operable. Si se quiere
  estudiar, sería una prueba informativa aparte, que también sumaría.

### G · Agotamiento
- **Señal de venta:**
  - máximo nuevo de 30 velas;
  - el volumen en los 2 ticks superiores es ≤ 5 % de `V_t`;
  - `0 < zΔ_t < 1`;
  - `V_t ≥ medV(m_t)`.
- **Entrada:** corto. **Stop:** `high_t + 1 tick`.
- **Decisión:** **no se registra** en RA-1. Tiene cuatro umbrales a la vez y se rompe con facilidad. Se
  deja definida para no reinventarla después de ver datos.

### H · Ruptura confirmada
- **Mecanismo:** si la ruptura llega con compra agresora fuerte y un CVD que sube, la empuja la demanda
  y continúa. Es la condición opuesta a E: las dos no se solapan.
- **Señal de compra:**
  - `close_t > max(R30_t) + 1 tick`;
  - `zΔ_t ≥ +2`;
  - `CVD_t − CVD_{t−30} > 0`.
- **Entrada:** largo. **Stop:** `low_t − 1 tick`. Es simétrica.
- **Datos:** L1a + L1b.
- **Decisión:** **RA-1**.

### I · Expansión de volumen con dirección del delta
- **Mecanismo:** un choque de volumen y rango con el delta del mismo signo es un evento de información
  que el precio tarda minutos en incorporar.
- **Señal:**
  - `V_t ≥ 3·medV(m_t)`;
  - `high_t − low_t ≥ 2·medRng(m_t)`;
  - `signo(Δ_t) = signo(close_t − open_t) ≠ 0`.
- **Entrada:** en esa dirección. **Stop:** extremo opuesto de la vela ± 1 tick.
- **Datos:** L1a + L1b. La versión con barras y la dirección de la vela es un **proxy** y no puede
  aprobar (ADR-F05).
- **Decisión:** **RA-1**.

### J · Reposición de liquidez (resiliencia del libro)
- **Mecanismo:** si tras un barrido vendedor la profundidad del bid se repone enseguida, hay compradores
  pasivos fuertes. El libro resiliente anticipa una subida.
- **Barrido vendedor:** en ≤ 1 s, el mejor bid baja ≥ 2 ticks.
- **Resiliencia:** `ρ` = profundidad del bid en los niveles 1-3 a `τ + 2 s`, dividida entre la de
  `τ − 1 s`.
- **Señal:**
  - `ρ ≥ 0,8`;
  - el mejor bid vuelve a ≥ el previo − 1 tick en ≤ 5 s.
- **Entrada:** largo a `τ + 5 s + L`. **Stop:** mínimo del barrido − 1 tick. **Salida por tiempo:**
  5 minutos.
- **Datos:** L2 `mbp-10`; L3 mejor.
- **Riesgo:** depende de la latencia (criterio c).
- **Decisión:** **RA-2**.

### Niveles de datos por hipótesis

| Hipótesis | Mínimo | Mejor | Familia |
|---|---|---|---|
| A Absorción | L1a + L1b | L3 (A3) | RA-1 (A3 en RA-3) |
| B Barrido | L2 | L3 | RA-2 |
| C Divergencia de delta | L1a + L1b | — | RA-1 |
| D Desequilibrios apilados | L1a + L1b | — | RA-1 |
| E Ruptura sin confirmación | L1a + L1b | — | RA-1 |
| F Subasta inacabada | L1a | — | no se registra |
| G Agotamiento | L1a + L1b | — | no se registra |
| H Ruptura confirmada | L1a + L1b | — | RA-1 |
| I Expansión de volumen | L1a + L1b | — | RA-1 |
| J Reposición de liquidez | L2 | L3 | RA-2 |

## 6. Potencia

- **Muestra:** 2019-06-03 → 2023-12-29, unas 1.140 sesiones descontando festivos y rolls.
- **Eventos:** como máximo unos 3.400 por hipótesis.
- **Dependencia dentro de la sesión:** error estándar agrupado por sesión. Para planificar se supone un
  efecto de diseño de 1,5 (`n_ef = n/1,5`).
- **σ supuesta:** 1,2 R. Son reglas con objetivo de 1,5 R y salida a 15 minutos.

| Eventos n | MDE, K = 6, σ = 1,0 | MDE, K = 6, σ = 1,2 |
|---:|---:|---:|
| 750 | 0,145 R | 0,174 R |
| 1.000 | 0,125 R | 0,150 R |
| 2.000 | 0,089 R | 0,106 R |
| 3.400 | ≈ 0,068 R | ≈ 0,081 R |

- **n mínimo para registrar:** **2.261 eventos**, el n con el que la MDE es ≤ 0,10 R con σ = 1,2,
  K = 6 y efecto de diseño 1,5. El conteo FUT-C2 (sin desenlaces) lo decide.
- **Ventaja mínima útil:** μ\* ≈ +0,08 R neta (provisional, `risk/01 §5`), hasta que exista FUT-A7.
- **"Rechazada" con una MDE > 0,08 no descarta** una ventaja útil, y el informe lo escribe.

## 7. Familia FUT-RA-1 y criterio de rechazo (escrito antes de ver datos)

- **Pruebas:** A, C, D, E, H e I sobre NQ (señal) y MNQ (ejecución).
- **K:** el número que pasa las condiciones de §2 y el n mínimo, con K ≤ 6. Se fija al registrar.
- **IDs:**
  - campaña `FUT-RA-1`;
  - hipótesis `H-2026-NNN` al registrar;
  - etiquetas `RA-A-NQ`, `RA-C-NQ`, etc.
- **Estadístico:** media de `R_net` por evento, con t agrupado por sesión (CR1). Unilateral.

| Criterio | Regla | Si falla |
|---|---|---|
| (a) | t ≥ z de Bonferroni (2,394 con K = 6) con fills base (L1b, latencia de 500 ms, comisión) | **rechazada** |
| (b) | Media > 0 con +1 tick adicional por lado | **rechazada por costes** |
| (c) | Media > 0 con latencia +1 s | **rechazada por latencia** |
| (d) | Mismo signo en 2019-06 → 2021-06 y en 2021-07 → 2023-12 | **inconclusa** |
| (e) informativo | Mediana del tiempo en posición ≥ 30 s | si no se cumple: "no operable en firmas con reglas de microscalping" (Lucid 5 s, Tradeify y TradeDay ≈ 10 s, ×3; `MOD-NR` NR-A2) |
| (f) informativo | Media ≥ μ\* | si no se cumple: "candidata, no monetizable todavía en prop" |

- **Si pasa (a)-(d):** queda como **candidata**.
- **Siguiente control:**
  - lectura única del OOS-2 de futuros con autorización y Bonferroni sobre las lecturas de la línea
    (ADR-F10). Confirma si la media de `R_net` > 0 y la media de la muestra cae dentro del IC al 95 %
    del OOS-2;
  - después, motor EV con la cota inferior;
  - por último, forward en paper con MNQ y el feed de la plataforma real (FUT-E1).
- **No se repite** con otros umbrales. Una variante es una prueba nueva, con su +1.
- **Réplicas:** ES/MES y GC/MGC, solo con las hipótesis que pasen RA-1 y su OOS-2, como familias nuevas
  (RA-1-ES, RA-1-GC). No hay transferencia sin prueba.

## 8. Tareas

| Paso | Qué | Quién | Estado |
|---|---|---|---|
| 1 | FUT-B1: coste exacto de `trades` + `tbbo` de NQ y MNQ, y `definition`, de 2019-05 a 2026-11 (también desde 2017-01, como opción) | OpenCode en el equipo del operador | **HECHO** 2026-11-28 (`evidencia/databento_costes_2026-11.md`) |
| 2 | OP-4 (compra), OP-7 (comisión); OP-8 (sello) aprobada el 2026-11-28 | operador | pendiente OP-4 y OP-7 (OP-8 aprobada) |
| 3 | **FUT-C1:** rasgos L1a (velas de delta, CVD, footprint y referencias móviles) con tests sintéticos y cifras exactas | Claude | **HECHO en código** (`futures/orderflow.py`); con datos reales espera a OP-4 |
| 4 | **FUT-C2:** conteo de eventos A-I **sin desenlaces**, por hipótesis y año, con exclusiones | OpenCode | **HECHO en código** 2026-11-28 (`futures/research_a.py`); el conteo real espera a los datos |
| 5 | Fijar K y registrar `FUT-RA-1` (+K) | operador | BLOCKED (4) |
| 6 | **FUT-C3:** evaluador único con fills L1b, latencia, estrés y criterios del §7 | OpenCode + correcciones de Claude | **HECHO en código** 2026-11-28 (`futures/research_a_eval.py`); NO se ejecuta con datos reales hasta el paso 5 |

**Aceptación de FUT-C1:** cifras exactas sobre un conjunto sintético de trades:
- `Δ`, `CVD` (que se reinicia a las 9:30), `B_t(k)` y `S_t(k)`;
- desequilibrio diagonal;
- `medV` y `sΔ` solo con pasado (un test cambia el futuro y comprueba que no cambia nada);
- un test comprueba que las filas ≥ 2024-01-01 se descartan antes de cualquier cálculo;
- `side = N` se excluye y se cuenta.

**Aceptación de FUT-C3:**
- entrada al ask en `τ + L`;
- stop disparado por un trade y llenado al bid;
- objetivo tocado sin atravesar → no se llena;
- t CR1 sobre una serie sintética conocida.

Los prompts pegables de C1-C3 se escriben cuando se desbloquee el paso 2, porque dependen del esquema
real de `trades` y `tbbo` que devuelva FUT-B2.
