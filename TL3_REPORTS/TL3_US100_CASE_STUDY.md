# TL3 · Caso de estudio: EA `us100-ftmo1` (protegido, solo lectura)

**No se modificó el EA, el setfile, el motor ni el forward. No se ejecutó el motor.** El análisis usa
los R diarios ya publicados (`reports/ea/us100-ftmo1_daily_r.parquet`, base v3, 463 días con operación,
2021-10-01 → 2026-11-13) y la caché M5 del EA. Reproducible con
`TL3_REPORTS/evidencia/tl3_regimen_ea.py`. Leyenda en `TL3_FORENSIC_AUDIT.md`.

## 1. Qué es el EA

- [HECHO] US100.cash M5, sesión NY. Rango de apertura de 15 min (09:30–09:45), entradas 09:45–11:00,
  cierre forzoso a las 15:45. Puntuación de confluencia (sweep 25, FVG 20, VWAP 20, estructura 15,
  RVOL 10, OR 10; mínimo 55), filtro de gap ≥ 0,7, régimen, noticias ±15 min, SL ATR 1,5, **RR 3,5**,
  máximo 3 operaciones y 1 pérdida consecutiva al día. Riesgo 0,35 % con escalera dinámica.
  (`US100_FTMO_v3_challenge.set`)
- [HECHO] Unos 70 parámetros de entrada. Historia de versiones registrada en git: v3 (2026-11-14),
  v3.1 y v3.2 (2026-11-15). Las versiones anteriores a v3 no están en el repo: **Sin datos**.

## 2. Resultados históricos

[DOC] `reports/ea/us100-ftmo1-v2.md` (motor v3.2, spread por barra, slippage 0,5 pt/lado):

| Año | Ops | Exp R | Total R | DD R |
|---|---:|---:|---:|---:|
| 2021 (sep–dic) | 34 | +0,135 | +4,6 | 7,2 |
| 2022 | 84 | **+0,675** | **+56,7** | 7,0 |
| 2023 | 94 | **+0,037** | **+3,5** | **16,5** |
| 2024 | 96 | +0,294 | +28,3 | 10,8 |
| 2025 | 86 | +0,273 | +23,5 | 14,1 |
| 2026 (ene–nov) | 84 | +0,379 | +31,9 | 9,1 |
| **Total** | **478** | **+0,310** | **+148,4** | **24,8** |

- [HECHO] **El periodo efectivo es 2021-09 → 2026-11 (~5,2 años), no 2017 → 2026.** La caché tiene D1 en
  2018–2020 y H1 en 2021; el motor no opera en esas velas. El título "2017-12-28 → 2026-11-23" del
  informe induce a error.
- [HECHO] El 2022 aporta el 38 % del R total con el 18 % de las operaciones.

## 3. Regímenes

### 3.1 Volatilidad intradía (rango RTH medio del mes, terciles) [REPRODUCIDO]

| Tercil de volatilidad | Meses | R total | R por mes |
|---|---:|---:|---:|
| Baja | 21 | +21,3 | +1,01 |
| Media | 20 | +43,0 | +2,15 |
| Alta | 21 | +79,7 | +3,79 |

Correlación mensual R ~ rango: **+0,30**. R ~ tendencia del mes: **+0,01**. R ~ |tendencia|: +0,18.

### 3.2 Por año [REPRODUCIDO]

| Año | R | Rango RTH medio (%) | \|Tendencia mensual\| media (%) | Meses positivos |
|---|---:|---:|---:|---:|
| 2021 | +0,1 | 1,43 | 3,6 | 67 % |
| 2022 | +56,7 | **2,37** | 7,4 | 83 % |
| 2023 | +3,5 | 1,40 | 5,3 | 50 % |
| 2024 | +28,3 | **1,26** | 3,1 | 58 % |
| 2025 | +23,5 | 1,48 | 3,8 | 67 % |
| 2026 | +31,9 | 1,51 | 5,7 | **100 %** |

### 3.3 2022 frente a 2023

- **[INFERENCIA]** 2022 fue el año de mayor rango intradía (2,37 % frente a 1,26–1,51 % del resto). Un
  sistema de RR 3,5 que necesita recorridos largos después de las 09:45 cobra más cuando el rango del día
  es grande. Esto explica bien **2022**.
- **[INFERENCIA]** No explica **2023**: su rango (1,40 %) es igual que el de 2021 y 2025, y 2024 tuvo menos
  rango y +28 R. Lo distintivo de 2023 es una subida sostenida (|tendencia| 5,3 %) con rango bajo. Una
  hipótesis compatible es que el lado corto del EA pierde en mercados de subida lenta y continua.
- **[HIPÓTESIS pendiente]** Comprobarlo exige la lista de operaciones con su lado (largo/corto) y la
  puntuación de cada componente. Esa lista no está publicada; obtenerla requiere **una** ejecución del
  motor con el setfile congelado y `counted=0`, que necesita aprobación del operador.
- **Conclusión [INFERENCIA]:** la ventaja **sí depende del régimen**: rinde 3,8 veces más por mes en
  volatilidad alta que en baja. En volatilidad baja sigue siendo positiva (+1,0 R/mes, 21 meses). No es
  una estrategia "solo de 2022", pero 2022 infla la media.

## 4. Distribución, días y rachas [REPRODUCIDO]

