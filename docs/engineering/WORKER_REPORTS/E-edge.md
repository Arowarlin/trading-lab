# E-edge · Discovery and Edge Research

**ENG-E1 · SHA `adc0eec` · 2026-11-26.** Trabajador E, solo lectura. Lo escribió un subagente de Claude.

- **Árbol leído:** `HEAD` = `19a68d6`. Entre `adc0eec` y `HEAD` solo cambian ficheros de
  `docs/engineering/` (`git diff --stat adc0eec..HEAD`). El código y los informes auditados son los
  de `adc0eec`.
- **Qué no se hizo:** no se ejecutó ninguna campaña, `research*`, `discovery run` ni barrido. No se
  abrieron `discovery.db` ni `lab.db`, no se calculó rendimiento sobre datos reales y no se leyó el
  OOS-2.
- **Única ejecución:** un script sintético, sin datos de mercado, en
  `/tmp/claude-0/-home-user-trading-lab/89310f7f-0a4e-5602-b5a9-56cac624406b/scratchpad/E/sess.py`
  (ver §2.2).

**Etiquetas:**
- **[HECHO: doc]**: cita literal o cifra de un documento del repo.
- **[REPORTADO]**: un resultado que otra cola ya informó; aquí no se reproduce.
- **[CÓDIGO]**: leído en el código, a veces con una prueba sintética.
- **[ARIT]**: aritmética mía sobre cifras citadas.
- **[HIPÓTESIS]**: propuesta o inferencia mía, sin verificar.

Cuando un dato falta, se escribe **Sin datos**.

---

## 1. Inventario de lo ya probado (no repetir)

Columna «Pruebas»: lo que esa línea suma al contador (`count_tests`, DSR), según el documento citado.
Los valores **Sin datos** no constan por separado. La evolución del contador consta así:
1.676 → 1.703 (C1) → 1.730 (N2 XAU) → 1.757 → 1.775 (R9b) → 1.894 → 1.895 (NQ-B) → 1.897 (T7+T8) →
1.926 (fase C de NASDAQ_EDGE: 7 + 22) → 12.694 (EDGE-1). Fuentes: `RESULTADO-*.md`, `ESTADO.md` y
`TL3_RESULTS_CICLO1.md`.

### 1.1 Antes de Discovery TL2

| Hipótesis / plantilla | Mercado | TF | Periodo | Pruebas | Veredicto | Motivo | Documento |
|---|---|---|---|---:|---|---|---|
| Barridos de indicadores (LONDON_PULLBACK, SESSION_TREND, TREND_INTRADAY, ORB_NY, TOKYO_BREAKOUT, FIX_FLOW ×48, PULLBACK, SESSION_HOLD…) | EURUSD, GBPUSD, USDJPY, US100, XAUUSD | Sin datos | 2026-11-09 → 11 | ~450 | rechazada | Todas `failed`: «DSR 0 % < 90 %; WF fallido; régimen no aprobado» | `TL3_REPORTS/TL3_DISCOVERY_FAILURE_ANALYSIS.md` §1.1 |
| Campañas A/B: TSMOM, ST_REVERSAL, VOL_BREAKOUT, CALENDAR | 16 activos | Sin datos | 2026-11-12 | 460 celdas | rechazada | A «passed» en descubrimiento; B contaminada; 0/23 confirmadas | ídem |
| Optuna sobre acciones (SPY, QQQ, MSFT) | acciones | Sin datos | Sin datos | 93 + 4 lecturas de holdout | fuera de alcance | Suman al contador de CFD | `TL3_FORENSIC_AUDIT.md` G-7 |

### 1.2 Discovery TL2 (16 campañas, 2026-11-20 → 25)

| Hipótesis / plantilla | Mercado | TF | Periodo IS | Pruebas | Veredicto | Motivo (cifras IS reportadas) | Documento |
|---|---|---|---|---:|---|---|---|
| `ny_open_vol_filter` (GA) | US100 (bróker) | M5 | 2021-10 → 2024-06 | Sin datos (260 filas) | inconclusive (H-2026-007) / sobreajustada | Neto mediano −0,0025 R; 2 finalistas caen en WF, PBO, régimen y bootstrap. Contaminada por el EA | `TL3_DISCOVERY_FAILURE_ANALYSIS.md` §1.2; `reports/discovery/edge_map.md` |
| `intraday_momentum_close` v1 | US100 | M5 | ídem | Sin datos (144 filas) | inválida | Espejo del umbral sin signo | ídem |
| `intraday_momentum_close_v2` | US100 | M5 | ídem | Sin datos (32 filas) | inconclusive (H-2026-006) | Bruto mediano −0,011 R; neto −0,078 R | ídem |
| `asia_range_reversion` (c1) | USDJPY | H1 | 2010-01 → 2024-06 | 27 | rechazada (H-2026-002, `no_gross_edge`) | Bruto −0,053 R; 1.321 operaciones IS; MDE 0,069 | ídem; `reports/discovery/c1-asia-usdjpy-h1-long.md` |
| `donchian_vol_h4` (n2) | XAUUSD | H4 | 2005-01 → 2024-06 | 27 | inconclusive (H-2026-005) | 23/27 con bruto > 0; mejor OOS-1 +0,39 R con 16-19 operaciones (EE ≈ 0,3 R) | `reports/discovery/n2-donchian-xauusd-h4.md` |
| `donchian_vol_h4` (n2) | USDJPY | H4 | Sin datos | 27 | el coste se come el bruto | Bruto +0,019 R; neto −0,003 R | `n2-donchian-usdjpy-h4.md` |
| `fix_reversal` (q2 ×3) | USDJPY, EURUSD, GBPUSD | H1 | Sin datos | 6 + 6 + 6 | rechazada (H-2026-001, `gross_lt_cost`) | Bruto +0,013 / +0,023 R frente a un coste de 0,033 / 0,036 R | `TL3_DISCOVERY_FAILURE_ANALYSIS.md` §1.2 |
| `fix_reversal` cesta, costes v2 | EURUSD + GBPUSD | H1 | Sin datos | 9 | rechazada (**familia cerrada**) | 7.527 operaciones; bruto +0,019 R < coste 0,032 R | ídem §5 |
| `turn_of_month` (r9, r9b) | US100, US500 | D1 | Sin datos | 9 × 4 = 36, más 18 informales (ES/NQ) | inconclusive (H-2026-003) | 56-109 operaciones; MDE 0,24-0,33 R | ídem §1.4 |
| `d1_extension_reversion` / rebote (q1) | US100, US500 | D1 | Sin datos | 27 + 27 | inconclusive (H-2026-004) | 16-27 operaciones en 10 años; MDE 0,48-0,62 | ídem |

