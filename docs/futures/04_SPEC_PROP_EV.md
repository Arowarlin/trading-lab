# FUT-A · Especificación del Futures Prop Firm Expected Value Engine

**Fecha:** 2026-11-27 · **Autor:** Claude Code · **Estado:** especificación lista para implementar
**tras la aprobación** de `03_ARQUITECTURA_FUTURES.md` (ADR-F03, F09). Paquete:
`src/tradinglab/prop_economics/`. No toca `prop/`, `propfund/` ni producción.

## 0. Objetivo y alcance

Calcular, para una estrategia de futuros y un programa de una firma, el **dinero neto que se espera
retirar** a 30/90/180/365 días, con sus probabilidades, su incertidumbre y el capital que exige, y la
**ventaja mínima rentable** μ\* del programa.

- **Dentro:** fases de evaluación y cuenta financiada simulada (Combine/XFA, Evaluation/PA), tarifas,
  activación, reset, payouts, reemplazo de cuentas, varias cuentas con la misma estrategia, bankroll.
- **Fuera de v1:** cuentas Live (p. ej. Topstep LFA): la transición se registra como evento terminal
  `to_live` y su valor se informa aparte como **Sin datos**; cambios de tamaño **dentro** de un día.
- **Regla de oro:** el motor **nunca** escribe en el libro de resultados reales (§9) y nunca presenta un
  número simulado como realizado.

## 1. Notación

| Símbolo | Significado |
|---|---|
| S | balance inicial de la fase (USD) |
| B_t | balance realizado al cierre del día t (tras costes) |
| E(τ) | equidad en el instante τ (balance + flotante) |
| T | objetivo de beneficio (USD) |
| D | importe del drawdown máximo (USD) |
| L(τ) | umbral de liquidación vigente |
| K | nivel de bloqueo del trailing (`lock_at`, absoluto) |
| κ_t | contratos del día t (entero ≥ 0), fijado al inicio del día |
| x_t(·) | trayectoria de P&L de **1 contrato** en el día t, con x_t(0) = 0 |
| H | horizonte en días naturales |

**Convención de rotura (obligatoria):** hay rotura cuando `E(τ) ≤ L(τ)` (igualdad incluida). Los
vectores de prueba de §10 dependen de ella.

## 2. Entrada: `DayPath`

Una estrategia entra al motor como un **pool de días de sesión** (incluidos los días sin operaciones):

```python
@dataclass(frozen=True)
class DayPath:
    session_date: date          # fecha de sesión CME
    marks: np.ndarray           # float64, P&L acumulado de 1 contrato, USD, neto de costes;
                                # marks[0] == 0.0; marks[-1] == cierre del día
    n_trades: int               # operaciones del día (0 = día sin operar)
    exit_idx: tuple[int, ...]   # índice en marks de la salida de cada operación (para §7.1)
    gross_pnl: float            # P&L bruto de 1 contrato (antes de costes), para escenarios
    cost: float                 # costes de 1 contrato en el día (comisión+fees+slippage), >= 0
    risk_usd: float | None      # riesgo inicial medio por operación de 1 contrato (para R)
    flags: frozenset[str]       # p. ej. {"news_window", "overnight"} para el cumplimiento
    source: str                 # "forward" | "oos" | "is" | "synthetic"
```

- `marks` contiene **todos los extremos locales** de la trayectoria a la resolución de los datos, en
  orden. Con barras de 1 minuto y sin saber el orden de máximo y mínimo dentro de la vela, cada vela
  aporta **primero el extremo favorable y después el adverso** (pico → valle). Es la ordenación que
  maximiza el drawdown desde el pico: **conservadora** para el trailing.
- Constructor mínimo desde una lista de operaciones `(pnl_neto, mfe, mae)` por día, en orden:
  `0 → … → acumulado + mfe → acumulado − mae → acumulado + pnl_neto`.
