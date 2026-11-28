# FUT-H0 · Modelo de dominio del dashboard de futuros (dinero real frente a simulado)

**Fecha:** 2026-11-28 · **Autor:** Claude Code · **Estado:** especificación para OpenCode
(FUT-H1…H3, y FUT-A8 para el libro). Amplía `04_SPEC_PROP_EV.md §9`.

**Principio:** solo es dinero lo que **llega a la cuenta bancaria del operador**. El saldo que muestra
una firma, el P&L simulado y el EV de un Monte Carlo son información, nunca dinero, y el dashboard no
los suma nunca con el dinero real.

## 1. Tres capas que no se mezclan

| Capa | Fuente | Quién escribe | Se muestra como |
|---|---|---|---|
| **Real** | `data/prop_economics/ledger.db` | solo el operador, con `lab propecon ledger add` y una evidencia (PDF, captura, extracto) | USD reales: pagados y recibidos |
| **Nominal de la firma** | snapshot de la plataforma en paper o demo (adaptadores de FUT-J) | el adaptador, solo lectura | «saldo de la firma (no es dinero)», con la hora del snapshot |
| **Simulada** | `SimulationRun` (FUT-A6/A7, ORPAE) | el motor, en su propia base, **sin acceso de escritura al libro** | EV, mediana, P5/P95 y probabilidades, siempre con la ventaja supuesta y la semilla |

## 2. Entidades

| Entidad | Campos clave | Notas |
|---|---|---|
| `Firm` | `firm_id`, nombre, `automation.category`, `execution_mode` | de `config/prop_economics/firms_futures.yaml` |
| `Program` | `program_id`, `rules_version`, `consulted_at`, `expires_at` | de los YAML. Cada cuenta guarda la versión con la que se compró |
| `Account` | `account_id`, `firm_id`, `program_id`, `rules_version`, `phase` (`evaluation`/`funded`/`live`), `status` (`active`/`passed`/`failed`/`closed`/`to_live`), `opened_at`, `closed_at`, `platform`, `origin` (`automated`/`semi_manual`) | una fila por cuenta comprada; un reset no crea cuenta nueva, es un evento |
| `LedgerEvent` | `id`, `ts`, `account_id`, `event`, `amount_usd`, `amount_local`, `currency_local`, `fx_rate`, `evidence_path`, `note` | inmutable: una corrección es otro evento (`correction`) que apunta al `id` corregido |
| `Payout` | `payout_id`, `account_id`, estado, importe y fecha de cada paso | se **deriva** de los eventos `payout_*` (§3); no se escribe a mano |
| `StrategyAssignment` | `account_id`, `strategy_id`, `hypothesis_id`, desde y hasta, perfil de riesgo | qué opera en cada cuenta y con qué riesgo |
| `RealFill` | `account_id`, contrato, lado, cantidad, precio, hora, comisión | viene de la plataforma (libro real de operaciones). No es dinero hasta un payout |
| `SimulationRun` | `run_id`, programa, política, escenario de ventaja, semilla, `n_paths`, horizonte, hash de la configuración y del pool, resultados | reproducible |
| `Recommendation` | `rec_id`, `run_id`, regla de decisión, ventaja usada (cota inferior), resultado, hora | lo que el ORPAE propone; nunca ejecuta nada |

## 3. Eventos del libro real (amplía `04 §9`)

| Evento | Importe | Significado |
|---|---|---|
| `fee_paid` / `reset_paid` / `activation_paid` | − | tarifas de la firma |
| `subscription_paid` | − | API (p. ej. ProjectX), datos, plataforma, VPS: cualquier coste mensual del proyecto |
| `account_opened`, `account_passed`, `account_failed`, `account_closed`, `to_live` | 0 | cambios de estado, con evidencia |
| `payout_requested` | + bruto pedido | el operador lo pide en el panel de la firma |
| `payout_approved` | + bruto aprobado | puede ser menor que lo pedido |
| `payout_rejected` | 0 | con el motivo en `note` |
| `payout_processed` | + neto enviado por la firma (después del reparto) | la firma lo manda al proveedor de pagos (Rise, Deel, banco…) |
| `payout_received` | + neto recibido en el banco | **el único evento que cuenta como dinero ganado**. Lleva `amount_local`, `currency_local` y `fx_rate` si la cuenta bancaria no es en USD |
| `transfer_fee` | − | comisiones del proveedor o del banco que no estén ya descontadas |
| `correction` | ± | corrige un evento anterior (`note` con el `id`) |