### 1.3 NASDAQ_EDGE (NQ / US100)

| Hipótesis / plantilla | Mercado | TF | Periodo | Pruebas | Veredicto | Motivo | Documento |
|---|---|---|---|---:|---|---|---|
| Fase B: 7 descriptivas (rango por franja, rupturas del OR, toques de VWAP, recorridos, barridos, días y régimen, noticias) | NQ | M1/M5 | DEV 2010-2018 | 7 (`informal_trials` id 6) | descriptiva | Ninguna es una estrategia | `NASDAQ_EDGE_INSTITUTIONAL/README.md`; `01_RESEARCH/Nasdaq_Intraday_Research.md` §5 |
| Fase C: 22 variantes A-E (ruptura del OR en la apertura de NY, barridos PD/ON, VWAP de reversión y de continuación, FVG, subasta/perfil con volumen CME), ventana 9:35-11:30 | NQ (DEV), Dukascopy US100 (DEV y OOS-1 2022-23) | M5 | DEV 2010-2018 | 22 (id 7) | rechazada; **contaminada por el EA** | Bruto ≈ 0 (−0,12 a +0,06 R); neto en DEV de −0,14 a −0,51 R; PF neto de 0,38 a 0,96 | `03_BACKTEST/Strategy_Comparison.md` |
| NQF-A / NQF-B / NQF-C | MNQ | M5 | forward desde el 2026-11-30 | Sin datos (Bonferroni /3 en el prerregistro) | **en forward**, no tocar | Evaluación única a n = 200 por variante | `04_FORWARD/prerregistro.md` |

### 1.4 TL3 (ciclo 1)

| Hipótesis | Mercado | TF | Periodo | Pruebas | Veredicto | Motivo | Documento |
|---|---|---|---|---:|---|---|---|
| T7: EA fuera de periodo (H-2026-008) | US100 Dukascopy | M5 | 2013-14 y 2018-21 (efectivos) | 1 | rechazada (`holdout_fail`) | 374 operaciones; −0,0296 R; LCB95 −0,1753 | `TL3_RESULTS_CICLO1.md` |
| E2: EA fuera de instrumento | US500, US30 | M5 | 2018 → 2026 | Sin datos | «no transfiere» | US500 −0,0229 R; US30 +0,069 R con LCB < 0 | `.orquestador/RESULTADO-E2.md` |
| NQ-B: EA en NQ (A-1/A-2 = paridad) | NQ | M1/M5 | 2010-2018 | 1 (contador 1.895) | Sin datos | Sin datos | `.orquestador/RESULTADO-NQ-B.md` |
| T8 / H2: deriva antes del FOMC (H-2026-009c) | US100, US500, US30 | M5 | 2011-2026, 117 eventos | 1 | rechazada (no confirma) | t bruto 1,909; neto 8,04 bps; LCB95 −0,60 | `TL3_RESULTS_CICLO1.md`; `literatura_T8_H1.md` |
| H1: deriva nocturna (H-2026-010) | cesta de índices CFD | M5 | — | 0 (no se ejecutó) | `cost_gate` | Coste de 3,1-3,9 bps/noche (swap 2,0-2,8) frente a un bruto declarado de 3,5 | `TL3_REPORTS/gates_tl3.md` |
| H3: impulso del OR con expansión de rango (H-2026-011) | US100 | M5 | holdout 2011-09 → 2014-12 | 0 (solo conteo) | `no_power` | 207 días con señal; MDE 0,1731 > δ 0,12 | ídem |
| T5 / H-2026-012 / H-2026-013 (`ai_trader` y su regla gemela) | US100 | H1 | — | — | excluidas de este informe | Derivadas de `ai_trader` | `ai_trader_power_plan.md`; `verificacion_h-2026-013.md` |
| HIPÓTESIS 4-8 (pre-FOMC, pre-festivo, fix 16:00, rebote, oro en Asia) | varios | H1/D1 | — | 0 (solo papel) | sin probar | Solo documento. H4 ≈ T8 (ya hecha); H6 ≈ familia fix (cerrada); H7 ≈ q1 (sin potencia). **H5 (pre-festivo) y H8 (oro en Asia) siguen sin probar** | `.orquestador/HIPOTESIS-4-10.md` |
| Specs P4: fix-londres, tom-indices, tsmom-cesta, rebote-indices | varios | H1/D1 | — | 0 (solo preflight y feasibility) | sin potencia | `potencia_ok = No` en las 4: MDE del holdout 0,092 / 0,46 / 0,88 / 1,02 | `.orquestador/RESULTADO-P4.md` |

### 1.5 EDGE-1 (28 campañas, GA perfil `small`, 440 evaluaciones cada una)

IS 2012-2019 y OOS-1 2020-2022. Las pruebas registradas son **12.320** (28 × 440). El contador pasó
de 1.926 a 12.694, es decir **+10.768** [HECHO: `ESTADO.md` §8].

> **Aviso:** 12.320 − 10.768 = **1.552 pruebas** registradas que no aparecen en el contador [ARIT]. La
> causa es **Sin datos**, porque no se abrió `discovery.db`. Hay que comprobar el `n_total` y el
> `approved_at` de las campañas `edge1-*` con OpenCode.

