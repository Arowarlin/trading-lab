# Backups y secretos

Fecha de revisión: 2026-11-06.

## Modelo actual

- Los secretos (Alpaca, MT5, ProjectX, FRED, Telegram, OpenAI) se guardan en
  **Windows Credential Manager** con `keyring` (servicio `tradinglab`).
- `.env` sigue existiendo como **fallback local**, pero ya **no se copia** en
  los zips de backup.
- Precedencia al cargar: variable de shell > keyring > `.env`.
- El backup incluye código, configuración, tests, scripts, docs, informes,
  `data\lab.db`, historial git y `.env.example`; **nunca** `.env`.

## Comandos

```powershell
# migrar los secretos actuales de .env a Credential Manager
.\.venv\Scripts\python.exe scripts\migrate_secrets.py

# ver qué claves hay (nunca muestra valores)
.\.venv\Scripts\python.exe scripts\migrate_secrets.py --status

# backup + verificación automática de restauración
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\backup.ps1

# verificar un zip concreto
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\restore_test.ps1 `
  -ZipPath "F:\TradingLabBackups\trading-lab_YYYYMMDD_HHMMSS.zip"
```

`restore_test.ps1` comprueba:

1. archivos mínimos (`README.md`, `config/lab.yaml`, `src`, `data/lab.db`);
2. que no haya `.env` ni `.env.*` dentro del zip;
3. que ningún valor real de secreto aparezca en los archivos de texto;
4. que no haya asignaciones de secretos con valor en `src/config/scripts/tests`;
5. `PRAGMA integrity_check` de SQLite.

## Backups antiguos

En `F:\TradingLabBackups` hay dos zips antiguos que **sí contienen `.env`**:

| Zip | Fecha | Contiene `.env` |
|---|---|---|
| `trading-lab_20261106_202735.zip` | 2026-11-06 20:27 | sí |
| `trading-lab_20261106_204317.zip` | 2026-11-06 20:43 | sí |
| `trading-lab_20261106_233622.zip` | 2026-11-06 23:36 | no |
| `trading-lab_20261106_233758.zip` | 2026-11-06 23:38 | no |

**No se han borrado**: la regla del proyecto prohíbe borrar datos sin
confirmación. Recomendación: eliminarlos o moverlos a un soporte cifrado cuando
el usuario lo autorice.

## restic vs Kopia

Verificado el 2026-11-06 en GitHub/PyPI:

| Herramienta | Versión | Licencia | Ventajas | Inconvenientes |
|---|---|---|---|---|
| **restic** | 0.19.1 (2026-07-05) | BSD-2-Clause | maduro, CLI simple, cifrado, incremental, deduplicación, Windows, muchos backends | sin GUI; la clave hay que custodiarla |
| **Kopia** | 0.23.1 (2026-06-16) | Apache-2.0 | GUI, políticas, deduplicación, snapshots | más piezas; curva algo mayor |

**Propuesta: restic** para el laboratorio, porque todo el flujo es CLI/PowerShell
y se puede programar junto a las tareas existentes. Kopia quedaría como opción
si se quiere GUI. No se instala nada en esta fase.

Esquema recomendado:

1. Zip local rápido en `F:` (sin secretos) para restaurar el código.
2. Repositorio restic cifrado en un **disco externo/USB**, con contraseña
   guardada fuera del repo (Credential Manager o gestor de contraseñas).
3. `restic check` mensual y una prueba de restauración trimestral.

`F:` es un disco local: si se pierde el PC, se pierde también. Mantén una copia
externa cifrada y no subas el zip a la nube.
