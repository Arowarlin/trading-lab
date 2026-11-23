# F10c · validación Databento H1

Fecha: 2026-11-23. Solo lectura de los 7 parquet descargados por el operador (`data/cache/databento/*_H1.parquet`); no se descargó nada, no se modificaron los originales, no se ejecutaron campañas ni OOS, no se tocaron tareas programadas, archivos protegidos ni el carril del EA.

## 1. Integridad

| Símbolo | Filas | Primera vela | Última vela | Duplicados | OHLC incoherente | Precio ≤ 0 | Cierre mín/máx |
|---|---:|---|---|---:|---:|---:|---|
| US100 | 98,073 | 2010-06-07 00:00:00+00:00 | 2026-11-23 06:00:00+00:00 | 0 | 0 | 0 | 1707.2500 / 31583.7500 |
| US500 | 98,113 | 2010-06-07 00:00:00+00:00 | 2026-11-23 06:00:00+00:00 | 0 | 0 | 0 | 1004.2500 / 7892.0000 |
| US30 | 98,168 | 2010-06-07 00:00:00+00:00 | 2026-11-23 06:00:00+00:00 | 0 | 0 | 0 | 9514.0000 / 54874.0000 |
| XAUUSD | 98,289 | 2010-06-07 00:00:00+00:00 | 2026-11-23 06:00:00+00:00 | 0 | 0 | 0 | 1049.1000 / 5554.4000 |
| EURUSD | 97,075 | 2010-06-07 00:00:00+00:00 | 2026-11-23 06:00:00+00:00 | 0 | 0 | 0 | 0.9595 / 1.4919 |
| GBPUSD | 97,050 | 2010-06-07 00:00:00+00:00 | 2026-11-23 06:00:00+00:00 | 0 | 0 | 0 | 1.0413 / 1.7165 |
| USDJPY | 97,055 | 2010-06-07 00:00:00+00:00 | 2026-11-23 06:00:00+00:00 | 0 | 0 | 0 | 75.6544 / 163.3053 |

Los 7 pasan: 0 duplicados, 0 OHLC incoherentes, 0 precios ≤ 0 y 0 velas con high < low. **USDJPY** está correctamente invertido desde 6J: cierre mínimo 75,6544 y máximo 163,3053, en la escala esperada 80–160.

## 2. Rolls de contrato

No hay metadatos de contrato dentro del parquet. Se detectan candidatos por **salto de nivel** entre velas consecutivas dentro de la misma sesión (hueco temporal ≤ 3 h) y |salto| ≥ 4 × ATR(14) H1. La lista incluye también algún gap de noticias; los candidatos se usan solo para excluir el retorno del roll, nunca para elegir una estrategia.

| Símbolo | Candidatos | Fechas (salto / ATR) |
|---|---:|---|
| US100 | 4 | 2024-06-19 00:00 (7.1), 2023-12-13 00:00 (5.5), 2023-09-13 00:00 (4.8), 2026-09-16 00:00 (4.3) |
| US500 | 8 | 2024-06-19 00:00 (8.1), 2025-09-17 00:00 (7.9), 2024-12-18 00:00 (7.4), 2023-12-13 00:00 (6.0), 2023-09-13 00:00 (5.9), 2026-06-17 00:00 (4.9), 2026-09-16 00:00 (4.6), 2024-09-18 00:00 (4.1) |
| US30 | 6 | 2024-12-18 00:00 (6.0), 2024-06-19 00:00 (5.7), 2023-09-13 00:00 (5.4), 2023-12-13 00:00 (5.3), 2025-09-17 00:00 (4.5), 2020-02-27 21:00 (4.4) |
| XAUUSD | 9 | 2023-07-31 00:00 (11.2), 2024-07-31 00:00 (8.1), 2024-11-29 00:00 (5.8), 2025-07-31 00:00 (5.7), 2019-11-29 00:00 (5.3), 2023-11-30 00:00 (4.6), 2023-03-31 00:00 (4.3), 2023-06-01 00:00 (4.2), 2024-01-31 00:00 (4.1) |
| EURUSD | 16 | 2018-12-17 00:00 (7.8), 2019-03-18 00:00 (7.0), 2019-06-17 00:00 (6.4), 2017-12-18 00:00 (6.1), 2018-03-19 00:00 (5.8), 2018-09-17 00:00 (5.4), 2024-03-18 00:00 (5.2), 2019-09-16 00:00 (5.1), 2025-09-15 00:00 (4.9), 2025-12-15 00:00 (4.9), 2017-06-19 00:00 (4.4), 2019-12-16 00:00 (4.4), 2024-09-16 00:00 (4.4), 2023-09-18 00:00 (4.3), 2018-06-18 00:00 (4.2), 2026-09-14 00:00 (4.0) |
| GBPUSD | 3 | 2017-06-08 22:00 (10.4), 2019-12-12 23:00 (7.3), 2015-05-07 22:00 (4.5) |
| USDJPY | 25 | 2023-09-18 00:00 (18.0), 2024-03-18 00:00 (14.5), 2026-06-15 00:00 (9.3), 2024-12-16 00:00 (9.1), 2019-01-02 23:00 (9.0), 2019-03-18 00:00 (8.9), 2025-09-15 00:00 (8.6), 2024-06-17 00:00 (8.5), 2018-12-17 00:00 (8.0), 2025-12-15 00:00 (7.5), 2019-06-17 00:00 (7.4), 2022-09-19 00:00 (7.4), 2025-03-17 00:00 (7.2), 2018-09-17 00:00 (6.5), 2026-03-16 00:00 (6.4), 2023-12-18 00:00 (6.2), 2019-09-16 00:00 (5.8), 2018-06-18 00:00 (5.7), 2024-09-16 00:00 (5.6), 2018-03-19 00:00 (5.6), 2017-12-18 00:00 (5.5), 2025-06-16 00:00 (5.3), 2019-12-16 00:00 (5.2), 2022-12-19 00:00 (4.7), 2026-09-14 00:00 (4.1) |

