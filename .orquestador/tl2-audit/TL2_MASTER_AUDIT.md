# TL2 · Auditoría maestra de TradingLab

**Fecha:** 2026-11-24 · **Commit inspeccionado:** `98d2a49` (`master` = `feature/prop-fund-multifirm`)
**Autor:** Claude (arquitecto). **Implementa:** OpenCode con DeepSeek V4.1 Flash.
**Documentos:** este (diagnóstico y prioridades) · `TL2_QUANT_AUDIT.md` (costes y estadística, con demostraciones) · `TL2_ARCHITECTURE.md` (mapa, arquitectura objetivo, tecnologías) · `TL2_OPENCODE_TASKS.md` (tareas, aceptación, rollback). Evidencia reproducible en `evidencia/`.

## 0. Qué se inspeccionó y qué no

| Inspeccionado (código actual) | No accesible (dato: **Sin datos**) |
|---|---|
| `discovery/` completo: `fastbt`, `costs`, `fitness`, `engine`, `nsga2`, `genetic`, `campaigns`, `levels`, `robustness`, `drift`, `guard`, `basket` | Contenido de `data/discovery.db` y `data/lab.db` (están en el PC del operador) |
| `stats.py` (DSR), `propfund/` (`firms.yaml`, `costs.yaml`, `protected.py`, `router.py`) | Resultados forward reales del EA y de `ai_trader` |
| `ea_us100_engine.py` (modelo de costes), `reports/audit/ea_us100_m5_only.md` | Fills reales de MT5 (TCA) |
| Specs y resultados de todas las campañas en `.orquestador/` | Datos de mercado (caché Parquet) |

Dos afirmaciones se demostraron ejecutando código: el doble cobro del spread (`evidencia/prueba_spread_fastbt.py`) y la falta de potencia estadística (`evidencia/potencia_validacion.py`). El resto procede de la lectura del código, citada por archivo y línea.

## 1. Diagnóstico en una frase

**TradingLab no está encontrando ventajas sobre todo por dos motivos que no son de búsqueda: el motor de costes sobrecarga cada operación, y la cadena de validación casi no puede aprobar una ventaja real de tamaño realista.** El resultado "0 finalistas" no distingue entre "no hay ventaja" y "hay ventaja, pero el sistema no puede verla". Añadir algoritmos de búsqueda (GA más grande, Optuna, RL) empeoraría el problema, porque aumentaría los falsos positivos sin arreglar ninguna de las dos causas.

## 2. Hallazgos críticos (P0)

### P0-1 · El spread se cobra dos veces en las salidas que no son por objetivo
- **Dónde:** `discovery/fastbt.py:222-235`, `:317-333` y `:381-404` construyen `stop_bps = entry_bps = comisión + slippage + spread`. `_core` (`:735-790`, `:838-935`, `:950-975`) y `_calendar_core` (`:991-1190`) cobran `entry_bps + stop_bps` en las salidas por stop, tiempo, señal y fin de sesión. `discovery/costs.py:399-407` (`CostBook.apply`) repite el mismo patrón.
- **Por qué es un error:** las barras son BID (`fetch_dukascopy`: `side="BID"`; MT5 también). Un largo compra al ASK y vende al BID: un solo spread. Un corto vende al BID y recompra al ASK: también uno solo. El código cobra dos.
- **Demostración** (`evidencia/prueba_spread_fastbt.py`): precio plano, spread 2 bps, sin comisión ni slippage. Salida por tiempo, largo y corto: **coste cobrado 4,0 bps, coste real 2,0 bps**. La salida por objetivo cobra un solo spread, así que esa ruta es correcta.
- **Impacto:** sobrecarga de un spread completo por operación en todas las plantillas con salida por tiempo o por stop: fix de divisas, cambio de mes, rebote, Donchian y momentum. El efecto se suma a otros dos sesgos pesimistas (P1-1 y P1-2). **Produce falsos negativos, no falsos positivos.**
- **Error de signo contrario, menor:** el stop de un corto se comprueba con el máximo BID (`fastbt.py:842`; igual en `:1102`), cuando lo dispara el ASK. Demostración: con el ASK por encima del stop y el BID por debajo, el modelo no sale (sale 8 barras después, por tiempo). Es un sesgo optimista de hasta un spread en el disparo.
- **Referencia correcta que ya existe en el repo:** `ea_us100_engine.py:13,134-158` modela bien BID/ASK (el largo entra en `open + spread`, el corto sale en `max(sl, open + spread)`) con el spread histórico de cada barra. El motor de Discovery debe adoptar esa convención.

