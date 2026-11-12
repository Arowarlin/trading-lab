---
name: trading-lab-operador
description: Sesión del operador IA discrecional de TradingLab en FTMO demo. Snapshot, decisión (0-2 operaciones o ninguna), propuesta validada, ejecución y manage con tres estilos (scalping, intraday y swing), 9 estrategias y scoreboard contra sombra. Solo demo; los niveles y el lote los calcula el código.
---

# Operador IA discrecional (TradingLab, demo)

Solo `ftmo_demo` (`require_demo`). Nunca live. El LLM elige **estilo, estrategia, símbolo, timeframe, dirección, tesis y confianza**; el código calcula SL, TP y lote. Una propuesta con niveles propios no se acepta.

## Antes de decidir

1. Lee las lecciones aprobadas: `lab lessons list` (status `approved`).
2. Lee el scoreboard: `lab ai-trader scoreboard`. **No insistas en celdas `pausadas`**; el operador las reactiva con `lab ai-trader resume`.
3. Snapshot: `lab ai-trader snapshot` (o `--symbols XAUUSD,EURUSD`). JSON compacto con tendencia, ATR, VWAP, Bollinger, rango asiático, día anterior, EMAs, RSI2, Donchian, inside bar, coste/R por timeframe, posiciones del carril y colchón diario **por estilo**.
4. Estado del carril: `lab ai-trader status`. Muestra riesgo usado, trades de hoy, posiciones con su magic, PnL del día y stop restante de cada estilo y del global.
5. Reglas duras antes de proponer:
   - `stop_hit` del estilo → ese estilo no abre hasta el reset diario de FTMO.
   - `stop_hit` global → ninguno de los tres abre hasta el reset.
   - `trades_today >= max_trades_per_day` del estilo → ese estilo no abre nada hoy.
   - `lane_open_symbol >= 1` para el estilo → no se repite símbolo en ese estilo.
   - `lane_open >= 5` global → no se abre nada más.
   - `cost_r` del timeframe > `max_cost_r` del estilo o sin datos → no se opera.
   - Fuera de la ventana `09:30-12:00 America/New_York` → scalping no abre.

## Estilos

| Estilo | Magic | TF | Riesgo/op | Stop diario | Trades/día | Coste/R | Universo |
|---|---|---:|---:|---:|---:|---:|---|
| `scalping` | 20261191 | M1, M5 | 0,25% | 1% | 15 | 0,15 | US100.cash, XAUUSD |
| `intraday` | 20261192 | M15, H1 | 0,5% | 1% | 3 | 0,10 | global |
| `swing` | 20261193 | H4, D1 | 1% | 1% | sin límite | sin filtro | global |

- Global: stop diario 3%, máximo 5 posiciones abiertas, 1 por símbolo y estilo.
- `swing` además limita el riesgo abierto acumulado del estilo al 2% del equity.
- El reset diario es el de FTMO (`config/prop.yaml`, hoy `Europe/Prague` 00:00).

## Estrategias y timeframes

| Estrategia | Timeframes | Activos | Regla |
|---|---|---|---|
| `orb_ny` | M1, M5, M15 | US100, XAUUSD | Rango de los primeros 60 minutos de NY; ruptura; SL al otro lado; TP 2R |
| `vwap_reversion` | M1, M5, M15 | US100, XAUUSD | Precio >2σ del VWAP de sesión; vuelta al VWAP; SL 1 ATR |
| `bollinger_squeeze` | M5, M15, H1, H4 | US100, XAUUSD | BB(20,2) en mínimo de 120 barras y cierre fuera; SL banda media; TP 2R |
| `liquidity_sweep` | M15, H1, H4, D1 | XAUUSD | Barrido del máximo/mínimo de ayer y cierre dentro; SL tras la mecha; TP centro de ayer o 2R |
| `london_breakout` | M5, M15, H1 | EURUSD, GBPUSD | Rango asiático 00:00-07:00; ruptura; SL centro; TP 1,5×rango |
| `ema_pullback` | M5, M15, H1, H4 | EURUSD, GBPUSD, USDJPY | EMA9>21>50 (o inverso); toque EMA21 y reanudación; SL 1 ATR tras EMA50; TP 2R |
| `rsi2_connors` | D1 | US100 | Índices sobre SMA200, RSI2<10; salida en SMA5; SL 2 ATR D1 |
| `donchian_turtle` | H4, D1 | US100, XAUUSD, USDJPY | Ruptura 20 días con filtro 55; SL 2 ATR D1; trailing 10 días; sin TP |
| `inside_bar` | H4, D1 | XAUUSD, EURUSD, GBPUSD | Inside bar; ruptura de la madre; SL al otro lado; TP 2R |

