# MASTER_PLAN · Programa ENG-1

**Creado:** 2026-11-26 por Claude Code a petición del operador (prompt "TradingLab Master Engineering
Orchestration").
**Objetivo:** que TradingLab pueda demostrar, o descartar con evidencia, una ventaja neta de costes.
El número de estrategias aprobadas no es un KPI; el KPI es reducir falsos positivos.

## 1. Cómo se relaciona con lo que ya existe

- Las colas de `.orquestador/COLA-*.md` siguen siendo las colas operativas del equipo del operador.
  ENG-1 **no las sustituye ni las edita**: es un programa de auditoría y corrección que produce
  hallazgos y propone colas nuevas.
- `ESTADO.md`, `README.md` y `PLAN.md` solo se actualizan al cerrar un bloque y bajo el lock
  `readme-plan`, que vive en el equipo del operador. Desde la nube **no se tocan**.
- Las reglas de `AGENTS.md` mandan sobre este plan.

## 2. Arquitectura de trabajadores (la real, no la ideal)

| Pieza | Dónde corre | Qué puede hacer | Qué no puede |
|---|---|---|---|
| **Claude Code (coordinador)** | Sesión en la nube, Linux, 4 núcleos, sin datos | Leer el repo, auditar, pruebas sintéticas, tests que no dependen de datos, escribir `docs/engineering/`, commits en la rama `claude/...` | Ver procesos, locks, datos, `discovery.db`, MT5 ni Telegram del operador |
| **Subagentes de Claude** (A-D, luego E-F) | La misma sesión | Auditorías paralelas de **solo lectura**; cada uno escribe un único informe en `WORKER_REPORTS/` | Editar código |
| **OpenCode (DeepSeek V4.1 Flash)** | Equipo del operador (Windows, Ryzen 9 5950X, 64 GB) | Lo que necesita datos reales o el entorno local: reproducir hallazgos con datos, tests locales, `lab doctor`, comprobar procesos y locks | Integrar en `master`, lanzar campañas, tocar componentes protegidos |

**No hay OpenCode en este contenedor.** Los prompts para OpenCode están en `OPENCODE_PROMPTS.md`,
escritos para DeepSeek V4.1 Flash: pasos numerados, lista cerrada de ficheros, condición de PARA.

### Reglas de paralelismo
- Cada trabajador de OpenCode que escriba código usa su propio worktree:
  `git worktree add ..\tl-eng-<id> -b eng/<id> master`. Nunca dos en la misma carpeta.
- Un fichero tiene un solo dueño a la vez (columna *Archivos* de `TASK_QUEUE.md`).
- Como mucho **2 trabajos pesados** a la vez en el equipo del operador (EDGE-2 ya ocupa uno) y
  reserva para LM Studio.
- Nadie integra en `master`: Claude revisa el diff y las pruebas y el operador hace el merge.

## 3. Fases y puertas

| Fase | Contenido | Puerta de salida | Estado |
|---|---|---|---|
| 0 | Baseline y seguridad | `BASELINE_REPORT.md` | **Hecha** |
| 1 | Auditorías paralelas A (motor), B (costes), C (datos), D (estadística) | Informes en `WORKER_REPORTS/` revisados por Claude | En curso |
| 2 | Consolidación y priorización | `AUDIT_FINDINGS.md` con severidad y reproducción | Pendiente |
| 3 | Correcciones aisladas **no bloqueadas** por EDGE-2 (tests, CI, lock de dependencias, código fuera del motor) | Test que falla antes y pasa después; diff revisado | Pendiente |
| 3b | Correcciones del motor (`fastbt`, `costs`, sesiones, métricas) | **Bloqueada** hasta el tag `edge2` y sin `lab discovery run` vivo; se preparan como test + parche en rama, sin integrar | Bloqueada |
| 4 | Validación estadística (DSR, PBO, bootstrap por bloques, SPA) | Propuesta con supuestos; cambio de umbrales solo con aprobación | Pendiente |
| 5 | Datos NQ/MNQ y TCA | Comparativa de proveedores (sin comprar) y diseño TCA | Pendiente |
| 6 | Nuevas hipótesis (NQ microestructura, NY open, FX sesiones, regímenes) | Prerregistro escrito **antes** de cualquier resultado; ninguna campaña sin aprobación | Pendiente |
| 7 | Rendimiento | Benchmark con igualdad de operaciones bit a bit | Pendiente |
| 8 | CI, integración y documentación | CI verde sin desactivar tests | Pendiente |

## 4. Lo que exige aprobación explícita del operador
Lanzar campañas o barridos que sumen al DSR · tocar componentes protegidos · integrar cambios que
alteren resultados históricos · cambiar umbrales · comprar datos · `git push` (AGENTS.md) · parar
EDGE-2 · leer el OOS-2 sellado.

## 5. Reanudación
1. Leer `AGENTS.md`, `ESTADO.md` y este fichero.
2. Leer `TASK_QUEUE.md` (estados) y la última entrada de `TASK_STATUS.md`.
3. `git log --oneline -10`, `git status`, procesos y locks (en el equipo del operador).
4. Seguir por la primera tarea `READY` cuyas dependencias estén `COMPLETED`.
