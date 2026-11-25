# Requisitos del dataset

## Partición (aprobada por el operador el 2026-11-25)

| Tramo | Fechas | Regla |
|---|---|---|
| DEV | 2010-06 → 2021-12 | descriptivas, reglas, ablación |
| OOS-1 | 2022-01 → 2023-12 | selección entre las 22 variantes preregistradas |
| **OOS-2 sellado** | **2024-01-01 → 2026-11-20** | una lectura por configuración final; ni descriptivas ni gráficos |

Huella de los ficheros fuente en el momento del sellado: `SEAL.md`.

## Mínimos por serie

1. **Zona horaria.** Índice en UTC en la caché; todo cálculo se hace en
   `America/New_York`. La barra se etiqueta por su hora de **apertura**.
   Comprobado con el pico de volumen de las 9:30 en horario de verano y en
   horario estándar (`Data_Quality.md`).
2. **Sesión RTH válida.** ≥ 380 de las 390 barras de 9:30 a 15:59 y última barra ≥ 15:55. Si no, la sesión se excluye y se cuenta.
3. **Medias sesiones** (cierre ≤ 13:15): excluidas de las descriptivas y contadas aparte.
4. **Roll NQ.c.0.** Se excluye la ventana fija de cada trimestre: del 3er viernes − 9 días al 3er viernes + 1. A eso se suman los saltos detectados a las 18:00 ET. Los niveles PDH/PDL no se usan si la víspera está excluida.
5. **ATR diario** sobre H/L/C de RTH, con dato de la **víspera** (sin futuro).
6. **Overnight** (ONH/ONL): de 18:00 ET de la víspera hábil a 09:29 ET; mínimo 60 barras.
7. **Noticias:** `news_calendar_history.csv`.
   - Fecha de primera publicación ALFRED (`output_type=4`) para CPI, NFP, PPI, PCE, GDP (avance), Retail Sales y JOLTS.
   - Fechas FOMC de federalreserve.gov.
   - Sin hora para FOMC antes de 2013, porque la hora del comunicado cambió.
8. **Costes:** comisión por contrato como input obligatorio; slippage base de 1 tick por lado y estrés de 2 y 4 ticks.
9. **Volumen:** solo NQ (CME) para RVOL y perfil. El tick volume de Dukascopy se marca como proxy y no se usa para el modelo E.
