# COLA TL2-DIARIO · Suelo diario "mayor de balance o equidad" en el simulador y la protección de riesgo

**Creada:** 2026-11-25 por Claude a petición del operador ("Sí, prepárala").
**Tipo:** cambio en **componentes de producción** (Prop Fund / riesgo: `src/tradinglab/prop/`).
Protocolo de `AGENTS.md`: baseline previo, test de regresión, entrada en
`docs/CHANGELOG-produccion.md` y tag `tl2-diario-pre` antes del primer commit.
**Autorización:** solo se ejecuta si el mensaje del operador que la lanza contiene literalmente
`APRUEBO CAMBIO DE PRODUCCIÓN TL2-DIARIO`. Si no, no se toca nada.
**Arranca:** después de D7 de `COLA-TL3-D.md` (nunca en paralelo con otra cola).
**Modo:** cadena continua P0 → P7. No suma al contador: no hay hipótesis de mercado y todas las
simulaciones son sintéticas o de reglas.

## 1. Problema (verificado por Claude en solo lectura)

| # | Dónde | Qué hace hoy | Qué dice la regla |
|---|---|---|---|
| E-1 | `prop/simulator.py:86-87` (`monte_carlo`) y `:224-225` (`monte_carlo_program`) | Con `daily_loss_mode == "higher_of_balance_or_equity"`: `daily_floor = np.maximum(initial, day_start) - eff_daily`, es decir, usa el balance **inicial** | FundingPips (`config/propfund/firms.yaml:188` y `:239`, panel del operador 2026-11-23): 5 % desde el **mayor de balance o equidad al inicio del día** |
| E-2 | `prop/guard.py:101-103` (`_bases`) | Cualquier modo distinto de `balance` usa `day_start_equity`, así que `higher_of_balance_or_equity` se trata como equidad | Base = `max(day_start_balance, day_start_equity)`. Con pérdida flotante a medianoche (balance > equidad), el suelo real es **más alto** que el de la protección: la protección es más laxa que la firma |
| E-3 | `propfund/snapshots.py:476-486` | Convierte `higher_of_balance_or_equity` en `equity` y lo anota como "algo más laxo" | Igual que E-2 |

**Efecto de E-1.**
- En el modelo diario no hay posiciones abiertas de un día para otro, así que el balance y la equidad
  al inicio del día coinciden con `day_start`.
- Con `initial`, toda cuenta que cae más de un 5 % por debajo del balance inicial cuenta como **rotura
  diaria** aunque ese día pierda muy poco. En la práctica, el límite total estático del 10 % pasa a ser
  un 5 %.
- Síntoma: en `TL3_REPORTS/propfund_zero_edge.md`, FundingPips da P(diario) = 18 % con un riesgo de
  0,25 % al día, cuando la pérdida diaria máxima posible es 0,25 %.

**Efecto de E-2/E-3.** Afecta a la cuenta FundingPips-Trial de `config/propfund/accounts.yaml:107`
(`daily_loss_base: higher_of_balance_or_equity`). Si la cuenta cruza medianoche con pérdida flotante,
la protección permite perder por debajo del suelo de la firma.

## 2. Reglas

- Las de `COLA-TL3-D.md §1` (escritura solo con Python o `git`, nada de `>`/`Out-File`).
- **Cambio mínimo:**
  - solo la rama `higher_of_balance_or_equity`;
  - los modos `balance` y `equity` (FTMO y el resto) deben dar resultados **idénticos** bit a bit con
    la misma semilla;
  - no se cambian límites, porcentajes ni otras reglas.
- **Prohibido:** tocar `config/propfund/*.yaml` y `config/prop*.yaml`, el EA, `ai_trader`, el forward,
  `schedule.yaml`, las tareas y `.env`; enviar órdenes; activar bots o F13; push; borrar archivos;
  reescribir informes históricos (los informes afectados se **listan**, no se reescriben).
- **Interpretación de la regla:** si en P1 aparece un texto oficial de FundingPips que mida el 5 % desde
  el balance **inicial**, se para la cola con `bloqueado: interpretación de la regla` y se informa. No
  se elige una interpretación por cuenta propia.
