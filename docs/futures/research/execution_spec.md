# FUT-J0 · Contrato de ejecución y riesgo de futuros (OrderIntent → RiskCheck → adaptador o ticket)

**Fecha:** 2026-11-28 · **Autor:** Claude Code (skills `futures-risk-sizing` y
`backtest-leakage-audit`) · **Estado:** especificación para OpenCode (FUT-J1…J4).
**Alcance:** paper y demo. **Nada de live:** cualquier endpoint real exige `ALLOW_LIVE=YES` más la
aprobación explícita del operador, y en esta fase se bloquea siempre.
**Base:**
- `research/platform_matrix.md §2`;
- `04_SPEC_PROP_EV.md §3` (fórmulas del umbral L);
- `risk/02_ORPAE_DISENO.md` (perfiles y escalera de evidencia);
- `config/prop_economics/firms_futures.yaml` (bots y modo de ejecución).

## 0. Decisiones

1. **Paquete nuevo: `src/tradinglab/futures/execution/`.** No se modifica:
   - `propfund/risk.py`: es producción (Prop Fund), trabaja en % para CFD, no aplica `lock_at` ni
     `max_contracts` (`risk/00_AUDITORIA_RIESGO.md`);
   - `execution/projectx.py`.

   Solo se **importan** de `propfund/instruments.py` (`resolve`, `micro_equivalent`) y el adaptador de
   ProjectX.
2. **Las reglas de cada programa salen de su YAML** (`prop_economics.rules.load_program`, FUT-A1). No
   hay constantes de firma en el código.
3. **Falla cerrado:** si un dato que el control necesita es `sin_datos` o está caducado, la orden **no
   sale**. La única excepción es la comisión en paper, que se marca `cost_assumed` (V15).
4. **Origen obligatorio:** `origin ∈ {automated, semi_manual}`.
   - En firmas `prohibited` o `unverified`, solo `semi_manual`: un ticket que confirma una persona
     (decisión del operador: en las que no aceptan bots, se opera de forma semimanual).
   - Tradovate exige `isAutomated: true` en las órdenes automáticas, y el adaptador lo traduce.

## 1. Flujo

```text
señal (estrategia validada o en forward) → OrderIntent (sin enviar)
  → sizing (skill futures-risk-sizing; perfil ORPAE) → RiskCheck (R01…R16, todas)
  → ok:     origin=automated   → ExecutionAdapter (paper | ProjectX demo | NT8 Sim101)
            origin=semi_manual → Ticket (alerta + confirmación humana + registro manual del fill)
  → no ok:  rechazo con códigos; nada sale
  → ledger: intents, checks (con métricas), tickets, acks y fills; libro real separado del simulado (04 §9)
```

## 2. `OrderIntent` (dataclass inmutable)

| Campo | Tipo | Regla |
|---|---|---|
| `intent_id` | str (UUID4) | único |
| `created_at` | datetime UTC | con zona |
| `strategy_id`, `hypothesis_id` | str | `hypothesis_id` = `H-AAAA-NNN` o `forward:<id>` |
| `account_id`, `firm_id`, `program_id`, `phase` | str | `phase ∈ {evaluation, funded}` |
| `root` | str | `MNQ`, `NQ`, `MES`, `ES`, `MGC` o `GC`, resuelto con `instruments.resolve` |
| `contract` | str | p. ej. `MNQZ6`; nunca un continuo |
| `side` | `buy` \| `sell` | — |
| `qty` | int ≥ 1 | contratos enteros (ADR-F02) |
| `entry_type`, `entry_price` | `market` \| `limit` \| `stop`, float \| None | precio alineado al tick si existe |
| `stop_price` | float | **obligatorio**, al lado correcto (un largo, por debajo de la entrada) |
| `target_price` | float \| None | al lado correcto si existe |
| `exit_by` | hora local con zona | ≤ `last_entry`/`flat_by` del programa (R08) |
| `origin` | `automated` \| `semi_manual` | R03 |
| `adapter` | `paper` \| `projectx` \| `nt8` \| `ticket` | R04 |
| `risk_usd`, `cost_usd`, `cost_assumed` | float, float, bool | calculados (§3) y nunca escritos a mano |
| `signal_hash` | str | SHA-256 de las entradas de la señal (auditoría) |
| `dry_run` | bool | **True por defecto** |