**Máquina de estados del payout:**
`requested → approved → processed → received`, y `requested → rejected`. Un payout procesado que no
llega en `processing_days + 5 días hábiles` genera la alerta `payout_delayed`.

**Invariantes (tests de FUT-H1):**
1. `aprobado ≤ pedido`.
2. `procesado ≤ aprobado`.
3. `recibido ≤ procesado + 0,01`.
4. No hay `payout_received` sin `payout_processed`, ni `processed` sin `approved`.
5. Ningún evento apunta a una cuenta inexistente.
6. Solo `correction` cambia una cifra anterior.
7. El motor de simulación abre `ledger.db` en `mode=ro` o no la abre; un test lo comprueba.

## 4. Cifras del dashboard (todas en USD; la moneda local aparte)

**Por proyecto y por firma:**
- **Dinero real:**
  - `costes_pagados` = Σ de importes negativos;
  - `recibido` = Σ `payout_received`;
  - **`neto_real` = `recibido` − `costes_pagados`**;
  - `capital_máximo_expuesto` = el máximo histórico de (costes pagados − recibido).
- **Canal de cobros:** pedido, aprobado, procesado y recibido, con el importe en cada estado. Aparte, lo
  que está en tránsito (procesado y no recibido).
- **Tiempos observados:**
  - de la petición a la aprobación, de la aprobación al envío y del envío al banco (mediana y máximo);
  - comparados con los `processing_days` del YAML. Si difieren, se avisa para actualizar el programa.
- **Observado frente a modelo** (`04 §7.3`, dos columnas):
  - P(aprobar la evaluación) = aprobadas/intentos, con intervalo de Wilson;
  - payouts por cuenta financiada, días hasta el primer payout, coste por cuenta financiada;
  - con n < 10: «muestra corta», sin conclusiones.

**Por cuenta:**
- estado, fase y versión de las reglas;
- saldo de la firma (nominal) y distancia al MLL en USD y en «stops» del perfil (del snapshot);
- estrategia asignada, origen (automático o semimanual) y perfil de riesgo;
- costes, payouts y neto real de esa cuenta.

**Simulado** (panel aparte, nunca sumado al real):
- el último `SimulationRun` de cada programa y estrategia;
- EV, mediana, P5/P95, P(≥ 1 payout) y ruina a 6, 12 y 24 meses;
- la ventaja supuesta y su origen (cota inferior medida o escenario hipotético).

## 5. Alertas

| Alerta | Condición |
|---|---|
| `rules_expired` | una cuenta activa opera con un YAML caducado (`expires_at` ≤ hoy) |
| `rules_changed` | la versión del YAML cambia mientras hay cuentas activas con la anterior |
| `payout_delayed` | ver §3 |
| `near_mll` | distancia al MLL < 1,5 × el riesgo por operación del perfil |
| `budget_low` | presupuesto + recibido − costes < precio de la próxima evaluación |
| `drift` | la cota inferior de la ventaja medida en forward baja de peldaño (`risk/01 §5`) |

## 6. Tareas para OpenCode (DeepSeek V4.1 Flash)

| ID | Qué | Ficheros | Depende de | Aceptación |
|---|---|---|---|---|
| FUT-H1 | Libro real v2: eventos de §3, máquina de estados del payout, invariantes y cifras de §4 | `src/tradinglab/prop_economics/ledger.py`, tests | A1 | los 7 invariantes y las cifras de un libro sintético con valores exactos |
| FUT-H2 | API de solo lectura `/api/futures/economics` (real, nominal y simulado por separado) | sub-ruta nueva en `web.py`, con el lock `web-py` | H1, A8 | el JSON trae tres bloques separados; no hay un campo que sume real y simulado |
| FUT-H3 | Vista en `webui/` | `webui/` (lock `web-py`) | H2 | los paneles real y simulado son distintos y el simulado lleva el rótulo «simulado, ventaja supuesta» |

FUT-A8 debe implementar el libro **según este modelo** (sustituye a la tabla mínima de `04 §9`).