- Validación: `marks[0] == 0`, finitos, `cost >= 0`, `abs(marks[-1] − (gross_pnl − cost)) < 1e-9`.

**Escalado:** el P&L del día con κ contratos es `κ · x_t(τ)`. Es lineal porque comisión, fees y
slippage son por contrato (`propfund/costs.py:596-621`).

## 3. Reglas por fase

Cada regla viene del YAML del programa (§8) y lleva `status`. Si una regla que afecta al resultado
tiene `status: sin_datos`, el motor **se niega a correr** salvo que se pase una suposición explícita
(`--assume clave=valor`), que se imprime en la cabecera del informe.

### 3.1 Drawdown máximo

| `mode` | Umbral | Cuándo se actualiza | Rotura |
|---|---|---|---|
| `static` | `L = S − D` | nunca | `E(τ) ≤ L` |
| `trailing_eod` | `L_t = min(max_{u≤t} B_u − D, K)` con `B_0 = S` | al cierre de cada día | durante el día t+1, `E(τ) ≤ L_t` si `check: realtime_unrealized`; o solo `B_{t+1} ≤ L_t` si `check: eod_only` |
| `trailing_intraday` | `L(τ) = min(max_{u≤τ} E(u) − D, K)` | en cada marca | `E(τ) ≤ L(τ)` |

- `K = +∞` si no hay bloqueo. Con bloqueo al balance inicial, `K = S`.
- `lock_after_first_payout: true` → tras el primer payout `L = K` para siempre.
- El umbral **nunca baja** (propiedad a comprobar con hypothesis).

**Evaluación de un día con marcas discretas** (κ contratos, balance de inicio `b`):

```text
peak = max(peak_prev, b)            # pico relevante para trailing_intraday
for m in marks[1:]:
    e = b + κ·m
    if mode == "trailing_intraday":
        peak = max(peak, e); L = min(peak − D, K)
    if e <= L:            → rotura; P&L del día = e − b; fin de la cuenta
    if dll and (e − b) <= −DLL:
        → acción DLL (§3.2); el resto de marcas del día se descarta
B = b + κ·marks[-1]
if mode == "trailing_eod": L = min(max(peak_eod, B) − D, K); peak_eod = max(peak_eod, B)
```

### 3.2 Límite de pérdida diaria (DLL)

- `action: pause_day` (Topstep, Apex): el día termina con P&L = `e − b` de la primera marca que cruza;
  no es rotura.
- `action: breach`: igual que el drawdown máximo.
- Base: `day_start_balance` (por defecto) o `higher_of_balance_or_equity`.
- `enabled: false` si la regla es opcional y no se contrató.

### 3.3 Objetivo, días mínimos, consistencia y plazo (evaluación)

Al cierre del día t, con beneficio total `P = B_t − S` y mejor día `best` (máximo P&L diario realizado):

```text
requerido = T
if consistency: requerido = max(T, best / c)          # c = max_best_day_fraction, basis total_profit
pasa = P >= requerido and dias_operados >= min_trading_days and not roto
```

- `dias_operados` cuenta los días con `n_trades > 0`.
- `max_calendar_days` / `max_trading_days`: si se agota sin pasar → `failed_timeout`.
- `on_violation: raise_target` es el caso anterior; `on_violation: fail` convierte la violación en fallo.

### 3.4 Contratos máximos y escalado

`κ_t = min(policy(estado), max_contracts(fase, balance))`, en la unidad del contrato que opera la
estrategia (1 mini = 10 micros, `propfund/instruments.py:236-246`). Tabla de escalado con
`status: sin_datos` → se exige `--assume`.

### 3.5 Cumplimiento por banderas

Si un día trae una bandera prohibida por el programa (`news_window` con NQ en Topstep, `overnight`), el
día se marca `rule_violation:<regla>` y se aplica la acción del YAML (`skip_day` = la estrategia no opera
ese día; `breach`). Por defecto `skip_day`: la estrategia debe filtrar esos días **antes** del motor.

