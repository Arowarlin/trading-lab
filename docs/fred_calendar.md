# FRED y calendario macro · verificación 2026-11-07

Implementación: `tradinglab.intel.fred.FredCalendarProvider`, detrás de la
interfaz `CalendarProvider` existente. La clave se lee de keyring/.env y nunca
se imprime ni se guarda en caché.

## Descubrimiento de releases

Consultado `GET /fred/releases?search_text=...` el 2026-11-07:

| Release | ID | Búsqueda |
|---|---:|---|
| Consumer Price Index | **10** | `Consumer Price Index` |
| Employment Situation (NFP) | **50** | `Employment Situation` |

Los IDs no están codificados a mano: el proveedor consulta FRED por nombre y
hace match exacto (case-insensitive). Si no encuentra el release, devuelve error
y no inventa un ID.

## Fechas futuras

Consultado `GET /fred/release/dates?release_id=...&include_release_dates_with_no_data=true`
para 2026-01-01 → 2027-12-31:

| Release | Con flag | Sin flag |
|---|---|---|
| CPI (10) | 12 fechas; futuras 2026-11-10 y 2026-12-10 | 10 fechas; 0 futuras |
| NFP (50) | 12 fechas; futura 2026-12-04 | 11 fechas; 0 futuras |

Conclusión: **sin** `include_release_dates_with_no_data=true`, FRED omite las
fechas programadas que aún no tienen datos. El proveedor siempre envía el flag.

## Limitación de hora

FRED devuelve solo `{"release_id": ..., "date": "YYYY-MM-DD"}`. No hay hora ni
zona horaria. Para que el guard tenga una ventana operativa, el proveedor usa
la convención **08:30 America/New_York** (hora habitual de CPI/NFP) y la
convierte a UTC con `tzdata`. Es una convención documentada, **no un dato de
FRED**; verifica la hora oficial antes de operar.

## Persistencia y seguridad

- Eventos en `macro_events` con `importance="high"` y `source="fred:<id>"`.
- Deduplicación por `(event, ts_utc, source)`.
- Caché JSON en `data/cache/fred/` durante 12 h; la caché no contiene la API key.
- Rate limit de 0,6 s entre peticiones (100/min; FRED permite 120/min).
- Si FRED falla, se registra `calendar_fetches.status="stale"` y se devuelven
  los eventos ya guardados. Sin eventos guardados también es `stale` con cero
  eventos; nunca se interpreta como “sin eventos”.
- El guard lee el último fetch de cualquier proveedor, de modo que un fallo de
  FRED no queda oculto por un fetch manual antiguo.

## FOMC manual

FOMC no se ingesta desde FRED en esta fase. Se copia del calendario oficial:

<https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm>

y se inserta con:

```powershell
lab intel event FOMC --at 2026-12-09T19:00:00+00:00
```