- Fallo técnico: hasta 3 reintentos corrigiendo la causa. Si un test de regresión de los modos
  `balance`/`equity` falla, **no** se continúa: rollback al tag y `bloqueado`.

## 3. Bloques

### P0 · Cola
`git add -f .orquestador/COLA-TL2-DIARIO.md`; commit `tl2: diario - cola`.

### P1 · Inventario y confirmación (solo lectura)
1. Inventario de:
   - toda construcción de `PropRules` con `daily_loss_mode = "higher_of_balance_or_equity"` (busca en
     `config/prop*.yaml`, `config/propfund/`, `prop/rules.py`, `propfund/`, `accounts.py` y los
     scripts);
   - todo consumidor de `daily_loss_mode`: `simulator`, `guard`, `overlay`, `defense`,
     `propfund/snapshots.py`, `propfund/risk.py`, la web y la CLI. Para cada uno, indica qué hace con
     ese modo.
2. Informes de Prop Fund o TL3 que contengan cifras de FundingPips calculadas con ese modo: fichero y
   cifra. Solo se listan.
3. **Confirmación sintética, con el código actual, sin modificarlo.** Reglas FundingPips (5 % diario,
   10 % estático, base `higher_of_balance_or_equity`, `buffer_pct` = 0), 100.000 USD, un camino determinista de 30 días
   con −0,25 % diario.
   - Esperado con el código actual: rotura "diaria" al cruzar −5 % (día 21).
   - Esperado con la regla: ninguna rotura en 30 días (−7,2 % < 10 %).

   Si el código actual **no** rompe, para la cola con `bloqueado: no se reproduce` e informa.
4. Guarda la salida de referencia ("golden") del código actual con semilla 42, `n_paths` 2.000, en
   `tests/data/prop_daily_golden.json`:
   - `monte_carlo` y `monte_carlo_program` con las reglas FTMO 2-Step (`balance`);
   - FTMO 1-Step;
   - un caso `equity` sintético;
   - las 9 combinaciones b × riesgo de D2 en FTMO.
5. Informe `TL3_REPORTS/tl2_diario_inventario.md`. Commit `tl2: diario - inventario y golden`.

### P2 · Tag y baseline previos
1. `git tag tl2-diario-pre` sobre el HEAD de P1 (antes de cualquier cambio de código).
2. `lab propfund baseline --reason "TL2-DIARIO: estado previo a corregir el suelo diario higher_of_balance_or_equity en prop/simulator.py y prop/guard.py"`.
3. `lab propfund verify` y commit del manifiesto, si cambió: `tl2: diario - baseline previo`.

### P3 · Corrección
1. `prop/simulator.py`, en los dos bucles: para `higher_of_balance_or_equity`,
   `daily_floor = np.maximum(day_start_balance, day_start) - eff_daily`, con
   `day_start_balance = day_start`. Comentario: "modelo diario: sin posiciones abiertas entre días;
   balance = equidad al inicio del día". Desaparece `initial` de esa fórmula.
2. `prop/guard.py::_bases`: rama nueva para `higher_of_balance_or_equity`:
   `daily_base = max(state.day_start_balance, state.day_start_equity)`. Si alguno de los dos falta,
   usa el disponible; si faltan ambos, conserva el comportamiento actual y regístralo.
3. `propfund/snapshots.py` (E-3): pasa el modo tal cual **solo si** P1 demostró que todos los
   consumidores (`overlay`, `defense`, `risk` y la web) lo soportan; añade el soporte mínimo donde
   falte. Si eso obliga a cambiar más de esos módulos, **no** toques `snapshots.py`: déjalo anotado
   como pendiente en el CHANGELOG.
4. Ningún otro cambio. Commit `tl2: diario - suelo diario higher_of`.

### P4 · Tests de regresión
1. **Identidad:** con el código nuevo, todas las salidas `balance`/`equity` de
   `tests/data/prop_daily_golden.json` son idénticas.
2. **Corrección:** el camino de P1.3 no rompe en 30 días. Un camino con un día de −5,1 % sí rompe ese
   día. Con `day_start_balance` 100.000, `day_start_equity` 98.000 y `buffer_pct` = 0, `guard` pone el
   suelo diario en 95.000, no en 93.000.