## 3. Riesgo y coste de una orden

```text
pv        = valor del punto del root (catálogo: MNQ 2, NQ 20, MES 5, ES 50, MGC 10, GC 100)
tick_v    = valor del tick (MNQ 0,50, NQ 5, MES 1,25, ES 12,50, MGC 1, GC 10)
coste_c   = 2·comisión_por_lado(programa) + 2·slippage_ticks·tick_v         (slippage base = 1 tick)
risk_usd  = qty·|entry − stop|·pv + qty·coste_c
cost_usd  = qty·coste_c
micro_eq  = qty·micro_equivalent(root)                                        (NQ → 10, MNQ → 1)
```

- Una orden `market` usa como `entry` el último precio de referencia que se pasa al control.
- Si la comisión del programa es `sin_datos`:
  - **en paper**, se usa la del laboratorio (MNQ 0,75 por lado, dato del operador) y se marca
    `cost_assumed = True`;
  - en un adaptador conectado a una firma, se **bloquea** (R15).

## 4. `RiskCheck`: controles (todos se evalúan; se devuelven todos los motivos)

`colchón = 0,10` y `margen_entrada = 5 min`: constantes de `config/futures/execution.yaml` (fichero
nuevo), fijadas aquí.

| ID | Control | Bloquea si | Código |
|---|---|---|---|
| R01 | Reglas vigentes | `is_expired(program, hoy)` | `rules_expired` |
| R02 | Reglas necesarias conocidas | `max_contracts`, `max_loss`, `flat_by` o la DLL activa son `sin_datos` | `rules_unknown:<clave>` |
| R03 | Automatización | `origin = automated` y la firma es `prohibited` o `unverified`; o la firma es `conditional` sin `firm_conditions_ack` del operador en `config/futures/execution.yaml` | `automation_prohibited`, `automation_conditions_not_acked` |
| R04 | Plataforma | el adaptador no está soportado por la firma (p. ej. `nt8` en Topstep, que solo admite TopstepX) | `platform_unsupported` |
| R05 | Contratos máximos | `micro_eq(abiertas) + micro_eq(nueva) > max_contracts(fase, escalón)`; el escalón de escalado sale del beneficio EOD | `max_contracts` |
| R06 | Distancia al MLL | `riesgo_abierto + risk_usd > (equity − L)·(1 − colchón)`, con L de `04 §3.1` (modo, `lock_at`, `lock_after_first_payout`) | `mll_room` |
| R07 | DLL | DLL activa y `pérdida_del_día + riesgo_abierto + risk_usd > DLL·(1 − colchón)` | `dll_room` |
| R08 | Hora | `ahora ≥ last_entry`, donde `last_entry = min(última entrada de la firma, flat_by − margen_entrada)`; o `exit_by > flat_by` | `time_window` |
| R09 | Noticias | el programa tiene una ventana de noticias en esta fase y la orden cae dentro; **si falta el calendario, se bloquea** | `news_window`, `sin_datos_calendario` |
| R10 | Overnight | `exit_by` cae después del cierre de la sesión | `overnight` |
| R11 | Riesgo autorizado | `risk_usd > riesgo_política` (perfil ORPAE vigente para esa estrategia y escalón) | `risk_above_policy` |
| R11b | Sin martingala | la operación anterior de la misma estrategia y cuenta perdió y `risk_usd` supera el `risk_usd` de esa operación | `risk_increase_after_loss` |
| R12 | Exposición duplicada | ya hay un intent o posición abierta de la misma estrategia, cuenta y root; o la exposición agregada por subyacente entre cuentas supera el límite global | `duplicate_exposure`, `global_underlying_limit` |
| R13 | Unidad y tick | `root` y `qty` no cuadran con la unidad del programa; precios no alineados al tick; stop u objetivo al lado equivocado | `unit_mismatch`, `tick_misaligned`, `stop_side` |
| R14 | Consistencia (evaluación) | **no bloquea**: avisa si `beneficio_hoy + objetivo_de_la_orden > c·requerido` | aviso `consistency_risk` |
| R15 | Costes | comisión `sin_datos` con un adaptador que no es paper | `cost_unknown` |
| R16 | Live | cualquier endpoint no demo sin `ALLOW_LIVE=YES`; en esta fase, **siempre** | `live_blocked` |

