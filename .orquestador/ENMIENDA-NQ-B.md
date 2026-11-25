# ENMIENDA NQ-B · Referencia de validez, factor k y cambios de contrato

> **OPCIÓN A ELEGIDA** por el operador el 2026-11-25 a las 10:47 (hora local), en la sesión de Claude:
> «Opción A». Para OpenCode entra en vigor cuando el operador escriba en **su** sesión:
> **`APRUEBO ENMIENDA NQ-B OPCIÓN A`** (regla de `AGENTS.md`: aprobación en la misma sesión).
> Hasta entonces, OpenCode **PARA tras B1** (descarga) y no ejecuta B2 ni B3.
> Sustituye a B2 y B3 de `COLA-TL2-NQ-B.md`; B1 (descarga) no cambia.
> **Modo de ejecución (operador, 2026-11-25):** «quiero que una tarea se ejecute una detrás de la otra
> sin parar». Tras la aprobación, E0 → E4 corren **en cadena, sin pedir confirmación entre bloques**
> (ver §6).

- **Fecha:** 2026-11-25
- **Redacta:** Claude (auditoría TL3), a petición del operador
- **Escrita antes de ver ningún resultado de NQ.** Del archivo descargado solo se leyó el número de
  filas, el rango de fechas y las 3 primeras filas (precios de 2010-06-07), para confirmar que contiene
  NQ. No se ejecutó el motor ni se calculó ningún retorno sobre NQ.
- **Base:** `TL3_REPORTS/TL3_FORENSIC_AUDIT.md` (G-1, G-2).

## 1. Motivo (hechos)

| Hecho | Evidencia |
|---|---|
| La caché `data/cache/ea/US100_CASH_M5_NY.parquet` tiene **velas D1 en 2018–2020** y H1 en ene–sep 2021. El M5 real empieza el **2021-09-14** | Paso dominante de 1 día en 2018 (258 velas en el año); `reports/audit/ea_us100_m5_only.md §1` |
| La validez de NQ-A compara NQ 2018 con esa caché en 2018 (`scripts/ea_nq_out_of_period.py:36-39`, `:190-192`) | Con velas diarias, el EA no puede generar las entradas de 09:45–11:00: `matched_pct` ≈ 0 → "no válida" de forma mecánica |
| El factor `k` se calcula con el ATR14 de NQ M5 frente al ATR14 de esa caché en 2018, que es **diario** | `k` saldría muy por debajo de 0,9 y **reescalaría** `min_sl`, `max_spread` y `be_off` con un valor sin sentido |
| La premisa de NQ-A ("el backtest del EA empieza el 2017-12-28") es falsa: las operaciones del backtest empiezan en 2021-09 | `reports/ea/us100-ftmo1-v2.md §2` (478 ops desde 2021) |
| La regla de rolls solo descarta operaciones que **cruzan** un cambio de contrato. El EA usa el máximo/mínimo del día previo, el rango overnight y el gap: en la primera sesión tras un cambio, esos niveles vienen **del contrato anterior** (salto de base) | `fetch_databento.py`: `NQ.c.0` sin ajuste y sin columna de contrato |

Conclusión: tal como está, B2 termina en "no válida (Sin datos)" por un defecto de especificación, no
por el comportamiento del EA. Si se corrige **después** de ver ese resultado, sería una enmienda post
hoc. Por eso se corrige **ahora**.

## 2. Qué NO cambia

- Hipótesis: la lógica v3.2, sin cambios, tiene ventaja en el Nasdaq-100 en 2010–2017.
- Periodo de prueba: **2010-06-06 → 2017-12-27**. Una sola ejecución.
- Criterio de la prueba: **n ≥ 300, expectativa ≥ 0,10 R y LCB95 > 0** (bootstrap estacionario,
  bloque de 1 semana, 10.000 remuestreos, LCB = media − 1,645 × sd bootstrap).
- Umbrales de validez: **≥ 80 % emparejadas** (misma barra de entrada ±1, mismo lado) y **correlación
  de R ≥ 0,7**.
- Costes: perfil de spread por franja de 5 min NY de US100.cash; slippage 0,5 pt/lado; comisión 0.
- Cuenta: 1 prueba (ya registrada por el operador en `informal_trials`, id 3, "TL2-NQ: EA v3.2 fuera de periodo NQ 2010-2017, prerregistrado").
- EA, setfile, motor y `ea_lab/nq_adapter.py`: **sin cambios**. Todo lo nuevo va en
  `scripts/ea_nq_out_of_period.py`, reutilizando las funciones del adaptador tal como están.

## 3. Cambios propuestos

### 3.1 Referencia de validez · elegir UNA opción

#### Opción A (recomendada) · Cadena de dos eslabones, sin coste adicional