| Plantilla | Activo · TF (campañas) | Finalistas | Veredicto | Motivo |
|---|---|---:|---|---|
| `trend_pullback_mtf` | USDJPY H4/H1/M30/M15, EURUSD H4/H1, GBPUSD H4/H1, XAUUSD H4/H1 (10) | 14 (edge1-01, 07, 11, 18, 22) | rechazada en X3 | Puerta 2: WF < 0,3 y/o PBO > 0,30; WF-TF 0/22 |
| `vol_squeeze_breakout` | USDJPY H4/H1/M30/M15, EURUSD H4/H1, GBPUSD H4/H1, XAUUSD H4 (9) | 6 (edge1-02, 05, 08, 12) | rechazada en X3 | ídem |
| `asia_range_reversion` | EURUSD H1, GBPUSD H1, USDJPY M30/M15, XAUUSD H1 (5) | 1 (edge1-21) | rechazada en X3 | WF −0,212; WF-TF con pliegues positivos 0,49 |
| `donchian_vol_h4` | EURUSD H4, GBPUSD H4 (2) | 1 (edge1-06) | rechazada en X3 | PBO 0,578; WF-TF con stitched −0,087 |
| `london_breakout` | EURUSD H1 (1) | 0 | sin finalistas | 223 evaluadas, 3 efectivas |
| `fix_reversal` | XAUUSD H1 (1) | — | bloqueada | Feasibility 12/40 (30 % < 50 %) |

Documentos: `TL3_REPORTS/edge1_plan.md`, `edge1_progreso.md`, `edge1_finalistas.md`, `robust1_*.md`
y `wf_tf_resultados.md`. X4 = sin pasada 2; X5 = 0; X6 = 0. Activos bloqueados en X0: US100 (swap),
US30 (spread Sin datos) y US500 (regla de dos cuentas).

### 1.6 EDGE-2 (índices; plan Y1 de 18 campañas, n_total 7.920)

| Plantilla | Mercado · TF | Estado | Documento |
|---|---|---|---|
| `donchian_vol_h4`, `trend_pullback_mtf`, `vol_squeeze_breakout` | US100 H4 | **ejecutadas** (edge2-01..03): 0, 5 y 1 finalistas | `TL3_REPORTS/edge2_progreso.md`; `edge2_pass1.log` (14:04-14:18Z) |
| `st_reversal_idx` | US100 H1 | **ejecutada** (edge2-04): 0 finalistas | ídem |
| Las 14 restantes (US100 H1/M30/M15, US500 H4/H1) | — | `draft` | `edge2_plan.md` |

> **Discrepancia [HECHO]:** `ESTADO.md` (13:20) dice que «Y2 no se lanza en esta sesión», pero el
> commit `554497c` («edge2: Y2 - campanas 1-4») y `edge2_pass1.log` registran 4 campañas `done`.
> Y3 (robustez) y el contador posterior a Y2 son **Sin datos**. `ESTADO.md` está desfasado.

### 1.7 Ideas agotadas o contaminadas (resumen)

- **Cerradas con veredicto firme:**
  - fix FX: 4 campañas + 48 barridos + intento en EDGE-1 [HECHO: TL3 §5];
  - las 22 variantes de la apertura de NY en NQ [HECHO: Strategy_Comparison].
- **Sin potencia con la frecuencia actual:**
  - cambio de mes y rebote en D1 por instrumento;
  - H3 (OR + expansión);
  - las cuatro specs de P4.
- **Contaminado como muestra de descubrimiento** [HECHO: `TL3_STATISTICAL_VALIDATION_AUDIT.md` §2.A]:
  US100 M5 2021-2026. A eso se suman NQ M1 2010-2018 y Dukascopy US100 2013-2021 en todo lo que se
  parezca a la apertura de NY, porque el EA se probó en esos tramos [HECHO: NQ-B, T7;
  `Nasdaq_Intraday_Research.md` §2].
- **Hipótesis reutilizada sobre los mismos datos** [HECHO + ARIT]: EDGE-1 evitó repetir la terna
  plantilla×activo×TF, pero no la hipótesis sobre los mismos años. Dos ejemplos:
  - `asia_range_reversion` USDJPY (c1, H1, IS 2010-2024) se volvió a probar en M30/M15 con 2012-2022;
  - `donchian_vol_h4` (n2: XAUUSD y USDJPY, IS hasta 2024-06) se pasó a EURUSD/GBPUSD.

  Esto es solapamiento de calendario, no un juicio sobre resultados.

---

## 2. Qué puede descubrir el motor (`engine.py`, `edge_map.py` y lo que condicionan)

### 2.1 Espacio de búsqueda [CÓDIGO]

**Qué entra:**
- **Operandos del DSL** (`dsl.py:37-56`): precio OHLC, `range` y `body`; niveles (sesión previa, día
  previo, OR y Donchian); indicadores, en `blocks.py` (SMA, EMA, RSI, ATR, z-score, MACD, ADX,
  Bollinger, estocástico, CCI, Keltner, `vwap_distance`, vol realizada, `atr_pct_rank`, compresión,
  swings, BOS/CHoCH, velas); regímenes (`trending`, `ranging`, `vol_high`, `vol_low`); HTF.
- **Operadores temporales:** `held_for`, `within_bars`, `time_between`, `weekday_in` y `month_turn`
  (solo largo).

**Qué no hay** (estructuralmente imposible con el DSL actual):
1. **Order flow:** ni volumen agresor, ni delta, ni desequilibrio bid/ask, ni L1/L2, ni tamaño de cola.
   - El único consumidor de volumen es `vwap_session`, que usa `volume` o `tickvol` y, si faltan,
     **volumen unitario** (`indicators_ext.py:212-219`).
   - Dukascopy no trae volumen útil y el ASK solo está en EURUSD (10,9 %) [HECHO: `data_manifest.md`;
     `NASDAQ_EDGE .../Data_Sources.md`].
   - NQ M1 trae volumen CME real, pero solo para 2010-2018 y solo en OHLCV (sin lado agresor).
2. **Eventos programados** (FOMC, CPI, NFP, festivos): no hay nodo de calendario de eventos.
   `HIPOTESIS-4-10.md` §8 lo lista como «por construir» (`fomc_pre`, `pre_holiday`). T8 se hizo
   fuera del DSL.
