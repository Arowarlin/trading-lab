# TL3 · Auditoría de datos y costes

Solo lectura. Leyenda en `TL3_FORENSIC_AUDIT.md`. Los CFD y los futuros se tratan por separado: **US100
(CFD de FTMO/FundingPips) no es NQ (futuro CME)**, y ningún resultado de uno es evidencia del otro.

## 1. Inventario de fuentes

| Fuente | Ubicación | Instrumentos | Periodo | BID/ASK | Uso actual | Etiqueta |
|---|---|---|---|---|---|---|
| MT5 FTMO (attach-only) | `data/cache/mt5/*_H1/H4/M15`, `data/cache/ea/US100_CASH_M5_NY.parquet` | ~40 CFD | Variable; US100 M5 desde **2021-09-14** | BID + `spread` por barra | EA, snapshots de Discovery M5 | [HECHO] |
| Dukascopy M1 | `data/cache/dukascopy/*_M1.parquet` (899 MB) | US100, US500, US30, XAUUSD, EURUSD, GBPUSD, USDJPY | 2003/2011 → 2026-11-20 | **Solo BID**: `ask_*` vacío salvo EURUSD 2021-09 → 2024-03 | Discovery H1/H4/D1 | [HECHO] |
| Databento GLBX OHLCV | `data/cache/databento/*` | NQ, ES, YM, GC, 6E, 6B, 6J **guardados como US100, US500, US30, XAUUSD, EURUSD…** | H1 2010-06 → 2026-11; NQ M1 descargándose | Sin bid/ask; sin contrato por fila | T31, R9 informal, NQ-B | [HECHO] |
| Yahoo (`*_F`, ETF, acciones) | `data/cache/*.parquet` | Acciones/ETF, ES_F, GC_F, CL_F | Diario | No | Carril archivado | [HECHO] |
| `broker_spreads` (lab.db) | — | 8 símbolos FTMO + 6 FundingPips | **1 semana** (FTMO, 2026-11-12 → 19) y **1 día** (CFD-006, 2026-11-19 → 20) | — | Coste de Discovery | [HECHO] |
| `tca` / `fills` | lab.db | Demo FTMO | 2026-11 | Precio de orden = fill en 58/58 filas | Slippage | [DOC] `RESULTADO-T12.md` |

## 2. CFD

### 2.1 US100 (CFD)

| Aspecto | Estado | Evidencia |
|---|---|---|
| OHLC M5 del bróker | **Bueno desde 2021-09-14.** 2018-2020 son velas D1 y ene-sep 2021 son H1, mezcladas en el mismo archivo | [HECHO] paso dominante por año (`tl3_regimen_ea.py`); `ea_us100_m5_only.md §1` |
| Duplicados / OHLC inválidos | 0 / 0 en M5 | [DOC] `ea_us100_m5_only.md` |
| Huecos | 205 huecos no programados (0,053 %) | [HECHO] `disc_campaigns.quality_json` |
| Zona horaria / DST | El EA trabaja en hora NY sin zona (`ny_offset_h=0`); caché ya convertida. Las pausas de 16:50 local aparecen como "informativas" (1.020) | [HECHO] |
| Spread | Por barra desde MT5 (EA). En Discovery, mediana horaria de **una semana** de 2026 | [HECHO] |
| Historia larga | Dukascopy US100 M1 desde 2011-09, **solo BID** | [HECHO] |
| Comisión | 0 en índices FTMO ("Zero Commissions on Indices", 2025-08-04) | [DOC] `costs.yaml` |
| Slippage | Supuesto: **0,5 pt/lado en el motor del EA** y **1,0 pt/lado en Discovery** (`costs.yaml`, copiado de `ai_trader.yaml`). Dos supuestos distintos para el mismo símbolo | [HECHO] |
| Swap | Medido el 2026-11-23 y aplicado a toda la historia | [DOC] TL2 P1-3; `swap.yaml` |

**Riesgo de mezcla [HECHO]:** el mismo archivo de caché del EA contiene D1, H1 y M5. El motor no detecta
la granularidad (`ea_us100_m5_only.md`). Ya rompió una prueba (NQ-B, ver `TL3_FORENSIC_AUDIT.md` G-1).

### 2.2 US500 y US30 (CFD)
- [HECHO] `costs.yaml`, CFD-001: spread, p75 y slippage **null** ("Sin datos"). Los costes de US500 en
  Discovery vienen de CFD-006 (FundingPips, `SPX500`), con 1 día de medición.