Las dos fuentes de referencia ya están en disco. Dukascopy US100 tiene el RTH completo en 2018 y 2022
(mediana de 390 velas M1 por sesión; los días por debajo de 350 son cierres tempranos).

| Paso | Comparación | Ventana | Datos | Si falla |
|---|---|---|---|---|
| **A-1 · Puente (sin NQ)** | Motor sobre **Dukascopy US100 M1 → M5 NY** (mismo `prepare_nq`: `resample_m5` + `apply_spread` con el mismo perfil) **frente a** motor sobre la caché US100.cash MT5 | **2022-01-03 → 2022-12-30** (primer año completo de M5 real) | Dukascopy + caché EA | "Prueba no válida (Sin datos)". **No se abre NQ** |
| **A-2 · Validez NQ** | Motor sobre **NQ** (adaptador) **frente a** motor sobre **Dukascopy US100** con el mismo procesado | **2018-01-02 → 2018-12-31** (solape original) | NQ + Dukascopy | "Prueba no válida (Sin datos)". No se mira 2010–2017 |

- Orden obligatorio: A-1 → A-2 → B3. **A-1 puede ejecutarse ya**, porque no usa NQ.
- A-1 es un control de paridad: solo informa `% emparejadas` y la correlación de R. **No informa
  expectativa, PF ni R totales** de 2022 (es la muestra de diseño del EA).
- A-1 sirve además como prerrequisito de la futura prueba fuera de periodo con Dukascopy 2011–2021
  (`TL3_US100_CASE_STUDY.md §6`).
- Recomendación de contabilidad: A-1 y A-2 son paridad y no suman pruebas. Lo decide el operador.

#### Opción B · Validez directa contra el bróker (coste adicional)
Descargar NQ **2022-01-01 → 2023-01-01** (estimar antes; orden de 1,1–1,3 USD por año según
`RESULTADO-NQ-A.md`) y validar NQ frente a US100.cash en 2022. Es el eslabón más directo, pero exige un
nuevo `OK DESCARGA <importe>` y deja 2018 sin uso.

#### Opción C · Parar NQ-B
Declarar NQ-B "Sin datos (referencia de validez inexistente)" y no ejecutar B2 ni B3. Priorizar la
prueba Dukascopy US100 2011–2021 (mismo tipo de instrumento). Los datos NQ quedan en disco para
futuros trabajos de futuros.

### 3.2 Factor de escala `k`
Se calcula **entre NQ y la misma referencia del eslabón que contiene NQ**: Dukascopy US100 M5 en
2018 (opción A) o US100.cash M5 en 2022 (opción B). Misma regla: sin escalar si `k ∈ [0,9; 1,1]`; si no,
la regla de E2, documentada. **Nunca** contra la caché del EA en 2018.

### 3.3 Cambios de contrato (aplica a A-2, B y la prueba 2010–2017)
1. Fechas de cambio de `NQ.c.0` desde la simbología de Databento (resolución `NQ.c.0` → `NQH0`,
   `NQM0`…; consulta de metadatos, **sin descarga de datos de mercado**). Si la consulta tiene coste o
   falla: no se repite y se usa automáticamente la regla de respaldo del punto 3, sin detener la cadena.
2. Se excluyen las **entradas** de la primera sesión NY posterior a cada cambio (niveles previos de otro
   contrato). Se aplica a **los dos lados** de la comparación de validez (mismas fechas) y a la prueba.
   Como el EA cierra siempre a las 15:45, filtrar las operaciones por sesión de entrada equivale a
   bloquear las entradas de ese día. **No hace falta tocar el adaptador.**
3. Regla de respaldo (calendario CME): excluir las entradas desde el jueves 8 días naturales antes del
   tercer viernes de mar/jun/sep/dic hasta la primera sesión posterior a ese viernes, ambos incluidos.
4. Se mantiene el descarte de operaciones que crucen un cambio (debería ser 0).
5. El informe cuenta las sesiones y operaciones excluidas por año.

### 3.5 Festivos y cierres tempranos fuera de 2021–2027 (añadido 2026-11-25 10:58, antes de E0)
- **Hecho:** `tradinglab/nyse_calendar.py`, que usa el motor del EA, solo cubre 2021–2027
  (`EARLY_CLOSES` de 20211126 a 20271126; `is_full_holiday(20120704)` = False). En 2010–2020 el motor no
  conoce festivos ni cierres tempranos: operaría en sesiones recortadas y no cerraría a las 13:00 en
  los cierres tempranos. NQ-A daba por hecho que el calendario los cubría.
