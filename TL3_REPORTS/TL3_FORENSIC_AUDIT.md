# TL3 · Auditoría forense de TradingLab

**Fecha:** 2026-11-25 · **Rama:** `feature/prop-fund-multifirm` · **HEAD:** `a36a5ee`
**Modo:** solo lectura. No se modificó código, configuración ni bases de datos. Las bases se
consultaron sobre **copias** en un directorio temporal (`mode=ro`). No se ejecutó ningún backtest,
campaña ni barrido, y `count_tests` no cambió.

## Leyenda de evidencia

| Etiqueta | Significado |
|---|---|
| **[HECHO]** | Comprobado en código, base de datos o archivo durante esta auditoría |
| **[REPRODUCIDO]** | Cifra recalculada por mí con `TL3_REPORTS/evidencia/*.py` |
| **[DOC]** | Lo dice un informe o documento del repo; no lo recalculé |
| **[INFERENCIA]** | Conclusión razonada a partir de hechos; puede ser errónea |
| **[HIPÓTESIS]** | Pendiente de comprobar |
| **[REC]** | Recomendación |

## 0. Contexto que cambia la lectura del problema

- **[HECHO]** El proyecto tiene **21 días** (primer commit 2026-11-05; HEAD 2026-11-25), **433 commits**,
  ~114.000 líneas Python en `src/`, 235 archivos de test y un `cli.py` de 12.392 líneas con 219 comandos.
- **[HECHO]** Discovery, el motor actual de investigación, existe desde el **2026-11-20**: cinco días.
  En `data/discovery.db` hay **18 campañas**, **634 filas de estrategia**, **681 evaluaciones** y
  **0 lecturas de holdout**. Ninguna estrategia ha llegado a nivel 4. Solo una pasó del nivel 2.
- **[INFERENCIA]** La sensación de "mucho tiempo sin resultados" no procede de una búsqueda larga que
  fracasa. Procede de **tres semanas casi enteramente dedicadas a infraestructura**, con un volumen de
  investigación real muy pequeño. La mayoría de las campañas, además, **no podían detectar**
  ventajas del tamaño realista (ver `TL3_STATISTICAL_VALIDATION_AUDIT.md`).

## 1. Mapa de componentes

Clasificación: **A** funcional · **B** funcional con limitaciones · **C** parcial · **D** experimental ·
**E** sin implementar · **F** redundante · **G** potencialmente defectuoso · **H** protegido.

### 1.1 Investigación (Discovery)

