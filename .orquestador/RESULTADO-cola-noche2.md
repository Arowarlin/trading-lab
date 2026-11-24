# RESULTADO · COLA-NOCHE2 — trabajo desatendido

Fecha: 2026-11-23. Sesión única en `E:\trading-lab`, HEAD `4d6f2c0`.
Sin register/approve/run/confirm/supersede, sin OOS-2, sin rendimiento de
specs no aprobadas, sin push, sin tareas programadas, sin borrar, sin
umbrales, sin protegidos, sin carril del EA, sin operar.

## N1 · Anclaje del cambio de mes

Ejecutado `COLA-tom-anclaje.md` entero. Informe completo en
`.orquestador/RESULTADO-tom-anclaje.md`.

Resultado: **sí había desfase de un día**. La etiqueta D1 es la apertura
17:00 NY del día anterior; `month_turn` mapeaba por etiqueta en
`compiler.py:388-389` (HEAD). Con datos reales de US500:

- antes: 69 señales N=1,M=2 en todo el histórico; los meses que terminan en
  viernes o víspera de festivo se perdían;
- después: 173 señales; 182 pares de calendario, 9 sin barra por huecos de
  datos;
- entrada y salida corregidas al cierre de la sesión NYSE N y M,
  respectivamente.

Cambio:

- `src/tradinglab/discovery/compiler.py:384-401`: `_session_dates` identifica
  la sesión por la frontera 17:00 NY.
- `src/tradinglab/discovery/compiler.py:414-432`: `_month_turn_signals` usa
  fechas de sesión para señales y `exit_index`.
- `tests/test_discovery_turn_of_month.py`: 3 tests nuevos/actualizados para
  sesión real, junio 2024 (viernes), noviembre 2024 (Acción de Gracias) y
  N=2/M=4 con el 4 de julio. **8 passed**.
- Specs `r9-tom-*` sin modificar. Q1 (`d1_extension_reversion`) no usa
  calendario: no le afecta.

Las campañas `r9-tom-us500-d1` y `r9-tom-us100-d1` **no se han tocado**:
están `done`, con `n_evaluated=9` cada una (US500 tiene 10 filas de
evaluación) y snapshots del código antiguo.

### Decisión humana pendiente: retirar las campañas viejas

El `supersede` que pedía la cola **no puede ejecutarse** con el código actual:

- `campaigns.py:701` solo acepta `rejected`/`registered`; ambas están `done`.
- `campaigns.py:705` rechaza campañas con evaluaciones; ambas tienen 9.
- La CLI (`cli.py:11162-11167`) no tiene `--reason`, y
  `campaigns.supersede` (`campaigns.py:677-683`) no recibe motivo.
- `supersede` genera un id `disc-…`, no `r9b-…`.

Opciones:

1. Registrar `r9b-…` sin retirar las viejas: no toca código, pero suma 9+9
   pruebas al contador (doble conteo de la hipótesis). Las specs
   `r9b-tom-us500-d1.yaml` y `r9b-tom-us100-d1.yaml` quedan preparadas,
   idénticas salvo `campaign_id`.
2. Autorizar un cambio auditado de `supersede` para campañas `done` con
   motivo: la vieja pasa a `superseded` y deja de contar, sin doble conteo.
   Decisión de integridad; no se implementa aquí.

Por la regla de la cola («si algo falla o exige decisión humana: escríbelo y
PARA TODO»), **N2 y N3 no se ejecutan**.

## Comandos pendientes del operador

```powershell
cd E:\trading-lab

# A) Intento tal como lo pedía la cola: FALLA con el código actual
#    (campaña done + evaluaciones; la CLI no acepta --reason).
# .\.venv\Scripts\lab.exe discovery supersede r9-tom-us500-d1 --approved-by-operator
# .\.venv\Scripts\lab.exe discovery supersede r9-tom-us100-d1 --approved-by-operator

# B) Opción sin cambiar código: registrar r9b (suma 9+9 pruebas al contador).
.\.venv\Scripts\lab.exe discovery register --spec .orquestador/specs/r9b-tom-us500-d1.yaml
.\.venv\Scripts\lab.exe discovery preflight r9b-tom-us500-d1
.\.venv\Scripts\lab.exe discovery approve r9b-tom-us500-d1 --approved-by-operator
.\.venv\Scripts\lab.exe discovery run r9b-tom-us500-d1 --approved-by-operator
.\.venv\Scripts\lab.exe discovery results r9b-tom-us500-d1

.\.venv\Scripts\lab.exe discovery register --spec .orquestador/specs/r9b-tom-us100-d1.yaml
.\.venv\Scripts\lab.exe discovery preflight r9b-tom-us100-d1
.\.venv\Scripts\lab.exe discovery approve r9b-tom-us100-d1 --approved-by-operator
.\.venv\Scripts\lab.exe discovery run r9b-tom-us100-d1 --approved-by-operator
.\.venv\Scripts\lab.exe discovery results r9b-tom-us100-d1

# C) Opción sin doble conteo: autorizar primero un cambio auditado de
#    supersede para campañas done; después, con el nuevo código:
# .\.venv\Scripts\lab.exe discovery supersede r9-tom-us500-d1 --approved-by-operator
# .\.venv\Scripts\lab.exe discovery supersede r9-tom-us100-d1 --approved-by-operator
#    y revisar el id nuevo antes de registrar nada más.
```

## Verificación

- `ruff check src/tradinglab tests docs`: limpio.
- `pytest -q`: **1796 passed, 1 skipped**.
- `lab propfund verify`: **4 OK**.
- `count_tests`: **1865** (sin cambios).
- Commit `tl2: month_turn - anclaje por sesión`, tag `tl2-tom-anclaje`.
- `git status`: solo cambios de N1 y `?? tl2-edge-map.patch` antes del commit.

PARADA EN N1: `supersede` no puede retirar campañas `done` con
`n_evaluated=9`; hace falta decisión del operador sobre el doble conteo. N2 y
N3 no ejecutadas.

PARA.
