# EA externo · US100 FTMO1

EA de MetaTrader 5 creado por el operador para `US100.cash`. El laboratorio lo
**observa y valida**, pero **no lo ejecuta ni envía órdenes por él**: el EA
corre dentro del terminal con su propio motor, su riesgo compartido y su magic.

## Identidad

| Campo | Valor |
|---|---|
| ID | `us100-ftmo1` |
| Cuenta actual | `ftmo_demo` (demo) |
| Cuenta dedicada | `ftmo_trial_ea` (registrada y `blocked` hasta abrir el trial) |
| Símbolo | `US100.cash` |
| Magic | `93010001` |
| Magics gestionados | `93010001`, `93020001` |
| Timeframe | M5 |
| Estrategia | `us100_ftmo_confluence` |
| Versión | **v3.1** (cierre efectivo en cierres tempranos) |
| Setfile | `US100_FTMO_v3_challenge.set` |
| Ruta | `MQL5/Experts/TradingLab/US100_FTMO1` |

Registro: `config/mt5_eas.yaml`. El EA no está en `bots.yaml` para que el
orquestador no intente ejecutarlo como si fuera un bot Python.

### Cómo activarlo en MT5

El laboratorio no adjunta EAs a gráficos. En el terminal:

1. Abre `US100.cash` en M5.
2. Arrastra `US100_EA` desde `MQL5/Experts/TradingLab/US100_FTMO1`.
3. Entradas → Cargar → `US100_FTMO_v3_challenge.set`.
4. Activa **Algo Trading**. El setfile ya trae `InpDynRisk=true`.
5. Si el EA estaba puesto antes de recompilar, quítalo y vuelve a arrastrarlo
   para que MT5 cargue el `.ex5` nuevo.

También queda una plantilla con el EA y el setfile v3 ya cargados:

```text
MQL5/Profiles/Templates/TradingLab_US100_v3.tpl
```

En MT5: clic derecho en el gráfico → **Plantillas** → `TradingLab_US100_v3`.
La plantilla abre US100.cash M5, adjunta `US100_EA` y carga los inputs de v3;
solo falta activar **Algo Trading**. La copia versionada está en
`integrations/mt5/us100_ftmo1/TradingLab_US100_v3.tpl`.

## Consola y Diario

```powershell
lab ea list
lab ea status us100-ftmo1
```

- `lab ea status` muestra archivos, setfile, posiciones del magic y últimos
  fills.
- El magic se traduce a `ea:us100-ftmo1` en el Diario/TCA
  (`lab_magic_map`), así que sus deals no se confunden con `manual`.
- En la consola web aparece como tarjeta **externo MT5**, solo lectura, sin
  botones de archivar ni evaluar.

## Cuenta dedicada y FTMO Free Trial

El EA sigue en `ftmo_demo` con los controles compartidos. Para separarlo se
reservó `ftmo_trial_ea` en `config/accounts.yaml` con las reglas del challenge
FTMO 100k, pero **`status: blocked`**: mientras esté bloqueada, el guardián no
exporta esa cuenta y `PropGuard`, el forward y `ai_trader` rechazan operarla.
No se inventó una cuenta que todavía no existe.

Pasos para abrir el trial y mover el EA:

1. Abre un **FTMO Free Trial** nuevo de 100.000 USD y anota login, servidor y
   terminal. No uses una cuenta real.
2. Instala el segundo terminal en una ruta distinta (por ejemplo
   `C:\Program Files\FTMO MetaTrader 5 Trial`).
3. Copia la plantilla `TradingLab_US100_v3.tpl` a
   `MQL5/Profiles/Templates/` de ese terminal y el EA/setfile a
   `MQL5/Experts/TradingLab/US100_FTMO1/`.
4. Abre `US100.cash` M5, aplica **Plantillas → TradingLab_US100_v3**, carga
   `US100_FTMO_v3_challenge.set` y activa **Algo Trading**.
5. En `config/accounts.yaml` cambia `ftmo_trial_ea.status` de `blocked` a
   `demo` y revisa que `account_size` sea 100.000.
6. En `config/mt5_eas.yaml` cambia `account: ftmo_demo` por
   `account: ftmo_trial_ea` en `us100-ftmo1`. El guardián y el stop de cuenta
   empiezan a usar los magics de esa cuenta en la siguiente exportación.
