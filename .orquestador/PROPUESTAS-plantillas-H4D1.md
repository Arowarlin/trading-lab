# PROPUESTAS · tres plantillas H4/D1 (solo papel)

Fecha: 2026-11-22. Documento de diseño, **sin código**: no se creó ninguna
plantilla en `config/discovery/templates/`, no se registró ninguna campaña, no
se aprobó/ejecutó/confirmó nada, no se leyó OOS-1/OOS-2 y no se tocó
`config/intraday_forward.yaml` ni la incubación `us100-trend-d1`.

## 0. Por qué H4/D1

El cribado de costes de `propfund/onboarding_mtf.py` (R típico = mediana de
ATR(14) de los últimos 12 meses; coste = spread p75 + comisión + slippage ×2)
deja las cinco plantillas actuales como máximo en H1 (`asia_range_reversion`)
o M30 (el resto). Sin embargo, **H4 y D1 son las temporalidades más baratas**
en ambas cuentas: el mismo coste en puntos se divide por un ATR mucho mayor.

| Símbolo | H4 cost_R CFD-001 | H4 cost_R CFD-006 | D1 cost_R CFD-001 | D1 cost_R CFD-006 |
|---|---:|---:|---:|---:|
| US100 | 0,0212 | 0,0221 | 0,0078 | 0,0081 |
| US500 | no permitido | 0,0724 | no permitido | 0,0278 |
| US30 | no permitido | Sin datos | no permitido | Sin datos |
| XAUUSD | 0,0209 | 0,0182 | 0,0078 | 0,0068 |
| EURUSD | 0,0751 | 0,0973 | 0,0281 | 0,0364 |
| GBPUSD | 0,0749 | 0,0851 | 0,0283 | 0,0321 |
| USDJPY | 0,0465 | 0,0405 | 0,0170 | 0,0148 |

Lectura: US100, XAUUSD y USDJPY son los más baratos en H4/D1; EURUSD y GBPUSD
solo son claramente viables en D1 (en H4, CFD-006 queda al 0,085–0,097 R, pegado
al umbral 0,10). US30 no tiene spread de CFD-006 y US500 solo existe en
CFD-006. **H4/D1 exigen `data_source: dukascopy`**; el bróker no tiene historia
suficiente. Fechas útiles: US100 H4 desde 2019-01 y D1 desde 2014-01; US500 H4
desde 2019-01 y D1 desde 2018-01; XAUUSD y los tres pares FX desde 2003-05.

Ninguna de las tres propuestas reutiliza las familias ya probadas
(`asia_range_reversion`, `intraday_momentum_close(_v2)`,
`ny_open_vol_filter`, `session_breakout_htf`). Son familias nuevas y, si se
implementan, declararían `timeframes` y `valid_timeframes` únicamente con su TF
(H4 o D1), sesión 00:00–23:59 y `flat_at: 23:59` (la sesión intradía no aplica).

---

## 1. Plantilla A · `ts_momentum_d1`

**Familia:** momentum de serie temporal / trend following en D1. **TF:** D1.

### Hipótesis y por qué podría existir

Los precios de índices, oro y divisas tienden a persistir en el horizonte de
semanas/meses: la infrarreacción a noticias, el rebalanceo lento de carteras y
el flujo de trend followers generan autocorrelación positiva de retornos a
plazos medios. La señal clásica es el retorno de 12 meses (o el cruce de medias
largas), no una ruptura intradía.

Referencias: Moskowitz, Ooi & Pedersen, *Time Series Momentum* (JFE, 2012);
Hurst, Ooi & Pedersen, *A Century of Evidence on Trend-Following Investing*
(JPM, 2017). Es la misma familia que la incubación `us100-trend-d1`, pero aquí
se propone **fuera de US100** para no duplicarla.

### Bloques DSL

- Usa: `sma` (dos ventanas), `cross_up`/`cross_down`, `price`, `atr`, `and`,
  `exit.stop` ATR y `exit.trailing`.
- Falta: un bloque genérico `roc(n)` o `slope(n)` para expresar directamente el
  momentum de 12 meses. Se puede aproximar con el cruce de SMA; si se quiere la
  señal académica exacta, hay que añadir `roc` al catálogo (fuera del alcance de
  este documento).

### Regla propuesta (descripción, no YAML)

- Largo: `cross_up(SMA(fast), SMA(slow))` **y** `close > SMA(slow)`.
- Corto: espejo exacto (`cross_down` y `close < SMA(slow)`) o plantilla
  long-only. Para la primera campaña se propone **symmetric: true**, porque en
  FX/oro el trend following funciona en ambos sentidos.
