# ESTADO · TradingLab

> **Lo primero que se lee.** Una página: dónde estamos, qué falta y qué decide el operador. Se
> actualiza al cerrar cada cola. Las colas antiguas de `.orquestador/` son historia; la vigente es la
> que aparece aquí.
>
> **Actualizado:** 2026-11-26 17:50 · `count_tests` **17.974** · WF-TF cerrado (0/34)

## 1. Objetivo
Encontrar una ventaja **real y neta de costes** y operarla en demo o en retos de prop firm (solo
paper/demo), sin engañarse: prerregistro, contador de pruebas (DSR) y holdout sellado.

## 2. Veredicto de hoy: **ninguna ventaja validada**

| Candidato | Evidencia | Estado | Próximo control |
|---|---|---|---|
| **EA `us100-ftmo1`** | +0,31 R/op en su periodo de diseño (réplica T6, 479 ops). Fuera de periodo (T7, 2013-14 y 2018-21): −0,03 R, **no confirma** | **Incierto**. Es el único que opera (forward FTMO demo: 3 cerradas) | n = 30 → 2027-03-16 · n = 60 → 2027-07-13 · final n = 515 → 2032-06-14 |
| **`ai_trader`** | No supera a la regla de tendencia (Δ −0,02 R, IC95 [−0,18; +0,12]). Real **+0,05 R** frente a +0,30 R simulado; la diferencia está en la salida | **No concluyente** | Evaluación única a n = 180 → **2027-01-04** |
| **NQF-A / NQF-B / NQF-C** (NASDAQ_EDGE) | Historia contaminada por el EA; solo vale el forward. Prerregistrado y congelado (tag `nqedge-forward-start`), comisión MNQ 0,75 USD/lado | **Forward desde el 2026-11-30** | n = 200: C → 2027-08-08 · A → 2027-09-26 · **B → 2030-10-18** (fechas optimistas) |

Cerradas: H1 nocturna (`cost_gate`), H2 FOMC (no confirma), H3 rango de apertura (`no_power`),
Fix FX y Asia USDJPY (rechazadas), cambio de mes / rebote D1 / Donchian / momentum / NY open GA
(`inconclusive`). La fase C histórica de NASDAQ_EDGE se ejecutó y está registrada (22 + 7 pruebas).

## 3. En marcha
- **Colas:**
  - `.orquestador/COLA-TL3-E.md`: locks entre sesiones, verificación previa de NQF y avisos por
    estrategia. Solo está hecho E0.
  - `.orquestador/COLA-EDGE-1.md`: fábrica de estrategias en M15/M30/H1/H4 con 7 activos y el motor
    `lab discovery`. **Pasada 1 cerrada** (28 campañas, 22 finalistas); X3 no dejó ningún finalista
    con las 4 puertas: X4 = sin pasada 2, X5 = 0 confirmadas, X6 = 0 EAs. Cierre X7-X8 en curso.
  - `.orquestador/COLA-EDGE-2.md`: índices US100/US500/US30. Y0-Y7 cerrados: 12/18 campañas `done`
    (6 bloqueadas por feasibility), 12 finalistas, 0 pasan Y3; Y4 = sin pasada 2, Y5 = 0 confirmadas
    (OOS-2 no leído), Y6 = 0 EAs. Y8 en cierre. Diagnóstico: H1/H4 empiezan 2019-01-02; US30 fuera
    por spread Sin datos; `intraday_momentum_close_v2` excluida (fallo de `_session_mask`).
  - Cerradas hoy: TL3-B, C y D (`tl3-ciclo1e`), TL2-DIARIO y NQEDGE-FORWARD (`nqedge-forward-start`).
- **Rutina diaria desde el 2026-11-30**, después del cierre de NY, con MT5 abierto:
  `E:\trading-lab\.venv\Scripts\python.exe E:\trading-lab\NASDAQ_EDGE_INSTITUTIONAL\tools\forward_daily.py --commission-side-usd 0.75`
  (la ayuda del script usa 1,25 como ejemplo: **no** es la comisión). El forward del EA y el de
  `ai_trader` corren en el sistema existente.