## 5. Adaptadores (`ExecutionAdapter`, protocolo)

```text
name: str
supports(firm_id, program_id) -> bool
submit(intent) -> Ack        # Ack(intent_id, broker_order_id | None, status, raw)
cancel(broker_order_id) -> Ack
positions(account_id) -> list[PositionView]
account_state(account_id) -> AccountState   # balance, equity, peak_eod, best_day, day_pnl, payouts_requested
```

| Adaptador | Tarea | Notas |
|---|---|---|
| `PaperAdapter` | FUT-J1 | Fills simulados con las reglas de `RA_spec.md §4`. Sin red |
| `TicketAdapter` | FUT-J2 | Genera el ticket (raíz, contrato, lado, contratos, entrada, stop, objetivo, hora límite, `risk_usd`) y lo envía por `lab alerts send`/Telegram. Espera la confirmación humana; el fill lo registra la persona. Caduca al llegar a `last_entry` |
| `ProjectXAdapter` | FUT-J3 | Envuelve `execution/projectx.py` sin modificarlo. Primero dry-run; la prueba en la demo de TopstepX la autoriza el operador |
| `NT8Bridge` | FUT-J4 | Python escribe el intent en JSON en una carpeta de intercambio; una estrategia NinjaScript **no gestionada** (`SubmitOrderUnmanaged`/`ChangeOrder`/`CancelOrder`) lo lee y lo envía **solo a Sim101 o Playback**, y escribe acks y fills. La NinjaScript tiene su propio límite de contratos (defensa en profundidad) |

## 6. Vectores de prueba (exactos)

Comisiones de Topstep (ficha verificada): MNQ 0,61 y NQ 1,89 USD por lado. Slippage base: 1 tick.

