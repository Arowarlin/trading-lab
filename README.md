# TradingLab

Laboratorio de trading **solo demo/paper** para cuentas de fondeo CFD y
futuros: índices, forex y metales en MT5; futuros CME cuando hay proveedor de
datos. Los agentes y la investigación trabajan únicamente sobre ese universo.
No hay acciones, ETF, Alpaca ni carril de renta variable.

> **Regla del proyecto:** ninguna vista, agente o script envía órdenes reales.
> El máximo es `READY_DRY_RUN` o DEMO con confirmación humana. La investigación
> (Discovery) nunca opera.

## 1 · Estado real (2026-11-25)

| Área | Estado |
|---|---|
| Discovery TL2 | Costes v2 (BID/ASK, spread por barra, swap), protocolo v2 (desarrollo → holdout único → SPRT), familias multi-instrumento y contador `count_tests` = 1894. |
| EA `us100-ftmo1` | Backtest fuerte (478 ops, +0,3104 R, LCB95 0,1682, DSR 0,99936), pero **INCIERTO**: holdout natural n=2 y forward n=1. |
| Fuera de instrumento | US500 y US30 **no transfieren** la lógica v3.2: exp −0,0229 R / LCB −0,1731 y exp +0,0692 R / LCB −0,0382. |
| `ai_trader` | **No se distingue del azar** frente a su gemela: Δ +0,3141 R, IC95 [−0,0686; +0,7060], n=42. |
| Hipótesis cerradas | Fix de Londres (el coste elimina el edge), cambio de mes (0 finalistas), rebote D1 (sin edge bruto). |
| Forward | Solo demo, attach-only. El EA y los carriles forward no se tocan desde la investigación. |

Veredictos completos: `reports/ea/us100-ftmo1-v2.md`,
`reports/ea/us100-ftmo1-fuera-de-instrumento.md`,
`reports/ea/us100-ftmo1-reto-contraido.md`, `reports/ai_trader/vs-gemela.md`.

## 2 · Mapa de módulos

```text
src/tradinglab/
  discovery/          Motor de investigación: snapshots, costes v2, fastbt,
                      compiler, fitness, campañas, protocolo v2, basket,
                      futuros ajustados, potencia y SPA.
  ea_us100_engine.py  Réplica Python del EA v3.2 (BID/ASK, M5 NY, reglas).
  ea_us100.py         Setfile, caché M5, barrido y filtros del EA.
  ea_parity.py        Paridad motor vs MT5 y actualización de caché sin barra
                      en curso.
  execution/          MT5 attach-only, paper broker y utilidades de ejecución.
  propfund/           Registro multiempresa: firmas, cuentas, costes,
                      snapshots y router de capital.
  prop/               Reglas de firma, simulador de reto y guard.
  ai_trader.py        Carril discrecional LLM (demo) con gemela aleatoria.
  web.py + webui/     Consola local (solo demo/paper).
  cli.py              Punto de entrada `lab` (219 comandos).
legacy/               Código archivado con `git mv`; no se ejecuta.
config/               YAML de firmas, cuentas, costes, motores y EA.
docs/                 Documentación operativa y auditorías.
.orquestador/         Colas de trabajo, resultados y auditoría TL2.
```

## 3 · Flujo de una campaña de Discovery

1. **Spec YAML** con hipótesis, plantilla, familia, segmentos, costes,
   primaria y `plausible_edge_r`.
2. **`lab discovery register --spec ...`** crea un borrador; no aprueba.
3. **`lab discovery preflight --spec ...`** valida población, DSL y potencia
   (MDE frente a δ).
4. **`lab discovery feasibility --spec ...`** comprueba operaciones, pliegues
   y `cost_R` sin calcular PnL.
5. **Aprobación humana explícita** (`lab discovery approve`). Sin ella, el
   guard bloquea cualquier rendimiento.
6. **`lab discovery run`** ejecuta IS y OOS-1 (desarrollo). No lee OOS-2.
7. **`lab discovery results`** muestra IS/OOS-1; el holdout OOS-2 se abre una
   sola vez con `lab discovery confirm`, y solo para la primaria.
8. **Protocolo v2:** LCB de desarrollo, meseta ≥ 0,6, deriva ≥ percentil 90 y
   decisión de holdout con consistencia. El SPRT decide en forward.

Nunca se registra, aprueba ni ejecuta una campaña sin autorización del
operador en esa misma sesión. `record-informal` solo lo usa el operador.

## 4 · Reglas de seguridad

- **Demo/paper solamente.** Prohibido operar en real, activar bots o F13 sin
  aprobación humana explícita.