| Componente | Archivo(s) | Clase | Evidencia |
|---|---|---|---|
| Registro, guard y aprobación de campañas | `discovery/campaigns.py`, `guard.py` | **A** | [HECHO] 18 campañas con `config_hash`, `dataset_hash` y estado; ninguna leyó OOS-2 sin `confirm` |
| Snapshots de datos con hash | `discovery/snapshots.py` | **A** | [HECHO] `snapshot_hash` y `snapshot_rows` en `disc_campaigns` |
| Backtester vectorial | `discovery/fastbt.py` (2.122 l.) | **B** | [HECHO] Modelo de coste v2 corregido (T10), pero `RunLimits.cost_model_version = 1` por defecto (`fastbt.py:150`, `:593`, `:1692`). Solo las campañas registradas con v2 lo usan |
| Modelo de costes | `discovery/costs.py` | **B/G** | [HECHO] v2 existe; **17 de 18 campañas se ejecutaron con v1** (doble spread). Spread histórico real solo para EURUSD 2021-09 → 2024-03 (ver §3) |
| Generador DSL + compilador | `dsl.py`, `compiler.py`, `blocks.py` | **B/G** | [HECHO] La campaña `disc-…171711-303e5662` quedó `invalid` por "espejo del umbral sin signo": un defecto del generador invalidó 144 estrategias |
| NSGA-II / GA | `nsga2.py`, `genetic.py` | **D** | [HECHO] Usado en **una** campaña (`ny_open_vol_filter`, 260 evaluadas). Sus 2 finalistas acabaron `SOBREAJUSTADA` |
| Rejilla (grid) | `grid.py` | **A** | [HECHO] 16 de 17 campañas no anuladas son rejillas de 6–32 celdas |
| Niveles y validaciones | `levels.py`, `robustness.py`, `decisions.py` | **A** | [HECHO] Las validaciones tumbaron correctamente a los finalistas del GA (WF, PBO, régimen, bootstrap en `disc_validations`) |
| Protocolo v2 (LCB dev + holdout único) | `protocol_v2.py` | **B** | [HECHO] Implementado; usado en **1** campaña (`v2-fix-londres-eurgbp-h1`) |
| Puerta de potencia | `power.py` | **B** | [HECHO] Solo bloquea si la spec declara `plausible_edge_r`. **Ninguna campaña registrada lo declara** (`delta=None` en las 18) |
| SPA / SPRT | `sprt.py`, `family.py` | **C** | [DOC] Implementados en T23/T24/A1; sin uso en una decisión real todavía |
| Arnés de autoevaluación | `harness.py` | **A** | [DOC] P(aprobar \| nulo) ≤ 0,005; P(aprobar \| 0,10 R, 1.000 ops/año) ≈ 0,96–0,98 |
| Edge Map | `edge_map.py` (1.431 l.) | **B** | [HECHO] Tabla `reports/discovery/edge_map.md` desactualizada (exportación del 2026-11-22) y con cambios sin commitear |
| Export a MQL5 | `export_mql5.py` (2.248 l.) | **F** | [INFERENCIA] No hay ninguna estrategia de Discovery que exportar. Es código sin consumidor |
| Optimizer / perturb | `optimizer.py`, `perturb.py` | **G** | [DOC] `RESULTADO-T10.md` los lista como "usa el default v1" |
| Fetch Dukascopy | `fetch_dukascopy.py` | **B/G** | [HECHO] Las columnas `ask_*` existen pero están **vacías** en 6 de 7 símbolos (ver `TL3_DATA_AND_COSTS_AUDIT.md`) |
| Fetch Databento (CME) | `fetch_databento.py` | **G** | [HECHO] Guarda NQ como `US100_*.parquet`, ES como `US500`, etc. (`ROOT_TO_INTERNAL`, `:66-74`), sin columna de contrato |
| Ajuste de vencimientos | `futures_roll.py` | **C** | [DOC] T31; no hay campañas de futuros ejecutadas |

### 1.2 Producción y protegidos (solo lectura)

| Componente | Archivo(s) | Clase | Nota |
|---|---|---|---|
| EA `us100-ftmo1` | `integrations/mt5/us100_ftmo1/`, `ea_us100_engine.py`, `ea_us100.py` | **H** | Ver `TL3_US100_CASE_STUDY.md` |
| `ai_trader` | `ai_trader.py` (3.957 l.) | **H + G** | La gemela aleatoria está mal construida (ver `TL3_AI_TRADER_AUDIT.md`) |
| Prop Fund | `propfund/` | **H** | No auditado en profundidad: no afecta al descubrimiento de ventaja |
| `ea_lab` | `ea_lab/` | **H** | `nq_adapter.py` contiene la prueba NQ-B (ver §2, G-1) |
| Riesgo FTMO / forward | `prop/`, `forward_intraday.py` | **H** | No modificado |

### 1.3 Carriles históricos

| Componente | Clase | Evidencia |
|---|---|---|
| Barridos "research" (`research.py`, `intraday.py`, `swing.py`) | **F** | [HECHO] `strategy_trials`: ~450 filas `sweep`, todas `failed` (LONDON_PULLBACK, SESSION_TREND, ORB_NY, TOKYO_BREAKOUT…), 2026-11-09 → 11 |
| Campañas multiactivo 2026-11-A/B (`campaign.py`, 2.928 l.) | **F** | [HECHO] `campaign_registry`: B marcada `contaminated` ("holdout solapado con el descubrimiento de 2026-11-A… regla (c) decidida tras ver el anexo; ejecutada sin aprobación"); 0 de 23 confirmadas |
| Optuna en acciones (SPY, QQQ, MSFT) | **F** | [HECHO] 93 `optimization_trials` y 4 `holdout_reads` sobre acciones: siguen sumando al contador del DSR de CFD |
| TradingAgents / agent-lite (LLM sobre acciones) | **F** | [HECHO] Las 115 `llm_calls` son `agent-lite:SPY/QQQ/NVDA…` y `news-score`. Carril archivado |

