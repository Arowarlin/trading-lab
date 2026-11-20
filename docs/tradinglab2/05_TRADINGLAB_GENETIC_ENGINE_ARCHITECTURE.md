# 05 · Motor genético multiobjetivo con integridad estadística

Módulos: `discovery/genetic.py` (operadores), `discovery/nsga2.py` (selección), `discovery/fitness.py`,
`discovery/campaigns.py` (registro estadístico). Todo en un **proceso aparte** con límites de recursos.

## 1. El problema estadístico (lo más importante)

Un GA evalúa miles de reglas. Si cada una cuenta como prueba independiente, el DSR global de TradingLab
(hoy N = 1.060) se vuelve inalcanzable para siempre; si no cuentan, es *data snooping*. El diseño resuelve
ambos con **tres tramos de datos sellados por instrumento** y **N honesto por tramo**:

```
 |---------- DESCUBRIMIENTO (IS) ----------|---- SELECCIÓN (OOS-1) ----|==== HOLDOUT SELLADO (OOS-2) ====|---- FORWARD DEMO ----|
   el GA evoluciona aquí                     solo para elegir finalistas   1 lectura por finalista          tiempo real
   (fitness con WF interno anclado)          nunca para mutar               N = nº de finalistas (≤ 5)
```

Reglas:

1. **Corte fijo por campaña** (fechas + hash del trozo, reutilizando el mecanismo de `campaign.py`): el GA
   **no puede leer** OOS-1 ni OOS-2. El cargador de datos de `discovery` recibe solo el rango IS; un test
   lo comprueba.
2. **Cada ejecución genética es UNA campaña registrada** con `N_total` = presupuesto de evaluaciones
   declarado **antes** de correr (como `register_campaign`). Se guarda en la tabla nueva `disc_campaigns`
   y se informa siempre junto al resultado.
3. **N efectivo** (`fitness.effective_trials`): las miles de reglas están muy correlacionadas. Se agrupan
   los retornos diarios de los individuos evaluados por correlación (clústeres jerárquicos, umbral 0,7) y
   el nº de clústeres es el N efectivo para el DSR **de exploración**. Se reporta N bruto y N efectivo.
4. **Selección en OOS-1**: de la frontera de Pareto final (IS) se eligen como máximo **K = 5 finalistas**
   por instrumento con reglas fijas (ver §5). OOS-1 no se usa para mutar ni reoptimizar.
5. **Confirmación en OOS-2 (holdout sellado)**: una única lectura por finalista. El DSR de confirmación
   usa **N = nº de finalistas leídos**, que es pequeño, y por eso puede ser significativo. Esa lectura
   cuenta en `count_tests` (contador global) como hoy.
6. **Contador global intacto**: `count_tests` suma la campaña completa (N_total) y las lecturas del
   holdout, igual que las campañas actuales. El informe muestra los tres DSR: exploración (N efectivo),
   confirmación (N finalistas) y global (histórico del laboratorio). **Producción exige el de
   confirmación ≥ 0,90 y el global documentado**; nunca se oculta el global.

## 2. Representación genética

El genotipo es el AST del doc 04. Operadores (`genetic.py`), todos producen ASTs válidos o se descartan
antes de evaluar:

| Operador | Qué cambia |
|---|---|
| `mutate_param` | Un parámetro dentro de su rango (paso discreto declarado por el bloque) |
| `mutate_block` | Sustituye un indicador/nivel por otro del mismo tipo de salida |
| `mutate_threshold` | Umbral ±1 paso |
| `mutate_logic` | `and`↔`or`, añade o quita un `not`, añade/quita una condición (respeta `max_nodes`) |
| `mutate_exit` | Tipo de stop/target, mult ATR, RR, BE, trailing, salida por tiempo |
| `mutate_session` | Ventana de entrada ±15 min dentro de la sesión de la plantilla |
| `crossover_subtree` | Intercambia subárboles de entrada del mismo tipo entre padre y madre |
| `crossover_exit` | Hereda el bloque de salida completo del otro progenitor |

