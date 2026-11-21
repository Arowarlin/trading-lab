# 13 · Edge Map: dónde hay edge, en qué temporalidad y para qué firma

Fecha: 2026-11-21. Sustituye la idea de "una campaña = un instrumento, una TF y una firma" por un **mapa**
que responde, con datos reales, a tres preguntas:

1. ¿Existe **edge bruto** (antes de costes) para esta hipótesis, en este instrumento y en esta temporalidad?
2. ¿En qué **firmas** sobrevive ese edge a sus costes reales y es compatible con sus reglas?
3. ¿Está **confirmado** fuera de muestra, o es solo un candidato?

## Principio estadístico que lo hace posible

El edge bruto es una propiedad del **mercado**, no de la firma: el mismo precio es el mismo para todos.
Lo que cambia entre firmas es un **coste conocido de antemano** (spread por hora, comisión, slippage) y unas
**reglas conocidas de antemano**. Por eso:

- La búsqueda se hace **una sola vez** por hipótesis × instrumento × TF × fuente de datos, y cuenta en el DSR.
- La capa de firma es una **transformación determinista** (restar el coste de cada firma operación por
  operación y comprobar sus reglas). No es una hipótesis nueva y no se repite la búsqueda por firma.
- Para no caer en elegir la firma a posteriori, **el mapa siempre informa de TODAS las firmas** a la vez y
  la confirmación por firma usa N = finalistas × firmas.

## Cuatro capas

### Capa 1 · Datos reales (por instrumento y TF)
| Fuente | Uso | Estado |
|---|---|---|
| Bróker de cada firma (MT5 attach-only) | Verdad de la firma: precios recientes, spreads por hora, símbolos | US100/US500 + 6 CFD (R2) |
| Dukascopy M1 → M5…D1 | Historia larga (10+ años) para descubrir | R2g |
| Databento (CME) | Futuros NQ/ES/GC y sus micros; historia limpia desde 2010 | Fase 10 |
| Ejecuciones reales de la demo | Slippage real y deriva (R7b) | Pendiente |
Cada campaña congela su snapshot y usa una sola fuente para sus tres tramos.

### Capa 2 · Descubrimiento de edge bruto (hipótesis × instrumento × TF)
1. `feasibility-scan` (gratis, sin PnL ni DSR): en qué TF y sesión la hipótesis es operable con el
   coste de la firma **más barata** y con nº de operaciones suficiente. Las TF no viables no se prueban.
2. Campaña por cada TF viable (grid o GA), registrada y contada. Fitness con el **coste de la firma más
   barata elegible** (`cost_mode: best`): es la condición necesaria; si no hay edge ni con la firma más
   barata, no lo hay para ninguna. Las métricas guardan además el neto de **cada** cuenta.
3. Informe bruto vs neto por cuenta (como el informe de la campaña intraday v2).

### Capa 3 · Superposición de firma (sin nueva búsqueda)
Para cada estrategia de nivel ≥ 3 y cada cuenta registrada:
- neto por operación con los costes por hora de esa cuenta;
- compatibilidad con sus reglas (`firm_constraints`: noticias, fin de semana, overnight, lotes, EAs);
- Monte Carlo del challenge con sus límites: P(pasar), P(romper), días;
- si la firma permite automatizarla.
Al añadir una cuenta nueva (`lab propfund onboard`), esta capa se recalcula sola.

### Capa 4 · Confirmación por firma
Una sola lectura de OOS-2 por estrategia (como ahora) produce la lista de operaciones. Con ella se calcula
el neto de **cada** firma sin volver a leer: DSR de confirmación con N = finalistas × firmas, test contra el
azar en OOS-2 y mínimo de operaciones. Resultado por firma: CONFIRMADA / NO CONFIRMADA / INCOMPATIBLE.

## Salida principal: el mapa

| Hipótesis | Instrumento | TF | Edge bruto | FTMO | FundingPips | Firma N… |
|---|---|---|---|---|---|---|
| intraday momentum | US100 | M5 | **No** (−0,015 R) | — | — | — |
| ruptura apertura NY | US100 | M5 | Débil, sobreajustado | ✗ coste | ✗ coste | |
| … | | | | ✓ / ✗ coste / ✗ reglas / ? sin datos | | |

Vistas en la consola (Fase 8): mapa por hipótesis, por firma ("¿qué puedo operar en esta firma?") y por
instrumento ("¿en qué TF hay algo?").

## Cambios sobre el plan

| Fase | Cambio |
|---|---|
| R2f (en curso) | Añadir `cost_mode: best` y usarlo por defecto en descubrimiento; guardar el neto de todas las cuentas |
| R2g | Dukascopy M1 y remuestreo a todas las TF (sin cambios) |
| R2h | Motor multi-TF + `feasibility-scan` por TF y por cuenta |
| R2i | Onboarding de cuenta = recalcular las capas 3 y 4 para la nueva firma |
| R3 (nuevo) | `lab discovery edge-map` + informe; confirmación por firma en `confirm` |
| Fase 8 | Vistas del mapa |

## Lo que no cambia
Contador global, OOS-2 de una lectura, snapshots, niveles deterministas, la IA no aprueba nada, nada
se reoptimiza al pasar de una firma a otra.
