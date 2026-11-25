# TL3 · Por qué Discovery no encuentra ventajas

**Fuente principal:** `data/discovery.db` (copia, solo lectura) y `data/lab.db`. Cifras reproducibles
con `TL3_REPORTS/evidencia/tl3_evidencia.py`. Leyenda: ver `TL3_FORENSIC_AUDIT.md`.

## 1. Inventario real de lo explorado

### 1.1 Tres épocas de investigación

| Época | Fechas | Qué se hizo | Resultado | Fuente |
|---|---|---|---|---|
| Barridos de indicadores | 2026-11-09 → 11 | ~450 combinaciones (LONDON_PULLBACK, SESSION_TREND, TREND_INTRADAY, ORB_NY, TOKYO_BREAKOUT, FIX_FLOW, PULLBACK, SESSION_HOLD…) sobre EURUSD, GBPUSD, USDJPY, US100, XAUUSD | **Todas `failed`** ("DSR 0 % < 90 %; WF fallido; régimen no aprobado") | [HECHO] `lab.db.strategy_trials` (`source='sweep'`) |
| Campañas multiactivo A/B | 2026-11-12 | 4 familias (TSMOM, ST_REVERSAL, VOL_BREAKOUT, CALENDAR) × 16 activos; 460 celdas | A "passed" en descubrimiento; **B contaminada** y 0/23 confirmadas | [HECHO] `campaign_registry` |
| Discovery | 2026-11-20 → 25 | 18 campañas, 10 plantillas, 9 hipótesis distintas | 0 nivel 4, 1 nivel 3 (sobreajustada) | [HECHO] `discovery.db` |

### 1.2 Discovery: embudo por campaña

`n` = filas en `disc_strategies`. "Bruto" es `raw_expectancy_r` y "neto" es `is.expectancy_r`, ambos en
IS (medianas). MDE = 2,49/√(ops IS) con σ = 1 R. [REPRODUCIDO]

| Campaña | Hipótesis | n | Bruto med. | Bruto > 0 | Coste med. | Neto med. | Neto > 0 | Ops IS med. | MDE | OOS-1 evaluadas | Nivel máx. |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `disc-…211100-092a76d2` | NY open + filtro vol (GA) | 260 | Sin datos | — | 0,049 | −0,0025 | 116 | 752 | 0,091 | 30 | 3 |
| `disc-…171711-303e5662` | Momentum al cierre | 144 | Sin datos | — | 0,095 | −0,127 | 0 | 395 | 0,125 | 0 | **inválida** |
| `disc-…180458-0e579341` | Momentum al cierre v2 | 32 | Sin datos | — | 0,064 | −0,078 | 0 | 531 | 0,108 | 0 | 1 |
| `c1-asia-usdjpy-h1-long` | Reversión rango Asia | 27 | −0,053 | 0 | 0,053 | −0,117 | 0 | 1.321 | 0,069 | 0 | 1 |
| `n2-donchian-xauusd-h4` | Ruptura Donchian + vol | 27 | +0,042 | 23 | 0,031 | +0,014 | 16 | 391 | 0,126 | 9 | 2 |
| `n2-donchian-usdjpy-h4` | Ruptura Donchian + vol | 27 | +0,019 | 17 | 0,019 | −0,003 | 11 | 330 | 0,137 | 0 | 1 |
| `q2-fix-usdjpy-h1` | Reversión en el fix | 6 | −0,002 | 2 | 0,045 | −0,048 | 0 | 3.771 | 0,041 | 0 | 1 |
| `q2-fix-eurusd-h1` | Reversión en el fix | 6 | +0,023 | 6 | 0,036 | −0,013 | 0 | 3.764 | 0,041 | 0 | 1 |
| `q2-fix-gbpusd-h1` | Reversión en el fix | 6 | +0,013 | 6 | 0,033 | −0,023 | 0 | 3.763 | 0,041 | 0 | 1 |
| `v2-fix-londres-eurgbp-h1` | Fix, cesta, **costes v2** | 9 | +0,019 | 9 | 0,032 | −0,017 | 0 | 7.527 | 0,029 | 0 | 1 |
| `r9-tom-us500-d1` | Cambio de mes | 9 | +0,066 | 8 | 0,047 | +0,016 | 5 | 56 | 0,333 | 1 | 1 |
| `r9-tom-us100-d1` | Cambio de mes | 9 | +0,032 | 7 | 0,009 | +0,021 | 7 | 91 | 0,261 | 0 | 1 |
| `r9b-tom-us500-d1` | Cambio de mes (anclaje) | 9 | +0,082 | 9 | 0,047 | +0,039 | 6 | 67 | 0,304 | 4 | 1 |
| `r9b-tom-us100-d1` | Cambio de mes (anclaje) | 9 | +0,060 | 9 | 0,009 | +0,049 | 8 | 109 | 0,238 | 0 | 1 |
| `q1-rebote-us500-d1` | Rebote tras ventas | 27 | −0,054 | 8 | 0,052 | −0,126 | 3 | 16 | 0,623 | 0 | 1 |
| `q1-rebote-us100-d1` | Rebote tras ventas | 27 | +0,150 | 27 | 0,010 | +0,136 | 25 | 27 | 0,479 | 3 (0 ops) | 1 |

