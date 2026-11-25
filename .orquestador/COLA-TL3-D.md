# COLA TL3-D · Protecciones, líneas base y planes de potencia (continuación sin paradas)

**Creada:** 2026-11-25, aprobada por el operador ("Sí, las cinco").
**Arranca:** en cuanto termine C6 de `COLA-TL3-C.md`, **sin pedir confirmación**.
**Modo:** cadena continua D0 → D5 → D5b → D6 → D7. Un commit pequeño por bloque.

**Nada de esta cola suma al contador.** No hay hipótesis de mercado nuevas. D2 usa datos sintéticos.
D3 solo cuenta velas. D4 y D5 solo calculan tamaños de muestra con datos ya publicados y fijan reglas
**antes** de mirar datos nuevos. `count_tests` debe seguir en 1897.

## 1. Reglas (las de `COLA-TL3-C.md §1`, más estas)

- Escritura de ficheros solo con Python (`write_text(..., encoding="utf-8")`) o con `git`. Nunca con
  `>`, `Out-File` ni `Set-Content`.
- **Solo lectura/importación** de `prop/`, `propfund/`, `ea_forward.py`, `drift.py`,
  `ea_us100_engine.py` y `ai_trader.py`: se pueden importar y llamar, **no** modificar.
- `lab.db` y `discovery.db`: solo lectura (`mode=ro`). `tl3_research.db`: solo filas nuevas.
- No se modifica ningún script que ya produjo un resultado registrado (`scripts/tl3_t5*`, `tl3_t7*`,
  `tl3_t8*`, `tl3_ai_counterfactual.py`). Si hace falta, se añade un test que los compruebe.
- Prohibido, igual que en TL3-C: EA, setfile, Prop Fund, riesgo FTMO, forward, `schedule.yaml`,
  tareas, `.env`, `record-informal`, órdenes, campañas, `research*`, OOS, `confirm`, push, borrar.
  Y además: **calcular el rendimiento del forward del EA o de operaciones de `ai_trader` posteriores a
  T5** (D4 y D5 solo cuentan operaciones).
- Fallo técnico: hasta 3 reintentos corrigiendo la causa; si sigue, `bloqueado: <motivo>` y sigue.
  Si falta un dato: **Sin datos**, nunca un valor inventado.

## 2. Bloques

### D0 · Commit de la cola
`git add -f .orquestador/COLA-TL3-D.md`; commit `tl3: D0 - cola TL3-D`.

### D1 · Protecciones contra errores repetidos
1. **Swap.** Módulo nuevo `src/tradinglab/tl3/costs.py`:
   - `swap_bps_per_night(rate, mode, *, price=None, point=None)`:
     - `mode` 5 (interés anual en %): `abs(rate) / 100 / 365 × 1e4`;
     - `mode` 1 (puntos): `abs(rate) × point / price × 1e4`;
     - cualquier otro modo: `ValueError("Sin datos: swap_mode no soportado")`.
   - `nights(entry_weekday, rollover3days=5)`: 3 si la noche cruza el día triple (entrada en viernes,
     con la convención MT5 0 = domingo … 5 = viernes); si no, 1.

   Tests:
   - 7,33 % → 2,008 bps (±0,001);
   - un caso de `mode` 1 calculado a mano;
   - modo desconocido → error;
   - viernes → 3, martes → 1;
   - `scripts/tl3_t8_fomc.SWAP_BPS == swap_bps_per_night(7.33, 5)` (sin modificar el script).

   Busca cualquier otro cálculo de swap en `scripts/tl3_*.py` y `src/tradinglab/tl3/`, y añade un test
   que lo compare con la función.
2. **Codificación.** Test `tests/test_tl3_reports_encoding.py`: todo `TL3_REPORTS/*.md` debe cumplir:
   - se decodifica como UTF-8 y no lleva BOM;
   - no contiene "?" pegado delante de un dígito;
   - no contiene las marcas de mojibake `Ã`, `â€`, `┬` ni `├`.

   Si algún informe actual falla, corrígelo con Python (mismo contenido) en este bloque.