- **Secretos en Windows Credential Manager.** No se lee ni se escribe `.env`.
- **No borrar archivos.** Se archiva con `git mv`; nunca `rm`.
- **No push, no reescribir historial, no tareas programadas** sin
  autorización.
- **MT5 attach-only:** solo `copy_rates_*`, `history_*` y lectura de estado.
  Nunca crear, modificar ni cerrar órdenes desde la investigación.
- **Componentes de producción** (EA `us100-ftmo1`, forward FTMO, riesgo FTMO,
  `ai_trader`, Prop Fund, `ea_lab`): baseline, test de regresión, changelog y
  tag `tl2-<id>-pre` antes de tocar.
- **Datos ausentes:** se escribe **Sin datos**; no se inventan precios,
  offsets ni históricos.
- **`count_tests`** es un contador único de pruebas; no se modifica a mano.

## 5 · Comandos útiles

```powershell
# Estado y salud
.\.venv\Scripts\lab.exe doctor
.\.venv\Scripts\lab.exe propfund verify

# Discovery
.\.venv\Scripts\lab.exe discovery preflight --spec .orquestador/specs/<spec>.yaml
.\.venv\Scripts\lab.exe discovery feasibility --spec .orquestador/specs/<spec>.yaml
.\.venv\Scripts\lab.exe discovery results <campaign_id>

# EA
.\.venv\Scripts\lab.exe ea status us100-ftmo1
.\.venv\Scripts\lab.exe ea parity us100-ftmo1 --since 2026-11-23

# Contador y presupuesto
.\.venv\Scripts\lab.exe research-trials --limit 5
```

## 6 · Documentación

- `docs/CHANGELOG-produccion.md`: cambios en componentes de producción.
- `docs/PLAN.md`: plan y fases.
- `docs/campanas.md`: flujo de campañas y holdout.
- `docs/ea_us100_ftmo1.md`: EA, setfile y forward.
- `docs/arquitectura.md`: arquitectura y dependencias.
- `.orquestador/tl2-audit/`: auditoría TL2, mapa y arquitectura objetivo.
- `.orquestador/RESULTADO-*.md`: cierre de cada bloque de trabajo.
- `docs/README-historico.md`: README anterior (histórico).

## 7 · Alcance

- **CFD:** US100, US500, GER40, XAUUSD, EURUSD, GBPUSD, USDJPY.
- **Futuros:** NQ, MNQ, GC, MGC cuando exista proveedor intradía.
- **Cuentas:** `config/propfund/accounts.yaml` (CFD-001/002 y plantillas
  FUT-*). FTMO demo/trial y Topstep en `config/accounts.yaml`.
- **Datos:** MT5 attach-only para precios, spreads y barras; Yahoo solo como
  caché macro, nunca para tickers de acciones.

TradingLab mide, documenta y valida. No promete rentabilidad. Los resultados
de backtest no son una predicción.

## 8 · Estado de las colas TL2

| Cola | Estado |
|---|---|
| TL2 F1b/F2 (C1-C4, T20-T24, A1) | Cerrada; contador, potencia, primaria, holdout y SPRT. |
| TL2 F3/F4 (T41, T42, T30-T32, P4) | Cerrada; EA INCIERTO, ai_trader sin ventaja, cesta v2, futuros ajustados y specs v2. |
| TL2 CNT | Contador v2 = `n_total`; `count_tests` 1894. |
| TL2 EA (E1-E3) | Caché sin barra en curso, paridad 1/1, fuera de instrumento "no transfiere" y P(pasar) contraída. |
| TL2 NOCHE3 (N1-N4) | N1 reglas oficiales y P(pasar); N2 código muerto; N3/N4 en curso. |
| TL2-DIARIO | Suelo diario `higher_of_balance_or_equity` corregido en `prop/simulator.py` y `prop/guard.py`; identidad `balance`/`equity` y P(diario) FundingPips a 0; tag `tl2-diario`. |

Los cierres están en `.orquestador/RESULTADO-*.md` y los informes en
`reports/`. La cola del EA no cambió el motor ni el setfile.

## 9 · Qué no hace TradingLab

- No opera en real, ni siquiera con una cuenta fondeada.
- No envía órdenes desde Discovery, la web o los agentes de investigación.
- No usa acciones, ETF ni Alpaca; ese carril está archivado en `legacy/`.
- No descarga datos de pago ni usa proveedores sin contrato.
- No promete ventaja: mide, y cuando no la encuentra lo dice.

## 10 · Convenciones para agentes

- Leer `AGENTS.md` antes de tocar código.
- Un bloque = tests sintéticos, `ruff`, `pytest`, `lab doctor`, docs y commit
  pequeño.
