# COLA TL3 · Ciclo 1 (ejecución continua)

**Modelo:** DeepSeek V4.1 Flash (OpenCode Go). **Redacta:** Claude (auditoría TL3), 2026-11-25 11:00.
**Base:** `TL3_REPORTS/*.md` (auditoría) y `.orquestador/ENMIENDA-NQ-B.md`.
**Modo de ejecución (operador, 2026-11-25):** «quiero que una tarea se ejecute una detrás de la otra
sin parar». Los bloques corren en cadena **sin pedir confirmación**. Ver §1.

Todos los prerregistros de esta cola están **escritos antes de ver ningún resultado** de los datos que
usan. OpenCode los transcribe y ejecuta; **no los cambia**.

## 0. Arranque

- **Empieza cuando** exista `.orquestador/RESULTADO-NQ-B.md` con el bloque E4 cerrado (la cadena NQ-B
  ha terminado, con cualquier veredicto). Mientras no exista, comprueba cada 2 minutos y sigue sola.
  Así no hay dos procesos escribiendo en el repo a la vez.
- **Rama:** la actual (`feature/prop-fund-multifirm`). Commits pequeños con prefijo `tl3:`. Sin push.
- **Pruebas que suman al contador** (las registra el operador **antes** de lanzar la cola, §7):
  T7 (1) y T8 (1). Ninguna otra tarea de esta cola suma.

## 1. Reglas de la cadena

| Situación | Qué hace OpenCode |
|---|---|
| Bloque terminado | Commit, línea en `RESULTADO-TL3.md` y **sigue con el siguiente bloque**. Sin preguntar |
| Fallo técnico (ruff, pytest, excepción) | Corrige y reintenta hasta 3 veces. Si sigue fallando: marca el bloque `bloqueado: <error>` en `RESULTADO-TL3.md`, salta los bloques que dependen de él (§2) y **sigue con el resto** |
| Puerta científica no superada (validez, potencia, coste) | Es un **resultado**: lo registra con su motivo y sigue. Nunca reinterpreta ni prueba "otra versión" |
| Falta el registro del contador (§7) para T7/T8 | Marca `bloqueado: falta registro del operador`, no ejecuta esa prueba y sigue |
| Fin de la cola | T11: cierre, tag y resumen. **No empieza nada que no esté aquí** |

**Prohibido en toda la cola:**
- Modificar el EA, el setfile, `ea_us100_engine.py`, `ea_lab/`, `ai_trader.py` y su configuración, Prop
  Fund, riesgo FTMO, forward, `config/schedule.yaml` y los scripts de tareas programadas.
- Escribir en `data/discovery.db` o `data/lab.db` (solo lectura, en copia). Usar `record-informal`,
  porque lo usa el operador.
- Campañas de Discovery, `confirm`, lectura de OOS-2, barridos o variantes no listadas aquí.
- Borrar o mover archivos (solo copiar), push, tareas programadas, órdenes, `.env`.
- Mirar el rendimiento de cualquier dato fuera del bloque que lo pide.

## 2. Bloques y dependencias

| Bloque | Contenido | Depende de | Suma pruebas |
|---|---|---|---|
| T0 | Commit de la auditoría y las colas | — | No |
| T1 | Manifiesto de datos y cargador con comprobaciones | T0 | No |
| T2 | Copias de futuros con nombre propio | T1 | No |
| T3 | Registro de hipótesis, candados, umbrales y Edge Map TL3 | T1 | No |
| T4 | Informe bruto → neto por componente (función + test) | T3 | No |
| T5 | Contrafactual correcto de `ai_trader` (offline) | T1 | No |
| T6 | Réplica exacta del EA con lista de operaciones | T1 | No (réplica, `counted=0`) |
| T7 | **EA fuera de periodo, US100 Dukascopy 2012-2021** | T1, T3, T6, NQ-B A-1 válido | **1** |
| T8 | **H2 deriva previa al FOMC** | T1, T3, T4 | **1** |
| T9 | Puertas de H1 y H3 (sin rendimiento) | T3 | No |
| T10 | Informe de resultados del ciclo | todos los anteriores que no estén bloqueados | No |
| T11 | Cierre: ruff, pytest completo, `lab doctor`, README/PLAN, tag, Telegram | — | No |

## 3. Infraestructura (T0–T6)

### T0 · Commit de partida
`git add TL3_REPORTS` y `git add -f .orquestador/COLA-TL3.md .orquestador/ENMIENDA-NQ-B.md`.
**No** añadir `reports/discovery/edge_map.md` ni `tl2-edge-map.patch` (no son de esta cola). Commit
`tl3: T0 - auditoria y colas`. Crear `.orquestador/RESULTADO-TL3.md` con una tabla de bloques y su estado.

