# TL3 · Auditoría de `ai_trader` (protegido, solo lectura)

Fuente: `data/lab.db` (copia, `mode=ro`), `src/tradinglab/ai_trader.py`, `docs/ai_trader_opencode.md`,
`reports/ai_trader/vs-gemela.md`. Reproducible con `TL3_REPORTS/evidencia/tl3_evidencia.py`. Leyenda en
`TL3_FORENSIC_AUDIT.md`.

## 1. Qué es realmente

- [HECHO] Un agente OpenCode (`.opencode/agents/ai-operator.md`, modelo
  `opencode-go/deepseek-v4.1-flash`) que llama a `lab ai-trader snapshot/plan/propose/skip/execute/manage`.
  Las **entradas** vienen de setups con reglas (`orb_5m`, `vwap_bounce`, `ema_ribbon_pullback`,
  `trend_pullback`, `donchian_turtle`…). La IA decide **si tomar**, **el lado** y gestiona la
  posición.
- [HECHO] `ai_trades`: 48 propuestas (44 cerradas), del 2026-11-13 al 2026-11-25. Estilos: scalping 41,
  swing 4 e intradía 3. Un solo `playbook_version` (1). Confianza 3 en 46 de 48.
- [HECHO] `ai_decisions`: 8.592 filas, de las que 7.346 son `skip` y 1.013 `no_setup` en forward, y 43
  `take`.

## 2. La comparación con la gemela no mide lo que dice medir

[REPRODUCIDO] n = 44 con R de la IA y de la gemela:

| Grupo | n | R IA | R gemela | Diferencia |
|---|---:|---:|---:|---:|
| Todas | 44 | +0,107 | −0,181 | +0,288 |
| Gemela del **mismo lado** que la IA | 22 | **+0,007** | **−0,271** | **+0,278** |
| Gemela del lado contrario | 22 | +0,206 | −0,090 | +0,296 |

**En los 22 casos de mismo lado, la entrada, el SL y el TP son idénticos** (ids 4, 5, 6, 8, 9, 12, 14,
18…; comprobado fila a fila). La decisión de la IA es la misma, así que la diferencia debería ser
≈ 0. Es +0,28 R. **Toda la "ventaja" medida puede venir del método de medición.**

Causas en `ai_trader.py:2840-2915` [HECHO]:
1. `_shadow_window` incluye **la vela que contiene la entrada** (`floor` del inicio). El SL de la gemela
   puede activarse con precios anteriores a la entrada.
2. En cada vela se comprueba **el SL antes que el TP**: resolución pesimista. La IA, en cambio, se
   resuelve con ticks reales.
3. La gemela no tiene el cierre forzoso de las 12:00 NY ni la gestión de la IA. Se evalúa hasta la vela
   de salida de la IA y se marca `open` con el último cierre (44/44 `shadow_status='open'`).
4. El R de la IA sale del PnL real (con spread). El de la gemela, de precios de vela **sin coste**.

Ejemplos: id 9 (US100, corto, mismos niveles): IA +1,63 R, gemela −1,00 R. Id 14: IA +1,66, gemela −1,00.

## 3. Lo que sí se puede decir

| Pregunta | Respuesta | Etiqueta |
|---|---|---|
| ¿Diferencia frente a la gemela? | No medible con este diseño (§2) | [REPRODUCIDO] |
| Expectativa | +0,107 R por operación, n = 44, 12 días | [REPRODUCIDO] |
| ¿De dónde sale? | **Del lado corto durante una caída del 10 %.** US100 pasó de 28.267 (11-12) a 25.262 (11-20). 33 de 44 operaciones fueron cortas: cortos +0,257 R, largos −0,346 R | [REPRODUCIDO] |
| Drawdown, estabilidad | Sin datos con n = 44 en un solo régimen | [INFERENCIA] |
| Costes | `cost_ratio` 0,005–0,13 del riesgo; coste LLM **Sin datos** | [HECHO] |
| Generalización | Un régimen (caída), dos símbolos (US100 24, XAUUSD 17) | [HECHO] |
| Dependencia de modelo y prompt | Un modelo y un playbook. Sin variación, no se puede medir | [HECHO] |
| Reproducibilidad | Las decisiones dependen del LLM en tiempo real; no hay semilla ni registro del prompt completo por decisión en `ai_trades` | [HECHO] columnas |
| Variabilidad entre ejecuciones | Sin datos: nunca se repitió una misma decisión | [HECHO] |
| Coste del carril | `vs-gemela.md` atribuye 115 llamadas LLM al carril. **Son del carril de acciones** (`agent-lite:SPY/QQQ/NVDA`, `news-score`, 2026-11-06 → 19). El coste de `ai_trader` no está registrado | [HECHO] |

## 4. Veredicto

**[INFERENCIA, fuerte]** No hay evidencia de que la IA aporte información útil. Lo que hay es
compatible con una IA que **sigue la tendencia reciente del día** (vende en una caída) más un sesgo de
medición a su favor. Eso se consigue con una regla de una línea, por ejemplo "operar solo en la
dirección del cierre de ayer frente a su apertura".

El análisis lingüístico de la IA (tesis, planes, bias) no es evidencia de ventaja. 7.346 `skip`
con razonamiento no equivalen a 7.346 decisiones evaluadas: no se mide el resultado de lo que se
saltó.

## 5. Qué haría falta para saber si aporta (sin tocar `ai_trader` hoy)

| # | Cambio (en un entorno TL3 aparte, nunca en el carril protegido sin el control de cambios T00) | Por qué |
|---|---|---|
| A1 | Gemela evaluada con **la misma** resolución que la IA: desde la vela siguiente a la entrada, con ticks o M1, TP/SL en orden temporal y los mismos costes | Elimina el sesgo del §2 |
| A2 | Tres contrafactuales en paralelo: lado aleatorio, **regla de tendencia simple** (signo del día anterior) y **siempre tomar** el setup | Separa "la IA elige el lado" de "la IA sigue la tendencia" y de "el setup funciona solo" |
| A3 | Registrar el R de los `skip` con la gemela "tomar siempre" | Mide si el filtro de la IA quita malas operaciones |
| A4 | Prompt, modelo y hash del snapshot en cada decisión; reproducir 20 decisiones dos veces | Variabilidad y dependencia del modelo |
| A5 | Criterio prerregistrado: Δ frente a la **regla de tendencia** ≥ 0,1 R con IC95 > 0, n ≥ 200, en ≥ 2 regímenes | Con 3–4 operaciones/día, ~3 meses |

**[REC]** Mientras no exista A1–A2, congelar las conclusiones sobre `ai_trader`: ni "aporta" ni "no
aporta". No dedicar trabajo de desarrollo al carril IA hasta tener ese contrafactual.