- Si faltan datos: **Sin datos**. No se inventan precios ni offsets.
- Los cambios en producción llevan baseline, regresión y changelog.
- Al cerrar un bloque, resumen a Telegram (o ntfy) y **PARA** si la cola lo
  pide.

## 11 · TL3 ciclo 1 (2026-11-25)

- Manifiesto de datos y cargador con comprobación de granularidad/clase;
  copias de futuros en `data/tl3/futures/`.
- Registro append-only `data/tl3/tl3_research.db` con 11 hipótesis, candados
  de potencia/coste/identidad y umbrales con hash.
- `ai_trader` frente a su gemela recalculada con M1: IA 0,2953 R, gemela
  0,2594 R, tendencia 0,3179 R; Δ vs tendencia −0,0225 R, IC95
  [−0,183; +0,121] → **no concluyente**.
- Réplica EA v3.2: 479 ops, +0,3104 R; el corto pierde en 2023 (−0,1368 R).
- T7 (EA Dukascopy 2012-2021) **no confirma** (374 ops, −0,0296 R, LCB −0,1753);
  T8 (H2 FOMC) **no confirma** (117 eventos, neto 8,04 bps, LCB −0,60).
- H1 nocturna: **rejected: cost_gate** (3,1-3,9 bps/noche, 2× > 3,5);
  H3 sin potencia (MDE 0,173 > 0,12).
- `count_tests` = 1897.

### Cierre 1e · TL3-D (2026-11-25)

- D1: swap 2,008 bps/noche, `nights(fecha)`, codificación UTF-8 y `add_status`/`status_table`.
- D2: línea base sin ventaja; FundingPips no fiable por el simulador anterior
  (`max(initial, day_start)`), corregido en TL2-DIARIO `020b41b`.
- D3: cobertura de datos; US100 2012-2021 = 1116 sesiones válidas frente a ~1128,
  0 en 2012/2016/2017.
- D3b: T5-bis con 12 TP / 13 SL / 23 otro y 23/48 coincidencias; FundingPips
  30.672/45.000 caminos afectados con el código anterior, 0 con el corregido.
- D4: plan de potencia de `ai_trader`; n=180 (Δ_t 177), evaluación única estimada
  ~2027-01-04; H-2026-012 `draft`.
- D5: forward del EA con 3 cerradas; T6 sd 1,9173; n 237/515; puntos 30/60/515.
- D5b: TCA con 68 filas y 66 en 0; causa en `mt5.py:772-783`; decisión→fill
  0,44 bps de mediana (45/48).
- D6: `ruff` limpio; **pytest 2000 passed + 1 skipped**; `lab propfund verify` OK;
  `lab doctor` con Frescura FAIL 7/17 (aviso). `count_tests` **1926**, no 1897:
  +29 de `informal_trials` 6 (n=7) y 7 (n=22) de NASDAQ EDGE, ajenas a TL3-D;
  `bloqueado: contador cambiado`. Tag `tl3-ciclo1e`.

### Cierre 1f · TL3-E (2026-11-25)

- E1: `orq_lock` con `acquire`/`release`/`status`/`held`; CLI `scripts/orq_lock.py`;
  sección de coordinación en `AGENTS.md` y plantilla `.orquestador/PLANTILLA-COLA.md`.
- E2: `docs/VERIFICACION.md` y `tl3/verify.py`; tabla `verifications` y
  `registry.require_verified`; verificación NQF-A/B/C **Conforma** (29 comprobaciones,
  0 defectos, 1 aviso documental), hash `cb7ee5a9…`.
- E3: tabla `warnings`, `add_warning`/`warnings_for`/`render`, CLI
  `scripts/tl3_warnings.py`, 12 avisos sembrados (ea 4, ai_trader 4, CFD-006 1,
  prop.simulator 2, nqedge 1) y columna «Avisos» en `status_table`.
- E4: `ruff` limpio; **pytest 2017 passed + 1 skipped**; `lab propfund verify` OK;
  `lab doctor` con Frescura/IA sesiones como avisos de entorno; `count_tests` **1926**
  (sin cambios desde el arranque); tag `tl3-ciclo1f`.

### Cierre 1g — TL3-F (2026-11-25/26)

- F1: auditoría de `scripts/tl3_warnings.py` (12 avisos), huecos D3 de US100 y
  `tl2-edge-map.patch` archivado en `legacy/`; `count_tests` **5446** al arrancar F1.
