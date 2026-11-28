# FUT-RISK-2 · Diseño del Optimal Risk & Payout Allocation Engine (ORPAE)

**Estado:** diseño (Paso 5). **Implementación:** solo tras validación y autorización (Paso 10), por
OpenCode con **DeepSeek V4.1 Flash**. Se construye **encima** del motor EV de FUT-A
(`docs/futures/04_SPEC_PROP_EV.md`) y del PFIE
(`docs/futures/research/propfirms_2026-11/12_PROP_FIRM_INTELLIGENCE_ENGINE.md`). Independiente de
NinjaTrader 8: produce **recomendaciones**, no órdenes.

## 1. Entradas y salidas

| Entrada | Origen |
|---|---|
| Pool de `DayPath` por estrategia y su procedencia (forward > OOS > IS) | backtests/forward con costes reales |
| μ, σ, cota inferior al 95 % (stationary bootstrap), n, agrupamiento de pérdidas | `prop_economics.stats` |
| Programas vigentes de cada firma y modo de ejecución (`automated` / `automated_conditional` / `semi_manual`) | `config/prop_economics/` |
| Presupuesto real del proyecto (USD) y tolerancias (P(ruina) máx., mediana mín.) | operador |

| Salida | Contenido |
|---|---|
| `AllocationRecommendation` | por firma × programa × estrategia: riesgo por operación (USD y contratos MNQ/NQ), número de cuentas, política de payout, peldaño de la escalera de evidencia, EV/mediana/P5/P95/P(ruina) a 6/12/24 m, reglas que limitan y supuestos |
| `RiskLimits` | topes duros que leen RiskCheck y los tickets semimanuales |
| Informe auditable | entradas con hash, semilla, versión del motor, todas las cifras etiquetadas **SIMULADO** |

## 2. Algoritmo

1. **Calidad estadística:** cota inferior `μ_LCB` (stationary bootstrap, 5.000 réplicas). Si
   `μ_LCB ≤ 0` → peldaño 0 (solo forward/paper).
2. **Rejilla de políticas:** riesgo fijo {12,5; 25; 37,5; 50} % del MLL; adaptativo por colchón
   `min(r_max, κ·colchón)`; tamaño mínimo 1 micro; techo = `max_contracts` del programa y escalado.
3. **Simulación** con el motor FUT-A, números aleatorios comunes entre políticas y firmas, horizontes
   126/252/504 sesiones; ventaja desplazada a `μ_LCB` (escenario de decisión) y a μ (referencia).
4. **Selección:** maximizar EV(12 m) con las restricciones `mediana > 0`, `P(ruina del presupuesto,
   24 m) ≤ ε` (defecto 10 %) y `P(neto > 0) ≥ 60 %`. Empate → menor capital requerido (P95).
5. **Cartera:** número de cuentas a la vez dentro del presupuesto. Las cuentas con la misma estrategia
   cuentan como **una sola apuesta**. La diversificación solo cuenta si la correlación de los P&L diarios
   es < 0,3, medida en forward.
6. **Revisión:** recalcular con cada lote nuevo de forward. Subir de peldaño solo si sube `μ_LCB`; bajar
   si cae. Nunca por una racha.

## 3. Controles automáticos (tests obligatorios, Paso 8)

| Control | Test |
|---|---|
| Riesgo por operación ≤ autorizado | propiedad: ninguna recomendación supera `RiskLimits` |
| Sin exposición duplicada | dos cuentas con la misma estrategia suman su riesgo en `exposure_by_underlying` |
| Contratos dentro del programa | `max_contracts` y escalado aplicados; 1 NQ = 10 MNQ |
| Sin aumento tras pérdidas | propiedad: tras una pérdida el riesgo recomendado no sube (antimartingala) |
| Valor del tick | NQ 5,00 · MNQ 0,50 · ES 12,50 · MES 1,25 · GC 10,00 · MGC 1,00 USD (`instruments.py`) |
| Reglas caducadas | el motor se niega a usarlas sin `--assume` |
| Costes incluidos | un pool sin comisión o slippage → error "Sin datos", nunca 0 |
| Modo de ejecución | una firma `semi_manual` solo recibe tickets; nunca una orden automática ni un copiador |

## 4. Tareas para OpenCode (tras FUT-A6)

| ID | Tarea | Ficheros | Aceptación |
|---|---|---|---|
| FUT-O1 | `stats`: stationary bootstrap (Politis-Romano) y `μ_LCB` | `prop_economics/stats.py` + tests | cobertura del IC ≈ 95 % en 1.000 réplicas sintéticas AR(1) |
| FUT-O2 | Kelly binario/continuo, Kelly fraccionario y Optimal f como **diagnóstico** | `prop_economics/sizing_diag.py` | Kelly(p = 0,452, W = 1,45, L = 1,05) = 0,0552 ± 1e-4 |
| FUT-O3 | Políticas de tamaño (fija, por colchón, mínimo 1 micro, topes) | `prop_economics/policies.py` | propiedades de §3 con hypothesis |
| FUT-O4 | Rejilla y selección con restricciones | `prop_economics/allocate.py` | reproduce la tabla de `01 §4.1` (±2 SE) con el pool sintético de `risk_sim.py` |
| FUT-O5 | Multicuenta correlada/independiente con números aleatorios comunes | `prop_economics/portfolio.py` | reproduce `01 §4.3` (±2 SE) |
| FUT-O6 | Informe y CLI `lab propecon allocate` | `prop_economics/report.py` | todas las tablas etiquetadas SIMULADO |
