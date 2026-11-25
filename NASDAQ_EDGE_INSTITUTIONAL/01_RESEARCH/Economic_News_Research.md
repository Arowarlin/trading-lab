# Noticias económicas · calendario, clasificación y News Protection

Consulta: 2026-11-25. Todas las horas en ET salvo indicación.

## 1. Calendario oficial verificado

| Evento | Hora | Próximas fechas | Fuente |
|---|---|---|---|
| CPI / Core CPI | 08:30 | 2026-12-10; 2027: 01-13, 02-11, 03-10, 04-13, 05-12, 06-10, 07-14, 08-11, 09-14, 10-14, 11-10, 12-10 | bls.gov/schedule/news_release/cpi.htm |
| Employment Situation (NFP, desempleo) | 08:30 | 2026-12-04; 2027: 01-08, 02-05, 03-05, 04-02, 05-07, 06-04, 07-02, 08-06, 09-03, 10-08, 11-05, 12-03 | bls.gov/…/empsit.htm |
| PPI / Core PPI | 08:30 | 2026-12-15; 2027: 01-14, 02-12, 03-12, 04-14, 05-13, 06-11, 07-15, 08-10, 09-10, 10-15, 11-12, 12-15 | bls.gov/…/ppi.htm |
| JOLTS | 10:00 | 2026-12-01; 2027: 01-05, 02-02, 03-09, 03-30, 05-04, 06-02, 06-29, 08-03, 08-31, 10-05, 11-02, 12-01 | bls.gov/…/jolts.htm |
| GDP | 08:30 | 2026-12-23 (3ª Q3); 2027: 01-28, 02-25, 03-31, 04-29, 05-27, 06-25, 07-29, 08-25, 09-30, 10-28, 11-24, 12-22 | bea.gov/news/schedule (+ /next-year) |
| PCE / Core PCE (Personal Income & Outlays) | 08:30 | 2026-12-23; 2027: mismas fechas que GDP | ídem |
| Retail Sales (avance) | 08:30 | 2026-12-16; 2027: 01-15, 02-17, 03-16, 04-16, 05-14, 06-16, 07-16, 08-16, 09-16, 10-15, 11-16, 12-15 | census.gov/economic-indicators/calendar-listview.html |
| FOMC | comunicado 14:00, rueda de prensa 14:30 (horas según Topstep: 13:00 y 13:30 CT) | 2026-12-08/09 (con SEP); 2027: 01-26/27, 03-16/17, 04-27/28, 06-08/09, 07-27/28, 09-14/15, 10-26/27, 11-16/17 | federalreserve.gov/monetarypolicy/fomccalendars.htm (actualizada el 2026-11-18) |
| ISM Manufacturing / Services | **Sin datos** (ismworld.org pide login) | Sin datos | — |
| Initial Jobless Claims | **Sin datos** (el PDF del DOL no fue legible) | Sin datos | — |
| Subastas del Tesoro | **Sin datos** (treasurydirect.gov no consultado) | Sin datos | — |
| Discursos de Powell / eventos extraordinarios de la Fed | no programables con antelación fija | carga manual | federalreserve.gov/newsevents/calendar |

Notas:
- Las páginas de BLS, BEA y Census dan la hora sin zona en el texto leído. Se
  asume ET porque es la práctica conocida de esas agencias, y lo confirma la
  tabla de Topstep: CPI/NFP/PPI a las 7:30 CT [OFICIAL Topstep].
- La Fed marca las fechas de 2027 como tentativas hasta su confirmación.
- BLS publica un iCal: https://www.bls.gov/schedule/news_release/bls.ics. Es una
  fuente apta para generar la tabla automáticamente.
- El laboratorio ya tiene `tradinglab.intel.fred.FredCalendarProvider` (CPI y
  NFP por FRED) y `data/calendar/events.csv`. Se reutilizan; no se duplican.

## 2. Clasificación interna (de este sistema, no de las firmas)

