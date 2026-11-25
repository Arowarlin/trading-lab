# TL2-DIARIO · P1 Inventario y confirmacion

Generado: 2026-11-25. Solo lectura: no se modifico codigo en este bloque.

## 1. Construcciones de `PropRules` con `daily_loss_mode = higher_of_balance_or_equity`

| Fichero:linea | Quien | Estado |
|---|---|---|
| `config/propfund/firms.yaml:191` | `fundingpips_2step` (2-Step Standard) | `needs_verification`; nota: 5 % desde el MAYOR de balance o equidad al inicio del dia |
| `config/propfund/firms.yaml:239` | `fundingpips_trial` (Free Trial) | `verified_operator_panel_2026-11-23`; panel: Starting Equity 100.000 y Balance Threshold 95.000 |
| `config/propfund/accounts.yaml:107` | Cuenta `CFD-006` (FundingPips Trial, demo) | `limits.daily_loss_base: higher_of_balance_or_equity` |
| `scripts/tl3_d2_zero_edge.py:41-52` | Linea base D2 (FTMO y FundingPips) | Script de investigacion; construye las dos fases de FundingPips con ese modo |
| `src/tradinglab/prop/rules.py:13` | Tipo `DailyBase` | Declara el literal; no calcula nada |
| `src/tradinglab/propfund/snapshots.py:476-487` | `_rules_from_account` | Traduce `higher_of...` a `equity` y lo anota (E-3) |
| `tests/test_prop_n1.py:32-46` | Test de N1 | Construye el modo y hoy afirma el comportamiento antiguo (ver §7) |

`config/prop.yaml`, `config/prop_templates.yaml` y el resto de `config/prop*.yaml`: **ninguna** construccion con ese modo. `accounts.py::rules_for_account` no lo introduce por si mismo: solo lo heredaria de `prop.yaml`, que no lo usa.

## 2. Consumidores de `daily_loss_mode`

| Consumidor | Que hace con el modo | Efecto |
|---|---|---|
| `prop/simulator.py::monte_carlo` (86-87) | Rama `higher_of`: `max(initial, day_start) - eff_daily` | E-1: usa el balance **inicial**; toda cuenta 5 % por debajo del inicial rompe el diario |
| `prop/simulator.py::monte_carlo_program` (224-227) | Igual | E-1, mismas consecuencias por fase |
| `prop/guard.py::_bases` (98-110) | `balance` -> `day_start_balance`; cualquier otro modo -> `day_start_equity` | E-2: `higher_of` se trata como equidad; con perdida flotante a medianoche el suelo real queda por debajo del de la firma |
| `propfund/snapshots.py::_rules_from_account` (476-487) | `balance` -> `balance`; todo lo demas -> `equity`; anade nota | E-3: la cuenta CFD-006 se evalua como equidad |
| `propfund/risk.py::check_account` (96-108) | **No lee el modo**: `day_loss = day_start_equity - equity` y compara con `lim.daily_loss * buffer` | Para `higher_of` es laxo (equidad), igual que E-2. No hay `day_start_balance` en `AccountSnapshot` |
| `prop/overlay.py::apply_overlay` (81-110) | **No lee el modo**: recibe `max_daily_loss_pct` y mide desde la primera equidad del dia | No modela balance; para `higher_of` es laxo por construccion |
| `prop/defense.py::DailyLossGuard` (225-245) | **No lee el modo**: usa `day_start_equity` opcional o la primera equidad observada | Igual: no hay entrada de balance |
| `web.py:1371` | Muestra `rules.daily_loss_mode` como "Base del limite diario" | Solo presentacion; no calcula |
| `cli.py:6308` | Muestra `rules.daily_loss_mode` | Solo presentacion; no calcula |

Conclusion de P1.1: los dos motores que **calculan** con el modo son `simulator` y `guard`. `overlay`, `defense` y `risk` no reciben el modo ni un balance de inicio de dia; anadir ese soporte exigiria cambiar sus firmas y la fuente de datos (no solo pasar el modo).

