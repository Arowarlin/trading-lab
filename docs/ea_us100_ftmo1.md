# EA externo · US100 FTMO1

EA de MetaTrader 5 creado por el operador para `US100.cash`. El laboratorio lo
**observa y valida**, pero **no lo ejecuta ni envía órdenes por él**: el EA
corre dentro del terminal con su propio motor, su riesgo compartido y su magic.

## Identidad

| Campo | Valor |
|---|---|
| ID | `us100-ftmo1` |
| Cuenta | `ftmo_demo` |
| Símbolo | `US100.cash` |
| Magic | `93010001` |
| Magics gestionados | `93010001`, `93020001` |
| Timeframe | M5 |
| Estrategia | `us100_ftmo_confluence` |
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

### Filtros del laboratorio

| Filtro | Valor | Estado |
|---|---|---|
| Trades ≥ 100 | 480 | OK |
| DSR ≥ 0,90 | 1,00 | OK |
| PBO ≤ 0,30 | 0,241 | OK |
| Walk-forward | `ok` (Sharpe OOS 1,31; eficiencia 0,97) | OK |
| Regímenes 2021-2026 | todos positivos | OK |
| Spread observado | 145 points de mediana | OK |
| Coste con 2 puntos de slippage | +0,246 R | OK |

**Veredicto: PASA** los filtros. El punto más justo es el PBO (24,1 % frente al
30 % máximo); no es un margen enorme.

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
- El EA sigue en demo. Nada de esto es asesoramiento financiero ni una
  autorización para live.
