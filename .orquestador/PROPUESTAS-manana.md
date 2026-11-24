# PROPUESTAS PARA LA MAÑANA · specs H4/D1 de N2

Fecha: 2026-11-22. Solo papel: **no se registró, aprobó ni ejecutó nada**.
Base DSR actual: **1703**. Cada spec tiene `n_total = 27`; aprobar uno lo lleva
a **1730**. Aprobar los seis lleva a **1865**.

Filtro aplicado: preflight 100 % (27/27) y feasibility ≥ 50 % (gate del
pipeline). Los seis lo cumplen. Orden: operaciones IS (mediana) de mayor a
menor y, a igualdad, `cost_R` menor. No se ha mirado expectativa, PF ni
equity: solo operaciones y coste.

| # | Spec | Plantilla | Símbolo · TF | n_total | Preflight | Factibles | Ops IS mediana [rango] | cost_R mediana [rango] | Cuentas viables | DSR si se aprueba |
|---:|---|---|---|---:|---:|---:|---|---|---|---:|
| 1 | `n2-donchian-xauusd-h4` | `donchian_vol_h4` | XAUUSD · H4 | 27 | 27/27 | 27/27 (100 %) | 391 [262–637] | 0,0309 [0,0245–0,0401] | CFD-001, CFD-006 | 1730 |
| 2 | `n2-donchian-usdjpy-h4` | `donchian_vol_h4` | USDJPY · H4 | 27 | 27/27 | 27/27 (100 %) | 330 [216–568] | 0,0185 [0,0145–0,0240] | CFD-001, CFD-006 | 1730 |
| 3 | `n2-d1reversion-eurusd` | `d1_extension_reversion` | EURUSD · D1 | 27 | 27/27 | 15/27 (55,6 %) | 48 [32–92] | 0,0508 [0,0355–0,0612] | CFD-001, CFD-006 | 1730 |
| 4 | `n2-d1reversion-xauusd` | `d1_extension_reversion` | XAUUSD · D1 | 27 | 27/27 | 18/27 (66,7 %) | 45 [24–105] | 0,0141 [0,0112–0,0182] | CFD-001, CFD-006 | 1730 |
| 5 | `n2-ts-usdjpy-d1` | `ts_momentum_d1` | USDJPY · D1 | 27 | 27/27 | 27/27 (100 %) | 31 [24–44] | 0,0120 [0,0085–0,0168] | CFD-001, CFD-006 | 1730 |
| 6 | `n2-ts-xauusd-d1` | `ts_momentum_d1` | XAUUSD · D1 | 27 | 27/27 | 18/27 (66,7 %) | 26,5 [22–36] | 0,0118 [0,0100–0,0152] | CFD-001, CFD-006 | 1730 |

## Recomendación: empezar por `n2-donchian-xauusd-h4`

Motivos, sin mirar rendimiento:

1. **Factibilidad completa**: 27/27 combinaciones pasan el gate; no hay filas
   descartadas por muestra ni por tiempo medio. Es la opción con menos riesgo
   de que la campaña se quede sin finalistas por tamaño de muestra.
2. **Más operaciones**: mediana 391 por combinación (rango 262–637), muy por
   encima de las opciones D1 (26–48). Un `n_total` 27 con esa densidad da
   pliegues de 59–167 operaciones, suficientes para el walk-forward.
3. **Coste dentro de límite**: `cost_R` mediano 0,0309, máximo 0,0401, por
   debajo del 0,10 y con holgura; las dos cuentas son viables en todas las
   combinaciones.
4. **Sin bloques nuevos**: Donchian + `vol_high` + ATR + salida temporal ya
   existen y están probados; el riesgo de implementación es el más bajo.
5. **Solape bajo**: XAUUSD H4 no es US100 ni la incubación `us100-trend-d1`;
   la familia es ruptura/tendencia, pero en otro subyacente y TF.

Por qué no las otras: `n2-donchian-usdjpy-h4` es la segunda (100 %, coste
0,0185, 330 ops) y sería la alternativa natural si se prefiere un par de FX;
las D1 tienen menos operaciones y dos de ellas solo pasan el 56–67 % de las
combinaciones. No se elige por expectativa porque no se ha calculado.

## Comandos exactos para el operador

Sustituir solo si se cambia de spec. No ejecutar `run` sin la aprobación
explícita; el pipeline la exige.

```powershell
Set-Location E:\trading-lab

# 1) Registrar el borrador desde la spec (no cuenta para el DSR).
.\.venv\Scripts\lab.exe discovery register --spec .orquestador\specs\n2-donchian-xauusd-h4.yaml

# 2) Revisar el borrador con los mismos controles en seco.
.\.venv\Scripts\lab.exe discovery preflight n2-donchian-xauusd-h4
.\.venv\Scripts\lab.exe discovery feasibility n2-donchian-xauusd-h4

# 3) Aprobar (explícito; suma 27 al DSR: 1703 -> 1730).
.\.venv\Scripts\lab.exe discovery approve n2-donchian-xauusd-h4 --approved-by-operator

# 4) Ejecutar la campaña real (solo con la aprobación del operador).
.\.venv\Scripts\lab.exe discovery run n2-donchian-xauusd-h4 --approved-by-operator --workers 12

# 5) Leer el resultado sin OOS-2.
.\.venv\Scripts\lab.exe discovery results n2-donchian-xauusd-h4
```

Si se prefiere la segunda opción, repetir con
`.orquestador\specs\n2-donchian-usdjpy-h4.yaml` y el id
`n2-donchian-usdjpy-h4`.

## Avisos

- El registro real exige que `usable_from` cubra el IS; las seis specs ya lo
  cumplen (N2).
- `data_source: dukascopy` es obligatorio en H4/D1; la spec ya lo declara.
- No se ha leído OOS-1 ni OOS-2. El `run` real calculará lo que el pipeline
  tenga configurado; la lectura de OOS-2 sigue siendo una decisión aparte.
- El contador DSR solo sube al **aprobar**, no al registrar el borrador.