- **Producción cambiada hoy:** TL2-DIARIO (suelo diario de FundingPips en `prop/simulator.py` y
  `prop/guard.py`; vuelta atrás en `tl2-diario-pre`).
- **TCA v2 aplicada (TL2-TCA2):** `signal_price` desde `ai_trader` y forward, `tca_version`
  (**68 filas v1, 0 v2**), lectores solo v2 y tolerancia `1e-9` en la frontera del SL; tags
  `tl2-tca2-pre`/`tl2-tca2-post`. **TCA v2 activa (tareas programadas); 0 filas v2 hasta el
  primer fill**.

## 4. Decisiones del operador pendientes

| # | Decisión | Qué desbloquea |
|---|---|---|
| 1 | ~~Comisión MNQ~~ **Hecho:** 0,75 USD/lado (2026-11-25) | Forward NQF desde el 2026-11-30 |
| 2 | ¿Mantener **NQF-B**? Llegaría a n = 200 hacia 2030 | Foco del forward |
| 3 | Arreglar la **TCA** (slippage siempre 0; `execution/mt5.py:772-783`), cola de producción | Costes reales medidos para todas las estrategias |
| 4 | **E-3**: la protección diaria de FundingPips solo usa la equidad, cola de producción | Riesgo correcto en la cuenta CFD-006 |
| 5 | ¿Comprar **NQ/MNQ 2019+** (Databento)? | Datos de futuros reales para NASDAQ_EDGE |
| 6 | **Medir el swap** durante ≥ 20 sesiones (necesita una tarea programada) | Reabrir hipótesis que duermen posiciones |
| 7 | **Tarifas y reparto** de cada prop firm | Valor esperado neto en Prop Fund |

## 5. Calendario de controles (lo único que mueve el veredicto)

| Fecha estimada | Control |
|---|---|
| 2027-01-04 | `ai_trader`: evaluación única (n = 180) |
| 2027-03-16 | EA forward: punto de control n = 30 |
| 2027-07-13 | EA forward: punto de control n = 60 |
| 2027-08-08 | NQF-C: n = 200, si arranca el 2026-11-30 |
| 2027-09-26 | NQF-A: n = 200, si arranca el 2026-11-30 |

Antes de cada fecha **no se mira** el rendimiento; solo se cuentan operaciones.

## 6. Dónde está cada cosa

| Qué | Fichero |
|---|---|
| Resultados TL3 por bloque e hipótesis | `TL3_REPORTS/TL3_RESULTS_CICLO1.md` |
| Cierre detallado de las colas TL3 | `.orquestador/RESULTADO-TL3.md` |
| Cambios de producción y vuelta atrás | `docs/CHANGELOG-produccion.md` |
| Planes de forward (EA / `ai_trader`) | `TL3_REPORTS/ea_forward_monitor_plan.md` · `TL3_REPORTS/ai_trader_power_plan.md` |
| NASDAQ_EDGE: plan vigente y prerregistro | `NASDAQ_EDGE_INSTITUTIONAL/README.md` · `NASDAQ_EDGE_INSTITUTIONAL/04_FORWARD/prerregistro.md` |
| Línea base de prop firms sin ventaja | `TL3_REPORTS/propfund_zero_edge.md` · `TL3_REPORTS/tl2_diario_inventario.md` |
| Diagnóstico de la ejecución (TCA) | `TL3_REPORTS/tca_diagnostico.md` |
| Reglas para agentes | `AGENTS.md` |

## 7. Cómo se mantiene
- Lo actualiza **solo** el cierre de cada cola (con el lock `readme-plan` cuando exista), sin borrar
  nada: las cifras nuevas sustituyen a las viejas y la historia queda en git.
- Una cola nueva solo se abre si responde a una fila de §4 o a una fecha de §5.

## 8. Campañas EDGE-1 (2026-11-26)

| Métrica | Valor |
|---|---:|
| Campañas pasada 1 | 28 (12.320 pruebas registradas) |
| Finalistas | 22 |
| Pasaron X3 completo | 0 |
| Pasada 2 (X4) | sin pasada 2 |
| Confirmadas OOS-2 (X5) | 0 |
| EAs exportados (X6) | 0 |

