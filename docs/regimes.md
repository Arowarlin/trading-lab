# Régimen de mercado (informativo)

Clasificador **causal** por reglas: tendencia + volatilidad. No usa información
futura, no activa ni desactiva bots y no cambia ningún criterio de propuesta.

## Reglas

- **Tendencia**: close > SMA200 y pendiente de SMA50 > 0 → `trend_up`;
  close < SMA200 y pendiente < 0 → `trend_down`; resto → `range`.
- **Volatilidad**: desviación anualizada de 20 días comparada con su mediana de
  252 días → `low`/`high`.
- Etiquetas `unknown` durante el warmup (200 barras).
- Todo es rolling/expanding hacia atrás; el test de truncado confirma que la
  etiqueta en `t` no cambia al añadir datos posteriores.

## Métricas

- **Estabilidad**: fracción de días con la misma etiqueta que el día anterior.
- **Duración media**: longitud media de los tramos de régimen.
- **Cambios**: número de transiciones.
- **Falsos cambios**: cambios que vuelven a la etiqueta previa en 5 días.
- **Retraso de detección**: días entre un cambio de la referencia suavizada
  (mayoría centrada de 21 días) y el primer cambio causal. La referencia
  centrada se usa **solo para evaluación**, nunca en vivo.
- **Rendimiento por régimen**: N, retorno, Sharpe, volatilidad, MaxDD y acierto
  para el activo y, con `--bot`, para el bot.

## Uso

```powershell
lab regimes QQQ
lab regimes QQQ --bot qqq-trend-f13
lab regimes QQQ --json
```

El Dashboard muestra el régimen actual de QQQ y el rendimiento del benchmark por
régimen. El selector por régimen se publica como **`proposed` / `enabled:false`**
y **no se aplica**.

## GMM/HMM

Se evaluó `hmmlearn 0.3.3` (BSD-3-Clause) y `scikit-learn 1.9.1`
(BSD-3-Clause). **No se añaden** en esta etapa: no están instalados, el
clasificador por reglas ya es causal y explicable, y no hay evidencia con la
muestra actual de que un GMM/HMM aporte estabilidad suficiente. Queda como
candidato para una etapa posterior, nunca como requisito de propuesta.

## Evidencia

`pytest tests/test_regimes.py tests/test_web.py -q` → 23 passed; suite completa
386 passed; `ruff` limpio; `lab doctor` OK. Sin dependencias nuevas.
