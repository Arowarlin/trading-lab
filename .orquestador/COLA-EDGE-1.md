# COLA EDGE-1 · Fábrica de estrategias: M15 / M30 / H1 / H4 × 7 activos, con costes reales

**Creada:** 2026-11-25 por Claude a petición del operador ("vamos a buscar edge, generar estrategias…
15m 30 1h 4h, diferentes activos, que calcule bien spread y comisiones, que se vea en la consola").
**Motor:** el que ya existe, `lab discovery`: GA → validación → robustez → `confirm` (OOS-2) →
`export-mql5`. **No se escribe un motor nuevo.**
**Modo:** cadena continua X0 → X8, todo el día, sin pedir confirmación. Un commit pequeño por bloque.
**Autorización:** solo corre si el mensaje del operador que la lanza contiene literalmente
`APRUEBO CAMPAÑAS EDGE-1`. Esa frase cubre:
- `discovery approve` y `run --approved-by-operator` de las campañas de §3;
- **un** `confirm --approved-by-operator` por finalista que pase **todas** las puertas de §4.

## 1. Qué hay y qué falta

- Hecho hasta hoy: unas 21 campañas de discovery, todas con el perfil `small`, en EURUSD H1, GBPUSD H1,
  US100 D1/M5, US500 D1, USDJPY H1/H4 y XAUUSD H4. Salieron 634 estrategias y 3 finalistas. **Nunca
  se ha leído un OOS-2** (`disc_holdout_reads` vacío).
- Nunca probado: **M15 y M30**; XAUUSD intradía; US30 y US500 intradía; GBPUSD/EURUSD en H4; las
  familias de pullback y compresión de volatilidad.
- Datos: Dukascopy M1 2011-2026 de US100, US500, US30, XAUUSD, EURUSD, GBPUSD y USDJPY, que se agregan
  a M15/M30/H1/H4. **Solo hay bid**: el spread viene del bróker (mediana por hora; motor v2).

## 2. Reglas

- `AGENTS.md`: solo paper/demo; ninguna orden; no activar bots ni F13; no desplegar EAs; no tocar
  `.env`; sin push; no borrar archivos.
- **No se toca producción:** EA `us100-ftmo1`, forward, `ai_trader`, Prop Fund/`prop/`, riesgo FTMO,
  `execution/`, `config/propfund/`, `schedule.yaml`. `config/discovery/engine.yaml` **no** se cambia:
  sus umbrales se congelaron el 2026-11-21.
- El contador lo lleva el propio motor (`register` escribe `n_total` antes de correr; `count_tests`
  suma discovery). **No** se usa `record-informal`.
- **Plantillas nuevas solo con los bloques que ya tiene el DSL.** Si falta un bloque, la plantilla se
  marca `Sin bloque en el DSL` y se sigue sin ella: en esta cola no se modifica el motor.
- **Nada se decide después de ver resultados:** combinaciones, segmentos, perfiles y puertas quedan
  fijados en X1, antes de la primera ejecución. La pasada 2 sigue una regla escrita aquí.
- Commits por ruta. Para README/PLAN/`ESTADO.md` se usa el lock `readme-plan` de
  `src/tradinglab/orq_lock.py` si TL3-E ya lo creó. Si no, se escriben solo después del tag
  `tl3-ciclo1f`.
- Fallo técnico: 3 reintentos y después `bloqueado: <motivo>`, y se sigue. Si falta un dato:
  **Sin datos**.

## 3. Bloques

### X0 · Preparación y auditoría de costes (no suma)
1. `git add -f .orquestador/COLA-EDGE-1.md`; commit `edge1: X0 - cola`.
2. `lab discovery data-check` de los 7 activos con `--source dukascopy`. Anota la cobertura por año y
   los huecos (D3 ya mostró que US100 tiene pocas velas nocturnas antes de 2018).
3. **Tabla de costes por activo y TF**, sin rendimiento, en `TL3_REPORTS/edge1_costes.md`:
   - spread (mediana y p75 por hora del bróker);
   - comisión por lado de CFD-001 y CFD-006;
   - swap por noche con el modelo `historical`;
   - slippage supuesto de `engine.yaml`.

   Cada uno en precio, en bps y en R con el stop mediano de un ATR(14) del TF.
   **Comprobación de magnitudes**, con `tl3.verify.magnitude` si existe o con un assert:
   - swap de un índice entre 0,5 y 5 bps/noche;
   - spread de US100 entre 0,3 y 3 bps;
   - comisión sin "Sin datos".

   Fuera de rango = `bloqueado: coste fuera de magnitud` para ese activo. Es la lección de T8, H1 y C1.
4. `lab discovery edge-map` y `lab discovery suggest`, con `--account CFD-001` y `CFD-006`: qué
   combinaciones activo × TF cumplen `cost_r_max` 0,10. Las que no lo cumplen quedan fuera, con su
   motivo.
5. **Ensayo sintético:** `lab discovery run <id> --synthetic` en un borrador por TF (M15, M30, H1 y H4),
   para comprobar la mecánica (horas, sesiones, costes por barra) sin datos reales. Si algo falla, se
   arregla **antes** de X1.
6. Commit `edge1: X0 - costes, viabilidad y ensayo`.

### X1 · Plan de campañas congelado (antes de ejecutar nada)
1. **Plantillas.** Las 10 de `config/discovery/templates/` más estas 4 nuevas, cada una con su
   mecanismo económico escrito en el YAML:

   | Plantilla nueva | Idea | Por qué debería existir |
   |---|---|---|
   | `trend_pullback_mtf` | Tendencia en H4/D1 (precio frente a la media o el canal); entrada en un retroceso de M15/M30/H1 | La tendencia persiste y se paga por dar liquidez en los retrocesos |
   | `vol_squeeze_breakout` | Volatilidad realizada en un percentil bajo (compresión) y ruptura del rango | La volatilidad se agrupa en regímenes; tras la compresión viene la expansión |
   | `london_breakout` | Ruptura del rango asiático en la apertura de Londres (EURUSD, GBPUSD, XAUUSD) | Llega información y liquidez en la apertura europea (es lo contrario de `asia_range_reversion`) |
   | `st_reversal_idx` | Reversión de corto plazo en índices: RSI(2) o IBS extremo, salida por tiempo o a la media | Sobrerreacción y provisión de liquidez a corto plazo |

2. **Matriz.** Plantilla × activo × TF, **solo** las combinaciones que la plantilla admite (según su
   YAML) y que X0.4 da por viables. Máximo **28 campañas** en la pasada 1. Si salen más, se priorizan
   por el menor `cost_r` mediano.
3. **Segmentos**, iguales para todas (fuente `dukascopy`):
   - IS = `2012-01-01:2019-12-31`;
   - OOS-1 = `2020-01-01:2022-12-31`;
   - OOS-2 = `2023-01-01:` (sellado; una sola lectura con `confirm`).
4. **Contaminación declarada desde ahora:** en US100, US500 y US30, las plantillas de la sesión de
   apertura de NY (`ny_open_vol_filter`, `session_breakout_htf` y cualquier ORB) tienen el OOS-2 dentro
   del periodo de diseño del EA `us100-ftmo1` (2021-2026). Su `confirm` **no** vale como validación;
   un finalista de esas plantillas va a forward, no a "validado".
5. Costes: `--cost-account CFD-001 --cost-account CFD-006 --cost-mode worst` (el peor de los dos,
   conservador). Perfil `small` y `--mode ga`. Semilla por campaña = índice en la matriz.
6. Registra **todos** los borradores con `--dry-run` primero y luego de verdad. Escribe la matriz,
   `n_total` por campaña y la suma en `TL3_REPORTS/edge1_plan.md`, con su hash. Commit
   `edge1: X1 - plan congelado`. A partir de aquí la matriz no cambia.

### X2 · Pasada 1 (suma al contador)
- `lab discovery approve <id> --approved-by-operator` y `lab discovery run <id> --approved-by-operator
  --time-limit <45 min>`, una campaña tras otra, en el orden de la matriz.
- Tras cada campaña:
  - una línea en `TL3_REPORTS/edge1_progreso.md`: id, activo, TF, plantilla, evaluadas, efectivas,
    finalistas, estado y tiempo;
  - comprobación de que aparece en la consola (`/api/discovery/campaigns` responde con ella).
- Commit cada 4 campañas: `edge1: X2 - campañas k-k+3`.

### X3 · Robustez de los finalistas (no suma: falsificación)
Para cada finalista de la pasada 1:
- `lab discovery robustness`, `perturb` y `power`;
- estrés de costes: spread p75 y slippage ×2.

Resultado por finalista en `TL3_REPORTS/edge1_finalistas.md`.

### X4 · Pasada 2 (suma; regla fijada ahora)
- Se repiten, con perfil **`medium`** y semilla nueva, las campañas de la pasada 1 con al menos
  **1 finalista que pasó X3 completo**. Máximo 6, por orden de más finalistas que pasaron y, a
  igualdad, menor `cost_r`.
- Si ninguna cumple, X4 = `sin pasada 2` y se sigue.
- Se registran antes de ejecutar, igual que en X1-X2, y sus finalistas pasan por X3.

### X5 · Confirmación OOS-2 (una lectura por finalista)
Solo para los finalistas que pasan **las 4 puertas** de §4:
- `lab discovery confirm <strategy_id> --approved-by-operator`;
- **una vez** por estrategia;
- veredicto literal del motor.

Los de plantillas contaminadas (X1.4) se marcan "a forward, OOS-2 no válido".

### X6 · EAs para el Strategy Tester (sin desplegar)
- Por cada estrategia que pasa X5 (o que va a forward según X1.4):
  `lab discovery export-mql5 --strategy-id <id> --account CFD-001` con los límites diario y máximo de
  la cuenta.
- Los `.mq5` van a `exports/edge1/`. **No** se copian al terminal, no se compilan en MT5 y no se
  despliegan: eso lo hace el operador.
- Ficha por EA: reglas, costes y avisos.

### X7 · Consola y mapa
- Comprueba en la consola (`lab web`, Discovery) que se ven, para cada campaña y finalista, el TF, el
  activo, la plantilla, el **desglose de costes** (spread, comisión, swap y slippage) y el estado.
- Si falta M15/M30 o el desglose de costes en la vista, ajusta `web.py` y `webui/index.html` (no son
  producción), con un test de la API.
- `ESTADO.md`: añade la sección "Campañas EDGE-1" con el número de campañas, finalistas, confirmadas,
  EAs exportados y el `count_tests` nuevo.

### X8 · Cierre y aviso
- `ruff`, `pytest -q`, `lab doctor` y `lab propfund verify`. README/PLAN con una línea.
- Tag `edge1`.
- Resumen a Telegram (`lab telegram send --file`; si no hay Telegram, `lab alerts send`). Formato
  **Hecho / 1..N / Aviso / Siguiente**, con:
  - campañas ejecutadas;
  - finalistas, con cuántos pasaron X3 y X5;
  - EAs exportados;
  - el `count_tests` antes → después;
  - bloqueos.
- Fin de la cola.

## 4. Puertas para ir a `confirm` (fijadas antes de ejecutar)

Un finalista lee el OOS-2 **solo** si cumple las cuatro:
1. Las validaciones del motor por TF (`engine.yaml`: `min_trades_is`, folds y `cost_r_max` 0,10) y
   un OOS-1 con expectativa neta > 0.
2. Robustez: walk-forward con eficiencia ≥ 0,3, PBO dentro del umbral del motor y `perturb` con
   `min_median_ratio` ≥ 0,5.
3. Costes: sigue con expectativa neta > 0 con el spread p75 y el slippage ×2.
4. No está en un clúster con correlación > 0,7 junto a otro finalista ya confirmado (se queda el de
   menor `cost_r`).

**"Validado" = pasa `confirm` en una plantilla no contaminada.** Todo lo demás es candidato o forward.
