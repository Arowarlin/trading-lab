# FUT-B3 · Manifiesto con hash de los datos existentes

**Ejecutado:** 2026-11-28 por Claude (sesión local), worktree `E:\tl-fut-s`. Script sin modificar.

## Hecho

Los parquet viven en el repo principal (`E:\trading-lab\data\cache\databento`), no en el worktree. El
script calcula `path.relative_to(ROOT)` con `ROOT` = repo del script, así que con `--data-dir` fuera del
worktree fallaría. Se ejecutó con un envoltorio fuera del repo que carga el script con `runpy`, fija
`ROOT = E:\trading-lab` y llama a `main()` con:

```
--data-dir E:\trading-lab\data\cache\databento --out-dir E:\tl-fut-s\docs\futures\evidencia
```

Solo lectura de los parquet (lectura y SHA-256). Nada se modificó, copió ni movió.

## Tabla (literal de `manifest_futuros.md`)

| Fichero | Raíz | TF | Filas | Primera (UTC) | Última (UTC) | instrument_id | SHA-256 (16) |
|---|---|---|---:|---|---|---|---|
| data/cache/databento/EURUSD_H1.parquet | 6E | H1 | 97075 | 2010-06-07T00:00:00+00:00 | 2026-11-23T06:00:00+00:00 | no | `f4958d3e6e89a839` |
| data/cache/databento/GBPUSD_H1.parquet | 6B | H1 | 97050 | 2010-06-07T00:00:00+00:00 | 2026-11-23T06:00:00+00:00 | no | `7e918ca6e2d60a26` |
| data/cache/databento/US100_H1.parquet | NQ | H1 | 98073 | 2010-06-07T00:00:00+00:00 | 2026-11-23T06:00:00+00:00 | no | `914642c7c3632072` |
| data/cache/databento/US100_M1.parquet | NQ | M1 | 5513724 | 2010-06-07T00:00:00+00:00 | 2026-11-26T16:01:00+00:00 | no | `51ab097106fa72c9` |
| data/cache/databento/US30_H1.parquet | YM | H1 | 98168 | 2010-06-07T00:00:00+00:00 | 2026-11-23T06:00:00+00:00 | no | `fd7793c705d9c792` |
| data/cache/databento/US500_H1.parquet | ES | H1 | 98113 | 2010-06-07T00:00:00+00:00 | 2026-11-23T06:00:00+00:00 | no | `16068fbb5b2f25c1` |
| data/cache/databento/USDJPY_H1.parquet | 6J | H1 | 97055 | 2010-06-07T00:00:00+00:00 | 2026-11-23T06:00:00+00:00 | no | `bb06e571330a3f00` |
| data/cache/databento/XAUUSD_H1.parquet | GC | H1 | 98289 | 2010-06-07T00:00:00+00:00 | 2026-11-23T06:00:00+00:00 | no | `87e3bd9a7ff68044` |
| data/cache/databento/XAUUSD_M1.parquet | GC | M1 | 5714061 | 2010-06-07T00:00:00+00:00 | 2026-11-26T16:01:00+00:00 | no | `3cec945faaf9c2a4` |

## Aviso

- Ningún fichero tiene `instrument_id`: son series continuas sin identidad de contrato. Para Research
  A/B hace falta `definition` (rolls), que espera a OP-4.
- Solo hay M1 de NQ y GC; ES, YM y las divisas solo en H1. No hay MNQ, MES ni MGC.
- Fallo menor del script: no admite `--data-dir` fuera de su propio repo (`relative_to`). Arreglo
  propuesto: ruta relativa solo si está dentro de `ROOT`; si no, la absoluta.

## Siguiente

FUT-J4b (puente NT8 en Sim101).