- Salida: stop ATR(14) × `stop_mult`, trailing ATR(14) × 3,0, sin target fijo
  (target R:R 1000 = “dejar correr”); sin salida por tiempo.
- Límites: 1 operación/día, cooldown 0 (las señales de cruce son raras).

### Parámetros (3; grid 3 × 2 × 3 = 18)

| Parámetro | Path DSL | Valores | Razón |
|---|---|---|---|
| `fast_n` | `long_entry.args[0].left.n` | 20, 50, 100 | 20 = rápido; 50 = clásico; 100 = medio. Siempre < slow. |
| `slow_n` | `long_entry.args[0].right.n` | 150, 200 | 150/200 capturan el ciclo largo sin mirar 12 meses exactos. |
| `stop_mult` | `exit.stop.mult` | 2,5, 3,0, 3,5 | En D1 el stop debe sobrevivir gaps y ruido; 3,0 es el de la incubación. |

Fijos: `target.rr = 1000`, `trailing = {n: 14, mult: 3.0}`,
`max_trades_per_day = 1`, `warmup_minutes = 288000` (200 barras D1).

### TF y símbolos viables (cribado)

D1, por orden de coste: **XAUUSD** (0,0068–0,0078 R), **USDJPY**
(0,0148–0,0170), **EURUSD** (0,0281–0,0364), **GBPUSD** (0,0283–0,0321).
US100 también es viable (0,0078–0,0081) pero **se excluye de esta propuesta**
por solape con `us100-trend-d1`. US500 solo CFD-006 y US30 sin spread.

Ventana IS razonable: 2004-01-01 → 2024-06-30 para XAU/FX; si se incluyera
US100, 2014-01-01 → 2024-06-30.

### Operaciones esperadas por año (aproximado)

1–3 por símbolo y año con cruces 50/200; al bajar a 20/150 puede llegar a 2–5.
Con 3–4 símbolos: **6–18 operaciones/año** en total. Referencia: la incubación
US100 50/200 hizo 10 operaciones en 9 años (~1,1/año); XAU 50/200 hizo 53 en
22 años (~2,4/año).

### Solape con `us100-trend-d1`

- Si se incluyera US100: **solape alto** (misma familia de tendencia, misma
  señal lenta, mismo subyacente). No se propone.
- Con XAU/FX: solape bajo; solo comparten la familia conceptual, no el activo.
- No se toca `us100-trend-d1` (`enabled: true`, magic 20261153) ni su propuesta
  de cementerio, que sigue sin aplicar.

---

## 2. Plantilla B · `donchian_vol_h4`

**Familia:** ruptura de canal Donchian con filtro de volatilidad en H4.
**TF:** H4.

### Hipótesis y por qué podría existir

Una ruptura del máximo de N barras señala que el mercado ha absorbido la
liquidez del rango y entra en una fase de descubrimiento de precio; los
breakouts tienen colas positivas y funcionan mejor cuando la volatilidad sale
de un régimen comprimido. El filtro de volatilidad alta evita rupturas en
mercados dormidos, donde el spread pesa más que el movimiento.

Referencias: sistemas Donchian/Turtle (Richard Dennis y William Eckhardt,
años 80; 20 y 55 barras), *Way of the Turtle* (Curtis Faith, 2007); la variante
de volatilidad sigue la idea de “volatility breakout” de Larry Williams. La
novedad aquí es H4 + filtro `atr_pct_rank`, no una copia del bot D1.

### Bloques DSL

- Usa: `level donchian_high` / `donchian_low` con `n`, `cross_up`/`cross_down`,
  `regime vol_high` (`atr_pct_rank`), `atr`, `time_exit_minutes`,
  `max_trades_per_day`, `cooldown_minutes`.
- Falta: nada imprescindible. `donchian_level` ya está desplazado una barra
  (`shift(1)`), así que no mira el futuro. Opcional: usar `donchian_pos` en vez
  del nivel, pero el nivel es más directo para una ruptura.

### Regla propuesta

- Largo: `cross_up(close, donchian_high(n))` **y**
  `vol_high(n=14, lookback=100, pct=vol_pct)`.
- Corto: espejo con `donchian_low(n)` y `cross_down`.
- Salida: stop ATR(14) × `stop_mult`, target R:R 2,0, salida por tiempo 5 días
  (7.200 minutos). Sin trailing en la primera versión.
