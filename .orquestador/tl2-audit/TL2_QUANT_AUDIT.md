# TL2 · Auditoría cuantitativa: costes, estadística y protocolo v2

Complementa `TL2_MASTER_AUDIT.md`. Aquí están las fórmulas, las demostraciones y el diseño del protocolo que sustituye al actual **solo para campañas nuevas**.

---

## 1. Modelo de ejecución y costes

### 1.1 Cómo funciona hoy (verificado en el código)

Las barras son BID. Para cada barra se construye un `CostPanel` (`fastbt.py:222-235`, `:317-333`, `:381-404`):

- `entry_bps = comisión + slippage + spread`
- `stop_bps = entry_bps` (se usa en salidas por stop, tiempo, señal, fin de sesión y fin de datos)
- `target_bps = comisión`

El coste en R de una operación es `(entry_bps + exit_bps) / 10⁴ · P_entrada / riesgo` (`fastbt.py:772`, `:899`, `:960`; `costs.py:407`).

### 1.2 Modelo de referencia BID/ASK

Sea `b_t` el precio BID, `s_t` el spread y `a_t = b_t + s_t` el ASK. Coste de una operación, con `σ` el slippage por lado y `c` la comisión por lado:

| Operación | Precio de entrada | Precio de salida | Spread pagado |
|---|---|---|---|
| Largo | `a_e = b_e + s_e` | `b_x` | `s_e` (uno) |
| Corto | `b_e` | `a_x = b_x + s_x` | `s_x` (uno) |

```
coste_R = [ s_pagado + σ_e + σ_x + c_e + c_x ] / riesgo
```

Con un objetivo límite, el slippage de salida es 0. Con un stop o una salida a mercado, `σ_x > 0`. **Nunca se paga más de un spread por operación.**

### 1.3 Discrepancias demostradas

| # | Caso | Código | Referencia | Sesgo |
|---|---|---|---|---|
| D1 | Largo o corto con salida por stop, tiempo, señal o fin | 2 spreads | 1 spread | **Pesimista**, +1 spread por operación |
| D2 | Stop de un corto | Se dispara si el máximo BID ≥ stop | Se dispara si el máximo ASK = `máximo BID + s` ≥ stop | Optimista: dispara tarde |
| D3 | Salida por objetivo | 1 spread (entrada) + comisión | Igual | Correcto |
| D4 | Objetivo de un corto | Se comprueba con `low + spread` (`fastbt.py:849`) | Igual | Correcto |

Evidencia: `evidencia/prueba_spread_fastbt.py` y su salida `.salida.txt`.

### 1.4 Otras fuentes de sesgo en costes

- **Spread p75 como coste esperado.** La expectativa debe usar la media del spread a la hora de la operación. El p75 es una prueba de estrés: se mantiene como escenario (`retest cost_x1_5` ya existe) y no como base.
- **Slippage supuesto.** EURUSD y GBPUSD cargan 0,5 pip por lado y USDJPY 0,5 pip (`costs.yaml`). Se debe estimar desde fills reales con:
  `σ̂ = mediana(|precio_fill − precio_solicitado|)` por símbolo, cuenta, tipo de orden y hora, con al menos 30 fills por celda. Si no se llega, se usa el supuesto con la marca `assumption`.
- **Anacronismo.** El spread y el swap medidos en noviembre de 2026 se aplican a toda la historia. Para el spread, Dukascopy trae `ask_*` histórico. Se usa el perfil intradía histórico, escalado al nivel del bróker:
  `s_t^bróker = s_t^Dukascopy · (mediana_reciente_bróker / mediana_reciente_Dukascopy)`, por hora local.
  Para el swap de índices y FX:
  `swap_t = (tipo_referencia_t ± diferencial) · nocional / 360`, con el tipo histórico (fondos federales, €STR/EONIA, SONIA, BoJ; FRED ya está integrado en `intel/fred.py`) y el markup del bróker medido hoy. El crédito sigue contando 0 en Discovery.

### 1.5 Magnitud esperada (a confirmar en T10–T12)

