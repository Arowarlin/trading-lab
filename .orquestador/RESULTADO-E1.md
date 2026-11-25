# RESULTADO E1 · Caché sin barra en curso y paridad motor vs MT5

- **Fecha:** 2026-11-24
- **Rama:** `feature/prop-fund-multifirm`
- **Commit:** `tl2: E1 - caché sin barra en curso y paridad`
- **Tag:** `tl2-e1`

## E1.1 · Contador y prerregistro

```text
lab research-trials  ->  Pruebas DSR (contador único): 1894
```

La tabla `informal_trials` contiene la anotación del operador:

```text
n = 2
reason = "TL2-E2: EA v3.2 fuera de instrumento US500+US30, prerregistrado"
approved_by = "operador"
```

## E1.2 · Corrección autorizada de la caché

El operador autorizó sustituir **solo** la barra `2026-11-24 19:15 NY`, con la
condición de que su apertura + 5 min fuera posterior a la escritura de la
caché (barra en formación). Cualquier otra barra solapada debía coincidir
exactamente.

### Condición de formación

| Dato | Valor |
|---|---|
| Escritura de la caché | `2026-11-25 00:17:29 UTC` |
| Apertura de la barra | `2026-11-25 00:15:00 UTC` (19:15 NY) |
| Apertura + 5 min | `2026-11-25 00:20:00 UTC` |
| ¿00:20 > 00:17:29? | **Sí, estaba en formación** |
| ¿00:20 <= ahora? | **Sí, ya cerró** |
| Otras 252 barras solapadas | **Coinciden exactamente** |

### Barra antigua y nueva (guardadas antes de escribir)

| Campo | Caché (antigua) | Terminal (nueva) |
|---|---:|---:|
| open | 26074.13 | 26074.13 |
| high | 26074.13 | 26074.13 |
| low | 26026.33 | 26026.23 |
| close | 26030.33 | **26046.63** |
| tickvol | 827 | **1643** |
| spread | 195 | 195 |

### Resultado de la actualización

`ea_parity.update_cache` volvió a comprobar las 252 barras, la condición de
formación y el login antes/después de escribir:

- login **1515349730** (FTMO-Demo, demo) antes y después;
- barra 19:15 reemplazada una sola vez;
- **29 barras nuevas** añadidas (19:20 → 21:40 NY; el mercado siguió
  produciendo velas durante la ejecución);
- 368.773 → **368.802** filas;
- última barra: `2026-11-24 21:40 NY`;
- ninguna otra barra modificada.

## E1.3 · Código: nunca guardar la barra en curso

- Nueva función `ea_us100.drop_forming_bar`: descarta la última vela si
  `apertura + 5 min > ahora`; el resto del histórico no se toca.
- `load_bars` la aplica antes de escribir la caché.
- Test sintético en `tests/test_ea_us100.py`:
  - a las 10:12 NY la vela de 10:10 se descarta;
  - a las 10:15 NY se conserva.
- `update_cache` aplica la misma regla y, además, exige que la barra antigua
  estuviera en formación antes de reemplazarla.

## E1.4 · Comando de paridad

Nuevo comando:

```text
lab ea parity us100-ftmo1 [--since 2026-11-23] [--json]
```

- ejecuta el motor sobre la caché;
- lee los deals reales de MT5 por `history_deals` y filtra los magics del EA
  (`93010001`, `93020001`);
- agrupa por `position_id` (una entrada y una o varias salidas);
- empareja por lado y entrada ±1 barra (5 min);
- muestra diferencias de entrada, salida y resultado en puntos, huérfanos y
  resumen de slippage;
- verifica el login antes y después.

Tests (`tests/test_ea_parity.py`, 3): emparejamiento correcto y diferencias
exactas, huérfanos y lados distintos, tolerancia de una vela.

## E1.5 · Paridad real

Ventana: desde `2026-11-23` (NY). Motor y MT5: **1 operación cada uno**,
**100 % emparejadas**, sin huérfanos.

| Lado | Entrada motor | Entrada MT5 | Dif. entrada | Dif. salida | Dif. resultado |
|---|---|---:|---:|---:|---:|
| short | 26.162,23 (15:20:00 UTC) | 26.185,73 (15:20:50 UTC) | **+2.350 pts** | **−270 pts** | **+2.620 pts** |

- Resultado motor: +49,25 puntos; resultado real: +75,45 puntos.
- El motor entra en el **open** de la barra; el EA entró 50 s después, a
  26.185,73 (23,50 puntos por encima del open). Para un corto, eso es
  favorable: slippage de entrada **−2.350 pts** (signo positivo = peor).
- Salida real 26.110,28; el motor 26.112,98: **−270 pts** favorable al real.
- El resultado real supera al del motor en **+2.620 pts** por esa diferencia
  de ejecución intrabar, no por una divergencia de señal.
- La señal, el lado y la hora de entrada coinciden; la diferencia es de
  **precio de ejecución**, no de lógica.

## E1.6 · Tests y verificación

- `ruff check`: limpio.
- `pytest tests/test_ea_parity.py tests/test_ea_us100.py`: **6 passed**.
- MT5 solo attach-only: `copy_rates_range`, `history_deals` y lectura; ninguna
  orden creada, modificada ni cerrada.
- `count_tests` sigue en **1894**.

## Git

Commit `tl2: E1 - caché sin barra en curso y paridad`, tag `tl2-e1`. La caché
M5 está en `data/cache/ea/` (ignorada por git). `git status` conserva los dos
cambios externos de la sesión anterior.
