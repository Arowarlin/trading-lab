# COLA-F10b · unir F10a y preparar la descarga Databento H1 (APROBADA por el operador)
Modelo: DeepSeek V4.1 Flash. BLOQUE COMÚN + AGENTS.md. Repo E:\trading-lab, rama feature/prop-fund-multifirm.
APROBACIÓN DEL OPERADOR (2026-11-23 10:39, literal): "OK DESCARGA H1 6,78". Cubre SOLO: GLBX.MDP3, schema ohlcv-1h, stype continuous .v.0 (roll por volumen), 7 símbolos NQ ES YM GC 6E 6B 6J, rango de F10a, coste estimado 6,78 USD. Nada más (no M1, no .c.0, no otros símbolos).
PROHIBIDO: ejecutar tú la descarga (la lanza el operador), campañas, OOS, push, tareas programadas, borrar, umbrales, protegidos, carril del EA. NUNCA leas en voz alta, imprimas ni escribas la API key (se lee de keyring dentro del código).

## Tareas
1. Merge `tl2-f10a` (tag tl2-f10a) en feature/prop-fund-multifirm con --no-ff. Conflictos previsibles solo en cli.py / data_sources: conserva todo. En E:: tests del módulo databento, tests del EA (deben pasar aquí), ruff, pytest -q, propfund verify (4 OK), count_tests 1730. Commit de merge "merge: F10a Databento", tag tl2-merge-f10a. NO borres worktree ni rama.
2. Re-estimación (gratis) con `lab discovery fetch-databento ... --estimate-only` para EXACTAMENTE lo aprobado. Si el coste difiere de 6,78 USD en más de 5 %, PARA y dilo (el operador decide de nuevo).
3. Escribe en .orquestador\RESULTADO-F10b.md un bloque PowerShell con el comando EXACTO de descarga para que lo ejecute el operador (con --download y --i-approve-cost igual al céntimo a la re-estimación), dónde quedarán los parquet, cuánto ocupan y cuánto tardará aproximadamente. Y los comandos de comprobación posteriores (solo lectura) para que el operador vea que llegaron.
4. Deja escrito en el mismo RESULTADO lo que hará la fase siguiente (F10c) cuando el operador diga "DESCARGADO": data-check por símbolo H1/H4/D1, derive-sessions --source databento (horario CME real), usable_from, y comparación Databento vs Dukascopy por símbolo (correlación de retornos, desfase, diferencias de nivel tras el roll, días con huecos). No la hagas ahora.
5. PARA.
