# COLA TL3-C · Correcciones de la revisión del ciclo 1c (continuación sin paradas)

**Creada:** 2026-11-25, tras la revisión de Claude (solo lectura) de `b5320f1..44d9f5e`.
**Modo:** cadena continua C0 → C6, sin pedir confirmación. Un commit pequeño por bloque.
**C3 (T8 corregido): APROBADO por el operador el 2026-11-25**, en la sesión de revisión de Claude y
antes de calcular ningún evento: una sola ejecución, con las correcciones de C3, **sin fila nueva** en
el contador (`count_tests` sigue en 1897). El mensaje de lanzamiento lo repite con
`APRUEBO REEJECUCIÓN T8`.

## 1. Reglas (las de `COLA-TL3-B.md §1`, más estas)

- **Escritura de ficheros:** solo con Python (`Path.write_text(..., encoding="utf-8")`) o con
  `git checkout`. **Nunca** con `>`, `Out-File` ni `Set-Content` de PowerShell: en `44d9f5e` eso dejó
  `ai_trader_contrafactual.md` en UTF-16 con mojibake y cambió los signos "−" por "?".
- **Registro `tl3_research.db`:** solo filas nuevas; el `created_at` de una fila nueva es la hora UTC
  actual (no se copia el del padre). No se modifica ninguna fila existente.
- **Prohibido:** tocar el EA, el setfile, `ea_us100_engine.py`, `ea_lab/`, `ai_trader.py`, Prop Fund,
  el riesgo FTMO, el forward, `config/schedule.yaml`, las tareas programadas y `.env`; escribir en
  `lab.db` o `discovery.db`; usar `record-informal`; enviar órdenes; campañas, `research*`, OOS,
  `confirm`; push; borrar archivos; **volver a ejecutar T7**; cualquier análisis de rendimiento fuera
  de C1 y C3. Ningún bloque necesita MT5.

## 2. Hallazgos que motivan la cola (verificados por Claude, solo lectura)

| # | Hallazgo | Efecto |
|---|---|---|
| H-a | `scripts/tl3_t8_fomc.py:32`: `SWAP_BPS = 7.33 / 365 * 1e4` = **200,8 bps/noche**. Lo correcto es 7,33 % / 365 = **2,008 bps** (falta `/100`). Con el ×3 de los viernes (713 de 3260 días placebo), la σ del placebo neto sube de 94,08 a 190,12 bps | MDE real = 2,49 × 94,08 / √117 = **21,66 bps < 30**: T8 **pasa** la puerta de potencia. `rejected: no_power` (H-2026-009b) es **inválido**. No se calculó ningún retorno de evento (ni OpenCode ni Claude): la prueba sigue limpia |
| H-b | T8: el slippage se suma como `+ 1.0` punto MT5 (0,01 pt de índice) en vez de 0,5 pt de índice por lado | Solo afecta al neto (criterio b) |
| H-c | T8: el t de Welch del criterio (a) usa valores **netos**; el prerregistro dice diferencia **bruta** | Sesgo a favor de los eventos: el placebo neto carga los swaps triples de los viernes |
| H-d | T8: exige la barra exacta de 15:55 y de la salida; el prerregistro admite ±2 min. Las exclusiones evento × índice no se cuentan. `add_sample` solo registra US100 | El n de eventos puede variar ligeramente |
| H-e | T7: cobertura de sesión con 371 velas (≈ 99 %) en vez de 95 % (357) y sin comprobar la sesión anterior; exclusiones no contadas por año; "Sesiones válidas por cobertura: 2363" cuenta todo el fichero 2011-2026, no la ventana (en la ventana: **1077 de 2334**) | El veredicto **no** cambia: con la regla del prerregistro hay ~1128 sesiones válidas (+51); para llegar a 0,10 R harían falta ~2,8 R de media en cada operación añadida. **Sin reejecución** |
| H-f | T7: 2012, 2016 y 2017 tienen **0** sesiones válidas y 2015 solo 37. Dukascopy US100 antes de 2018 trae ~450 velas nocturnas (18:00-09:29), frente a 930 desde 2018, y la regla prerregistrada del 80 % nocturno las excluye | La muestra efectiva es **2013-2014 + 2018-2021**, no "2012-2021" |
| H-g | T5-bis usó las **48 primeras por id** de una relectura con 50 operaciones: incluye la #52 (cerrada a las 17:00 UTC, después de T5) y excluye la #53, que T5 sí tenía. El conjunto de T5 = las 50 menos #52 y #54, y reproduce exactamente IA 0,2953, gemela 0,2594, tendencia 0,3179 y real 0,0479 | Las cifras de T5-bis (+0,0637 / +0,2664 / −0,2027) no corresponden a las 48 de T5; la etiqueta "R simulado medio (IA, T5)" es incorrecta |
| H-h | T5-bis: las #3 y #5 duran 1 s con `pnl` = 0 (probablemente no ejecutadas). La descomposición no atribuye el gap en R, "+2,05 unidades" mezcla símbolos distintos y falta la tabla de motivos de salida | La conclusión "se explica por ejecución" no está cuantificada |
| H-i | `TL3_RESULTS_CICLO1.md` y `RESULTADO-TL3.md` dicen a la vez T7/T8 "Bloqueado — no se ejecutó" y `rejected`. Las recomendaciones siguen diciendo que T7 espera el registro, la fila T11 está sobrescrita y falta la fila de T5-bis. "?0,0296" (signo perdido) aparece también en `edge_map_tl3.md`. README §11 sigue diciendo T7/T8 bloqueados | Corrección documental |
| H-j | Las filas `H-2026-008b` y `H-2026-009b` copian el `created_at` del padre | No se puede fechar el veredicto; las filas nuevas usan la hora actual |