7. En `config/ops.yaml` apunta `mt5.terminal_path` al terminal del trial y
   reinicia los procesos del lab que hablan con MT5.

**Dos terminales a la vez:** el paquete `MetaTrader5` inicializa un solo
terminal por proceso (`mt5.initialize(path=...)`); no mantiene dos conexiones
simultáneas. El laboratorio usa un broker por proceso, así que hay dos rutas:

- **Recomendada:** un proceso por terminal (por ejemplo, el forward del EA en
  el trial y los bots del lab en `ftmo_demo`), cada uno con su
  `mt5.terminal_path`.
- **Alternar:** si solo hay un proceso, cambia `terminal_path`, reinicia y
  asume que durante la ventana de cambio el otro terminal no se lee. El EA
  sigue operando dentro de su terminal; el lab solo deja de observarlo.

Mientras el trial no exista, no se toca `status`: la cuenta queda `blocked`.
El EA puede seguir en `ftmo_demo` porque el stop de cuenta y el tope por
símbolo ya incluyen sus magics.

## Controles de riesgo compartidos

- **Guardián:** `tradinglab_guardian.json` incluye los `managed_magics` de todos
  los EAs de `config/mt5_eas.yaml` cuya `account` sea la del guardián. Hoy son
  `93010001` y `93020001`, además de los magics del forward y de `ai_trader`.
  Una cuenta `blocked` no se exporta.
- **Stop diario de cuenta:** `account_daily_report` suma la pérdida realizada y
  el flotante de los magics del lab **y** de los EAs. Si el stop se toca por el
  EA, el lab no cierra sus posiciones (no son suyas): bloquea las aperturas de
  sus carriles, escribe una acción `account_stop` en `console_actions`, alerta
  con severidad `critical` una sola vez al día y deja `stop_cause=ea`.
- **Tope por símbolo:** `ftmo_demo.symbol_risk_caps["US100.cash"] = 0.02`
  (2.000 USD sobre 100.000). El riesgo abierto se mide como
  `|entrada − SL| × volumen × (tick_value / tick_size)` para todos los magics
  del lab y del EA en ese símbolo. `PropGuard`, el forward y `ai_trader` rechazan una
  apertura que supere el tope; `lab doctor` muestra el riesgo abierto por
  símbolo y marca WARN si está por encima.

## Forward pre-registrado

El forward del EA está congelado en `lifecycle` **antes** de contar, con hash
`2bfad45ca4ba36fc`. El reloj no arranca hoy: arranca el primer día con un fill
real del EA (`start_date` queda `NULL` hasta entonces).

| Criterio | Umbral |
|---|---|
| Ventana | 60 días o 40 operaciones (lo que llegue después) |
| Profit factor | ≥ 1,15 |
| Expectativa | ≥ +0,10 R |
| Drawdown | ≤ 6 % |
| Slippage medio | ≤ 2 puntos |
| Breaches del guardián | 0 |
| Coincidencia de entradas con el motor | ≥ 90 % |

La coincidencia compara cada operación forward con la que predice
`ea_us100_engine` para la misma vela M5 (misma dirección y entrada a ±5 min).
`lab ea forward us100-ftmo1` muestra el estado, el hash y las métricas; no
ejecuta el EA ni envía órdenes.

## Horizonte del challenge

`lab ea horizon us100-ftmo1` simula FTMO 100k con los retornos diarios del
motor v3, sin optimizar ni probar variantes nuevas. El horizonte “sin límite”
se corta a 750 días, el máximo práctico de `exposure_sweep`. Informe completo
en `reports/research/ea_us100_ftmo1/horizon.md`:

| Riesgo | Horizonte | P(pasar) | P(breach) | Mediana días | EV neto |
|---|---|---:|---:|---:|---:|
| 0,35 % fijo | 21 d | 1,98 % | 0,00 % | 18 | −490 EUR |
| 0,35 % fijo | 60 d | 34,46 % | 0,08 % | 42 | +326 EUR |
| 0,35 % fijo | 120 d | 75,72 % | 0,44 % | 64 | +1.364 EUR |
| 0,35 % fijo | sin límite | 99,28 % | 0,72 % | 77 | +1.956 EUR |
| Dinámico v3 | 21 d | 21,92 % | 0,42 % | 15 | +369 EUR |
| Dinámico v3 | 60 d | 68,00 % | 3,08 % | 29 | +2.279 EUR |
| Dinámico v3 | 120 d | 89,46 % | 4,54 % | 37 | +3.168 EUR |
| Dinámico v3 | sin límite | 95,06 % | 4,94 % | 39 | +3.400 EUR |

