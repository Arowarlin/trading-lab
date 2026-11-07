# Calendario macro (CSV)

`events.csv` es una **plantilla de estructura**, no una fuente de verdad.
La fila `1,USD,FOMC,...` es un ejemplo y **no** afirma que ese evento esté
programado.

- `scheduled_at_utc`: ISO 8601 en UTC, con `Z` o `+00:00`.
- `impact`: `low`, `medium` o `high`.
- `blackout_before_min` / `blackout_after_min`: ventana por evento; si están
  vacíos se usan los minutos globales del guard.
- `source_url`: enlace oficial del proveedor.

Cuando se conecte Finnhub/FRED, este CSV puede servir como fixture o importarse
a `macro_events`; no se activa ningún bot por leerlo.