### P0-2 · La cadena de validación no tiene potencia para ventajas realistas
- **Dónde:** tramos fijos para todas las temporalidades (`engine.yaml:124-127`: OOS-1 de 12 meses, OOS-2 desde 2025-07); `min_trades_oos2: 30`; nivel 4 (`levels.py:164-182`) como conjunción de unas 12 puertas, entre ellas DSR ≥ 0,90 y percentil al azar ≥ 95 **solo sobre OOS-2**.
- **Simulación** (`evidencia/potencia_validacion.py`; R por operación ~ N(ventaja, 1); solo OOS-1 y OOS-2, sin contar IS, deriva, PBO, WF ni régimen, que solo restan):

| Operaciones/año | Ventaja 0,10 R: P(aprobar) | Ventaja 0,20 R: P(aprobar) | Sin ventaja: P(aprobar) |
|---:|---:|---:|---:|
| 12 (cambio de mes) | **0,00** (imposible: OOS-2 nunca llega a 30) | 0,00 | 0,000 |
| 50 | 0,15 | 0,45 | 0,024 |
| 250 | 0,50 | 0,98 | 0,013 |
| 1.000 | 0,96 | 1,00 | 0,004 |

- **Lectura:**
  - Para estrategias D1 o de calendario, el sistema **no puede** aprobar nada, haya ventaja o no.
  - OOS-1 como filtro de signo apenas discrimina a baja frecuencia: con 12 operaciones aprueba al 45 % de las estrategias sin ventaja y al 58 % de las que tienen 0,10 R. **Las `r9b-tom` descartadas por OOS-1 de −0,20 a −0,41 R estaban dentro de ±1 error estándar** (≈ 0,29 R con 12 operaciones). No es evidencia en contra; es ruido.
  - Ese descarte se mantiene (la regla estaba registrada), pero el protocolo debe cambiar para campañas nuevas.
- **Problema de datos y supuestos, no de código:** el defecto no es un bug. Es un diseño de validación sin cálculo de potencia previo.

### P0-3 · El sistema no mide su propia tasa de error
No existe un arnés que inyecte ventajas conocidas en datos reales o sintéticos y mida cuántas recupera el pipeline (falsos negativos) ni cuántas fabrica sin ventaja (falsos positivos). Sin eso, cualquier cambio de umbral, nuevo o viejo, es opinión. **Es la primera tarea a construir** (T01), y la que permitirá cambiar el protocolo sin rebajar el rigor.

## 3. Hallazgos de alto impacto (P1)

