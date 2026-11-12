---
name: trading-lab-operador
description: Sesión del operador IA discrecional de TradingLab en FTMO demo. Snapshot, decisión (0-2 operaciones o ninguna), propuesta validada, ejecución y manage con 9 estrategias y scoreboard contra sombra. Solo demo; los niveles y el lote los calcula el código.
---

# Operador IA discrecional (TradingLab, demo)

Solo `ftmo_demo` (`require_demo`). Nunca live. El LLM elige **estrategia, símbolo, timeframe, dirección, tesis y confianza**; el código calcula SL, TP y lote. Una propuesta con niveles propios no se acepta.

## Antes de decidir

1. Lee las lecciones aprobadas: `lab lessons list` (status `approved`).
2. Lee el scoreboard: `lab ai-trader scoreboard`. **No insistas en celdas `pausadas`**; el operador las reactiva con `lab ai-trader resume`.
3. Snapshot: `lab ai-trader snapshot` (o `--symbols XAUUSD,EURUSD`). JSON compacto con tendencia, ATR, VWAP, Bollinger, rango asiático, día anterior, EMAs, RSI2, Donchian, inside bar, coste/R por timeframe, posiciones del carril y colchón diario.
4. Reglas duras antes de proponer:
   - `daily_stop_remaining <= 0` → no se abre hasta el reset diario de FTMO.
   - `trades_today >= 6` → no se abre nada hoy.
   - `lane_open_symbol >= 1` → no se repite símbolo.
   - `lane_open >= 3` → no se abre nada más.
   - `cost_r` del timeframe > 0,10 o sin datos → no se opera.

## Estrategias y asignación

| Estrategia | TF | Activos | Regla |
|---|---|---|---|
| `orb_ny` | M15 | US100 | Rango primeros 4 bloques M15 de NY; ruptura; SL al otro lado; TP 2R; cierre de sesión |
| `vwap_reversion` | M15 | US100 | Precio >2σ del VWAP de sesión; vuelta al VWAP; SL 1 ATR M15 |
| `bollinger_squeeze` | H1 | US100 | BB(20,2) en mínimo de 120 barras y cierre fuera; SL banda media; TP 2R |
| `liquidity_sweep` | H1 | XAUUSD | Barrido del máximo/mínimo de ayer y cierre dentro; SL tras la mecha; TP centro de ayer o 2R |
| `london_breakout` | H1 | EURUSD, GBPUSD | Rango asiático 00:00-07:00; ruptura 07:00-10:00; SL centro; TP 1,5×rango |
| `ema_pullback` | H1 | EURUSD, GBPUSD, USDJPY | EMA9>21>50 (o inverso); toque EMA21 y reanudación; SL 1 ATR tras EMA50; TP 2R |
| `rsi2_connors` | D1 | US100 | Índices sobre SMA200, RSI2<10; salida en SMA5; SL 2 ATR D1 |
| `donchian_turtle` | D1 | US100, XAUUSD, USDJPY | Ruptura 20 días con filtro 55; SL 2 ATR D1; trailing 10 días; sin TP |
| `inside_bar` | D1 | XAUUSD, EURUSD, GBPUSD | Inside bar; ruptura de la madre; SL al otro lado; TP 2R |

Una propuesta fuera de su asignación (símbolo/estrategia/timeframe) se rechaza.

## Riesgo y lote

- `risk_per_trade` 0,5 % del equity; `daily_stop` 2 %; máx. 6 operaciones/día; máx. 1 por símbolo; máx. 3 abiertas.
- Lote = `(equity × 0,5%) / (distancia_SL × valor_por_lote)`, hacia abajo al `volume_step`. Si queda por debajo de `volume_min`, **se rechaza** (no se redondea hacia arriba).
- SL mínimo: 3× spread actual y `trade_stops_level`; si no, se rechaza.
- Coste/R = (spread + comisión FTMO + 1 bps) / distancia_SL; si > 0,10, se rechaza.

## Proponer y ejecutar

```powershell
lab ai-trader propose --json '{"symbol":"XAUUSD","strategy":"liquidity_sweep","timeframe":"H1","side":"sell","thesis":"...","confidence":3}'
lab ai-trader execute --id <id>
```

`propose` valida esquema, asignación, setup en el snapshot, celda no pausada, riesgo, coste/R, lote, PropGuard y los límites del carril. `execute` envía con magic `20261190` y SL/TP.

## Manage

```powershell
lab ai-trader manage
```

Breakeven a 0,5R; trailing 1 ATR del **timeframe de la operación** desde 1R; `donchian_turtle` usa el mínimo/máximo de 10 días; nunca aleja el stop; solo magic del carril. La tarea `scripts/ai_trader_manage.ps1` está lista para cada 15 min en horario de mercado, **no registrada**.

## Cierre de sesión

- `lab ai-trader scoreboard`: por estrategia × símbolo × timeframe, real vs sombra. n<30 = “muestra insuficiente”. Una celda con n≥30 y expectativa peor que la sombra pasa a `pausada` automáticamente.
- `lab ai-trader review`: informe semanal y hasta 3 lecciones `proposed` con evidencia. Ninguna lección cambia el playbook sola; el operador aprueba con `lab ai-trader approve-lesson <id>`, que sube `playbook_version`.

## Reglas que no se negocian

- No operar con el stop diario tocado, la celda pausada o el coste/R fuera de límite.
- No repetir símbolo con posición abierta del carril.
- No inventar niveles, lotes ni saltarse `propose`.
- No operar `mean_reversion` ni ninguna estrategia sin datos fiables.
- Todo demo; si el bróker no está en demo, se para.