### T1 · Manifiesto de datos (`src/tradinglab/tl3/data.py`)
1. `build_manifest()` recorre `data/cache/{ea,dukascopy,databento,mt5}` y escribe por archivo: `path`,
   `source`, `instrument_real` (p. ej. `US100.cash`, `Dukascopy USATECHIDXUSD`, `NQ.c.0`),
   `instrument_class` (`cfd`/`future`), paso dominante **por año**, `usable_from` (primer año cuyo paso
   dominante es la granularidad nominal), fracción con ASK, filas y hash.
   Regla fija: todo `data/cache/databento/*` es `future` (raíces: US100→NQ, US500→ES, US30→YM,
   XAUUSD→GC, EURUSD→6E, GBPUSD→6B, USDJPY→6J).
2. `load(path, timeframe, start, end, instrument_class)` lanza error si la granularidad dominante de la
   ventana no coincide o si la clase no coincide.
3. Informe `TL3_REPORTS/data_manifest.md` y `data/tl3/manifest.json`.
4. Tests sintéticos: cargar 2018 de `US100_CASH_M5_NY.parquet` como M5 → error; cargar
   `databento/US100_M1.parquet` como `cfd` → error; Dukascopy `ask_*` vacío → `has_ask = 0`.

### T2 · Copias de futuros
Copiar (no mover) cada `data/cache/databento/<X>_<TF>.parquet` a
`data/tl3/futures/<RAIZ>_c0_<TF>.parquet` y anotar origen y hash en el manifiesto. Los originales no se
tocan. Nota en `RESULTADO-TL3.md`: los rolls de `reports/discovery/futuros-roll.md` están incompletos
(NQ 17 de ~66; GC con meses equivocados) y **no** se usan.

### T3 · Registro de hipótesis (`src/tradinglab/tl3/registry.py`, `gates.py`, `thresholds.yaml`)
1. Base nueva `data/tl3/tl3_research.db` con `hypotheses`, `experiments` y `sample_usage`, con los campos
   de `TL3_REPORTS/TL3_ARCHITECTURE_PROPOSAL.md §2`. Solo inserciones; los cambios de estado son filas
   nuevas.
2. `thresholds.yaml` con: `mde_rule: 2.49`, `cost_gate_ratio: 2.0`, `lcb_z: 1.645`,
   `validity_match_pct: 80`, `validity_corr: 0.7`, `bootstrap: {block: week, n: 10000, seed: 42}`. Su
   hash se guarda en cada experimento. Ningún bloque de esta cola lo modifica tras T3.
3. Candados: potencia (MDE ≤ δ), coste (bruto esperado ≥ 2 × coste) e identidad (`structural_hash`).
4. Alta en el registro (estado tomado de la auditoría, sin recalcular nada):
   - las 9 ideas de Discovery: fix FX → `rejected: gross_lt_cost` (v2, 7.527 ops); Asia USDJPY →
     `rejected: no_gross_edge`; cambio de mes, rebote, Donchian, momentum intradía, NY open GA →
     `inconclusive: no_power_cost_v1`;
   - EA-OOP (T7), H2 (T8), H1 y H3 (T9) con sus prerregistros literales de §4–§5.
5. `TL3_REPORTS/edge_map_tl3.md`: tabla con esas etiquetas y su evidencia (cifras de
   `TL3_DISCOVERY_FAILURE_ANALYSIS.md`). **No** se toca `reports/discovery/edge_map.md`.
6. Tests: un `structural_hash` repetido de una hipótesis rechazada se bloquea; un holdout que se solapa
   con una ventana usada se rechaza; un experimento con otro hash de umbrales queda `invalid`.

### T4 · Informe bruto → neto (`src/tradinglab/tl3/report.py`)
Función que, dada una lista de operaciones con `gross`, `spread`, `commission`, `slippage` y `swap`
(R o bps), produce la escalera bruto → −spread → −comisión → −slippage → −swap → neto con n, media,
IC95 y MDE. Test sintético con costes calculados a mano. **No** se reevalúan campañas antiguas: eso
sumaría pruebas.

### T5 · Contrafactual de `ai_trader` (offline, solo lectura)
1. Lee `ai_trades` de una **copia** de `lab.db` (`mode=ro`). Precios M1 (o M5 si no hay M1) con MT5
   attach-only `copy_rates_range`, con el login verificado antes y después. Ninguna orden.
