# RESULTADO · R9 — cierre Donchian H4, turn_of_month y diseño multi-símbolo

Fecha: 2026-11-23. Sesión única en `E:\trading-lab`, HEAD `86bd87d` + R9.
Sin registrar/aprobar/ejecutar campañas, sin OOS-1/OOS-2, sin push, sin tareas
programadas, sin operar, sin tocar MT5, sin descargar datos y sin activar bots.

## 1. Cierre de Donchian H4 en USDJPY

Informe: `reports/discovery/n2-donchian-usdjpy-h4.md`.

- Campaña `n2-donchian-usdjpy-h4`: 27/27 evaluadas, **0 finalistas**.
- Tabla de las 27 combinaciones con parámetros, operaciones, bruto/neto, largo
  vs corto y percentil de deriva guardado.
- Mejor por neto: **ID 500** (canal 40, vol 0.6, stop 1.5): 404 ops, bruto
  0.0753 R/op, neto 0.0470 R/op, percentil **85,0**; aun así no pasa el umbral
  90. Mediana por neto: ID 505 (canal 40, vol 0.7, stop 2.5), percentil 59,2.
- Bruto por año 2005–2024 de la mejor y la mediana (suma de R por año de
  entrada), en el informe.
- Conclusión: `donchian_vol_h4` queda **probada en XAUUSD y USDJPY H4**. En XAU
  la ventaja era deriva del oro (C2-informe); en USDJPY ninguna combinación
  alcanza el percentil 90. No se propone reabrir la misma rejilla; otra prueba
  debe ser otra hipótesis/filtro/régimen.

## 2. Plantilla `turn_of_month`

Archivo: `config/discovery/templates/turn_of_month.yaml`.

- Hipótesis literal en la plantilla y en las specs, escrita antes de calcular:
  "Los índices de EE. UU. concentran una parte desproporcionada de su
  rentabilidad entre el último día hábil del mes y los primeros días hábiles
  del siguiente, por flujos de nóminas, fondos y rebalanceos. Si es real,
  comprar en esa ventana supera a comprar en días aleatorios del mismo número
  y duración." Citas: Ariel (1987), Lakonishok & Smidt (1988), McConnell & Xu
  (2008).
- **Long-only** (`symmetric: false`): la hipótesis es asimétrica; un corto
  espejo no tiene la misma justificación y duplicaría las pruebas.
- Entrada al cierre del día hábil **N** antes de fin de mes; salida al cierre
  del día hábil **M** del mes siguiente. N ∈ {1,2,3}, M ∈ {2,3,4} → 9
  combinaciones. Calendario NYSE de `calendars.py` (festivos, fines de semana y
  cierres especiales).
- Stop de catástrofe fijo **3×ATR(14) D1**, no optimizado: cubre un hueco de
  varios días sin confundirse con el ruido normal; la salida real es el
  calendario.
- `valid_timeframes: [D1]`; no se declara H1 porque la entrada/salida exacta
  al cierre de sesión no está garantizada con barras H1 del servidor.

Implementación necesaria:

- `dsl.py`: nodo temporal `month_turn` con `n` y `m`; validación de rango,
  long-only y raíz de la entrada.
- `compiler.py`: calcula la señal de entrada y `Signals.exit_index` con los
  pares entrada/salida del calendario NYSE.
- `fastbt.py`: modo de ejecución específico que entra al **cierre** de la vela
  de señal, aplica stop/objetivo opcionales y sale al cierre de
  `exit_index[entrada]` (motivo `calendar_exit`). El camino normal
  `open_next` no cambia.
- `fitness.py`/`feasibility.py`: los pliegues conservan `exit_index`; la cota
  de tiempo medio para `month_turn` es N+M+5 velas (cota estructural por fines
  de semana/festivos, no un umbral de optimización).
- `drift.py`: para plantillas long-only usa entradas aleatorias **solo largas**
  con la misma duración. Verificado con test directo y con la ventaja sintética
  long-only (percentil 100).

Tests nuevos:

- Pares de calendario con fin de mes en fin de semana, festivos y N=2.
- Plantilla long-only y 9 combinaciones; rechazo de `month_turn` en corto o
  anidado.
- Señales y salidas exactas contra el calendario.
- Sin anticipación: cambiar el futuro no cambia las entradas.
- Ejecución al cierre y salida en el día M.
- Control de deriva long-only (no toca los cortos).

Durante R9 se calcularon 36 miradas informativas de `turn_of_month` antes de
registrar (US500/US100 × Dukascopy/Databento × 9). Ese cálculo se documenta en
`reports/discovery/incidente-r9-snooping.md` y queda anotado en el contador
DSR; **no se usa para recomendar ninguna spec**. La recomendación basada en
rendimiento queda retirada: la elección de qué spec registrar es del operador.

