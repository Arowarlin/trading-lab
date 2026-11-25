# COLA TL3-B · T7, T8, diferencia simulación/real de T5 y cierre del ciclo 1 (continuación sin paradas)

**Creada:** 2026-11-25 · **Arranca:** en cuanto termine el T11 en curso de la relanza (tag `tl3-ciclo1b`).
Si T11 sigue ejecutándose, termínalo primero y después empieza aquí, **sin pedir confirmación**.
**Modo:** cadena continua B0 → B6. Ningún bloque espera al operador salvo B1, que espera las filas
del contador con un límite de tiempo. Un commit pequeño por bloque.

## 1. Reglas (las mismas de `COLA-TL3.md §1`, más estas)

| Situación | Qué hacer |
|---|---|
| Fallo técnico (excepción, datos que no cargan, test roto) | Hasta 3 reintentos corrigiendo la causa; si sigue, marca el bloque `bloqueado: <motivo>` y **sigue** con el siguiente |
| Fallo de validez o de potencia previsto en el prerregistro | Aplica el prerregistro literal (p. ej. `rejected: no_power`), sin calcular el resultado, y **sigue** |
| Resultado que no gusta | Se informa tal cual. **No** se reinterpreta, no se cambian ventanas ni criterios, no se prueba otra versión |
| Duda no cubierta aquí | Elige la opción más conservadora, anótala en `RESULTADO-TL3.md` y **sigue** |

Prohibido: tocar el EA, el setfile, `ea_us100_engine.py`, `ea_lab/`, `ai_trader.py`, Prop Fund, el
riesgo FTMO, el forward, `config/schedule.yaml`, las tareas programadas y `.env`; escribir en
`discovery.db` o `lab.db` (solo lectura, en copia); usar `record-informal`; enviar órdenes;
campañas, `research*`, OOS, `confirm`; push; borrar archivos; ejecutar T7 o T8 más de una vez;
cualquier otra prueba o análisis que mire rendimiento fuera de B0, B2 y B3.

## 2. Bloques

### B0 · T5-bis · Diferencia entre simulación y ejecución real de `ai_trader` (descriptivo, no suma)
**Motivo.** En T5, la IA recalculada con M1 da **+0,2953 R** por operación y el resultado real
registrado es **+0,0479 R** (mismas 48 operaciones). Una diferencia de ~0,25 R por operación entre
simulación y ejecución importa tanto como el veredicto de T5. Este bloque no evalúa ninguna hipótesis:
solo descompone la diferencia. No suma al contador. Se hace **mientras** el operador registra el
contador, por eso va antes que B1.

1. Lee `ai_trades` de una **copia** de `lab.db` (`mode=ro`) y la salida por operación del script de
   T5 (o vuelve a ejecutar solo su simulación de la IA, con MT5 attach-only y login verificado antes y
   después; ninguna orden).
2. Para cada una de las 48 operaciones, en R de la propia operación:
   - `gap = result_r real − R simulado`;
   - **entrada**: precio real de entrada frente al simulado (apertura de la vela siguiente + spread) y
     diferencia de hora;
   - **salida**: precio y motivo reales (TP/SL/cierre forzoso/manual/otro) frente a los simulados;
     marca las operaciones donde el motivo no coincide;
   - **costes**: comisión y swap reales (de `pnl` frente a precio) frente a los del modelo;
   - **definición de R**: distancia de SL usada en `result_r` frente a la usada en la simulación.
3. Comprueba también por qué "siempre tomar" coincide exactamente con la IA (Δ = 0,0000): si es
   porque el setup siempre fija el lado y la IA nunca lo contradice, dilo; si es un error del script,
   dilo.
4. **Si encuentras un error en la simulación de T5**, corrígelo, vuelve a ejecutar T5 **una vez** con
   el mismo prerregistro (T5 no suma) e informa las cifras antiguas y las nuevas. Si no hay error, no
   se toca T5.
5. Informe `TL3_REPORTS/ai_trader_sim_vs_real.md`: R real medio, R simulado medio, gap medio con IC95
   (bootstrap 10.000, semilla 7), descomposición del gap (entrada / salida / costes / definición de R /
   resto), desglose por símbolo y lado, tabla de las 10 operaciones con mayor |gap| y conclusión
   literal ("la diferencia se explica por…" o "Sin datos" si falta información). No se proponen
   cambios en `ai_trader`.