2. Para cada operación cerrada, en la vela **siguiente** a la entrada, con TP/SL en orden temporal
   (si los dos caen en la misma vela M1: SL primero y anotarlo), mismo cierre forzoso que la IA (12:00 NY
   en scalping), coste = spread de la vela + 0,5 pt/lado:
   - **gemela aleatoria** con la semilla guardada (`shadow_seed`);
   - **regla de tendencia** (fijada ahora): lado = signo de (cierre 15:55 NY − apertura 09:30 NY) de la
     sesión anterior del mismo símbolo;
   - **siempre tomar** el lado del setup, si el setup define lado; si no, Sin datos.
3. `TL3_REPORTS/ai_trader_contrafactual.md`: IA frente a cada benchmark, Δ con IC95 bootstrap
   (10.000, semilla 7) y desglose por lado y símbolo. Veredicto con la regla de
   `TL3_AI_TRADER_AUDIT.md §5`: la IA solo "aporta" si Δ frente a la regla de tendencia ≥ 0,1 R con IC95 > 0
   (con n = 44 casi seguro **Sin datos**; se dice así).
4. No se toca `ai_trader.py`, su base ni sus tareas.

### T6 · Réplica exacta del EA (`counted=0`)
1. Motor `ea_us100_engine.run` con el setfile v3.2 sin cambios sobre `data/cache/ea/US100_CASH_M5_NY.parquet`
   desde 2021-09-14 (solo M5). Es la misma réplica que las anteriores (convención `counted=0` de
   `docs/ea_us100_ftmo1.md`).
2. Guardar `TL3_REPORTS/ea_trades_v32.parquet` con: entrada, salida, lado, R, MAE y MFE en R (calculados
   con las barras entre entrada y salida) y hora de entrada.
3. `TL3_REPORTS/TL3_US100_ADDENDUM.md`: largo/corto por año, MAE/MFE, R por hora de entrada, y la
   comprobación de la hipótesis de `TL3_US100_CASE_STUDY.md §3.3` ("el lado corto pierde en 2023").
   **Solo descriptivo:** prohibido proponer filtros o parámetros a partir de esta tabla.
4. Comprobación: total de operaciones y expectativa iguales a `reports/ea/us100-ftmo1-v2.md` ± la
   diferencia por las barras nuevas; si no cuadra, `bloqueado: réplica no reproduce`.

## 4. Experimentos que suman (T7, T8)

### T7 · EA v3.2 fuera de periodo en US100 Dukascopy (1 prueba)

**Requisito:** NQ-B A-1 válido (Dukascopy ↔ US100.cash 2022: ≥ 80 % emparejadas y correlación ≥ 0,7).
Si A-1 fue "no válida" o no se ejecutó: T7 = `no válida (Sin datos): el procesado Dukascopy no reproduce
al bróker`. No se ejecuta.

| Campo | Prerregistro |
|---|---|
| Hipótesis | La lógica v3.2, sin cambios, tiene ventaja en US100 (CFD Dukascopy) fuera del periodo de diseño |
| Datos | `data/cache/dukascopy/US100_M1.parquet` (BID) → `prepare_nq` (`resample_m5` + `apply_spread` con `us100_spread_profile_ny5m.parquet`) |
| Ventana | Calentamiento desde 2011-10-01; operaciones con entrada **2012-01-03 → 2021-08-31** |
| Parámetros | Setfile v3.2 sin cambios. `k` = ATR14 M5 Dukascopy / US100.cash en 2022-01-03 → 2022-12-30; sin escalar si está en [0,9; 1,1]; si no, regla de E2 |
| Exclusiones (contadas por año) | Festivos, cierres especiales y cierres tempranos NYSE (`discovery/calendars.py`); sesiones con < 95 % de velas M1 en 09:30–15:44 de la sesión o de la anterior, o con < 80 % de 18:00 (día previo) a 09:29 |
| Costes | Spread por franja de 5 min (perfil 2021-2026, anacrónico: se declara), slippage 0,5 pt/lado, comisión 0. Filtro de noticias no modelado (igual que el backtest) |
| Criterio | **n ≥ 300, expectativa ≥ 0,10 R y LCB95 > 0** (bootstrap por bloques de 1 semana, 10.000, semilla 42) |
| Veredicto | "confirma" / "no confirma"; con n < 300, "Sin datos (muestra insuficiente)" |
| Lectura | Confirma → evidencia fuerte contra "ajuste a 2021-2026". No confirma → alta probabilidad de ajuste o de dependencia de régimen. **En ningún caso** se cambia el EA ni el riesgo por este resultado |
| Informe | `TL3_REPORTS/ea_oop_dukascopy.md`: tabla por año, largo/corto, slippage 0/0,5/1/2/3 pt, `slip_eq`, exclusiones |
| Ejecuciones | **Una.** Registrar en `experiments` y `sample_usage` (US100, M5, 2012-2021, `holdout`) |

