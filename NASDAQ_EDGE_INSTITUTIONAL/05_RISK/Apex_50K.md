# Perfil · Apex Trader Funding 50K (versión 2026-11-25.1, verificado 2026-11-25)

Fuente: apextraderfunding.com/help-center, rutas EOD e Intraday,
scaling-levels-pa-explained, daily-loss-limit-explained y prohibited-activities.

| Perfil del indicador | Drawdown | DLL | Contratos | Notas |
|---|---|---|---|---|
| Evaluación EOD | $2.000, umbral fijado al cierre (16:59:59 ET) y vigilado en tiempo real | $1.000 | 6 | Rithmic/Wealthcharts se fija en $53.000; Tradovate sigue trailing |
| Evaluación Intraday | $2.000 trailing sobre el **pico intradía no realizado** | no hay | 6 | El umbral sube aunque la operación cierre en 0 |
| PA EOD / PA Intraday | $2.000; se fija en $50.100 | por nivel: $1.000 / $1.000 / $2.000 / $3.000 | 2 / 3 / 4 / 4 por nivel (beneficio < 1,5k / < 3k / < 6k / ≥ 6k) | El indicador calcula el nivel con el saldo introducido |

- Equivalencia micro/mini en Apex: **Sin datos** (la página no la publica). El
  indicador aplica 1 mini = 10 micros por defecto; verificar en la plataforma.
- **Automatización prohibida.** El indicador solo informa.
- Noticias: se permite operar la estrategia normal; se prohíbe el "news trading"
  a ambos lados.
- No se pueden mantener posiciones al cierre. Hora exacta del cierre forzoso:
  **Sin datos**; el indicador corta las entradas a las 16:55 ET.
- Obligatorio el stop. Prohibido usar el umbral como stop y hacer hedging.
