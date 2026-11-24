# RESULTADO · R2g-fix — huecos de fin de semana por calendario

Fecha: 2026-11-22. Sin campañas, sin OOS-1/OOS-2, sin push.

## Hecho

- Revertido y verificado `_GAP_RULES["D1"] = (1.5, 72.0)` y su test.
- Nuevo clasificador de huecos por sesiones NY en `data_quality._calendar_gap`.
- Medición corregida: del **cierre** de la vela anterior a la **apertura** de la siguiente.
- Tests nuevos de fin de semana normal/DST, miércoles perdido, viernes→lunes,
  jueves→domingo, sesión H4 perdida y Año Nuevo forex.
- `PLAN.md`: total M1 corregido a **46.851.600**.
- Commit `cb5417d` · `tl2: R2g - huecos de fin de semana por calendario`.
- Tag nuevo `tl2-r2g-fix`; `tl2-r2g` no se ha movido.

## 1. Regla implementada (sin tocar umbrales)

- Un hueco se mide desde `cierre = inicio_vieja + TF` hasta `inicio_nueva`.
- Se enumeran las sesiones NY 17:00→17:00 que caen dentro del hueco.
- Es **programado** solo si todas las sesiones que faltan son sábado/domingo o
  festivo (NYSE para índices; 25-dic y 1-ene para forex/oro). Tolerancia ±1 h
  en los bordes por DST.
- Si falta al menos una sesión de lunes a viernes no festiva, es **real**.
- Una sesión completa perdida se detecta aunque el hueco cierre→apertura sea de
  24 h (caso del miércoles en D1). No se cambió `gap_factor`, `max_gap_hours`,
  `scheduled_gap_share` ni `fail_if_gap_pct_gt`.

## 2. Antes / después de D1 (ventana 2021-09 → 2026-11-20)

| Símbolo | Antes (72, sin calendario) | Después (72 + calendario) |
|---|---|---|
| US100 | FAIL · 7 huecos (71 h DST + Año Nuevo) | **OK · 0 huecos reales** |
| US500 | FAIL · 7 | **OK · 0** |
| US30 | FAIL · 7 | **OK · 0** |
| XAUUSD | FAIL · 9 | **FAIL · 8** (24-dic, Good Friday, 2-ene) |
| EURUSD | FAIL · 7 | **WARN · 0** |
| GBPUSD | FAIL · 7 | **WARN · 0** |
| USDJPY | FAIL · 7 | **WARN · 0** |

Los 8 huecos de XAUUSD son: `2021-12-23`, `2022-04-14`, `2022-12-23`,
`2022-12-30`, `2023-04-06`, `2024-03-28`, `2025-04-17`, `2026-04-02`. Son
Nochebuena/Good Friday/2-ene, festivos de oro/forex que la regla del operador no
incluye (solo 25-dic y 1-ene). No se tocan umbrales.

## 3. Data-check --all-tf (historia completa)

Cada celda: **estado · inicio útil · huecos reales**.