**Nota previa a T7 (2026-11-25, escrita antes de ejecutar T7; no cambia criterio, lectura ni ejecución).**
Tres trabajos independientes sobre reglas de apertura en NQ (Marx 2026, ORB prerregistrado con prueba
2015-2019 fallida; Krueger 2026, réplica de Zarattini-Aziz en 5 índices CFD con 2015-2017 negativo y
neto ≈ 0; Chuk 2026, banda de ruido con 2014-2019 plano) encuentran el patrón plano o negativo antes
de 2020 y positivo después. Por tanto, "no confirma" en T7 es esperable tanto si el EA está ajustado
como si su ventaja es real pero limitada al régimen posterior a 2020; T7 no separa ambas causas y la
tabla por año **no** se usará para reformular ni para elegir subperiodos. "Confirma" sería evidencia
especialmente fuerte, porque llegaría en el régimen donde las reglas simples fallaron.

### T8 · H2 deriva previa al FOMC (1 prueba)

| Campo | Prerregistro |
|---|---|
| Hipótesis | Los índices de EE. UU. tienen una deriva positiva anormal entre el cierre previo y el comunicado del FOMC (Lucca-Moench 2015; muestra publicada 1994-2011, la nuestra es posterior) |
| Eventos | Reuniones **programadas** de `.orquestador/fomc-fechas.md` desde 2011-09-19 hasta 2026-11-25 (se excluye la futura 2026-12-09). Sin reuniones no programadas |
| Instrumentos | US500, US100, US30 (Dukascopy BID, CFD). US30 desde 2013-09-30 |
| Entrada | Largo a las **15:55 NY** de la sesión NYSE anterior al anuncio (ASK = BID + spread de la franja) |
| Salida | **12:25 NY** para eventos anteriores a 2016-01-01 (en 2011-2012 hubo comunicados a las 12:30 y la hora 2010-2015 no está verificada); **13:55 NY** desde 2016 (14:00 verificada). Regla fija, sin buscar horas |
| Observación | Una por evento: media igual ponderada de los índices disponibles, en bps (log-retorno × 1e4) |
| Costes | Spread por franja de 5 min NY: perfil de cada índice construido igual que el de US100 (mediana por franja) desde `data/cache/ea/US500_CASH_M5_NY.parquet`, `US30_CASH_M5_NY.parquet` y `us100_spread_profile_ny5m.parquet`. Slippage 0,5 pt/lado. Swap de **una noche**: ~~débito de `swap.yaml` CFD-001; los créditos cuentan 0~~ **enmienda 2026-11-25 (abajo):** interés largo de `swap.yaml` CFD-006 (`swap_mode` 5: −7,33 % anual sobre el precio de entrada) = 7,33 % / 365 por noche en cada índice, ×3 si la noche cruza el rollover del día triple (`swap_rollover3days` = 5, 17:00 NY) |
| Placebo | Mismo reloj (15:55 del día previo → hora de salida de la época) en todos los demás días NYSE, excluyendo t−1, t y t+1 de cada FOMC, festivos y cierres tempranos |
| Potencia (antes de mirar los eventos) | σ = desviación del placebo; MDE = 2,49 × σ / √n_eventos. **δ = 30 bps.** Si MDE > 30 bps: `rejected: no_power`, no se calcula el retorno de los eventos |
| Criterio | (a) diferencia bruta FOMC − placebo con t de Welch unilateral ≥ 1,645, **y** (b) LCB95 de la media **neta** de los eventos > 0 (bootstrap de eventos, 10.000, semilla 42) |
| Cobertura | Evento × índice válido si hay barras M1 a ±2 min de la entrada y de la salida; si no, ese índice se excluye para ese evento (contado) |
| Veredicto | "confirma" / "no confirma"; sin reinterpretación |
| Informe | `TL3_REPORTS/h2_pre_fomc.md`: n, σ, MDE, escalera bruto → neto (T4), tabla por año y por época (≤2015 / ≥2016), placebo |
| Ejecuciones | **Una.** Registrar en `experiments` y `sample_usage` |