## 3. Bloques

### C0 · Commit de la cola
`git add -f .orquestador/COLA-TL3-C.md`; commit `tl3: C0 - cola TL3-C`.

### C1 · T5-bis rehecho (descriptivo, no suma)
1. Fuente: `TL3_REPORTS/ai_trader_t5_rows.json` (sin MT5). Conjunto = **las 48 de T5** = todas menos
   `id` 52 y 54. Antes de seguir, comprueba que reproduce IA 0,2953, gemela 0,2594, tendencia 0,3179
   y real 0,0479 (±0,0001). Si no, `bloqueado: conjunto de T5 no reproducible` y sigue con C2.
2. Por operación, en R de la simulación (distancia de SL de la propia operación; `side` = +1 compra,
   −1 venta):
   - entrada: `side × (sim_entry − real_entry) / dist_SL` (positivo = la real entró mejor);
   - costes: coste real implícito − coste del modelo, en R;
   - salida y resto: `gap − entrada − costes`. Si la definición de R real (`risk_usd`) no se puede
     aislar, escribe "Sin datos" y queda dentro del resto;
   - motivo de salida real: TP si |exit − tp| ≤ 2 × spread; SL si |exit − sl| ≤ 2 × spread; forzoso
     si `real_exit_ts` está a ≤ 2 min de `forced`; si no, otro. Motivo simulado: inferido del R simulado
     (TP / SL / forzoso). Tabla de coincidencias;
   - marca como `posible no ejecutada` toda operación con duración ≤ 5 s y `pnl` = 0 (#3 y #5).
3. Informe: sobrescribe `TL3_REPORTS/ai_trader_sim_vs_real.md` con una nota arriba ("Rehecho en TL3-C:
   la versión de 134f7c9 usó otro conjunto de 48; ver COLA-TL3-C H-g"). Debe incluir:
   - R real, R simulado y gap con IC95 (bootstrap 10.000, semilla 7), con y **sin** las posibles no
     ejecutadas;
   - descomposición media en R (entrada / costes / salida y resto) que sume exactamente al gap;
   - desglose por símbolo y por lado;
   - tabla de motivos de salida;
   - las 10 operaciones con mayor |gap|;
   - conclusión literal o "Sin datos".

   No se toca T5 ni `ai_trader`.
4. Commit `tl3: C1 - T5-bis rehecho`.

### C2 · T7: anexo de exclusiones (sin reejecutar)
1. No se ejecuta el motor ni se calcula ningún rendimiento. Se usa **solo la cobertura** de las velas M1.
2. Tabla por año 2012-2021 con:
   - días NYSE de la ventana;
   - válidos con la regla del script (371 velas, sin sesión anterior);
   - válidos con la regla del prerregistro (≥ 357 velas en 09:30-15:44 de la sesión **y** de la
     anterior; ≥ 744 velas de 18:00 a 09:29);
   - mediana de velas nocturnas.

   Referencia de Claude: script 1077 y prerregistro ~1128 de 2334; 2012, 2016 y 2017 = 0.
3. Añade a `TL3_REPORTS/ea_oop_dukascopy.md` una sección "Corrección TL3-C" con:
   - la desviación (371 frente a 357; sin sesión anterior) y la tabla;
   - "Sesiones válidas por cobertura en la ventana: 1077 de 2334 (el 2363 anterior contaba 2011-2026)";
   - la muestra efectiva (2013-2014 y 2018-2021);
   - la cota: el veredicto **no confirma** no puede cambiar.

   No se cambian el veredicto, el registro ni `scripts/tl3_t7_ea_oop.py` (es el código que produjo el
   resultado).
4. Commit `tl3: C2 - T7 anexo de exclusiones`.

### C3 · T8 corregido (solo con `APRUEBO REEJECUCIÓN T8`)
**Estatus.** Es la **misma** prueba prerregistrada (`COLA-TL3.md §4 T8`, con la enmienda de costes y la
decisión del operador). La ejecución de `972d916` se detuvo en la puerta de potencia por el error H-a y
no calculó ningún evento. **Contador:** la fila `TL3-T8` ya existente cubre esta ejecución; no se usa
`record-informal`.

1. Correcciones en `scripts/tl3_t8_fomc.py`, cada una con su test sintético, **antes** de ejecutar:
   1. `SWAP_BPS = 7.33 / 100 / 365 * 1e4` (2,008 bps/noche), ×3 si la entrada es viernes (como ahora).
   2. Slippage 0,5 punto de índice por lado: 1,0 punto de índice ida y vuelta = 100 puntos MT5 con
      `point` 0,01. Es la lectura conservadora de "0,5 pt/lado".
   3. Potencia: σ de la observación **bruta** del placebo (informa también la neta). Referencia de
      Claude, calculada solo sobre el placebo: σ bruta 94,07 bps; MDE ≈ 21,7 bps con 117 eventos.
   4. Criterio (a): t de Welch unilateral sobre la observación **bruta** (eventos − placebo). Criterio
      (b): LCB95 de la media **neta** de los eventos (bootstrap 10.000, semilla 42).
   5. Cobertura: barra M1 a ±2 min de 15:55 y de la hora de salida (la más cercana; si empatan, la
      anterior). Cuenta las exclusiones evento × índice.
   6. Registro: experimento nuevo `exp-t8-fix-…`, fila nueva `H-2026-009c` (padre `H-2026-009`) con
      `created_at` actual. `add_sample` para US500, US100 y US30.
2. Orden: σ y MDE primero; si MDE > 30 → `rejected: no_power` y no se calculan eventos. Si pasa,
   **una** evaluación de (a) y (b), sin mirar nada antes.
3. Informe: sobrescribe `TL3_REPORTS/h2_pre_fomc.md` con una nota arriba ("La versión de 972d916 es
   inválida: swap 100× mayor; ver COLA-TL3-C H-a"). Debe incluir:
   - n y exclusiones por índice;
   - σ bruta y neta, y MDE;
   - criterios (a) y (b) y el veredicto literal;
   - escalera bruto → neto de T4 (spread, slippage, swap);
   - tabla por año y por época (≤ 2015 / ≥ 2016), solo descriptiva;
   - placebo;
   - referencia a `literatura_T8_H1.md`;
   - la lectura fijada en la "Decisión del operador".
4. Anota en `RESULTADO-TL3.md`: "H-2026-009b invalidada por error de unidades del swap (TL3-C H-a)".
5. Commit `tl3: C3 - T8 corregido`.

**Sin aprobación:** no se toca el script. Anota H-a…H-d en `RESULTADO-TL3.md` y deja H-2026-009 como
"veredicto 009b inválido; T8 pendiente de reejecución aprobada".

### C4 · Documentos
1. `git checkout 352323d -- TL3_REPORTS/ai_trader_contrafactual.md` para volver a UTF-8 (mismo
   contenido).
2. `TL3_RESULTS_CICLO1.md` y `RESULTADO-TL3.md`, una fila por bloque con su estado real:
   - T5-bis con las cifras de C1;
   - T7 `Hecho — no confirma`, con la muestra efectiva de C2;
   - T8 con el resultado de C3 (o pendiente);
   - T11 como cierre 1b, y filas nuevas para el cierre 1c y el 1d.

   Actualiza también la tabla de hipótesis. Recomendación del EA: "T7 no confirma en 2013-2014 y
   2018-2021 con el coste prerregistrado; según la lectura fijada, alta probabilidad de ajuste o de
   dependencia de régimen; no se cambia el EA ni el riesgo".
3. Signos: en `TL3_REPORTS/*.md` y `RESULTADO-TL3.md`, cambia por "−" todo "?" que esté delante de
   un número y fuera un signo.
4. README §11 y PLAN: estado real de T5-bis, T7 y T8.
5. Commit `tl3: C4 - documentos corregidos`.

### C5 · Cierre
- `ruff check`, `pytest -q` completo, `lab doctor`, `lab propfund verify`.
- Commit `tl3: cierre ciclo 1d` y tag `tl3-ciclo1d`.

### C6 · Aviso
- Resumen a Telegram con `lab telegram send --file <resumen>`; si Telegram no está configurado,
  `lab alerts send`. Formato **Hecho / 1..N / Aviso / Siguiente**, con:
  - la conclusión de T5-bis rehecho;
  - la corrección de T7;
  - el veredicto de T8 (o "pendiente");
  - `count_tests` (debe seguir en 1897);
  - los tests y los bloqueos, si los hubo.
- Fin de esta cola. **Después, sin pedir confirmación, sigue con `.orquestador/COLA-TL3-D.md`
  (D0 → D7)**, aprobada por el operador el 2026-11-25.