| Símbolo | M1 | M5 | M15 | M30 | H1 | H4 | D1 |
|---|---|---|---|---|---|---|---|
| US100 | WARN · 2013-11-01 · 2857 | WARN · 2013-11-01 · 414 | WARN · 2013-11-01 · 21 | WARN · 2013-11-01 · 11 | FAIL · 2013-11-01 · 870 | FAIL · 2013-06-02 · 814 | WARN · 2013-06-02 · 8 |
| US500 | WARN · 2013-11-01 · 8949 | WARN · 2013-11-01 · 454 | WARN · 2013-11-01 · 36 | WARN · 2013-11-01 · 14 | FAIL · 2013-11-01 · 872 | FAIL · 2013-06-02 · 814 | FAIL · 2013-06-02 · 18 |
| US30 | WARN · 2013-11-01 · 2018 | WARN · 2013-11-01 · 360 | WARN · 2013-11-01 · 18 | WARN · 2013-11-01 · 8 | FAIL · 2013-11-01 · 867 | FAIL · 2013-09-30 · 806 | WARN · 2013-09-29 · 9 |
| XAUUSD | WARN · 2003-12-01 · 26549 | WARN · 2003-05-05 · 2417 | WARN · 2003-05-05 · 122 | WARN · 2003-05-05 · 45 | WARN · 2003-05-05 · 171 | WARN · 2003-05-04 · 28 | WARN · 2003-05-04 · 17 |
| EURUSD | WARN · 2003-05-04 · 597 | WARN · 2003-05-04 · 35 | WARN · 2003-05-04 · 6 | WARN · 2003-05-04 · 1 | WARN · 2003-05-04 · 3 | WARN · 2003-05-04 · 0 | WARN · 2003-05-04 · 0 |
| GBPUSD | WARN · 2003-05-04 · 840 | WARN · 2003-05-04 · 36 | WARN · 2003-05-04 · 8 | WARN · 2003-05-04 · 3 | WARN · 2003-05-04 · 3 | WARN · 2003-05-04 · 0 | WARN · 2003-05-04 · 0 |
| USDJPY | WARN · 2003-05-04 · 701 | WARN · 2003-05-04 · 33 | WARN · 2003-05-04 · 7 | WARN · 2003-05-04 · 1 | WARN · 2003-05-04 · 4 | WARN · 2003-05-04 · 2 | WARN · 2003-05-04 · 0 |

### FAIL que quedan y causa concreta

- **US100/US500/US30 H1 y H4**: 806–872 huecos reales cada uno. Dukascopy corta
  sistemáticamente las velas H1/H4 de los viernes antes de las 17:00 NY. Muestras
  H1: `2013-11-01`, `2013-11-08`, `2013-11-15`, `2013-11-22`, `2013-11-28`;
  muestras H4: `2013-06-03`, `2013-08-09`, `2013-08-26`, `2013-09-27`,
  `2013-09-30`. Falta una parte de la sesión del viernes, así que la regla los
  considera reales.
- **US500 D1**: 18 huecos, todos de 2013–2016, fuera de la cobertura del
  `nyse_calendar` (2021–2027): `2013-10-01`, `2013-10-11`, `2013-10-24`,
  `2014-02-05`, `2015-02-20`, `2016-03-01`… La ventana 2021-09→2026-11 está OK.
- **XAUUSD D1**: en la ventana 2021-09→2026-11 da FAIL por los 8 festivos de
  Nochebuena/Good Friday/2-ene ya listados; en la historia completa da WARN
  (17 huecos, 0,28 % < 0,5 %).

No se ha cambiado ningún umbral para ocultar estos FAIL.

## 4. PLAN.md

Corregido el total de filas M1 de 49,7 M a **46.851.600** (suma real de los 7
símbolos). Añadida la fila R2g-fix.

## 5. Cierre

`git status --short`:

```text
?? tl2-edge-map.patch
```

`git log --oneline -5`:

```text
cb5417d tl2: R2g - huecos de fin de semana por calendario
1886c20 orquestador: protocolo de relevo por archivos
f9666ef tl2: R2g - revertir umbral D1
e85b75f tl2: R2g - cierre e historia completa
1b260cb tl2: R2g - cierre e historia completa
```

- `pytest -q`: **1532 passed, 1 skipped** (866,93 s; 1 warning de psutil ausente).
- `ruff check src/tradinglab/discovery tests`: **limpio**.
- `lab propfund verify`: **OK** en ai_trader, ea_us100_ftmo1, ftmo_forward y ftmo_risk.
- `count_tests`: **1676**.
- Tag `tl2-r2g-fix` → `cb5417d`. `tl2-r2g` no se ha movido.

## Aviso

- Los H1/H4 de índices y el D1 de US500 siguen en FAIL por la fuente/cobertura
  antigua, no por la regla de fin de semana. Fechas arriba.
- XAUUSD D1 sigue en FAIL en la ventana por festivos que la regla no cubre.
- No se ejecutaron campañas ni se leyó OOS-1/OOS-2. No se instaló el bucle
  `claude -p`.

## Siguiente

PARA.