| ID | Hallazgo | Evidencia | Efecto |
|---|---|---|---|
| P1-1 | **Slippage no medido.** EURUSD y GBPUSD cargan 0,5 pip por lado y USDJPY 0,5 pip, copiados de `config/ai_trader.yaml global.slippage_price` | `config/propfund/costs.yaml:42,52,57`; `engine.yaml assumed_slippage` | En EURUSD con spread p75 de 0,2 pip, el slippage supuesto de ida y vuelta (1,0 pip) es **5 veces el spread**. Probable sobrecoste. Hay fills reales de demo (`mt5_fills.py`, `tca.py`) que no se usan para calibrar |
| P1-2 | **Spread p75 usado como coste esperado.** p75 es una cifra de estrés, no la esperanza | `fastbt.py:267-270` (`use_p75`), `costs.py:199` | La expectativa neta queda sistemáticamente sesgada a la baja |
| P1-3 | **Costes anacrónicos.** El spread medido en 2026 y el swap de 2026 se aplican a 2010–2024. Con tipos cercanos a 0 entre 2013 y 2021, el swap de un largo en índices era mucho menor | `swap.yaml` (medido el 2026-11-23); `costs.yaml measured_at` | Sesgo pesimista en estrategias D1 que duermen posiciones (cambio de mes, rebote, momentum). Dukascopy trae ASK histórico que no se usa para el spread |
| P1-4 | **Selección del mejor dentro del frente.** En rejilla, solo pasa el frente de Pareto (`engine.py:415-457`). La hipótesis no tiene un parámetro primario prerregistrado | Specs `q*`, `r9b*` | Mezcla prueba de hipótesis con optimización. Lo correcto es probar una especificación primaria y usar la rejilla para comprobar que hay una meseta |
| P1-5 | **Futuros `.v.0` sin ajuste de vencimientos.** Los cambios de contrato crean saltos de precio falsos | `RESULTADO-F10c.md`, `fetch_databento.py` | Cualquier campaña de futuros en D1 o H4 vería retornos falsos en cada vencimiento |
| P1-6 | **Reglas FTMO de fuente secundaria.** El objetivo, la pérdida diaria y la máxima de FTMO citan `app.luxalgo.com` (`verified_secondary`) | `config/propfund/firms.yaml:56-61` | Los simuladores de P(pasar) dependen de reglas sin verificar. Además, la pérdida diaria de FundingPips como max(balance, equity) sigue pendiente en los simuladores |
| P1-7 | **El activo con más evidencia no está en el proceso.** El EA `us100-ftmo1` tiene 476 operaciones en backtest, +0,32 R por operación y PF 1,48 con modelo BID/ASK correcto, pero solo `DSR local` y forward informal | `reports/audit/ea_us100_m5_only.md` | El mayor valor esperado está en validar y mejorar lo que ya muestra señal, no en buscar desde cero. Su año 2023 (+3,5 R) muestra que depende del régimen |
| P1-8 | **El contador global de 1.883 pruebas mezcla familias heterogéneas** (lecciones de IA, Optuna antiguo, GA en M5, rejillas D1). En Discovery solo es informativo: `levels.py:819` lo reporta y el DSR de confirmación usa K finalistas | `learning.count_tests`, `levels.py:396-438` | No sesga resultados, pero no sirve como corrección de pruebas múltiples. Hace falta contabilidad por familia de hipótesis (T23) |

## 4. Respuestas a las 18 preguntas