### 1.3 Respuesta a las diez preguntas del embudo

| # | Pregunta | Respuesta | Etiqueta |
|---|---|---|---|
| 1 | Familias exploradas | 9 hipótesis en Discovery (tabla 1.2) + ~20 familias de indicadores en barridos + 4 familias en campañas A/B | [HECHO] |
| 2 | Hipótesis probadas | Las 9 de la tabla; solo 4 traen hipótesis económica escrita en la spec (fix, cambio de mes, rebote, TSMOM pendiente) | [HECHO] `.orquestador/specs/` |
| 3 | Variantes generadas | Discovery 634 filas (144 de una campaña inválida); barridos ~450; A/B 460 | [HECHO] |
| 4 | Descartadas | Discovery 632 de 634 `discarded`/`evaluated`; las 2 restantes, `finalist` sin confirmar | [HECHO] |
| 5 | Por qué | IS negativo, pliegues, deriva < p90 y OOS-1 (v1). Ninguna por holdout: nunca se abrió | [HECHO] `disc_validations`, `reject_reason` |
| 6 | Bruto > 0 | 131 de 198 celdas de rejilla con bruto medido (el GA y el momentum no guardan bruto: Sin datos) | [REPRODUCIDO] |
| 7 | Sobreviven al coste | Neto > 0 en IS: 81 de 198 celdas de rejilla y 116 de 260 en el GA; **0 de 27** en el fix (la única familia con potencia) | [REPRODUCIDO] |
| 8 | Sobreviven al walk-forward | Solo se aplicó WF a 2 finalistas del GA: **0 de 2** | [HECHO] `disc_validations` (`wf` passed=0 ×2) |
| 9 | Sobreviven fuera de muestra (OOS-2) | **0 evaluadas**. Nunca se abrió el holdout | [HECHO] `disc_holdout_reads` = 0 |
| 10 | Llegan a forward | **0** desde Discovery. El único forward es el EA del operador (no sale de Discovery) | [HECHO] |

### 1.4 Duplicados y familias agotadas

- **[HECHO]** Cambio de mes: 4 campañas (`r9-*`, `r9b-*`) más 18 "miradas informales" Databento ES/NQ
  (`informal_trials` id 1). Es **una** hipótesis probada 6 veces con variaciones de anclaje y mercado.
- **[HECHO]** Fix: 4 campañas (3 × `q2-*` + `v2-fix-londres`) más 48 barridos `FIX_FLOW` del 2026-11-11.
  Es la familia más repetida y la única con veredicto firme: **cerrada**.
- **[HECHO]** Apertura de NY en US100: `ORB_NY` (barridos), `TREND_INTRADAY`, `ny_open_vol_filter` (GA),
  `intraday_momentum_close` v1/v2, `session_breakout_htf` y el propio EA. Es la familia con más
  intentos y la que comparte holdout con el EA (ver `TL3_STATISTICAL_VALIDATION_AUDIT.md §C`).
- **[INFERENCIA]** Las "9 hipótesis" son en realidad **unas 6 ideas**: apertura NY, fix FX, cambio de
  mes, rebote, ruptura de canal y reversión de rango asiático.

## 2. Preguntas obligatorias

**¿Exploramos demasiadas combinaciones de indicadores?** Sí en la época de barridos (~450 celdas sin
hipótesis, todas fallidas). En Discovery no: las rejillas son de 6–32 celdas. **El problema actual no
es el exceso de combinaciones.** [HECHO]

**¿Generamos estrategias sin hipótesis económica?** En barridos y en el GA, sí (`ny_open_vol_filter`
mezcla OR, régimen de volatilidad, ATR stop y RR libres; complejidad 18–20). Las rejillas q1/q2/q3/r9
traen hipótesis escrita. [HECHO]

**¿Los filtros eliminan demasiadas candidatas?** No eliminan candidatas buenas que se puedan
demostrar: no hay ninguna con potencia y neto > 0 que haya caído por un filtro dudoso. El caso más
"injusto" es `r9b-tom-us500` (OOS-1 −0,20 a −0,29 R con 9 operaciones), pero el error estándar con
n = 9 es ≈ 0,33 R: ese OOS-1 no dice nada en ningún sentido. [REPRODUCIDO + INFERENCIA]

