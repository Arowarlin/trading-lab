# Plan de continuación (trabajo autónomo de Claude)

**Escrito:** 2026-11-27 20:10 (Santo Domingo). **Autorización del operador:** "tienes permiso para
absolutamente todo", "sigue trabajando, no pares", "que te programe para seguir cuando el límite se
resetee". Siguen vigentes sin excepción:
- **Nunca live ni dinero real.** No activar bots ni F13. No comprar evaluaciones ni crear cuentas.
- **No lanzar campañas** ni barridos que sumen al DSR.
- **No tocar `.env`.** No borrar archivos. Commits por ruta.
- **No descargar automáticamente webs cuyos términos lo prohíben:** Topstep, Bulenox, TradeDay, Alpha
  Futures y Tradeify. Tampoco forzar las que dan 403.
- **Rol:** Claude investiga, especifica y revisa. OpenCode implementa el código de producción con
  DeepSeek V4.1 Flash.

**Decisiones del operador (2026-11-28):** "todo lo que no sea futuros, en segundo plano" y "no ligues la
data: solo futuros". No se empieza trabajo nuevo fuera de futuros (CFD, FX/C1, EA, `ai_trader`) y la
investigación de futuros usa **solo datos de futuros CME**: nada de CFD, Dukascopy ni MT5 como datos o
proxy.

## Estado al cierre de la sesión 1

| Hecho | Dónde |
|---|---|
| Auditoría, matriz tecnológica, extensiones, arquitectura, spec del motor EV, cola | `docs/futures/00-05` |
| Hooks de AGENTS.md, plugins `context7` y `pyright-lsp`, 9 skills, 7 agentes | `.claude/` |
| Dependencias (hypothesis, pytest-cov, scipy; sin alpaca-py) | `pyproject.toml`, `uv.lock` (suite 2224 passed) |
| 10 fichas de firmas, informe con ranking y catálogo por bots y modo de ejecución | `docs/futures/research/propfirms_2026-11/`, `config/prop_economics/firms_futures.yaml` |
| Investigación de riesgo (Kelly, ruina, 6 perfiles, 6/12/24 m), ORPAE y módulos MOD-NR/MOD-PR | `docs/futures/risk/` |

## Siguiente, en este orden (un commit + push por paso)

1. ✅ (2026-11-28, `c56b698`) **Cola de OpenCode al día** (`docs/futures/05_COLA_Y_ROADMAP.md`):
   - añadir FUT-O1..O6 (`risk/02_ORPAE_DISENO.md`), FUT-P1..P6 (PFIE) y FUT-M1..M3 (módulos), con estado
     y dependencias;
   - prompts pegables para **FUT-A3** (motor de una cuenta en evaluación) y **FUT-A5** (tarifas y
     bankroll), formato §4 y vectores T8, T10, T11, T12 y T13 de `04_SPEC_PROP_EV.md`.
2. ✅ (2026-11-28) **FUT-D0 · Especificación de Research B (NY open)**, en `docs/futures/research/RB_spec.md`:
   - hipótesis ORB, opening drive, VWAP reclaim/rejection, ON/PD high-low, failed breakout,
     IB/volatilidad, continuación y reversión;
   - etiqueta de contaminación por hipótesis e instrumento (FUT-11: NQ 2010-2026 contaminado para la
     lógica del EA; ES/GC más limpios);
   - definición matemática, entradas, salidas, costes, datos mínimos, potencia frente a μ\* y criterio de
     rechazo escrito antes;
   - usar la skill `hypothesis-preregistration`. **No registrar ni ejecutar nada.**
3. ✅ (2026-11-28) **FUT-C0 · Especificación de Research A (order flow)**, en `docs/futures/research/RA_spec.md`:
   - hipótesis A-J (absorción, barrido de liquidez, divergencia de delta, desequilibrios, ruptura y
     subasta fallidas, agotamiento, confirmación, expansión de volumen, recuperación de liquidez);
   - para cada una, el nivel de datos mínimo (L1 `trades`/`tbbo`, L2 `mbp-10`, L3 `mbo`), las
     definiciones con fórmulas y los costes con stops cortos (≈ 0,25 R con 5 puntos en MNQ).
4. ✅ (2026-11-28) **FUT-E1 · Matriz de plataformas** (NinjaTrader 8, Tradovate, ProjectX) con documentación oficial de
   las plataformas, no de las firmas. Antes de descargar nada, comprobar sus términos sobre el acceso
   automatizado. Si hace falta un host nuevo, proponerlo con `update_environment`.
5. ✅ (2026-11-28, borradores en `research/programs/`; FUT-A10 los lleva a `config/`) **Ficha → YAML de programa** para My Funded Futures Rapid y Lucid Flex (esquema de `04 §8`), con el
   estado de cada valor. Los precios de Lucid quedan como `sin_datos`.
6. ✅ (2026-11-28) **Actualizar `docs/futures/README.md`** (índice) y **`ESTADO.md`**, si procede, con el lock
   `readme-plan`.

Al terminar cada paso: `ruff check` de lo tocado, tests rápidos si hay código, commit por ruta, push a
`claude/vibrant-mayer-r46s0o`. Si el límite de uso vuelve a cortar, dejar este fichero actualizado con lo
que falte.

## Sesión 3 (escrito el 2026-11-28 tras cerrar los pasos 1-6)

7. ✅ (2026-11-28, `research/execution_spec.md`) **FUT-J0 · Contrato de ejecución y riesgo** en `docs/futures/research/execution_spec.md`:
   - `OrderIntent` con `origin ∈ {automated, semi_manual}`;
   - `RiskCheck` con las reglas de cada programa: contratos máximos, escalones de escalado, `flat_by`,
     ventanas de noticias, prohibición de overnight;
   - adaptadores NT8 (no gestionado), ProjectX (dry-run existente) y ticket semimanual;
   - vectores de prueba exactos para OpenCode.
   - Base: `research/platform_matrix.md §2`.
8. **Comparación de programas con el simulador de riesgo:** Topstep 50K frente a MFF Rapid 50K frente a
   Lucid Flex 50K.
   - Ventajas **hipotéticas**, las mismas políticas y 6/12/24 meses.
   - Los precios de Lucid son Sin datos: se informa del EV por **precio de equilibrio** (la tarifa
     máxima que deja EV ≥ 0).
   - Código en `docs/futures/risk/sim/`, sin tocar producción.
9. **FUT-E4** (límites de tasa de Tradovate), solo si sobra tiempo.

Sigue prohibido: live, campañas, `.env`, borrar, descargar automáticamente de webs que lo prohíben
(ahora también ProjectX) y mezclar datos que no sean de futuros.
