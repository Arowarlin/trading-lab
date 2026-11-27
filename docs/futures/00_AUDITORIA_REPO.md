# FUT-0 · Auditoría del repositorio (Fase 0) · TradingLab Futures-First

**Fecha:** 2026-11-27 · **Autor:** Claude Code (arquitecto) · **SHA auditado:** `5b277cb`
(rama `claude/vibrant-mayer-r46s0o` = `master` del operador en ese commit).
**Modo:** solo lectura. No se ha modificado código, configuración, datos, campañas ni producción.

**Etiquetas de certeza** (se usan en todo el documento):
- **Confirmado:** leído en el código o en un fichero del repo, con su ruta.
- **Estimado:** cálculo o inferencia razonada sobre datos del repo.
- **Hipotético:** posible, pendiente de comprobar.
- **No verificado:** dato externo (web, firma, proveedor) no comprobado en esta sesión.

Esta auditoría **no repite** la de ENG-1 (`docs/engineering/AUDIT_FINDINGS.md`, 2026-11-26), que
sigue vigente: la cita por su ID (A-01, D-02…) y añade solo lo que cambia con el enfoque futures-first.

---

## 1. Executive Summary

1. TradingLab es un laboratorio **maduro y honesto, pero nacido para CFD/MT5**: 117.171 líneas de
   Python en `src/tradinglab`, 236 comandos `lab`, 276 ficheros de test (~2.100 tests), CI en Windows.
   Su cultura científica es su mayor activo: prerregistro, holdout OOS-2 sellado, contador único de
   pruebas (`count_tests` = **17.974**), puertas v3, SPA de Hansen, SPRT y verificación por una sesión
   independiente. **Confirmado.**
2. **No existe ninguna ventaja validada.** 0 de 34 finalistas (EDGE-1 + EDGE-2) pasan las 4 puertas;
   C1 (USDJPY gotobi) rechazada hoy (t HAC 1,02 < 1,645); el EA `us100-ftmo1` es **incierto** fuera de
   su periodo de diseño (−0,03 R); `ai_trader` no concluyente. **Confirmado** (`ESTADO.md`,
   `docs/engineering/WORKER_REPORTS/L3-c1.json`).
3. Los futuros existen como **camino secundario**: NQ M1 solo 2010-06 → 2018-12, H1 2010 → 2026-11
   (Databento OHLCV, sin bid/ask ni instrument_id), ProjectX en dry-run, firmas de futuros con reglas
   vacías en el registro y costes de futuros en **Sin datos**. **Confirmado.**
4. **Research A (order flow) está bloqueada por datos:** no hay trades, TBBO, MBP ni MBO; el código
   solo admite `ohlcv-1m/1h`. **Research B (NY open) está contaminada** en NQ/US100 2010-2026 por la
   lógica del EA (`COLA-NQEDGE-FORWARD §1`); la única evidencia limpia es el forward NQF que arranca
   el **2026-11-30**. **Confirmado.**
5. **El valor esperado neto de una cuenta de fondeo nunca se ha calculado** (`TL3_REPORTS/
   propfund_zero_edge.md`: "EV: Sin datos"). El simulador existente (`prop/simulator.py`) trabaja con
   retornos diarios en % para CFD y no modela flotante intradía, payouts, tarifas ni reglas de futuros.
   **Confirmado.**
6. **No hay integración con NinjaTrader 8** (solo se menciona en documentos). **Confirmado.**
7. **Recomendación principal:** construir primero el **Prop Firm Expected Value Engine** nativo
   (no depende de datos ni de tener ventaja: convierte el objetivo "maximizar retiros netos" en un número
   calculable y fija la **ventaja mínima rentable** que la investigación debe buscar). En paralelo, que el
   operador decida la compra de datos L1 de NQ/MNQ con estimaciones de coste gratuitas, y rediseñar
   Research A y B como **pruebas únicas prerregistradas** (método ENG-1 R1), no como barridos.

