# Perfil · Topstep 50K (versión 2026-11-25.1, verificado 2026-11-25)

Fuente: help.topstep.com, artículos 8284197, 8284204, 8284206, 8284208,
8284215, 8284233, 13613539, 10305426 y 14289835. Detalle en
`01_RESEARCH/Prop_Firm_Rules.md` §1.

| Campo | Combine | XFA |
|---|---|---|
| Profit target | $3.000 | — |
| Drawdown | MLL $2.000 trailing EOD, vigilado en tiempo real con P&L abierto; se fija en el saldo inicial | MLL −$2.000; se fija en $0 al llegar a +$2.000 o tras el 1er payout |
| DLL | opcional, $1.000 (input del indicador) | heredado si se contrató |
| Consistencia | mejor día < $1.650 (55 % del objetivo) | Consistency: ≤ 40 %; Standard: 5 días ≥ $150 |
| Días mínimos | 2 | — |
| Máximo de contratos | 5 minis / 50 micros | techo 5/50; el Scaling Plan es una imagen no leída → **Sin datos**; el usuario debe vigilarlo |
| Noticias (Tier 1: CPI, PPI, NFP, FOMC, rueda de prensa) | ±5 min: NQ bloqueado, MNQ ≤ 3 | según saldo: 0/1, 0/1, 0/3 |
| Cierre | plano a las 15:10 CT; nuevas entradas hasta las 15:08 CT → indicador 16:08 ET | igual |
| Automatización | API TopstepX en Combine y XFA; **no** en LFA | |

El indicador aplica la ventana Tier 1 de la firma **además** de la interna
(−15/+20 min y FOMC +60 min o resto de sesión). Gana la más estricta.