| Tier | Eventos | Motivo | Bloqueo inicial |
|---|---|---|---|
| **1** | CPI, NFP, FOMC (comunicado y rueda de prensa), PPI | Topstep restringe aperturas en estos cinco [OFICIAL]; mayor impacto conocido [HIPÓTESIS hasta medirlo] | −15 / +15 min |
| **2** | PCE, GDP avance, Retail Sales, ISM Manufacturing, ISM Services, JOLTS, Powell (discursos con fecha) | macro de primer orden sin restricción de firma [HIPÓTESIS] | −10 / +10 min |
| **3** | GDP 2ª/3ª estimación, Jobless Claims, subastas del Tesoro (10 y 30 años) | impacto moderado [HIPÓTESIS] | exigir confirmación extra y reducir el riesgo al 50 % |
| **4** | resto | — | sin bloqueo |

La clasificación es **provisional**. La Fase B mide en M1, por evento y por año,
sobre el periodo de desarrollo:
- rango de los 15 min previos frente a la mediana de días sin noticias;
- rango de 0 a +5, +15 y +30 min;
- expansión frente al ATR;
- proporción de vuelos falsos: dirección inicial a +5 min frente a dirección a +60 min;
- minutos hasta que el rango de 5 min vuelve a menos de 1,5× la mediana normal;
- slippage proxy: high−low de la vela M1 de publicación, en ticks.

Un evento sube o baja de tier solo con esa medición. Los resultados no se
inventan; mientras no existan, el informe dice **Sin datos**.

## 3. Arquitectura de News Protection en TradingView

### 3.1 Qué puede y qué no puede hacer Pine v6

Fuentes: tradingview.com/pine-script-docs (other-timeframes-and-data, limitations, time).

- **No existe** una función que lea un calendario económico externo ni que haga
  peticiones HTTP.
- `request.economic(país, campo)` devuelve **valores** de una serie (por ejemplo
  GDPQQ), no las fechas de publicación futuras.
- `request.seed()` sigue documentado, pero "la creación de nuevos repositorios
  Pine Seeds no está disponible actualmente". No es una vía fiable.
- Límites: 40 peticiones `request.*` únicas (64 en Ultimate); 64 plots; 9 tablas.
- `timestamp("America/New_York", y, m, d, h, min)` gestiona el DST
  automáticamente.

### 3.2 Diseño viable

1. **Tabla embebida generada fuera de Pine.** Un comando del laboratorio (por
   ejemplo `lab news pine-table`, a crear en la Fase E) lee las fuentes
   oficiales: BLS iCal, BEA, Census, Fed y la carga manual de Powell/ISM/Claims.
   Con ellas escribe un bloque Pine:

   ```pine
   // GENERATED 2026-11-25 · valid_until 2027-03-31 · sources: bls.ics, bea, census, fomc
   var int   CAL_VALID_UNTIL = timestamp("America/New_York", 2027, 3, 31, 23, 59)
   var array<int>    EV_T   = array.from(timestamp("America/New_York",2026,12,4,8,30), ...)
   var array<int>    EV_TIER= array.from(1, ...)
   var array<string> EV_NAME= array.from("NFP", ...)
   ```

   El usuario pega el bloque nuevo en el indicador (o lo actualiza con la versión
   publicada) cada trimestre.
2. **Validez explícita.**
   - Si `time > CAL_VALID_UNTIL`, el estado es **NEWS DATA STALE** y todas las
     señales pasan a **NO TRADE**.
   - Si la tabla está vacía, el estado es **NEWS UNVERIFIED**.
   - **NEWS CLEAR** solo se muestra si el calendario es válido y no hay ningún
     evento Tier 1–2 dentro de su ventana.
3. **Eventos manuales.** Hasta 5 `input.time` para Powell o eventos
   extraordinarios, cada uno con su tier.
4. **Cuenta atrás** hasta el próximo evento Tier 1–2, con su nombre, en el
   dashboard.