El riesgo dinámico sube la probabilidad de pasar y también el breach; no se
cambió el setfile ni se activó nada por este informe.

## Validación con el laboratorio

El motor Python `tradinglab.ea_us100_engine` es la réplica del EA incluida por
el operador. `lab ea validate` carga 366.847 velas M5 (2017-12-28 → 2026-11-13),
las pasa a hora de Nueva York y ejecuta el setfile.

```powershell
lab ea validate us100-ftmo1
lab ea optimize us100-ftmo1
```

Resultado de la base **v3 challenge** (2021-09-15 → 2026-11-13):

| Métrica | Valor |
|---|---|
| Operaciones | 480 |
| Win rate | 33,8 % |
| Profit factor | 1,45 |
| Expectancy | +0,298 R |
| Total | +143,2 R |
| DD máximo | 24,8 R |

Esta tabla es la base **v3**. La v3.1 cambia solo el cierre de los días de
cierre temprano: 481 operaciones y +146,8 R (ver la sección v3.1).

### Filtros del laboratorio

| Filtro | Valor | Estado |
|---|---|---|
| Trades ≥ 100 | 480 | OK |
| DSR local (N=8) ≥ 0,90 | 0,9994 | OK informativo |
| DSR global (N=1042) ≥ 0,90 | 0,634 (653 Sharpes diarios) | FALLO |
| PBO ≤ 0,30 | 0,241 | OK |
| Walk-forward | `ok` (Sharpe OOS 1,31; eficiencia 0,97) | OK |
| Regímenes 2021-2026 | todos positivos | OK |
| Spread observado | 145 points de mediana | OK |
| Coste con 2 puntos de slippage | +0,246 R | OK |

**Veredicto: NO PASA.** El resto de filtros está OK, pero el DSR global es
**0,634 < 0,90**: usa N = `count_tests` (1042) y la dispersión de 653 Sharpes
diarios registrados (460 celdas de campaña, 192 resultados de research y el
informe del EA). El DSR local (0,9994, N=8) es solo informativo y no sustituye
al global. El punto más justo es el PBO (24,1 % frente al 30 % máximo); no es un
margen enorme.

El DSR v2 usa `dsr_from_returns` con Sharpe, dispersión, asimetría y curtosis
**por periodo**. El 1,0 anterior era `dsr_v1_invalid_units` (Sharpe anualizado
con `n_obs` diario) y se conserva en los informes históricos, pero no debe usarse
como evidencia.

### Comprobación independiente en MT5

El operador ya había corrido el EA en el Strategy Tester con **ticks reales**,
US100.cash M5, 2022-01-01 → 2026-11-14, depósito 100.000 USD y el setfile v3
(`US100_EA.US100.cash.M5.20220101_20261114.400.ini`):

| Métrica MT5 | Valor |
|---|---|
| Operaciones | 445 |
| Profit factor | 1,50 |
| Beneficio neto | +50.845 USD (+50,8 %) |
| DD de equity máximo | 4,74 % (5,43 % relativo) |
| Sharpe | 1,08 |
| Recovery factor | 7,26 |

Coincide con el motor Python (480 operaciones en 2021-2026; 446 en 2022-2026)
y con la expectativa positiva. Esa prueba usó el riesgo fijo del 0,35 %, no la
escalera dinámica; el setfile v3 ya trae `InpDynRisk=true` para el EA
recompilado.

### Por año (base v3, 0,35 % de riesgo)

| Año | Retorno | Sharpe | DD |
|---|---|---|---|
| 2021 (sep-dic) | +1,54 % | 0,42 | −2,48 % |
| 2022 | +21,66 % | 2,80 | −2,43 % |
| 2023 | +1,04 % | 0,20 | −5,70 % |
| 2024 | +10,15 % | 1,47 | −3,72 % |
| 2025 | +6,82 % | 1,09 | −4,82 % |
| 2026 (ene-nov) | +11,15 % | 1,73 | −3,47 % |

2023 sigue siendo el año débil; pasa el filtro por poco.

### Monte Carlo 21 días

- Pasar +10 %: **0,02 %**
- Tocar −5 %: **0,00 %**
- DD mediano: −1,06 %
- Peor DD: −3,84 %

