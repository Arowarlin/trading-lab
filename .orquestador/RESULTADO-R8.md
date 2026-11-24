# RESULTADO · R8 — reloj del EA, control vs deriva, calendario CME, LF

Fecha: 2026-11-23. Sesión única en `E:\trading-lab`, rama
`feature/prop-fund-multifirm`. Sin push, sin campañas (register/approve/run/
confirm/supersede), sin OOS, sin operar, sin tocar MT5 en esta fase, sin tareas
programadas y sin activar bots.

## 1. Reloj del forward del EA

Comando nuevo:

```text
lab ea forward-reset BOT --start YYYY-MM-DD --reason "..." --approved-by-operator
```

Sin `--approved-by-operator` no cambia nada (test). Con el flag cambia el reloj,
conserva criterios y `criteria_hash`, y deja un evento en `lifecycle_events` con
el motivo y la autorización literal del operador.

Antes:

| Campo | Valor |
|---|---|
| Estado | incubando |
| Inicio | 2026-11-16 |
| Fin ventana | 2027-01-15 |
| Hash criterios | f490642ba7a1f71b |
| n_trades | 2 (fills viejos 11-16/11-18) |

Ejecutado para `ea:us100-ftmo1` con `--start 2026-11-23` y motivo
`EA v3.2 instalado 2026-11-23; fills v3 del 11-16/11-18 excluidos`.

Después:

| Campo | Valor |
|---|---|
| Estado | incubando |
| Inicio | 2026-11-23 |
| Fin ventana | 2027-01-22 |
| Frozen at | 2026-11-23T18:21:44.769+00:00 |
| Hash criterios | f490642ba7a1f71b |
| n_trades | 0 |

Los fills antiguos no se borraron: quedan fuera de la ventana porque los
informes filtran por `start_date`. El evento registrado es:

```text
from_state=incubando to_state=incubando actor=operador
reason=EA v3.2 instalado 2026-11-23; fills v3 del 11-16/11-18 excluidos |
autorización: OPERADOR 2026-11-23: "Sí, reiniciar hoy". EA v3.2 instalado y
verificado; fills v3 del 11-16/11-18 excluidos.
```

`lifecycle_bots`/`lifecycle_events` no forman parte de los grupos protegidos de
`lab propfund verify`; no hubo que re-sellar el manifiesto. `verify` sigue en
4 OK.

## 2. Control contra deriva (`test_vs_random_direction`)

Módulo nuevo `src/tradinglab/discovery/drift.py`:

- 1.000 simulaciones por estrategia, semilla fija derivada de
  `sha256(campaign_id)` (misma secuencia para todas las estrategias de la
  campaña).
- Entradas aleatorias sobre las mismas velas IS, con el mismo número de
  operaciones y la misma proporción de compras/ventas que la estrategia.
- Mismo stop en ATR y mismo tiempo medio en mercado. El control no replica el
  objetivo: sale por stop o al vencer el horizonte, para no acortar el tiempo en
  mercado por objetivos que la estrategia sí tiene.
- Expectativa neta (costes del perfil base de la campaña) frente a la
  distribución aleatoria. El percentil se guarda en `metrics.drift` de la
  evaluación y se muestra en `discovery results` como `Pctl deriva`.

Puerta de selección en `_rank1_candidates`: exige percentil ≥ 90 para pasar a
candidata. Si la evaluación no trae `drift` (campañas anteriores), no se aplica.

Marca de versión: las campañas nuevas reales incluyen
`config.controls.test_vs_random_direction` con `version=1`, `simulations=1000`
y `percentile_min=90`; eso cambia el `config_hash`. Las campañas existentes no
tienen la marca, no se recalculan y conservan su estado (test explícito). Las
campañas sintéticas de la prueba de ruido (`register_synthetic`) se registran
sin la marca para no invalidar el criterio histórico de esa prueba; el control
sí se ejercita en las campañas reales y en los tests directos.

Tests:

- Deriva pura (siempre largo en una serie con tendencia): percentil **50,6**,
  no pasa.
- Ventaja sintética (compras tras caída, rebote fuerte): percentil **100**,
  pasa.
- Campaña antigua sin marca: `drift=None`, sin percentil y estado intacto.
- Campaña nueva: la marca activa 1.000 simulaciones y umbral 90.
- `_rank1_candidates` descarta 55,0 y acepta 95,0; sin `drift` no filtra.
- `discovery results` muestra el percentil guardado.

Validación informativa (sin escribir en la BD) sobre las campañas existentes,
1.000 simulaciones, semilla derivada del id de campaña, coste base y
expectativa neta:

