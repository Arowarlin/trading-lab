# COLA EDGE-2 · Fábrica de estrategias en índices (US100, US500, US30)

**Creada:** 2026-11-25 por Claude a petición del operador ("Sí, EDGE-2"). Complementa EDGE-1, que solo
cubrió forex y oro.
**Motor, reglas generales, puertas (§4) y bloques X3-X6:** los mismos de `COLA-EDGE-1.md`, salvo lo que
se cambia aquí.
**Modo:** cadena continua Y0 → Y8, sin pedir confirmación. Un commit pequeño por bloque.
**Arranque:**
- Y0-Y1 (diagnóstico, costes y plan; no suman) pueden empezar ya.
- Y2 en adelante (approve/run) espera al tag `edge1`, es decir, a que EDGE-1 cierre X8: así no compiten
  por la CPU ni por `discovery.db`. Se comprueba cada 10 min, sin límite.

**Autorización:** solo corre si el mensaje del operador que la lanza contiene literalmente
`APRUEBO CAMPAÑAS EDGE-2`. Esa frase cubre `approve`/`run` del plan congelado en Y1 y **un**
`confirm` por finalista que pase las 4 puertas de `COLA-EDGE-1.md §4`.

## 1. Por qué EDGE-1 dejó fuera los índices, y qué se corrige

| Motivo en EDGE-1 X0 | Qué se hace en EDGE-2 |
|---|---|
| **US100 bloqueado** por swap CFD-001 6,24 bps/noche > 5 | **Enmienda de la cota (Claude, escrita antes de cualquier resultado de EDGE-2).** La comprobación de magnitud existe para cazar errores de **unidades** (T8: ×100). Nueva regla: el swap de un índice es válido si está entre **⅓ y 3×** la referencia de tipo de interés de esa noche (CFD-006 ≈ 2,44 bps), es decir, entre 0,8 y 7,3 bps. 6,24 pasa. Con `--cost-mode worst`, el swap alto de FTMO penaliza las posiciones que duermen, lo que es conservador |
| **US30** sin spread en `broker_spreads` | Buscar el spread medido en `config/propfund/costs.measured.yaml` y `config/costs.yaml` (US30 aparece en ambos). Si hay mediana por hora o p75 por cuenta, se usa y se cita. Si no, US30 = **Sin datos** y queda fuera |
| **Índices H1/H4 con `data-check` FAIL** (812/791 huecos no programados frente a 20 en M15) | **Diagnóstico** en Y0. Probablemente sea un efecto de la combinación `gap_factor` × TF con `max_gap_hours`, o de los huecos nocturnos de Dukascopy anteriores a 2018 (ver D3). No se cambian los umbrales de `engine.yaml` |
| **US500 M15/M30** con `cost_r` > 0,10 | Sigue fuera: la puerta de coste no se toca |

## 2. Reglas propias

- Todas las de `COLA-EDGE-1.md §2`, más el lock `proyecto-edge2`.
- **No se modifican** `scripts/edge1_*.py` mientras EDGE-1 esté abierta. EDGE-2 usa sus propias copias
  `scripts/edge2_*.py`, con el prefijo de campaña `edge2-` como parámetro.
- **Plantillas de la sesión de apertura de NY excluidas** (`ny_open_vol_filter`,
  `session_breakout_htf` y cualquier ORB). En índices, todo su OOS cae en el periodo de diseño del EA
  `us100-ftmo1`: solo se pueden validar en forward (como NQF).
- **Contaminación débil, declarada:** OOS-1 y OOS-2 de índices (2021-2026) coinciden con el periodo de
  diseño del EA. Para las plantillas que no son de apertura (pullback, compresión, Donchian, reversión
  y momentum de cierre), la lógica del EA no se transfiere, pero el laboratorio ya ha mirado mucho
  US100 en esos años. Se anota en cada informe.
- El estudio paralelo `edge1_h1_ny_impulse` (otra sesión) **no** forma parte de esta cola. No se
  toca ni se usa.

## 3. Bloques

### Y0 · Diagnóstico y costes (no suma)
1. `git add -f .orquestador/COLA-EDGE-2.md`; commit `edge2: Y0 - cola`.
2. **Huecos de índices en H1/H4:**
   - Para US100 y US500, tabla por año y duración de los huecos que `data-check` cuenta como "no
     programados" en H1 y H4, frente a M15.
   - Clasifica cada uno: noche corta de Dukascopy antes de 2018, festivo o cierre temprano, pausa
     diaria o hueco real.
   - Conclusión literal:
     - **error del control** (p. ej. una pausa programada que en H1 no se reconoce): corrígelo en el
       código de `data-check`, no en los umbrales, con un test sintético que reproduzca el caso, y
       vuelve a pasar `data-check`;
     - **huecos reales anteriores a 2018:** el desarrollo de H1/H4 empieza el 2018-01-02 (§Y1.3);
     - **huecos reales posteriores a 2018:** esa combinación queda fuera.
