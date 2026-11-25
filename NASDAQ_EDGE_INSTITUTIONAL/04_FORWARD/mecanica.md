# Mecanica historica del forward (F3)

Solo conteos: no se calculo P&L, expectativa, PF ni win rate. El corte por
2 perdidas o -300 USD/dia necesita desenlaces y **no** se aplica aqui.

Datos DEV: NQ CME 2010-2018 y Dukascopy 2019-2021. Sesiones completas,
con los rolls de NQ excluidos. Ventana 9:35-11:30 ET; maximas 3 senales/dia.

## Comision

**0,75 USD por contrato y lado** (input del operador, 2026-11-25).
La columna `NO TRADE` aplica la formula de contratos con esa comision y
slippage de 1 tick por lado. El corte por 2 perdidas no se aplica (necesita
desenlaces).

## NQF-A

- Sesiones: 2486; dias con senal: 2329 (93.68 %).
- Senales brutas: 2388; bloqueadas por FOMC: 56; por Tier 1: 0; tras noticias: 2332.
- Tras el maximo de 3/dia: 2329 senales. Objetivo invalido (<1R): 0; stop invalido: 0.
- Stop: mediana 6.84 pt (27.4 ticks); p90 25.72 pt (102.9 ticks).
- NO TRADE (comision 0,75): 3 (0.13 % de las senales tras noticias).
- Estimacion de fecha para n=200 operaciones (tras NO TRADE; sin el corte por perdidas): 214 sesiones, ~42.8 semanas, 2027-09-26, desde 2026-11-30.

| Ano | Sesiones | Dias con senal | % dias | Brutas | FOMC | Tier1 | Tras noticias | Tras 3/dia | NO TRADE | <1R | Stop invalido | Stop mediana pt |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2010 | 115 | 108 | 93.91 % | 110 | 2 | 0 | 108 | 108 | 0 | 0 | 0 | 4.04 |
| 2011 | 210 | 198 | 94.29 % | 203 | 5 | 0 | 198 | 198 | 0 | 0 | 0 | 4.28 |
| 2012 | 205 | 194 | 94.63 % | 198 | 4 | 0 | 194 | 194 | 0 | 0 | 0 | 4.29 |
| 2013 | 201 | 189 | 94.03 % | 192 | 3 | 0 | 189 | 189 | 0 | 0 | 0 | 3.96 |
| 2014 | 198 | 184 | 92.93 % | 187 | 3 | 0 | 184 | 184 | 0 | 0 | 0 | 4.89 |
| 2015 | 204 | 194 | 95.10 % | 198 | 4 | 0 | 194 | 194 | 0 | 0 | 0 | 6.89 |
| 2016 | 203 | 187 | 92.12 % | 192 | 5 | 0 | 187 | 187 | 0 | 0 | 0 | 6.00 |
| 2017 | 202 | 190 | 94.06 % | 194 | 4 | 0 | 190 | 190 | 0 | 0 | 0 | 5.46 |
| 2018 | 201 | 189 | 94.03 % | 194 | 5 | 0 | 189 | 189 | 0 | 0 | 0 | 12.99 |
| 2019 | 249 | 229 | 91.97 % | 234 | 5 | 0 | 229 | 229 | 0 | 0 | 0 | 10.85 |
| 2020 | 247 | 227 | 91.90 % | 238 | 8 | 0 | 230 | 227 | 3 | 0 | 0 | 24.41 |
| 2021 | 251 | 240 | 95.62 % | 248 | 8 | 0 | 240 | 240 | 0 | 0 | 0 | 24.53 |

## NQF-B

- Sesiones: 2486; dias con senal: 477 (19.19 %).
- Senales brutas: 1314; bloqueadas por FOMC: 39; por Tier 1: 0; tras noticias: 1275.
- Tras el maximo de 3/dia: 491 senales. Objetivo invalido (<1R): 784; stop invalido: 0.
- Stop: mediana 4.25 pt (17.0 ticks); p90 16.32 pt (65.3 ticks).
- NO TRADE (comision 0,75): 0 (0.0 % de las senales tras noticias).
- Estimacion de fecha para n=200 operaciones (tras NO TRADE; sin el corte por perdidas): 1013 sesiones, ~202.6 semanas, 2030-10-18, desde 2026-11-30.