| Campaña | Estrategias | Percentil mediana | Rango | Estrategia 478 |
|---|---:|---:|---|---:|
| n2-donchian-xauusd-h4 | 27 | 72,5 | 29,1–99,3 | **70,3** |
| c1-asia-usdjpy-h1-long | 27 | 0,3 | 0,0–2,3 | — |

Detalle de 478: 361 operaciones, 48,48 % largos, 21,64 barras medias IS,
expectativa neta −0,0213 R/op, mediana aleatoria −0,0570 R/op, percentil 70,3.
Con el umbral 90 habría quedado fuera de candidatas.

**Sobre el ~8 esperado:** el informe C2 usó un benchmark distinto: entradas
aleatorias **solo largas**, expectativa **bruta** y semilla 20261123. Con ese
método, 478 da percentil ≈ 10,6 % (media aleatoria +0,1207 R/op frente a
+0,0414 bruto de la estrategia), del mismo orden que el 7,9 % citado. El control
nuevo aplica la regla aprobada en R8 (misma proporción largos/cortos y neto), por
eso el número cambia a 70,3. No se escribió nada en la BD ni se reclasificó la
campaña.

## 3. Calendario CME (Globex) 2010-2030

Añadido en `src/tradinglab/discovery/calendars.py`, sin tocar
`nyse_calendar.py`:

- Cierres completos del índice CME: Año Nuevo, Viernes Santo, Memorial,
  Juneteenth (desde 2022), 4 de julio, Labor, Acción de Gracias y Navidad, con
  observados.
- Sesiones cortas (hora de Nueva York): víspera del 4 de julio y Nochebuena a
  las 13:00; día después de Acción de Gracias a las 13:15. Si la Nochebuena
  observada es festivo, no se marca como sesión corta.
- MLK y Presidents no cierran el índice CME (los productos de tipos tienen su
  propio horario y no se mezclan).
- La fuente `databento` usa `calendar=cme` en `data_sources` y
  `source_quality`; la pausa diaria sigue viniendo de `engine.yaml`.

D1 Databento antes (F10c) y después:

| Símbolo | Antes | Después |
|---|---|---|
| US100 | FAIL · 4.241 filas · 52 huecos · sin calendario | WARN · 4.241 filas · 7 huecos (0,165 %) · cme |
| US500 | FAIL · 4.241 · 52 | WARN · 4.241 · 7 |
| US30 | FAIL · 4.246 · 51 | WARN · 4.246 · 5 |
| XAUUSD | FAIL · 4.237 · 57 | WARN · 4.237 · 7 |
| EURUSD | FAIL · 4.241 · 52 | WARN · 4.241 · 7 |
| GBPUSD | FAIL · 4.241 · 52 | WARN · 4.241 · 7 |
| USDJPY | FAIL · 4.241 · 52 | WARN · 4.241 · 7 |

`usable-from --source databento` para D1: antes no había año válido y no se
escribió clave; ahora los 7 símbolos dan **2010-06-06** con estado `warn`. No se
escribió `usable_from` en `engine.yaml` (no había autorización para tocar
configuración). No se cambiaron umbrales.

## 4. `.gitattributes` y LF

Creado `.gitattributes` con `* text=auto eol=lf` y binarios marcados
(`parquet`, `db`, `sqlite`, `ex5`, `ex4`, `png`, `jpg`, `pdf`, `zip`, `npy`,
`pkl`, `dll`, `exe`, etc.).

Comprobación en seco con índice temporal (`git read-tree HEAD` +
`git add --renormalize -u .`): solo aparecen los 14 archivos tracked editados en
R8; **ningún archivo protegido** y ningún archivo existente cambia solo por
EOL. Aplicado.

## 5. Verificación

- `ruff check src/tradinglab tests docs`: limpio.
- `pytest -q`: **1758 passed, 1 skipped** (20:41).
- `lab propfund verify`: **4 OK**.
- `count_tests`: **1730**.
- Sin push, sin campañas, sin OOS, sin órdenes.

## Commits y tag

```text
86bd87d  tl2: R8 - reloj EA, control vs deriva, calendario CME, LF  (tl2-r8)
```

`git status --short` queda solo con `?? tl2-edge-map.patch`, el parche previo
del operador.

## Avisos

- El percentil de 478 bajo la regla R8 es 70,3, no ~8: el ~8 procede del
  benchmark C2 de entradas solo largas y brutas. Bajo la regla aprobada (misma
  proporción de lados y neto), 478 también queda por debajo del umbral 90.
- El control compara la expectativa neta con el coste base de la campaña; la
  evaluación principal puede usar el `cost_book` de varias cuentas. El número
  queda guardado junto al percentil para que sea trazable.
- El control añade ~0,2–0,6 s por estrategia después de compilar numba; solo
  afecta a campañas nuevas con la marca.

PARA.
