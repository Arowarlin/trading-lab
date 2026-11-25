# TradingLab · README completo

> **Laboratorio de investigación y operativa de trading, solo en demo/paper.** Busca ventajas
> (*edge*) reales y netas de costes en CFD (índices, forex y metales en MT5) y en futuros CME, para
> cuentas de fondeo (FTMO, FundingPips, Topstep…), sin engañarse: prerregistro, un contador único
> de pruebas (DSR), holdout sellado y forward.
>
> **Ninguna vista, agente ni script envía órdenes reales.** Como máximo, `READY_DRY_RUN` o DEMO con
> confirmación humana.

**Versión del documento:** 2026-11-25 · rama `master` (`origin/master` = `73fad0e`) ·
`count_tests` **1926** · suite **2000 passed + 1 skipped**

---

## Índice

1. [Qué es y qué no es](#1--qué-es-y-qué-no-es)
2. [Estado actual](#2--estado-actual)
3. [Reglas del proyecto](#3--reglas-del-proyecto)
4. [Arquitectura](#4--arquitectura)
5. [Datos](#5--datos)
6. [Modelo de costes](#6--modelo-de-costes)
7. [Investigación: de la idea al EA](#7--investigación-de-la-idea-al-ea)
8. [Componentes de producción](#8--componentes-de-producción)
9. [Prop firms](#9--prop-firms)
10. [Proyecto NASDAQ_EDGE y forward NQF](#10--proyecto-nasdaq_edge-y-forward-nqf)
11. [Consola gráfica](#11--consola-gráfica)
12. [Trabajo con agentes](#12--trabajo-con-agentes)
13. [Instalación y comandos](#13--instalación-y-comandos)
14. [Rutina diaria y semanal](#14--rutina-diaria-y-semanal)
15. [Historial de ciclos](#15--historial-de-ciclos)
16. [Glosario](#16--glosario)
17. [Documentos de referencia](#17--documentos-de-referencia)

---

## 1 · Qué es y qué no es

**Qué es:**
- Un motor de investigación (`lab discovery`, `lab campaign`, `lab research*`). Genera estrategias,
  las valida con costes reales y separa desarrollo, selección y holdout.
- Un registro honesto de pruebas: cada configuración probada suma al contador `count_tests`, que
  endurece el umbral del DSR.
- Una capa de operativa **demo**: MT5 attach-only, el EA `us100-ftmo1`, el carril `ai_trader`
  (LLM), carriles forward, Prop Fund multiempresa, protección de riesgo de prop firms y TCA.
- Una consola web local y avisos por Telegram o ntfy.

**Qué no es:**
- No opera en real, ni siquiera con una cuenta fondeada.
- No envía órdenes desde Discovery, la web ni los agentes de investigación.
- No usa acciones, ETF ni Alpaca: ese carril está archivado en `legacy/`.
- No descarga datos de pago ni usa proveedores sin contrato.
- No promete ventaja. Mide, y cuando no la encuentra lo dice. Un backtest no es una predicción.

---

## 2 · Estado actual

> La fuente viva es **`ESTADO.md`**, en la raíz: lo primero que se lee. Lo que sigue es una foto del
> 2026-11-25.

### Veredicto: **ninguna ventaja validada todavía**

| Candidato | Evidencia | Estado | Próximo control |
|---|---|---|---|
| **EA `us100-ftmo1`** (v3.2) | +0,31 R por operación en su periodo de diseño (réplica T6, 479 ops). Fuera de periodo (T7, Dukascopy 2013-14 y 2018-21): −0,03 R, **no confirma** | **Incierto**. Es el único que opera (forward FTMO demo, 3 cerradas) | n = 30 → 2027-03-16 · n = 60 → 2027-07-13 · n = 515 → 2032-06-14 |
| **`ai_trader`** | No supera a la regla de tendencia (Δ −0,02 R, IC95 [−0,18; +0,12]). Real +0,05 R frente a +0,30 R simulado; la diferencia está en la salida (stops móviles) | **No concluyente** | Evaluación única a n = 180 → 2027-01-04 |
| **NQF-A/B/C** (NASDAQ_EDGE) | Historia contaminada por el EA; solo vale el forward. Prerregistrado y congelado | **Forward desde el 2026-11-30** | n = 200: C → 2027-08 · A → 2027-09 · B → 2030-10 |
| **EDGE-1** (fábrica de estrategias) | M15/M30/H1/H4 × 7 activos con el motor Discovery | **En marcha** | Informe al cierre de la cola |

**Hipótesis cerradas (TL3):**
- H1 deriva nocturna: `cost_gate`.
- H2 deriva previa al FOMC: no confirma (neto 8,04 bps, LCB −0,60).
- H3 impulso de apertura: `no_power`.
- Fix FX y Asia USDJPY: rechazadas.
- Cambio de mes, rebote D1, Donchian, momentum intradía y NY open GA: `inconclusive`.
- EA fuera de periodo: `holdout_fail`.

### Decisiones del operador pendientes

| # | Decisión | Qué desbloquea |
|---|---|---|
| 2 | ¿Mantener NQF-B? Llegaría a n = 200 hacia 2030 | Foco del forward |
| 3 | Arreglar la **TCA** (slippage siempre 0), cola de producción | Costes de ejecución reales medidos |
| 4 | **E-3**: la protección diaria de FundingPips solo usa la equidad (`propfund/snapshots.py`) | Riesgo correcto en la cuenta CFD-006 |
| 5 | ¿Comprar **NQ/MNQ 2019+** (Databento)? | Futuros reales para NASDAQ_EDGE |
| 6 | **Medir el swap** durante ≥ 20 sesiones | Reabrir hipótesis que duermen posiciones |
| 7 | **Tarifas y reparto** de cada prop firm | Valor esperado neto en Prop Fund |

---

## 3 · Reglas del proyecto

Las reglas completas están en **`AGENTS.md`**. Valen para cualquier persona o agente:

- **Solo paper/demo.** Nunca dinero real. Nunca activar bots ni F13 sin aprobación humana explícita.
- **Ningún agente ejecuta** `lab campaign run`, `research*` ni ningún barrido que sume pruebas sin la
  aprobación explícita del operador **en esa misma sesión**. `lab campaign run` exige
  `--approved-by-operator`. `record-informal` solo lo usa el operador.
- **Secretos:** en Windows Credential Manager (keyring). **No se toca `.env`.**
- **No se borran archivos:** se archiva con `git mv`. Sin push, sin reescribir historial y sin tareas
  programadas salvo autorización.
- **Scripts de administrador:** `scripts/register_tasks_tz.ps1`, `config/schedule.yaml` y los que
  corren con `RunLevel Highest` necesitan aprobación expresa.
- **Componentes de producción** (EA `us100-ftmo1`, forward FTMO, riesgo FTMO, `ai_trader`, Prop
  Fund, `ea_lab`). Todo cambio lleva:
  1. línea base: `lab propfund baseline --reason "..."`;
  2. test de regresión antes/después;
  3. entrada en `docs/CHANGELOG-produccion.md`;
  4. tag `tl2-<id>-pre` antes del primer commit, para poder volver atrás.
- **MT5 attach-only** desde la investigación: solo `copy_rates_*`, `history_*` y lectura de estado.
- **Datos ausentes → "Sin datos".** No se inventan precios, offsets ni históricos.
- **Cierre de cada bloque:** tests sintéticos, `ruff`, `pytest`, `lab doctor`, README/PLAN y un
  commit pequeño. Después, resumen a Telegram con el formato **Hecho / 1..N / Aviso / Siguiente**.
- **Coordinación entre sesiones (TL3-E):**
  - lock antes de escribir ficheros compartidos (`orq_lock`);
  - commits solo de las rutas propias (nunca `git add -A`);
  - una sola cola activa por proyecto.
- **Verificación previa (TL3-E):** antes de cualquier prueba que cuente, **otra sesión** comprueba la
  conformidad con el prerregistro (unidades, constantes, muestra, horas y frecuencia), nunca el
  resultado. Lista de comprobación en `docs/VERIFICACION.md`.

---

## 4 · Arquitectura

```text
trading-lab/
├─ src/tradinglab/           Código (paquete instalable, CLI `lab`, más de 200 comandos)
│  ├─ discovery/             Motor de investigación: snapshots, costes v2, fastbt, compilador DSL,
│  │                         GA, fitness, campañas, protocolo v2, potencia, SPA, export MQL5
│  ├─ campaign.py            Campañas registradas (universo por coste, familias tsmom/st_reversal/
│  │                         vol_breakout/calendar, holdout sellado por hash)
│  ├─ research.py, intraday.py, swing.py, horizons.py   Barridos de investigación (con aprobación)
│  ├─ tl3/                   Registro TL3: hipótesis, experimentos, uso de muestra, puertas
│  │                         (potencia, coste, identidad, holdout), costs.py (swap), verify.py,
│  │                         avisos, report.status_table
│  ├─ ea_us100_engine.py     Réplica Python del EA v3.2 (M5 NY, BID/ASK, SL primero si SL y TP
│  │                         caen en la misma barra)
│  ├─ ea_us100.py, ea_parity.py, ea_forward.py, ea_horizon.py, ea_registry.py, ea_lab/
│  ├─ execution/             MT5 attach-only (mt5.py), paper broker (paper.py)
│  ├─ tca.py, slippage_probe.py, mt5_fills.py, reconciliation.py   Ejecución y costes reales
│  ├─ prop/                  Reglas de firma (rules.py), simulador Monte Carlo (simulator.py),
│  │                         protección de riesgo (guard.py), defensa y overlay
│  ├─ propfund/              Prop Fund multiempresa: firmas, cuentas, costes, snapshots, router,
│  │                         riesgo, manifiesto protegido
│  ├─ ai_trader.py, ai_*.py  Carril discrecional LLM (demo) con gemela aleatoria
│  ├─ lifecycle.py, drift.py, forward_intraday.py, killswitch.py, guardian.py, risk*.py
│  ├─ web.py + webui/        Consola local
│  ├─ telegram.py, alerts.py, heartbeat.py   Avisos y salud
│  ├─ orq_lock.py            Locks atómicos entre sesiones de agentes
│  └─ cli.py                 Punto de entrada `lab`
├─ config/                   YAML: firmas, cuentas, costes, motores, EA, discovery/engine.yaml,
│                            plantillas, campañas, propfund/
├─ data/                     lab.db, discovery.db, tl3/tl3_research.db, cachés (no se borran)
├─ docs/                     Documentación operativa, CHANGELOG de producción, VERIFICACION.md
├─ reports/                  Informes de EA, discovery y ai_trader
├─ TL3_REPORTS/              Informes del ciclo TL3 (resultados, planes, diagnósticos)
├─ NASDAQ_EDGE_INSTITUTIONAL/ Proyecto NQ/MNQ: investigación, datos, forward NQF
├─ exports/                  EAs exportados (MQL5) para el Strategy Tester; no se despliegan solos
├─ .orquestador/             Colas de trabajo de agentes, resultados, locks (fuera de git;
│                            las colas se versionan con `git add -f`)
├─ legacy/                   Código archivado con `git mv`; no se ejecuta
├─ AGENTS.md                 Reglas para agentes
├─ ESTADO.md                 Mapa único del proyecto
└─ README.md / PLAN.md       Resumen técnico e historial de bloques
```

**Bases de datos:**
- `data/lab.db`: operativa, `informal_trials`, fills, TCA, `ai_trades`, órdenes demo y registro de
  campañas.
- `data/discovery.db`: campañas, estrategias, evaluaciones, validaciones y lecturas de holdout.
- `data/tl3/tl3_research.db`: hipótesis, experimentos, uso de muestra, verificaciones y avisos.
  Solo se añaden filas; nunca se modifican.

---

## 5 · Datos

| Fuente | Qué hay | Uso | Notas |
|---|---|---|---|
| **MT5 FTMO** (attach-only) | M5/H1/H4 de CFD (`US100.cash`, `US500.cash`, `US30.cash`, XAUUSD, FX…), spreads, fills demo | Operativa demo, coste del bróker, validación | Hora del servidor ≠ UTC: se corrige con `mt5_offset.json` |
| **Dukascopy** | M1 2011-09 → 2026-11 de US100, US500, US30, XAUUSD, EURUSD, GBPUSD y USDJPY | Historia larga para investigación | **Solo bid**: el spread se toma del bróker. US100 tiene pocas velas nocturnas antes de 2018 |
| **Databento** (GLBX) | NQ M1 2010-06 → 2018-12 y H1 de varios símbolos | Futuros CME reales | Falta 2019+, una compra pendiente de decisión |
| **FRED** | Tipos diarios (swap histórico), calendario | Modelo de swap v2 | — |
| **Calendarios** | NYSE (festivos y cierres tempranos), FOMC, noticias de primera publicación (ALFRED) | Exclusiones y filtros | — |

Cobertura por año: `TL3_REPORTS/data_coverage.md`. Calidad (huecos, sesiones válidas):
`lab discovery data-check`.

---

## 6 · Modelo de costes

Todo resultado es **neto**. El motor Discovery usa la versión de coste **v2**:

| Componente | Cómo se modela | Dónde |
|---|---|---|
| **Spread** | Si hay ASK, histórico escalado; si no (Dukascopy), **mediana por hora del bróker**. El p75 se usa en el estrés | `config/discovery/engine.yaml`, perfiles `us*_spread_profile_ny5m` |
| **Comisión** | Por cuenta: CFD-001 (FTMO) y CFD-006 (FundingPips) | Coste del bróker / `config/costs.yaml` |
| **Swap** | `historical`: tipo de FRED más un margen calibrado. Un swap positivo **no cuenta** como ventaja (`swap_credit: false`) | `engine.yaml`, `config/propfund/swap.yaml` |
| **Slippage** | Supuesto por instrumento (US100 1,0 pt; US500 0,5; US30 2,5; XAUUSD 0,15; FX 0,5 pip; USDJPY 0,005) | `engine.yaml` → `assumed_slippage` |
| **Puerta de coste** | Coste ida y vuelta / distancia del stop ≤ **0,10 R** (mediana) | `engine.yaml` → `cost_r_max` |

**Conversión del swap** (`tl3/costs.py`):
- `swap_mode` 5 (interés anual en %): bps/noche = |tasa| / 100 / 365 × 10⁴. Por ejemplo, 7,33 % →
  2,008 bps.
- `swap_mode` 1 (puntos): |tasa| × punto / precio × 10⁴.
- La noche del día triple (viernes, convención MT5 5) cuenta ×3.

**Ejecución real (TCA):** hoy registra el slippage siempre en 0, porque guarda el precio de envío
como precio de señal (`execution/mt5.py:772-783`). El slippage real entre decisión y ejecución
medido aparte tiene una mediana de **0,44 bps**. El arreglo es un cambio de producción pendiente.

---

## 7 · Investigación: de la idea al EA

### 7.1 Discovery (el motor principal)

```text
spec / plantilla → register (borrador) → preflight (potencia) → feasibility (operaciones y coste,
sin PnL) → approve (operador) → run (IS + OOS-1) → results → robustness / perturb / power →
confirm (OOS-2, una sola vez) → export-mql5 (EA para el Strategy Tester)
```

- **Generación:** algoritmo genético sobre un DSL (máximo 12 nodos, profundidad 4) o rejilla.
  Perfiles: `small` 40×10, `medium` 100×25 y `large` 200×60 (población × generaciones).
- **Plantillas** en `config/discovery/templates/`:
  - existentes: `asia_range_reversion`, `d1_extension_reversion`, `donchian_vol_h4`,
    `fix_reversal`, `intraday_momentum_close` (+v2), `ny_open_vol_filter`,
    `session_breakout_htf`, `ts_momentum_d1`, `turn_of_month`;
  - EDGE-1 añade: `trend_pullback_mtf`, `vol_squeeze_breakout`, `london_breakout` y
    `st_reversal_idx`.
- **Validación por timeframe** (congelada el 2026-11-21):

  | TF | Operaciones mínimas IS | Mínimas por pliegue | Pliegues |
  |---|---:|---:|---:|
  | M5 | 100 | 15 | 4 |
  | M15 | 60 | 10 | 4 |
  | M30 | 50 | 8 | 4 |
  | H1 | 40 | 6 | 4 |
  | H4 | 25 | 4 | 3 |
  | D1 | 15 | 3 | 3 |

- **Robustez:**
  - walk-forward con eficiencia ≥ 0,3;
  - PBO;
  - Monte Carlo y bootstrap;
  - `perturb`: ruido, retrasos de entrada y salida, saltos de ejecución (no suma al contador);
  - simulación de reto en CFD-001 y CFD-006.
- **Segmentos:** IS (desarrollo), OOS-1 (selección) y **OOS-2 sellado**, que se lee una sola vez con
  `confirm`.
- **EA:** `lab discovery export-mql5 --strategy-id N --account CFD-001` genera un `.mq5` con los
  límites diario y máximo de la cuenta. Se prueba en el Strategy Tester; **nunca** se despliega solo.

### 7.2 Campañas registradas (`lab campaign`)
`universe → n-total → fetch → plan → register → status → run`.
- Universo por coste: un activo es elegible si `cost_atr` < 0,05.
- Familias expresadas en horas o días, escaladas al timeframe.
- `N_total` se escribe **antes** de ejecutar, y el holdout queda sellado con un hash de los datos
  exactos.

### 7.3 Registro TL3 y puertas
- **Hipótesis** H-2026-001…012, con estados `draft`, `rejected`, `inconclusive` y `validated`. Solo
  se añaden filas: un cambio de estado es una fila hija.
- **Puertas:**
  - potencia: MDE = 2,49·σ/√n frente a δ;
  - coste: bruto esperado ≥ 2 × coste;
  - identidad;
  - holdout.
- **Verificación previa:** `registry.require_verified(hipótesis, hash_código)` antes de cualquier
  ejecución que cuente.
- **Avisos que viajan:** `scripts/tl3_warnings.py list|render <subject>`. Solo se añaden; aparecen en
  `status_table`.

### 7.4 Contador de pruebas y DSR
`count_tests` = suma de `n_total` de discovery y de campañas + `informal_trials` (miradas informales
registradas por el operador). Cada configuración probada sube el umbral del DSR para todas. **No se
modifica a mano.** Para registrar una prueba manual (solo el operador):

```powershell
E:\trading-lab\.venv\Scripts\lab.exe learning record-informal --n 1 --reason "ID: descripción" --approved-by-operator
```

---

## 8 · Componentes de producción

| Componente | Qué es | Dónde |
|---|---|---|
| **EA `us100-ftmo1`** ("NASDAQ NY OPEN PRO", v3.2) | Confluencia en la apertura de NY: rango de apertura y retest, barridos de PDH/PDL/ON, FVG, VWAP ± 2σ, RVOL. Entradas de 9:35 a 11:30, cierre a las 15:45, RR 2, BE a 1R. Réplica Python vela a vela | `integrations/mt5/us100_ftmo1/`, `ea_us100_engine.py`, `docs/ea_us100_ftmo1.md` |
| **Forward FTMO** | EA y carriles en cuenta demo, attach-only, comparados vela a vela con el motor | `ea_forward.py`, `lifecycle.py`, `drift.py` |
| **`ai_trader`** | Carril discrecional con LLM (scalping e intradía; cierre forzoso a las 12:00 NY en scalping), stops móviles y gemela aleatoria para comparar | `ai_trader.py`, `config/ai_trader.yaml` |
| **Prop Fund** | Registro multiempresa de firmas, cuentas, costes, snapshots y router de capital | `propfund/`, `config/propfund/` |
| **Riesgo de prop firm** | Reglas, simulador de reto y protección diaria y máxima | `prop/` |
| **`ea_lab`** | Laboratorio del EA | `ea_lab/` |

**Puntos de vuelta atrás** (tags): `tl2-<id>-pre` antes de cada cambio de producción, por ejemplo
`tl2-diario-pre`. Cierres de ciclo: `tl3-ciclo1` … `tl3-ciclo1e`, `tl2-diario`,
`nqedge-forward-start`.

---

## 9 · Prop firms

- **Firmas modeladas:** FTMO (2-Step y 1-Step), FundingPips (2-Step y trial) y Topstep, entre otras
  (`config/propfund/firms.yaml`, `config/prop.yaml`).
- **Simulador** (`prop/simulator.py`): `monte_carlo` (una fase) y `monte_carlo_program` (varias
  fases). Aplica los límites diario y máximo (estático o trailing), el objetivo y los días mínimos.
  Usa datos **diarios**, así que subestima el riesgo intradía.
- **Línea base sin ventaja** (`TL3_REPORTS/propfund_zero_edge.md`): con ventaja cero, b = 2 y
  riesgo del 0,5 %, P(financiada) es ≈ 17 % en FTMO 2-Step, ≈ 30 % en FTMO 1-Step y ≈ 22 % en
  FundingPips. **Una estrategia real solo aporta si supera esta línea base** con la misma regla de
  riesgo.
- **TL2-DIARIO** (2026-11-25): corregido el suelo diario "mayor de balance o equidad" en el simulador
  y en la protección de riesgo. El modo FTMO no cambia (15/15 casos idénticos). Queda pendiente E-3
  (`propfund/snapshots.py`).

---

## 10 · Proyecto NASDAQ_EDGE y forward NQF

- **Carpeta:** `NASDAQ_EDGE_INSTITUTIONAL/`, con investigación (fase A), datos (fase B), backtest
  histórico (fase C, ejecutado, registrado y **contaminado por el EA**), forward (`04_FORWARD/`) e
  indicador Pine v6 (`NO EDGE VALIDATED`).
- **Variantes congeladas** (`tools/forward_models.py`, con hash):
  - **NQF-A:** rango de apertura de 15 min, entrada al cierre de la ruptura, objetivo 2R;
  - **NQF-B:** barrido del máximo o mínimo nocturno y cierre de vuelta dentro, objetivo VWAP;
  - **NQF-C:** reversión desde VWAP ± 2σ al VWAP.
- **Reglas:**
  - MNQ con 150 USD de riesgo por operación;
  - comisión de **0,75 USD por contrato y lado** (dato del operador);
  - slippage de 1 tick, con estrés de 2 y 4;
  - sin entradas en días FOMC; cierre 5 min antes de un Tier 1.
- **Evaluación única** a n = 200 operaciones por variante, con α = 0,05/3. Antes **no se mira**
  ningún resultado. El operador registra 3 pruebas antes de evaluar.
- **Registro diario**, desde el 2026-11-30, después del cierre de NY y con MT5 abierto:

```powershell
E:\trading-lab\.venv\Scripts\python.exe E:\trading-lab\NASDAQ_EDGE_INSTITUTIONAL\tools\forward_daily.py --commission-side-usd 0.75
```

(La ayuda del script usa 1,25 como ejemplo: **no** es la comisión.)

---

## 11 · Consola gráfica

```powershell
E:\trading-lab\.venv\Scripts\lab.exe web --no-open --port 8420
```

Después se abre `http://127.0.0.1:8420`. Muestra, entre otras cosas:
- **Discovery:** campañas, estrategias, mapa de edge y sugerencias (`/api/discovery/*`);
- TCA;
- estado de bots, cuentas y Prop Fund;
- alertas.

Solo lectura y demo: la consola no envía órdenes reales.

---

## 12 · Trabajo con agentes

| Rol | Hace |
|---|---|
| **Operador** (humano) | Decide, aprueba campañas y cambios de producción, registra pruebas (`record-informal`) y hace push |
| **Claude** | Audita, escribe las especificaciones y las colas, y revisa los resultados contra el prerregistro |
| **OpenCode** | Ejecuta las colas de `.orquestador/` de principio a fin, con un commit por bloque |

- **Colas:** un fichero `COLA-*.md` por bloque de trabajo, con reglas, bloques y cierre. La plantilla
  está en `.orquestador/PLANTILLA-COLA.md`. Los cierres se escriben en `.orquestador/RESULTADO-*.md`.
- **Locks:**
  ```powershell
  E:\trading-lab\.venv\Scripts\python.exe scripts\orq_lock.py status
  ```
  Recursos: `readme-plan`, `changelog-produccion`, `protected-manifest`, `tl3-registry`,
  `pytest-full` y `proyecto-<nombre>`.
- **Mapa:** `ESTADO.md` es la única fuente del estado. Una cola nueva solo se abre si responde a una
  decisión pendiente o a una fecha de control.
- **Errores que se repiten** y conviene comprobar primero: conversiones de unidades (swap en % sin
  /100, spread en puntos usado como precio), muestras que cambian entre ejecuciones, umbrales que se
  apartan del prerregistro y escritura de ficheros con PowerShell `>`, que deja UTF-16.

---

## 13 · Instalación y comandos

**Requisitos:** Windows, Python ≥ 3.12, terminal MT5 (demo) para attach-only y el entorno virtual
`.venv` del repositorio. El paquete se llama `tradinglab` (`pyproject.toml`) y expone el comando
`lab`.

```powershell
# Salud del laboratorio
E:\trading-lab\.venv\Scripts\lab.exe doctor
E:\trading-lab\.venv\Scripts\lab.exe propfund verify

# Discovery
E:\trading-lab\.venv\Scripts\lab.exe discovery data-check
E:\trading-lab\.venv\Scripts\lab.exe discovery edge-map
E:\trading-lab\.venv\Scripts\lab.exe discovery suggest --account CFD-001
E:\trading-lab\.venv\Scripts\lab.exe discovery results <campaign_id>
E:\trading-lab\.venv\Scripts\lab.exe discovery export-mql5 --strategy-id <id> --account CFD-001

# EA
E:\trading-lab\.venv\Scripts\lab.exe ea status us100-ftmo1
E:\trading-lab\.venv\Scripts\lab.exe ea parity us100-ftmo1 --since 2026-11-23

# Contador
E:\trading-lab\.venv\Scripts\lab.exe research-trials --limit 5

# Avisos
E:\trading-lab\.venv\Scripts\lab.exe telegram send --file resumen.txt
E:\trading-lab\.venv\Scripts\lab.exe alerts send

# Tests y estilo
E:\trading-lab\.venv\Scripts\python.exe -m ruff check .
E:\trading-lab\.venv\Scripts\python.exe -m pytest -q
```

Las órdenes que **aprueban o ejecutan** campañas (`discovery approve`, `discovery run`,
`campaign run`, `confirm`) llevan `--approved-by-operator` y solo se lanzan con la autorización del
operador.

---

## 14 · Rutina diaria y semanal

**Diaria:**
1. `lab doctor`. El aviso preexistente de "Frescura" es de datos de mercado.
2. Desde el 2026-11-30: registro forward de NQF (comando en §10), después del cierre de NY.
3. Revisar Telegram: avisos de las colas y del heartbeat.

**Semanal:**
1. Contar operaciones del forward (EA, `ai_trader` y NQF) **sin mirar el rendimiento** hasta su
   fecha de control.
2. Revisar `ESTADO.md`: decisiones pendientes y fechas.
3. Hacer push de lo cerrado (lo hace el operador).

**Fechas de control:**
- 2027-01-04: `ai_trader` (n = 180);
- 2027-03-16 y 2027-07-13: EA (n = 30 y n = 60);
- 2027-08 y 2027-09: NQF-C y NQF-A (n = 200).

---

## 15 · Historial de ciclos

| Ciclo | Qué dejó |
|---|---|
| **TL2** (F0-F4, CNT, EA, NOCHE, NQ) | Costes v2 BID/ASK, protocolo v2 (desarrollo → holdout único → SPRT), contador v2, EA "incierto", fuera de instrumento "no transfiere", `ai_trader` sin ventaja frente a la gemela |
| **TL3 ciclo 1** (T0-T11) | Manifiesto de datos, registro append-only de 11 hipótesis, escalera bruto → neto, réplica del EA, puertas de H1 y H3 |
| **TL3-B/C** | T7 no confirma; T8 corregido (swap 100× mayor) y no confirma; T5-bis: la simulación es optimista en la salida |
| **TL3-D** | Protecciones de unidades y codificación, línea base sin ventaja, mapa de cobertura, planes de potencia de `ai_trader` y del EA, diagnóstico de la TCA |
| **TL2-DIARIO** | Suelo diario de FundingPips corregido en el simulador y en la protección de riesgo |
| **NQEDGE-FORWARD** | Tres variantes congeladas y prerregistradas para forward |
| **TL3-E** | Locks entre sesiones, verificación previa (NQF: Conforma) y avisos que viajan |
| **EDGE-1** | Fábrica de estrategias M15/M30/H1/H4 × 7 activos (en marcha) |

Detalle completo en `PLAN.md` y `.orquestador/RESULTADO-*.md`.

---

## 16 · Glosario

| Término | Significado |
|---|---|
| **R** | Resultado en múltiplos del riesgo inicial (distancia al stop) |
| **Neto** | Después de spread, comisión, swap y slippage |
| **IS / OOS-1 / OOS-2** | Desarrollo / selección / holdout sellado (una sola lectura) |
| **Holdout** | Tramo de datos que no se mira hasta la decisión final |
| **Forward** | Datos nuevos, posteriores al prerregistro: la única prueba limpia |
| **Prerregistro** | Reglas, muestra y criterio escritos **antes** de ver resultados |
| **MDE** | Efecto mínimo detectable con potencia del 80 %: 2,49·σ/√n |
| **LCB95** | Cota inferior del IC95 (bootstrap) |
| **DSR** | Deflated Sharpe Ratio: corrige por el número de pruebas (`count_tests`) |
| **PBO** | Probabilidad de sobreajuste del backtest |
| **`cost_r`** | Coste ida y vuelta dividido por la distancia del stop |
| **Attach-only** | Conexión a MT5 solo para leer; nunca para operar |
| **Sin datos** | El dato no existe o no está verificado; nunca se inventa |
| **Contaminado** | Datos que ya influyeron en el diseño (p. ej. 2021-26 para la lógica del EA) |

---

## 17 · Documentos de referencia

| Qué | Fichero |
|---|---|
| Estado vivo | `ESTADO.md` |
| Reglas para agentes | `AGENTS.md` |
| Resumen técnico | `README.md` |
| Historial de bloques | `PLAN.md` |
| Cambios de producción | `docs/CHANGELOG-produccion.md` |
| Verificación previa | `docs/VERIFICACION.md` |
| Arquitectura y dependencias | `docs/arquitectura.md`, `docs/dependencias.md` |
| Campañas y holdout | `docs/campanas.md`, `docs/holdout.md` |
| EA | `docs/ea_us100_ftmo1.md`, `reports/ea/` |
| Resultados TL3 | `TL3_REPORTS/TL3_RESULTS_CICLO1.md` |
| Planes de forward | `TL3_REPORTS/ea_forward_monitor_plan.md`, `TL3_REPORTS/ai_trader_power_plan.md` |
| Prop firms | `TL3_REPORTS/propfund_zero_edge.md`, `TL3_REPORTS/tl2_diario_inventario.md` |
| TCA | `TL3_REPORTS/tca_diagnostico.md` |
| NASDAQ_EDGE | `NASDAQ_EDGE_INSTITUTIONAL/README.md`, `04_FORWARD/prerregistro.md` |
| Fábrica de estrategias | `.orquestador/COLA-EDGE-1.md`, `TL3_REPORTS/edge1_*.md` |

---

*TradingLab mide, documenta y valida. No promete rentabilidad. Solo demo/paper.*