**¿El motor optimiza ruido?** En el GA, sí: 116 de 260 con neto IS > 0 y mediana −0,0025 R es lo que
produce ruido puro alrededor de cero. Los dos finalistas caen en WF, PBO, régimen y bootstrap. El
sistema lo detectó. [HECHO]

**¿El espacio de búsqueda es demasiado limitado?** El espacio no es el cuello de botella. Lo es la
**elección de hipótesis por plantilla disponible** en lugar de por tamaño de efecto y número de
operaciones esperables. [INFERENCIA]

**¿Mercados y temporalidades incorrectos?** Parcialmente:
- D1 por instrumento (cambio de mes, rebote): 7–27 operaciones/año. Con MDE ≥ 0,24 R, el diseño
  no puede detectar el efecto publicado (≈ 0,05–0,10 R). **Mala elección de temporalidad para la
  pregunta.** [REPRODUCIDO]
- M5 en US100 con stops cortos: coste de 0,05–0,095 R por operación (tabla 1.2). Un efecto bruto de
  0,05 R desaparece. [REPRODUCIDO]
- FX H1 en el fix: con potencia, pero el bruto es demasiado pequeño. [REPRODUCIDO]

**¿Hay operaciones suficientes?** Solo en 5 de 16 campañas (fix ×4 y Asia). [REPRODUCIDO]

**¿Métricas de selección adecuadas?** La fitness del GA (expectativa, PF, DD, complejidad, Δ coste)
selecciona por expectativa en IS sin penalizar la varianza muestral. Con 750 operaciones y σ ≈ 1 R,
el error estándar es ≈ 0,036 R, así que ordenar 260 candidatos por expectativa IS es ordenar ruido.
[INFERENCIA]

**¿Discrepancia generador ↔ backtester?** Sí, una documentada: la campaña `…171711-303e5662` se anuló
por "espejo del umbral sin signo" (el DSL generaba la regla corta mal). Otra probable: `optimizer.py`,
`perturb.py` y partes de `edge_map.py` usan el coste v1 por defecto (`RESULTADO-T10.md`). [HECHO]

## 3. Causa raíz

**[INFERENCIA, fuerte]** Discovery falla porque responde a "¿qué plantilla tengo?" en lugar de a
"¿qué efecto de tamaño X, con N operaciones, puedo detectar con este coste?". El resultado son
campañas que, antes de correr, ya tenían una de estas dos salidas:

1. **Sin potencia** (MDE > efecto plausible): cambio de mes, rebote, Donchian y momentum v2. No dicen
   nada en ningún sentido y gastan pruebas del contador.
2. **Con potencia pero con un bruto menor que el coste conocido** (el fix): veredicto firme y útil,
   pero se podía anticipar con un cálculo de coste/bruto de la literatura antes de registrar.

La puerta de potencia ya existe (`power.py`), pero ninguna spec declara δ (`TL3_FORENSIC_AUDIT.md` G-6).

## 4. Lo único que muestra señal

| Candidato | Evidencia a favor | Lo que falta |
|---|---|---|
| EA `us100-ftmo1` (no viene de Discovery) | 478 ops, +0,31 R, LCB95 0,17 R **en muestra de diseño** | Una sola prueba fuera de muestra válida. US500/US30 no transfieren. Ver `TL3_US100_CASE_STUDY.md` |
| Donchian XAUUSD H4 (`n2-donchian-xauusd-h4`) | 23/27 bruto > 0, OOS-1 +0,39 R (mejor celda) | OOS-1 con 16–19 operaciones (SE ≈ 0,3 R). Es la mejor celda de 27 tras ver OOS-1. Nivel "SIN VEREDICTO". Es la tendencia del oro de 2024-25, no una prueba |
| Rebote US100 D1 | 27/27 bruto > 0, +0,15 R | 27 operaciones en 10 años. Imposible de validar por sí sola |

**Ninguno permite afirmar hoy que exista una ventaja.** [INFERENCIA]

## 5. Qué no hacer

- No relanzar cambio de mes ni rebote en un solo instrumento D1: con 10 años no alcanzan potencia.
  Solo tienen sentido como **cesta** (muchos instrumentos, una hipótesis), como prevé `q3`/`v2-*`, y
  **con δ declarado** y MDE ≤ δ antes de aprobar.
- No ampliar el GA. Ya demostró que fabrica finalistas sobreajustados.
- No reabrir el fix: con 7.527 operaciones y costes v2, el bruto (+0,019 R) es menor que el coste
  (0,032 R). Es el único veredicto sólido del proyecto.