**Enmienda de costes T8 (2026-11-25, aprobada por el operador antes de ejecutar T8 y sin ver ningún
evento).** Motivo: los créditos de CFD-001 en US100/US500 son una sola medición y probablemente un ajuste
por dividendos; contarlos como 0 infravalora la financiación real de un largo en CFD. CFD-006 es la única
medición de interés plausible (~2,0 bps/noche). El cambio solo encarece el neto, es decir, hace el
criterio (b) más exigente; no cambia eventos, horas, placebo, δ ni el criterio (a). Se refleja en la fila
de swap de la escalera bruto → neto del informe.

**Decisión del operador (2026-11-25, antes de ejecutar T8):** tras revisar `TL3_REPORTS/literatura_T8_H1.md`,
se mantiene T8 sin cambios (δ = 30 bps, mismas ventanas y criterio). Lectura fijada ahora, antes de ver
eventos: "no confirma" descarta un efecto del tamaño de 1994-2011 (≥ 30 bps), pero **no** uno de ~20 bps
como el de la literatura posterior a 2011 (potencia estimada ~55 %), y no se reformula sobre esta
muestra; "confirma" es una replicación independiente 2011-2026 en CFD, neta de costes.

## 5. Puertas sin rendimiento (T9)

### H1 · Deriva nocturna (no se ejecuta como prueba)
- Bruto esperado declarado ahora: **3,5 bps/noche** (literatura).
- Coste por noche, **sin mirar retornos**: spread 15:55 + 09:35 por franja + slippage + swap de una noche,
  para CFD-001 y CFD-006 con `swap.yaml`.
- **Hecho conocido:** CFD-001 da swap largo **positivo** en US100 (+1076,28 pt) y US500 (+32,83 pt) con
  una sola medición (2026-11-23). Un crédito en el largo de un índice es probablemente un ajuste por
  dividendos o una rareza del bróker. Swap FTMO: **Sin datos fiables**.
- Candado de coste: bruto ≥ 2 × coste. Si no se cumple en CFD-006 → `rejected: cost_gate`. En CFD-001 →
  `blocked: swap sin datos fiables`. **No** se calcula ningún retorno nocturno.
- Anotar como tarea de datos para el operador: medir `swap_long/short` durante ≥ 20 sesiones antes de
  cualquier hipótesis que duerma posiciones.

### H3 · Impulso de apertura con expansión de rango (solo conteo)
- Prerregistro de `TL3_NEW_RESEARCH_METHODOLOGY.md §3 H3` (OR de 30 min, rango OR ≥ p70 de 60 días,
  holdout 2011-09 → 2014-12, desarrollo 2015-2020).
- Contar **sin PnL**: sesiones válidas (mismas reglas de cobertura que T7) con señal en el holdout,
  por índice y en **días distintos**. MDE = 2,49 / √(días distintos con señal). **δ = 0,12 R.**
- Si MDE > 0,12 → `rejected: no_power`. Si pasa → `approved_gate: pendiente de registro del operador`.
  **No se ejecuta en esta cola en ningún caso.**

## 6. Resultados y cierre (T10, T11)

### T10 · `TL3_REPORTS/TL3_RESULTS_CICLO1.md`
Por bloque: estado, cifra principal y veredicto literal. Tabla de hipótesis con su estado en el
registro. Recomendaciones **para el operador** (no se aplica ninguna): EA (mantener/reetiquetar según
T7), `ai_trader` (según T5), siguiente lista de hipótesis ordenada por (bruto esperado − coste) / MDE.

### T11 · Cierre
`ruff check`, `pytest` completo, `lab doctor`, `lab propfund verify` (debe dar los mismos grupos sin
cambios: prueba de que no se tocó producción). README (§1 y §8) y PLAN con el estado TL3. Commit
`tl3: ciclo 1`, tag `tl3-ciclo1`. Resumen a Telegram (si no está configurado, `lab alerts send`) con el
formato **Hecho / 1..N / Aviso / Siguiente**. **Fin.**

## 7. Registro previo del contador (lo hace el operador antes de lanzar)

```powershell
.\.venv\Scripts\lab.exe learning record-informal --n 1 --reason "TL3-T7: EA v3.2 fuera de periodo US100 Dukascopy 2012-2021, prerregistrado en COLA-TL3" --approved-by-operator
```

```powershell
.\.venv\Scripts\lab.exe learning record-informal --n 1 --reason "TL3-T8: H2 deriva pre-FOMC indices 2011-2026, prerregistrado en COLA-TL3" --approved-by-operator
```

T0 comprueba que existen esas dos filas en `informal_trials` (por el texto `TL3-T7` y `TL3-T8`). Si falta
alguna, el bloque correspondiente queda `bloqueado: falta registro del operador` y la cola sigue.
