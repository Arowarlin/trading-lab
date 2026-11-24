# COLA TL2 · Fase 0 + Fase 1 (preparación y costes)
Modelo: **DeepSeek V4.1 Flash** (OpenCode Go). Ejecuta los bloques **en este orden y sin parar entre ellos**. Al cerrar cada bloque: commit, tag y RESULTADO. Después, el siguiente.

**Regla de parada:** si un bloque falla en tests, encuentra algo que contradice la especificación o necesita una decisión humana, escribe el RESULTADO de ese bloque con el problema y **PARA TODO**.

Especificación completa: `.orquestador/tl2-audit/TL2_OPENCODE_TASKS.md`. Contexto: `TL2_MASTER_AUDIT.md` y `TL2_QUANT_AUDIT.md`. Léelos antes de empezar.

Autorización del operador (2026-11-24): trabajar sobre todos los módulos, incluidos FTMO, `us100-ftmo1`, `ai_trader`, Prop Fund y `ea_lab`. Cada cambio importante necesita pruebas, comparación con el comportamiento anterior, documentación y rollback. Nunca cuentas reales ni órdenes.

## Prohibido en toda la cola
- Registrar, aprobar o ejecutar campañas; leer OOS-1 u OOS-2; `confirm`; `record-informal`.
- Calcular expectativa, PF o percentil de cualquier campaña real (el guard lo impide; no lo rodees).
- Push, borrar archivos, tareas programadas, operar, descargar datos de pago.
- Modificar filas existentes de `data/discovery.db` o `data/lab.db`. Solo están permitidas migraciones aditivas.
- `count_tests` debe seguir en **1883** al final.

---

## Bloque 1 · T00 (protección → control de cambios)
Ejecuta `.orquestador/COLA-TL2-T00.md` completa. Su cierre (commit `tl2-t00`, `RESULTADO-T00.md`) vale como cierre de este bloque. **No pares**: sigue con el bloque 2.

## Bloque 2 · T02 (copia automática de discovery.db)
Según la especificación T02.
- Hook tras `register`, `approve`, `run`, `confirm` y `record-informal`.
- Usa `sqlite3.Connection.backup`. Destino `data/backups/discovery_<YYYYmmddTHHMMSSZ>.db`.
- Retención: las 30 últimas más la primera de cada mes. **La retención no borra nada**: si hay que retirar copias, se mueven a `data/backups/_old/`.
- Opción `discovery.backup: true` en `engine.yaml`.
- Test con base temporal: la copia existe y `PRAGMA integrity_check` devuelve `ok`.
- Commit `tl2: T02 - copia automática discovery.db`, tag `tl2-t02`, `RESULTADO-T02.md`.

## Bloque 3 · T10 (modelo de ejecución BID/ASK) — el más importante
1. `git tag tl2-t10-pre`.
2. **Antes de tocar nada:** ejecuta `python -I .orquestador/tl2-audit/evidencia/prueba_spread_fastbt.py` y guarda la salida en el RESULTADO. Debe mostrar 4,0 bps en las salidas por tiempo y "time_exit salida barra 16" en el corto.
3. **Separar costes.** `CostPanel` lleva `spread_bps`, `slip_bps` y `comm_bps` por barra; `entry_bps`, `stop_bps` y `target_bps` quedan solo como propiedades de compatibilidad para la v1. Aplica esto en `CfdBpsCosts`, `CfdProfileCosts`, `CfdHourlyCosts`, `FuturesCosts` (spread 0) y en el panel de `discovery/costs.py` (`CostBook.panel` con best/worst/target).
4. **Reglas v2** en `_core` y `_calendar_core`, con `cost_model_version == 2`:
   - Largo: entrada = `comm + slip + spread[entrada]`. Salida por stop, tiempo, señal, flat o fin = `comm + slip`. Salida por objetivo = `comm`.
   - Corto: entrada = `comm + slip`. Salida por stop, tiempo, señal, flat o fin = `comm + slip + spread[salida]`. Salida por objetivo = `comm`: el precio del objetivo ya es nivel ASK, se comprueba con `low + spread` como hoy.
   - Disparo del stop de un corto: `high[i] + high[i]*spread_bps[i]/1e4 >= stop_p`. El precio de salida sigue siendo `max(stop_p, open_ask)`, con `open_ask = open + open*spread/1e4`; en ese caso **no** se suma otra vez el spread en el coste.
   - Con `cost_model_version == 1` todo queda **exactamente** como hoy.