## 3. Informes con cifras de FundingPips calculadas con el modo antiguo

| Informe | Cifras afectadas |
|---|---|
| `TL3_REPORTS/propfund_zero_edge.md` | 9 filas de FundingPips 2-Step. Ejemplos: b=1, riesgo 0,25 % -> P(diario) 18,36 %; b=2, 0,25 % -> 32,86 %; b=3, 1,00 % -> 67,68 %. La P(diario) es practicamente toda la P(romper) |
| `reports/ea/p-pasar-oficial.md` | FundingPips 2-Step: backtest 0,25 % -> P(pasar) 95,66 %, P(romper) 4,34 %; al 0,35 % -> P(pasar) 87,52 % (rompe 12,5 %); mitad y LCB95 -> "ninguno". El texto (linea 35) afirma la base `max(balance, equity)` que el simulador no aplicaba |

Menciones sin cifras (no se reescriben): `docs/CHANGELOG-produccion.md:143-145` (entrada historica), `.orquestador/RESULTADO-N1.md:27` y `.orquestador/RESULTADO-cola-tl2-noche3.md:23`. El generador de `p-pasar-oficial.md` no esta en `scripts/` (**Sin datos**): el informe se produjo con un script no versionado.

## 4. Confirmacion sintetica con el codigo actual (sin modificarlo)

Reglas FundingPips: 100.000 USD, 5 % diario, 10 % estatico, base `higher_of_balance_or_equity`, `buffer_pct` = 0, sin dias minimos. Camino determinista de 30 dias con -0,25 % diario (compuesto).

| Horizonte | Equidad final | `monte_carlo` P(romper) | `monte_carlo_program` P(romper) |
|---:|---:|---:|---:|
| 20 dias | 95.116,99 | 0 % | 0 % |
| 21 dias | 94.879,20 | **100 %** | **100 %** |
| 30 dias | 92.765,64 | 100 % | 100 % |

Se reproduce E-1: con el codigo actual la cuenta rompe el "diario" al cruzar -5 % del balance inicial (dia 21). Con la regla correcta (`day_start - eff_daily`) no hay rotura: ningun dia pierde 5 % y el suelo estatico (90.000) queda por debajo de 92.765,64 al dia 30.

**Interpretacion de la regla:** no aparece en el repositorio ningun texto oficial de FundingPips que mida el 5 % desde el balance inicial. `firms.yaml` (panel del operador 2026-11-23) y `accounts.yaml` dicen "el MAYOR de balance o equidad al inicio del dia". La cola no se bloquea.

## 5. Golden de los modos `balance`/`equity`

Fichero `tests/data/prop_daily_golden.json`, generado con el codigo antiguo por `scripts/tl2_diario_golden.py` (semilla 42, `n_paths` 2.000):

- `monte_carlo` y `monte_carlo_program` con FTMO 2-Step (`balance`);
- FTMO 1-Step (`equity`);
- un caso sintetico `equity` con serie determinista de 90 dias (sin RNG);
- las 9 combinaciones b x riesgo de D2 en FTMO 2-Step.

15 casos en total. SHA-256 del fichero: `E40C78E5ECC67AF83A0057DD05DD9F6A4943BEE55E9248511F67E7808F5850A6`. Regenerarlo dos veces produce el mismo hash.

## 6. Decision sobre E-3 (`propfund/snapshots.py`)

P3.3 exige que **todos** los consumidores soporten el modo para pasar el literal. P1 muestra que `overlay`, `defense` y `risk` no leen el modo ni tienen balance de inicio de dia: darselo obliga a cambiar sus firmas y la fuente de datos (curva de balance, no solo de equidad), mas que un cambio minimo. Por tanto, **no se toca `snapshots.py`**; E-3 queda anotado como pendiente en `docs/CHANGELOG-produccion.md`.

## 7. Test preexistente que codifica el comportamiento antiguo

