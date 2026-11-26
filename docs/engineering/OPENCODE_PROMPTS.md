# OPENCODE_PROMPTS · tareas L (equipo del operador)

**Modelo para todas:** DeepSeek V4.1 Flash (OpenCode Go).
Los prompts son cortos y cerrados a propósito. Cada uno dice qué ficheros puede escribir y cuándo PARAR.
Claude revisa cada entrega antes de darla por buena.

## Preparación (una vez, en PowerShell, la hace el operador)

```powershell
cd E:\trading-lab
git fetch origin claude/upbeat-pasteur-nz8e0u
git worktree add ..\tl-eng-l1 origin/claude/upbeat-pasteur-nz8e0u
```

El worktree `..\tl-eng-l1` es **solo de lectura** para el código: los scripts leen los datos de
`E:\trading-lab\data` (pasando `--root E:\trading-lab`) y escriben los informes dentro del worktree.
EDGE-2 sigue en `E:\trading-lab` sin que nadie lo toque.

---

## L0 · Comprobación previa (lectura)

```text
Eres un trabajador de TradingLab. Solo lees; no cambias nada.
Carpeta de trabajo: E:\tl-eng-l1

1. Ejecuta en PowerShell y copia la salida literal:
   Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "lab|pytest|discovery" } | Select-Object ProcessId, CommandLine
2. Ejecuta: Get-ChildItem E:\trading-lab\.orquestador\locks -ErrorAction SilentlyContinue | Select-Object Name, LastWriteTime
3. Ejecuta: git -C E:\trading-lab log --oneline -5 ; git -C E:\trading-lab tag --list "edge*" "robust*" "motor*"
4. Escribe la salida de los pasos 1-3, sin interpretarla, en E:\tl-eng-l1\docs\engineering\WORKER_REPORTS\L0-estado.md
5. PARA. No ejecutes nada más. No hagas commit.

Prohibido: borrar, mover o editar ficheros fuera de WORKER_REPORTS; matar procesos; ejecutar lab, pytest o git push.
```

## L1a · ¿La suite de tests ha escrito o enviado alertas reales? (F0-08, lectura)

```text
Eres un trabajador de TradingLab. Solo lees; no cambias nada.
Carpeta de trabajo: E:\tl-eng-l1

1. Ejecuta exactamente este comando (abre la base de datos en modo SOLO LECTURA):
   E:\trading-lab\.venv\Scripts\python.exe -c "import sqlite3;c=sqlite3.connect('file:E:/trading-lab/data/lab.db?mode=ro',uri=True);q=\"select ts,event,severity,channel,ok,substr(message,1,80) from alerts where message like '%gate-test%' or message like '%intra-x%' or message like '%BTCUSD%' or message like '%presupuesto test%' order by ts\";rows=c.execute(q).fetchall();print(len(rows));[print(r) for r in rows[:200]]"
2. Ejecuta también:
   E:\trading-lab\.venv\Scripts\python.exe -c "import sqlite3;c=sqlite3.connect('file:E:/trading-lab/data/lab.db?mode=ro',uri=True);print(c.execute('select * from learning_holdout').fetchall());print(c.execute('select symbol,timeframe,last_bar_utc,fetched_at_utc,source from data_freshness order by id desc limit 15').fetchall())"
3. Escribe en E:\tl-eng-l1\docs\engineering\WORKER_REPORTS\L1a-alertas.md:
   - la salida literal de los pasos 1 y 2;
   - cuántas filas tienen channel distinto de 'none' y ok = 1 (esas se ENVIARON de verdad);
   - las fechas de la primera y la última.
4. PARA. No borres ninguna fila aunque sean de tests. No hagas commit.

Prohibido: abrir lab.db en modo escritura, borrar, editar, ejecutar lab, pytest o git push.
```

## L1b · Huecos y meses truncados en la caché Dukascopy (C-01, C-02, lectura)