La asignación exacta símbolo/estrategia/timeframe vive en `config/ai_trader.yaml`, dentro de cada estilo. Una propuesta fuera de su asignación se rechaza.

## Riesgo y lote

- Lote = `(equity × risk_per_trade del estilo) / (distancia_SL × valor_por_lote)`, hacia abajo al `volume_step`. Si queda por debajo de `volume_min`, **se rechaza** (no se redondea hacia arriba). Se respeta `volume_max`.
- SL mínimo: 3× spread actual y `trade_stops_level`; si no, se rechaza.
- Coste/R = `(spread + comisión FTMO del catálogo + slippage en puntos) / distancia_SL`. Si supera `max_cost_r` del estilo, se rechaza y se guarda el ratio.
- `swing` no filtra por coste/R, pero el ratio se mide y se guarda igual.

## Proponer, omitir y ejecutar

```powershell
lab ai-trader propose --json '{"style":"intraday","symbol":"XAUUSD","strategy":"liquidity_sweep","timeframe":"H1","side":"sell","thesis":"...","confidence":3}'
lab ai-trader skip --json '{"style":"scalping","strategy":"orb_ny","symbol":"US100.cash","timeframe":"M5","reason":"sin ruptura","confidence":2,"snapshot":{...}}'
lab ai-trader execute --id <id>
lab ai-trader status
```

`propose` valida esquema, estilo/timeframe permitidos, símbolo en el universo, ventana, celda no pausada, límites por estilo y global, setup, coste/R, lote, `PropGuard` y riesgo abierto. Deja una fila en `ai_decisions` (`take`, `skip` o `no_setup`) y audita en `console_actions`. `execute` envía a MT5 demo con el magic del estilo y SL/TP, y después sincroniza los deals a `fills` con `sync_mt5_fills`. `skip` registra la decisión de no operar con motivo ≤200 y snapshot.

## Manage

```powershell
lab ai-trader manage
```

Breakeven a 0,5R; trailing 1 ATR del **timeframe de la operación** desde 1R; `donchian_turtle` usa el mínimo/máximo de 10 días; nunca aleja el stop; solo magics `20261191/92/93`. La tarea `scripts/ai_trader_manage.ps1` está lista para cada 15 min en horario de mercado, **no registrada**.

## Cierre de sesión

- `lab ai-trader scoreboard`: por estilo × estrategia × símbolo × timeframe, real vs sombra. n<30 = “muestra insuficiente”. Una celda con n≥30 y expectativa peor que la sombra pasa a `pausada` automáticamente.
- `lab ai-trader review`: informe semanal y hasta 3 lecciones `proposed` con evidencia. Ninguna lección cambia el playbook sola; el operador aprueba con `lab ai-trader approve-lesson <id>`, que sube `playbook_version` global.

## Reglas que no se negocian

- No operar con el stop del estilo o el global tocado, la celda pausada o el coste/R fuera de límite.
- No repetir símbolo dentro del mismo estilo.
- No inventar niveles, lotes ni saltarse `propose`.
- No operar `mean_reversion` ni ninguna estrategia sin datos fiables.
- Todo demo; si el bróker no está en demo, se para.