## 2. Current State

### 2.1 Git y entorno (Confirmado)

| Elemento | Estado |
|---|---|
| Rama | `claude/vibrant-mayer-r46s0o`, limpia, igual a `master` (`5b277cb`, 2026-11-27 15:38 −04:00) |
| Historial | 121 commits en `master`; clon no superficial; 0 tags locales y **137 tags en `origin`** (`git ls-remote --tags`), entre ellos los de vuelta atrás `*-pre`, `edge1`, `edge2`, `nqedge-forward-start` |
| Cambios locales | ninguno (`git status` limpio) |
| CI | `.github/workflows/ci.yml`: Windows, uv 0.13.7, Python 3.13, `ruff check src tests scripts`, `pytest -m "not network and not mt5 and not lmstudio and not alpaca and not credentials"` |
| Lint en esta sesión | `ruff check .` → **All checks passed** |
| Tests en esta sesión | ver §12 (suite completa en Linux) |
| Secretos | Windows Credential Manager (keyring); `.env` ignorado; `execution/projectx.py:75-77` lee de entorno (ver FUT-09) |
| Datos reales | **no están en el repo** (`data/cache/` ignorado). Viven en `E:\trading-lab\data` del operador. Aquí solo hay `data/tl3/manifest.json`, `coverage.json` y `tl3_research.db` |

### 2.2 Inventario por áreas (Confirmado, líneas de código)

| Área | Líneas | Qué es | Futuros |
|---|---:|---|---|
| `discovery/` | 31.051 | Motor de investigación: fastbt (numba), compiler/DSL, GA/NSGA-II, campañas, protocolo v2/v3, robustez, edge map, costes v2/v3, calidad de datos, Databento/Dukascopy | Parcial: Databento OHLCV, `futures_roll`, `FuturesCost` |
| `propfund/` | 7.437 | Registro multiempresa (`config/propfund/firms.yaml`, reglas versionadas con fuente), cuentas, costes, router, snapshots, manifiesto protegido | Firmas de futuros con reglas vacías |
| `prop/` | 1.903 | `PropRules` (%), simulador de reto MC diario, guard FTMO, defensa | No apto para futuros (FUT-01) |
| `execution/` | 2.060 | MT5 attach-only (producción), paper, `projectx.py` (dry-run), offsets | ProjectX dry-run |
| `ea_lab/` + `ea_us100*.py` | ~3.900 | Réplica Python del EA v3.2, adaptador NQ, informe | `nq_adapter.py` |
| `tl3/` | 1.415 | Registro append-only de hipótesis, puertas, verificación, avisos | Neutro |
| `cli.py` / `web.py` | 12.392 / 3.141 | 236 comandos `lab`; consola web local | — |
| `ai_trader.py` | 3.980 | Carril discrecional LLM (demo) con gemela aleatoria | CFD |
| `NASDAQ_EDGE_INSTITUTIONAL/` | proyecto aparte | Investigación NQ/MNQ: reglas verificadas Topstep/Apex/Tradeify 50K, OOS-2 sellado, forward NQF-A/B/C, indicador Pine | **Sí**, el más avanzado |

### 2.3 Campañas y carriles activos (Confirmado, `ESTADO.md`)

| ID | Tipo | Estado | Fecha de control | Regla |
|---|---|---|---|---|
| NQF-A / NQF-B / NQF-C | Forward MNQ prerregistrado (tag `nqedge-forward-start`) | **Arranca 2026-11-30** | n = 200: C 2027-08-08, A 2027-09-26, B 2030-10-18 | No tocar; no mirar P&L antes de n |
| EA `us100-ftmo1` | Forward FTMO demo (CFD) | 3 cerradas | n = 30 → 2027-03-16 | No tocar |
| `ai_trader` | Forward demo (CFD) | en marcha | n = 180 → 2027-01-04 | No tocar |
| EDGE-1 / EDGE-2 | Campañas Discovery CFD | cerradas (0 confirmadas) | — | Historia, no reutilizar |
| ENG-1 | Programa de ingeniería | bloque 3 integrado (`85cb477`); C1 rechazada | — | Sus hallazgos siguen abiertos |

