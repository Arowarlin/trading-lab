# EDGE1_H1_NY_IMPULSE_CONTINUATION · backtest IS (OOS sellado)

- Título: Continuación del impulso de apertura de Nueva York en índices, H1
- Prerregistro: `configs/edge1_h1_ny_impulse.yaml`
- SHA256 del prerregistro: `3a15133141f28b9d2e26b0262596723c9b0522ba264669fe826a2fb291978230`
- Generado: 2026-11-25T23:01:43+00:00
- Datos: Dukascopy BID M1 -> H1, US100, US500
- IS: 2011-09-19 .. 2023-12-31
- OOS: 2024-01-01 .. 2026-11-25 **sellado, no leído**

## 1. Regla ejecutada

| Campo | Regla |
|---|---|
| Vela de señal | 9:00-10:00 NY |
| Impulso | cuerpo / rango >= 0.50 |
| Ruptura | cierre > máximo (o < mínimo) de las 3 velas H1 previas |
| Entrada | open de la vela 10:00 NY |
| Stop | 2.0 x ATR(14) H1 |
| Objetivo | 2.0 R |
| Salida por tiempo | cierre de la vela 15:00 NY (16:00) |
| Prioridad intrabar | stop antes que target si ambos se tocan en la misma vela |
| Frecuencia | máximo 1 operación por instrumento y día |
| Costes | v2: spread + 2 x slippage + 2 x comisión; peor de CFD-001/CFD-006 |

## 2. Cobertura y sello OOS

| Instrumento | Filas M1 usadas | Filas OOS descartadas | Velas H1 | Primera vela | Última vela | Días sin velas completas |
|---|---:|---:|---:|---|---|---:|
| US100 | 3,287,116 | 988,475 | 58,278 | 2011-09-18T21:00:00+00:00 | 2023-12-29T21:00:00+00:00 | 712 |
| US500 | 3,130,072 | 979,416 | 58,031 | 2011-09-18T21:00:00+00:00 | 2023-12-29T21:00:00+00:00 | 698 |

El OOS se descartó antes de remuestrear y de calcular señales. Ninguna fila con timestamp >= 2024-01-01T00:00:00Z entra en la regla, los costes o las métricas.

## 3. Puertas (antes del DSR)

| Puerta | Resultado | Detalle |
|---|---|---|
| power_gate (n >= 40) | PASA | n = 2039 |
| cost_gate (mediana cost_r <= 0.10) | NO PASA | mediana = 0.1051; p90 = 0.2396 |

**DSR: no calculado.** Una de las dos puertas no se superó; calcularlo después sería una mirada no prerregistrada.

## 4. Resultado IS

| Métrica | Valor |
|---|---:|
| Operaciones | 2039 |
| Bruto medio | 0.0946 R |
| Coste mediano | 0.1051 R |
| Neto medio | -0.0291 R |
| Desviación del neto | 1.1488 R |
| LCB95 (bootstrap por fecha) | -0.0816 R |
| MDE (2,49 x sigma / sqrt(n)) | 0.0634 R |
| Tasa de acierto | 0.4497 |
| Profit factor | 0.9448 |

### Neto medio por instrumento

| Instrumento | n | Bruto R | Coste R | Neto R |
|---|---:|---:|---:|---:|
| US100 | 1075 | +0.1214 | 0.0893 | +0.0321 |
| US500 | 964 | +0.0647 | 0.1619 | -0.0972 |

### Neto medio por año

| Año | n | Neto medio R |
|---|---:|---:|
| 2013 | 99 | -0.4040 |
| 2014 | 173 | -0.1887 |
| 2015 | 185 | -0.0404 |
| 2016 | 215 | -0.1926 |
| 2017 | 202 | -0.0868 |
| 2018 | 186 | -0.0159 |
| 2019 | 216 | -0.1109 |
| 2020 | 162 | +0.1141 |
| 2021 | 215 | +0.1893 |
| 2022 | 183 | +0.2229 |
| 2023 | 203 | +0.0332 |

## 5. DSR

| Campo | Valor |
|---|---|
| Estado | No calculado (puerta fallida) |

## 6. Veredicto

**rejected: cost_gate**

## 7. Límites

- Solo se ejecutó el tramo IS; 2024-2026 sigue sellado y no se ha mirado.
- Dukascopy es BID; el spread se modela con la mediana horaria del bróker y el slippage con el supuesto de `engine.yaml`. No es un fill real.
- US30 queda fuera por falta de spread/comisión en las cuentas; no se inventan costes.
- Un resultado positivo aquí no es una estrategia validada: es un candidato para una lectura OOS única, con su propio registro.