Inicialización: mezcla de (a) plantillas del doc 04 con huecos aleatorios, (b) hipótesis de IA traducidas
a AST (doc 07), (c) aleatorias válidas con profundidad ≤ 2.

## 3. Fitness multiobjetivo (NSGA-II) — solo con datos IS

Objetivos (todos calculados con código determinista sobre IS con **walk-forward interno anclado**, 4
pliegues; el fitness es la mediana de los pliegues de test, no el ajuste completo):

| # | Objetivo | Sentido |
|---|---|---|
| 1 | Expectativa neta en R tras costes del perfil de coste **conservador** (p75 del spread) | max |
| 2 | Estabilidad: % de pliegues con expectativa > 0 y desviación entre pliegues | max |
| 3 | Max drawdown en R | min |
| 4 | Complejidad (nº de nodos + nº de parámetros) | min |
| 5 | Sensibilidad al coste: caída de expectativa con +1 punto/tick | min |

**Restricciones duras** (si fallan, el individuo es no factible y no puede compensarse con otra métrica):
operaciones IS ≥ 100 y ≥ 15 por pliegue; ninguna operación individual > 20 % del beneficio total
(concentración); sin barras con datos inválidos según `datacheck`; tiempo medio en mercado coherente con
la sesión; coste relativo spread/ATR de la ventana ≤ `COST_ATR_MAX` (reutiliza `campaign.cost_atr`).

Selección: ordenación no dominada + distancia de *crowding* (NSGA-II, Deb 2002). **Elitismo**: la frontera
de rango 1 pasa entera (hasta `elite_frac`). **Diversidad**: si dos individuos tienen correlación de
retornos diarios > 0,9, el peor se penaliza (nicho); además distancia estructural del AST (Jaccard de
nodos) para evitar clones. **Control de bloat**: objetivo 4 + límite duro `max_nodes`.

## 4. Configuración y presupuestos (`config/discovery/engine.yaml`)

| Perfil | Población | Generaciones | Evaluaciones aprox. | Uso |
|---|---|---|---|---|
| `small` | 60 | 15 | ~900 | Probar plantillas, minutos |
| `medium` | 150 | 30 | ~4.500 | Una plantilla/instrumento, ~1 h |
| `large` | 300 | 50 | ~15.000 | Nocturno, varias plantillas |

Tasas por defecto: mutación 0,3 por individuo, crossover 0,6, `elite_frac` 0,1, torneo binario sobre
(rango, crowding). Justificación: valores estándar de NSGA-II para poblaciones pequeñas; el usuario puede
cambiarlos y **el valor usado se guarda en la campaña** (no se puede cambiar a mitad). Límite de tiempo y
de evaluaciones: el que llegue antes detiene la campaña de forma limpia.

## 5. Regla de finalistas (fija y pre-registrada)

Tras la última generación, sobre la frontera de rango 1 en IS:
1. Filtrar factibles con **expectativa IS completa > 0** y expectativa IS > 0 en ≥ 3 de 4 pliegues.
2. Evaluar en OOS-1 (sin tocar parámetros). Quedan los de expectativa OOS-1 > 0 y PF > 1,1.
3. Ordenar por expectativa OOS-1 penalizada por complejidad y elegir **K ≤ 5** con correlación entre sí < 0,7.
4. Robustness Lab (doc 07) sobre IS+OOS-1. Los que lo pasan → **una** lectura del holdout sellado.

## 6. Genealogía (`disc_lineage`)

Por individuo: generación, `parent_a`, `parent_b`, operador, diff de parámetros (JSON), fitness vector,
rango, crowding, motivo de selección o descarte. Permite reconstruir el árbol completo de cualquier finalista.

## 7. Recursos (Ryzen 9 5950X, 64 GB)

`ProcessPoolExecutor` con `max_workers = 12` (deja 4 núcleos para MT5, el EA, `ai_trader` y LM Studio),
prioridad de proceso *below normal* en Windows, datos IS en `numpy` compartidos por memoria
(`multiprocessing.shared_memory`), límite de RAM por campaña (8 GB por defecto) comprobado con `psutil`
si está instalado o con el tamaño de los arrays si no. La GPU (RX 6800) queda para el LLM local; el GA no
la usa.
