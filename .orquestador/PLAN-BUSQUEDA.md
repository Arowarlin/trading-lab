# PLAN DE BÚSQUEDA · versión final (operador 2026-11-23; reordenado tras revisión de literatura y la sesión en papel HIPOTESIS-4-10.md)

## Reglas
1. Infraestructura CONGELADA: solo lo mínimo que una campaña de esta lista necesite.
2. Solo estas hipótesis. Hipótesis literal y spec escritas ANTES de mirar resultados. Nunca calcular rendimiento antes de register+approve (el guard de R9b lo impide).
3. Ritmo: una campaña cada 1-2 días; informe de 1 página.
4. PARADA: si el 2026-12-14 ninguna estrategia ha pasado el OOS-2, se para la búsqueda (quedan los carriles demo) y se replantea.
5. ÉXITO: una estrategia que pase OOS-2 con expectativa neta > 0, deriva ≥ 90 y mejora de P(pasar) en una cuenta; contraste con futuros Databento si existe el símbolo.
6. Expectativa realista: los efectos publicados rinden bastante menos tras publicarse (McLean & Pontiff 2016).

## Presupuesto final (4 hipótesis, ~80 combinaciones en total)
| # | Hipótesis | Evidencia | Mercado · TF | n_total | Qué falta | Notas de la sesión en papel |
|---|---|---|---|---:|---|---|
| 1 | Cambio de mes | Mixta (Carchano & Pardo: el único efecto de calendario persistente en futuros S&P; Maberly & Waggoner: desaparecido tras 1990; Liu: adelantado) | US500, US100 · D1 | 18 | Swap (R9c, en curso) | Specs ya escritas y verificadas sin cambios |
| 2 | Reversión alrededor de los fix de divisas | Fuerte y reciente (Krohn, Mueller & Whelan, JF 2024; sin costes) | USDJPY (fix Tokio 09:55 JST = 00:55 UTC), EURUSD y GBPUSD (fix Londres 16:00 Londres) · H1 | ≤ 18 | Plantilla `fix_reversal` (H1): ventana antes/después del fix con DST de Londres y de NY por separado; lado = contra el dólar después del fix | EURUSD/GBPUSD H1 solo viables por coste con stop ≥ 2,5×ATR; USDJPY H1 viable en ambas cuentas |
| 3 | Momentum de serie temporal en cesta | Un siglo de evidencia; más débil tras 2009; pocos mercados | XAU, US500, US100, EURUSD, GBPUSD, USDJPY · D1 | 9-18 | Campañas multi-símbolo (excepción mínima; diseño en PROPUESTA-multisimbolo.md) | — |
| 4 | Rebote tras ventas fuertes en índices | Boyarchenko, Larsen & Whelan 2023 (reversión asimétrica tras ventas) | US500, US100 · D1 | ≤ 27 | Ninguna: `d1_extension_reversion` con solo el lado largo tras caída | Riesgo: pocas operaciones |

## Descartadas (no se prueban)
- Deriva nocturna general (desaparecida 2021-25, NY Fed 2026).
- Pre-FOMC (desaparecida desde 2015, Kurov, Wolfe & Gilbert 2021). Las fechas FOMC quedan en fomc-fechas.md por si acaso.
- Pre-festivo y estacionalidad del oro (evidencia débil).
- Momentum de la última media hora (M30 no viable por coste; variante ya probada).
Ya probadas: reversión asiática USDJPY H1; Donchian+vol H4 en XAU y USDJPY; ny_open_vol_filter US100 M5; intraday_momentum_close.

## Calendario orientativo
| Fecha | Paso |
|---|---|
| 23-24 nov | R9c (swap) → campañas 1 (US500 y US100) |
| 25-27 nov | Plantilla fix_reversal → campaña 2 (USDJPY primero; EUR/GBP con stop ≥ 2,5 ATR) |
| 27 nov (viernes) | Traslado al SSD tras el cierre |
| 28 nov - 3 dic | Cesta multi-símbolo → campaña 3 |
| 4-6 dic | Campaña 4 (rebote) |
| 7-13 dic | Confirmaciones OOS-2 de lo que haya llegado; contraste con futuros |
| 14 dic | Decisión: seguir (fase C) o parar |