- Límites: 1 operación/día, cooldown 240 minutos (una barra H4).

### Parámetros (3; grid 3 × 3 × 3 = 27)

| Parámetro | Path DSL | Valores | Razón |
|---|---|---|---|
| `channel_n` | `long_entry.args[0].right.n` | 20, 40, 55 | 20 = Turtle rápido; 40 = intermedio; 55 = Turtle lento. |
| `vol_pct` | `long_entry.args[1].params.pct` | 0,60, 0,70, 0,80 | Exigir que el ATR esté en el 60/70/80 % superior de 100 barras. |
| `stop_mult` | `exit.stop.mult` | 1,5, 2,0, 2,5 | Stop H4: 1,5 ajusta; 2,5 da aire sin disparar el riesgo por operación. |

Fijos: `target.rr = 2.0`, `time_exit_minutes = 7200`, `max_trades_per_day = 1`,
`cooldown_minutes = 240`, `warmup_minutes = 14400` (60 barras H4).

### TF y símbolos viables (cribado)

H4, por orden de coste: **XAUUSD** (0,0182–0,0209 R), **US100**
(0,0212–0,0221), **USDJPY** (0,0405–0,0465), **US500** solo CFD-006
(0,0724), **EURUSD** (0,0751–0,0973) y **GBPUSD** (0,0749–0,0851) al límite.
Recomendación inicial: **XAUUSD + USDJPY**. US100 se deja fuera por solape;
EUR/GBP solo después de comprobar que el bruto supera 0,10 R/op con holgura.
US30 no tiene spread.

Ventana IS: 2004-01-01 → 2024-06-30 para XAU/FX; US100 2019-01-01 →
2024-06-30 si se reconsidera.

### Operaciones esperadas por año (aproximado)

Un canal de 20–55 barras H4 equivale a 3–9 días; con 1 operación/día y salida
máxima de 5 días, **15–35 por símbolo y año**. Con 2 símbolos: **30–70/año**.
La cifra es una estimación de diseño, no un resultado: la frecuencia real la
decide el preflight/feasibility seco.

### Solape con `us100-trend-d1`

- En US100 H4: **solape alto** (tendencia/ruptura en el mismo TF y activo, y la
  incubación ya está `enabled`). No se propone US100 en la primera campaña.
- En XAU/USDJPY: solape bajo; familia de ruptura, pero otro activo.
- No se toca la incubación ni su configuración; su propuesta de cementerio
  (Sharpe con swap 0,041) sigue pendiente de decisión del operador.

---

## 3. Plantilla C · `d1_extension_reversion`

**Familia:** reversión a la media en D1 tras extensión, con filtro de tendencia
larga. **TF:** D1. **Long-only** en la primera versión.

### Hipótesis y por qué podría existir

Tras una extensión bajista short-term (varias desviaciones estándar por debajo
de la media) en un activo que sigue en tendencia larga, el precio tiende a
rebotar: el movimiento responde a liquidez/sobrerreacción y no a un cambio de
régimen. Comprar la extensión en la dirección de la tendencia larga evita
pelear contra el mercado.

Referencias: Connors & Alvarez, *Short Term Trading Strategies That Work*
(2008), RSI(2) y compras de dips en índices; Jegadeesh, *Evidence of Predictable
Behavior of Security Returns* (JF, 1990), reversión short-term; De Bondt &
Thaler, *Does the Stock Market Overreact?* (JF, 1985). Es una familia distinta
de la reversión intradía al rango asiático.

### Bloques DSL

- Usa: `zscore` (ventana), `const`, `sma` (200), `rsi` (2), `price`, `atr`,
  `and`, `gt`/`lt`, `exit.stop`, `exit.target`, `time_exit_minutes`.
- Falta: una condición de salida DSL (“cerrar cuando close > SMA(5)” o “RSI >
  65”). El motor solo tiene stop, target, trailing, tiempo y `opposite_signal`.
  Workaround: target R:R 1,0 + salida por tiempo 5 días. Si se quiere la regla
  Connors exacta, hay que añadir `exit_when` al DSL (fuera de alcance).

### Regla propuesta

- Largo: `zscore(z_n) < z_entry` (valor negativo, p. ej. −2,0) **y**
  `close > SMA(200)` **y** `RSI(2) < 10`.
- Sin cortos en la primera versión: en índices/oro el sesgo largo es parte de
  la hipótesis; el espejo bajista sería otra hipótesis.