3. **Antes/después descriptivo:** repite las 9 filas FundingPips de D2 con el código nuevo y publica la
   tabla antigua y la nueva en `TL3_REPORTS/tl2_diario_inventario.md`. Comprobación esperada: con un
   riesgo de 0,25 % al día, P(diario) = 0. `propfund_zero_edge.md` **no** se reescribe: se le añade
   una línea al final que remite a la tabla nueva.
4. `ruff` y los tests de `prop`/`propfund`. Commit `tl2: diario - tests de regresion`.

### P5 · CHANGELOG y baseline posterior
1. Entrada en `docs/CHANGELOG-produccion.md` con el formato del fichero:
   - fecha;
   - **autorización del operador (literal del mensaje de lanzamiento)**;
   - qué cambia (E-1, E-2 y, si se hizo, E-3);
   - qué no cambia (modos `balance`/`equity`, límites, FTMO, órdenes);
   - cómo se comprueba (tests de P4);
   - informes históricos afectados (lista de P1.2);
   - rollback: tag `tl2-diario-pre`.
2. `lab propfund verify`: debe listar solo los ficheros tocados en P3.
3. `lab propfund baseline --reason "TL2-DIARIO: corregido suelo diario higher_of_balance_or_equity (simulator/guard); ver CHANGELOG 2026-11-25"`.
4. Commit `tl2: diario - changelog y baseline`.

### P6 · Cierre
- `ruff check`, `pytest -q` completo, `lab doctor`, `lab propfund verify`.
- README y PLAN: una línea.
- Commit `tl2: diario - cierre` y tag `tl2-diario`.

### P7 · Aviso
- Resumen a Telegram con `lab telegram send --file <resumen>`; si no hay Telegram, `lab alerts send`.
  Formato **Hecho / 1..N / Aviso / Siguiente**, con:
  - la confirmación de P1.3;
  - los ficheros cambiados;
  - las identidades de regresión (OK o fallo);
  - FundingPips antes → después con riesgo 0,5 % y b = 2;
  - E-3 hecho o pendiente;
  - el rollback.
- Fin de la cola.


## Estado de ejecución (2026-11-25)

- **P0-P6 hechos.** P7 (aviso) pendiente de envío.
- Commits: `5303e4e` (cola), `591b03e` (inventario y golden, **tag `tl2-diario-pre`**),
  `74cadbc` (baseline previo), `020b41b` (suelo diario higher_of),
  `7bd100b` (tests de regresión), `cac3bec` (CHANGELOG y baseline).
- Cambios de producción: solo `src/tradinglab/prop/simulator.py` y
  `src/tradinglab/prop/guard.py`, rama `higher_of_balance_or_equity`.
  `propfund/snapshots.py` **no** se tocó: P1 demostró que `overlay`, `defense`
  y `risk` no reciben el modo ni balance de inicio de día; E-3 queda pendiente
  en el CHANGELOG.
- Confirmación P1.3: el código anterior rompía en el día 21 con −0,25 % diario;
  el corregido no rompe en 30 días y un día de −5,1 % rompe ese día.
- Identidad: 15/15 casos `balance`/`equity` del golden, bit a bit.
- Tests: `pytest -q` completo **1999 passed, 1 skipped**; dirigidos de
  `prop`/`propfund` **59 passed**; `ruff check .` limpio; `lab doctor` con el
  FAIL preexistente de Frescura; `lab propfund verify` OK tras el baseline.
- Nota: otra sesión ejecutó TL3-D en paralelo (commits `e68936b` a `a65db83`).
  Todos los commits de esta cola usan rutas explícitas; el trabajo ajeno no se
  incluyó. El `pytest -q` se lanzó con el árbol de esa sesión y terminó en
  verde.
- Rollback: tag `tl2-diario-pre` (`591b03e`). Tag de cierre: `tl2-diario`.
- Sin órdenes, sin push, sin tocar `config/propfund/*.yaml`, EA, `ai_trader`,
  forward, `schedule.yaml`, tareas ni `.env`.