## 3. Technical Findings

Hallazgos nuevos con el enfoque futures-first. Los de ENG-1 que afectan a futuros se citan al final.

| ID | Hallazgo | Certeza | Evidencia | Consecuencia |
|---|---|---|---|---|
| **FUT-01** | El simulador de reto multiplica retornos **diarios en %** (`equity *= 1 + r`), sin flotante intradía, sin payouts, sin tarifas, sin bloqueo del trailing por umbral en USD | Confirmado | `src/tradinglab/prop/simulator.py:20-140` | No sirve para Topstep/Apex: su MLL se vigila **en tiempo real con P&L no realizado** y en USD. Hace falta un motor nuevo (ADR-F03) |
| **FUT-02** | Tres representaciones de reglas de firma sin sincronizar: `prop/rules.py` (%), `config/propfund/firms.yaml` (Topstep `profit_target_usd: null`, `needs_verification`) y `NASDAQ_EDGE_INSTITUTIONAL/01_RESEARCH/Prop_Firm_Rules.md` (reglas **verificadas** el 2026-11-25) | Confirmado | `firms.yaml:269-299`; `Prop_Firm_Rules.md §1-2` | La información buena está en Markdown, fuera del registro que lee el código |
| **FUT-03** | Costes de futuros en **Sin datos** en el CostBook (`MNQ/NQ commission_value: null`). El forward NQF usa 0,75 USD/lado por decisión del operador; **no consta** si incluye exchange, clearing y NFA | Confirmado / el desglose, No verificado | `config/propfund/costs.yaml:139-140`; `ESTADO.md §4` | Cualquier EV o backtest de futuros necesita el desglose por firma/plataforma |
| **FUT-04** | El objetivo se llena **al tocar** el precio (`hit_tgt = high >= tgt_p`, `px = tgt_p`). En futuros, tocar un límite no garantiza el fill (cola) | Confirmado | `discovery/fastbt.py:1028-1059` | Sesgo **a favor** en objetivos cercanos. Para futuros: regla "trade-through ≥ 1 tick" o modelo de cola |
| **FUT-05** | El motor mide en **R** y bps del nocional; no dimensiona contratos **enteros** con riesgo en USD | Confirmado | `fastbt.py:1097-1110` | En prop firms el redondeo importa (p. ej. un stop de 50 pt en NQ = 1.000 USD/contrato; con 400 USD de riesgo → 0 NQ, 4 MNQ). Lo cubre el motor de riesgo de futuros (ADR-F02) |
| **FUT-06** | La caché Databento **no guarda `instrument_id`**: los rolls se infieren por saltos > 5σ a las 18:00 ET | Confirmado | `discovery/futures_roll.py:1-60`; ENG-1 C-05 | Rolls frágiles. Solución: guardar `instrument_id`/`raw_symbol` y el esquema `definition` al descargar |
| **FUT-07** | Los futuros se guardan con nombres de CFD (`NQ→US100`, `data/cache/databento/US100_M1.parquet`) | Confirmado | `fetch_databento.py` `ROOT_TO_INTERNAL` | Identidad de datos ambigua (ENG-1 C-04 ya bloquea la mezcla al registrar). El contrato de datos nuevo usa raíz + contrato |
| **FUT-08** | `cme_holidays` trata Memorial, 4 de julio, Labor, Acción de Gracias, Juneteenth y Viernes Santo como **cierre completo** | Confirmado (código) / el horario real de CME, **No verificado** | `discovery/calendars.py:176-212` | Hipotético: en varios festivos de EE. UU. Globex abre una sesión corta; afectaría a estudios overnight y al control de huecos, no a la sesión regular. Verificar contra el calendario oficial de CME |
| **FUT-09** | **No hay adaptador NinjaTrader 8.** ProjectX existe (dry-run por defecto, guard de cuenta simulada), pero lee credenciales de entorno/`.env` | Confirmado | `grep -ri ninjatrader` (solo docs); `execution/projectx.py:62-80` | NT8 es trabajo nuevo; ProjectX debe pasar a keyring antes de usarse |
| **FUT-10** | Sin código ni datos de order flow: `SCHEMAS = ("ohlcv-1m", "ohlcv-1h")` | Confirmado | `fetch_databento.py:79` | Research A no puede empezar sin comprar datos L1 (TBBO/trades) o L3 (MBO) |
| **FUT-11** | Toda la historia NY open de NQ/US100 2010-2026 está contaminada por la lógica del EA (ORB-retest, PD/ON sweep, VWAP ±2σ, FVG, RVOL, 9:35-11:30) | Confirmado | `.orquestador/COLA-NQEDGE-FORWARD.md §1`; `docs/engineering/EDGE_RESEARCH_PLAN.md §1` | Research B en NQ: forward, o hipótesis ortogonales marcadas "contaminación parcial". ES/MES y GC/MGC son campo más limpio |
| **FUT-12** | Datos de futuros disponibles: NQ M1 2010-06 → 2018-12; H1 de NQ/ES/YM/GC 2010 → 2026-11. **Sin datos:** MNQ, MES, MGC; ES/GC en M1; cualquier tick o bid/ask | Confirmado | `TL3_REPORTS/data_manifest.md`; `reports/discovery/f10c-databento.md` | Research B en ES/GC necesita al menos M1 2019+ |
| **FUT-13** | Potencia: con σ ≈ 1-1,9 R por operación, detectar 0,1 R al 80 % exige **619-2.233 operaciones** | Confirmado (ENG-1 E1) | `EDGE_RESEARCH_PLAN.md §0` | A 1 operación/día son 2,5-9 años. El motor EV debe trabajar con **bandas de incertidumbre**, no con la media del backtest |
| **FUT-14** | Duplicidades: dos calendarios (`nyse_calendar.py` del EA y `discovery/calendars.py`), dos libros de costes (`config/costs.yaml`, `config/propfund/costs.yaml`), cuatro auditorías previas (`docs/audit_2026`, `docs/tradinglab2`, `TL3_REPORTS`, `docs/engineering`), `PLAN.md` de 256 KB | Confirmado | rutas citadas | Deuda documental. No se reorganiza ahora; `docs/futures/` es el único punto de entrada nuevo |
| **FUT-15** | Monolito de CLI: `cli.py` 12.392 líneas, 236 comandos | Confirmado | `src/tradinglab/cli.py` | Los comandos nuevos van en un sub-app propio (`lab propecon …`), no en el cuerpo de `cli.py` |
| **FUT-16** | Los carriles CFD (EA, `ai_trader`, tareas programadas) siguen en producción demo | Confirmado | `ESTADO.md §3` | Se **congelan** (sin desarrollo nuevo) y se dejan llegar a sus controles prerregistrados; apagarlos antes no ahorra nada y destruye evidencia |