X3 falló por puerta 2: WF con eficiencia < 0,3 y PBO > 0,30 en todos los finalistas. No se leyó
OOS-2. count_tests pasó de 1.926 a 12.694. Tag edge1 al cerrar X8.

## 9. ROBUST-1 (2026-11-26)

- **EDGE-1: 0 robustas.** Motivo: la repetición de X3 con las herramientas
  corregidas deja 0/22 finalistas con las 4 puertas. El fallo ya no es el
  `point` (gate 3 pasa en la mayoría): sigue la puerta 2, con WF < 0,3
  (14/22 “WF no informativo” por baja frecuencia) y PBO > 0,30 en la mayoría.
  `edge1-01` PBO 0,743; `edge1-11` PBO 0,198 pero WF 0,000.
- **EDGE-2: lista para Y2.** El plan Y1 sigue intacto: la corrección de huecos
  de Y0 no cambió `cost_r`, elegibilidad ni inicio; las 18 campañas siguen en
  `draft` (7.920 pruebas sin contar).
- **TCA v2 activa (tareas programadas); 0 filas v2 hasta el primer fill**
  (TL2-TCA y TCA2; el `pid` de `owner.json` no declara locks huérfanos).
- Cierre: `ruff check .` limpio; `pytest -q` **2073 passed + 1 skipped**
  (34:40); `lab doctor` Frescura FAIL 7/17 y Reglas fondeo WARN (entorno);
  `lab propfund verify` **4 OK**.
- `count_tests` **12.694 → 12.694**; tags `robust-pre` y `robust-1`.

## 10. Motor flat_mode (2026-11-26)

- `discovery` 0.2.0: `flat_mode` `legacy` (defecto, identico bit a bit) y
  `no_overnight` (cierra la vela que contiene `flat_at` y la ultima vela
  disponible del dia de sesion; cubre cierres tempranos NYSE y velas que
  faltan). H-2026-013: **21 → 0** operaciones con `nights > 0` (799 ops, sin
  PnL).
- Inventario: 64 campanas, 52 afectadas con `legacy` (48 de 24 h por diseno y 4
  intradia de `st_reversal_idx`); 22 finalistas EDGE-1 (21 multi-dia, 1
  intradia correcto); 0 EAs en `exports/edge1/`. Informe
  `TL3_REPORTS/motor_flat_inventario.md` y 7 avisos.
- `motor flat_mode; intraday_momentum_close_v3 lista para una campana futura`.
  Tambien `session_breakout_htf_v3` y `st_reversal_idx_v3`.
- `h1_sma50_session_long_v2` + spec 15:00/360 + `H-2026-013b` (`draft`) listos
  para la verificacion independiente; **no verificados aqui**.
- Sin campanas, sin `record-informal`, sin ordenes, sin push. Tag
  `motor-flat`.

## 10. Campañas EDGE-2 (2026-11-26)

| Métrica | Valor |
|---|---:|
| Campañas pasada 1 | 12 `done` de 18 (5.280 pruebas) |
| Bloqueadas en `approve` | 6 por feasibility < 50 % (siguen en `draft`, no suman) |
| Finalistas | 12 |
| Pasaron Y3 completo | 0 |
| Pasada 2 (Y4) | sin pasada 2 |
| Confirmadas OOS-2 (Y5) | 0 (OOS-2 no leído) |
| EAs exportados (Y6) | 0 |

Y3 falló por puerta 2: WF ≈0 y PBO >0,30 en los 12; la puerta 3 (spread p75 y slippage ×2) pasó en
todos. Bloqueadas: `edge2-10`, `13`, `15`, `16`, `17` y `18` (US100 M15/M30 y US500 H1
`st_reversal_idx`). `count_tests` pasó de 12.694 a **17.974**. Tag `edge2` al cerrar Y8.

## 11. WF-TF (2026-11-26)

- **0 de 34 finalistas** (22 EDGE-1 + 12 EDGE-2) pasan las 4 puertas con las ventanas por TF; sin
  candidato a `confirm` y OOS-2 sin leer. `count_tests` 14.014 al empezar → 17.974 (solo por EDGE-2);
  `ruff` limpio, pytest **2081 passed + 1 skipped** (31:53), `lab doctor` Frescura FAIL 1/17. Tag
  `wf-tf-1`.