```text
Eres un trabajador de TradingLab. Solo lees los datos; no cambias nada.
Carpeta de trabajo: E:\tl-eng-l1

1. Ejecuta exactamente:
   E:\trading-lab\.venv\Scripts\python.exe docs\engineering\tools\eng_l1_data_checks.py --root E:\trading-lab --out docs\engineering\WORKER_REPORTS\L1b-datos.md
2. Si el comando falla, copia el error completo al final de L1b-datos.md (créalo si no existe) y PARA.
3. Si funciona, añade al final de L1b-datos.md una sección "Resumen" con tres líneas por símbolo:
   huecos totales, huecos dentro del IS 2015-2019 y meses truncados. Copia las cifras del propio informe; no las calcules tú.
4. PARA. No hagas commit.

Prohibido: modificar el script, la caché, data-check o engine.yaml; ejecutar fetch, lab, pytest o git push.
```

## L1d · ¿Dónde están las 1.552 pruebas de EDGE-1 que no suma el contador? (E-04, lectura)

```text
Eres un trabajador de TradingLab. Solo lees; no cambias nada.
Carpeta de trabajo: E:\tl-eng-l1

1. Ejecuta exactamente (abre discovery.db en modo SOLO LECTURA):
   E:\trading-lab\.venv\Scripts\python.exe -c "import sqlite3;c=sqlite3.connect('file:E:/trading-lab/data/discovery.db?mode=ro',uri=True);rows=c.execute(\"select id,n_total,status,approved_at is not null from disc_campaigns where id like 'edge1-%' order by id\").fetchall();[print(r) for r in rows];print('registradas',sum(r[1] or 0 for r in rows));print('cuentan',sum(r[1] or 0 for r in rows if r[3] and (r[2] or '')!='superseded'))"
2. Escribe la salida literal en E:\tl-eng-l1\docs\engineering\WORKER_REPORTS\L1d-contador.md
   y debajo, una lista de las campañas que NO cuentan (approved = 0 o status = superseded) con su n_total.
3. PARA. No hagas commit.

Prohibido: abrir discovery.db en modo escritura, ejecutar lab, pytest o git push.
```

## L2 · Preparar C1: festivos japoneses y cobertura de USDJPY (sin rendimiento)

```text
Eres un trabajador de TradingLab. No calculas ningún rendimiento.
Carpeta de trabajo: E:\tl-eng-l1

1. Descarga el CSV oficial de festivos de Japón (Oficina del Gabinete) a E:\tl-eng-l1\data\calendar\jp_holidays_cao.csv:
   Invoke-WebRequest -Uri "https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv" -OutFile data\calendar\jp_holidays_cao.csv
   Si falla, escribe el error en docs\engineering\WORKER_REPORTS\L2-c1-prep.md y PARA.
2. Ejecuta exactamente (solo lee el índice y cuenta velas; no mira precios):
   E:\trading-lab\.venv\Scripts\python.exe -c "import pandas as pd;f=pd.read_parquet(r'E:\trading-lab\data\cache\dukascopy\USDJPY_M1.parquet',columns=['ask_open']);i=pd.DatetimeIndex(pd.to_datetime(f.index));i=i.tz_localize('UTC') if i.tz is None else i.tz_convert('UTC');m=(i<'2023-01-01')&(i.hour==0)&(i.minute.isin([0,54]));s=f.loc[m,'ask_open'];print('primera',i.min(),'velas_00:00_y_00:54',int(m.sum()),'con_ask',int(s.notna().sum()));print(s.groupby(i[m].year).count().to_string())"
3. Escribe la salida literal en docs\engineering\WORKER_REPORTS\L2-c1-prep.md, más el número de líneas del CSV y su primera y última fecha.
4. PARA. No ejecutes c1_tokyo_fix_gotobi.py. No hagas commit.

Prohibido: leer datos de 2023 en adelante, editar código, ejecutar lab, pytest o git push.
```

## L3 · Ejecutar C1 · **BLOCKED**

Ejecutar C1 suma +1 al contador de pruebas. Requiere que el operador escriba literalmente
`APRUEBO C1` en una sesión de Claude Code, después de revisar L2.

## L4 · Puerta 2 de EDGE-1 y EDGE-2 con puertas v2 y v3 (sin campañas, sin OOS-2)

