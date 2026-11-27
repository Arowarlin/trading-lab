# TradingLab Futures-First · punto de entrada

**Proyecto:** `proyecto-futures` · **Creado:** 2026-11-27 por Claude Code (arquitecto).
**Encargos:** "TradingLab — Ultimate Master Prompt" (futuros y prop firms) y "Master Open-Source
Research, Claude Code Extensions & Engineering Orchestration Prompt", del operador, 2026-11-27.

## Plan vigente

Fases 0-3 de diseño **cerradas en documentos, en solo lectura**: no se ha cambiado código, configuración,
datos, campañas, dependencias ni extensiones. Lo siguiente espera las decisiones OP-1…OP-7
(`05_COLA_Y_ROADMAP.md §2`). Primero el motor de valor esperado (FUT-A) y la estimación gratuita del
coste de datos (FUT-B1), en paralelo.

## Documentos

| # | Documento | Contenido | Estado |
|---|---|---|---|
| 0 | `00_AUDITORIA_REPO.md` | Auditoría del repo con el enfoque futures-first (FUT-01…16) | hecho |
| 1 | `01_MATRIZ_TECNOLOGIA.md` | ~70 repos: licencia y actividad verificadas, decisión A-E, pila mínima, licencias y seguridad, proyectos descubiertos, PoC | hecho |
| 2 | `02_EXTENSIONES_CLAUDE_CODE.md` | Plugins oficiales y de la comunidad (manifiestos leídos), configuración mínima, instalación y vuelta atrás, MCP, skills, subagentes y hooks | hecho (diseño) |
| 3 | `03_ARQUITECTURA_FUTURES.md` | Componentes, datos de futuros, backtesting, riesgo y ejecución, matriz de plataformas inicial, programas A/B, ADR-F01…F10 | propuesta |
| 4 | `04_SPEC_PROP_EV.md` | Especificación matemática del motor EV con vectores de prueba exactos | lista para implementar tras OP-1 |
| 5 | `05_COLA_Y_ROADMAP.md` | Hoja de ruta, decisiones del operador, cola y prompts de OpenCode (DeepSeek V4.1 Flash) | activa |

Pendientes de Claude (siguiente sesión): FUT-R1 (reglas oficiales de 6 firmas), FUT-E1 (plataformas),
FUT-C0 (especificación Research A), FUT-D0 (especificación Research B).

## Informes que el encargo pide y dónde están

| Informe pedido | Dónde |
|---|---|
| Repository Audit | `00` |
| Open-Source Technology Matrix · License and Security Matrix | `01 §1-2` |
| Claude Code Extension Audit · Skills and Agents Architecture | `02` |
| Futures Data Architecture · Backtesting Architecture | `03 §3-4` |
| Platform Capability Matrix | `03 §6` (inicial; se completa en FUT-E1) |
| Prop Firm Expected Value Specification | `04` |
| Order Flow / NY Open Research Specification | `03 §7` (marco); detalle en FUT-C0 / FUT-D0 |
| Benchmark Results | **Sin datos**: PoC pendientes de aprobación (`01 §5`) |
| Integration Roadmap · OpenCode Task Queue | `05` |
| Architecture Decision Records | `03 §8` |
| Change Log | `git log -- docs/futures`; producción sin cambios (no aplica `docs/CHANGELOG-produccion.md`) |

## Comprobaciones de esta sesión (nube, Linux)

- `ruff check .` → limpio.
- `pytest` con los marcadores de CI: ver §4.

## 4. Resultado de la suite

`pytest -q -m "not network and not mt5 and not lmstudio and not alpaca and not credentials"` sobre
`5b277cb` en Linux (Python 3.13, `uv sync --frozen --extra dev --extra discovery`), 2026-11-27:
**2163 passed, 22 skipped, 2 deselected, 0 failed** en 28:15. Avisos: `fork()` con hilos en
`multiprocessing` (Linux) y `psutil` no instalado en `discovery/jobs.py`. Línea base para comparar las
entregas de OpenCode.

Tras FUT-D1 (dependencias) y los tests de hooks y catálogo, 2026-11-27: **2224 passed, 22 skipped,
2 deselected, 0 failed** en 28:11 (+61 tests nuevos).