5. `CostBook.apply` aplica las mismas reglas por cuenta y por versión.
6. `Trade` añade `spread_r`, `slip_r` y `comm_r` (opcionales). Su suma menos `swap_r` debe dar `r_cost` (tolerancia 1e-9).
7. **Versión por campaña.**
   - `cost_model_version` se guarda en el `config_json` al registrar; por defecto vale **2** en campañas nuevas.
   - Al cargar una campaña sin ese campo, se usa **1**. Así las campañas viejas se reproducen igual.
   - `jobs`, `fitness`, `drift`, `robustness`, `levels`, `feasibility` y `basket` deben pasar la versión hasta `fastbt.run`.
   - Busca todas las llamadas a `fastbt.run` y a `CostBook` con `grep -rn "fastbt.run\|CostBook(" src/` y lista en el RESULTADO las que tocaste.
8. **Tests nuevos** (`tests/test_discovery_execution_v2.py`), con resultados calculados a mano:
   - precio plano, spread 2 bps, comisión y slippage 0: largo y corto × {stop, tiempo, señal, flat, fin} → coste exacto 2 bps;
   - largo con salida por objetivo → 2 bps; corto con objetivo → precio de salida al ASK y coste solo de comisión;
   - ASK sobre el stop de un corto con el BID por debajo → sale en esa barra con v2 y no sale con v1;
   - spread variable por barra: el largo usa el de la barra de entrada y el corto el de la barra de salida;
   - comisión `round_turn` de 5 USD/lote → 2,5 por lado;
   - **paridad v1:** las fixtures existentes de `test_discovery_fastbt.py` y `test_discovery_parity.py` dan resultados idénticos con v1;
   - **paridad de convención con `ea_us100_engine`:** misma serie sintética y mismo spread por barra → mismos precios de entrada y salida en largo y corto con stop (copia la convención de `ea_us100_engine.py:134-158`; **no modifiques ese archivo**).
9. **Comparación antes/después sin rendimiento.** Para las specs `q2-fix-eurusd-h1`, `q2-fix-gbpusd-h1`, `q2-fix-usdjpy-h1`, `q1-rebote-us500-d1` y `r9b-tom-us500-d1`, ejecuta **solo `feasibility`** con v1 y con v2 (usando las specs como borrador, sin registrar). Tabla en el RESULTADO: `cost_r` mínimo, mediano y máximo, y combinaciones factibles, v1 frente a v2. **No calcules expectativa.**
10. Documenta en `docs/tradinglab2/06_TRADINGLAB_DATA_AND_COST_AUDIT.md` (sección "Modelo de ejecución v2") y añade la entrada en `docs/CHANGELOG-produccion.md`.
11. Cierre: ruff, pytest, propfund verify, count_tests (1883). Commit `tl2: T10 - ejecución BID/ASK v2`, tag `tl2-t10`, `RESULTADO-T10.md`.

## Bloque 4 · T01 (arnés de autoevaluación)
1. **Refactor sin cambio de comportamiento.**
   - Extrae a `discovery/decisions.py` funciones puras con las reglas de decisión que hoy viven en `engine._rank1_candidates`, `engine._select_finalists` y `levels.evaluate`: deriva, IS > 0, pliegues, OOS-1 con expectativa y PF, nivel 3 y nivel 4.
   - `engine` y `levels` las llaman.
   - **Test de equivalencia:** mismas entradas → mismas salidas que antes del refactor. Usa las fixtures `tests/fixtures/discovery_*`.
2. `discovery/harness.py`, con dos modos:
   - **`gates`:** genera flujos de R por operación (normal con media δ y desviación 1, y además t de Student con 4 grados de libertad) para IS, OOS-1 y OOS-2, con el número de operaciones de `freq` × duración de cada tramo (tramos por defecto de `engine.yaml`), y les aplica las funciones de `decisions.py`. Las puertas que no se pueden simular con flujos de R (PBO, WF, régimen, perturbaciones) se marcan "no simuladas" y se tratan como aprobadas (cota superior optimista).
   - **`bars`:** barras sintéticas BID con spread conocido y una señal que tiene ventaja δ conocida, pasadas por `fastbt` v2 + `CostBook`. Debe recuperar `δ − coste` dentro del intervalo de confianza: **esto valida también T10**.
