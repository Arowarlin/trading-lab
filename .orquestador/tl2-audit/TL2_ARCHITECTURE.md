# TL2 · Mapa actual, arquitectura objetivo y tecnologías

## 1. Inventario (commit `98d2a49`)

| Bloque | Líneas | Estado | Comentario crítico |
|---|---:|---|---|
| `discovery/` (49 módulos) | 24.800 | Implementado, con tests | Núcleo útil. Le sobran el GA como herramienta de validación y le faltan potencia y costes v2 |
| `propfund/` | 7.000 | Implementado, con tests | Registro multiempresa sólido. Reglas FTMO de fuente secundaria |
| `ea_lab/` + `ea_us100_engine.py` | 2.800 + motor | Implementado | Mejor modelo BID/ASK del repo. **Activo con más señal** |
| `execution/` (MT5) | 2.000 | Implementado (demo) | Conexión attach-only |
| `ai_trader.py` y relacionados | ~9.000 | Implementado (demo) | Diseño correcto: se mide contra una gemela aleatoria. Resultados: **Sin datos** en esta auditoría |
| `cli.py` | 12.020 | Funciona | Monolito de 219 comandos. Encarece cada tarea de OpenCode |
| `web.py` + `webui/` | 3.100 + HTML | Funciona | Consola local |
| Módulos de fases antiguas (intel, telegram, journal, research, swing, intraday, campaign…) | ~40.000 | Mezcla | Parte en uso por tareas programadas; parte obsoleta |

**Código que ningún módulo importa** (análisis estático; verificar uso por CLI con cadenas o por scripts antes de mover): `conditioners`, `data.futures`, `data.yahoo`, `discovery.export_samples`, `discovery.indicators_ext`, `discovery.optimizer`, `ea_lab.atr`, `ea_lab.session_data`, `ea_lab.validation`, `execution_model`, `health`, `intel.finnhub`, `overnight_report`, `prop.overlay`, `propfund.router`, `strategies.meanrev`, `strategies.sector_momentum`, `trailing`.

**Duplicados con nombres parecidos:**

| Uno | Otro | Decisión propuesta |
|---|---|---|
| `drift.py` (2.066 líneas, deriva real frente a backtest) | `discovery/drift.py` (control contra el azar) | Mantener los dos y renombrar el segundo a `discovery/random_null.py` |
| `campaign.py` (2.928, sistema antiguo de campañas) | `discovery/campaigns.py` | Mover el antiguo a `legacy/` cuando T60 confirme que no lo usan tareas programadas |
| `backtest.py`, `intraday.py`, `ea_us100_engine.py` | `discovery/fastbt.py` | Un solo modelo de ejecución BID/ASK (T62), con tests de paridad contra el motor del EA |

## 2. Dependencias críticas

```
datos (Dukascopy BID/ASK, MT5, Databento)
   └─ discovery.snapshots (hash) ─┐
propfund.costs (perfiles por cuenta) ─┤
                                       ├─ fastbt (ejecución + costes) ─ fitness ─ engine (rejilla/GA) ─ campaigns/databank
calendars / sessions ─ compiler ───────┘                                                        │
                                                                         levels (OOS-2, DSR, PBO, WF, retos) ─ export_mql5
learning.count_tests ← databank + lab.db (contador)
```

El modelo de costes está en el centro: un error ahí (P0-1) contamina factibilidad, fitness, control de deriva, robustez y confirmación a la vez. Por eso T10 va antes que cualquier otra mejora de Discovery.

## 3. Debilidades de diseño y cómo reemplazarlas

| Diseño actual | Problema | Reemplazo |
|---|---|---|
| `CostPanel` con `entry`, `stop` y `target` en bps, sumados | Mezcla el spread con costes por lado y produce el doble cobro | `ExecutionModel` con precios ejecutables: `bid_t`, `ask_t` (ASK histórico o BID + spread calibrado), `slip_side_t` y `comm_side`. El precio de llenado se calcula; el coste deja de ser un sumando aparte |
| Tramos de calendario fijos para todas las temporalidades | Potencia nula en D1 | Tramos por número de operaciones esperadas, con potencia declarada (T20, T22) |
| Selección del frente de Pareto en rejilla | *Winner's curse* | Primaria prerregistrada y rejilla de meseta (T21) |
| Puertas en conjunción en nivel 4 (~12 condiciones) | Potencia multiplicativamente baja; difícil de razonar | Tres decisiones con error controlado (desarrollo, holdout, SPRT); el resto (PBO, WF, régimen, estrés) se informa como diagnóstico, salvo el estrés de coste ×1,5, que sigue siendo puerta |
| Protección por hash bloqueante | Impedía mejorar lo que ya funciona | Registro de cambios con baseline, regresión y tag (T00) |
| Contador global único | Mezcla familias | Libro de pruebas por familia + SPA (T23); el global se queda como registro |

