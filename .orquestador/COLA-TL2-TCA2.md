# COLA TL2-TCA2 · Slippage decisión → ejecución de verdad: llamadores y lectores de la TCA

**Creada:** 2026-11-25 por Claude a petición del operador ("Sí, prepárala"). Sigue al parche
`e02ad7e` (tags `tl2-tca-pre`/`tl2-tca-post`).
**Tipo:** cambio en **componentes de producción** (`ai_trader`, el carril forward y los lectores de
riesgo y coste). Protocolo completo de `AGENTS.md`.
**Autorización:** solo se ejecuta si el mensaje que la lanza contiene literalmente
`APRUEBO CAMBIO DE PRODUCCIÓN TL2-TCA2`.
**Modo:** cadena continua T0 → T7, sin pedir confirmación.

## 1. Problema (revisión de Claude, solo lectura)

| # | Dónde | Hoy | Consecuencia |
|---|---|---|---|
| P-1 | `ai_trader.py:2277`: `broker.submit_market(...)` | No pasa `signal_price` | La TCA toma como "señal" el tick que lee al entrar en `submit_market`, milisegundos antes de enviar. **No mide** el tramo de la propuesta de la IA (`row["entry"]`) a la ejecución, que D5b midió en 0,44 bps de mediana |
| P-2 | `forward_intraday.py:1539` | No pasa `signal_price`, aunque la decisión tiene `entry` (el precio de la señal, `ForwardDecision.price`) | Lo mismo en el carril forward |
| P-3 | `ai_trader.py:3205` (`_slippage_avg`), `ai_distill.py:1260`, `tca.py:164` (`build_tca`, web y `lab tca`), `drift.py` y `discovery/slippage_measured.py:289/363` | Promedian **todas** las filas | Las 66 filas anteriores al parche (slippage 0 por construcción) diluyen la media durante mucho tiempo |
| P-4 | `e02ad7e` | Además de la TCA, cambia la **ejecución**: la orden usa un tick que se vuelve a leer justo antes de `order_send`, y hay comprobaciones nuevas de distancia de SL/TP que pueden rechazar órdenes | Cambio de comportamiento sin un test que lo cubra por separado |

**Nota operativa:** los procesos de demo que ya están corriendo (`ai_trader`, forward) cargaron el
código antiguo. **Ni el parche `e02ad7e` ni este hacen efecto hasta que el operador los reinicie.**
Esta cola **no** reinicia ni activa nada.

## 2. Reglas

- `AGENTS.md` completo:
  - solo demo; ninguna orden;
  - no activar, reiniciar ni parar bots, `ai_trader`, forward ni F13;
  - no tocar `.env`;
  - sin push; no borrar archivos;
  - commits por ruta.
- **Protocolo de producción, en este orden y sin excepción:**
  1. locks;
  2. **tag `tl2-tca2-pre` sobre el HEAD actual ANTES de tocar código** (en `tl2-tca` el código entró
     primero: no se repite);
  3. `lab propfund baseline --reason`;
  4. código y tests;
  5. CHANGELOG;
  6. baseline posterior;
  7. tag `tl2-tca2-post`.
- **Locks:** `proyecto-prod-tca2`, `changelog-produccion` y `protected-manifest`. Se liberan al final.
- **Filas antiguas:** nunca se modifican ni se borran. Se distinguen por una columna nueva.
- **Contador:** esta cola no crea campañas ni pruebas. Se comprueba que `informal_trials` y las
  campañas de discovery que **no** son `edge1-`/`edge2-` no cambian entre el inicio y el final.
  `count_tests` puede subir por EDGE-1/EDGE-2, que corren en paralelo.

## 3. Bloques

### T0 · Cola, locks, tag y baseline
- `git add -f .orquestador/COLA-TL2-TCA2.md`; commit `tl2-tca2: cola`.
- Locks de §2. `git tag -a tl2-tca2-pre HEAD -m "tca2: estado previo"`.
- `lab propfund baseline --reason "TL2-TCA2: signal_price desde ai_trader y forward; lectores de TCA solo v2; autorizado por el operador 2026-11-25"`.
- Escribe `.orquestador/BASELINE-prod-tca2.md` con los hashes previos de los ficheros que se van a
  tocar.