### 3.1 Auditoría de sesgos del motor (`fastbt.py`, modo `open_next`)

| Sesgo | Resultado | Certeza | Evidencia |
|---|---|---|---|
| Lookahead en la entrada | No: entra en el open de la vela siguiente a la señal | Confirmado | `fastbt.py:946-1003` |
| Lookahead en el stop ATR | No: usa el ATR de la vela de la señal | Confirmado | `fastbt.py:956-959` |
| Same-bar SL/TP | Conservador: el stop gana si los dos se tocan | Confirmado | `fastbt.py:1042-1059` |
| Huecos | Al peor precio (`min(stop, open)`) | Confirmado | `fastbt.py:1043-1050` |
| BE y trailing | Se actualizan al cierre y valen desde la vela siguiente | Confirmado | `fastbt.py:1113-1126` |
| Fills de límite | **Optimista** en el objetivo (FUT-04) | Confirmado | `fastbt.py:1053-1059` |
| Fills parciales, latencia, cola | No se modelan | Confirmado | — |
| Una posición a la vez | Sí; señales con posición abierta se ignoran | Confirmado | docstring `fastbt.py:19-21` |
| Coste de futuros | Comisión + fees por contrato + slippage en ticks; falta → `MissingCostData` ("Sin datos", nunca 0) | Confirmado | `fastbt.py:527-561`; `propfund/costs.py:596-621` |
| Rolls | Heurística (FUT-06); ENG-1 C-05 | Confirmado | `futures_roll.py` |
| Selección/multiple testing | Contador único + v3; ENG-1 D-01/D-02/D-03 abiertos o rediseñados | Confirmado | `AUDIT_FINDINGS.md §1` |
| Survivorship | No aplica a futuros de índice continuos; sí aplicaría a acciones (excluidas) | Estimado | — |