- [HECHO] Coste medio de `r9b-tom-us500-d1`: 0,047 R frente a 0,009 R en US100. El coste de US500 es
  5 veces mayor por una medición de un solo día en otra firma. **El resultado de US500 depende de un
  dato frágil.**
- [DOC] La prueba fuera de instrumento del EA usó el spread por barra de MT5 FTMO (`fuera-de-instrumento.md`).

### 2.3 XAUUSD (CFD)
- [HECHO] Dukascopy desde 2003, solo BID. Spread de 1 semana (FTMO) y 1 día (FundingPips).
- [HECHO] Slippage supuesto de 0,15 USD/lado, también copiado de `ai_trader.yaml`.

### 2.4 Forex (EURUSD, GBPUSD, USDJPY)
- [HECHO] Única serie con ASK histórico real: EURUSD 2021-09 → 2024-03. Muestra que el spread nocturno
  de 17:00 ET (1,8 bps medio en 2021) es 6–7 veces el diurno (`spread-historico.md`). Por eso un spread
  medio por hora de 2026 no sirve para 2010–2020.
- [HECHO] Slippage supuesto: 0,5 pip/lado en EURUSD y GBPUSD (`costs.yaml`), sin medición.
  El slippage de ida y vuelta (1,0 pip) es mayor que el spread mediano.

## 3. Futuros (NQ, MNQ, ES, MES, GC, MGC…)

| Requisito para investigar NQ/MNQ de forma profesional | Estado | Evidencia |
|---|---|---|
| Datos por **contrato** (`raw_symbol`, `instrument_id`) | **No.** Solo continuo `c.0` sin columna de contrato | [HECHO] `fetch_databento.py`, columnas `open, high, low, close, volume` |
| Regla de roll explícita (volumen u OI, fecha) | **No.** `roll="c"` (calendario) y detección posterior por salto > 5σ | [HECHO] `futures_roll.py:24,35-70` |
| Detección de rolls completa | **No.** NQ 2010-06 → 2026-11 (~66 vencimientos trimestrales): **17 detectados**. ES: 23. GC vence en meses pares (feb, abr, jun, ago, oct, dic), pero el detector solo mira **mar/jun/sep/dic**: 14 detectados | [HECHO] `reports/discovery/futuros-roll.md`; [INFERENCIA] el resto de rolls queda como retorno falso |
| Sesión CME (18:00–17:00 ET, pausa diaria, festivos CME) | Calendario CME existe (`discovery/calendars.py`) | [DOC] TL2 |
| Bid/ask o spread | **No** (OHLCV). Para NQ el tick es 0,25 pt; el spread típico es 1 tick en RTH | [HECHO] / [INFERENCIA] |
| Comisiones reales (Topstep/ProjectX/Apex) | "Pendientes de verificar" | [DOC] TL2 Q10 |
| Volumen por contrato | Sí en OHLCV, pero mezclado entre contratos en el continuo | [HECHO] |
| MNQ separado de NQ | **No hay** datos MNQ | [HECHO] |
| Nombres propios | **No.** NQ se guarda como `US100_*` | [HECHO] G-2 |
| Ejecución simulada de futuros | `fastbt` suma `2·fut_price/riesgo` como comisión | [DOC] `RESULTADO-T10.md` |

**Conclusión [INFERENCIA]:** hoy no se puede hacer investigación profesional con NQ/MNQ. Falta:
(1) descargar por contrato o con `stype_in=continuous` guardando `instrument_id`; (2) regla de roll por
volumen fijada antes de mirar resultados; (3) tabla de vencimientos y especificaciones por raíz
(multiplicador, tick, tick value, horario); (4) comisiones verificadas por firma; (5) nombres de
archivo propios; (6) un test que impida cargar un archivo de futuros como CFD.

## 4. Modelo de costes

### 4.1 Clasificación de cada componente

| Componente | US100 | US500/US30 | XAUUSD | FX | Futuros |
|---|---|---|---|---|---|
| Spread | **Observado** (MT5 por barra, 2021+) en el EA; **estimado** (1 semana de 2026) en Discovery | **Insuficiente** (1 día, otra firma) / **ausente** en FTMO | **Estimado** (1 semana) | **Observado** EURUSD 2021-24; **estimado** el resto | **Ausente** |
| Comisión | Observada (0 FTMO) | Por defecto | Documentada | Documentada (FTMO; FundingPips por lote, `round_turn`) | **Ausente** |
| Slippage | **Por defecto** (0,5 EA / 1,0 Discovery) | **Ausente** | **Por defecto** | **Por defecto** | **Ausente** |
| Swap | Estimado (2026 → historia) | Estimado | Estimado | Estimado | No aplica |