**Política:** el `.v.0` sin ajuste es la serie canónica de ejecución y costes. Para análisis de retornos se excluyen las velas de roll (la vela del salto y la anterior); para una serie continua de indicadores se usaría back-adjust por diferencia con una tabla explícita de rolls, nunca deducida del resultado de una estrategia. No se generó ninguna copia ajustada.

## 3. Sesiones CME y calidad

`lab discovery derive-sessions SYMBOL --source databento` es estable en los 7 (moda semanal, regla del 60 %). Los tramos quedan en `config/discovery/engine.yaml` como `databento:<SÍMBOLO>`, sin tocar las claves de Dukascopy o bróker. Régimen final 2016–2026 en los 7: pausa 17:00–18:00 NY, cierre viernes 17:00 y apertura domingo 18:00.

| Símbolo | Tramos | Tramo final |
|---|---:|---|
| US100 | 5 | 2016-01-01 → 2026-12-31: viernes 17:00, domingo 18:00, pausa 17:00–18:00 |
| US500 | 5 | 2016-01-01 → 2026-12-31: viernes 17:00, domingo 18:00, pausa 17:00–18:00 |
| US30 | 4 | 2016-01-01 → 2026-12-31: viernes 17:00, domingo 18:00, pausa 17:00–18:00 |
| XAUUSD | 4 | 2016-01-01 → 2026-12-31: viernes 17:00, domingo 18:00, pausa 17:00–18:00 |
| EURUSD | 4 | 2015-01-01 → 2026-12-31: viernes 17:00, domingo 18:00, pausa 17:00–18:00 |
| GBPUSD | 4 | 2015-01-01 → 2026-12-31: viernes 17:00, domingo 18:00, pausa 17:00–18:00 |
| USDJPY | 4 | 2015-01-01 → 2026-12-31: viernes 17:00, domingo 18:00, pausa 17:00–18:00 |

`data-check --source databento --all-tf`: M1/M5/M15/M30 no existen en esta descarga (FAIL esperado); H1 y H4 dan WARN; D1 da FAIL por huecos no programados y falta de calendario CME de festivos (no se cambian umbrales).

| Símbolo | H1 | H4 | D1 |
|---|---|---|---|
| US100 | WARN · 98,073 filas · 184 huecos | WARN · 25,268 filas · 85 huecos | FAIL · 4,241 filas · 52 huecos |
| US500 | WARN · 98,113 filas · 184 huecos | WARN · 25,268 filas · 85 huecos | FAIL · 4,241 filas · 52 huecos |
| US30 | WARN · 98,168 filas · 187 huecos | WARN · 25,294 filas · 86 huecos | FAIL · 4,246 filas · 51 huecos |
| XAUUSD | WARN · 98,289 filas · 178 huecos | WARN · 25,311 filas · 81 huecos | FAIL · 4,237 filas · 57 huecos |
| EURUSD | WARN · 97,075 filas · 143 huecos | WARN · 25,320 filas · 81 huecos | FAIL · 4,241 filas · 52 huecos |
| GBPUSD | WARN · 97,050 filas · 143 huecos | WARN · 25,320 filas · 81 huecos | FAIL · 4,241 filas · 52 huecos |
| USDJPY | WARN · 97,055 filas · 143 huecos | WARN · 25,320 filas · 81 huecos | FAIL · 4,241 filas · 52 huecos |

`usable-from --source databento --write`: H1 desde **2010-06-07** y H4 desde **2010-06-06** en los 7; D1 no tiene año que cumpla y no se escribió clave D1. Se conservaron las claves existentes: 91 en total (28 bróker, 49 Dukascopy, 14 Databento). No se tocaron umbrales.

## 4. Databento vs Dukascopy

Periodo común tras alinear índices; retornos con exclusión de velas de roll; desfase en horas; diferencia de nivel media (futuro − CFD) en precio y ATR; cobertura sobre la unión de velas.

