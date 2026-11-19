# 02 · Arquitectura objetivo · Prop Fund multiempresa

```
                 ┌─────────────────────────── TradingLab Console (web) ───────────────────────────┐
                 │  Prop Fund: Resumen · Empresas · Cuentas · CFD · Futures · Estrategias · Protección │
                 └──────────────────────────────────────▲──────────────────────────────────────────┘
                                                        │ GET /api/propfund (solo lectura)
┌─────────────── config/propfund ───────────────┐   ┌──┴───────────────── src/tradinglab/propfund ─────────────────┐
│ firms.yaml        10 firmas + matriz automat.  │──▶│ registry.py   carga + validación cruzada (pydantic)            │
│ accounts.yaml     una entrada por cuenta       │   │ models.py     Firm, Program, FirmRule, AutomationPolicy,       │
│ strategies.yaml   carriles (5 protegidas)      │   │               PropAccount, Strategy, StrategyAssignment...     │
│ assignments.yaml  estrategia → cuenta          │   │ instruments.py universo CFD/Futures, alias, subyacentes        │
│ costs.yaml        perfiles por cuenta/símbolo  │   │ costs.py      motor CFD  |  motor Futures (independientes)     │
│ risk.yaml         límites globales             │   │ risk.py       riesgo de cuenta + global por subyacente         │
│ protected_manifest.json  SHA-256 protegidos    │   │ router.py     Señal→Elegib.→Compliance→Riesgo→Coste→Solicitud │
└────────────────────────────────────────────────┘   │ protected.py  manifiesto e integridad                          │
                                                     │ cli.py        lab propfund status|firms|accounts|verify|route  │
                                                     └──────────────┬─────────────────────────────────────────────────┘
                     solo lectura ▲                                 │ ExecutionRequest (dry-run)
┌──────────── carril FTMO protegido ────────────┐                    ▼
│ EA us100-ftmo1 · ai_trader · forward FX        │      Fase 4: adaptadores de ejecución aislados
│ prop/ · guardian · account_daily · mt5.py      │      MT5 worker por cuenta · ProjectX · Tradovate · Rithmic
└────────────────────────────────────────────────┘
```

## Principios

1. **Construir alrededor, no encima.** Nada del carril FTMO se edita; el Prop
   Fund lo lee (cuentas `CFD-001/002` son espejos de `ftmo_demo` y
   `ftmo_trial_ea`) y suma sus posiciones al riesgo global.
2. **La estrategia no conoce la firma.** Emite una señal (entrada, stop). La
   asignación + cuenta + firma deciden si se opera, cuánto y con qué coste.
3. **Una decisión por cuenta.** Nunca un copiador ciego.
4. **CFD y Futures no se mezclan.** Motores, costes y validaciones separados;
   se unen solo en el riesgo global por subyacente.
5. **API disponible ≠ API autorizada.** Solo `full/conditional` +
   `verified_official` + confirmación del operador habilita órdenes
   automáticas. El resto: `ALERT_ONLY`.
6. **PAPER/DEMO por defecto.** El router produce como máximo
   `READY_DRY_RUN`. `LIVE_*` no se puede declarar en archivo.

## Flujo de ejecución (router)

| Paso | Rechazo | Comprueba |
|---|---|---|
| 1 Elegibilidad | `REJECTED_ELIGIBILITY` | asignación activa, cuenta no plantilla, conexión PAPER/DEMO, instrumento permitido, mismo motor, estrategia no protegida |
| 2 Compliance | `ALERT_ONLY` / `REJECTED_COMPLIANCE` | permiso de automatización, verificación oficial, confirmación del operador, fase, bot exclusivo (Tradeify), replicación |
| 3 Tamaño | `REJECTED_SIZING` | riesgo por operación → lotes (CFD, con tamaño de contrato del bróker) o contratos (Futures, tick value) |
| 4 Riesgo | `REJECTED_RISK` | cuenta: tope por operación, operaciones/día, posiciones, riesgo diario propio, límite diario y máximo de la firma con colchón. Global: hedging entre cuentas, nocional por subyacente, cuentas por subyacente, riesgo por firma/estrategia/total |
| 5 Coste | `REJECTED_COST` | perfil completo y coste ≤ `max_cost_r` |
| 6 Solicitud | — | `READY_DRY_RUN` con clave de idempotencia; se registra en `logs/propfund/decisions.jsonl` |
| 7 Reconciliación | — | Fase 4: fills vs. solicitud (reutiliza `reconciliation.py`) |

## Estados de conexión

`DISCONNECTED → CONNECTED_READ_ONLY → PAPER/DEMO → LIVE_LOCKED → LIVE_AUTHORIZED`.
Toda cuenta nueva arranca en `DISCONNECTED`; solo PAPER/DEMO enrutan; LIVE
requiere autorización humana fuera del archivo (no implementado a propósito).