### T1 · Versión de la TCA (sin tocar filas)
- `db.py::_migrate_tca`: añade la columna `tca_version INTEGER`, de forma idempotente y sin
  actualizar filas. Las antiguas quedan en NULL (= v1).
- `tca.record_fill` escribe `tca_version = 2` en todas las filas nuevas, desde MT5 y desde el broker
  paper.
- Tests:
  - la migración es idempotente;
  - las filas antiguas siguen intactas (mismo hash del contenido);
  - una fila nueva lleva 2.

### T2 · Los llamadores pasan el precio de la decisión
- **`ai_trader.py`:** `signal_price=float(row["entry"])` (precio de la propuesta). Antes de enviar,
  se registra también la antigüedad de la propuesta, si existe el dato.
- **`forward_intraday.py`:** `signal_price=entry` (precio de la señal de la decisión).
- **`operator.py` y `cli.py`** (órdenes manuales del operador): **no** se cambian; su "señal" sigue
  siendo el tick al enviar y se documenta así.
- **Broker paper** (`execution/paper.py`): acepta `signal_price` opcional con la misma semántica,
  para que un llamador común no falle según el broker.
- **`slippage_probe.py`:** no se cambia; mide su propio slippage.
- Tests de regresión para `ai_trader` y forward, con un broker falso:
  - el `signal_px` registrado es `row["entry"]` / `entry`, y no el tick de envío;
  - sin `signal_price`, el comportamiento es idéntico al de `tl2-tca-post`.

### T3 · Los lectores ignoran las filas v1
- En `ai_trader._slippage_avg`, `ai_distill` (1260), `tca.build_tca`, `drift.py` y
  `discovery/slippage_measured.py`, filtra `tca_version >= 2`.
- Si quedan menos filas que su mínimo actual (`MIN_FILLS` = 5 en `tca.py`, o el que use cada lector),
  el lector devuelve **"sin datos"** igual que hoy, y el consumidor usa su supuesto configurado. No se
  inventa un valor intermedio.
- Tests:
  - con 66 filas v1 a 0 y 6 filas v2 a 2,0 bps, la media es 2,0, no 0,16;
  - con solo filas v1, el resultado es "sin datos".

### T4 · P-4: cubrir el cambio de ejecución de `e02ad7e`
Tests propios para `MT5Broker.submit_market`:
- la orden usa el tick releído;
- un SL a exactamente `stop_distance` pasa;
- un SL a `stop_distance − 1 point` se rechaza con `MT5Error`;
- con el tick de envío igual al de entrada, el comportamiento coincide con `tl2-tca-pre`.

Si alguno revela un rechazo que el código antiguo no hacía en un caso legítimo, se informa como
**riesgo** en el CHANGELOG. No se cambia la regla sin autorización.

### T5 · CHANGELOG y baseline posterior
- Entrada en `docs/CHANGELOG-produccion.md` con:
  - la autorización literal;
  - P-1 a P-4;
  - qué no cambia;
  - los tests;
  - la **nota de reinicio** (los procesos en marcha siguen con el código viejo hasta que el operador
    los reinicie);
  - la vuelta atrás con `tl2-tca2-pre`.
- `lab propfund verify` debe listar solo los ficheros tocados. Después,
  `lab propfund baseline --reason "TL2-TCA2: aplicado; ver CHANGELOG 2026-11-25"`.

### T6 · Cierre
- `ruff check`, `pytest -q` completo, `lab doctor` y `lab propfund verify`.
- Comprobación del contador de §2.
- README y PLAN con una línea, bajo el lock `readme-plan`. Fila nueva en `ESTADO.md` §3:
  "TCA v2 aplicada; pendiente reinicio del operador".
- Commit por ruta `tl2-tca2: cierre` y tag `tl2-tca2-post`. Libera los locks.

### T7 · Aviso
- Telegram (o `lab alerts send`) con el formato **Hecho / 1..N / Aviso / Siguiente**:
  - ficheros cambiados y tests;
  - número de filas v1 y v2;
  - **"reinicio pendiente del operador"**;
  - vuelta atrás.
- **PARA.**
