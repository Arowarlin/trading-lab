# TradingLab Futures-First · punto de entrada

**Proyecto:** `proyecto-futures` · **Creado:** 2026-11-27 por Claude Code (arquitecto).
**Encargos:** "TradingLab — Ultimate Master Prompt" (futuros y prop firms) y "Master Open-Source
Research, Claude Code Extensions & Engineering Orchestration Prompt", del operador, 2026-11-27.

## Plan vigente (2026-11-28)

**Decisiones del operador (2026-11-28):**
- Todo lo que no sea futuros queda en segundo plano.
- Solo datos de futuros CME: nada de CFD, Dukascopy ni MT5 como datos o proxy.

**Estado (actualizado el 2026-11-28, tras «apruebo todo… y también lo que opencode debe hacer»):**
- **Código implementado por Claude**, con tests exactos (todo en paper; nada live):
  - **Motor EV de prop firms** (`src/tradinglab/prop_economics/`):
    - esquema de programas y reglas caducadas (A1, A1b, A10);
    - `DayPath` (A2);
    - motor escalar de evaluación, financiada y payouts (A3, A4);
    - tarifas (A5);
    - bootstrap y evaluación vectorizada (A6a);
    - proyecto completo vectorizado, igual camino a camino al escalar (A6b);
    - escenarios y μ\* (A7);
    - informe y CLI `lab propecon` (A8);
    - propiedades (A9);
    - libro real inmutable (H1).
  - **ORPAE** (O1-O6): μ_LCB, Kelly y Optimal f como diagnóstico, políticas de tamaño, selección con la
    cota inferior, cartera correlada/independiente y `lab propecon allocate`.
  - **Ejecución** (`src/tradinglab/futures/execution/`): `OrderIntent`, `RiskCheck` R01-R16,
    `PaperAdapter` y ticket semimanual (J1, J2).
  - **Scripts de datos** para el equipo del operador: FUT-B1 (coste en Databento) y FUT-B3 (manifiesto),
    ya ejecutados el 2026-11-28.
  - **Entregas de OpenCode del 2026-11-28, revisadas e integradas:** Research A en código (C2 detectores,
    C3 evaluador), descarga gobernada de Databento (B2) y servidor MCP de solo lectura (T2). Claude
    corrigió C3, B2 y el manifiesto.
  - **Programas en `config/prop_economics/programs/`:** Topstep 50K, MFF Rapid 50K y Lucid Flex 50K, más
    dos sintéticos.
- **Ninguna estrategia está validada** (`NO EDGE VALIDATED`). Las simulaciones con pools sintéticos se
  etiquetan HIPOTÉTICO.
- **Bloqueado:**
  - **OP-4:** compra de datos. Lectura del coste: `evidencia/OP4_lectura_costes_2026-11.md` (Research B
    entero ≈ 41,89 USD; Research A ≤ 4.133,45 USD con el OOS-2);
  - **OP-7:** comisiones de MES y MGC;
  - con navegador: ProjectX, CME y el precio de Lucid.
- **Siguiente:** `CONTINUACION.md`.

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
| E | `evidencia/OP4_lectura_costes_2026-11.md` | Coste de datos de FUT-B1 leído para OP-4: paquetes por familia, `trades` duplicado en `tbbo` | hecho (2026-11-28) |
| K | `risk/04_PERFILES_MOTOR.md` | Seis perfiles A-F a 6/12/24 meses con el motor real en Topstep, MFF Rapid y Lucid Flex (hipotético) | hecho (2026-11-28) |
| K | `risk/03_COMPARACION_PROGRAMAS.md` | Topstep frente a MFF Rapid frente a Lucid Flex con la misma estrategia hipotética; precio de equilibrio de Lucid | hecho (2026-11-28) |
| R | `research/execution_spec.md` | Contrato `OrderIntent` → `RiskCheck` (R01-R16) → adaptador o ticket semimanual, con vectores V1-V16 | especificación (FUT-J0) |
| C | `../../config/prop_economics/programs/` | Programas YAML (Topstep, MFF Rapid, Lucid Flex y sintéticos) | vigentes |
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

2026-11-28, tras implementar el motor EV, ORPAE, PFIE y ejecución:
- **Suite completa del repositorio:** `pytest -q -m "not network and not mt5 and not lmstudio and not
  alpaca and not credentials"` (Linux, Python 3.13) → **2336 passed, 22 skipped, 2 deselected,
  0 failed** en 34:30. Esa ejecución empezó antes de los últimos tests de futuros.
- **Tests de futuros juntos,** incluidos los posteriores: `tests/test_prop_economics_*.py`,
  `tests/test_futures_*.py`, hooks y catálogo → **293 passed** (sin los 8 `slow` de precisión T1-T7,
  que pasan aparte en ~3 min).
- **Test del endpoint web** (`tests/test_web_futures_economics.py`, marcado `network` por usar
  loopback): pasa.
- **`ruff`:** limpio en todo lo tocado.
- **`lab doctor` en el contenedor:** FAIL en «Reloj» (no hay NTP ni MT5) y en «Frescura» (no hay datos
  locales), los dos del entorno. Hay que repetirlo en el equipo del operador.