## 4. Fase financiada y payouts

### 4.1 Elegibilidad (plantillas parametrizadas)

| Plantilla | Condición desde el último payout | Ejemplo |
|---|---|---|
| `winning_days` | ≥ `n` días con P&L ≥ `min_day_profit` | Topstep Standard: 5 días ≥ 150 USD |
| `trading_days_consistency` | ≥ `n` días operados y `best ≤ c · beneficio_neto` | Topstep Consistency: 3 días, c = 0,40 |
| `min_balance_and_days` | balance ≥ `min_balance` y ≥ `n` días | genérico |

### 4.2 Importe y política del trader

```text
disponible = min(max_fraction_of_balance · B, cap_per_payout, B − buffer_min)
w = política(disponible, estado)       # "max_asap" (defecto), "keep_cushion(X)", "fixed(X)"
if w < min_amount: no se pide
recibido = split · w − payout_fee
B = B − w ; si lock_after_first_payout: L = K
```

- El payout se **solicita** el día t y se **cobra** el día `t + processing_days` (si es `sin_datos`, se
  exige `--assume`). Para los horizontes cuenta la fecha de cobro.
- `max_payouts`, techo acumulado y transición a Live → evento terminal `to_live` (§0).
- Retirar baja el colchón: con `lock_after_first_payout`, un payout puede dejar la cuenta a un mal día de
  la rotura. El motor lo mide (vector T9); no lo suaviza.

## 5. Tarifas y ciclo de intentos

| Tarifa | Modelo |
|---|---|
| Evaluación por suscripción | `amount` cada `period_days` días naturales mientras la evaluación siga activa: cargos en los días `0, P, 2P, …` estrictamente anteriores al fin; n.º de cargos = `ceil(d_fin / P)` con `d_fin ≥ 1` |
| Evaluación de pago único | `amount` al empezar el intento |
| Reset | `amount` al reiniciar tras rotura, si la política elige reset en lugar de comprar |
| Activación | al pasar, antes de la fase financiada |
| Datos y plataforma | mensual mientras haya alguna cuenta viva |
| Payout fee | por payout |

**Política de intentos** (`attempt_policy`): al fallar una evaluación o perder una financiada →
`replace` (nueva evaluación o reset, la más barata permitida), mientras `bankroll_disponible ≥ coste` y
`cuentas_vivas < max_accounts`. Sin bankroll → `ruined` (no se compran más intentos).

## 6. Simulación Monte Carlo

1. **Calendario:** días de sesión CME desde `start_date` (defecto: el lunes siguiente), con
   `discovery.calendars.cme_holidays`; los horizontes se miden en días naturales.
2. **Remuestreo de días:** *stationary bootstrap* (Politis-Romano) sobre el pool ordenado por fecha, con
   longitud media de bloque `ℓ = arch.bootstrap.optimal_block_length(pnl_diario)["stationary"]`
   (mínimo 1). Los índices se generan con `numpy.random.Generator(PCG64(seed))` propio, no con el objeto
   de arch, para controlar la semilla.
3. **Números aleatorios comunes (CRN):** la misma secuencia de días para todas las cuentas de un camino
   (están correlacionadas: misma estrategia, mismos días) y para todos los programas que se comparan.
4. **Prioridad del pool:** `forward` > `oos` > `is`; el informe dice qué fracción viene de cada fuente.
   Pool con menos de 60 días con operaciones → aviso "muestra corta".
5. **Error MC:** `n_paths` por defecto 20.000; se informa `SE(EV) = sd/√n` y Wilson al 95 % para cada
   probabilidad. Si `SE(EV) > max(25 USD, 0,05·|EV|)` se dobla `n` hasta 200.000.
6. **Rachas:** distribución de la racha máxima de días perdedores y de operaciones perdedoras por camino,
   comparada con la observada en el pool.

## 7. Escenarios, ventaja mínima y métricas

