# RESULTADO CNT · Contador de pruebas v2 = n_total

- **Fecha:** 2026-11-24
- **Commit:** `tl2: CNT - contador v2 = n_total`
- **Tag:** `tl2-cnt`
- **Tag previo:** `tl2-cnt-pre`

## Diagnóstico

`lab research-trials` daba **1886** y debía dar **1894**:

- 1883 de partida;
- +2 del `record-informal` "TL2-E2" del operador;
- +9 de la campaña `v2-fix-londres-eurgbp-h1`, que evaluó 9 combinaciones.

La campaña solo sumó **1**. Causa doble en `discovery/campaigns.py`:

1. `register` guardaba `protocol_version = 2` pero calculaba `plateau_n` y
   `decision_n_total` con `int(protocol_version or 1) >= 2`; con `None` la
   condición era falsa y `plateau_n` quedaba en 0.
2. `discovery_tests` contaba `1 + plateau_n` en v2 con primaria. Como la
   primaria es un punto **dentro** de la rejilla, esa fórmula cuenta una
   operación de más y, con `plateau_n = 0`, contaba 1 en vez de 9.

## Cambio

- `discovery_tests` suma **siempre `n_total`** de cada campaña aprobada y no
  reemplazada. Se elimina la rama `1 + plateau_n` y la lectura de
  `config_json`.
- `register` calcula **un único** `protocol_version` efectivo
  (`None` → 2) y lo usa para guardar, para `plateau_n` y para
  `decision_n_total`.
- `plateau_n = n_total - 1` cuando hay primaria v2 (puntos de rejilla sin la
  primaria). Es **informativo**: no cuenta.
- `decision_n_total = 1` cuando hay primaria v2; `None` en el resto.
- La ruta de cesta guarda desde la spec `protocol_version`, `primary`,
  `plateau_grid`, `holdout_start`, `plausible_edge_r`, `family` y
  `cost_model_version`, con la misma regla de `plateau_n`.
- `register_from_spec` sigue delegando la cesta en `basket.register`; no hay
  una segunda ruta que pueda perder los campos.

## Diagnóstico de la campaña ya ejecutada (solo lectura)

`v2-fix-londres-eurgbp-h1`, `config_json` guardado:

| Campo | Valor guardado |
|---|---|
| `protocol_version` | 2 |
| `primary` | `{"hold_hours": 60, "stop_mult": 2.5}` |
| `plateau_n` | **0** |
| `decision_n_total` | 1 |
| `cost_model_version` | 2 |
| `holdout_start` | 2025-07-01 |
| `family` | `fx_fix` |
| `plausible_edge_r` | `None` |
| `plateau_grid` | `None` |

Se ejecutó **sin la decisión v2 por primaria**: no hay ninguna validación
`protocol_v2_dev`, los únicos motivos de selección son lenguaje v1
("descartado: IS completa ... <= 0") y `n_finalists = 0`. El veredicto no
cambia: las 9 combinaciones tienen neto < 0 y la primaria (ID 627) también,
con **−0,0235 R**. No se reejecutó la campaña.

## Verificación con la base real (solo lectura)

```text
lab research-trials  ->  Pruebas DSR (contador único): 1894
```

`campaigns.discovery_tests()` devuelve 814 campañas de Discovery (incluida
`v2-fix-londres-eurgbp-h1` con 9) y 0 lecturas de holdout; el contador global
de `lab research-trials` añade el resto de fuentes de `learning` y da 1894.
La diferencia con 1886 es exactamente **+8**: de 1 a 9 en la campaña.

## Tests

- `tests/test_discovery_plateau.py`: v1 con `n_total=9` → 9; v2 con primaria
  y `n_total=9` → 9; fila antigua v2 con `plateau_n=0` → 9.
- `tests/test_discovery_protocol_v2.py`: `register` con
  `protocol_version=None` guarda 2, `plateau_n = n_total - 1` y
  `decision_n_total=1`; con `protocol_version=1`, `plateau_n=0` y `None`.
- `tests/test_discovery_basket_run.py`: spec de cesta v2 sintética guarda en
  `config_json` todos los campos con sus valores.
- `ruff check`: limpio.
- `pytest` dirigido: **12 passed** (2,5 s).

## Changelog

Entrada añadida a `docs/CHANGELOG-produccion.md` con alcance, verificación y
rollback.

## Rollback

`git reset --hard tl2-cnt-pre` o revertir el commit. No se modificó ninguna
fila de base de datos; el contador se recalcula en lectura.