3. **Registro.** En `src/tradinglab/tl3/registry.py`, función nueva
   `add_status(hypothesis_id, parent_id, status, reason, *, note=None)`. Inserta una fila hija con
   `created_at = _now()` copiando el resto de campos del padre, y sustituye en el futuro a los
   `INSERT` manuales de los scripts. Las filas antiguas no se tocan. Tests: la fecha es la actual,
   la fila padre no cambia y el `hypothesis_id` es único.
4. **Tablas de estado desde el registro.** En `src/tradinglab/tl3/report.py`,
   `status_table(db=...)`: devuelve en markdown el último estado por hipótesis (orden por `rowid`).
   Añade un test que compare la tabla de hipótesis de `TL3_REPORTS/TL3_RESULTS_CICLO1.md` con
   `status_table()`. Si no coinciden hoy, corrige el documento en este bloque, no el test.
5. `ruff`, tests de los módulos tocados. Commit `tl3: D1 - protecciones swap, codificacion y registro`.

### D2 · Línea base sin ventaja para Prop Fund (sintética, no suma)
**Pregunta:** ¿qué probabilidad de aprobar, y qué valor esperado si hay datos de tarifa y reparto,
tiene una estrategia **sin ventaja** con las reglas de cada firma? Las reglas de una prop firm pueden
dar valor esperado positivo a una estrategia sin ventaja (Youngblood 2026). Una estrategia real solo
aporta si supera esta línea base con la misma regla de riesgo.

1. Firmas y fases de `config/propfund/firms.yaml` vía `prop.rules.from_yaml` (y `prop.rules.ftmo`
   para FTMO), sin modificar nada.
2. Retornos diarios sintéticos (semilla 42, 20.000 días): 1 operación/día con resultado `+b` R con
   probabilidad `p = 1/(1+b)` y `−1` R en el resto, es decir, ventaja bruta exactamente 0.
   - `b` ∈ {1, 2, 3}.
   - Riesgo por operación ∈ {0,25 %; 0,5 %; 1,0 %} y, además, el riesgo configurado de cada cuenta en
     `config/propfund/risk.yaml` / `accounts.yaml`, si existe (si no, **Sin datos**).
   - Retorno diario = riesgo × resultado.
   - Coste: 0 (bruto). Si `config/propfund/costs.yaml` permite expresar el coste por operación en R
     sin suponer nada, añade la versión neta; si no, "neto: Sin datos".
3. Simulación con `prop.simulator.monte_carlo_program` (programas de varias fases) o `monte_carlo`
   (una fase), `n_paths` 5.000, semilla 42, con los parámetros por defecto del simulador.
4. Para cada firma × `b` × riesgo se informa:
   - P(aprobar cada fase) y P(cuenta financiada);
   - P(romper el límite diario) y P(romper el límite total);
   - días medianos hasta aprobar;
   - si `firms.yaml` trae tarifa y reparto: `EV = P(financiada) × pago esperado − tarifa`, indicando
     qué parte del pago se ha modelado; si no, "EV: Sin datos".
5. Si existen informes de Prop Fund con P(aprobar) de estrategias reales, se citan junto a la línea
   base (fichero y cifra). Si no, **Sin datos**. **No** se simula ninguna estrategia real.
6. Informe `TL3_REPORTS/propfund_zero_edge.md` con la lectura: "una estrategia real aporta sobre las
   reglas solo si su P(financiada) o EV supera la línea base con la misma regla de riesgo".
   Recuerda la advertencia del simulador: con datos diarios, el riesgo intradía queda subestimado.
7. Commit `tl3: D2 - linea base sin ventaja Prop Fund`.

### D3 · Mapa de cobertura de datos (solo conteos, no suma)
1. Para cada `data/cache/dukascopy/*_M1.parquet` y cada copia de `data/tl3/futures/`, por año, sin
   leer precios más allá de la existencia de velas:
   - sesiones NYSE;
   - sesiones con ≥ 95 % de velas en 09:30-15:44 NY;
   - mediana de velas de 18:00 (día previo) a 09:29;
   - % de sesiones con ≥ 80 % nocturno;
   - sesiones válidas con la **regla prerregistrada de T7** (≥ 357 en la sesión y en la anterior;
     ≥ 744 nocturnas);
   - mayor hueco intradía en minutos;
   - días sin ninguna vela.