### 7.1 Desplazamiento de la ventaja

Se desplaza el P&L de **cada operación** en δ USD por contrato: en `marks`, cada marca posterior al
cierre de la operación k suma `k·δ` (el orden se conserva). `mean_net` = media del P&L neto por
operación en el pool; `LCB95` = cota inferior al 95 % de esa media por stationary bootstrap (2.000
réplicas).

| Escenario | δ por operación | Costes | Uso |
|---|---|---|---|
| Optimista | 0 | medidos | solo referencia |
| Base | `−0,5 · mean_net` (si `mean_net > 0`) | medidos | lectura central |
| **Conservador** | `LCB95 − mean_net` | ×1,25 | **decisión** |
| Estrés severo | `−mean_gross` (ventaja bruta 0) | ×1,5 y +1 tick por lado | supervivencia |
| Sin ventaja | `−mean_gross` | medidos | línea base de **convexidad de las reglas** |

El haircut de 0,5 es una **estimación** de la caída fuera de muestra (orden de magnitud de la literatura
de anomalías publicadas); es configurable y se imprime.

### 7.2 Ventaja mínima rentable μ\*

`μ* = mean_net + δ*` con `EV_H(δ*) = 0`, por bisección en δ con CRN (EV es creciente en δ salvo ruido
MC; se comprueba la monotonía en 9 puntos). Se informa en USD/operación/contrato y en R
(`/ risk_usd` medio). Es el **objetivo de MDE** para la investigación de cada programa.

### 7.3 Métricas por programa × escenario × horizonte (30/90/180/365)

| Grupo | Métricas |
|---|---|
| Valor | EV neto, mediana, P5, P95, P(neto > 0), ROI = EV / tarifas esperadas |
| Probabilidades (por intento) | P(pasar), P(financiada), P(primer payout \| financiada), P(≥ k payouts), P(rotura) por regla (MLL, DLL, plazo, cumplimiento), P(`to_live`) |
| Tiempos | tiempo hasta pasar, hasta el primer payout (condicional), vida esperada de la financiada |
| Costes | coste por cuenta financiada, coste por payout, coste esperado de reemplazo, pérdida antes del primer payout |
| Capital | capital requerido = P95 de la salida de caja acumulada máxima; P(ruina del bankroll) |
| Flujo | retiro neto mensual = EV_H · 30 / H; anual = EV_365 |
| Atribución | EV(estrategia) − EV(sin ventaja) |

Cada probabilidad se presenta en dos columnas: **observada** (libro real, §9; "Sin datos" si n = 0) y
**modelo**.

**Regla de lectura del informe (no decide, informa):** "apto para considerar" solo si
`EV_conservador(180) > 0`, `P(ruina) < 5 %` con el bankroll dado, ninguna regla caducada (ADR-F09) y el
error MC dentro de §6.5.

## 8. Esquema YAML del programa

`config/prop_economics/programs/<firma>_<programa>_<tamaño>.yaml` (clave de enlace: `firm_id` de
`config/propfund/firms.yaml`). Cada valor numérico lleva `status` ∈ {`verified`, `verified_repo`,
`discrepancia`, `sin_datos`, `assumed`} y `source: {url, consulted_at}`.