3. CLI `lab discovery harness --mode gates|bars --freq 12,50,250,1000 --edge 0,0.05,0.1,0.2 --sims 2000 --seed 7`. Base de datos temporal en memoria. **No escribe en `discovery.db` ni toca el contador.**
4. Salida `reports/discovery/harness-current.md`: tabla P(aprobar) con IC de Wilson.
5. **Aceptación:** con δ = 0, P(aprobar) < 0,05 en todas las frecuencias; los órdenes de magnitud coinciden con `.orquestador/tl2-audit/evidencia/potencia_validacion.salida.txt` (diferencias explicadas en el RESULTADO); el modo `bars` recupera δ.
6. Commit `tl2: T01 - arnés de autoevaluación`, tag `tl2-t01`, `RESULTADO-T01.md`.

## Bloque 5 · T11 (spread histórico por barra)
1. Comprueba si los snapshots y la caché Dukascopy tienen `ask_close`. Lista por símbolo y timeframe el porcentaje de barras con ASK válido. **Si no hay ASK para un símbolo: Sin datos.** No descargues nada.
2. `spread_model` en `engine.yaml`, con valores `p75_static` (actual, por defecto en v1), `hourly_median` y `historical_scaled` (por defecto en v2 cuando hay ASK; si no, `hourly_median`).
3. Escalado: `s_t = (ask_t − bid_t) · m_h^bróker / m_h^Dukascopy`. `m_h` es la mediana por hora local en la ventana común más reciente de 90 días. Si no hay ventana común: Sin datos y se usa `hourly_median`.
4. El p75 queda solo en el escenario de estrés (`retest cost_x1_5` y uno nuevo, `spread_p75`).
5. Tests: ASK sintético conocido → spread exacto; sin ASK → mediana horaria; el escalado preserva la mediana del bróker.
6. `reports/discovery/spread-historico.md`: spread medio y p75 por año, símbolo y hora (2010–2026), solo con los datos disponibles.
7. Commit, tag `tl2-t11`, `RESULTADO-T11.md`.

## Bloque 6 · T13 (swap histórico)
1. Revisa `intel/fred.py`.
   - Si hay caché o clave FRED disponible (keyring), obtén las series diarias de tipos de referencia: EE. UU. (EFFR), zona euro (€STR, y EONIA antes de 2019), Reino Unido (SONIA) y Japón (la que tenga FRED; si no hay ninguna adecuada: Sin datos).
   - Si no hay clave: **Sin datos**; escribe el RESULTADO y salta al bloque 7 **sin parar la cola**.
2. `SwapSpec` admite `mode: historical`: `swap_t = (tipo_ref_t + markup_lado) · nocional · noches / 360`, con el triple rollover como hoy. El markup se calibra para que el valor de hoy reproduzca `config/propfund/swap.yaml`.
3. El crédito sigue contando 0 en Discovery (`swap_credit: false`).
4. Tests: tipo histórico igual al de hoy → reproduce `swap.yaml`; tipo 0 → solo markup; triple rollover.
5. Commit, tag `tl2-t13`, `RESULTADO-T13.md`, con la tabla de swap medio anual por símbolo y lado.

## Bloque 7 · T12 (slippage medido)
1. Localiza los fills reales (`mt5_fills.py`, `tca.py`, tablas en `lab.db`). Lista las tablas y el número de fills por símbolo, cuenta y tipo de orden. **Solo lectura.**
2. `lab costs slippage-measure` calcula la mediana y el p75 de |fill − precio solicitado| en unidades de precio por celda (símbolo, cuenta, tipo, franja de 4 horas), con su n.
3. **No sobrescribas `costs.yaml`.** Escribe una propuesta en `config/propfund/costs.measured.yaml`:
   - con `source: measured` y la fecha en las celdas con n ≥ 30;
   - con `source: assumption` (el valor actual) en el resto.
   
   El operador decidirá si se aplica.
4. Tests con fills sintéticos.
5. Commit, tag `tl2-t12`, `RESULTADO-T12.md`, con la tabla real y "Sin datos" donde n < 30.

## Cierre de la cola
`RESULTADO-cola-tl2-f0f1.md`: un resumen de una línea por bloque, los tags, `count_tests` (1883), `git status` y los problemas pendientes. **PARA.**