## 4. Arquitectura objetivo (reducida a lo que aporta)

| Capa | Contenido | Contrato | Estado |
|---|---|---|---|
| Datos | Snapshots BID/ASK con hash; calidad; calendarios; futuros ajustados | `Snapshot(id, hash, bid, ask?, source, usable_from)` | Existe; falta el ASK en el modelo y el ajuste de futuros |
| Ejecución y costes | `ExecutionModel` único para Discovery, EA lab y forward | `fill(side, kind, t, ref_price) → (price, cost_breakdown)` | **Nuevo** (T10–T13) |
| Hipótesis | Spec con hipótesis literal, primaria, meseta, δ y familia | YAML validado por pydantic | Ampliar specs (T21) |
| Evaluación | `fastbt` + control de deriva | `Trades` con desglose de coste por operación | Existe |
| Validación | Potencia → desarrollo → holdout único → SPRT; SPA por familia | `Decision(stage, statistic, threshold, passed, power)` | **Nuevo** (T20–T24) |
| Autoevaluación | Arnés de nulos y ventajas inyectadas | `HarnessReport(P_null, P_edge[δ, freq])` | **Nuevo** (T01) |
| Firmas | Reglas con fuente primaria y fecha efectiva; simulador de reto | `RuleSet(firm, program, effective_from, rules[])` | Existe; falta verificación |
| Registro | `discovery.db` con copia automática y libro por familia | Solo inserciones; campañas inmutables | Existe; falta copia (T02) |
| Producción (demo) | EA, forward FTMO, ai_trader | Separados del motor de investigación; solo demo | Existe |

Aislamiento que se mantiene: Discovery nunca envía órdenes. El forward solo opera en demo. Los resultados históricos son de solo inserción.

## 5. Tecnologías evaluadas

| Tecnología | Qué aportaría | ¿Resuelve la restricción actual? | Decisión |
|---|---|---|---|
| Hansen SPA / Romano-Wolf (métodos; implementación en el paquete `arch`) | Control de error por familia con bootstrap | **Sí** (multiplicidad entre primarias) | **Adoptar** (T23). Coste bajo. Probar en el arnés T01 |
| SPRT de Wald (método) | Regla de parada en forward | **Sí** | **Adoptar** (T24). Sin dependencias |
| Bootstrap estacionario Politis-Romano | IC con dependencia temporal | Sí | Adoptar dentro de T21–T23 |
| CPCV / PBO (López de Prado) | Sobreajuste en selección entre muchas configuraciones | Parcial: con primaria única, poco aplicable | Mantener el PBO existente como diagnóstico |
| vectorbt / backtesting.py | Backtest vectorizado | No: `fastbt` con numba ya cumple, y el problema es el modelo de costes | Descartar |
| NautilusTrader | Simulación por eventos con BID/ASK y libro | Parcial, y con gran coste de integración | Descartar por ahora; reconsiderar solo para futuros intradía |
| QuantConnect Lean | Plataforma completa | No; duplicaría todo | Descartar |
| Qlib / FinRL / RL | Modelos de ML/RL sobre factores | No: más grados de libertad, más falsos positivos con estas muestras | Descartar |
| Optuna, DEAP, Nevergrad, CGP, ES | Más búsqueda | **No: la búsqueda no es el cuello de botella** | Descartar para validación; el GA existente basta para exploración |
| Ray / distribución | Paralelismo multinodo | No: 16 núcleos bastan para estas campañas | Descartar |
| GPU (RX 6800) | Aceleración | ROCm en Windows no es práctico para numba o pandas | Descartar |
| Polars / DuckDB | Lectura más rápida de Parquet | Mejora marginal | P3, solo si el perfilado lo justifica |
| StrategyQuant / Build Alpha | Generación masiva más filtros de robustez | Su enfoque es el que fabrica falsos positivos; sus pruebas de robustez ya existen aquí | No adoptar; ya analizado en `docs/tradinglab2/competitive_research/` |

## 6. Lo que no se construye ahora (y por qué)

- **Motor de régimen genérico:** sin hipótesis que lo use es un filtro más para sobreajustar. Si una hipótesis lo necesita (por ejemplo, momentum solo en alta volatilidad), el régimen entra como parte de esa spec.
- **Optimizador de cartera:** requiere al menos dos estrategias validadas; hoy no hay ninguna. Portfolio Lab ya cubre el cálculo básico.
- **"Inteligencia de hipótesis" con LLM:** las hipótesis buenas salen de la literatura y de la microestructura, no de la generación masiva. Se mantiene el proceso manual documentado (`HIPOTESIS-4-10.md`).
- **Scheduler adaptativo:** las campañas tardan minutos; no hay problema de recursos que resolver.
