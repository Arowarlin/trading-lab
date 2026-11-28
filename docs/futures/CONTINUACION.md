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
8. ✅ (2026-11-28, `risk/03_COMPARACION_PROGRAMAS.md`) **Comparación de programas con el simulador de riesgo:** Topstep 50K frente a MFF Rapid 50K frente a
   Lucid Flex 50K.
   - Ventajas **hipotéticas**, las mismas políticas y 6/12/24 meses.
   - Los precios de Lucid son Sin datos: se informa del EV por **precio de equilibrio** (la tarifa
     máxima que deja EV ≥ 0).
   - Código en `docs/futures/risk/sim/`, sin tocar producción.
9. **FUT-E4** (límites de tasa de Tradovate), solo si sobra tiempo.

**2026-11-28, operador:** «aprueba op8 sigue con lo que no esta bloqueado». OP-8 queda aprobada
(muestra 2010-06-07 → 2023-12-31; OOS-2 de futuros 2024-01-01 → 2026-11-20 sellado; forward desde el
2026-11-28). Siguen bloqueadas por OP-4/OP-7: FUT-D2, FUT-C1 y todo lo que mira datos.

Trabajo no bloqueado, en este orden:
10. ⛔ (2026-11-28: `www.cmegroup.com` corta las conexiones automáticas en HTTP/2 y 1.1; no se fuerza ni se imita un navegador → **operador con navegador**) **FUT-E3:** especificaciones y horarios de CME (horas de GC, MES y MGC), revisando antes sus
    términos.
11. ✅ (2026-11-28, `05 §4.8-4.9`; A6 dividida en A6a/A6b) **Prompts pegables** de OpenCode (DeepSeek V4.1 Flash) para FUT-A4 (financiada y payouts, T9) y
    FUT-A6 (Monte Carlo), para que la cola no se pare cuando cierren A3 y A5.
12. ✅ (2026-11-28, `research/dashboard_model.md`) **FUT-H0 · Modelo de dominio del dashboard:** realizado frente a simulado; payout solicitado,
    aprobado, procesado y recibido.
13. ✅ (2026-11-28, `research/platform_matrix.md`) FUT-E4 (límites de Tradovate).

**Estado al cierre (2026-11-28):** todo lo de Claude que no depende de datos está hecho. Bloqueado:
- OP-4 (compra de datos) y OP-7 (comisiones de MES y MGC): FUT-D2, FUT-C1, FUT-B2 y todo lo que mira
  datos;
- **operador con navegador**: FUT-E2 (ProjectX), FUT-E3 (CME), precio de Lucid, Apex, Earn2Trade y TPT;
- **OpenCode** (DeepSeek V4.1 Flash): FUT-A1, A2, B1 y B3 READY; después A3, A4, A5 y A6a, cuyos prompts
  están listos.

Cuando lleguen las entregas de OpenCode, Claude las revisa con el agente `tradinglab-reviewer`
(ficheros permitidos, cifras exactas, `ruff` y `pytest`).

Sigue prohibido: live, campañas, `.env`, borrar, descargar automáticamente de webs que lo prohíben
(ahora también ProjectX) y mezclar datos que no sean de futuros.

## Sesión 3b · implementación (2026-11-28, «apruebo todo puedes seguir y también lo que opencode debe hacer»)

Hecho por Claude, con commit y push por tarea:
- **Motor EV:** FUT-A1-A10 y A1b.
- **Libro real:** FUT-H1.
- **ORPAE:** FUT-O1-O6.
- **Ejecución:** FUT-J1-J2.
- **Scripts de datos:** FUT-B1 y B3, que ejecuta el operador.

Para cada uno, la cola (`05`) dice qué y dónde.

Siguiente, sin bloqueo:
1. FUT-J3 (envoltorio dry-run de ProjectX);
2. FUT-P (Prop Firm Intelligence Engine: registro, frescura, compatibilidad, ranking ponderado);
3. FUT-H2/H3 (API y vista del dashboard, con el lock `web-py`);
4. FUT-M1-M3 (políticas de ratio negativo y positivo sobre el motor);
5. FUT-C1 (rasgos de order flow con tests sintéticos; el esquema real se confirma con FUT-B2).

Bloqueado: OP-4 (compra de datos), OP-7 (comisiones de MES y MGC) y lo que se lee con navegador.