## 2. Problemas identificados

Prioridad: **P0** invalida conclusiones o gasta dinero/tiempo ya · **P1** sesga resultados · **P2** deuda.

### G-1 · P0 · La prueba NQ-B no puede pasar su propia puerta de validez
- **Archivo:** `scripts/ea_nq_out_of_period.py:36-39, :170-192`; `ea_lab/nq_adapter.py:246-291` (`match_validity`).
- **Evidencia [HECHO]:** la validez exige reproducir en **2018** las operaciones del motor sobre
  `data/cache/ea/US100_CASH_M5_NY.parquet`. En esa caché **2018, 2019 y 2020 son velas D1**
  (paso dominante 1 día; 258 filas en 2018). El M5 empieza el 2021-09-14
  (`reports/audit/ea_us100_m5_only.md §1`, recomprobado). Con velas diarias, el motor no genera las
  operaciones de 09:45–11:00, y `matched_pct` saldrá ≈ 0 % → "prueba no válida".
- **Agravante [HECHO]:** el factor `k` se calcula con el ATR14 de NQ M5 frente al ATR14 de "US100 M5"
  en 2018, que es en realidad ATR diario. `k` quedaría muy por debajo de 0,9 y **reescalaría los
  parámetros del EA** con un valor sin sentido.
- **Estado [HECHO]:** OpenCode está ejecutando ahora la descarga (`download_nq.py`, PIDs 3336/31648,
  iniciados a las 10:13). El archivo `data/cache/databento/US100_M1.parquet` ya contiene NQ
  2010-06-07 → 2012-12-31 (788.783 filas) y crece. El operador ya registró `informal_trials` n=1.
- **Impacto:** ~9,93 USD gastados en una prueba que, con el prerregistro tal como está, termina
  en "Sin datos". El riesgo mayor es metodológico: tras ver "no válida", la tentación será cambiar
  el criterio de validez **después** de tener los datos.
- **[REC]** Antes de ejecutar B2, el operador decide por escrito **una** de estas enmiendas, sin mirar
  NQ 2010-2017: (a) validar contra Dukascopy US100 M1 2018 (solo BID, ver §3) remuestreado a M5; o
  (b) validar NQ frente a US100.cash en el primer tramo M5 común (2021-10 → 2022-09) y no usar 2018.
  La enmienda se anota en el `RESULTADO` antes de correr nada.

### G-2 · P0 · Futuros CME guardados con nombre de CFD
- **Archivo:** `discovery/fetch_databento.py:66-74` (`ROOT_TO_INTERNAL`), `:223-230` (`cache_path`), `:650-660`.
- **Evidencia [HECHO]:** `data/cache/databento/US100_M1.parquet` contiene precios NQ (1.826,25 el
  2010-06-07). `US100_H1`, `US500_H1`, `US30_H1`, `XAUUSD_H1`, `EURUSD_H1`… son NQ, ES, YM, GC, 6E.
  El archivo no guarda el contrato (`instrument_id`/`raw_symbol`), y `download` **concatena** sobre la
  caché existente sin registrar la procedencia de cada tramo.
- **Impacto:** cualquier módulo que cargue "US100" desde `databento/` está usando futuros. Es
  exactamente la confusión US100 CFD ↔ NQ que el operador quiere evitar. Sin contrato por fila, los
  rolls no pueden auditarse desde el dato.
- **[REC]** Nombres de futuros propios (`NQ_c0_M1.parquet`), columna `raw_symbol` y un manifiesto
  de descargas. Ver `TL3_DATA_AND_COSTS_AUDIT.md`.

### G-3 · P0 · Las conclusiones vigentes se obtuvieron con el modelo de costes defectuoso
- **Evidencia [HECHO]:** `config_json.cost_model_version` es `None` (→ v1, doble spread) en 17 de 18
  campañas. Solo `v2-fix-londres-eurgbp-h1` usa v2. `README.md §1` cita como "cerradas" el fix de
  Londres, el cambio de mes y el rebote D1.