2. Función reutilizable en `src/tradinglab/tl3/data.py`: `session_coverage(m1, day, *, session_min=357,
   night_min=744, check_previous=True)`, la regla de T7 tal como se prerregistró. Tests sintéticos,
   incluido el caso de la sesión anterior incompleta. El ciclo 2 debe usar esta función.
3. Comprobación cruzada: para US100 2012-2021, la regla prerregistrada debe dar ~1128 sesiones válidas
   y 0 en 2012, 2016 y 2017 (referencia de la revisión de Claude). Si no coincide, informa la
   diferencia; no ajustes la función para que coincida.
4. Informe `TL3_REPORTS/data_coverage.md`, datos en `data/tl3/coverage.json` y una línea en
   `TL3_REPORTS/data_manifest.md` que apunte al informe. **No** se modifica `data/tl3/manifest.json`.
5. Commit `tl3: D3 - mapa de cobertura`.

### D4 · Plan de potencia de `ai_trader` (no suma, no mira operaciones nuevas)
1. Fuente: las **48 de T5** (`ai_trader_t5_rows.json` sin los `id` 52 y 54). Por operación:
   - Δ_t = IA − tendencia;
   - Δ_g = IA − gemela;
   - real − simulado de la IA.

   Calcula la desviación de cada serie.
2. n necesario para un MDE de 0,10 R: `n = ⌈(2,49 × sd / 0,10)²⌉` para Δ_t, Δ_g y para el R real
   (frente a 0).
3. Ritmo: operaciones cerradas por día hábil entre la primera y la última de las 48 (solo fechas, sin
   resultados) → fecha estimada para alcanzar cada n.
4. Versiones: si `ai_trades` o `model_registry` permiten saber qué versión de modelo o prompt generó
   cada operación, informa cuántas versiones hay en las 48. Si no se puede, **Sin datos**. Una mezcla
   de versiones debe constar en el plan.
5. **Regla fijada ahora:** la próxima evaluación de `ai_trader` se hace **una sola vez**, cuando el
   número de operaciones cerradas alcance el n de Δ_t (redondeado hacia arriba a múltiplo de 10). Se
   usan el script de T5, el criterio de `TL3_AI_TRADER_AUDIT §5` y el bootstrap con semilla 7. Antes
   no se mira, y esa evaluación necesitará aprobación del operador y registro en el contador.