- F2: H-2026-013 `draft` (US100 H1, cierre D1 > SMA50, entrada al open de la vela
  siguiente a la señal de 09:00 NY, stop 2,0×ATR(14), target 2R, flat 15:00,
  `nights == 0`). Plantilla `h1_sma50_session_long`; feasibility **799 ops** IS
  2019-2023, pliegues 207/202/77/199, `cost_r` **0,05388**; **21/799 cruzan día**
  en festivos/cierres NYSE.
- F3: verificación independiente contra `c4ec579` → **Defectos** (35 comprobaciones,
  3 defectos, 3 avisos): el spec conserva 15:55/415 frente a 15:00/360 de la
  plantilla+fila (documental) y **21/799 (2,63 %) noches >0**; 2 señales de Viernes
  Santo sin barra posterior. `H-2026-013` **no se aprueba**; informe
  `TL3_REPORTS/verificacion_h-2026-013.md` y fila en `verifications` (hash
  `9605ebc8…`, veredicto `Defectos`).
- Cierre: `ruff` limpio en las rutas de F3 (`ruff check .` solo marca
  `scripts/edge2_x0.py`, sin seguimiento y de la sesión EDGE2); pytest
  **2050 passed + 1 skipped** (34:05); `lab doctor` Frescura FAIL 5/17 y Reglas
  fondeo WARN (entorno); `lab propfund verify` OK; `count_tests` **7206 → 9846**
  (+2640 por 6 campañas `edge1-` aprobadas en paralelo; los 18 borradores
  `edge2-` no cuentan); sin filas nuevas en `informal_trials` (7, id 7) ni
  campañas ajenas a `edge1-`/`edge2-`; tag `tl3-ciclo1g`.

### Cierre 1h — TL2-TCA2 (2026-11-26)

- TCA v2: `signal_price` desde `ai_trader` (precio de la propuesta) y forward
  (precio de la decisión); `tca_version` en filas nuevas (**68 v1, 0 v2**);
  lectores de TCA solo v2; tolerancia `1e-9` en la frontera del SL; tags
  `tl2-tca2-pre`/`tl2-tca2-post`. **TCA v2 activa (tareas programadas); 0 filas
  v2 hasta el primer fill**.

### Cierre 1i — ROBUST-1 (2026-11-26)

- R1: `point` sale del instrumento (`EURUSD`/`GBPUSD` 0,00001, `USDJPY`
  0,001, `XAUUSD`/índices 0,01); se elimina el 0,01 por defecto y las
  campañas antiguas se corrigen al cargar. El estrés `slippage +2` de EURUSD
  pasa de ~182 bps a **0,18 bps**.
- R2: el PBO/WF usaba una unión desordenada de días con operación. Ahora es
  una serie diaria de días hábiles con ceros; `edge1-01` PBO **0,743** y
  `edge1-11` **0,198** (antes ambos 0,634 por el redondeo de una matriz
  defectuosa).
- R3: 14 de 22 finalistas quedan con **“WF no informativo (baja frecuencia)”**
  (mediana < 2 operaciones por pliegue). La puerta WF sigue en ≥ 0,3; no se
  tocaron ventanas ni umbrales. Propuesta por TF en
  `TL3_REPORTS/robust1_wf_windows.md`.
- R4: repetición de X3 sobre los 22 finalistas: **0 pasan las 4 puertas**;
  gate 3 ya pasa en la mayoría, gate 2 sigue fallando por WF/PBO/ruido.
- R5: EDGE-2 intacto; solo cambió la clasificación de huecos, sin cambios de
  `cost_r`, elegibilidad ni inicio. Las 18 campañas siguen en `draft`.
- Cierre: `ruff check .` limpio; `pytest -q` **2073 passed + 1 skipped**
  (34:40); `lab doctor` Frescura FAIL 7/17 y Reglas fondeo WARN (entorno);
  `lab propfund verify` **4 OK**.
- `count_tests` **12.694 → 12.694** (sin cambios). Tags `robust-pre` y
  `robust-1`. **TCA v2 activa (tareas programadas); 0 filas v2 hasta el primer
  fill** (TL2-TCA y TCA2).
- EDGE-2 (2026-11-26): 12/18 campanas `done` (6 bloqueadas por feasibility < 50 %), 12 finalistas,
  **0 pasan Y3** (WF ≈0 y PBO >0,30; puerta 3 OK); Y4 sin pasada 2, Y5 0 confirmadas (OOS-2 no
  leido), Y6 0 EAs. `count_tests` 12.694 → 17.974. Tag `edge2`.



- 2026-11-26: EDGE-1 cerrado (28 campanas, 22 finalistas, 0 confirmadas, 0 EAs; tag `edge1`).
