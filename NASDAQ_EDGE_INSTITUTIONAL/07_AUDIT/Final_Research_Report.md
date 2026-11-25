# Informe final · NASDAQ EDGE INSTITUTIONAL (2026-11-25)

## Conclusión

**No se ha encontrado una ventaja estadística demostrable** en la sesión de
Nueva York del Nasdaq con las familias A–E (ORB, barrido de liquidez, VWAP,
desplazamiento + FVG y subasta/volumen) tal como se preregistraron.

Por eso, como pedía el encargo, no se entrega un sistema de señales. Se entrega
una herramienta de **contexto, riesgo y cumplimiento** que muestra siempre
**NO EDGE VALIDATED**.

## Evidencia

| Fase | Resultado | Documento |
|---|---|---|
| A · Mercado, noticias y firmas | Especificaciones CME, reglas oficiales de Topstep, Apex y Tradeify 50K, calendario oficial hasta 2027-11 | `01_RESEARCH/` |
| B · Datos | NQ M1 2010–2018 apto (1.733 sesiones); Dukascopy solo como proxy de precio; OOS-2 sellado; descriptivas DEV con IC | `02_DATA/`, `01_RESEARCH/Nasdaq_Intraday_Research.md` §5 |
| C · 22 variantes | Bruto ≈ 0; neto DEV de −0,14R a −0,51R; OOS-1 casi neutro; 0/22 pasan | `03_BACKTEST/Strategy_Comparison.md` |
| D · Selección | Sin candidatas | ídem |
| E · Indicador | Pine v6 sin señales; motor de riesgo con test; compilación pendiente | `04_PINE_SCRIPT/`, `07_AUDIT/` |
| F · OOS-2 y Monte Carlo | No aplica: no hay configuración final. OOS-2 sigue sin leer | `03_BACKTEST/Out_Of_Sample_Results.md` |

Pruebas contadas en el DSR del laboratorio: 7 + 22 (`informal_trials` ids 6 y 7;
`count_tests` 1926).

## Qué sí se aprendió (medido, no supuesto)

- Las distancias en puntos no son comparables entre años; en múltiplos de ATR sí.
- La ruptura del OR15 continúa 1×OR solo en el 16,6 % de los casos (NQ DEV).
- FOMC mantiene una volatilidad superior a 1,5 veces la normal durante más de 60 min.
- CPI, NFP y PPI tardan unos 20 min en normalizarse. JOLTS no tiene efecto medible.
- Con stops estructurales de 3,5–8 pt (NQ 2010–2018), el coste de ejecución
  (0,15–0,36R por operación) basta para que estrategias con bruto ≈ 0 pierdan
  claramente.

## Qué haría falta para reabrir la investigación

1. Hipótesis **nuevas**, con un preregistro y un registro DSR nuevos del
   operador. Reutilizar o ajustar las 22 de aquí sería sobreoptimización.
2. NQ y MNQ M1 de 2019 en adelante (Databento) para validar con volumen CME real.
3. Comisiones reales de MNQ en la firma elegida.