3. **Señales entre activos** (una serie condiciona a otra): no hay operando que lea otro símbolo.
   `basket.py` aplica la misma regla a varios símbolos, pero no los cruza. **[HIPÓTESIS]** Lo deduzco de
   los operandos de `dsl.py`; `basket.py` no lo revisé a fondo.
4. **Niveles de Globex:** no existe ONH/ONL propio de futuros. `prev_session_*` depende de la sesión
   declarada.
5. **Carry y swap como señal:** el swap solo entra como coste (`engine.yaml: swap_credit: false`).
6. **Volatilidad implícita, VIX y estructura temporal de futuros:** Sin datos en el manifiesto.
7. **Tamaño de posición y volatility targeting:** todo se mide en **R por operación**, con stop en
   ATR. Una ventaja que esté en el tamaño (por ejemplo, exposición inversa a la varianza) queda
   neutralizada por la normalización en R. **[HIPÓTESIS]**: la idea es mía y es consecuencia directa
   de la métrica.

### 2.2 GA: qué explora de verdad [CÓDIGO]

- **Presupuesto:** perfil `small` = población 40 × 10 generaciones, es decir **440 evaluaciones por
  campaña** (`engine.yaml:33-35`). Ese es el `n_total` de cada campaña EDGE.
- **La mutación cambia la hipótesis:**
  - `mutate_block` (`genetic.py:228-259`) sustituye un indicador por **cualquier otro** del mismo tipo
    de salida;
  - `mutate_logic` añade o quita condiciones y cambia AND/OR (`genetic.py:340-371`).

  La «plantilla» es solo la semilla: una campaña `trend_pullback_mtf` puede acabar con finalistas que
  ya no son una reanudación tras un pullback. La hipótesis económica de la plantilla **no limita** lo
  que se selecciona.
- **`mutate_session` solo funciona dentro de 09:30-15:00** (`genetic.py:416-433`). Lo comprobé con
  un script sintético: 200 semillas por plantilla, sin datos de mercado (`scratchpad/E/sess.py`).

  | Plantilla | Sesión | Mutaciones válidas |
  |---|---|---:|
  | `asia_range_reversion` | 18:00-03:00 | 0/200 |
  | `london_breakout` | 02:00-11:00 | 0/200 |
  | `vol_squeeze_breakout` | 00:00-23:59 | 0/200 |
  | `trend_pullback_mtf` | 00:00-23:59 | 0/200 |
  | `donchian_vol_h4` | 00:00-23:59 | 0/200 |
  | `st_reversal_idx` | 09:35-15:55 | 0/200 |
  | `ny_open_vol_filter` | 09:35-11:30 | 147/200 |

  En EDGE-1 y EDGE-2, el GA **nunca** cambió el horario. En FX por sesiones, la hora es la de la
  plantilla y no se explora. Además, el límite está escrito pensando en NY aunque la sesión de FX se
  evalúa en `Europe/London` o `Asia/Tokyo` (`engine.yaml: session_tz`).
- **Salidas:** stop de 1-5 ATR, RR de 1-4, `time_exit` de 60-480 min, BE y trailing
  (`genetic.py:374-413`). En H4, 480 min son 2 velas.
- **Las plantillas de 24 h mantienen varios días sin quererlo.** `flat_at` 23:55/23:59 **nunca**
  dispara en M15-H4, así que en EDGE-1 esas estrategias son de varios días y pagan swap
  [HECHO: `COLA-MOTOR-FLAT.md` §1]. Una hipótesis de «tendencia intradía» frente a «tendencia de
  varios días» **no está separada** en lo que se probó.
- **Fallos del motor que sesgan lo que se ve** [HECHO: `WORKER_REPORTS/A-engine.md`]:
  - A-02: el stop no se evalúa mientras la posición «duerme»; sesgo optimista.
  - A-03: la última vela del día civil nunca abre operación (H4 21:00 NY, H1 23:00).
  - A-01: en D1/H4, `weekday` se evalúa sobre la etiqueta; se pierde la sesión del lunes (o la del
    viernes en Tokio).

### 2.3 Puertas de coste y de factibilidad [CÓDIGO]

`fitness.evaluate` (`fitness.py:248-273`) declara infactible una estrategia que tenga cualquiera de
estas violaciones:
- `cost_r` (mediana de `r_cost` por operación) > `cost_r_max` = **0,10**;
- operaciones IS < `min_trades_is[TF]` (H4: 25, H1: 40, M30: 50, M15: 60, D1: 15), o algún pliegue
  por debajo de `min_trades_fold`;
- concentración > 0,20;
- duración media > `max_holding_bars`.

Consecuencias:
- **Stops cortos.** Con `cost_r` ≤ 0,10, el stop tiene que valer al menos 10 veces el coste de ida y
  vuelta. En NQ, el escenario base de la fase C cobra 0,23 R con un stop mediano de 5,5 pt (A_OR15),
  es decir un coste de unos 1,27 pt [HECHO + ARIT]. Para pasar la puerta, el stop tendría que ser de
  ≥ 12,7 pt [ARIT]. La **microestructura de stop corto queda fuera por diseño**: es correcto como
  filtro económico, pero impide estudiarla.
- **Baja frecuencia.** Los mínimos de operaciones no se derivan de la potencia [HECHO:
  `TL3_STATISTICAL_VALIDATION_AUDIT.md`]. Una hipótesis de eventos (8-30 al año) o una D1 por
  instrumento se vuelve infactible, o factible pero sin potencia (§1.2).
- **La puerta mira solo la mediana.** En `tsmom-cesta`, la mediana de `cost_r` es 0,053, pero el p90
  es 0,32 y el máximo 1,13 [HECHO: `RESULTADO-P4.md`]. La cola de costes no filtra.

### 2.4 Fitness y selección: sesgos [CÓDIGO]