- **Regla:** en A-2 (ambos lados) y en B3 se excluyen las operaciones cuya sesión de entrada sea
  festivo NYSE, cierre especial o cierre temprano según `discovery/calendars.py`
  (`nyse_holidays`, `nyse_early_closes`, `is_special_closure`, 2003–2030). No se toca el motor.
  Se cuentan por año.
- A-1 (2022) no cambia: el calendario del motor cubre 2022 en los dos lados.
- El filtro de noticias (`InpNewsFilter`) **no** está modelado en el motor (tampoco lo estaba en las
  478 operaciones del backtest). Se mantiene así y se declara en el informe.

### 3.4 Etiquetas
- El informe nombra los datos como **`NQ.c.0` (futuro CME, Databento GLBX.MDP3)**, aunque el archivo
  se llame `data/cache/databento/US100_M1.parquet`. Ningún otro proceso debe cargar ese archivo como
  US100 CFD.
- Al terminar, el operador decide si se hace una **copia** con nombre propio (`NQ_c0_M1.parquet`).
  No se mueve ni se borra el original.

## 4. Lectura prerregistrada del resultado

| Resultado | Qué significa | Qué NO significa |
|---|---|---|
| "No válida" en A-1 | El procesado Dukascopy no reproduce al bróker: tampoco sirve para la prueba Dukascopy 2011–2021 sin revisar el volumen/RVOL | Nada sobre la ventaja del EA |
| "No válida" en A-2 | NQ (futuro, volumen de contratos) no reproduce al CFD: la prueba NQ no es posible con este adaptador | Nada sobre la ventaja del EA |
| "Confirma" | La lógica v3.2 tiene ventaja en el Nasdaq-100 fuera del periodo de diseño, con costes tipo CFD modelados. Evidencia fuerte contra "solo es ajuste a 2021–2026" | Que el EA sea rentable en FTMO con sus costes reales: es otro instrumento |
| "No confirma" | La ventaja no aparece en 2010–2017 en NQ. Aumenta mucho la probabilidad de ajuste a 2021–2026 o de dependencia de régimen | Por sí solo, que el EA no tenga ventaja en US100.cash hoy |

Sin reinterpretaciones: no se cambian ventanas, umbrales, costes, `k` ni exclusiones después de ver
cualquier resultado de A-1, A-2 o B3.

## 5. Texto para OpenCode (lo pega el operador)

Solo si todavía no quieres aprobar (sustituido por el bloque siguiente):

```text
PARA tras B1. No ejecutes B2 ni B3. Lee .orquestador/ENMIENDA-NQ-B.md.
Espera a que el operador escriba "APRUEBO ENMIENDA NQ-B OPCIÓN <A|B|C>".
No mires el rendimiento de NQ en ningún periodo mientras tanto.
```

Con la opción A ya elegida, el operador envía **un solo mensaje** y la cadena corre hasta el final:

```text
APRUEBO ENMIENDA NQ-B OPCIÓN A. Ejecuta .orquestador/ENMIENDA-NQ-B.md §6
(E0 → E1 → E2 → E3 → E4) en cadena, SIN PARAR NI PEDIRME CONFIRMACIÓN entre
bloques. E0, E1 y E2 no necesitan NQ: empiézalos ya, mientras termina la
descarga. Los únicos desvíos son los del §6 (un fallo de validez salta a E4,
nunca a la prueba). No ejecutes B2 ni B3 de COLA-TL2-NQ-B.md: los sustituye
la enmienda. Contabilidad de A-1/A-2: paridad, no suma.
```

## 6. Implementación (OpenCode, solo tras `APRUEBO ENMIENDA NQ-B OPCIÓN A`)

Modelo: DeepSeek V4.1 Flash.

**Ejecución en cadena.** Los bloques corren uno detrás de otro **sin pausas ni preguntas al
operador**. No hay ningún "PARA" intermedio. La cadena solo cambia de rumbo en dos casos, y en los
dos **sigue hasta E4 y cierra**:

| Situación | Qué hace | Por qué no se continúa hacia la prueba |
|---|---|---|
| Fallo técnico (ruff, pytest, excepción) | Corrige y reintenta **hasta 3 veces** por bloque. Si sigue fallando: salta a E4 con estado "bloqueado: <error>" | Correr la prueba con código roto la gastaría |
| A-1 o A-2 por debajo del umbral | Salta a E4 con el veredicto "Prueba no válida (Sin datos)" | Es el **resultado** prerregistrado, no una pausa. Abrir 2010–2017 tras una validez fallida invalidaría la prueba |

**Espera de datos (no es una pausa).** E3 necesita la descarga completa de B1. Si al llegar a E3 la
descarga no ha terminado, comprueba cada 2 minutos que el proceso de descarga sigue vivo y que el
archivo crece. Cuando termine, continúa solo. Si el proceso muere sin terminar 2018: relanza **una vez**
el tramo pendiente con el mismo coste aprobado; si vuelve a fallar, salta a E4 con "bloqueado:
descarga incompleta".

