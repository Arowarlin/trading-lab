# Incidente R9 — miradas de rendimiento antes del pre-registro

Fecha: 2026-11-23. Documento de incidente; no registra, aprueba ni ejecuta
campañas.

## Qué pasó

Durante R9 se calculó el rendimiento de `turn_of_month` **antes de registrar
ninguna campaña**, para elegir qué spec recomendar. Se usó `fitness.evaluate`
en modo lectura sobre las barras IS de cuatro specs:

| Spec | Símbolo | Fuente | Combinaciones |
|---|---|---|---:|
| `r9-tom-us500-d1` | US500 | Dukascopy | 9 |
| `r9-tom-us100-d1` | US100 | Dukascopy | 9 |
| `r9-tom-us500-d1-confirm` | US500 | Databento ES | 9 |
| `r9-tom-us100-d1-confirm` | US100 | Databento NQ | 9 |

Total: **36 miradas** (18 Dukascopy + 18 Databento). Se miraron expectativa
neta y bruta, profit factor, coste, concentración, tiempo medio y percentil de
deriva. No se leyó OOS-1 ni OOS-2, no se escribió en `disc_*` y no se registró
ninguna campaña, pero el contador DSR no las contaba. Eso viola el pre-registro:
el rendimiento se usó para recomendar US500.

## Decisión del operador

Literal (2026-11-23): **"Contar todo"**.

- Se registran y ejecutan **US500 y US100 Dukascopy** (2 campañas × 9 = 18
  pruebas; las ejecuta el operador).
- Las **18 miradas Databento** se anotan ahora en el contador como deuda de
  pre-registro.
- OOS-1/OOS-2 siguen limpios y deciden.

## Contador antes/después

| Momento | count_tests |
|---|---:|
| Antes de R9b | 1757 |
| Tras anotar 18 miradas Databento | **1775** |
| Esperado tras registrar US500 y US100 Dukascopy | 1793 |

La anotación quedó en `informal_trials` (lab.db) con `n=18`, motivo:

```text
R9: miradas informativas turn_of_month Databento ES/NQ D1 (2×9) antes de
pre-registro; decisión operador 'Contar todo' 2026-11-23
```

No se borró ni se reescribió ninguna campaña. La recomendación basada en
rendimiento se retiró de `RESULTADO-R9.md`; la elección de qué spec registrar
es del operador.

## Specs: comprobación de contenido

`r9-tom-us500-d1.yaml` y `r9-tom-us100-d1.yaml` no se tocaron después de R9.
Como `.orquestador/` está en `.gitignore`, no están dentro del commit
`6e2125b`; la comprobación se hizo contra el contenido exacto escrito en R9:

| Spec | Bytes | SHA256 (16) | Igual a R9 |
|---|---:|---|---|
| `r9-tom-us500-d1.yaml` | 1138 | `40546d39abad4f7d` | sí |
| `r9-tom-us100-d1.yaml` | 1138 | `382e9a364e6b5140` | sí |

No se modificaron. Las únicas specs que cambiaron después de R9 son las dos de
confirmación Databento, a las que se añadió `confirmation_only: true` (no son
las specs de las campañas que ejecuta el operador).

## Blindaje

- `src/tradinglab/discovery/guard.py`: bloquea `fitness.evaluate`,
  `drift.evaluate`/`percentile`, `robustness.run` y las perturbaciones/MC si no
  hay campaña aprobada. `preflight` y `feasibility` (operaciones y coste) siguen
  permitidos.
- Flag interno de test por variable `TRADINGLAB_ALLOW_UNAPPROVED=1` en
  `tests/conftest.py`; los tests que verifican el bloqueo lo desactivan.
- Regla añadida al BLOQUE COMÚN (`docs/tradinglab2/10`): "Nunca calcules
  rendimiento antes de register+approve; si ocurre, se anota en el contador".
- Tests: rechazo sin aprobar, permiso con `approved=True`, rechazo de deriva y
  `record-informal` (sin flag no escribe; con flag suma exactamente n y deja
  traza).
