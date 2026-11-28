# FUT-B2 · Informe del worker

Modelo: DeepSeek V4.1 Flash. Worktree `E:\tl-fut-data` (rama `fut-data`, desde
`origin/claude/vibrant-mayer-r46s0o`). Fecha: 2026-11-28. Prompt: `OPENCODE_PROMPTS.md §3 P2`.

## Hecho

1. `data_download.plan(rows)` → `list[Job]` (dataset `GLBX.MDP3`, esquema validado contra los nombres de
   `03_ARQUITECTURA_FUTURES.md §3.1`, raíz normalizada a mayúsculas, símbolo `<raíz>.v.0`). Descarta
   duplicados exactos y rechaza `end <= start`. Sin red.
2. `data_download.download(job, client, out_root, *, approved_by_operator)`:
   - `approved_by_operator=False` → `RuntimeError("OP-4 sin aprobar")` **antes** de cualquier llamada.
   - `client.post(<base>/timeseries.get_range)` con `encoding=csv`, `compression=zstd`,
     `stype_in=continuous`, `pretty_px`/`pretty_ts` y el símbolo `<raíz>.v.0`.
   - Destino `data/futures/raw/databento/GLBX.MDP3/<schema>/<raíz>/<start>_<end>.csv.zst` (los `:` del
     timestamp pasan a `-` para que el nombre sea válido en Windows; el rango literal queda en el
     manifiesto). Escritura atómica y **sin sobrescribir**: si existe con el mismo sha256 que su ficha →
     no descarga; con otro hash → error; sin ficha → error.
3. Manifiesto: una línea JSON por fichero en `data/futures/catalog/manifest.jsonl` con `sha256`, `bytes`,
   `rows`, `provider`, `dataset`, `schema`, `root`, `symbol`, `start`, `end`, `encoding`, `compression`,
   `generator`, `generator_version` y `created_at` (UTC).
4. `normalize_trades(payload)` → DataFrame con exactamente `ts_event` (datetime64[ns, UTC]), `price`,
   `size`, `side` (letra literal B/A/N) e `instrument_id`; columna ausente → `DownloadError("Sin datos:
   <columna>")`; `write_norm_trades(payload, path)` escribe el parquet (la ruta la fija quien llama; §3.2
   exige contrato en la ruta y aún no hay tabla de rolls, así que no se inventa).
5. Tests con cliente FALSO (sin red): plan y validaciones, ruta cruda, sin aprobación no hay POST,
   descarga + manifiesto + idempotencia, conflicto de hash sin sobrescribir, fichero huérfano sin ficha,
   error HTTP, normalización con valores exactos y parquet, columna ausente y manifiesto con una línea por
   fichero.

## Ficheros

- `src/tradinglab/futures/data_download.py` (nuevo)
- `tests/test_futures_data_download.py` (nuevo)
- `docs/futures/WORKER_REPORTS/FUT-B2.md` (este informe)

No se ha modificado ningún fichero existente. No se ha descargado nada real.

## Salidas literales

Entorno: `uv sync --frozen --extra dev --extra discovery` en el worktree (venv local `E:\tl-fut-data\.venv`,
tradinglab 0.1.0 desde `file:///E:/tl-fut-data`); `uv` informó `Checked 93 packages in 90ms`.

```text
PS E:\tl-fut-data> .\.venv\Scripts\ruff.exe check src\tradinglab\futures\data_download.py tests\test_futures_data_download.py
All checks passed!
```

```text
PS E:\tl-fut-data> .\.venv\Scripts\python.exe -m pytest -q tests\test_futures_data_download.py
..........                                                               [100%]
10 passed in 2.18s
```

## Aviso

- `compression=zstd` en la petición: el destino `.csv.zst` lo exige y los bytes llegan ya comprimidos, así
  que **no** hace falta la dependencia `zstandard`. El CSV normalizado se pasa a `normalize_trades` en
  claro (bytes/str/ruta); descomprimir el `.zst` queda para el paso de auditoría, cuando haya datos.
- El esquema real de `trades` (nombres y valores de `side`, presencia de `ts_event`) está **por confirmar**
  con la primera descarga aprobada (OP-4); los tests usan el CSV documentado en `RA_spec.md §2`.
- `out_root` es la raíz `data/futures`, porque §3.2 coloca ahí `raw/` y `catalog/`.
- Sin descargas reales, sin `git push`, sin tocar `.env`; solo el venv local del worktree y el fichero de
  este informe fuera de las rutas de código.

## Siguiente

- Revisión de Claude (`tradinglab-reviewer`) y, si pasa, actualizar `05_COLA_Y_ROADMAP.md §3` (FUT-B2:
  código listo; con datos: tras OP-4).
- Pendiente de OP-4: ejecutar `download` con el cliente real y la aprobación del operador, confirmar el
  esquema de `trades` y añadir la tabla de rolls para `norm/<esquema>/<raíz>/<contrato>/<AAAA>.parquet`.