```text
Eres un trabajador de TradingLab. No ejecutas campañas ni lees el OOS-2.
Carpeta de trabajo: E:\trading-lab

0. Comprueba que no hay ningún proceso "discovery run" vivo:
   Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "discovery run" }
   Si sale alguno, escribe "bloqueado: campaña en marcha" en docs\engineering\WORKER_REPORTS\V3-gate2.md y PARA.
1. Ejecuta exactamente (trabaja sobre una COPIA de discovery.db en una carpeta temporal):
   .\.venv\Scripts\python.exe docs\engineering\tools\v3_gate2_reeval.py --db E:\trading-lab\data\discovery.db --prefix edge1- --prefix edge2- --out docs\engineering\WORKER_REPORTS\V3-gate2.md
2. Copia la última línea que imprime al final de V3-gate2.md, bajo un título "Salida".
3. PARA. No hagas commit.

Prohibido: editar código o configuración, ejecutar lab, pytest, campañas o git push.
```

## L5 · ¿Qué noche cobra el triple swap tu bróker? (B-04, solo lectura)

```text
Eres un trabajador de TradingLab. Solo lees; no cambias nada.
Carpeta de trabajo: E:\trading-lab

1. Ejecuta exactamente (abre lab.db en modo SOLO LECTURA):
   .\.venv\Scripts\python.exe docs\engineering\tools\b04_swap_nights.py --db E:\trading-lab\data\lab.db --out docs\engineering\WORKER_REPORTS\B04-swap.md
2. Copia la línea que imprime al final de B04-swap.md, bajo un título "Salida".
3. PARA. No interpretes la tabla. No hagas commit.

Prohibido: editar código, abrir lab.db en modo escritura, ejecutar lab, pytest o git push.
```

## L6 · Descargar el ASK de USDJPY para C1 (2003-2022; no toca el OOS-2)

```text
Eres un trabajador de TradingLab. Solo descargas datos; no calculas rendimiento.
Carpeta de trabajo: E:\trading-lab

0. Comprueba que no hay ningún proceso "discovery run" ni "fetch-dukascopy" vivo:
   Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "discovery run|fetch-dukascopy" }
   Si sale alguno, escribe "bloqueado" en docs\engineering\WORKER_REPORTS\L6-ask.md y PARA.
1. Ejecuta exactamente (tarda; puede ser más de una hora; si se corta, vuelve a ejecutarlo: reanuda):
   .\.venv\Scripts\lab.exe discovery fetch-dukascopy USDJPY --from 2003-05-04 --to 2022-12-31 --workers 4 --rate 5
2. Cuando termine, ejecuta (solo cuenta velas con ASK; no mira precios):
   .\.venv\Scripts\python.exe -c "import pandas as pd;f=pd.read_parquet(r'E:\trading-lab\data\cache\dukascopy\USDJPY_M1.parquet',columns=['ask_open']);i=pd.DatetimeIndex(pd.to_datetime(f.index));i=i.tz_localize('UTC') if i.tz is None else i.tz_convert('UTC');m=(i<'2023-01-01')&(i.hour==0)&(i.minute.isin([0,54]));s=f.loc[m,'ask_open'];print('velas',int(m.sum()),'con_ask',int(s.notna().sum()));print(s.notna().groupby(i[m].year).mean().round(3).to_string())"
3. Escribe en docs\engineering\WORKER_REPORTS\L6-ask.md la última línea del paso 1 y la salida literal del paso 2.
4. PARA. No ejecutes c1_tokyo_fix_gotobi.py. No hagas commit.

Prohibido: --force, otras fechas, otros símbolos, editar código, ejecutar campañas, pytest o git push.
```

## L1c · Suite completa con el fixture nuevo · **BLOCKED**

No se lanza todavía. Con el `.venv` de `E:\trading-lab`, los tests importan `E:\trading-lab\src`, así
que `ROOT\data\lab.db` es la base de datos real: la suite seguiría escribiendo filas de test en ella
(F0-08). El fixture nuevo corta los **envíos** de alertas, no las escrituras. Se desbloquea con ENG-F5
(`DEFAULT_DB` configurable en los tests), que requiere la aprobación del operador.

---

Tareas que **no** se dan a OpenCode: integrar en `master`, tocar `fastbt.py`, `costs.py` u otros
módulos congelados, componentes de producción, campañas o lecturas del OOS-2.