- **Objetivos del NSGA-II** (`fitness.py:275-281`): mediana de la expectativa por pliegue,
  estabilidad, peor DD, complejidad y caída por coste.
  - Ninguno penaliza el **error estándar**: con σ ≈ 1 R y cientos de operaciones, ordenar por
    expectativa IS es ordenar ruido [HECHO: `TL3_DISCOVERY_FAILURE_ANALYSIS.md` §2].
  - El frente de rango 0 incluye estrategias que solo son «buenas» en complejidad o DD
    [HECHO: `D-stats.md` D-02].
- **OOS-1 se usa para seleccionar, no para confirmar.** `_select_finalists` (`engine.py:551-599`)
  ordena los candidatos de rango 0 por **expectativa OOS-1** y se queda con los K mejores.
  `decisions.oos1_check` no exige un n mínimo:
  - los cinco finalistas de `edge1-07` pasaron con **1 operación en OOS-1** (MDE 2,49 R)
    [HECHO: `edge1_finalistas.json`];
  - por eso el OOS-1 no confirma nada, y el único juez limpio es el OOS-2.
- **PBO y WF son de la campaña, no de la estrategia.**
  - `_pbo_wf` usa la matriz del frente IS (`robustness.py:383-453`; `databank.frontier`). Todos los
    finalistas de una campaña reciben el mismo PBO y el mismo WF: lo confirman las tablas, por
    ejemplo 0,789 × 5 en `edge1-07`.
  - El WF mide dentro de la muestra de selección [HECHO: `D-stats.md` D-01].
  - El PBO sobre el frente no es informativo en ninguna de las dos direcciones [HECHO: `D-stats.md`
    D-02].
- **`_niche` y `effective_trials`** alinean series de «días con operación» con
  `pd.concat(..., sort=False).fillna(0)` (`engine.py:361-380`; `fitness.py:366-394`). Es el mismo
  patrón que ROBUST-1 corrigió en el PBO (`robust1_pbo.md`), pero aquí sigue sin calendario hábil
  [CÓDIGO]. El impacto en `n_effective` es **Sin datos**; ver también `D-stats.md` D-07.

### 2.5 `edge_map.py`: cómo etiqueta [CÓDIGO]

- **Bruto y neto positivos acaban como «sin edge bruto».** En `_state_from_campaign`
  (`edge_map.py:437-446`), cuando la mediana bruta y la neta son **ambas > 0**, la rama final
  (`else`) asigna **«sin edge bruto»**. Casos visibles en `reports/discovery/edge_map.md`:

  | Hipótesis | Bruto mediano | Neto mediano | Etiqueta actual |
  |---|---:|---:|---|
  | `turn_of_month` US100 D1 | +0,060 | +0,021 | «sin edge bruto» |
  | `d1_extension_reversion` US100 D1 | +0,150 | +0,136 | «sin edge bruto» |
  | `donchian_vol_h4` XAUUSD | +0,042 | +0,014 | «sin edge bruto» |

  La etiqueta correcta sería del tipo «neto > 0 sin potencia o sin validar». Hoy el mapa **oculta**
  las hipótesis con señal sin potencia, justo las que habría que reformular como cesta.
- **Las medianas en modo GA salen del frente de rango 1**, que es un subconjunto ya seleccionado: el
  bruto y el neto «medianos» tienen sesgo al alza.
- **«Sobreajustada»** se asigna si el PBO > 0,5 **o el WF es False**. Con el WF «no informativo»
  por baja frecuencia (§3), las hipótesis de baja frecuencia caen ahí por construcción.
- **Sin columna de potencia.** El mapa no informa del MDE ni de δ. La puerta de potencia existe
  (`power.py`), pero las specs no declaran δ [HECHO: TL3 G-6].

---

## 3. Diagnóstico: ¿por qué EDGE-1 dio 0 robustas?

### 3.1 Cifras citadas

| Medida | Valor | Documento |
|---|---|---|
| Evaluaciones / efectivas | 11.539 evaluadas en 27 campañas; 2.091 efectivas (30-161 por campaña) | `edge1_progreso.md` [ARIT: suma de las columnas] |
| Campañas con finalista | 11 de 28; 22 finalistas | ídem |
| Operaciones IS por finalista (8 años) | **47-460**, es decir 6-58 al año | `edge1_finalistas.json` [ARIT] |
| Operaciones OOS-1 por finalista (3 años) | **1-170**; MDE OOS-1 (σ = 1 R) **0,19-2,49 R** | ídem |
| Expectativa OOS-1 de los finalistas | 0,010-0,605 R, **por debajo de su MDE en los 22** (el más cercano: 5566, 0,183 frente a 0,191) | ídem [ARIT: comparación] |
| WF 60/20, operaciones por ventana de test | mediana 0-9; **14/22 «no informativo»** | `robust1_wf.md` |
| WF-TF (ventanas por TF), operaciones por ventana | mediana 0-22; **0/22 pasan** | `wf_tf_resultados.md` |
| WF-TF stitched < 0 | **10/22 finalistas** (6 campañas: edge1-02, 05, 06, 11, 12, 22) | ídem [ARIT: conteo] |
| WF-TF stitched > 0 pero falla | 12/22 (estabilidad 0,25; pliegues + 0,23-0,49; eficiencia 0,071) | ídem |
| PBO (matriz diaria corregida) | 0,023-0,957; ≤ 0,30 en 5 de 11 campañas (edge1-05, 11, 12, 21, 22) | `edge1_finalistas.md` (repetición) |
| Puerta 3 (spread p75, slippage +2) | la pasan 21/22 | ídem |

### 3.2 Lectura: «no hay ventaja» frente a «la herramienta no puede verla»

1. **La herramienta no puede ver ventajas de 0,05-0,10 R a esta frecuencia** [ARIT + HECHO].
   - Para detectar 0,1 R hacen falta ≥ 619 operaciones fuera de muestra (§4.0).
   - El mejor finalista tuvo 170 en OOS-1, y 21 de 22 tuvieron ≤ 131.
   - Ninguna expectativa OOS-1 supera su MDE. **Ningún OOS-1 de EDGE-1 distingue ventaja de ruido**,
     ni a favor ni en contra.
   - Un efecto de ≤ 0,1 R en H4/H1 FX **no queda descartado**.