| ID | Entrada | Esperado |
|---|---|---|
| V1 | MNQ, compra 5 a 21.000,00, stop 20.990,00 | `risk_usd = 5·10·2 + 5·(2·0,61 + 2·0,50) =` **111,10**; `cost_usd = 11,10` |
| V2 | NQ, compra 1 a 21.000,00, stop 20.990,00 | `risk_usd = 200 + (3,78 + 10) =` **213,78**; `micro_eq = 10` |
| V3 | Topstep, evaluación (50 micros): abiertas 45 MNQ, nueva 10 MNQ / 5 MNQ; abiertas 4 NQ + nueva 10 MNQ / 11 MNQ | bloquea `max_contracts` / ok; ok (50) / bloquea (51) |
| V4 | Lucid Flex, financiada: beneficio EOD 999 / 1.000 / 2.000 | máximo **20 / 30 / 40** micros |
| V5 | Topstep, evaluación (S 50.000, D 2.000, `lock_at` = S): `peak_eod` 51.500, equity 50.200, sin riesgo abierto; nueva de 650 / 600 | `L = min(49.500, 50.000) = 49.500`; hueco `700·0,9 = 630` → bloquea `mll_room` / ok. Con `peak_eod` 52.500: `L = 50.000` |
| V6 | Lucid Flex, financiada (`lock_at` 50.100, `lock_after_first_payout`): payout pedido, equity 50.600; nueva de 460 / 440. Sin payout y `peak_eod` 51.000 | `L = 50.100`, hueco `500·0,9 = 450` → bloquea / ok. Sin payout: `L = min(49.000, 50.100) = 49.000` |
| V7 | Topstep: `flat_by` 15:10 CT, última entrada de la firma 15:08 CT; orden a las 15:04:59 / 15:05:00 CT | `last_entry = min(15:08, 15:05) = 15:05` → ok / bloquea `time_window` |
| V8 | Alpha + `automated` / Alpha + `semi_manual` (`ticket`) / Lucid + `automated` (`nt8`) / Topstep + `nt8` / Topstep + `projectx` sin ack / con ack | `automation_prohibited` / ok / ok / `platform_unsupported` / `automation_conditions_not_acked` / ok |
| V9 | Política de 500 USD. La anterior perdió con 500; nueva de 650 / 500. La anterior ganó; nueva de 650 | bloquea `risk_increase_after_loss` y `risk_above_policy` / ok; bloquea `risk_above_policy` |
| V10 | Topstep consultado el 2026-11-27 (30 días); orden el 2026-12-26 / 2026-12-27 | ok / `rules_expired` |
| V11 | MFF Rapid, financiada, con ventana de noticias T1 y sin calendario / evaluación | `sin_datos_calendario` / ok |
| V12 | Intent abierto de la estrategia S1 en la cuenta A con MNQ; otro de S1/A/MNQ / de S1/B/MNQ | `duplicate_exposure` / ok (salvo `global_underlying_limit`) |
| V13 | Adaptador con un endpoint live sin `ALLOW_LIVE` / con `ALLOW_LIVE=YES` | `live_blocked` en los dos casos (esta fase) |
| V14 | MNQ con entrada a 21.000,10 / MGC con stop a 2.650,05 / MGC con stop a 2.650,10 | `tick_misaligned` / `tick_misaligned` / ok |
| V15 | Programa con comisión `sin_datos`: adaptador `paper` / `projectx` | ok con `cost_assumed=True` (0,75 por lado en MNQ) / `cost_unknown` |
| V16 | Largo con el stop por encima de la entrada | `stop_side` |

**Propiedad (hypothesis, 500 ejemplos):**
- `risk_usd ≥ qty·coste_c > 0`;
- R05 nunca deja pasar una orden con `micro_eq` total > máximo;
- con `peak_eod` creciente, `L` nunca decrece.

## 7. Tareas para OpenCode (DeepSeek V4.1 Flash)

| ID | Qué | Ficheros permitidos | Depende de | Aceptación |
|---|---|---|---|---|
| FUT-J1 | `intent.py`, `riskcheck.py`, `PaperAdapter`, `config/futures/execution.yaml` | `src/tradinglab/futures/execution/{__init__,intent,riskcheck,paper}.py`, `config/futures/execution.yaml`, `tests/test_futures_execution.py` | A1 (cargador de programas), A10 (escalado y `compliance`) | V1-V16 exactos y la propiedad |
| FUT-J2 | `TicketAdapter` y ledger de intents, checks y tickets | `.../ticket.py`, `.../ledger.py`, tests | J1 | ticket caducado a `last_entry`; el fill manual queda en el libro real, nunca en el simulado |
| FUT-J3 | `ProjectXAdapter` (envoltorio, dry-run) | `.../projectx_adapter.py`, tests | J1 | sin red en los tests; `live_blocked` |
| FUT-J4 | `NT8Bridge` + NinjaScript no gestionada solo para Sim101/Playback | `.../nt8_bridge.py`, `integrations/nt8/TradingLabBridge.cs` (nuevo), tests de Python | J1 | la NinjaScript rechaza cuentas que no sean Sim; límite de contratos propio |

El prompt pegable de FUT-J1 se escribe cuando A1 esté cerrada, porque usa su `Program` real.

**Prohibido en J1-J4:**
- tocar `propfund/*`, `execution/projectx.py` y `execution/mt5*.py` (este último es protegido);
- endpoints live;
- `.env`.