### 3.2 Hallazgos de ENG-1 que siguen pesando en futuros

A-01/A-02 (stops ciegos fuera de `allowed`, corregidos en motor 0.3.0), C-04 (mezcla futuros/CFD al
registrar), C-05 (`detect_rolls` borra saltos reales), D-01/D-02/D-03 (WF sobre IS, PBO sobre el
frontier, DSR de `confirm`), D-07 (Sharpe anualizado con solo días con salida), E-06 (solo OHLCV;
microestructura de stop corto fuera por `cost_r ≤ 0,10`). Detalle en `docs/engineering/AUDIT_FINDINGS.md`.

## 4. Quantitative Findings

| Medida | Valor | Certeza | Fuente |
|---|---|---|---|
| Pruebas registradas | 17.974 | Confirmado | `ESTADO.md` (cabecera) |
| Finalistas que pasan 4 puertas | 0 / 34 | Confirmado | `ESTADO.md §11` |
| NASDAQ_EDGE Fase C (22 variantes NQ) | bruto −0,12 a +0,06 R; neto DEV −0,14 a −0,51 R; coste 0,15-0,36 R por stops de 3,5-8 pt | Confirmado | `PLAN.md` (fila NASDAQ EDGE Fase C) |
| EA `us100-ftmo1` | +0,31 R diseño (479 ops); −0,03 R fuera de periodo | Confirmado | `ESTADO.md §2` |
| C1 USDJPY gotobi | 1.401 eventos, neto 0,43 pips, t HAC 1,02 → rechazada | Confirmado | `L3-c1.json` |
| Operaciones para ver 0,1 R | 619-2.233 | Confirmado | `EDGE_RESEARCH_PLAN.md §0` |
| Coste de un stop corto en NQ | con 0,75 USD/lado MNQ y 1 tick de slippage por lado, un stop de 5 pt (5 pt × 2 USD/pt = 10 USD de riesgo por contrato) cuesta 2·0,75 + 2·0,50 = **2,50 USD = 0,25 R** | Estimado (fórmula; la comisión es la del operador) | `instruments.py:360` (MNQ 0,25 pt = 0,50 USD) |

Lectura: **la microestructura de stop corto en MNQ paga ~0,25 R por operación solo en costes**. Una
hipótesis de order flow con stops de 5 puntos necesita una ventaja bruta mayor que eso para existir.

## 5. Economic Impact

- **Retiros netos esperados hoy: Sin datos.** No hay estrategia validada y el EV de las firmas nunca se
  calculó. Comprar evaluaciones con dinero real sobre las estrategias actuales no tiene base. *Recomendación,
  no hecho medido.*
- El motor EV aporta valor **antes** de tener ventaja: (1) dice qué programa pierde menos o gana más con
  una ventaja dada; (2) calcula la **ventaja mínima rentable** μ\* por programa, que fija el MDE de la
  investigación; (3) mide cuánto EV viene solo de la convexidad de las reglas (sin ventaja), que es frágil y
  puede chocar con los términos de las firmas.
