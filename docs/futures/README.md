# TradingLab Futures-First · punto de entrada

**Proyecto:** `proyecto-futures` · **Creado:** 2026-11-27 por Claude Code (arquitecto).
**Encargos:** "TradingLab — Ultimate Master Prompt" (futuros y prop firms) y "Master Open-Source
Research, Claude Code Extensions & Engineering Orchestration Prompt", del operador, 2026-11-27.

## Plan vigente (2026-11-28)

**Decisiones del operador (2026-11-28):**
- Todo lo que no sea futuros queda en segundo plano.
- Solo datos de futuros CME: nada de CFD, Dukascopy ni MT5 como datos o proxy.

**Estado:**
- **Diseño e investigación de Claude:** hechos. Incluye la auditoría, la arquitectura, la especificación
  EV, los hooks, las skills, los agentes, las 10 firmas, el riesgo, Research A y B, la matriz de
  plataformas y dos borradores de programa.
- **Ninguna estrategia está validada** (`NO EDGE VALIDATED`). Todo el dimensionamiento es condicional.
- **Siguiente:**
  - el operador decide OP-4 (compra de datos), OP-7 (comisiones de MES y MGC) y OP-8 (sello del holdout
    de futuros);
  - OpenCode (DeepSeek V4.1 Flash) implementa FUT-A1/A2/B1/B3, que están READY;
  - Claude sigue con FUT-J0 (contrato de ejecución) y lo que quede en `CONTINUACION.md`.

## Documentos

| # | Documento | Contenido | Estado |
|---|---|---|---|
| 0 | `00_AUDITORIA_REPO.md` | Auditoría del repo con el enfoque futures-first (FUT-01…16) | hecho |
| 1 | `01_MATRIZ_TECNOLOGIA.md` | ~70 repos: licencia y actividad verificadas, decisión A-E, pila mínima, licencias y seguridad, proyectos descubiertos, PoC | hecho |
| 2 | `02_EXTENSIONES_CLAUDE_CODE.md` | Plugins oficiales y de la comunidad (manifiestos leídos), configuración mínima, instalación y vuelta atrás, MCP, skills, subagentes y hooks | hecho (diseño) |
| 3 | `03_ARQUITECTURA_FUTURES.md` | Componentes, datos de futuros, backtesting, riesgo y ejecución, matriz de plataformas inicial, programas A/B, ADR-F01…F10 | propuesta |
| 4 | `04_SPEC_PROP_EV.md` | Especificación matemática del motor EV con vectores de prueba exactos | lista para implementar tras OP-1 |
| 5 | `05_COLA_Y_ROADMAP.md` | Hoja de ruta, decisiones del operador (OP-1…OP-8), cola y prompts de OpenCode (DeepSeek V4.1 Flash) | activa |
| — | `CONTINUACION.md` | Plan de trabajo autónomo de Claude entre sesiones | activo |
| R | `research/propfirms_2026-11/` | 10 fichas de firmas, informe con ranking, diseño del Prop Firm Intelligence Engine | hecho (FUT-R3) |
| R | `research/prop_firms_2026-11-27.md` | Verificación de Topstep y estado de las demás | hecho |
| R | `research/RB_spec.md` | Research B (NY open): 8 hipótesis, contaminación por instrumento, familia FUT-RB-1 (5 pruebas en ES/GC) | borrador de prerregistro (FUT-D0) |
| R | `research/RA_spec.md` | Research A (order flow): hipótesis A-J, niveles de datos, familia FUT-RA-1 (6 pruebas NQ→MNQ) | borrador de prerregistro (FUT-C0) |
| R | `research/platform_matrix.md` | NinjaTrader 8, Tradovate y ProjectX con documentación oficial y términos de acceso | hecho (FUT-E1) |
| R | `research/programs/` | Borradores YAML de MFF Rapid 50K y Lucid Flex 50K | borrador (FUT-A10 los lleva a `config/`) |
| K | `risk/` | Auditoría de riesgo, Kelly, ruina, 6 perfiles a 6/12/24 meses, ORPAE, módulos MOD-NR/MOD-PR, simuladores | hecho (FUT-RISK) |
| C | `../../config/prop_economics/firms_futures.yaml` | Catálogo de 10 firmas por bots y modo de ejecución | hecho (FUT-R2) |

## Informes que el encargo pide y dónde están

| Informe pedido | Dónde |
|---|---|
| Repository Audit | `00` |
| Open-Source Technology Matrix · License and Security Matrix | `01 §1-2` |
| Claude Code Extension Audit · Skills and Agents Architecture | `02` |
| Futures Data Architecture · Backtesting Architecture | `03 §3-4` |
| Platform Capability Matrix | `research/platform_matrix.md` (FUT-E1) |
| Prop Firm Expected Value Specification | `04` |
| Order Flow / NY Open Research Specification | `research/RA_spec.md` y `research/RB_spec.md` (marco en `03 §7`) |
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