### 4.2 Bruto → neto con los datos que existen

**Discovery** (medianas IS, [REPRODUCIDO]). El sistema guarda bruto y coste total, **no** la
descomposición por componente en `metrics_json`: spread, comisión y slippage por separado son
**Sin datos** para las campañas ya ejecutadas.

| Campaña (coste) | Bruto | Coste total | Neto | Coste / bruto |
|---|---:|---:|---:|---:|
| Fix EURUSD (v1) | +0,023 | 0,036 | −0,013 | 1,54 |
| Fix cesta EUR+GBP (**v2**) | +0,019 | 0,032 | −0,017 | 1,65 |
| Donchian XAUUSD H4 (v1) | +0,042 | 0,031 | +0,014 | 0,73 |
| Cambio de mes US100 (v1) | +0,060 | 0,009 | +0,049 | 0,15 |
| Cambio de mes US500 (v1) | +0,082 | 0,047 | +0,039 | 0,58 |
| Rebote US100 (v1) | +0,150 | 0,010 | +0,136 | 0,07 |
| Momentum intradía US100 M5 v2 (v1) | Sin datos | 0,064 | −0,078 | — |
| NY open GA US100 M5 (v1) | Sin datos | 0,049 | −0,003 | — |

**EA `us100-ftmo1`** ([DOC] `us100-ftmo1-v2.md §3`):

| Escenario | Expectativa | Δ |
|---|---:|---:|
| Spread por barra, slippage 0 | +0,3396 R | — |
| + slippage 0,5 pt/lado (actual) | +0,3104 R | −0,029 |
| + slippage 2 pt/lado | +0,2517 R | −0,088 |
| Slippage de equilibrio | ≈ 8,9 pt/lado | — |
| Comisión | 0 | 0 |
| Bruto sin spread | **Sin datos** (exige ejecutar el motor con spread 0, `counted=0`) | — |

### 4.3 Lectura

- **[REPRODUCIDO]** El coste importa sobre todo donde la operación es corta y frecuente: US100 M5
  (0,05–0,095 R) y FX H1 (0,03–0,05 R). En D1 es pequeño (0,01 R en US100).
- **[INFERENCIA]** En el fix, el paso de v1 a v2 baja el coste ~12 % (0,036 → 0,032). **El doble spread
  no fue la causa del fracaso del fix**; el bruto es demasiado pequeño.
- **[INFERENCIA]** Para el EA, el coste no es el riesgo principal (aguanta ~9 pt/lado). Su riesgo es
  estadístico (ver `TL3_US100_CASE_STUDY.md`).
- **[HECHO]** El slippage está **sin medir en todos los mercados**. Las 58 filas de TCA tienen
  `order_px == fill_px`, y MT5 guarda `price_open = 0` en las entradas a mercado (`RESULTADO-C4.md`).
  La medición válida solo empezará con los campos `bid/ask/requested_price` añadidos en C4.

## 5. Recomendaciones

| # | Recomendación | Prioridad | Impacto |
|---|---|---|---|
| D1 | Separar la caché del EA por granularidad (`US100_CASH_M5_NY.parquet` solo M5) o marcar `usable_from=2021-09-14` en el cargador. En **copia nueva**, sin tocar la original | P0 | Evita pruebas rotas como NQ-B |
| D2 | Renombrar la caché de futuros por raíz (`NQ_c0_M1`), con `raw_symbol` y manifiesto de descarga; test que impida cargar futuros como CFD | P0 | Elimina la confusión CFD ↔ futuro |
| D3 | Rehacer el roll: descarga con `instrument_id` o roll por volumen; tabla de vencimientos por raíz (GC en meses pares) | P1 | Futuros D1/H4 utilizables |
| D4 | Medir el spread durante ≥ 4 semanas por firma antes de usarlo como coste. US500/US30 en FTMO hoy es "Sin datos" | P1 | Costes de índices fiables |
| D5 | Guardar en `metrics_json` la descomposición `spread_r`, `slip_r`, `comm_r`, `swap_r` (ya existe por operación en v2) | P1 | Informe bruto → neto por componente |
| D6 | Un solo supuesto de slippage por símbolo, compartido por el motor del EA y Discovery, hasta tener ≥ 30 fills medidos | P2 | Coherencia |
| D7 | No comprar más datos de pago hasta tener D1–D3. Dukascopy BID M1 de US100 (2011+) ya permite una prueba fuera de periodo del EA con spread modelado | P1 | Ahorro y mejor prueba |