6. Commit: `tl3: T5-bis - simulacion vs real`.

### B1 · Contador (espera acotada)
1. Comprueba en `informal_trials` (copia de `lab.db`, `mode=ro`) que existen las filas con `TL3-T7` y
   `TL3-T8` y que `count_tests` = **1897**.
2. Si falta alguna: vuelve a comprobar cada 5 minutos durante **60 minutos como máximo**, sin hacer
   nada más. Si aparece, sigue. Si a los 60 minutos sigue faltando, marca el bloque que corresponda
   (T7 y/o T8) como `bloqueado: falta registro del operador` y salta directamente a B4.
3. Sin commit si no hay cambios.

### B2 · T7 · EA v3.2 fuera de periodo, US100 Dukascopy (1 prueba)
- Exactamente como `COLA-TL3.md §4 T7`, incluida la **nota previa a T7**: datos, ventana (entradas
  2012-01-03 → 2021-08-31, calentamiento desde 2011-10-01), `k` contra US100.cash 2022, exclusiones,
  costes, criterio (n ≥ 300, exp ≥ 0,10 R, LCB95 > 0, bootstrap semanal 10.000, semilla 42) y
  lectura.
- **Una ejecución.** Registra `experiments` y `sample_usage` (US100, M5, 2012-2021, `holdout`) en
  `tl3_research.db` y una fila de estado nueva para H-2026-008 (append-only).
- Informe `TL3_REPORTS/ea_oop_dukascopy.md` con lo que pide el prerregistro (tabla por año,
  largo/corto, slippage 0/0,5/1/2/3 pt, `slip_eq`, exclusiones por año). La tabla por año es
  descriptiva: no se usa para elegir subperiodos.
- Commit: `tl3: T7 - EA fuera de periodo Dukascopy`.

### B3 · T8 · H2 deriva previa al FOMC (1 prueba)
- Exactamente como `COLA-TL3.md §4 T8`, con la **enmienda de costes** (swap = interés largo de
  CFD-006, 7,33 %/365 por noche, ×3 si cruza el rollover del día triple) y la **decisión del
  operador** (δ = 30 bps, lectura fijada).
- Orden obligatorio: primero σ del placebo y MDE; si MDE > 30 bps → `rejected: no_power` y **no**
  se calcula el retorno de los eventos. Si pasa, una sola evaluación del criterio (a) y (b).
- **Una ejecución.** Registra `experiments`, `sample_usage` y una fila de estado nueva para
  H-2026-009 (append-only).
- Informe `TL3_REPORTS/h2_pre_fomc.md` con lo que pide el prerregistro, incluida la escalera
  bruto → neto de T4 y la tabla por época (≤ 2015 / ≥ 2016), y la referencia a
  `TL3_REPORTS/literatura_T8_H1.md`.
- Commit: `tl3: T8 - H2 pre-FOMC`.

### B4 · Resultados
- Actualiza `TL3_REPORTS/TL3_RESULTS_CICLO1.md` y `.orquestador/RESULTADO-TL3.md`: estado de cada
  bloque, cifras de T5-bis, T7 y T8 con su conclusión o veredicto literal, `count_tests` final,
  tabla de hipótesis.
- Commit: `tl3: resultados T5-bis, T7 y T8`.

### B5 · Cierre
- `ruff check`, `pytest -q` completo, `lab doctor`, `lab propfund verify`.
- README y PLAN actualizados (estado del ciclo 1 de TL3).
- Commit `tl3: cierre ciclo 1c` y tag `tl3-ciclo1c`.

### B6 · Aviso
- Resumen a Telegram con `lab telegram send --file <resumen>`; si Telegram no está configurado,
  `lab alerts send`. Formato **Hecho / 1..N / Aviso / Siguiente**, con: conclusión de T5-bis,
  veredicto de T7, veredicto de T8, `count_tests` final, tests y bloqueos si los hubo.
- Fin de la cola. No se empieza nada más.