2. **Las puertas no eran ni sensibles ni específicas.**
   - WF y PBO son de la campaña y se calculan sobre el frente IS (§2.4). El WF de 20 días con 0-2
     operaciones da una eficiencia de 0,000 por construcción (14/22).
   - El PBO ≤ 0,30 lo aprueba el ruido el 97,5 % de las veces si el frente es mixto, y tiene una
     potencia del 3 % si es top-k [HECHO: `D-stats.md` D-02].
   - Que las 4 puertas fallaran **no prueba** que no haya ventaja. Que alguna hubiera pasado tampoco
     la habría probado.
3. **Hay alguna evidencia negativa con algo de potencia** [HECHO + HIPÓTESIS].
   - `edge1-12` (USDJPY H1 `vol_squeeze_breakout`) tiene 290-447 operaciones IS, 111-170 en OOS-1 y
     mediana de 16 operaciones por ventana WF-TF.
   - Su WF-TF da eficiencia −0,225 y stitched −0,279, **dentro** de la muestra de selección
     (D-01 dice que eso favorece el positivo).
   - Es lo más cerca que EDGE-1 llega a un «no hay ventaja seleccionable». Lo mismo pasa con
     `edge1-11` (stitched −0,488, 29 pliegues), aunque con 2 operaciones por ventana.
4. **Población grande, correlacionada y con hipótesis que derivan** [HECHO + CÓDIGO].
   - 12.320 pruebas, con unas 75 efectivas de media por campaña.
   - La mutación de bloques y de lógica cambia la hipótesis (§2.2).
   - La selección por OOS-1 entre muchos vecinos lleva a la maldición del ganador: OOS-1 con n = 1
     aceptado.
   - Con un contador de 12.694, cualquier resultado posterior paga un listón DSR enorme. El contador
     mezcla universos [HECHO: TL3 G-7].
5. **Hay defectos del motor que añaden sesgo optimista**: A-02 (stop dormido) y el mantenimiento de
   varios días no intencionado (COLA-MOTOR-FLAT) [HECHO]. Si una estrategia hubiera pasado, habría
   que repetirla con el motor corregido. Que no pasara ninguna con sesgo optimista refuerza el
   «no hay ventaja grande».

**Veredicto [HIPÓTESIS, apoyado en las cifras de arriba]:**
- EDGE-1 descarta, con potencia moderada, ventajas **grandes** (≳ 0,3-0,4 R) en las plantillas
  probadas de FX y XAU H1/H4.
- Sobre ventajas de **0,05-0,15 R no dice nada**: la frecuencia (6-58 operaciones al año), el OOS-1 de
  3 años y unas puertas que no son ni sensibles ni específicas lo impiden.
- Repetir EDGE-1 con más generaciones o perfil `medium` no cambia eso: se gastan pruebas sin ganar
  potencia.

---

## 4. Las cuatro líneas de investigación

### 4.0 Supuesto de potencia (común) [ARIT]

Fórmula: n = ((z₁₋α + z₁₋β) · σ / δ)², con δ = 0,10 R, potencia del 80 % (z = 0,8416) y operaciones
independientes.

- σ = 1,0 R: es la convención del repo (`MDE = 2,49/√n`, TL3).
- σ = 1,4 R: el prerregistro NQF para SL 1R / TP 2R.
- σ = 1,9 R: la medida del EA con RR 3,5 (1,87-1,92 R, `RESULTADO-E2.md`).
- En la fase C de NQ, el EE citado (±0,03-0,05 R con n de cientos a miles) implica σ ≈ 1,0-1,3 R
  [ARIT].

| σ (R) | Unilateral, α = 0,05 | Bilateral, α = 0,05 | Unilateral, α = 0,05/3 |
|---:|---:|---:|---:|
| 1,0 | **619** | 785 | 882 |
| 1,4 | **1.212** | 1.539 | 1.729 |
| 1,9 | **2.232** | 2.834 | 3.184 |

Años necesarios (unilateral, α = 0,05) según la frecuencia:

| Operaciones/año | σ = 1,0 | σ = 1,4 | σ = 1,9 |
|---:|---:|---:|---:|
| 14 | 44 | 87 | 159 |
| 30 | 21 | 40 | 74 |
| 58 | 11 | 21 | 39 |
| 70 | 8,8 | 17 | 32 |
| 91 | 6,8 | 13 | 25 |
| 200 | 3,1 | 6,1 | 11 |
| 250 | 2,5 | 4,8 | 8,9 |
| 370 | 1,7 | 3,3 | 6,0 |

Todos estos tamaños son **para la muestra de confirmación**: el desarrollo necesita su propia
muestra. Con autocorrelación ρ = 0,3, el EE real es 1,43 veces el i.i.d. [HECHO: `D-stats.md`
D-12], así que n se multiplica por unas 2 veces. Si el umbral es el DSR global (N ≈ 12.694) en vez
de una α por familia, n crece todavía más.

### 4.A NQ / MNQ: microestructura CME

**Ya probado (no repetir):**
- Fase C completa: ruptura del OR (5/15/30, cierre o retest); barridos PD/ON; VWAP de reversión y de
  continuación; desplazamiento + FVG; subasta/perfil de volumen con RVOL. Todo en 9:35-11:30 ET,
  NQ 2010-2018 y Dukascopy 2022-23. Resultado: rechazadas.
- Fase B: 7 descriptivas.
- NQF-A/B/C: en forward; no se tocan ni se derivan.
- H1 nocturna (`cost_gate` en CFD).
- T8 pre-FOMC (no confirma).

