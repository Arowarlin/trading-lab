# COLA MOTOR-FLAT · `flat_at` que nunca dispara en TF no alineados (motor Discovery)

**Creada:** 2026-11-25 por Claude a petición del operador ("Sí, prepárala").
**Tipo:** corrección del motor de investigación (`discovery/`). No es un componente de producción de
`AGENTS.md`, pero cambia resultados futuros: va con tests de identidad, nueva versión del motor y su
documentación.
**No suma al contador:** no se ejecuta ninguna campaña ni se calcula ningún PnL.
**Arranque:**
- Solo cuando existan los tags `edge1` **y** `edge2` (o `TL3_REPORTS/edge2_progreso.md` declare
  EDGE-2 cerrada o bloqueada);
- y **no haya ningún proceso `lab discovery run` en marcha** (compruébalo con `Get-CimInstance
  Win32_Process`).

Comprueba cada 10 min. Así ninguna campaña cambia de motor a mitad de una pasada.
**Modo:** cadena continua M0 → M6, sin pedir confirmación.

## 1. El fallo (verificado por Claude en solo lectura)

- `discovery/fastbt.py::_session_mask`:
  `flat_flag = (relative >= flat_relative) & (relative <= duration)`. El cierre se ejecuta a
  `close[i]` de la vela marcada (`fastbt.py:1039`, `reason = 3`).
- Las velas se etiquetan por su hora de **apertura**. Si ninguna vela empieza entre `flat_at` y el
  fin de la sesión, **ninguna se marca y la posición duerme**. Ejemplo: sesión 09:30-15:55 con
  `flat_at` 15:55 en M15, M30 o H1. F2 lo encontró en H-2026-013 (291 operaciones durmieron).
- `discovery/export_mql5.py::FlatFlag` aplica **la misma fórmula** con la hora de apertura de la vela
  (`iTime`), así que el EA exportado y el backtest **coinciden**: los dos se equivocan igual. Se
  corrigen juntos.
- **Plantillas de 24 h** (`trend_pullback_mtf`, `vol_squeeze_breakout`, `donchian_vol_h4`,
  `fix_reversal`; sesión 00:00-23:59, `flat_at` 23:55/23:59): hoy **nunca** cierran en M15, M30, H1
  ni H4, así que en EDGE-1 son estrategias de **varios días** (con swap). No se sabe si la intención
  era esa o un cierre diario. **No se decide aquí:** se conserva su comportamiento y se declara.

## 2. Diseño (sin romper nada)

- Nuevo campo opcional en `SessionSpec` (`dsl.py`):
  `flat_mode: "legacy" | "no_overnight"`, por defecto **`legacy`**.
  - **`legacy`:** la fórmula actual, **idéntica bit a bit**. Todo lo ya registrado y ejecutado
    (EDGE-1, EDGE-2, NQF, campañas antiguas) se reproduce igual.
  - **`no_overnight`:** además de lo anterior, se marca la vela que contiene el final de la sesión
    sin haber marcado ninguna antes:
    `relative < flat_relative and relative + tf_seconds > duration`. El cierre ocurre a su `close`,
    como mucho una vela después de `flat_at`, y la posición nunca duerme.
- Se implementa igual en `fastbt._session_mask`, en `export_mql5.FlatFlag` (constante `FLAT_MODE`
  en el `.mq5`) y en `discovery/drift.py`, que también usa `flat_flag`.
- **Aviso estático** en `preflight`/`feasibility`: si con `legacy` el `flat_at` no cae en ninguna
  vela de la sesión en ese TF, avisar con "flat_at no dispara en {TF}: la posición puede dormir" y
  la lista de TF afectados.
- `discovery.__version__`: subir la versión menor. Las campañas nuevas registran `engine_version`
  con ella.

## 3. Bloques

### M0 · Cola, comprobación de arranque y tag
- Comprueba la condición de arranque.
- `git add -f .orquestador/COLA-MOTOR-FLAT.md`; commit `motor-flat: cola`.
- Lock `proyecto-motor`. Tag `motor-flat-pre` sobre HEAD **antes** de tocar código.

### M1 · Tests que reproducen el fallo (antes de arreglarlo)
Con barras sintéticas en NY (horario de verano y de invierno):
- sesión 09:30-15:55 con `flat_at` 15:55: en M5 se marca la vela de las 15:55; en M15, M30 y H1
  **no** se marca ninguna;
- sesión 18:00-03:00 con `flat_at` 02:45: en H1 se marca la vela de las 03:00;
- sesión 24 h con `flat_at` 23:55: en H1 no se marca ninguna.

Los tests documentan el comportamiento `legacy` y deben pasar **antes y después** del cambio.

### M2 · Implementación de `flat_mode`
- Código en `dsl.py`, `fastbt.py`, `export_mql5.py` y `drift.py`, según §2.
- Tests de `no_overnight`:
  - con 09:30-15:55 en M15, M30 y H1 se marca la vela que contiene las 15:55 (15:45 en M15, 15:30
    en M30, 15:00 en H1);
  - ninguna operación sintética pasa la noche;
  - en M5 el resultado es idéntico a `legacy`.
- **Identidad:** en todas las plantillas de `config/discovery/templates/` y en M5, M15, M30, H1 y H4,
  `legacy` da el mismo `flat_flag` que en `motor-flat-pre`. Se comparan los arrays con barras
  sintéticas de 60 días.
- **EA:** el `.mq5` exportado con `legacy` es idéntico byte a byte salvo la línea de la versión y
  `FLAT_MODE`. Con `no_overnight`, `FlatFlag` reproduce el array de `fastbt` en las mismas barras
  (test con una tabla de horas).

### M3 · Inventario de lo afectado (sin cambiar registros)
- Recorre `disc_campaigns` (`config_json`: plantilla, sesión, TF) y lista cada campaña donde el
  `flat_at` **no dispara** con `legacy`:
  - las de 24 h (varios días por diseño, a declarar);
  - las de sesión intradía con TF no alineado (fallo real).
- Para EDGE-1, cruza con los finalistas y los EAs de `exports/edge1/`. Cada uno se marca "mantiene
  varios días (swap; revisar las reglas de fin de semana de la firma)" o "intradía correcto".
- Escribe un aviso por plantilla afectada con `tl3.warnings.add_warning` (subject
  `discovery:<plantilla>`). No se modifica ninguna campaña ni estrategia existente.
- Informe `TL3_REPORTS/motor_flat_inventario.md`.

### M4 · Plantillas intradía en `no_overnight`
- `intraday_momentum_close_v2` (y cualquier plantilla cuyo YAML diga que es intradía o de sesión) se
  versiona como **`_v3`** con `flat_mode: no_overnight`, en un fichero nuevo; el `_v2` no se toca.
- **No** se registra ninguna campaña.
- Las de 24 h se quedan en `legacy`. Su YAML gana un comentario "varios días: flat_at no dispara en
  TF ≥ M15".

### M5 · Cierre
- `ruff`, `pytest -q` completo y `lab doctor`.
- README §11 y PLAN, bajo el lock `readme-plan`.
- `ESTADO.md`: "motor flat_mode; intraday_momentum_close_v3 lista para una campaña futura".
- Commit por ruta, tag `motor-flat` y liberación de locks.

### M6 · Aviso
- Telegram (o `lab alerts send`) con el formato **Hecho / 1..N / Aviso / Siguiente**:
  - campañas afectadas por tipo;
  - finalistas y EAs de EDGE-1 que mantienen varios días;
  - plantillas `_v3`;
  - identidad `legacy` OK.
- **PARA.**