```yaml
schema_version: 1
program_id: topstep_50k_combine_xfa
firm_id: topstep
rules_version: "2026-11-25.1"
consulted_at: 2026-11-25
expires_after_days: 30
instrument_unit: micro            # micro | mini
phases:
  evaluation:
    start_balance: {value: 50000, status: verified_repo}
    profit_target: {value: 3000, status: verified_repo}
    max_loss: {mode: trailing_eod, amount: 2000, check: realtime_unrealized, lock_at: start_balance, status: verified_repo}
    daily_loss: {amount: 1000, action: pause_day, enabled: false, optional: true, status: verified_repo}
    consistency: {max_best_day_fraction: 0.55, basis: total_profit, on_violation: raise_target, status: verified_repo}
    min_trading_days: {value: 2, status: verified_repo}
    max_contracts: {mini: 5, micro: 50, status: verified_repo}
    flat_by: {value: "15:10 America/Chicago", status: verified_repo}
  funded:
    start_balance: {value: 0, status: verified_repo}
    max_loss: {mode: trailing_eod, amount: 2000, lock_at: 0, lock_after_first_payout: true, status: verified_repo}
    scaling_plan: {status: sin_datos}
    payout:
      eligibility: {template: winning_days, n: 5, min_day_profit: 150, status: verified_repo}
      max_fraction_of_balance: {value: 0.5, status: verified_repo}
      cap_per_payout: {value: 2000, alt: 5000, status: discrepancia}
      min_amount: {value: 125, status: verified_repo}
      split: {value: 0.90, status: verified_repo}
      processing_days: {status: sin_datos}
fees:
  evaluation: {type: subscription, amount: 49, period_days: 30, status: verified_repo}
  activation: {amount: 149, status: verified_repo}
  reset: {status: sin_datos}
  data_platform_monthly: {status: sin_datos}
commissions_per_side: {MNQ: {status: sin_datos}, NQ: {status: sin_datos}}
sources:
  - {url: "https://help.topstep.com/en/articles/8284197", consulted_at: 2026-11-25}
  - {url: "https://help.topstep.com/en/articles/8284233", consulted_at: 2026-11-25}
  - {url: "https://help.topstep.com/en/articles/14289835", consulted_at: 2026-11-25}
```

`verified_repo` = verificado por el laboratorio el 2026-11-25 según
`NASDAQ_EDGE_INSTITUTIONAL/01_RESEARCH/Prop_Firm_Rules.md §1`; **no** re-verificado en esta sesión. Con
`expires_after_days: 30`, el motor deja de aceptarlo el **2026-12-25**.

## 9. Libro real (separado)

`data/prop_economics/ledger.db` (SQLite, fuera de git). Tabla `ledger_events(id, ts, account_id,
firm_id, program_id, event, amount_usd, evidence_path, note)` con `event` ∈ {`fee_paid`, `reset_paid`,
`activation_paid`, `account_passed`, `account_failed`, `payout_requested`, `payout_approved`,
`payout_received`, `to_live`}. Solo la escribe un comando manual del operador
(`lab propecon ledger add …`); el simulador no tiene acceso de escritura.

## 10. Vectores de prueba (exactos)

Calculados por Claude con una cadena de Markov resuelta como sistema lineal (absorción), no por
simulación. Un trade por día, `marks = [0, ±W]`, sin DLL, sin consistencia, sin días mínimos, sin plazo,
S = 0, D = 2.000, T = 3.000. El motor de simulación debe acercarse con `n_paths = 200.000` y horizonte de
2.000 días de sesión: **tolerancia ±0,004** (≈ 4 errores estándar). Los motores exactos de prueba deben
dar el valor con `abs < 1e-9`.

| ID | Regla | W / pérdida | p(ganar) | P(pasar) |
|---|---|---|---:|---:|
| T1 | `static` | +500 / −500 | 0,50 | **0,4** (= D/(D+T)) |
| T2 | `static` | +500 / −500 | 0,55 | **0,637586** |
| T3 | `static` | +500 / −500 | 0,45 | **0,191266** |
| T4 | `trailing_eod`, `lock_at = 0` | +500 / −500 | 0,50 | **0,273067** (= 4.096/15.000) |
| T5 | `trailing_eod`, sin bloqueo | +500 / −500 | 0,50 | **0,262144** (= 0,64³) |
| T6 | `trailing_eod`, `lock_at = 0` | +500 / −500 | 0,55 | **0,454480** |
| T7 | `trailing_eod`, `lock_at = 0` | +1.000 / −500 | 1/3 (ventaja 0) | **0,277285** (`static`: **0,387582**) |