**Lo que queda, con otra hipótesis económica** [HIPÓTESIS; ninguna usa OR, gap, FVG, VWAP, barrido
ni RVOL de la apertura, que son entradas del EA]:
1. **Presión de precio por el desequilibrio MOC del cierre de contado (16:00 ET) y reversión en
   Globex.** Mecanismo: liquidez prestada a los desequilibrios de cierre, que se paga con reversión.
   - Unas 250 operaciones al año.
   - Riesgo de solape parcial con `intraday_momentum_close` (última media hora; probada en US100
     2021-24). Hay que declarar la diferencia: reversión **después** de las 16:00, no momentum
     **hasta** el cierre.
2. **Descubrimiento de precio en la apertura europea (03:00 ET) dentro de Globex.** Mecanismo:
   información de la sesión europea con poca liquidez en NQ.
   - Unas 250 al año.
   - Dukascopy US100 antes de 2018 trae unas 450 velas nocturnas, frente a 930 después
     [HECHO: `COLA-TL3-C.md` H-f]. Solo es viable con NQ.
3. **Deriva nocturna en futuros (reapertura de H1).** No es una hipótesis nueva: es H1 en otro
   instrumento.
   - Motivo para reabrir: en futuros la financiación va implícita en la base (≈ r − q) y no se paga el
     margen del swap de CFD que provocó el `cost_gate`.
   - Solo con decisión del operador, porque H1 ya tiene veredicto de coste.
4. **Order flow** (delta agresor, desequilibrio del libro): **imposible** con OHLCV-1m y con el DSL
   actual (§2.1).

**Datos: necesarios frente a disponibles** [HECHO: `Nasdaq_Intraday_Research.md` §2;
`data_manifest.md`]:

| Necesario | Disponible |
|---|---|
| NQ M1 con volumen | 2010-06 → 2018-12 (NQ-B; contaminado para la apertura de NY por el EA, no para 16:00-03:00 ET [HIPÓTESIS]) |
| NQ/MNQ M1 de 2019 en adelante | **no** (decisión 5 de `ESTADO.md`) |
| NQ H1 | 2010 → 2026 (Databento) |
| Trades/MBP para order flow | **Sin datos**; el coste del esquema no consta en el repo |
| Contratos individuales para el roll | **no** (solo `NQ.c.0` por calendario; 36 rolls y 288 sesiones excluidas) |
| Comisiones MNQ | 0,75 USD/lado (`ESTADO.md`). Exchange y clearing: **Sin datos** (`Market_Microstructure.md` §2) |

**Potencia:** a unas 250 operaciones al año, δ = 0,1 R pide 2,5 años (σ = 1) o 4,8 años (σ = 1,4).
- NQ 2010-2018 da unos 8,5 años: alcanza para desarrollo + confirmación con σ ≈ 1, pero no
  sobra para 1,4.
- La restricción real es el **coste**: con stops de 5-6 pt, el coste se come 0,2 R o más (§2.3). Las
  hipótesis 1-2 solo son viables con stops de ≥ 12-13 pt o sin stop intradía.

### 4.B NASDAQ: apertura de NY

**Ya probado:**
- barridos ORB_NY y TREND_INTRADAY;
- `ny_open_vol_filter` con GA (sobreajustada);
- `intraday_momentum_close` v1/v2;
- `session_breakout_htf` (contaminada; edge1_plan §7);
- `st_reversal_idx` US100 H1 (edge2-04, 0 finalistas);
- fase C A-E (las 22 variantes);
- H3 (`no_power`);
- el EA, T7, E2 y NQ-B (inventario; no se proponen derivados).

**Choque con el periodo de diseño del EA [HECHO]:**
- El EA se diseñó en US100 M5 2021-09 → 2026-11 y se probó fuera de periodo en NQ 2010-2018 (NQ-B),
  en Dukascopy 2013-14 y 2018-21 (T7) y en US500/US30 (E2).
- **Todo el histórico de apertura de NY del laboratorio, de 2010 a 2026 y en US100, NQ, US500 y
  US30, ya ha pasado por el diseño o la validación del EA.**
- Sus entradas (OR, gap, FVG, VWAP, sweep, RVOL; `TL3_STATISTICAL_VALIDATION_AUDIT.md` §B) cubren
  casi todo el vocabulario de la apertura.
- El propio plan EDGE-1 marca estas plantillas «a forward, OOS-2 no válido» (`edge1_plan.md` §6-7).

**Cómo aislarla** [HIPÓTESIS]:
1. **Solo forward**, prerregistrado como NQF, con una variante nueva y **sin** las entradas del EA.
   - Coste: n = 200 da un MDE de unos 0,29 R (prerregistro NQF). Para 0,1 R hacen falta unas 1.212
     operaciones (σ = 1,4): **unos 4,8 años** a 250 al año.
   - Útil solo para ventajas grandes.
2. **Otro índice con apertura propia:** GER40 o EU50 (apertura de contado de Xetra/Eurex).
   - Datos: MT5 desde 2021-2022 (`data_manifest.md`); histórico largo **Sin datos**.
   - ES/YM M1: **no** descargado (solo H1 de Databento). E2 ya miró US500/US30 a través del EA:
     contaminación parcial.
3. **Otro periodo:** no hay NQ antes de 2010-06 ni Dukascopy US100 antes de 2011-09 [HECHO]. **No
   hay un periodo limpio disponible.**

**Hipótesis que queda** [HIPÓTESIS, prior baja]:
- Momentum de la primera media hora sobre la última media hora en un **índice no estadounidense**
  (GER40).
- Es la misma idea económica que `intraday_momentum_close`, que en US100 dio un bruto de −0,011 R.
  Aquí sería una réplica en otro mercado y contaría como prueba nueva.

**Potencia:** 1 operación al día como máximo (250 al año); con filtros, unas 63-70 al año (H3: 207
días en unos 3,3 años [ARIT]). δ = 0,1 R pide 2,5-8,8 años con σ = 1 y 4,8-17 años con σ = 1,4.

### 4.C Forex por sesiones

**Ya probado:**
- fix (familia cerrada);
- `asia_range_reversion`: USDJPY H1 2010-2024 (c1), más EDGE-1 en EURUSD/GBPUSD H1, USDJPY M30/M15 y
  XAUUSD H1;