1. **Estado real.** Infraestructura amplia y bien probada (unos 1.800 tests, 108.000 líneas). Un motor de Discovery con controles de integridad excelentes (prerregistro, guard, OOS sellado, control de deriva). **Pero un modelo de costes sesgado y una validación sin potencia.** Ninguna estrategia de Discovery ha llegado a nivel 4. El único activo con señal es el EA del operador.
2. **Fortalezas.** Contabilidad de pruebas con miradas informales; guard que impide calcular rendimiento sin aprobación; snapshots con hash de dataset y configuración; control contra entradas al azar con la misma deriva (sólido para separar ventaja de beta); calendarios NYSE y CME; tests de lookahead y de paridad; reglas de firmas con fuente y versión.
3. **Debilidades.** Costes (P0-1, P1-1 a P1-3); diseño de validación (P0-2, P1-4); ausencia de autoevaluación del pipeline (P0-3); módulos dispersos (`cli.py` de 12.020 líneas, tres motores de backtest con convenciones distintas, 18 módulos que ningún otro módulo importa).
4. **Por qué encuentra pocas ventajas.** Por orden de peso: (a) potencia insuficiente para el tamaño de efecto realista; (b) costes inflados, entre 1,5 y 2,5 veces según el instrumento, estimación a confirmar en T10–T12; (c) los efectos publicados ya están muy arbitrados (McLean y Pontiff: en acciones rinden un 58 % menos tras publicarse). El código de búsqueda no es la restricción.
5. **¿Discovery está suficientemente desarrollado?** Como infraestructura, sí. Como método, no: le faltan la puerta de potencia, la especificación primaria, la prueba de familia (SPA) y la confirmación secuencial en forward.
6. **Qué limita la calidad.** Muestra efectiva por hipótesis (pocas operaciones, un solo instrumento, historia recortada a 2018 en specs D1 aunque hay datos desde 2013) y costes.
7. **¿Errores en costes?** Sí: doble spread (demostrado), stop de corto optimista (demostrado), slippage supuesto sin medir, p75 como esperanza, spread y swap anacrónicos. La comisión por lote de FundingPips está bien tratada (`round_turn` → factor 0,5 por lado, `fastbt.py:307`).
8. **¿La validación es fiable?** Contra falsos positivos, sí: es muy conservadora, con un falso positivo de la cadena OOS por debajo del 2,5 % simulado. Contra falsos negativos, no. A baja frecuencia es una moneda al aire o directamente imposible.
9. **Qué falta para CFD.** Modelo BID/ASK correcto; spread histórico por barra (Dukascopy ASK); slippage desde fills; swap histórico; reglas FTMO verificadas de fuente oficial.
10. **Qué falta para futuros.** Series ajustadas por vencimiento o negociación por contrato con regla de cambio; comisiones reales de Topstep/ProjectX (marcadas "pendientes de verificar" en `06_TRADINGLAB_DATA_AND_COST_AUDIT.md`); validación de calidad intradía. **Hoy ninguna estrategia de futuros puede considerarse validada.**
11. **Qué falta para FTMO y FundingPips.** Reglas FTMO de fuente primaria; FundingPips max(balance, equity) en los simuladores; versionado con fecha efectiva (existe `rules_version`; falta histórico de cambios).
12. **Tecnologías que merecen entrar.** Pocas. El test SPA de Hansen con bootstrap estacionario (paquete `arch`, ya maduro) y el SPRT para forward, que son métodos más que librerías. Lo demás (vectorbt, Nautilus, Lean, Qlib, FinRL, Optuna, Ray, GPU) no resuelve la restricción actual. Detalle en `TL2_ARCHITECTURE.md §5`.
13. **Nuevas capacidades.** Arnés de autoevaluación (T01); puerta de potencia (T20); familias multi-instrumento (T30); confirmación secuencial en demo (T24). El motor de régimen, la optimización de cartera y la "inteligencia de hipótesis" con LLM son P3: no tienen sentido sin al menos dos estrategias validadas.
14. **Mayor impacto.** T10 (costes BID/ASK), T01 (arnés), T20+T21+T22 (protocolo con potencia) y T41 (validar el EA con el protocolo nuevo).
15. **Lo que no merece la pena.** Más algoritmos de búsqueda; GPU (la RX 6800 en Windows no tiene un ROCm práctico para este stack); RL; reescribir el backtester en otro framework; un "motor de régimen" genérico; más plantillas de indicadores sin hipótesis económica.
16. **Arquitectura objetivo.** Un solo modelo de ejecución BID/ASK compartido por Discovery, EA lab y forward; un registro de experimentos por familia; validación en tres etapas (desarrollo, holdout único sellado, forward secuencial). Ver `TL2_ARCHITECTURE.md §4`.
17. **Orden óptimo.** Fase 0: T00–T02 → Fase 1: costes (T10–T13) → Fase 2: protocolo (T20–T24) → Fase 3: datos para potencia (T30–T32) → Fase 4: reevaluación y EA (T40–T42) → Fase 5: firmas (T50) → Fase 6: limpieza (T60–T63).
18. **Cómo verificaremos cada mejora.** Cada tarea trae pruebas sintéticas con resultado calculado a mano, una comparación antes/después sobre un conjunto fijo de campañas de referencia (reproducción con `cost_model_version` anterior y nueva) y, para cambios de protocolo, el arnés T01: **el protocolo nuevo debe tener P(aprobar | sin ventaja) ≤ el actual y mayor P(aprobar | ventaja)**. Claude revisa el diff, ejecuta la evidencia y firma el RESULTADO.

## 5. Impacto en el plan de búsqueda vigente

- La regla de parada del 14 de diciembre partía de la premisa "si nada pasa, no hay ventaja". **Esa premisa no se sostiene** mientras los costes estén inflados y la validación no tenga potencia.
- Recomendación, que decide el operador: no lanzar campañas nuevas hasta cerrar T10 (costes) y T01+T20 (arnés y potencia). Después, reevaluar Q3 y el fix de divisas con costes v2, y cambiar la regla de parada de una fecha a un número de campañas con potencia suficiente bajo el protocolo v2.
- **Lo que no cambia:** nada de lo ya registrado se borra ni se reescribe. Las campañas viejas conservan su versión de costes y protocolo. Las reevaluaciones son campañas nuevas y suman al contador.

## 6. Protección de componentes (orden del operador del 2026-11-24)