## 3. Specs y viabilidad

Specs creadas en `.orquestador/specs/` (no registradas):

- `r9-tom-us500-d1.yaml`: US500 D1, Dukascopy, IS 2018-01-01…2024-06-30,
  CFD-006 target.
- `r9-tom-us100-d1.yaml`: US100 D1, Dukascopy, IS 2014-01-01…2024-06-30,
  CFD-001/CFD-006 best.
- `r9-tom-us500-d1-confirm.yaml`: US500 D1, Databento ES desde 2010-06-06,
  `confirmation_only: true`.
- `r9-tom-us100-d1-confirm.yaml`: US100 D1, Databento NQ desde 2010-06-06,
  `confirmation_only: true`.

`preflight --spec`: 9 generados, 9 válidos, 0 rechazados, 0 duplicados en las
cuatro.

`feasibility --spec` (solo IS, sin PnL ni DSR):

| Spec | Factibles | Ops IS | Cost_R (elegida) |
|---|---:|---|---:|
| US500 Dukascopy | 9/9 | 32–63 | 0.0149–0.0174 (CFD-006) |
| US100 Dukascopy | 9/9 | 52–103 | 0.0085–0.0093 (CFD-001); CFD-006 0.0101–0.0108 |
| US500 Databento | 9/9 | 71–137 | 0.0225–0.0241 (CFD-006) |
| US100 Databento | 9/9 | 71–137 | 0.0124–0.0139 (CFD-001) |

Pliegues: todos por encima del mínimo D1 (3 por pliegue). ~5–10 operaciones al
año por símbolo, algo por debajo de las ~12/año estimadas; la cesta
multi-símbolo es la vía para subir la muestra.

**Confirmación Databento:** `confirmation_only: true` permite preflight y
feasibility de D1, pero `campaigns.register` sigue bloqueando D1 con fuente
distinta de Dukascopy. Registrar la spec de confirmación requiere una decisión
explícita del operador y una excepción de registro (no incluida).

## 4. Propuesta multi-símbolo

Documento: `.orquestador/PROPUESTA-multisimbolo.md` (sin código).

Resumen:

- Una hipótesis evaluada sobre una cesta de 6 símbolos; `n_total` = número de
  combinaciones (p. ej. 27), no 27×6. Los símbolos son observaciones, no
  ensayos.
- R del portfolio = suma de R netos de las piernas por fecha; pliegues globales
  sobre el IS común, no pliegues por símbolo.
- Coste por símbolo y cuenta; `cost_R` agregado y peor cuenta.
- Control de deriva por cesta: 1.000 réplicas por pierna con semilla estable y
  agregación del portfolio aleatorio.
- Riesgos: correlación (US100/US500), p-hacking por símbolo, coste/liquidez,
  fuentes y husos distintos, riesgo agregado y dependencia de una sola pierna.
- Estimación: `ts_momentum_d1` y `d1_extension_reversion` ~26–48 ops IS por
  símbolo → ~156–288 por cesta de 6; `turn_of_month` ~50–100 por símbolo →
  ~300–600 por cesta.

## 5. Verificación

- `ruff check src/tradinglab tests docs`: limpio.
- `pytest -q`: **1768 passed, 1 skipped**.
- `lab propfund verify`: **4 OK**.
- `count_tests`: **1757**.
- `preflight`/`feasibility` de las 4 specs: OK (9/9 factibles).
- Sin push, sin campañas, sin OOS, sin órdenes.

## Comandos para el operador (NO ejecutados)

R9 **no recomienda** ninguna spec por rendimiento. La elección de qué spec
registrar queda al operador; los comandos para ambas campañas están en
`RESULTADO-R9b.md`.

La spec de confirmación `r9-tom-us500-d1-confirm.yaml` no se puede registrar
con el código actual (D1 Databento bloqueado); si el operador quiere usarla,
debe autorizar una excepción de registro.

## Commits y tag

```text
6e2125b  tl2: R9 - cierre donchian H4, plantilla turn_of_month  (tl2-r9)
```

## Avisos

- El informe Donchian USDJPY no leyó OOS-1/OOS-2. Las 36 miradas informativas
  de `turn_of_month` se hicieron antes de registrar y quedan anotadas en el
  contador (R9b); no se usan para recomendar ninguna spec ni se presentan como
  validación.
- La cota de tiempo medio N+M+5 para `month_turn` es una corrección estructural
  del gate, no un cambio de umbral de rentabilidad.

PARA.
