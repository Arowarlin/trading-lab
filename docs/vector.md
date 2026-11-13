# Vector · observabilidad local

**Vector 0.61.0**, herramienta externa (no es dependencia de Python), solo
observa. No toca MT5, SQLite ni las órdenes; no tiene destinos de red. El
operador lo instala; el laboratorio no lo instala solo.

- Licencia: **MPL-2.0** (ver `docs/dependencias.md`).
- `data_dir`: `E:/trading-lab/data/vector/`.
- Configuración: `config/vector/vector.yaml` (sin secretos).
- Destinos: `logs/vector/all-YYYY-MM-DD.jsonl` (todo) y
  `logs/vector/alerts.jsonl` (warn + critical).
- Retención: 14 días para `all-*.jsonl`, limpiada por
  `scripts/vector_cleanup.ps1` desde `TradingLab-Heartbeat`.

## Instalación (solo el operador)

Versión fija: **0.61.0**. Assets oficiales del release
`https://github.com/vectordotdev/vector/releases/tag/v0.61.0`:

| Asset | SHA-256 |
|---|---|
| `vector-0.61.0-x64.msi` | `3ac167f226204e141d164c6218ae54a2df77dda1b3322bef4b565d4066c4cfad` |
| `vector-0.61.0-x86_64-pc-windows-msvc.zip` | `6a04e833f9a91f874688e8087d768f5cb35d40e3271c87df6258e271915d0f49` |

### Opción A · MSI + servicio de Windows (recomendada)

1. Abre una consola **elevada**.
2. Ejecuta:

   ```powershell
   cd E:\trading-lab
   .\scripts\vector_install.ps1
   ```

   El script descarga el MSI, comprueba el SHA-256, instala con `msiexec /qn`,
   copia `config/vector/vector.yaml` a `C:\Program Files\Vector\config\vector.yaml`
   y valida la configuración.
3. Registra el servicio (el MSI no lo crea solo):

   ```powershell
   & 'C:\Program Files\Vector\bin\vector.exe' service install `
       --name Vector `
       --display-name 'Vector Observability' `
       --config 'C:\Program Files\Vector\config\vector.yaml'
   & 'C:\Program Files\Vector\bin\vector.exe' service start
   Set-Service -Name Vector -StartupType Automatic
   ```

   El servicio corre como `LocalSystem`, que puede leer el diario del Programador
   y los logs de MT5. `Get-Service Vector` debe mostrar `Running`.

### Opción B · zip oficial (portable, sin servicio)

```powershell
cd E:\trading-lab
.\scripts\vector_install.ps1 -Portable
.\data\vector\bin\vector.exe --config .\data\vector\vector.yaml
```

El zip se extrae en `data/vector/bin/` y la configuración se copia a
`data/vector/vector.yaml`. No se registra ninguna tarea.

### Comprobaciones después de instalar

```powershell
.\scripts\vector_test.ps1          # vector test: casos critical/warn/normal
.\data\vector\bin\vector.exe validate .\config\vector\vector.yaml   # portable
```

El MSI instala el binario en `C:\Program Files\Vector\bin\vector.exe`; el
servicio se registra aparte con `vector service install` (ver Opción A).

## Rutas de MT5

El terminal FTMO actual escribe en:

```text
C:\Users\PC\AppData\Roaming\MetaQuotes\Terminal\81A933A9AFC5DE3C23B15CAB19C63850
```

`vector.yaml` lee:

| Fuente | Ruta | Codificación |
|---|---|---|
| Diario del terminal | `<data_path>/logs/*.log` | **UTF-16 LE con BOM** |
| Diario de Experts | `<data_path>/MQL5/Logs/*.log` | **UTF-16 LE con BOM** |
| Guardián | `<data_path>/MQL5/Files/tradinglab_guardian.log` | UTF-8 |
| Programador de tareas | `Microsoft-Windows-TaskScheduler/Operational` | evento Windows |

La codificación se verificó el **2026-11-13** leyendo los primeros bytes de un
log real: `ff fe` (BOM UTF-16 LE) en terminal y Experts; el guardián empieza
con `2026.11.10...` en UTF-8. Si el terminal cambia de hash o de instalación,
actualiza las tres rutas de `config/vector/vector.yaml` y vuelve a validar.

## Clasificación

El transform `classify` añade `source`, `task`/`symbol`, `timestamp` UTC,
`severity` y `pattern`:

- **critical**: `Traceback`, `AutoTrading disabled`, `TRIGGER`/`BLOCK`/
  `CLOSE ticket=` del guardián, `retcode` 10006/10013/10014/10016/10019/10027/
  10031, y tareas `TradingLab-*` con `return code` distinto de 0 o fallo.
- **warn**: requotes, reconexiones y una desconexión aislada de MT5
  (`connection to ... lost` / `no connection`). La segunda desconexión del
  mismo patrón en 30 min la escala a critical el relevo.
- **info**: el resto. `alerts_only` filtra y solo deja warn/critical.

## Relevo de alertas

`lab alerts relay` lee solo las líneas nuevas de `logs/vector/alerts.jsonl`
desde el offset guardado en SQLite. Si el archivo no existe, no hace nada.
Deduplica por `(source, pattern)` durante 30 min, envía solo las critical con
`alerts.py` (Telegram/ntfy) y respeta el presupuesto semanal de alertas. Las
warn solo se cuentan en `vector_daily` para el resumen diario.

`TradingLab-Heartbeat` llama a `lab alerts relay` y a
`scripts/vector_cleanup.ps1` en cada pasada (cada 5 min). El relevo nunca
bloquea el latido.

## Tests

La sección `tests` de `config/vector/vector.yaml` cubre:

- una línea critical por patrón (traceback, AutoTrading, guardián, retcode,
  tarea con resultado distinto de 0);
- una línea warn por patrón (requote, reconexión);
- una línea normal que **no** debe salir por `alerts_only`.

```powershell
.\scripts\vector_test.ps1
```

Los tests del relevo están en `tests/test_vector_relay.py` (offset,
deduplicación, presupuesto y archivo ausente) y los del doctor en
`tests/test_vector_health.py`.
