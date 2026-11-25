# COLA NQEDGE-FORWARD · NASDAQ_EDGE: de 22 variantes históricas a 3 variantes en forward

**Creada:** 2026-11-25 por Claude. **Decisión del operador (2026-11-25):** "Forward, pocas variantes".
**Proyecto:** `NASDAQ_EDGE_INSTITUTIONAL/`. **Modo:** cadena continua F0 → F6, sin pedir confirmación.
**No suma al contador:** no se calcula ningún rendimiento, ni histórico ni forward. Las 3 pruebas se
registrarán solo en la evaluación final (F7, en el futuro, con aprobación del operador).

## 1. Motivo (revisión de Claude, solo lectura)

Las familias A-E son los componentes de confluencia del EA `us100-ftmo1`. Lo muestra
`src/tradinglab/ea_us100_engine.py` (`DEF`):
- `trade_start=935` y `trade_end=1130`: misma ventana de entrada que el proyecto;
- `or_end=945` y modo `ORB_RETEST`, con `fb_window=6`: el retest en ≤ 6 velas del modelo A;
- `use_pd`/`use_on` y `sweep_window=12`: el modelo B;
- `vwap_ext_sd=2.0`: el modelo C;
- FVG con `htf_min=15`: el modelo D;
- RVOL, `rr=2.0` y BE a 1R;
- la misma regla de SL primero cuando SL y TP caen en la misma barra.

El laboratorio ya ha mirado esta lógica en **toda** la historia disponible:
- NQ 2010-2017: el EA sobre NQ, en `reports/ea/us100-ftmo1-nq-2010-2017.md`;
- Dukascopy 2012-2021: TL3 T7, **no confirma**;
- US100 2021-2026: el periodo de diseño del EA, que coincide con OOS-1 y OOS-2 del proyecto.

Ningún tramo histórico es una prueba limpia. **Solo los datos nuevos lo son.** En forward, que los
parámetros vengan del EA ya no contamina nada, porque los datos de evaluación todavía no existen.

## 2. Reglas

- Las de `AGENTS.md`: solo paper/demo; ninguna orden; no activar bots ni F13; no tocar `.env`; no
  borrar archivos; sin push; nada de tareas programadas sin autorización del operador; los agentes no
  usan `record-informal`.
- **Prohibido:** calcular P&L, expectativa, PF, win rate o cualquier resultado de las variantes, en el
  histórico o en el forward, antes de F7. Sí se permiten **conteos** de señales, tamaños de stop y
  contratos (mecánica), sin el desenlace de las operaciones.
- OOS-2 (2024-01-01 → 2026-11-20) sigue sellado. Las descriptivas del DEV ya calculadas quedan como
  están; no se amplían.
- No se modifica nada fuera de `NASDAQ_EDGE_INSTITUTIONAL/`, salvo el `git add` de esa carpeta.
- Si falta un dato (p. ej. la comisión): **Sin datos**, y el bloque que lo necesita se marca
  `bloqueado: falta <dato> del operador`.

## 3. Bloques

### F0 · Versionar lo existente
1. Añade `__pycache__/` al `.gitignore` del proyecto si no está cubierto.
2. `git add NASDAQ_EDGE_INSTITUTIONAL` y commit `nqedge: fases A-B tal como estaban (antes de la
   decision forward)`. Este commit fija la hora del sellado y del borrador de hipótesis.
3. Hash SHA-256 de `01_RESEARCH/Strategy_Hypotheses.md` en el mensaje del commit.

### F1 · Contaminación declarada
En `02_DATA/Data_Quality.md` §2.8 sustituye "Contaminación previa" por:
- la tabla de coincidencias EA ↔ familias de §1 de esta cola;
- los tres usos previos de la historia: NQ 2010-2017 con el EA; Dukascopy 2012-2021 con T7
  (`TL3_REPORTS/ea_oop_dukascopy.md`, no confirma); 2021-2026 como periodo de diseño del EA;
- la frase: "OOS-1 y OOS-2 no son fuera de muestra para estas familias".

En `README.md` del proyecto: la fase C histórica queda **sustituida por forward** (decisión del
operador 2026-11-25). Las 22 variantes no se ejecutan ni se registran.

Commit `nqedge: F1 - contaminacion declarada`.

### F2 · Tres variantes congeladas
Claude las elige **sin ver resultados** (no ha leído las descriptivas del DEV). El criterio es tener
mecanismos distintos y pocas condiciones, y poder emitirse como alerta:

| ID | Familia | Variante exacta (de `Strategy_Hypotheses.md`) | Mecanismo |
|---|---|---|---|
| **NQF-A** | A · NY Open Breakout | OR de **15** min; entrada al **cierre de ruptura** (sin retest) | continuación |
| **NQF-B** | B · Liquidity Sweep | nivel **ON** (ONH/ONL); confirmación **cierre dentro** | reversión tras barrido |
| **NQF-C** | C · VWAP | **reversión** (fuera de VWAP ± 2σ y cierre dentro, objetivo VWAP); **sin** filtro F | reversión a la media |

Reglas comunes, las de `Strategy_Hypotheses.md` con estos cambios:
- **Noticias:** en días FOMC no hay entradas. En días con un Tier 1 dentro de la sesión, se cierra a
  mercado 5 min antes del evento. Topstep exige estar sin posición ±5 min con NQ.
