# TL3 · Auditoría de validación estadística

Solo lectura. Leyenda en `TL3_FORENSIC_AUDIT.md`. Notación: R por operación con desviación σ;
MDE (efecto mínimo detectable al 5 % unilateral con 80 % de potencia) = 2,49·σ/√n.

## 1. Implementación real de cada procedimiento

| Procedimiento | Dónde | Estado | Observaciones |
|---|---|---|---|
| IS / OOS-1 / OOS-2 | `engine.yaml:142-143`, `campaigns.py` | **A** | Tramos fijos y comunes a todas las campañas. OOS-2 sellado (0 lecturas) [HECHO] |
| Protocolo v2 (LCB dev + holdout único + consistencia) | `protocol_v2.py` | **B** | Correcto en diseño; usado en 1 campaña [HECHO] |
| Walk-forward | `robustness.py`; EA: 19 pliegues 252/63 | **B** | En Discovery solo se aplica a finalistas. En el EA, el WF **elige entre 8 variantes** ya preseleccionadas [HECHO] `us100-ftmo1_v3.json` |
| Monte Carlo | `prop/simulator.monte_carlo` | **B** | Bootstrap de R diarios **del backtest de diseño**; P(pasar) hereda el sesgo de selección [INFERENCIA] |
| Bootstrap por bloques | `nq_adapter.weekly_lcb`, informes EA | **A** | Bloques semanales de 10.000 remuestreos [DOC] |
| DSR | `stats.py:63-187` | **A (fórmula) / G (uso)** | La fórmula de Bailey-López de Prado está bien implementada y valida unidades. El problema son las entradas: ver §B |
| PBO (CSCV) | `robustness.py` | **B** | EA: 0,241 con **8 variantes**. Con 8 variantes casi idénticas, el PBO mide poco [INFERENCIA] |
| Pruebas múltiples | `count_tests`, SPA (`family.py`) | **C** | Contador global heterogéneo; SPA por familia sin uso real [HECHO] |
| Intervalos de confianza | t / bootstrap | **A** | — |
| Potencia | `power.py` | **C** | Sin δ declarado no bloquea; 0 de 18 campañas declararon δ [HECHO] |
| Tamaño mínimo | `min_trades_*` en `engine.yaml:53-90` | **G** | Mínimos de 15 operaciones (D1) o 25 (H4) en IS no tienen relación con la potencia [HECHO] |
| Estabilidad de parámetros | `plateau.py` (meseta ≥ 0,6) | **B** | Solo en protocolo v2 [DOC] |
| Estabilidad de régimen | `levels.py` (años positivos) | **B** | "Todos los años positivos" con 34–96 operaciones/año aprueba fácilmente un efecto grande en muestra [INFERENCIA] |
| SPRT forward | `sprt.py` | **A** | Bien usado en el informe del EA: demuestra que el forward no puede decidir en un plazo razonable [DOC] |

## 2. Errores metodológicos

### A · Data snooping

| Datos | Usos documentados | Etiqueta |
|---|---|---|
| US100 M5 2021-09 → 2026-11 | Diseño del EA (v1 → v3 → v3.1 → v3.2, iteraciones **sin registrar**), barrido de 8 variantes, WF, PBO, régimen, P(pasar), 3 campañas Discovery M5 (momentum ×2, GA NY open), barridos ORB_NY / TREND_INTRADAY, `ai_trader` (en vivo) | [HECHO] |
| US100/US500 D1 2014/2018 → 2024 | 4 campañas de cambio de mes, 2 de rebote, 18 miradas informales en ES/NQ, campañas A/B | [HECHO] |
| EURUSD/GBPUSD/USDJPY H1 2010 → 2024 | 48 barridos FIX_FLOW, 4 campañas de fix, Asia | [HECHO] |

**[INFERENCIA]** US100 M5 está **agotado como muestra de descubrimiento**. Cualquier hipótesis nueva de
apertura NY en US100 M5 que se evalúe en 2021-2026 hereda lo que el operador y los agentes ya vieron
al construir el EA.

### B · DSR: fórmula correcta, entradas incorrectas
- **[HECHO]** `dsr_local` del EA usa N = 8 y la desviación de los Sharpes de 8 variantes que difieren en
  RR (3,0/3,5), gap (0,5/0,7) y racha (1/2) (`trial_sr_std_period = 0,0080`). Ocho vecinos de un diseño
  ya elegido no representan las pruebas reales: el diseño de un EA con **~70 entradas** (pesos de
  puntuación 25/20/20/15/10/10, `InpMinScore=55`, `InpRR=3.5`, `InpGapMin=0.7`, filtros de FVG, VWAP,
  sweep y RVOL; ver `US100_FTMO_v3_challenge.set`) implicó muchas más decisiones. El número real de
  pruebas es **Sin datos**. **DSR local = 0,999 es una cota superior optimista.**
- **[HECHO]** El setfile elegido es la **mejor** de las 8 variantes (`baseline_index = 6`, SR 1,441, la más
  alta de la tabla de `ea_us100_m5_only.md §3`).
- **[HECHO]** `dsr_global` usa N = `count_tests` (hoy 1.894) y la dispersión de 653–661 Sharpes de
  acciones, D1, H4 y M5. Mezcla universos que no se buscaron para este EA. **No es un DSR útil para
  ninguna decisión.**
- **[REC]** Para el EA, sustituir ambos por una prueba que no dependa de contar el pasado: datos que el
  diseño no vio (ver `TL3_US100_CASE_STUDY.md §6`).

