# PARALELO · F10a · futuros Databento: SOLO coste + tubería (sin descargar)
Modelo: DeepSeek V4.1 Flash. BLOQUE COMÚN (docs/tradinglab2/10) + AGENTS.md.
Otras sesiones trabajan en E:\trading-lab (C2-informe) y en otros worktrees. TÚ NO TRABAJAS EN E:\trading-lab.

## 0. Worktree (antes de nada)
```powershell
cd E:\trading-lab
git worktree add -b tl2-f10a C:\Users\PC\.local\share\opencode\worktree\tl2-f10a HEAD
cd C:\Users\PC\.local\share\opencode\worktree\tl2-f10a
```
Usa E:\trading-lab\.venv con `$env:PYTHONPATH="$PWD\src"`. Escribe solo dentro del worktree, salvo el RESULTADO en E:\trading-lab\.orquestador\RESULTADO-F10a.md.
Si un test falla solo por CRLF (hashes del EA/protegidos), es entorno del worktree: lístalo, no lo arregles.

## Prohibido
DESCARGAR DATOS DE PAGO (timeseries.get_range, batch, o cualquier llamada que facture). Campañas, approve/run/confirm/supersede, OOS, push, tareas programadas, borrar, umbrales, archivos protegidos, carril del EA, instalar paquetes en .venv. NUNCA imprimas ni escribas la API key.
Tests: solo los del módulo nuevo; suite completa una vez al final.

## Tareas
1. Clave: léela con keyring ('tradinglab','DATABENTO_API_KEY'). Si no existe: PARA y dilo.
2. Coste (gratis): metadata.get_cost, get_record_count y get_billable_size (paquete `databento` si está instalado; si no, la API REST https://hist.databento.com/v0/metadata.* con requests/httpx y auth básica; NO instales nada). Dataset GLBX.MDP3, schema ohlcv-1m y ohlcv-1h, símbolos continuos NQ, ES, YM, GC, 6E, 6B, 6J con stype continuous en dos variantes de roll (.c.0 calendario y .v.0 volumen), desde el inicio del dataset hasta la última fecha disponible. Tabla: símbolo × schema × roll → registros, tamaño, coste USD; total por schema. Indica la opción más barata que cubre M1 de los 7.
3. Tubería (código, sin ejecutar descargas): `src/tradinglab/discovery/fetch_databento.py` + `lab discovery fetch-databento --symbols ... --schema ... --start ... --end ... --estimate-only` (por defecto SOLO estima; descargar exigirá un flag `--i-approve-cost USD` que debe coincidir con la estimación, y no se usa en esta fase). Guarda a parquet con el mismo formato que Dukascopy (UTC, OHLCV), fuente `databento`, mapeo a símbolos internos (NQ→US100, ES→US500, YM→US30, GC→XAUUSD, 6E→EURUSD, 6B→GBPUSD, 6J→USDJPY invertido: documenta cómo se invierte el precio 6J), y ajuste por roll documentado (sin ajuste / back-adjust por diferencia). Tests con respuestas simuladas (sin red).
4. Integración: data_sources acepta `databento`; usable_from y data-check funcionan sobre la fuente (con fixtures). Sesiones CME (pausa 17:00-18:00 NY, cierre viernes 17:00) declaradas como hipótesis a derivar cuando haya datos.
5. ruff, tests del módulo, pytest -q (una vez), propfund verify (4 OK), count_tests (el que haya; no debe cambiar por ti). Commit en tl2-f10a "tl2: F10a - Databento coste y tubería", tag tl2-f10a. NO push, NO merge.
6. RESULTADO-F10a.md con la tabla de costes y la recomendación (qué descargar, cuánto cuesta) para que el operador diga "OK DESCARGA" o no. PARA.