3. **Costes** de US100, US500 y US30 (si hay dato) en M15/M30/H1/H4, en el mismo formato que
   `TL3_REPORTS/edge1_costes.md`, aplicando la cota de swap enmendada (§1).
4. **Viabilidad:** `edge-map`/`suggest` con `cost_r_max` 0,10 y `--cost-mode worst`.
5. Ensayo `--synthetic` de un borrador de índice por TF.
6. Informe `TL3_REPORTS/edge2_costes.md`. Commit `edge2: Y0 - diagnostico, costes y ensayo`.

### Y1 · Plan congelado (antes de ejecutar nada)
1. **Plantillas:** `trend_pullback_mtf`, `vol_squeeze_breakout`, `donchian_vol_h4` y
   `st_reversal_idx`, solo en las combinaciones que admite cada YAML.
   - **Excluida `intraday_momentum_close_v2`** (enmienda de Claude, 2026-11-25 21:20, escrita antes
     de Y1). Su sesión termina a las 15:55 con `flat_at` 15:55. En `fastbt._session_mask`,
     `flat_flag = (relative >= flat_relative) & (relative <= duration)`, así que en M15, M30 y H1
     ninguna vela cae en esa franja y la posición **nunca se cierra en el día**: el mismo fallo que
     encontró F2 en H-2026-013.
   - El arreglo del motor se hará en otra cola, **después** del tag `edge1`. EDGE-1 lanza
     `lab discovery run` en procesos nuevos, así que cambiar `fastbt.py` ahora alteraría sus
     campañas restantes.
   - Las plantillas de EDGE-1 no se ven afectadas: `asia_range_reversion` y `london_breakout` caen en
     una vela con `relative == duration`, y las de sesión de 24 h son de varios días por diseño.
2. **Activos y TF:** US100, US500 y US30 (si Y0 trajo coste) × M15/M30/H1/H4, solo con `cost_r` ≤ 0,10
   y `data-check` válido. Máximo **20 campañas**. Si salen más, se priorizan por menor `cost_r`.
3. **Segmentos:**
   - **M15/M30:** IS = `2014-01-02:2019-12-31`, OOS-1 = `2020-01-01:2022-12-31`,
     OOS-2 = `2023-01-01:` (sellado).
   - **H1/H4:** IS = `2018-01-02:2020-12-31`, OOS-1 = `2021-01-01:2022-12-31`, OOS-2 = `2023-01-01:`.
     Si Y0 demostró que el control de huecos daba un falso fallo y lo corrigió, se usa el mismo
     segmento que en M15/M30. La decisión se escribe aquí antes de registrar.
4. Costes `--cost-account CFD-001 --cost-account CFD-006 --cost-mode worst`. Perfil `small` y
   `--mode ga`. Semilla = índice en la matriz.
5. `register` con `--dry-run` y después real. Plan, `n_total` y hash en `TL3_REPORTS/edge2_plan.md`.
   Commit `edge2: Y1 - plan congelado`. La matriz no cambia después.

### Y2 · Pasada 1 (suma). **Espera al tag `edge1` y al tag `robust-1`.**
Enmienda de Claude (2026-11-26): `COLA-ROBUST-1.md` corrige el `point` del retester (estrés de
slippage), revisa el PBO y comprueba la coherencia del plan. Si `robust-1` recongela el plan (Y1b),
se usa ese plan.
- Igual que EDGE-1 X2: `approve` y `run --approved-by-operator --time-limit <45 min>`, una campaña tras
  otra.
- Progreso en `TL3_REPORTS/edge2_progreso.md`. Commit cada 4 campañas.

### Y3-Y6 · Robustez, pasada 2, confirm y EAs
- Exactamente como EDGE-1 X3-X6 y las 4 puertas de `COLA-EDGE-1.md §4`, con `scripts/edge2_*.py`.
- La pasada 2 (perfil `medium`) es como máximo de 4 campañas.
- EAs en `exports/edge2/`, sin desplegar.

### Y7 · Consola y mapa
- Las campañas `edge2-` se ven en la consola Discovery con el desglose de costes.
- `ESTADO.md`: sección "Campañas EDGE-2" y el `count_tests` nuevo.

### Y8 · Cierre y aviso
- Igual que EDGE-1 X8, con el tag `edge2`.
- Telegram con: campañas, finalistas, cuántos pasan Y3 e Y5, EAs, `count_tests` antes → después,
  diagnóstico de los huecos de H1/H4 y situación de US30.

## 4. Nota sobre el contador
EDGE-1 lleva `count_tests` de 1926 a unas 14.250. EDGE-2 suma como máximo 20 × 440 = 8.800 más. El
listón del DSR crece con √(2·ln N), así que de 14.250 a 23.000 pruebas sube apenas un **2-3 %**: una
vez hecho el barrido amplio, ampliar el universo cuesta poco.