Ejemplo EURUSD H1, fix de Londres, cuenta FTMO, con los valores de `costs.yaml`:
- **Hoy:** 2 × 0,2 pip de spread p75 + 2 × 0,5 pip de slippage supuesto + comisión.
- **Modelo v2:** 1 × spread medio + slippage medido + comisión.

**La reducción depende del slippage medido, que hoy es Sin datos.** No se afirma ninguna cifra: T40 la medirá al reevaluar.

---

## 2. Potencia estadística

### 2.1 El tamaño de efecto realista

Una ventaja publicada y todavía viva, tras costes, ronda los 0,02 a 0,15 R por operación con desviación de unos 1 R por operación. El EA del operador muestra +0,31 R, pero en backtest y sin corregir por sus variantes.

### 2.2 Efecto mínimo detectable (MDE)

Para un test unilateral con nivel `α` y potencia `1−β`, con `n` operaciones y desviación `σ_R`:

```
MDE = (z_{1−α} + z_{1−β}) · σ_R / √n
```

Con α = 0,05, potencia 0,80 y σ_R = 1, MDE ≈ 2,49 / √n.

| n operaciones | MDE (R) |
|---:|---:|
| 12 | 0,72 |
| 68 (US500 cambio de mes, IS) | 0,30 |
| 400 | 0,12 |
| 3.760 (fix EURUSD, IS) | 0,041 |

**Conclusión:** una campaña con menos de unas 600 operaciones en el tramo que decide no puede confirmar una ventaja menor de 0,10 R. Hay que saberlo **antes** de gastar pruebas.

### 2.3 Potencia de la cadena actual

`evidencia/potencia_validacion.py` simula solo las puertas OOS-1 (media > 0 y PF > 1,1) y OOS-2 (≥ 30 operaciones, media > 0 y z ≥ 1,645). Las demás puertas solo pueden bajar más la probabilidad.

| Ops/año | Sin ventaja | 0,05 R | 0,10 R | 0,20 R |
|---:|---:|---:|---:|---:|
| 12 | 0,000 | 0,00 | 0,00 | 0,00 |
| 50 | 0,024 | 0,07 | 0,15 | 0,45 |
| 250 | 0,013 | 0,15 | 0,50 | 0,98 |
| 1.000 | 0,004 | 0,37 | 0,96 | 1,00 |

La cadena controla muy bien el falso positivo, pero rechaza la mayoría de las ventajas reales por debajo de 250 operaciones al año. Además, OOS-1 de 12 meses, usado como filtro de signo, casi no discrimina:
- con 12 operaciones al año aprueba al 45 % de las estrategias **sin** ventaja;
- y solo al 58 % de las que **sí** tienen 0,10 R.

### 2.4 Qué se hace con las campañas ya ejecutadas

Nada se reescribe. Sus veredictos se mantienen con la regla con que se registraron. El informe de cada una añadirá la línea "potencia de la regla: X" calculada por T20, para que nadie interprete "descartada" como "sin ventaja demostrada".

---

## 3. Fitness y selección

### 3.1 Fitness actual (`fitness.py:274-280`)

Se maximiza el vector **[mediana de expectativa por pliegue, estabilidad, −DD peor, −complejidad, −caída por coste]** con NSGA-II y se seleccionan los de rango 0.