| Ano | Sesiones | Dias con senal | % dias | Brutas | FOMC | Tier1 | Tras noticias | Tras 3/dia | NO TRADE | <1R | Stop invalido | Stop mediana pt |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2010 | 115 | 17 | 14.78 % | 56 | 2 | 0 | 54 | 17 | 0 | 37 | 0 | 2.75 |
| 2011 | 210 | 38 | 18.10 % | 103 | 4 | 0 | 99 | 38 | 0 | 61 | 0 | 2.25 |
| 2012 | 205 | 41 | 20.00 % | 112 | 0 | 0 | 112 | 41 | 0 | 71 | 0 | 2.50 |
| 2013 | 201 | 27 | 13.43 % | 114 | 5 | 0 | 109 | 30 | 0 | 79 | 0 | 2.25 |
| 2014 | 198 | 40 | 20.20 % | 124 | 5 | 0 | 119 | 41 | 0 | 78 | 0 | 3.25 |
| 2015 | 204 | 32 | 15.69 % | 91 | 2 | 0 | 89 | 33 | 0 | 56 | 0 | 3.25 |
| 2016 | 203 | 46 | 22.66 % | 104 | 2 | 0 | 102 | 47 | 0 | 55 | 0 | 3.75 |
| 2017 | 202 | 35 | 17.33 % | 112 | 1 | 0 | 111 | 35 | 0 | 76 | 0 | 3.50 |
| 2018 | 201 | 41 | 20.40 % | 114 | 2 | 0 | 112 | 42 | 0 | 70 | 0 | 8.88 |
| 2019 | 249 | 54 | 21.69 % | 122 | 5 | 0 | 117 | 56 | 0 | 61 | 0 | 5.65 |
| 2020 | 247 | 55 | 22.27 % | 118 | 4 | 0 | 114 | 57 | 0 | 57 | 0 | 11.43 |
| 2021 | 251 | 51 | 20.32 % | 144 | 7 | 0 | 137 | 54 | 0 | 83 | 0 | 11.52 |

## NQF-C

- Sesiones: 2486; dias con senal: 1796 (72.24 %).
- Senales brutas: 3986; bloqueadas por FOMC: 99; por Tier 1: 0; tras noticias: 3887.
- Tras el maximo de 3/dia: 2779 senales. Objetivo invalido (<1R): 1049; stop invalido: 14.
- Stop: mediana 4.0 pt (16.0 ticks); p90 15.59 pt (62.4 ticks).
- NO TRADE (comision 0,75): 6 (0.15 % de las senales tras noticias).
- Estimacion de fecha para n=200 operaciones (tras NO TRADE; sin el corte por perdidas): 179 sesiones, ~35.8 semanas, 2027-08-08, desde 2026-11-30.

| Ano | Sesiones | Dias con senal | % dias | Brutas | FOMC | Tier1 | Tras noticias | Tras 3/dia | NO TRADE | <1R | Stop invalido | Stop mediana pt |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2010 | 115 | 81 | 70.43 % | 161 | 2 | 0 | 159 | 126 | 0 | 31 | 1 | 2.50 |
| 2011 | 210 | 155 | 73.81 % | 363 | 10 | 0 | 353 | 241 | 0 | 108 | 1 | 2.50 |
| 2012 | 205 | 155 | 75.61 % | 338 | 5 | 0 | 333 | 233 | 0 | 95 | 1 | 2.75 |
| 2013 | 201 | 151 | 75.12 % | 340 | 6 | 0 | 334 | 229 | 0 | 100 | 1 | 2.25 |
| 2014 | 198 | 138 | 69.70 % | 306 | 7 | 0 | 299 | 214 | 0 | 81 | 1 | 2.75 |
| 2015 | 204 | 141 | 69.12 % | 299 | 6 | 0 | 293 | 201 | 0 | 90 | 1 | 4.25 |
| 2016 | 203 | 151 | 74.38 % | 349 | 11 | 0 | 338 | 233 | 0 | 100 | 1 | 3.75 |
| 2017 | 202 | 137 | 67.82 % | 294 | 9 | 0 | 285 | 207 | 0 | 76 | 0 | 3.25 |
| 2018 | 201 | 146 | 72.64 % | 317 | 9 | 0 | 308 | 229 | 0 | 70 | 1 | 7.50 |
| 2019 | 249 | 191 | 76.71 % | 412 | 8 | 0 | 404 | 303 | 0 | 98 | 0 | 6.35 |
| 2020 | 247 | 179 | 72.47 % | 434 | 19 | 0 | 415 | 302 | 5 | 104 | 2 | 13.49 |
| 2021 | 251 | 171 | 68.13 % | 373 | 7 | 0 | 366 | 261 | 1 | 96 | 4 | 13.82 |

## Lectura

- La fecha estimada es una **cota optimista**: descuenta el NO TRADE, pero no
  el corte por 2 perdidas ni el -300 USD/dia, que necesitan desenlaces.
- No se leyo ningun desenlace ni se calculo ningun resultado.