La ventaja es de proceso, no de “pasar el Challenge en 30 días”. El propio
README del EA ya lo advertía.

## v3.1 · cierre efectivo en cierres tempranos

La v3 cerraba solo si llegaba un tick con la hora NY entre `InpFlatAt` (15:45)
y las 18:00. En un cierre temprano no hay ticks en esa ventana: la posición
sobrevivía a la sesión siguiente. La réplica lo detectó en **2 de 480**
operaciones (3-jul-2025 y 3-jul-2026), que se quedaron dentro hasta el SL.

La v3.1 cambia solo la salida forzosa:

- **Cierre efectivo** = `min(InpFlatAt, fin_de_sesión − 10 min)`.
- El fin de sesión se lee de `SymbolInfoSessionTrade` para el día actual.
- Si la lectura falla, se usa el calendario `InpEarlyClose`; si tampoco hay
  entrada, se queda `InpFlatAt`.
- El calendario también se aplica cuando la lectura funciona pero el bróker
  publica una sesión semanal fija que no conoce el cierre puntual (es el caso
  de los índices CFD): siempre se toma el mínimo.
- En la réplica Python no existe `SymbolInfoSessionTrade`: el calendario NYSE
  hace de fin de sesión y el resto de la regla es idéntico.
- **Entradas nuevas:** se bloquean si quedan menos de **60 minutos** hasta el
  cierre efectivo. En este setfile la ventana termina a las 11:00, así que la
  regla no recorta ninguna entrada; queda como protección para otros horarios.

Formato del input (coma entre fechas, `YYYYMMDD:HHMM`):

```text
InpEarlyClose=20211126:1300,20221125:1300,20230703:1300,20231124:1300,20240703:1300,20241129:1300,20241224:1300,20250703:1300,20251128:1300,20251224:1300,20260703:1300,20261127:1300,20261224:1300
```

También acepta `=` y `;` como separadores. El setfile v3 ya trae el calendario
cargado; no se cambió ningún otro input.

### Réplica v3.1 (mismos parámetros, counted=0)

| Métrica | v3 | v3.1 | Δ |
|---|---:|---:|---:|
| Operaciones | 480 | **481** | +1 |
| Win rate | 33,8 % | **34,1 %** | +0,3 pp |
| Profit factor | 1,45 | **1,46** | +0,01 |
| Expectancy | +0,298 R | **+0,305 R** | +0,007 R |
| Total | +143,2 R | **+146,8 R** | **+3,6 R** |
| DD máximo | 24,8 R | 24,8 R | 0 |
| Operaciones que cruzan noche | 2 | **0** | −2 |

Las tres operaciones que cambian:

| Entrada | Lado | v3 | v3.1 | Δ |
|---|---|---:|---:|---:|
| 2025-07-03 10:00 | largo | −1,0149 R (SL 04-jul 03:15) | **+2,0427 R** (EOD 12:50) | +3,0576 R |
| 2026-07-03 09:50 | corto | −1,0172 R (SL 05-jul 18:20) | **+0,5037 R** (EOD 12:50) | +1,5209 R |
| 2025-07-04 09:50 | largo | — | **−1,0229 R** (SL 12:40) | −1,0229 R |

La tercera operación es una cascada: en v3 el SL del 3-jul cerraba el 4-jul a
las 03:15 y contaba como primera pérdida consecutiva del día 4; con v3.1 el
3-jul cierra como ganancia y `InpMaxConsecLoss=1` ya no bloquea la entrada del
4-jul. El balance neto sigue siendo **+3,6 R**. Informe completo:
`reports/research/ea_us100_ftmo1/early_close.md`.

La rejilla de 8 variantes y la tabla de optimización siguen siendo la base v3;
no se reejecutaron.

### Cómo compilarlo y probarlo en el Strategy Tester

1. Copia `US100_EA.mq5`, `US100_EntryManager.mqh` y `US100_ExitManager.mqh` a
   `MQL5/Experts/TradingLab/US100_FTMO1` y compila `US100_EA.mq5` en MetaEditor.
   Debe terminar con **0 errores y 0 warnings**. El `#property version` es
   `3.10`.
2. Abre `US100.cash` M5 y carga `US100_FTMO_v3_challenge.set`. Comprueba en
   Entradas que `InpEarlyClose` trae el calendario y que `InpFlatAt=1545`.