6. Hipótesis borrador `H-2026-012` ("ai_trader frente a regla de tendencia, evaluación única a
   n = N") en `tl3_research.db` con `add_hypothesis`, estado `draft`.
7. Informe `TL3_REPORTS/ai_trader_power_plan.md`. Commit `tl3: D4 - plan de potencia ai_trader`.

### D5 · Plan de seguimiento del EA en el forward (no suma, solo conteos)
1. Cuenta, en solo lectura, las operaciones **cerradas** del EA en el forward:
   - con `ea_forward` (`_closed` / `forward_metrics`, sin modificarlo) o con `fills` de `lab.db`
     (`bot = 'ea:us100-ftmo1'`, `magic` 93010001);
   - **solo el número y las fechas**: no se calcula ningún R, PF ni expectativa del forward.
2. Referencia del backtest: réplica T6 (479 operaciones, +0,3104 R). Calcula su desviación de R por
   operación a partir de los datos de la réplica, y la frecuencia por año.
3. n necesario para que, si la expectativa real fuera 0, la cota superior del IC95 del forward quede
   por debajo de +0,3104 R con una potencia del 80 %: `n = ⌈(2,49 × sd / 0,3104)²⌉`. Calcula lo mismo
   para una expectativa real de 0,10 R. Fecha estimada con la frecuencia del backtest.
4. **Regla fijada ahora:**
   - el rendimiento del forward se mira solo en los puntos de control n ∈ {30, 60, N};
   - en cada punto se informan la media de R y su IC95 (bootstrap semanal, semilla 42);
   - "alerta de deriva" si la cota superior del IC95 < +0,10 R;
   - "compatible con el backtest" si el IC95 contiene +0,3104;
   - cualquier otro caso, "indeterminado".

   Ninguna alerta cambia el EA ni el riesgo: decide el operador.
5. Comprueba si `drift.py` ya produce para el EA algo equivalente. Si es así, cítalo en lugar de
   duplicarlo.
6. Informe `TL3_REPORTS/ea_forward_monitor_plan.md`. Commit `tl3: D5 - plan de seguimiento del EA`.

### D5b · Diagnóstico de la TCA (solo lectura, no suma; aprobado por el operador el 2026-11-25)
**Hallazgo de Claude (verificado en solo lectura):**
- La tabla `tca` de `lab.db` tiene 68 filas: 66 con `slippage_bps` = 0 y `signal_px` = `fill_px`, 2 con
  `fill_px` nulo, y `latency_ms` vacío en todas.
- Causa probable en `src/tradinglab/execution/mt5.py:772-783`:
  - `signal_px=price` y `order_px=price`, donde `price` es el precio de la petición en el momento del
    envío, no el de la decisión;
  - `fill_px = result.price or price` cae al precio pedido si MT5 devuelve 0;
  - no se pasa `latency_ms`.

  Así, la TCA solo puede medir el desvío entre envío y ejecución en el mismo tick, y nunca entre
  decisión y ejecución.
- Consumidores afectados:
  - `ai_trader.py:3209` lee `AVG(slippage_bps)` de `tca` para sus costes;
  - `ai_distill.py:1260` aplica con ella el criterio `max_slippage_bps` 3,0;
  - `drift.py` y la web (`tca.build_tca`) muestran estado `ok`.

  Todos ven una ejecución gratuita.

1. Confirma o corrige la causa leyendo `execution/mt5.py` y `execution/paper.py:140` (otro escritor de
   `tca`). Sin modificarlos.
2. Por bot y símbolo, cuenta las filas de `tca`, las que tienen slippage 0, las de `fill_px` nulo y
   las que no traen `bid`/`ask`/`requested_price` (filas anteriores a la migración).
3. Slippage entre decisión y ejecución, **descriptivo** (es coste de ejecución, no rendimiento):
   - si `ai_decisions`, `signals` u `orders` guardan un precio o una hora de la decisión que se pueda
     unir a cada fill sin suponer nada, calcula por operación `fill − precio de decisión` en bps y en
     puntos, con el signo del lado, y la mediana y el p95 por bot y símbolo;
   - si solo hay hora, usa el cierre M1 de esa hora solo si esa vela ya está en la caché local
     (sin MT5); si no, **Sin datos**;
   - compara el resultado con la componente de entrada de T5-bis rehecho (C1).
4. Lista todos los lectores de `tca.slippage_bps` y explica qué decide cada uno con el valor actual.
5. Informe `TL3_REPORTS/tca_diagnostico.md` con:
   - causa, conteos, slippage decisión → ejecución (o Sin datos) y consumidores afectados;
   - una **propuesta** de corrección (no se aplica): qué precio pasar como `signal_px`, cómo medir
     `latency_ms` y qué hacer con las filas antiguas, **sin borrarlas ni reescribirlas**.

   `execution/mt5.py` es la ejecución del forward y de `ai_trader` (producción). Aplicar la propuesta
   exige, en otra cola y con aprobación del operador: línea base (`lab propfund baseline --reason`),
   test de regresión, entrada en `docs/CHANGELOG-produccion.md` y tag `tl2-<id>-pre`.
6. Commit `tl3: D5b - diagnostico TCA`.

### D6 · Cierre
- `ruff check`, `pytest -q` completo, `lab doctor`, `lab propfund verify`.
- README §11 y PLAN: una línea por D1-D5b.
- `count_tests` debe seguir en **1897**; si no, `bloqueado: contador cambiado` y se informa.
- Commit `tl3: cierre ciclo 1e` y tag `tl3-ciclo1e`.

### D7 · Aviso
- Resumen a Telegram con `lab telegram send --file <resumen>`; si Telegram no está configurado,
  `lab alerts send`. Formato **Hecho / 1..N / Aviso / Siguiente**, con:
  - las protecciones añadidas;
  - la P(financiada) de la línea base sin ventaja por firma con riesgo 0,5 % y b = 2;
  - las sesiones válidas por índice;
  - el n y la fecha de la próxima evaluación de `ai_trader` y de los puntos de control del EA;
  - la causa de la TCA en 0 y el slippage decisión → ejecución (o Sin datos);
  - los bloqueos, si los hubo.
- Fin de la cola. No se empieza nada más.
