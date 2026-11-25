# RESULTADO N4 · README real

- **Fecha:** 2026-11-25
- **Rama:** `tl2-n4` (desde `feature/prop-fund-multifirm`)
- **Tag:** `tl2-n4`

## Cambio

- `README.md` anterior movido con `git mv` a `docs/README-historico.md`.
- `README.md` nuevo (131 líneas) con:
  - qué es TradingLab hoy y el alcance demo/paper;
  - estado real: Discovery TL2 con costes v2/protocolo v2, EA us100-ftmo1
    INCIERTO, fuera de instrumento "no transfiere", ai_trader sin ventaja,
    hipótesis cerradas;
  - mapa de módulos;
  - flujo de una campaña con aprobación humana;
  - reglas de seguridad;
  - comandos útiles;
  - enlaces a `docs/`, `reports/` y `.orquestador/tl2-audit/`;
  - estado de las colas TL2 y convenciones para agentes.

## `tests/test_docs.py`

Se sustituyeron las dos comprobaciones del README antiguo:

- `test_readme_sin_duplicado_lm_studio` y `test_readme_numeracion_f15`
  comprobaban secciones que ya no existen (F15, LM Studio).
- Nuevas: `test_readme_estado_real` (Discovery TL2, us100-ftmo1, INCIERTO,
  enlace al histórico) y `test_readme_historico_existe`.
- Se conservan `test_plan_existe` y `test_readme_menciona_propfund`.

`pytest tests/test_docs.py`: **4 passed**. `ruff`: limpio.

## Verificación

- `pytest -q`: **1956 passed, 1 skipped** (30:50). Único aviso:
  `psutil no está instalado: la cola corre sin prioridad below normal`.
- `ruff check src tests`: limpio.
- `count_tests` = 1894.

## Cierre

Merge `--ff-only` a `feature/prop-fund-multifirm`, tag `tl2-n4`.
`git status` conserva solo los cambios externos
(`reports/discovery/edge_map.md` y `tl2-edge-map.patch`).