`tests/test_prop_n1.py::test_fundingpips_usa_max_balance_equity_en_el_reinicio` afirma que dos dias de -3 % rompen con `higher_of`. Con la regla correcta no rompen (el suelo del segundo dia es 97.000 - 5.000 = 92.000 y la equidad es 94.090). El test se corrige en P4 junto con los tests de regresion; no es un cambio de produccion.

## 8. Limites

- No se ejecuto ninguna simulacion de estrategia real ni se sumo al contador.
- `Sin datos`: generador de `reports/ea/p-pasar-oficial.md` y curva historica de balance por dia de CFD-006.


## 9. Antes / despues de las 9 filas de FundingPips (P4.3)

Mismas reglas y mismos retornos sinteticos de D2 (5.000 caminos, 180 dias por fase, semilla 42). La unica diferencia es la base del limite diario.

**Antes** (codigo con `max(initial, day_start)`; valores de `propfund_zero_edge.md`):

| b | Riesgo | P(fase 1) | P(fase 2) | P(financiada) | P(romper) | P(diario) | P(total) | Dias |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0,25% | 1,96% | 0,24% | 0,24% | 18,36% | 18,36% | 0,58% | 253,0 |
| 1 | 0,50% | 19,86% | 7,40% | 7,40% | 61,28% | 61,28% | 21,66% | 173,5 |
| 1 | 1,00% | 36,30% | 17,30% | 17,30% | 82,08% | 82,08% | 63,08% | 66,0 |
| 2 | 0,25% | 10,70% | 2,94% | 2,94% | 32,86% | 32,86% | 4,10% | 226,0 |
| 2 | 0,50% | 34,10% | 15,86% | 15,86% | 75,46% | 75,46% | 38,84% | 113,0 |
| 2 | 1,00% | 37,66% | 18,00% | 18,00% | 82,00% | 82,00% | 65,34% | 34,0 |
| 3 | 0,25% | 19,10% | 7,18% | 7,18% | 46,82% | 46,82% | 9,76% | 186,0 |
| 3 | 0,50% | 35,88% | 16,74% | 16,74% | 80,88% | 80,88% | 52,54% | 80,0 |
| 3 | 1,00% | 37,02% | 17,32% | 17,32% | 82,68% | 82,68% | 67,68% | 24,0 |

**Despues** (codigo corregido, base `day_start`):

| b | Riesgo | P(fase 1) | P(fase 2) | P(financiada) | P(romper) | P(diario) | P(total) | Dias |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0,25% | 1,96% | 0,24% | 0,24% | 0,58% | 0,00% | 0,58% | 253,0 |
| 1 | 0,50% | 20,50% | 8,22% | 8,22% | 21,66% | 0,00% | 21,66% | 180,0 |
| 1 | 1,00% | 46,82% | 28,04% | 28,04% | 63,08% | 0,00% | 63,08% | 90,0 |
| 2 | 0,25% | 10,72% | 2,98% | 2,98% | 4,10% | 0,00% | 4,10% | 226,0 |
| 2 | 0,50% | 39,68% | 22,46% | 22,46% | 38,84% | 0,00% | 38,84% | 135,0 |
| 2 | 1,00% | 53,12% | 33,92% | 33,92% | 65,34% | 0,00% | 65,34% | 53,5 |
| 3 | 0,25% | 19,38% | 7,50% | 7,50% | 9,76% | 0,00% | 9,76% | 188,0 |
| 3 | 0,50% | 45,86% | 28,06% | 28,06% | 52,54% | 0,00% | 52,54% | 110,0 |
| 3 | 1,00% | 52,30% | 32,26% | 32,26% | 67,68% | 0,00% | 67,68% | 36,0 |

Lectura: la P(diario) pasa de 18,36-67,68 % a **0** en las 9 filas; con riesgo 0,25 % al dia no hay ninguna rotura diaria. La P(total) no cambia (esas corridas aislan el limite total), y la P(financiada) sube porque los caminos que antes morian por el diario falso ahora siguen. El unico limite que sigue mordiendo es el 10 % estatico.