3. Strategy Tester: símbolo `US100.cash`, M5, **Every tick based on real
   ticks**, depósito 100.000 USD, modo *Every tick* y el setfile v3.
4. Primera prueba: **2025-07-01 → 2025-07-04**. El panel debe mostrar
   `cierre efectivo 12:50` el 3-jul. En el Diario busca
   `Fin del horario operativo` y comprueba que la posición del 3-jul se cerró
   antes de las 13:00 NY y que no hay ningún deal del mismo ticket el 4-jul.
5. Segunda prueba: **2024-11-27 → 2024-11-30** (Black Friday **29-11-2024**).
   Mismo control: cierre ≤ 12:50 NY y cero posiciones al día siguiente.
6. Si el tester no tiene ticks en la ventana, el `OnTimer` también llama al
   cierre; aun así, la prueba válida es con ticks reales.

El calendario cubre los cierres tempranos de NYSE 2021-2026. Si el bróker
añade un cierre puntual, se añade una línea `YYYYMMDD:HHMM` al input; no hace
falta recompilar.

La copia versionada se compiló con MetaEditor64 el 2026-11-16: **0 errores,
0 warnings**. El `.ex5` se genera al compilar en el terminal; no se versiona.

## Optimización

`lab ea optimize us100-ftmo1` barre una vecindad acotada y **congelada** del
setfile v3, sin cambiar el umbral de score 55:

| score | RR | gap | consec | Ops | Exp. | PF | Total R |
|---|---|---|---|---|---|---|---|
| 55 | 3.0 | 0.5 | 1 | 546 | +0.214 | 1.32 | +116.7 |
| 55 | 3.0 | 0.5 | 2 | 607 | +0.168 | 1.25 | +102.1 |
| 55 | 3.0 | 0.7 | 1 | 490 | +0.252 | 1.38 | +123.4 |
| 55 | 3.0 | 0.7 | 2 | 543 | +0.215 | 1.32 | +116.9 |
| 55 | 3.5 | 0.5 | 1 | 535 | +0.252 | 1.37 | +134.7 |
| 55 | 3.5 | 0.5 | 2 | 596 | +0.193 | 1.28 | +115.0 |
| **55** | **3.5** | **0.7** | **1** | **480** | **+0.298** | **1.45** | **+143.2** |
| 55 | 3.5 | 0.7 | 2 | 533 | +0.247 | 1.37 | +131.7 |

La variante del setfile v3 (última fila resaltada) es la mejor de la vecindad en
muestra completa y en In-Sample, y mantiene OOS positivo. No se recomienda
cambiar el setfile: la “optimización” confirma la v3, no la sustituye.

## Riesgo dinámico v3

El setfile v3 trae `InpDynRisk=true` y la escalera
`1,0 → 0,6 → 0,35 → 0,25 %` según drawdown estático desde el capital inicial
(2 %, 4 %, 6 %). El código original no tenía esos inputs; se añadieron a
`US100_EA.mq5` y `US100_RiskManager.mqh` y se compiló con MetaEditor:

```text
Result: 0 errors, 0 warnings
```

Con el riesgo dinámico, la simulación histórica da **+140,8 %** (equity
240.837), un DD máximo desde el pico de **−13,9 %** y **no** toca el kill
switch estático del 8 % desde el capital inicial. En 21 días, el Monte Carlo
sube la probabilidad de pasar a **1,74 %** (frente al 0,02 % con 0,35 % fijo) y
mantiene el breach en 0 %. Es más agresivo: úsalo solo si aceptas ese DD.
El EA sigue usando `InpRiskPct=0.35` como respaldo si `InpDynRisk=false`.

## Avisos

- La validación usa el motor Python, no el Strategy Tester con ticks reales.
  El README del EA reporta 103/106 operaciones coincidentes en su prueba.
- El filtro de gap y la selección de variantes tienen sesgo de selección; el
  walk-forward es la estimación más prudente.
- 2023 es plano y el PBO está cerca del límite. No subir riesgo por los
  resultados del backtest.
- La v3.1 cierra antes en los cierres tempranos, pero el calendario es una
  lista manual: si el bróker añade un cierre puntual, hay que añadirlo a
  `InpEarlyClose`. El `SymbolInfoSessionTrade` es la primera fuente; el
  calendario es la red de seguridad.
- El EA sigue en demo. Nada de esto es asesoramiento financiero ni una
  autorización para live.