- **Lo que está bien:** es multiobjetivo, penaliza la complejidad y mide la sensibilidad al coste.
- **Lo que falla:** la mediana de 3 o 4 pliegues con pocas operaciones es muy ruidosa, y el frente de Pareto premia el extremo afortunado (*winner's curse*). La selección optimiza ruido.

### 3.2 Propuesta para campañas de hipótesis (no GA)

1. **Una especificación primaria prerregistrada.** Es la que se prueba. La rejilla solo verifica la **meseta**: la fracción de vecinos con expectativa neta > 0 debe ser ≥ 0,6. No se elige el mejor punto.
2. **Estadístico de decisión:** cota inferior de la expectativa neta.
   `LCB = x̄ − t_{0,95; n−1} · s / √n`, sobre operaciones o sobre bloques semanales si hay dependencia (bootstrap estacionario de Politis-Romano con bloque medio igual a la duración media de la operación).
3. **Para cuentas de fondeo, como objetivo secundario y no como filtro:**
   `P(pasar) = P(alcanzar el objetivo antes de romper la pérdida diaria o la máxima, en T días)`.
   Se estima por bootstrap de bloques de los R diarios con el riesgo por operación como variable (ya existe en `robustness._challenge`). Se informa el riesgo por operación que maximiza P(pasar) sujeto a P(romper) ≤ 5 %.

### 3.3 Cuando se use el GA

Solo en campañas declaradas como "exploración": el resultado no es una estrategia, sino una **hipótesis** que debe reformularse y probarse en una campaña nueva con datos que el GA no vio (otro instrumento u otro periodo). Esto convierte la exploración en generadora de hipótesis y evita usarla como validación.

---

## 4. Protocolo v2 para campañas nuevas

### 4.1 Etapas

| Etapa | Qué se hace | Regla de decisión | Lee rendimiento |
|---|---|---|---|
| 0 · Registro | Hipótesis literal, especificación primaria, rejilla de meseta, efecto plausible `δ` declarado, familia | — | No |
| 1 · Potencia (preflight) | Cuenta las operaciones esperadas en desarrollo y en holdout (solo conteos, permitido por el guard) y calcula el MDE | Si MDE_holdout > δ: la campaña queda **sin potencia** y no se ejecuta salvo que se amplíe la muestra (historia, instrumentos) | No |
| 2 · Desarrollo | Primaria + meseta + control de deriva + costes v2 | LCB_desarrollo > 0; meseta ≥ 0,6; percentil de deriva ≥ 90 | Sí, tras aprobar |
| 3 · Holdout único | OOS-1 y OOS-2 fusionados en un tramo sellado de una sola lectura, **solo la primaria** | Test unilateral `x̄_h > 0` con α = 0,05 **y** consistencia: `x̄_h` no menor que el LCB de desarrollo por más de 2 errores estándar | Sí, una vez |
| 4 · Forward demo | SPRT con H0: μ = 0 y H1: μ = δ | Acepta H1 si `Λ_n ≥ ln((1−β)/α)`; acepta H0 si `Λ_n ≤ ln(β/(1−α))` | Continuo |

La regla del SPRT con R normales y varianza `σ²` estimada en desarrollo:
`Λ_n = (δ/σ²) · Σ R_i − n·δ²/(2σ²)`.

### 4.2 Multiplicidad

- **Dentro de una campaña:** como solo se decide sobre la primaria, K = 1. La rejilla no suma pruebas de decisión, pero sí se registra.
- **Entre campañas de la misma familia** (por ejemplo, todos los efectos de calendario): Hansen SPA (*Superior Predictive Ability*) sobre las primarias, con bootstrap estacionario, o Romano-Wolf *stepdown*. Así se controla el error por familia.
- El contador global sigue existiendo como registro, no como corrección.

### 4.3 Garantía de no relajar el rigor

T01 mide, en el mismo arnés, la probabilidad de aprobar del protocolo actual y del v2:
- con datos sin ventaja (permutación de señales y reinicio aleatorio de entradas);
- con ventajas inyectadas de 0,05, 0,10 y 0,20 R.

**Criterio de aceptación del v2:**
- `P_v2(aprobar | nulo) ≤ max(0,05, P_actual(aprobar | nulo))`, y
- `P_v2(aprobar | 0,10 R)` mayor que la actual en todas las frecuencias con potencia declarada.

Si no se cumple, el v2 no entra.

---

## 5. Lo que ya está bien y no debe tocarse

- `guard.require_approved` y el registro de miradas informales.
- Los snapshots con hash de dataset y de configuración, y el sellado de OOS-2 con lectura registrada.
- El control de deriva con entradas al azar del mismo perfil, que es la mejor defensa del sistema contra confundir beta con ventaja.
- El DSR v2 (`stats.py:63-100`): la fórmula de Bailey y López de Prado está bien implementada, con validación de unidades por periodo.
- Los tests de lookahead y de paridad.
