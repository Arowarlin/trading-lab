# TL3-D · D5 Plan de seguimiento del EA en el forward

Solo conteos: no se calcula ningún R, PF ni expectativa del forward. Nada de este bloque suma al contador.

## Forward del EA

- Operaciones **cerradas**: **3**.
- Fechas de entrada: **2026-11-16, 2026-11-18, 2026-11-24**.
- Fuente: `ea_forward._closed` (sin modificarlo) sobre `data/lab.db`; bot `ea:us100-ftmo1`.

## Referencia del backtest (T6)

- Réplica: **479 operaciones**, **+0.3104 R** de media, sd **1.9173 R**.
- Frecuencia por año: 2021: 34, 2022: 84, 2023: 94, 2024: 96, 2025: 86, 2026: 85.
- Ventana: 2021-09-20 a 2026-11-24; **1301 sesiones NYSE** y **0.368 operaciones por sesión**.

## Potencia

| Escenario | n necesario | Fecha estimada |
|---|---:|---|
| Expectativa real 0, cota superior < +0.3104 R | **237** | 2029-06-11 |
| Expectativa real 0.10 R, cota superior < +0.3104 R | **515** | 2032-06-14 |

`n = ⌈(2.49 × sd / distancia)²⌉`, con sd = 1.9173. La fecha usa el ritmo del backtest y el calendario NYSE; es una estimación, no un compromiso.

## Regla fijada ahora

- El rendimiento del forward se mira **solo** en los puntos de control n ∈ {30, 60, 515}. El punto final es **N = 515** (el mayor de 237 y 515, para cubrir también el escenario de 0.10 R).
- En cada punto se informan la media de R y su IC95 con **bootstrap semanal** (semanas ISO remuestreadas con reemplazo, 10.000 réplicas, semilla 42).
- **Alerta de deriva** si la cota superior del IC95 < +0.10 R.
- **Compatible con el backtest** si el IC95 contiene +0.3104 R.
- Cualquier otro caso: **indeterminado**.
- Ninguna alerta cambia el EA ni el riesgo: decide el operador.

Puntos de control y fechas estimadas:

| n | Fecha estimada |
|---:|---|
| 30 | 2027-03-16 |
| 60 | 2027-07-13 |
| 515 | 2032-06-14 |

El n = 237 (escenario de expectativa 0) queda como hito intermedio de potencia, pero **no** es un punto de control: no se mira.

## `drift.py`

`drift.lane_specs()` incluye el carril `us100-ftmo1` y `drift.build_lane_drift()` ya compara demo contra el backtest congelado (operaciones, emparejamiento y slippage) en solo lectura. Es el monitor operativo existente; **no** implementa estos puntos de control ni el bootstrap semanal, así que D5 añade solo la regla de potencia y no duplica el emparejamiento ni el slippage.

## Límites

- No se calcula el rendimiento del forward; solo el número y las fechas.
- No se toca el EA, el setfile, `ea_forward.py` ni el forward.
- El plan no suma al contador y no ejecuta ninguna evaluación.
