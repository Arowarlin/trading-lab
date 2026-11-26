# EDGE_RESEARCH_PLAN · Programa ENG-1 (Fase 6) · **BORRADORES**

**Estado:** borradores. **Nada de esto está registrado ni se ha ejecutado.** Registrar una hipótesis y
ejecutarla requiere la aprobación explícita del operador (AGENTS.md). Fuente del inventario de lo ya
probado: `WORKER_REPORTS/E-edge.md`.

## 0. Lección de EDGE-1 que cambia el método

- Con σ ≈ 1-1,9 R por operación, detectar **0,1 R** con un 80 % de potencia exige **619-2.233
  operaciones**. Las plantillas de EDGE-1 hacen 6-58 al año. Ningún barrido GA de esas plantillas
  puede ver una ventaja realista: solo descarta las grandes (≳0,3-0,4 R).
- Además, las puertas actuales tienen fallos en los dos sentidos (D-01, D-02, D-03, E-01).
- **Propuesta:** dejar de barrer y pasar a **pruebas únicas prerregistradas**: una regla fija, sin
  parámetros que ajustar, sobre muchos eventos, con un solo test estadístico (N del DSR +1). Solo se
  vuelve al GA cuando ENG-S1 haya corregido las puertas.

## 1. Prioridad

| # | Línea | Hipótesis | Eventos disponibles | Bloqueos | Prioridad |
|---|---|---|---|---|---|
| C1 | FX por sesiones | Deriva de USDJPY hacia el fix de Tokio (9:55 JST) en días gotobi | ~1.600 (2003-2022, Dukascopy) | Calendario de festivos japoneses (**Sin datos**); B-01 (comisión USDJPY); confirmar que H-2026-002 no es esta hipótesis | **1** |
| A1 | NQ/MNQ | Reversión en Globex tras el cierre de la sesión regular (16:00-16:15 ET) cuando el último tramo fue extremo | ~2.200 días (NQ M1 2010-2018) | Sin datos de desequilibrio MOC; NQ 2019+ = **Sin datos** (compra pendiente, decisión 5 de ESTADO) | 2 |
| D1 | Regímenes | Momentum temporal (12 meses) en una cesta multiactivo D1 | Depende de la cesta | La métrica en R con stop ATR no representa volatility targeting: hace falta una métrica de cartera | 3 |
| B | Apertura NY | — | — | Todo 2010-2026 está contaminado por el EA. **Solo forward** (ya en marcha con NQF) | Sin campaña |

## 2. C1 · Fix de Tokio en días gotobi (borrador de prerregistro)

1. **Mecanismo.** Los importadores japoneses liquidan pagos en USD los días gotobi (5, 10, 15, 20, 25
   y el último día hábil del mes) y compran USD contra JPY al precio del fix de las 9:55 JST. Es un
   flujo previsible y no informativo que debería presionar al alza a USDJPY antes del fix.
   *Referencias publicadas: por verificar; no se citan cifras.*
2. **Por qué daría una expectativa positiva:** el flujo se conoce de antemano y no depende del
   precio. Los proveedores de liquidez cobran por absorberlo, y quien se anticipa recoge parte de ese
   cobro.
3. **Mercado:** USDJPY spot (Dukascopy BID/ASK). No se transfiere a ningún otro instrumento.
4. **Timeframe:** M1 agregado a la ventana del evento.
5. **Datos:** caché Dukascopy USDJPY M1 (desde 2003 según E-edge), BID **y** ASK, y un calendario de
   festivos japoneses (**Sin datos** en `calendars.py`: hace falta una fuente oficial). Antes de nada
   se comprueba con L1b que no hay huecos C-01/C-02 en la ventana 8:00-10:00 JST.
6. **Entrada (fija, sin parámetros que ajustar):** compra en la apertura de la vela de las 9:00 JST
   del día gotobi efectivo. Si cae en fin de semana o festivo japonés, se adelanta al hábil anterior.
7. **Salida:** cierre de la vela de las 9:54 JST (antes del fix). Sin stop ni objetivo: es una
   medida del flujo, no una estrategia operable.
8. **Costes:** entrada al ASK y salida al BID de Dukascopy. Más la comisión de la cuenta, con la
   conversión correcta USD→JPY (B-01: **no** usar `fastbt` sin el parche). Más un escenario de
   estrés con el spread p75 medido en `broker_spreads` a esa hora.
9. **Periodo:** 2003-01-01 a 2022-12-31 en un solo bloque (no hay nada que optimizar). 2023+ sigue
   sellado como en el resto del laboratorio.
10. **Criterio de rechazo (escrito antes de mirar):**
    - Media neta por evento en pips con t HAC (Newey-West, 5 retardos) **< 1,645**: rechazada.
    - Media neta > 0 pero con signo distinto en 2003-2012 y 2013-2022: **inconclusive**.
    - Si pasa, se registra como **candidato** (no validado). Siguiente control: lectura única del
      tramo 2023+ con autorización del operador.
11. **Registro:** `count_tests` +1 al registrar. La familia de pruebas (días no gotobi como control
    placebo) se declara aquí: **1** prueba principal y **1** placebo, que no suma porque no se elige
    entre ellas.

**Condición previa:** abrir en solo lectura la definición de H-2026-002 en `lab.db`. Si ya era esta
hipótesis, C1 queda **REJECTED (ya probada)** y no se repite.

## 3. A1 · Reversión post-cierre en NQ (esbozo)
- **Mecanismo:** el desequilibrio de las órdenes MOC empuja el precio en los últimos minutos de la
  sesión regular. Cuando termina el flujo, parte del movimiento se deshace en Globex.
- **Datos:** NQ M1 2010-2018 (Databento, ya en la caché según los documentos), con volumen real CME.
  Sin datos de desequilibrio MOC: se usa un proxy (el movimiento de 15:50 a 16:00 en múltiplos de
  ATR), que se declara.
- **Riesgo:** el laboratorio ya ha mirado mucho el NQ intradía. Este tramo **no** es la apertura NY,
  pero se declara la contaminación débil.
- Se desarrolla como C1 si el operador lo prioriza.

## 4. D1 · Momentum temporal multiactivo (esbozo)
- Literatura amplia (por verificar); en el laboratorio, "momentum" ya salió `inconclusive`.
- Solo tiene sentido con una cesta amplia y un efecto declarado ≥ 0,25 R, o con una métrica de
  cartera (Sharpe con volatility targeting), que hoy no existe en Discovery.
- Queda en esbozo hasta que exista esa métrica.
