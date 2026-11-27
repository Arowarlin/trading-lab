# B04-swap · Swap cobrado por noche en deals reales (solo lectura)

Posiciones emparejadas: 74; de una sola noche: 10.

| Cuenta | Símbolo | Lado | Apertura (NY) | Cierre (NY) | Noche | Volumen | Swap | Swap/volumen |
|---|---|---|---|---|---|---:|---:|---:|
| ftmo_demo | EURUSD | sell | 2026-11-11 Wed 13:11 | 2026-11-11 Wed 17:05 | Wed->Thu | 2.04 | 1.22 | 0.60 |
| ftmo_demo | GBPUSD | sell | 2026-11-20 Fri 03:08 | 2026-11-22 Sun 17:59 | Fri->Mon | 1.49 | -8.28 | -5.56 |
| ftmo_demo | GBPUSD | buy | 2026-11-26 Thu 03:06 | 2026-11-27 Fri 08:23 | Thu->Fri | 2.26 | -10.15 | -4.49 |
| ftmo_demo | US100.CASH | sell | 2026-11-20 Fri 10:18 | 2026-11-23 Mon 10:30 | Fri->Mon | 1.06 | 0.00 | 0.00 |
| ftmo_demo | US100.CASH | sell | 2026-11-19 Thu 09:57 | 2026-11-20 Fri 09:49 | Thu->Fri | 1.25 | 0.00 | 0.00 |
| ftmo_demo | US100.CASH | sell | 2026-11-25 Wed 12:00 | 2026-11-26 Thu 09:59 | Wed->Thu | 0.62 | 0.00 | 0.00 |
| ftmo_demo | XAUUSD | sell | 2026-11-12 Thu 09:31 | 2026-11-12 Thu 20:16 | Thu->Fri | 0.03 | -0.13 | -4.33 |
| ftmo_demo | XAUUSD | sell | 2026-11-19 Thu 10:17 | 2026-11-20 Fri 10:00 | Thu->Fri | 0.16 | 0.00 | 0.00 |
| ftmo_demo | XAUUSD | sell | 2026-11-11 Wed 13:53 | 2026-11-11 Wed 18:05 | Wed->Thu | 0.03 | -0.38 | -12.67 |
| ftmo_demo | XAUUSD | sell | 2026-11-11 Wed 13:43 | 2026-11-11 Wed 18:05 | Wed->Thu | 0.07 | -0.88 | -12.57 |

Cómo leerlo: para un mismo símbolo y lado, compara el swap por volumen de la noche
`Thu->Fri` y la de `Fri->Mon` con el de una noche normal (`Mon->Tue`, `Tue->Wed`).
La que sea ~3 veces mayor es la del triple swap. Si no hay ninguna de esas noches: Sin datos.

## Salida

Escrito docs\engineering\WORKER_REPORTS\B04-swap.md: 10 posiciones de una noche