- Salida: target R:R 1,0, stop ATR(14) × `stop_mult`, salida por tiempo 5 días
  (7.200 minutos).
- Límites: 1 operación/día, cooldown 0.

### Parámetros (3; grid 3 × 3 × 3 = 27)

| Parámetro | Path DSL | Valores | Razón |
|---|---|---|---|
| `z_n` | `long_entry.args[0].right.n` | 10, 20, 30 | 2, 4 y 6 semanas de ventana; la extensión se mide contra su propia media. |
| `z_entry` | `long_entry.args[0].left.value` | −1,5, −2,0, −2,5 | Más negativo = menos trades y más extremos; −2,0 es el centro. |
| `stop_mult` | `exit.stop.mult` | 1,5, 2,0, 2,5 | D1: 1,5 puede saltar con el ruido; 2,5 protege el rebote. |

Fijos: `RSI(2) < 10`, `SMA(200)`, `target.rr = 1.0`,
`time_exit_minutes = 7200`, `max_trades_per_day = 1`,
`warmup_minutes = 288000` (200 barras D1).

### TF y símbolos viables (cribado)

D1, por orden de coste: **XAUUSD** (0,0068–0,0078 R), **USDJPY**
(0,0148–0,0170), **EURUSD** (0,0281–0,0364), **GBPUSD** (0,0283–0,0321).
US100 es viable (0,0078–0,0081) pero se excluye por solape de subyacente con la
incubación; US500 solo CFD-006 y US30 sin spread.

Ventana IS: 2004-01-01 → 2024-06-30.

### Operaciones esperadas por año (aproximado)

La combinación RSI(2) < 10 + z < −2 + cierre > SMA200 es selectiva: **5–12 por
símbolo y año**. Con 2–3 símbolos: **10–36/año**. Es una estimación; el número
real depende de la ventana y del régimen.

### Solape con `us100-trend-d1`

- En US100 D1: **solape conceptual bajo** (reversión contra extensión frente a
  tendencia), pero comparten subyacente y TF. Si ambos corren en la misma
  cuenta, la exposición neta puede compensarse y complicar el riesgo; no se
  propone US100 en la primera campaña.
- En XAU/FX: solape bajo. La incubación no opera esos activos.
- No se toca `us100-trend-d1` ni su configuración.

---

## 4. Comparación y orden sugerido

| # | Plantilla | Familia | TF | Símbolos iniciales | Params | n_total | Ops/año (aprox.) | Coste D1/H4 (R) | Solape US100 |
|---|---|---|---|---|---:|---:|---|---|---|
| A | `ts_momentum_d1` | momentum de serie temporal | D1 | XAUUSD, USDJPY, EURUSD, GBPUSD | 3 | 18 | 6–18 | 0,007–0,036 | bajo (sin US100) |
| B | `donchian_vol_h4` | ruptura Donchian + volatilidad | H4 | XAUUSD, USDJPY | 3 | 27 | 30–70 | 0,018–0,047 | bajo (sin US100) |
| C | `d1_extension_reversion` | reversión tras extensión | D1 | XAUUSD, EURUSD, GBPUSD | 3 | 27 | 10–36 | 0,007–0,036 | bajo (sin US100) |

**Orden sugerido para la siguiente campaña:** B primero. Es la que tiene todos
los bloques DSL disponibles, coste H4 bajo en XAU/USDJPY y una definición
mecánica difícil de sobreajustar; A depende de un proxy de momentum (falta
`roc`) y C depende de un workaround de salida (falta `exit_when`). Si B pasa el
preflight y la factibilidad en seco, A y C quedan como segunda y tercera.

Ninguna se registra aquí. Si el operador las aprobara, cada `n_total` entraría
completo en el DSR al registrar: 1703 + 18 = 1721 (A), 1703 + 27 = 1730 (B) y
1703 + 27 = 1730 (C). Son cifras informativas; **no se consumió DSR**.

## 5. Lo que haría falta para implementarlas (sin hacerlo ahora)

1. Crear los YAML en `config/discovery/templates/` con `timeframes` y
   `valid_timeframes` H4/D1, sesión 00:00–23:59 y `flat_at: 23:59`.
2. Pasar `preflight --spec` y `feasibility --spec` en seco, sin registrar.
3. Solo si el operador lo pide: registrar la campaña con `data_source:
   dukascopy` y `IS` dentro de `usable_from`.
4. No tocar `config/intraday_forward.yaml`, `us100-trend-d1` ni su `enabled`.