- **Impacto:** el fix sigue cerrado (con v2 el bruto 0,019 R no cubre el coste 0,032 R). Cambio de mes
  y rebote se cerraron con v1 **y** sin potencia: **no están refutados, están sin probar**.
- **[REC]** Reetiquetar en el Edge Map: "no concluyente (v1, sin potencia)". No relanzarlos tal cual
  (ver `TL3_DISCOVERY_FAILURE_ANALYSIS.md §5`).

### G-4 · P0 · La gemela aleatoria de `ai_trader` no es un contrafactual válido
- **Archivo:** `ai_trader.py:2840-2915` (`_shadow_window`, `_shadow_sim`).
- **Evidencia [REPRODUCIDO]:** en los 22 casos en que la gemela eligió **el mismo lado** que la IA, con
  entrada, SL y TP idénticos, la IA obtiene +0,007 R y la gemela −0,271 R. Esa diferencia no puede
  venir de la decisión de la IA.
- **Causas [HECHO]:** (1) la ventana incluye la vela que contiene la entrada, así que el SL puede
  "dispararse" con precios anteriores a la entrada; (2) dentro de una vela se comprueba el SL antes que
  el TP; (3) la gemela no tiene el cierre forzoso ni la gestión de la IA; se evalúa hasta la salida de
  la IA y queda en `shadow_status='open'` (44/44); (4) la IA se mide con fills reales y costes, y la
  gemela con precios de vela sin coste.
- **Impacto:** el +0,31 R de `reports/ai_trader/vs-gemela.md` está sesgado a favor de la IA. El
  veredicto "no se distingue del azar" es correcto, pero por razones más fuertes que las citadas.

### G-5 · P1 · Spread histórico: anunciado como implementado, pero casi sin datos
- **Evidencia [HECHO]:** columnas `ask_*` de Dukascopy vacías en US100, US500, US30, XAUUSD, GBPUSD
  y USDJPY. EURUSD solo tiene ASK de 2021-09 a 2024-03 (10,9 % de las barras). `reports/discovery/spread-historico.md`
  lo reconoce y el modelo v2 cae a la **mediana horaria del bróker de 2026**.
- **Impacto:** `README.md §1` dice "Costes v2 (BID/ASK, spread por barra…)". Para Discovery, el
  spread por barra solo existe en EURUSD. En el resto es un spread de 2026 aplicado a 2010–2024.
  El EA sí usa el spread histórico por barra de MT5 (2021+).

### G-6 · P1 · La puerta de potencia no bloquea nada en la práctica
- **Archivo:** `discovery/power.py`; `campaigns.register`.
- **Evidencia [HECHO]:** `plausible_edge_r` es `None` en las 18 campañas. Sin δ, `power_check` "avisa y
  no bloquea" (`RESULTADO-T20.md`).
- **[REC]** Hacer obligatorio `plausible_edge_r` en specs nuevas y rechazar el registro sin él.

### G-7 · P1 · El contador del DSR mezcla universos
- **Evidencia [HECHO]:** `count_tests` (`learning.py:175-260`) suma 93 trials Optuna y 4 lecturas de
  holdout sobre **acciones**, ~450 barridos de un carril archivado y 460 celdas de campañas A/B
  junto a las campañas CFD. `dsr_global` usa N = `count_tests` y la dispersión de Sharpes de series
  con frecuencias y activos distintos.
- **Impacto:** el DSR global no responde a ninguna pregunta concreta. Penaliza al EA por búsquedas en
  acciones que no tienen relación con su diseño, y a la vez **no** cuenta las iteraciones reales del
  diseño del EA (v1 → v3.2), que no están registradas.
- **[REC]** Contabilidad por familia de hipótesis (ya iniciada en T23), con el contador global solo
  como dato informativo.

### G-8 · P1 · Un solo holdout, compartido y con fecha fija, para todo
- **Archivo:** `config/discovery/engine.yaml:142-143`; `protocol_v2` (`holdout_start=2025-07-01`).
- **Evidencia [HECHO]:** las 18 campañas usan OOS-1 = 2024-07 → 2025-06 y OOS-2 = 2025-07 → hoy.
  El EA v3 → v3.2 se diseñó y ajustó con datos de US100 hasta 2026-11
  (`docs/ea_us100_ftmo1.md`: "2021-09-15 → 2026-11-13").