5. **Ventanas configurables** por tier (inputs). Por defecto:
   - Tier 1: 15/15;
   - Tier 2: 10/10;
   - Tier 3: reducir riesgo y exigir confirmación;
   - Tier 4: sin bloqueo.
6. **Capa de firma.** Si el perfil es Topstep, la ventana de la firma (±5 min,
   NQ bloqueado, MNQ ≤ 3) se aplica **además** de la interna. Gana la más
   estricta.
7. Razón del bloqueo visible: `NO TRADE · CPI 08:30 en 12 min (Tier 1)`.

Limitación declarada: si un evento cambia de fecha (por ejemplo por un cierre
del gobierno), la tabla embebida no lo sabe. El usuario debe regenerarla. El
manual lo dice explícitamente.

## 4. Medición DEV de eventos (Fase B, 2026-11-25)

**Muestra**
- NQ CME M1, 2010-06 → 2018-12.
- Calendario: `02_DATA/news_calendar_history.csv` (primera publicación ALFRED y
  fechas de la Fed).
- Base de comparación: días sin ningún evento del calendario.

**Métrica:** rango mediano de cada bloque de 5 min dividido por el mismo bloque
en la base.

| Evento | Días | −5 min | 0–5 | +5–10 | +10–15 | +15–20 | +20–25 | Vuelve a < 1,5× base | Dirección 0–5 min = dirección 0–60 min |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| Tier 1 08:30 (CPI, NFP, PPI) | 306 | 1,19 | **2,80** | 1,67 | 1,62 | 1,50 | 1,38 | a los ~20 min | 74,5 % [69,1–79,2] (n = 286) |
| Tier 2 08:30 (PCE, GDP avance, Retail Sales) | 237 | 1,00 | 1,90 | 1,33 | 1,25 | 1,25 | 1,25 | a los ~5 min | 63,4 % [56,8–69,6] |
| JOLTS 10:00 | 99 | 1,05 | 1,00 | 1,00 | 1,00 | 1,10 | 1,05 | sin efecto medible | 59,2 % [49,3–68,4] |
| FOMC 14:00 | 69 | 1,25 | **4,69** | 3,00 | 2,38 | 2,62 | 2,31 | **no vuelve en 60 min** (+55 min: 1,54) | 66,7 % [54,7–76,8] |

Dukascopy 2012–2021 reproduce el patrón: Tier 1 2,62× → < 1,5 a los ~20 min;
FOMC 4,18× y > 1,5 durante 60 min; JOLTS sin efecto.

Limitaciones:
- En 2010–2012, varias reuniones FOMC de un solo día publicaron antes de las
  14:00. Su efecto queda fuera de la ventana y diluye la media.
- ISM y Jobless Claims no se midieron (no hay calendario histórico oficial
  abierto).
- El slippage real no se mide con barras M1. El proxy es el rango del bloque
  0–5: Tier 1 NQ mediana de 7,0 pt frente a 2,0 pt en la base; FOMC 15,3 pt.

### Ajustes de la clasificación por la medición (defaults de la V1)

| Cambio | Antes | Después | Motivo medido |
|---|---|---|---|
| Post-ventana Tier 1 a las 08:30 | +15 min | **+20 min** | ratio 1,50 a +15 y 1,38 a +20 |
| Post-ventana FOMC | +15 min | **+60 min**; sin nuevas entradas el resto de la sesión por defecto (configurable) | > 1,5× durante 60 min |
| JOLTS | Tier 2 | **Tier 3** | sin efecto medible |
| Tier 2 a las 08:30 | ±10 min | ±10 min (se mantiene) | vuelve a ~1,3× a los 5 min |

Las publicaciones de las 08:30 ocurren antes de la apertura. Su principal
efecto sobre una ventana de entrada que empieza a las 9:35 es indirecto: amplían
el pre-market. El OR posterior no difiere de forma medible: la continuación del
OR15 es del 17,8 % en días Tier 1 frente al 16,4 % sin noticias.