| Métrica | Valor |
|---|---|
| Cuantiles del R diario (5/25/50/75/95 %) | −1,02 / −1,01 / −1,01 / +2,02 / +3,50 |
| Cuota del R total en los 20 mejores días (de 463) | **59 %** |
| Racha máxima de días perdedores | 13 |
| DD máximo | 24,8 R (fondo 2024-03-18) |
| Win rate | 34 % [DOC] |

| Día | Días con op. | R medio | R total |
|---|---:|---:|---:|
| Lunes | 90 | +0,28 | +25,1 |
| Martes | 95 | +0,36 | +33,9 |
| Miércoles | 94 | +0,42 | +39,2 |
| Jueves | 95 | +0,30 | +28,1 |
| Viernes | 89 | +0,20 | +17,6 |

- **[INFERENCIA]** No hay un día malo; el viernes rinde menos, dentro del ruido (SE diaria ≈ 0,2 R).
  **No se recomienda filtrar días**: sería ajustar con la misma muestra.
- **[INFERENCIA]** La mediana de un día es una pérdida de −1 R. El resultado depende de pocos días
  grandes: 20 días hacen el 59 % del total. Es el perfil normal de RR 3,5, y también la razón de que
  la varianza sea alta (σ = 1,92 R) y el forward sea tan lento de validar.
- **MAE/MFE y horario de entrada:** **Sin datos.** No están en los informes publicados; requieren la
  misma ejecución `counted=0` del §3.3.

## 5. Sensibilidad a costes

[DOC] Slippage de equilibrio ≈ 8,9 pt/lado frente a 0,5 modelado; con 2 pt/lado la expectativa baja a
+0,25 R. **El coste no es el riesgo principal del EA.** El slippage real sigue sin medir (C4: 6 cierres
US100 con mediana 0,30 pt, n < 30).

## 6. Fuera de muestra: lo que hay y lo que falta

| Prueba | Resultado | Valor como evidencia |
|---|---|---|
| Backtest 2021-09 → 2026-11 | +0,31 R, LCB95 0,17 | **Muestra de diseño.** El setfile es la mejor de 8 variantes y el diseño previo no está registrado |
| Holdout natural tras la congelación | 2 ops, −1,00 R media | Nulo (n = 2) |
| Forward demo | 1 op, +0,56 R | Nulo (n = 1) |
| Fuera de instrumento (US500, US30, prerregistrado) | US500 −0,023 R (LCB −0,17); US30 +0,069 R (LCB −0,04): **no transfiere** | **Única prueba independiente real, y es negativa.** Sin embargo, la escala de parámetros en puntos por ATR y el slippage fijo de 0,5 pt pesan mucho más en US500 (slip_eq 0,43 pt) |
| NQ 2010–2017 (NQ-B, en curso) | — | **Mal especificada:** su puerta de validez compara con un 2018 que en la caché es D1 (ver `TL3_FORENSIC_AUDIT.md` G-1). Además, NQ es un futuro, no el CFD |

### Interpretación [INFERENCIA]
Hay dos explicaciones compatibles con los datos:
1. **Ventaja específica de US100.** Su volatilidad intradía y su concentración tecnológica favorecen
   este patrón de apertura más que en US500/US30.
2. **Sobreajuste a US100 2021-2026.** Unos 70 parámetros, pesos de puntuación y selección de la mejor
   variante en la misma muestra producen exactamente este perfil: muy bueno en muestra y que no
   transfiere.

Los datos actuales **no permiten distinguir entre (1) y (2)**. La correlación diaria baja entre
símbolos (0,29–0,35) no decide nada.

### La prueba que sí las distingue
**US100 fuera de periodo, mismo tipo de instrumento:** Dukascopy US100 M1 (2011-09 → 2021-08, ya en
disco, gratis) remuestreado a M5 NY, con el perfil de spread por franja que ya construye
`ea_lab/nq_adapter.py`. Precauciones a fijar **antes** de mirar:
- Dukascopy es BID-only: el spread se modela, no se observa.
- El filtro RVOL del EA usa volumen de ticks; el volumen de Dukascopy tiene otra escala. Hay que
  decidir antes la normalización (por ejemplo, RVOL relativo a su propia media de 20 días, que es lo
  que calcula el EA) y comprobar la paridad con MT5 en 2022 (≥ 80 % de operaciones emparejadas).
- Criterio prerregistrado igual que E2: n ≥ 300, exp ≥ 0,10 R, LCB95 > 0.
- Una sola ejecución, registrada en `informal_trials`.

Si pasa, (1) gana mucho peso. Si no pasa, el EA es, con alta probabilidad, un ajuste a 2021-2026.

## 7. Qué aprender del EA para la investigación

- [INFERENCIA] Lo que funciona está en la **apertura de NY con expansión de rango** y salidas
  asimétricas (RR alto). Esa es una hipótesis económica investigable aparte: *el primer impulso tras
  la apertura cash continúa cuando el rango del día se expande*, formulada con **pocos parámetros**
  en datos que el EA no vio. Ver `TL3_NEW_RESEARCH_METHODOLOGY.md` H1.
- [REC] No usar 2025-07 → 2026-11 de US100 M5 como holdout de ninguna hipótesis de apertura NY.
- [REC] No cambiar el riesgo a 0,65 % por el cálculo de P(pasar) (`us100-ftmo1-v2.md §8`): ese
  Monte Carlo remuestrea la muestra de diseño y hereda su optimismo.