Lectura de T4 frente a T1: con la misma ventaja nula, el trailing EOD baja P(pasar) de 0,40 a 0,27.

Vectores deterministas (S = 0, κ = 1):

| ID | Entrada | Esperado |
|---|---|---|
| T8 | Un día `marks = [0, +1500, −600]`, D = 2.000 | `trailing_intraday`: **rotura** (pico 1.500 → L = −500; −600 ≤ −500). `trailing_eod` (L = −2.000): sigue, B = −600. `static`: sigue. DLL 1.000 `pause_day`: no se activa |
| T9 | Financiada: 5 días de +300 (B = 1.500), `winning_days` n=5 ≥150, fracción 0,5, cap 2.000, mín. 125, split 0,9, `lock_at = 0`, `lock_after_first_payout` | Payout el día 5: w = **750**, recibido **675**, B = 750, L = 0. Día 6 con −800 → e = −50 ≤ 0 → **rotura**. Antes del payout el umbral era min(1.500 − 2.000, 0) = −500 |
| T10 | Consistencia c = 0,5, T = 3.000: días +2.000, +1.100, +900 | Día 2: P = 3.100 < max(3.000, 4.000) → no pasa. Día 3: P = 4.000 ≥ 4.000 → **pasa** |
| T11 | Suscripción 49 USD / 30 días; la evaluación acaba el día natural 30, 31 y 61 | **1, 2 y 3** cargos (49, 98, 147 USD) |
| T12 | Intentos independientes: P(pasar) = 0,4, tarifa única 100, activación 150, payout neto por financiada fijo 900 | EV por intento = −100 + 0,4·(900 − 150) = **+200**; coste por financiada = 100/0,4 + 150 = **400** |
| T13 | DLL 1.000 `pause_day`, `static` D = 2.000, `marks = [0, −400, −1.000, +500]` | el día cierra en **−1.000**; la marca +500 se descarta; no es rotura |
| T14 | Propiedad (hypothesis): cualquier camino | `L` no decrece; `B_t − B_{t−1} = κ_t·marks_t[−1]` salvo DLL/rotura; tarifas ≥ 0; `recibido ≤ w` |

## 11. Interfaz y CLI

```python
run_ev(pool: Sequence[DayPath], program: Program, *, policy: SizingPolicy, attempt_policy: AttemptPolicy,
       bankroll_usd: float, horizons=(30, 90, 180, 365), scenarios=("base", "conservative", "stress",
       "zero_edge", "optimistic"), n_paths=20_000, seed=42, start_date=None, assume: dict | None = None
      ) -> EvReport
break_even_edge(pool, program, *, horizon=180, scenario="conservative", ...) -> BreakEven
```

CLI en un sub-app propio (no en el cuerpo de `cli.py`): `lab propecon run --program <id> --pool
<parquet> --bankroll 1500 --seed 42`, `lab propecon breakeven …`, `lab propecon programs` (lista y
caducidad), `lab propecon ledger add|show`. Informe en `reports/prop_economics/<fecha>-<programa>.md`
con la cabecera de suposiciones, la fecha de las reglas y la etiqueta **SIMULADO** en cada tabla.

## 12. Riesgos del modelo

| Riesgo | Efecto | Mitigación |
|---|---|---|
| Orden pico→valle dentro de la vela | P(rotura) algo **sobreestimada** | conservador a propósito; con datos de ticks se reconstruye el orden real |
| Pool corto o de IS | EV inflado | prioridad forward/OOS; escenario conservador decide |
| Reglas caducadas o en discrepancia | EV sin base | ADR-F09; `discrepancia` exige `--assume` |
| Independencia entre días | colas infravaloradas | stationary bootstrap con bloque óptimo |
| Convexidad de las reglas | EV > 0 sin ventaja | métrica de atribución; los términos de las firmas pueden prohibir estrategias de "todo o nada" |