**Prohibido:** cambiar el EA, el setfile, `ea_us100_engine.py` o `ea_lab/nq_adapter.py`; mirar
expectativa, PF o R totales de 2022, 2018 o 2010–2017 fuera del bloque que lo pide; ejecutar B3 más de
una vez; campañas, OOS, `confirm`, push, borrar u órdenes.

### E0 · Código y tests sintéticos (sin datos reales)
1. En `scripts/ea_nq_out_of_period.py`, añadir sin quitar nada:
   - `--reference-m1 PATH`: M1 de referencia procesado con `prepare_nq` (el mismo `resample_m5` +
     `apply_spread` que NQ). Con la opción A apunta a `data/cache/dukascopy/US100_M1.parquet`.
   - `--bridge`: ejecuta **solo** A-1 (referencia procesada frente a `--us100` en 2022-01-03 → 2022-12-30)
     y escribe `% emparejadas` y la correlación. **No calcula ni imprime** expectativa, PF ni totales.
   - `--roll-dates PATH`: JSON con las fechas de cambio de contrato; las operaciones cuya **sesión de
     entrada** sea la primera sesión NY tras un cambio se excluyen en **ambos** lados de A-2 y en B3.
     Se cuentan por año.
   - `k` (`atr_ratio`) se calcula entre NQ y la referencia de `--reference-m1` en 2018, nunca contra
     `--us100`.
   - Exclusión de festivos, cierres especiales y cierres tempranos NYSE (§3.5) en A-2 y B3, con
     `discovery/calendars.py`, en ambos lados y contadas por año.
   - El informe nombra los datos como `NQ.c.0 (futuro CME, Databento GLBX.MDP3)`.
2. Tests sintéticos: el puente no imprime métricas de rendimiento; la exclusión de sesiones de roll se
   aplica a los dos lados; `k` usa la referencia correcta; con `--us100` D1 en la ventana el script
   responde "Sin datos: granularidad" en vez de emparejar.
3. `ruff`, `pytest` dirigido. Commit `tl2: NQ-B - enmienda A (codigo)`. Si falla: regla de fallo
   técnico (3 reintentos). Sigue con E1.

### E1 · Fechas de cambio de contrato
1. Consulta de simbología de Databento para `NQ.c.0`, 2010-06-06 → 2019-01-01 (solo metadatos). Si la
   API indica coste o falla: no la repitas; genera las fechas con la regla de respaldo §3.3.3 y anótalo.
2. Guarda `.orquestador/nq-rolls.json` con la fuente (simbología o calendario). Sigue con E2.

### E2 · A-1 Puente (no usa NQ)
`--bridge --reference-m1 data/cache/dukascopy/US100_M1.parquet`. Tabla: operaciones de cada lado,
emparejadas, % y correlación. Si **≥ 80 %** y **correlación ≥ 0,7**: sigue con E3. Si no: anota
"Prueba no válida (Sin datos): el procesado Dukascopy no reproduce al bróker" y **salta a E4** (no abre
NQ).

### E3 · A-2 Validez NQ 2018 y B3 prueba 2010–2017 (una sola ejecución)
Script sin `--bridge`, con `--m1 data/cache/databento/US100_M1.parquet` (es NQ), `--reference-m1` y
`--roll-dates`, en cuanto la descarga esté completa. Si A-2 falla, el propio script no mira 2010–2017 y
la cadena salta a E4. Si pasa, B3 según `COLA-TL2-NQ-B.md` (tablas por año, slippage 0/0,5/1/2/3 pt,
`slip_eq`, excluidas por roll), veredicto literal según el §2. Sigue con E4.

### E4 · Cierre
`RESULTADO-NQ-B.md` con: opción A, coste real de la descarga, k, A-1, A-2, B3 y veredicto (o el estado
"bloqueado"/"no válida" y el bloque en que ocurrió). Commit `tl2: NQ-B - prueba fuera de periodo`, tag
`tl2-nq-b`, resumen a Telegram (Hecho / 1..N / Aviso / Siguiente). **Fin de la cadena.** No empieza
ninguna tarea que no esté en esta enmienda.

## 7. Firma del operador

- Opción elegida: **A** (2026-11-25 10:47, sesión de Claude; pendiente de confirmar en OpenCode)
- Contabilidad de A-1/A-2: ☑ **paridad, no suma** · ☐ suma 1 informal — decidido por el operador en
  la sesión de Claude: «Paridad, no suma»
- Fecha y hora de la aprobación en OpenCode: ____
