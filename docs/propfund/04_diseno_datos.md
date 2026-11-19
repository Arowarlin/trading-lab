# 04 · Diseño de datos

## Entidades (prompt maestro §6) → implementación

| Entidad | Dónde vive | Notas |
|---|---|---|
| Firm | `propfund/models.py::Firm` | mercado, prioridad, `protected`, `legacy_prop_key`, plataformas, proveedores |
| Program | `Program` | fases, plataformas, tamaños, reglas |
| Account | `PropAccount` | id propio (`CFD-001`, `FUT-001`), `legacy_account` hacia `config/accounts.yaml` |
| AccountPhase | `AccountPhase` | evaluation · verification · funded · live |
| TradingPlatform / Broker / ExecutionProvider | campos `platform`, `execution_provider` en cuenta y firma | se promueven a entidad propia cuando exista más de un adaptador por plataforma |
| Connection | `ConnectionState` + `credentials_ref` (keyring) | nunca el secreto |
| Instrument / InstrumentAlias / InstrumentSpecification | `propfund/instruments.py::CanonicalInstrument` | reutiliza `tradinglab.instruments` para futuros CME |
| CostProfile | `propfund/costs.py::CostProfile` + `config/propfund/costs.yaml` | FTMO hereda comisión verificada de `config/costs.yaml` |
| Strategy / StrategyInstance | `Strategy` | parámetros por referencia (`params_ref`), no duplicados |
| StrategyAssignment | `StrategyAssignment` | `replication_group` opcional |
| RiskPolicy | `RiskPolicy` | por cuenta, con colchón respecto a la firma |
| FirmRule | `FirmRule` | valor + unidad + fase + estado + fuente |
| ExecutionRoute / Order | `router.AccountDecision.request` | dry-run idempotente |
| Position | `risk.PositionView` | incluye posiciones de componentes protegidos (lectura) |
| AccountSnapshot | `risk.AccountSnapshot` | balance, equity, inicio de día, pico |
| ComplianceEvent / AuditLog | `logs/propfund/decisions.jsonl` | cada paso con motivos |

Entidades **existentes reutilizadas sin cambios**: `PropRules`,
`AccountDefinition`, `Instrument`, tabla `broker_spreads`, tabla
`account_limit_history`.

## Compatibilidad

* No hay migración de SQLite en esta fase: todo es configuración versionada.
* `config/accounts.yaml` y `config/prop.yaml` no se modifican (hash F13).
* Cuando la Fase 4 escriba snapshots/fills se usará una tabla nueva
  `propfund_snapshots` con `account_id` del Prop Fund, sin tocar las tablas del
  carril FTMO.

## Universo

* CFD: Forex (EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF, NZDUSD, EURJPY,
  GBPJPY), Índices (US100, US500, US30, US2000, GER40, UK100, JP225), Metales
  (XAUUSD, XAGUSD).
* Futures: NQ, MNQ, ES, MES, YM, MYM, RTY, M2K, GC, MGC, SI.
* Excluidos: acciones y ETF (`EXCLUDED_ASSET_CLASSES`). El registro rechaza
  cualquier símbolo fuera del universo.
* Subyacentes comunes: `NASDAQ100` = US100 + NQ + MNQ; `GOLD` = XAUUSD + GC + MGC; etc.