- **Impacto [INFERENCIA]:** para hipótesis de **apertura de NY en US100** (la familia del EA), el OOS-2
  ya está visto por el operador a través del EA. Es contaminación indirecta del holdout. Ver
  `TL3_STATISTICAL_VALIDATION_AUDIT.md §C`.

### G-9 · P2 · Informes y README desalineados con la base de datos
- **[HECHO]** `README.md §1`: "rebote D1 (sin edge bruto)". En `discovery.db`, `q1-rebote-us100-d1`
  tiene 27/27 celdas con bruto > 0 (mediana +0,150 R), con 27 operaciones de mediana en 10 años y 0
  en OOS-1. Es "muestra insuficiente", como dice `edge_map.md`, no "sin edge bruto".
- **[HECHO]** `reports/ai_trader/vs-gemela.md` atribuye al carril IA "115 llamadas LLM". Esas llamadas
  son del carril de acciones (`agent-lite:SPY…`, 2026-11-06 → 19). El coste real de `ai_trader`
  (OpenCode + DeepSeek) no está registrado: **Sin datos**.
- **[HECHO]** `reports/ea/us100-ftmo1-v2.md §2` titula "Backtest (2017-12-28 → 2026-11-23)", pero
  las 478 operaciones son de 2021-09 en adelante. El periodo efectivo es de ~5,2 años.

### G-10 · P2 · Tamaño y dispersión del código
- **[HECHO]** `cli.py` 12.392 líneas, `web.py` 3.141, `ai_trader.py` 3.957, `campaign.py` 2.928,
  `export_mql5.py` 2.248. Hay tres motores de backtest con convenciones distintas (`fastbt`,
  `ea_us100_engine`, `backtest`/`campaign`).
- **Impacto [INFERENCIA]:** cada cambio de convención (coste, sesión, festivos) hay que replicarlo en
  varios sitios. G-3 y G-5 son síntomas de eso. No es la causa principal de que no haya ventaja.

## 3. Lo que funciona bien (y no hay que tocar)

- **[HECHO]** Disciplina de holdout: 0 lecturas de OOS-2 en Discovery; las 4 lecturas que existen son
  de acciones (Optuna) y están registradas.
- **[HECHO]** Prerregistro y trazabilidad: `config_hash`, `dataset_hash`, `informal_trials` con
  motivo, `superseded_by`, contaminación declarada en `campaign_registry`.
- **[HECHO]** Las validaciones de nivel 3 descartaron a los finalistas sobreajustados del GA. El
  sistema **no aprueba basura**.
- **[DOC]** El arnés T01 mide P(aprobar | nulo) y P(aprobar | δ). Es la herramienta más valiosa del
  repo para cambiar umbrales sin autoengaño.
- **[HECHO]** El motor del EA modela bien BID/ASK con el spread de cada barra MT5.

## 4. Diagnóstico

**[INFERENCIA, con la evidencia de los otros nueve documentos]** TradingLab no encuentra ventajas por
este orden de causas:

1. **Casi nunca ha hecho una prueba capaz de encontrarlas.** De 16 campañas evaluadas, solo 4 (las
   del fix) tienen potencia para detectar 0,05 R, y allí el bruto (0,01–0,02 R) no cubre el coste.
   Las demás tienen un MDE de 0,09 a 0,62 R.
2. **Las hipótesis se eligen por disponibilidad de plantilla, no por tamaño de efecto esperado.**
   Efectos de calendario D1 de un solo instrumento no se pueden detectar en R con 10 años de datos.
3. **Costes v1 y spread anacrónico** sesgaron a la baja 17 campañas. Es real, pero pesa menos que (1):
   en el fix, v1 → v2 solo baja el coste de 0,036 a 0,032 R.
4. **Toda la energía se fue a infraestructura.** 21 días, 114.000 líneas y 18 campañas, de las que solo
   9 hipótesis son distintas.
5. **El único activo con señal (el EA) no tiene ninguna prueba fuera de muestra válida.** La única
   prueba en marcha (NQ-B) está mal especificada (G-1).