- **Riesgo:** **MNQ**, 150 USD por operación. Contratos = floor(150 / (stop_pt × 2 USD + costes)); si
  sale 0 → NO TRADE.
- **Costes:** comisión MNQ por contrato y lado = **input del operador** (si falta, `bloqueado`).
  Slippage 1 tick por lado, con estrés de 2 y 4.
- **Datos forward:** M1 de `US100.cash` en MT5, attach-only, con el login verificado antes y después,
  como proxy de precio de NQ durante **toda** la prueba (declarado, sin cambiar de fuente a mitad).
  Volumen: no se usa (VWAP con tick volume, marcado como proxy).

Implementación:
- `tools/forward_models.py` con funciones puras por variante y tests sintéticos en
  `tests/test_forward_models.py`: ruptura, barrido, reversión al VWAP, SL primero en la misma vela,
  NO TRADE, bloqueo FOMC y cierre antes de un Tier 1.
- Hash SHA-256 del código y de los tests en el prerregistro. **Cualquier cambio posterior = variante
  nueva con fecha de inicio nueva.**

Commit `nqedge: F2 - tres variantes congeladas`.

### F3 · Mecánica histórica (solo conteos, sin desenlaces)
Sobre el DEV (NQ CME 2010-2018 y Dukascopy 2019-2021), sin mirar ningún resultado. Para cada
variante y año:
- señales por día;
- % de días con señal;
- mediana y p90 del stop en puntos y en ticks;
- % de NO TRADE por tamaño;
- operaciones bloqueadas por noticias.

Con eso, estima la **fecha esperada** para llegar a n = 200 operaciones por variante, empezando en
F5. Informe `04_FORWARD/mecanica.md`. Commit `nqedge: F3 - mecanica`.

### F4 · Prerregistro forward
Escribe `04_FORWARD/prerregistro.md`:
- Inicio: primera sesión NYSE completa después del commit de F4. Sin fecha de fin; termina al llegar
  a **n = 200** operaciones cerradas por variante (cada una por separado).
- Tamaño y potencia:
  - con SL de 1R y TP de 2R, sin parciales, sd ≈ √(p(1−p)) × 3 ≈ 1,4 R (aproximación: C y B apuntan
    al VWAP y no se afina sin mirar desenlaces);
  - con α = 0,05/3 y una potencia del 80 %, el MDE es (2,13 + 0,84) × 1,4 / √200 ≈ **0,29 R**;
  - un efecto real menor de ~0,3 R puede quedar sin detectar, y "no confirma" no lo descarta.
- **Una sola evaluación por variante**, al llegar a n = 200. Antes **no se mira** ningún resultado:
  los informes intermedios solo dan número de operaciones y fechas.
- Criterio por variante, con 3 pruebas (Bonferroni α = 0,05/3):
  - (a) media neta de R con 1 tick > 0 y t unilateral ≥ 2,13;
  - (b) media neta con 2 ticks por lado > 0;
  - (c) informativo: Monte Carlo Topstep 50K sobre la secuencia de R, frente a la línea base de
    ventaja cero con la misma regla de riesgo (método de `TL3_REPORTS/propfund_zero_edge.md`).
- Veredicto literal: "confirma" / "no confirma". Sin reinterpretación ni cambio de variante.
- Contador: en F7, el operador registra 3 pruebas (`TL3-NQF-A/B/C`) **antes** de evaluar.
- Indicador Pine (fase E): puede mostrar las señales de NQF-A/B/C con la etiqueta "en forward, sin
  validar". El estado global sigue siendo `NO EDGE VALIDATED`.

Commit `nqedge: F4 - prerregistro forward` (hash del prerregistro en el mensaje).

### F5 · Registro diario (sin resultados)
1. `tools/forward_daily.py`:
   - lee las M1 del día cerrado (MT5 attach-only, login verificado);
   - aplica el código congelado;
   - añade a `04_FORWARD/ledger.csv` (append-only) por operación: variante, fecha, hora, lado,
     entrada, stop, objetivo, contratos, motivo de salida y R neto con 1, 2 y 4 ticks;
   - guarda el hash del código en cada fila.
2. El script **no** imprime ni resume R, PF ni medias. Su salida es solo "n por variante" y la fecha
   estimada para llegar a 200.
3. Ejecución: manual una vez al día. Una tarea programada solo si el operador la autoriza
   expresamente; el agente no la registra.
4. Test: un día sintético produce exactamente las filas esperadas y no imprime métricas.

Commit `nqedge: F5 - registro diario`.

### F6 · Cierre y aviso
- `ruff`, tests del proyecto, `pytest -q` completo y `lab doctor`.
- README del proyecto y PLAN: una línea.
- Tag `nqedge-forward-start`.
- Resumen a Telegram (`lab telegram send --file`; si no hay Telegram, `lab alerts send`). Formato
  **Hecho / 1..N / Aviso / Siguiente**, con:
  - las tres variantes y sus hashes;
  - la fecha de inicio;
  - la fecha estimada para n = 200;
  - los bloqueos (p. ej. la comisión).
- Fin de la cola.

### F7 · Evaluación (futuro; no se ejecuta en esta cola)
Cuando una variante llegue a n = 200:
1. el operador registra las 3 pruebas;
2. se evalúa una vez con el prerregistro de F4;
3. informe y veredicto literal.