| Símbolo | TF | Velas comunes | Corr | Desfase h | Δ nivel | Δ ATR | DB falta % | DK falta % |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| US100 | H1 | 75,063 | 0.9786 | 0 | 38.422350 | 0.777 | 0.28 | 23.40 |
| US100 | H4 | 19,780 | 0.9775 | 0 | 38.283459 | 0.353 | 0.31 | 22.27 |
| US100 | D1 | 3,762 | 0.9796 | 0 | 33.300736 | 0.102 | 0.20 | 14.43 |
| US500 | H1 | 74,823 | 0.9699 | 0 | 6.909707 | 0.488 | 0.28 | 23.67 |
| US500 | H4 | 19,788 | 0.9731 | 0 | 6.824175 | 0.207 | 0.31 | 22.25 |
| US500 | D1 | 3,742 | 0.9807 | 0 | 5.627287 | 0.032 | 0.20 | 14.92 |
| US30 | H1 | 70,774 | 0.9845 | 0 | 23.015884 | 0.082 | 0.14 | 27.87 |
| US30 | H4 | 18,578 | 0.9835 | 0 | 23.009022 | 0.021 | 0.14 | 27.08 |
| US30 | D1 | 3,390 | 0.9851 | 0 | 16.960175 | -0.030 | 0.07 | 22.90 |
| XAUUSD | H1 | 97,813 | 0.9867 | 0 | 5.228083 | 0.937 | 31.41 | 0.33 |
| XAUUSD | H4 | 25,356 | 0.9891 | 0 | 5.314433 | 0.453 | 30.47 | 0.73 |
| XAUUSD | D1 | 4,247 | 0.9929 | 0 | 5.571968 | 0.181 | 29.20 | 4.16 |
| EURUSD | H1 | 97,062 | 0.9417 | 0 | 0.001730 | 1.456 | 34.00 | 0.01 |
| EURUSD | H4 | 25,342 | 0.9587 | 0 | 0.001740 | 0.665 | 31.09 | 0.02 |
| EURUSD | D1 | 4,239 | 0.9608 | 0 | 0.001786 | 0.248 | 30.91 | 0.10 |
| GBPUSD | H1 | 97,039 | 0.9630 | 0 | 0.000473 | 0.284 | 34.01 | 0.01 |
| GBPUSD | H4 | 25,342 | 0.9739 | 0 | 0.000493 | 0.134 | 31.09 | 0.02 |
| GBPUSD | D1 | 4,239 | 0.9775 | 0 | 0.000641 | 0.061 | 30.91 | 0.07 |
| USDJPY | H1 | 97,039 | 0.9362 | 0 | -0.306858 | -1.865 | 34.00 | 0.01 |
| USDJPY | H4 | 25,342 | 0.9519 | 0 | -0.306075 | -0.853 | 31.09 | 0.01 |
| USDJPY | D1 | 4,239 | 0.9515 | 0 | -0.295548 | -0.298 | 30.97 | 0.05 |

La correlación es alta (0,936–0,993) y el desfase óptimo es **0 h** en las 21 combinaciones. Pero el nivel no es intercambiable: el basis futuro–CFD es distinto de cero y cambia por año, y la cobertura de cada fuente no coincide (Databento tiene más velas en índices; Dukascopy en FX/oro).

| Símbolo | Basis H1 inicio | 2016 | 2026 |
|---|---:|---:|---:|
| US100 | -0.280% | -0.086% | 0.498% |
| US500 | -0.738% | -0.245% | 0.428% |
| US30 | -0.247% | -0.343% | 0.337% |
| XAUUSD | 0.095% | 0.130% | 0.451% |
| EURUSD | -0.001% | 0.162% | 0.203% |
| GBPUSD | -0.018% | 0.049% | 0.003% |
| USDJPY | -0.048% | -0.139% | -0.374% |

**Conclusión:** Databento sirve como segunda fuente para **confirmar retornos/ventaja de dirección** en US100, US500, US30 y XAUUSD (correlación alta, lag 0, tras excluir rolls), siempre que no se usen niveles absolutos. **USDJPY es dudoso** (6J invertido, 25 candidatos de roll y basis −0,307) y **EURUSD también** (corr 0,942, 34 % de velas que no están en Databento y basis 1,46 ATR). GBPUSD es aceptable con basis pequeño; XAUUSD es el más limpio.

## 5. Comprobaciones

- `tests/test_discovery_fetch_databento.py`: **18 passed** (incluye el nuevo `derive_sessions` con fuente Databento).
- `ruff check src/tradinglab tests docs`: limpio.
- `pytest -q`: **1746 passed, 1 skipped**.
- `lab propfund verify`: 4 OK; `count_tests`: 1730.
- `lab doctor`: 0/17 FAIL y 6 avisos FX H1/H4; no se descargó ni tocó ningún dato para el doctor.

## 6. Reproducibilidad

```powershell
Set-Location E:\trading-lab
.\.venv\Scripts\lab.exe discovery data-check US100 --source databento --all-tf
.\.venv\Scripts\lab.exe discovery derive-sessions US100 --source databento
.\.venv\Scripts\lab.exe discovery usable-from --source databento --write
```
