# Futuros intradía: diseño y límites (Etapa 3)

## Perfil `intraday_futures`

Definido en `config/profiles.yaml`:

- timeframe **M15**;
- ventana **08:30–15:00 America/Chicago** (RTH), L-V;
- riesgo máximo por operación **0,25%**;
- máximo **3 operaciones/día**;
- validación mínima: **80 trades**, DSR ≥ 90%, PBO ≤ 30%, walk-forward y
  regímenes obligatorios.

No hay ningún bot de futuros activo; solo está el perfil y el stub de datos.

## Interfaz de datos

`tradinglab.data.futures.FuturesDataProvider` define:

```python
fetch_bars(symbol, timeframe, start, end, cache_dir) -> DataFrame
```

`ProjectXFuturesProvider` es un **stub explícito** que lanza
`NotImplementedError`: `/api/History/retrieveBars` requiere suscripción de datos
de ProjectX/TopstepX. No se ha implementado ni comprado esa descarga.

## Validación parcial mientras tanto

Mientras no haya barras intradía de pago, se pueden usar **ES=F y NQ=F diarios**
con el cargador yfinance/caché ya existente:

```powershell
lab fetch ES=F --start 2015-01-01
lab fetch NQ=F --start 2015-01-01
lab backtest ES=F --strategy trend
lab backtest NQ=F --strategy trend-ls
```

Esto valida la lógica de tendencia y el motor, **no** sustituye la validación
intradía: no modela RTH, gap de apertura, spread de futuros ni rollover de
contratos. Cuando exista suscripción, el proveedor ProjectX deberá cachear
barras M15 con la misma interfaz y pasar por los mismos controles.

## Pendiente

1. Suscripción de datos ProjectX/TopstepX.
2. Implementar `ProjectXFuturesProvider.fetch_bars` con rate limit y caché.
3. Contratos continuos y rollover.
4. Validar con MLL y reglas Topstep verificadas en el contrato.