El operador retiró la protección de `us100-ftmo1`, `ai_trader`, el carril forward FTMO, el riesgo FTMO, Prop Fund y `ea_lab`. **T00 la sustituye por control de cambios.** El manifiesto deja de bloquear y pasa a registrar qué cambió, con baseline, prueba de regresión y tag de rollback. Se mantienen dos distinciones que no son protección sino hechos técnicos: (a) un EA externo corre en MT5 con su propio motor, y el router de Prop Fund no debe enviarle órdenes; (b) solo demo/paper, sin órdenes reales ni activación automática.

## 7. Tabla de prioridades

| Prioridad | Mejora | Problema que resuelve | Impacto esperado | Dificultad | Dependencias | Responsable |
|---|---|---|---|---|---|---|
| P0 | T00 Protección → control de cambios | Orden del operador; deja la trazabilidad | Permite mejorar EA, IA y riesgo | Baja | — | Claude diseña · OpenCode implementa |
| P0 | T01 Arnés de autoevaluación (ventaja inyectada / nulo) | No se conoce la tasa de error del pipeline | Base objetiva para todo cambio de umbral | Media | — | Claude · OpenCode |
| P0 | T10 Ejecución BID/ASK en `fastbt` y `CostBook` | Doble spread; stop de corto optimista | Coste correcto en todas las campañas | Media | T01 (regresión) | Claude · OpenCode |
| P0 | T20 Puerta de potencia en preflight | Campañas imposibles de aprobar | Ahorra presupuesto y evita conclusiones falsas | Baja | T01 | Claude · OpenCode |
| P1 | T11 Spread histórico por barra (Dukascopy ASK) | Spread de 2026 aplicado a 2010 | Coste fiel a cada época | Media | T10 | Claude · OpenCode |
| P1 | T12 Slippage medido desde fills | 0,5 pip supuesto en FX | Coste calibrado con la realidad | Media | T10 | Claude · OpenCode |
| P1 | T13 Swap histórico | Swap de 2026 aplicado a 2013 | Estrategias D1 sin sesgo | Media | T10 | Claude · OpenCode |
| P1 | T21 Especificación primaria + rejilla de meseta | Selección del mejor del frente | Menos pruebas y más honestas | Media | T01 | Claude · OpenCode |
| P1 | T22 Holdout único con test de consistencia | OOS-1 sin potencia | Validación con potencia declarada | Media | T01, T20 | Claude · OpenCode |
| P1 | T23 SPA de Hansen / Romano-Wolf por familia | Pruebas múltiples dentro de la rejilla | Control de error por familia | Media | T21 | Claude · OpenCode |
| P1 | T24 Confirmación forward con SPRT | Forward sin regla de parada | Decisión demo con error controlado | Media | — | Claude · OpenCode |
| P1 | T30 Familias multi-instrumento | Pocas operaciones por hipótesis | Más potencia sin más pruebas | Media | Cesta N2 | Claude · OpenCode |
| P1 | T31 Futuros ajustados por vencimiento | Saltos falsos en los cambios de contrato | Futuros utilizables | Media | — | Claude · OpenCode |
| P1 | T41 EA us100-ftmo1 bajo protocolo v2 + forward vs backtest | El activo con señal está fuera del proceso | Mayor valor esperado del proyecto | Media | T10, T24 | Claude · OpenCode |
| P1 | T50 Reglas de firmas verificadas y versionadas | FTMO secundario; FundingPips max(bal, eq) | P(pasar) correcta | Baja | — | Claude · OpenCode |
| P2 | T40 Reevaluar fix de divisas y Q3 con costes v2 | Descartes con costes inflados | Puede reabrir la única ventaja bruta real | Baja | T10–T12, T22 | Operador aprueba · OpenCode ejecuta |
| P2 | T42 Informe ai_trader frente a su gemela aleatoria | Coste del carril IA sin beneficio medido | Congelar o mantener con datos | Baja | — | Claude · OpenCode |
| P2 | T02 Copia automática de `discovery.db` | Contador y holdout sin respaldo | Integridad del registro | Baja | — | OpenCode |
| P2 | T60–T63 Limpieza (código muerto, `cli.py`, motores, README) | Mantenibilidad y coste de tokens | OpenCode más rápido y fiable | Media | T10 | Claude · OpenCode |
| P3 | Régimen, cartera, inteligencia de hipótesis, scheduler | — | Solo con ≥ 2 estrategias validadas | Alta | Fases 1–4 | Más adelante |
