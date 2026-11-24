# RESULTADO · R9b — contar miradas previas y blindar el pre-registro

Fecha: 2026-11-23. Sesión única en `E:\trading-lab`, HEAD `6e2125b` + R9b.
Sin registrar/aprobar/ejecutar campañas, sin OOS, sin push, sin tareas
programadas, sin borrar, sin operar y sin tocar el carril del EA.

## 1. Incidente y decisión

R9 calculó el rendimiento de `turn_of_month` antes de registrar: 36 miradas
(US500/US100 × Dukascopy/Databento × 9). Se miraron expectativa neta/bruta, PF,
coste, concentración y percentil de deriva; no se leyó OOS-1/OOS-2 ni se
escribió en `disc_*`, pero el contador DSR no las contaba y la recomendación de
R9 se basó en ellas. Es una violación de pre-registro.

Decisión del operador (literal, 2026-11-23): **"Contar todo"**.

- Se registran y ejecutan US500 y US100 Dukascopy (2 × 9 = 18 pruebas; las
  ejecuta el operador).
- Las 18 miradas Databento se anotan ahora en el contador.
- OOS-1/OOS-2 siguen limpios y deciden.

Incidente completo: `reports/discovery/incidente-r9-snooping.md`.

## 2. Anotación en el contador

Mecanismo nuevo:

```text
lab learning record-informal --n 18 --reason "..." --approved-by-operator
```

- Tabla `informal_trials` en `lab.db`; `count_tests` suma `SUM(n)`.
- Sin `--approved-by-operator` no escribe; el CLI lo dice y sale sin cambios.
- Test: `count_tests` sube exactamente `n` y la fila queda trazada con motivo,
  timestamp y aprobador.

Ejecutado:

```text
n = 18
reason = R9: miradas informativas turn_of_month Databento ES/NQ D1 (2×9)
         antes de pre-registro; decisión operador 'Contar todo' 2026-11-23
approved_by = operador
```

| Momento | count_tests |
|---|---:|
| Antes de R9b | 1757 |
| Tras la anotación | **1775** |
| Esperado tras registrar US500 y US100 Dukascopy | 1793 |

La fila `informal_trials` id=1 conserva el `n=18` y el motivo. No se borró ni se
reclasificó ninguna campaña.

## 3. Blindaje del pre-registro

Módulo `src/tradinglab/discovery/guard.py`:

- `require_approved` / `require_approved_campaign` /
  `require_approved_strategy`.
- `fitness.evaluate` exige `approved=True` (lo pone el worker desde
  `QueueSetup.approved`, calculado con `approved_at` de la campaña).
- `drift.evaluate` y `drift.percentile` exigen aprobación.
- `robustness.run` exige campaña aprobada.
- `perturb.noise_test`, `delay_test` y `execution_mc` exigen `strategy_id` de
  campaña aprobada.
- `run_campaign` y `run_queue` comprueban la campaña; `synthetic` se permite
  solo por la vía sintética explícita.
- `preflight` y `feasibility` siguen permitidos: solo operaciones, pliegues,
  coste_R y tiempo; no calculan expectativa/PF/percentil.

Flag interno de test: `TRADINGLAB_ALLOW_UNAPPROVED=1`, activado por el fixture
autouse de `tests/conftest.py`. Los tests que verifican el bloqueo lo apagan.

Regla añadida al BLOQUE COMÚN (`docs/tradinglab2/10`):

> Nunca calcules rendimiento (expectativa, PF, percentil de deriva, Monte Carlo,
> perturbaciones) antes de register+approve. Si ocurre, se anota en el contador
> con `lab learning record-informal --n N --reason "..." --approved-by-operator`.

Tests nuevos (`tests/test_discovery_guard.py`):

- `fitness.evaluate` rechaza campaña sin aprobar y acepta `approved=True`.
- `drift.percentile` rechaza sin aprobar.
- `record-informal` sin flag no escribe; con flag suma exactamente 18 y deja
  fila trazada.
- CLI `learning record-informal` sin flag no escribe; con flag escribe.

## 4. Specs de R9

Comprobación de contenido de las dos specs Dukascopy:

| Spec | Bytes | SHA256 (16) | Igual a R9 |
|---|---:|---|---|
| `r9-tom-us500-d1.yaml` | 1138 | `40546d39abad4f7d` | sí |
| `r9-tom-us100-d1.yaml` | 1138 | `382e9a364e6b5140` | sí |

No se cambiaron después de las miradas. Nota: `.orquestador/` está en
`.gitignore`, así que las specs **no están dentro del commit `6e2125b`**; la
comprobación se hizo contra el contenido exacto escrito en R9, no contra el
árbol de git. Las únicas specs modificadas después de R9 son las dos de
confirmación Databento, a las que se añadió `confirmation_only: true`; no son
las specs que ejecuta el operador.

## 5. Informe R9 corregido

`RESULTADO-R9.md` ya no recomienda ninguna spec por rendimiento. La sección de
evaluación informativa se sustituyó por la referencia al incidente y la
retirada de la recomendación; se mantienen las tablas de `preflight` y
`feasibility` (operaciones y coste, permitidas). No se borró ningún archivo.

## 6. Verificación

- `ruff check src/tradinglab tests docs`: limpio.
- `pytest -q`: **1773 passed, 1 skipped**.
- `lab propfund verify`: **4 OK**.
- `count_tests`: **1775**.
- `preflight`/`feasibility` siguen funcionando sin aprobación (probado con
  `r9-tom-us500-d1`: 9/9 factibles).
- Sin push, sin campañas, sin OOS, sin órdenes.

## Commits y tag

```text
dd2f1f8  tl2: R9b - contar miradas previas y blindar pre-registro  (tl2-r9b)
```

## Comandos para el operador (NO ejecutados)

Ambas campañas Dukascopy, en el orden que decida el operador. Registrar las dos
sube el contador de 1775 a 1793.

```powershell
cd E:\trading-lab

# US500
.\.venv\Scripts\lab.exe discovery register --spec .orquestador/specs/r9-tom-us500-d1.yaml
.\.venv\Scripts\lab.exe discovery approve r9-tom-us500-d1 --approved-by-operator
.\.venv\Scripts\lab.exe discovery run r9-tom-us500-d1 --approved-by-operator
.\.venv\Scripts\lab.exe discovery results r9-tom-us500-d1

# US100
.\.venv\Scripts\lab.exe discovery register --spec .orquestador/specs/r9-tom-us100-d1.yaml
.\.venv\Scripts\lab.exe discovery approve r9-tom-us100-d1 --approved-by-operator
.\.venv\Scripts\lab.exe discovery run r9-tom-us100-d1 --approved-by-operator
.\.venv\Scripts\lab.exe discovery results r9-tom-us100-d1
```

No se ha ejecutado ninguno. La spec de confirmación Databento sigue bloqueada
para registro real (D1 Databento) y no forma parte de estos comandos.

## Avisos

- El contador ya incluye las 18 miradas Databento; las 18 de Dukascopy se
  sumarán al registrar las campañas, no antes.
- El flag `TRADINGLAB_ALLOW_UNAPPROVED` es solo para tests; no debe usarse en
  una sesión de operador.
- La comprobación de specs contra `6e2125b` no es posible por git (directorio
  ignorado); se sustituyó por hash del contenido exacto de R9. No hubo cambios
  en las dos specs Dukascopy.

PARA.
