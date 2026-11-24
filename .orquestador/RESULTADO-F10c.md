# RESULTADO · F10c — validación Databento H1

Fecha: 2026-11-23. Solo lectura de los 7 parquet H1 ya descargados. No se
descargó nada, no se modificaron los originales, no se ejecutaron campañas ni
OOS, no se hizo push, no se tocaron tareas programadas, protegidos ni el carril
del EA. Informe completo: `reports/discovery/f10c-databento.md`.

## 1. Integridad

Los 7 ficheros pasan: 0 duplicados, 0 OHLC incoherentes, 0 precios ≤ 0 y 0
velas con high < low.

| Símbolo | Filas | Primera | Última |
|---|---:|---|---|
| US100 | 98.073 | 2010-06-07 | 2026-11-23 06:00 |
| US500 | 98.113 | 2010-06-07 | 2026-11-23 06:00 |
| US30 | 98.168 | 2010-06-07 | 2026-11-23 06:00 |
| XAUUSD | 98.289 | 2010-06-07 | 2026-11-23 06:00 |
| EURUSD | 97.075 | 2010-06-07 | 2026-11-23 06:00 |
| GBPUSD | 97.050 | 2010-06-07 | 2026-11-23 06:00 |
| USDJPY | 97.055 | 2010-06-07 | 2026-11-23 06:00 |

USDJPY (6J invertido) queda en escala correcta: cierre mínimo **75,6544**,
máximo **163,3053**, media 115,43; high ≥ low tras invertir.

## 2. Rolls

Detección por salto de nivel intra-sesión (hueco ≤ 3 h, |salto| ≥ 4 × ATR(14)
H1), sin metadatos de contrato. Candidatos: US100 4, US500 8, US30 6, XAUUSD 9,
EURUSD 16, GBPUSD 3, USDJPY 25. Las fechas completas y el salto/ATR están en el
informe. Los índices muestran los rolls trimestrales esperados (p. ej. US100
2024-06-19 7,1 ATR; 2023-12-13 5,5 ATR); XAUUSD los cambios de fin de mes;
EURUSD/USDJPY los terceros lunes trimestrales. GBPUSD incluye gaps de noticias
(2017-06-08, 2019-12-12), no solo rolls.

Política documentada: `.v.0` **sin ajuste** es la serie canónica de ejecución y
costes; para retornos se excluyen la vela del roll y la anterior; para una serie
continua de indicadores se usaría back-adjust por diferencia con una tabla
explícita. No se generó ninguna copia ajustada ni se eligió nada por resultado
de estrategia.

## 3. Sesiones y calidad

`derive-sessions --source databento` es estable en los 7. Se añadieron las
claves `databento:<SÍMBOLO>` en `config/discovery/engine.yaml`, conservando las
de bróker/Dukascopy. Régimen final 2016–2026: pausa 17:00–18:00 NY, cierre
viernes 17:00 y apertura domingo 18:00.

`data-check --source databento --all-tf`:
- M1/M5/M15/M30: FAIL porque esta descarga es solo H1 (no hay M1).
- H1: WARN en los 7 (143–187 huecos no programados).
- H4: WARN en los 7 (81–86 huecos).
- D1: FAIL en los 7 (51–57 huecos y sin calendario CME de festivos).

No se cambiaron umbrales. `usable-from --source databento --write`: H1 desde
**2010-06-07** y H4 desde **2010-06-06** en los 7; D1 no cumple y no se escribió
clave D1. Se corrigió `write_usable_from` para **fusionar** el bloque en vez de
sustituirlo: se conservaron 28 claves de bróker, 49 de Dukascopy y se añadieron
14 de Databento (91 en total). Test actualizado.

## 4. Databento vs Dukascopy

Periodo común; retornos sin velas de roll; desfase en horas; diferencia de nivel
media (futuro − CFD) en precio y ATR; cobertura sobre la unión.

- Correlación: **0,936–0,993** en las 21 combinaciones (7 símbolos × H1/H4/D1).
- Desfase óptimo: **0 h** en todas.
- Cobertura desigual: Databento falta 0,07–0,31 % en índices y 29–34 % en
  XAU/FX; Dukascopy falta 14–28 % en índices y 0–4 % en XAU/FX.
- Basis no intercambiable: US100 +38,4 puntos (0,78 ATR H1), US500 +6,9,
  US30 +23,0, XAUUSD +5,23 (0,94 ATR), EURUSD +0,00173 (1,46 ATR), GBPUSD
  +0,00047 (0,28 ATR), USDJPY −0,307 (−1,86 ATR). El basis cambia por año
  (p. ej. US100 −0,28 % en 2011 → +0,50 % en 2026; USDJPY −0,05 % → −0,37 %).

**Conclusión:** Databento sirve como segunda fuente para confirmar
retornos/ventaja de dirección en US100, US500, US30 y XAUUSD, excluyendo rolls y
sin usar niveles absolutos. **USDJPY es dudoso** (6J invertido, 25 candidatos de
roll, basis −0,307) y **EURUSD también** (corr 0,942, 34 % de velas ausentes y
basis 1,46 ATR). GBPUSD es aceptable; XAUUSD es el más limpio.

## 5. Comprobaciones

- `tests/test_discovery_fetch_databento.py`: **18 passed** (nuevo test de
  `derive_sessions` con Databento).
- `tests/test_discovery_config.py`: incluido en la suite; test de
  `write_usable_from` actualizado a fusión.
- `pytest -q`: **1746 passed, 1 skipped**.
- `ruff check src/tradinglab tests docs`: limpio.
- `lab propfund verify`: **4 OK**.
- `count_tests`: **1730**.
- `lab discovery data-check ... --source databento --all-tf`: exit 0 en los 7.
- No se descargó nada; los parquet originales no se tocaron.

## 6. Commit/tag

- Commit **`b53e62e`** · `tl2: F10c - validación Databento H1`
- Tag **`tl2-f10c`**
- `git status --short`: solo `?? tl2-edge-map.patch`.

PARA.