- Coste de datos para Research A: **No verificado** (se obtiene gratis con `metadata.get_cost`, ver
  FUT-B1 en la cola).

## 6. Evidence

Rutas y líneas en §3 y §3.1. Metadatos de los repositorios externos en `01_MATRIZ_TECNOLOGIA.md`
(API de búsqueda de GitHub, 2026-11-27). Manifiestos de plugins en `02_EXTENSIONES_CLAUDE_CODE.md`
(clon superficial de `anthropics/claude-plugins-official`, 2026-11-27).

## 7. Risks

| Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|
| Diseñar sobre reglas de firma caducadas | Alta (cambian a menudo) | Alto | Reglas versionadas con fecha de consulta y caducidad; el motor rechaza reglas vencidas |
| Reabrir NY open en NQ con datos ya vistos | Media | Alto (falso positivo) | ADR-F06: forward o hipótesis ortogonales marcadas |
| Comprar datos L3 caros sin hipótesis que los necesiten | Media | Medio | Empezar por L1 (TBBO/trades) y solo las hipótesis que lo requieren |
| Tocar `discovery/` con campañas que dependen de su versión | Media | Alto (reproducibilidad) | Código nuevo en paquetes nuevos; migraciones con `engine_version` |
| Saturar a OpenCode (DeepSeek V4.1 Flash) con tareas largas | Alta | Medio | Tareas de una sesión, ficheros cerrados, tests con cifras exactas |
| Instalar extensiones que reescriben el comportamiento del agente | Media | Medio | Auditoría en `02_EXTENSIONES_CLAUDE_CODE.md`; instalación solo con aprobación |

## 8. Alternatives

1. **Migrar a un motor externo (NautilusTrader/LEAN) ya.** Rechazado por ahora: no hay ventaja que
   ejecutar y el motor propio está auditado; se decide con el benchmark de la Fase 4.
2. **Ampliar `prop/simulator.py`.** Rechazado: es producción (guard FTMO), en %, y su modelo diario no
   representa el flotante intradía. Motor nuevo y separado.
3. **Barridos GA en futuros.** Rechazado: la potencia no da (FUT-13) y las puertas tienen fallos
   (ENG-1 D-01/D-02/D-03).

## 9. Recommendation

1. Aprobar `03_ARQUITECTURA_FUTURES.md` (ADR-F01 a F10).
2. Arrancar la cola `05_COLA_Y_ROADMAP.md` por **FUT-A** (motor EV) y **FUT-B1** (estimación gratuita de
   costes de datos), que son independientes entre sí.
3. Instalar como mucho **dos** extensiones de Claude Code, y solo tras aprobación (ver
   `02_EXTENSIONES_CLAUDE_CODE.md §6`).

## 10. Implementation Tasks for OpenCode

Ver `05_COLA_Y_ROADMAP.md §3` (IDs FUT-A1…A9, FUT-B1…B3, FUT-D0, FUT-E1, FUT-X1…X3).

## 11. Dependencies

FUT-A no depende de datos. FUT-B2 (instrument_id) depende de una descarga aprobada. Research A
depende de la compra de datos (decisión 5 de `ESTADO.md`). Research B en NQ depende del forward.

## 12. Tests

- `ruff check .` → limpio (esta sesión).
- `pytest` con los marcadores de CI en Linux: resultado en `docs/futures/README.md §4` (se anota al
  terminar la suite; los fallos de entorno de Linux están catalogados en ENG-1 F0-03/F2a).

## 13. Acceptance Criteria

Esta auditoría se acepta si el operador confirma: (a) la lista de campañas activas de §2.3, (b) que los
carriles CFD se congelan sin apagarse (FUT-16) y (c) la prioridad de §9.

## 14. Next Steps

`03_ARQUITECTURA_FUTURES.md` → `04_SPEC_PROP_EV.md` → `05_COLA_Y_ROADMAP.md`.