- `london_breakout` (EURUSD H1, 3 efectivas);
- TOKYO_BREAKOUT, LONDON_PULLBACK y SESSION_TREND (barridos);
- H-2026-002 Asia USDJPY;
- H6 de HIPÓTESIS (fix de las 16:00; misma familia).
- Ojo: en estas campañas el GA no movió nunca la hora de sesión (§2.2).

**Lo que queda, con otra hipótesis económica** [HIPÓTESIS]:
1. **Fix de Tokio a las 9:55 JST en días gotobi** (5, 10, 15, 20, 25 y fin de mes). Mecanismo:
   demanda de USD de los importadores japoneses antes del fix y reversión posterior.
   - Unos 70 días al año en USDJPY.
   - La referencia bibliográfica está **por verificar**; no la cito.
   - El fix de Tokio **no** se ha probado (el fix probado es el de Londres a las 16:00).
   - Necesita una sesión 08:00-10:30 JST, que hoy no se puede mutar (§2.2), y una regla de calendario
     gotobi con festivos japoneses: **Sin datos** en `calendars.py` [HIPÓTESIS: no lo verifiqué].
2. **Rebalanceo de fin de mes condicionado al retorno de la renta variable** (flujos de cobertura
   antes del fix de Londres). Es distinto del fix genérico, pero hay unos 12 eventos al año por par:
   619 operaciones serían unos 50 años por par. **Sin potencia** salvo con δ ≥ 0,3 R o con una cesta
   amplia; probablemente es otra `no_power`.
3. **Carry** (diferencial de tipos): está bloqueado hasta medir el swap durante ≥ 20 sesiones
   (decisión 6 de `ESTADO.md`).

**Datos:**
- Dukascopy M1 desde 2003 (EURUSD con un 10,9 % de ASK; GBPUSD/USDJPY sin ASK).
- Databento 6E/6B/6J H1 desde 2010.
- MT5 H4 de unos 28 cruces desde 2000-2007 y H1 desde 2018 (`data_manifest.md`).
- Spread por franja horaria: de los perfiles del bróker (TCA con slippage siempre 0: decisión 3 de
  `ESTADO.md`).

**Potencia:** es la **única línea con historia suficiente**.
- A 1 sesión al día (unas 250 al año) se necesitan 2,5 años con σ = 1 y 4,8 con σ = 1,4.
- Al ritmo de c1 (unas 91 al año) se necesitan 6,8 y 13 años.
- Con 23 años de Dukascopy caben un desarrollo y una confirmación de ~10 años cada uno.
- El factor limitante es el **coste en H1 o menos** (`cost_r` de 0,026-0,055 en EDGE-1; la cola de
  `fix-londres` llega a un máximo de 0,169).

### 4.D Regímenes de volatilidad y momentum

**Ya probado:**
- `trend_pullback_mtf` (10 campañas EDGE-1 + 1 en EDGE-2 con 5 finalistas sin Y3);
- `vol_squeeze_breakout` (9 + 1);
- `donchian_vol_h4` (2 + n2 ×2 + edge2-01);
- TSMOM (campañas A/B; spec P4 sin potencia);
- ST_REVERSAL / VOL_BREAKOUT (A/B);
- `st_reversal_idx`;
- `d1_extension_reversion`;
- los bloques de régimen, que el GA ya combina libremente (§2.2).

**Lo que queda, con otra hipótesis económica** [HIPÓTESIS]:
1. **Volatility targeting / exposición gestionada por volatilidad.** La ventaja estaría en el tamaño
   (Sharpe de la cartera), no en la entrada.
   - **Estructuralmente invisible** con R por operación y stop en ATR (§2.1, punto 7).
   - Para estudiarla hace falta otra métrica: rendimiento diario de una cartera con exposición
     variable. Es una construcción nueva, no una campaña.
2. **Deriva o continuación después de eventos programados** (FOMC, CPI, NFP), distinta de la deriva
   *previa* al FOMC (T8).
   - Unos 30 eventos al año por índice: 619 operaciones serían unos 21 años. **Sin potencia** para
     0,1 R.
   - Para δ = 0,25 R bastan unas 99 operaciones, es decir unos 3,3 años [ARIT].
   - Necesita un nodo de eventos (§2.1, punto 2). El calendario histórico ya existe:
     `NASDAQ_EDGE_INSTITUTIONAL/02_DATA/news_calendar_history.csv`.
3. **Régimen de volatilidad implícita** (VIX, término): **Sin datos**.

**Datos:**
- Dukascopy desde 2003 (FX y XAU) y desde 2011-2013 (índices).
- Índices H1/H4 de Dukascopy válidos solo desde 2019-01-02 (`edge2_plan.md`); Databento H1 desde 2010
  en 7 futuros.

**Potencia:** a 6-58 operaciones al año por instrumento (los finalistas de EDGE-1), δ = 0,1 R pide
11-44 años con σ = 1. Tiene que ser una **cesta** amplia (≥ 10-20 instrumentos, con penalización por
correlación **Sin datos**) o declarar δ ≥ 0,25-0,3 R.

### 4.E Recomendaciones transversales [HIPÓTESIS]

1. **Ninguna campaña nueva sin δ y σ declarados** y con el MDE de la muestra de confirmación ≤ δ
   (`power.py` ya existe). Con eso, las campañas de §1.2, H3 y P4 se habrían descartado antes de
   gastar pruebas.
2. **Antes de cualquier reapertura FX o D1, corregir:**
   - el `edge_map` (rama «sin edge bruto», §2.5);
   - `mutate_session` (§2.2);
   - el aviso del contador (§1.5).

   El orden lo decide el operador.
3. **Contar las pruebas por familia** (TL3 S2) y separar EDGE-1 del resto. Con 12.694 pruebas
   mezcladas, el DSR global ya no discrimina.
4. **Prioridad por potencia alcanzable con los datos que ya hay:**
   - C (FX por sesiones, historia larga);
   - A fuera de la apertura de NY (NQ 2010-2018);
   - D solo como cesta o con δ grande;
   - B solo en forward o en otro índice.