### C · Contaminación del holdout
- **[HECHO]** OOS-2 de Discovery = 2025-07-01 → hoy, para **todas** las campañas.
- **[HECHO]** El EA v3.2 se fijó el 2026-11-16 con datos hasta 2026-11-13 (`docs/ea_us100_ftmo1.md`). Su
  "holdout natural" son **2 operaciones** (`us100-ftmo1-v2.md §5`).
- **[INFERENCIA]** Para cualquier hipótesis de US100 intradía alrededor de la apertura de NY, el OOS-2
  de Discovery está contaminado por el diseño del EA. Para hipótesis D1 de índices, OOS-2 está limpio
  de lecturas formales, pero el operador observa el mercado a diario y `ai_trader` opera en él. Un
  holdout de calendario reciente nunca es ciego para alguien que vive en ese mercado.
- **[HECHO]** La campaña 2026-11-B ya se declaró `contaminated` (holdout solapado con A y regla
  decidida tras ver el anexo). Bien detectado.
- **[REC]** Holdouts **fuera de periodo o fuera de instrumento**, fijados en la spec: por ejemplo,
  desarrollar en 2015–2021 (Dukascopy) y reservar 2011–2014. La historia vieja no está "vista" por
  la memoria reciente del operador.

### D · Tamaño muestral
[REPRODUCIDO] con σ = 1 R (supuesto del arnés T01; para estrategias con RR ≥ 2, σ es mayor, así que
estos MDE son **optimistas**):

| Campaña | Ops IS (mediana) | MDE IS | Ops OOS-1 | MDE OOS-1 | Efecto plausible (literatura/bruto observado) | ¿Detectable? |
|---|---:|---:|---:|---:|---:|---|
| Cambio de mes US100 | 109 | 0,24 | ~10 | ~0,8 | 0,05–0,10 | **No** |
| Rebote US100 | 27 | 0,48 | 0 | — | 0,1–0,15 | **No** |
| Donchian XAUUSD H4 | 391 | 0,13 | 16–19 | ~0,6 | 0,04 (bruto) | **No** |
| GA NY open US100 M5 | 752 | 0,09 | ~160 | ~0,2 | 0,02–0,05 | **No** |
| Fix EUR+GBP v2 | 7.527 | 0,029 | — | — | 0,02 (bruto) | Sí en IS; el bruto < coste |
| EA (σ = 1,92) | 478 | 0,22 | — | — | 0,15–0,31 | Sí en muestra de diseño |

**[INFERENCIA]** 11 de 16 campañas no podían, por diseño, detectar el efecto que buscaban.

### E · Potencia del forward
- [DOC] EA: σ = 1,92 R, 2,02 operaciones/semana. Confirmar δ = LCB95 (0,168 R) con SPRT exige
  ~246 semanas (`us100-ftmo1-v2.md §7`). **El forward demo no puede validar el EA en un plazo útil.**
- [REPRODUCIDO] `ai_trader`: 44 operaciones en 12 días. Con sd(diferencia) = 1,32, MDE ≈ 0,50 R.

### F · Otras observaciones
- **[HECHO]** OOS-1 como filtro de signo con PF > 1,1 (`decisions.oos1_check`) se aplicó a OOS-1 de
  9–19 operaciones en D1/H4. Con ese n, el filtro es una moneda al aire (TL2 P0-2).
- **[INFERENCIA]** Seleccionar la mejor celda de la rejilla por OOS-1 (Donchian XAUUSD, +0,39 R) es una
  selección post hoc sobre OOS-1. El protocolo v1 lo permite. El v2 lo corrige con la primaria
  prerregistrada.
- **[HECHO]** Los criterios del EA fuera de instrumento (exp ≥ 0,10 R, LCB95 > 0, n ≥ 150) se fijaron
  antes y se respetaron. Buen ejemplo a seguir.

## 3. Lo que está bien

- Fórmula del DSR, validación de unidades y rechazo del DSR v1 "anualizado" (`dsr_v1_invalid_units`).
- Arnés T01 con P(aprobar | nulo) ≤ 0,005. **El pipeline no fabrica falsos positivos.**
- Protocolo v2: primaria prerregistrada, LCB de desarrollo, meseta y consistencia del holdout.
- Registro de miradas informales con motivo y aprobación.

## 4. Recomendaciones (sin rebajar el rigor)

| # | Cambio | Por qué |
|---|---|---|
| S1 | `plausible_edge_r` y `sigma_r` obligatorios; rechazar el registro si MDE_holdout > δ | Elimina las campañas sin potencia (11 de 16) |
| S2 | Contabilidad de pruebas **por familia de hipótesis** con DSR/SPA por familia; contador global solo informativo | El DSR global actual no responde a nada |
| S3 | Holdout por spec: fuera de periodo antiguo o fuera de instrumento, nunca "los últimos 16 meses" para US100 intradía | Contaminación §C |
| S4 | Usar el arnés T01 para cada cambio de umbral, con la tabla P(aprobar \| 0) y P(aprobar \| δ) en el `RESULTADO` | Ya existe; hacerlo obligatorio |
| S5 | Registrar el **número de variantes** de cualquier diseño manual (EA, ideas de agentes) en `informal_trials` antes de mirar resultados | El EA no tiene ese registro |
| S6 | No aceptar "PF > 1" ni "todos los años positivos" como criterio. Primaria: LCB95 de la expectativa neta por operación ≥ 0 y holdout consistente | Pedido del operador; ya en v2 |
