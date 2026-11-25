# Verificación previa NQF-A/B/C

| Comprobación | Valor | Límite | Factor | Estado | Detalle |
|---|---:|---:|---:|---|---|
| ENTRY_END | 690 | 690 | Sin datos | ok | constante |
| ENTRY_START | 575 | 575 | Sin datos | ok | constante |
| FLAT | 955 | 955 | Sin datos | ok | constante |
| MNQ_USD_PER_POINT | 2 | 2 | Sin datos | ok | constante |
| OR_MIN | 15 | 15 | Sin datos | ok | constante |
| RISK_USD | 150 | 150 | Sin datos | ok | constante |
| SESS_CLOSE | 960 | 960 | Sin datos | ok | constante |
| SESS_OPEN | 570 | 570 | Sin datos | ok | constante |
| TICK | 0.25 | 0.25 | Sin datos | ok | constante |
| tick MNQ USD | 0.5 | 0.5..0.5 | 1 | ok |  |
| riesgo USD | 150 | 150..150 | 1 | ok |  |
| comision USD/lado | 0.75 | 0.75..0.75 | 1 | ok |  |
| NQF-A OR15 ruptura | ok | sí | Sin datos | ok | OR 9:30-9:44; entrada 9:50; stop 99,5 |
| NQF-B barrido ONH >= 2 ticks | ok | sí | Sin datos | ok | cierre dentro; stop 1 tick sobre el extremo |
| NQF-C reversion VWAP +/- 2 sigma | ok | sí | Sin datos | ok | cierre fuera y vuelta dentro; stop extremo + 1 tick |
| SL primero en la misma vela | ok | sí | Sin datos | ok | si SL y TP caen en la misma vela, gana el SL |
| contratos stop 10 pt | ok | sí | Sin datos | ok | 150/22,5 = 6 |
| NO TRADE stop 75 pt | ok | sí | Sin datos | ok | 150/152,5 = 0 |
| comisión ausente no se inventa | ok | sí | Sin datos | ok | MissingInput |
| FOMC bloquea el día completo | ok | sí | Sin datos | ok | día FOMC sin entradas |
| Tier 1 +/- 5 min | ok | sí | Sin datos | ok | bloqueo simétrico alrededor del evento |
| cierre 5 min antes de Tier 1 | ok | sí | Sin datos | ok | salida a mercado 5 min antes |
| cierre a las 15:55 ET | ok | sí | Sin datos | ok | flat en el minuto 955 |
| zona horaria del runner | ok | sí | Sin datos | ok | forward_daily.py convierte a America/New_York |
| NQF-A señales/día DEV | 0.938 | 0..3 | 1 | ok | conteo F3, no resultado; máximo 3/día |
| NQF-B señales/día DEV | 0.198 | 0..3 | 1 | ok | conteo F3, no resultado; máximo 3/día |
| NQF-C señales/día DEV | 1.12 | 0..3 | 1 | ok | conteo F3, no resultado; máximo 3/día |
| ejemplo de comisión del runner | 1.25 | 0.75 | Sin datos | aviso | ejemplo del docstring; no es una constante ni afecta a la mecánica |
| huella de la fecha de inicio | e0b7c44611a45c9d | 2026-11-30 | Sin datos | ok | forward n=0; solo fecha de inicio |

**Veredicto: Conforma** — 29 comprobaciones, 0 defectos (1 avisos).

## Alcance

- Código verificado: `NASDAQ_EDGE_INSTITUTIONAL/tools/forward_models.py`.
- SHA-256: `cb7ee5a996e28becba65d211c99f23436c9ec4e31cd0ae8c4281268cb47c69b3`.
- Prerregistro: `04_FORWARD/prerregistro.md`; comisión 0.75 USD por contrato y lado.
- Datos: sintéticos y conteos DEV de `04_FORWARD/mecanica.md`; sin desenlaces, sin P&L y sin leer `03_BACKTEST/`.
- Verificador: otra sesión (TL3-E2); el código no se modifica.

## Notas

- `forward_daily.py` recibe la comisión por CLI; no la hardcodea. El valor 0,75 está en el prerregistro y en `forward_mechanics.py`.
- El ejemplo del docstring de `forward_daily.py` usa 1,25: es un aviso documental, no un defecto de la mecánica congelada.
