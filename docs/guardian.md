# Guardián de equity en MetaTrader 5

Defensa de equity dentro del terminal, pensada para seguir actuando aunque
Python se caiga. Es **solo demo/paper**: no abre operaciones, no activa bots y
no sustituye al kill-switch de Python. Su trabajo es avisar (ALERT) o cerrar
las posiciones de los `magic` del forward (CLOSE) si la cuenta rompe los
límites.

Código propio. No se copió nada de los repositorios externos revisados.

## Piezas

| Pieza | Ruta | Función |
|---|---|---|
| Exportador | `src/tradinglab/guardian.py` | Valida cuenta, límites efectivos y magics; escribe el JSON |
| CLI | `lab guardian export\|status` | Exporta y consulta el último JSON |
| EA | `mql5/TradingLabGuardian.mq5` | Vigila la equity dentro de MT5 |
| Tests | `tests/test_guardian.py` | Fixtures sintéticas, sin terminal |

## Instalación

1. Exporta el JSON:

   ```powershell
   .\.venv\Scripts\lab.exe guardian export --account ftmo_demo
   ```

2. Copia el JSON al terminal. Si `config/lab.yaml` tiene `mt5.data_path`
   (la carpeta de datos del terminal, la que contiene `MQL5/`), el comando
   escribe directamente en `MQL5/Files/tradinglab_guardian.json`. Si no,
   escribe en `data/guardian.json` y avisa: cópialo a mano a
   `<terminal>/MQL5/Files/tradinglab_guardian.json`.

3. Copia `mql5/TradingLabGuardian.mq5` a
   `<terminal>/MQL5/Experts/TradingLab/` y compílalo en MetaEditor.

4. Si vas a usar ntfy, permite la URL en **Herramientas → Opciones →
   Expert Advisors → Permitir WebRequest para las siguientes URLs**.

5. Adjunta el EA a un gráfico, con `Mode=ALERT` y, si quieres, `NtfyUrl`.
   Revisa `MQL5/Files/tradinglab_guardian.log`.

## Qué lee y qué vigila

El JSON lo genera Python a partir de:

- `config/accounts.yaml`: cuenta, tamaño y, para cuentas propias, sus límites.
- `config/prop.yaml` vía `prop/rules.py`: para cuentas de fondeo, los límites
  **efectivos** (con el colchón). En FTMO 100k: diario **4,5%** y máximo
  **9%**.
- `config/intraday_forward.yaml`: los `magic` que puede cerrar.

Campos del JSON:

```json
{
  "version": 1,
  "generated_at": "2026-11-10T23:04:07+00:00",
  "account": "ftmo_demo",
  "account_size": 100000.0,
  "daily_loss_pct": 0.045,
  "max_drawdown_pct": 0.09,
  "reset_tz": "Europe/Prague",
  "reset_time": "00:00",
  "reset_utc_offset_minutes": 60,
  "magics": [20261151, 20261152],
  "bots": ["eurusd-london-pullback-forward", "usdjpy-tokyo-breakout-forward"],
  "limits_source": "prop.yaml:ftmo/challenge:effective"
}
```

El EA no inventa límites: si falta un campo, no arranca y lo escribe en el
log. `DailyLossPct` y `TrailingDDPct` son opcionales y, si son mayores que 0,
**endurecen** el límite del JSON (se expresan en porcentaje, por ejemplo 4.5).

MQL5 no trae base de datos de zonas horarias. Por eso Python resuelve
`reset_tz` a `reset_utc_offset_minutes` en el momento de exportar. **Vuelve a
exportar después de un cambio de horario de verano** (o semanalmente) para que
el corte de las 00:00 locales siga siendo correcto. El JSON guarda también
`reset_tz` para trazabilidad.

## Comportamiento

- **Base del día:** equity en el primer tick después de las 00:00 locales.
  Se persiste en `GlobalVariable("TradingLabGuardianDayStart")`.
- **Pico trailing:** máximo de equity visto; nunca baja. Se persiste en
  `GlobalVariable("TradingLabGuardianPeak")`.
- **Disparo:** `(base - equity) / base >= daily_loss_pct` o
  `(pico - equity) / pico >= max_drawdown_pct`.
- **ALERT:** `Print`, línea en el log y un POST a ntfy por día. No cierra.
- **CLOSE:** cierra **solo** posiciones cuyo `magic` esté en `magics`; el
  resto no se toca. Escribe `MQL5/Files/tradinglab_guardian_block.flag` y
  `GlobalVariable("TradingLabGuardianBlocked", 1)`. Insiste cada 2 s con las
  posiciones gestionadas que reaparezcan.
- **Reset:** al cambiar el día local, base = equity actual, se borra el flag y
  se permite volver a abrir. El pico trailing **no** se resetea.
- Cada acción queda en `MQL5/Files/tradinglab_guardian.log`.

El bloqueo de nuevas aperturas es cooperativo: este EA no abre nada, así que
publica el flag y la variable global para que otros EAs o scripts lo
consulten. El runner de Python no lo consulta todavía; si Python está caído,
tampoco abre.

## Probar con equity sintética (Strategy Tester)

El Strategy Tester no permite inyectar equity sin operaciones. Para probar la
lógica de umbrales, el EA trae un input de pruebas:

1. Crea `MQL5/Files/guardian_equity.csv` con una equity por línea. Por
   ejemplo, para probar el límite diario del 4,5%:

   ```text
   100000
   100000
   99500
   99000
   95500
   95000
   96000
   ```

   Para probar el trailing, empieza en 100000, sube a 110000 y baja a 99000.

2. En el Strategy Tester, elige un símbolo cualquiera, modo **Every tick** o
   **Every tick based on real ticks**, depósito inicial 100000.

3. Adjunta `TradingLabGuardian` con `Mode=ALERT` y
   `TestEquityFile=guardian_equity.csv`. El EA lee una línea por tick de
   timer; al agotarlas repite la última.

4. Comprueba que el `Print` y el log aparecen al cruzar el umbral. En el
   tester `WebRequest` no funciona; el aviso ntfy se prueba en demo.

5. Repite con `Mode=CLOSE` y una posición abierta con `magic=20261151` en una
   cuenta demo: debe cerrarla y dejar intacta cualquier posición con otro
   `magic`. El sintético sirve para los umbrales; el cierre real se prueba en
   demo.

## Regla de activación

`defense_mode: enforce` en `config/intraday_forward.yaml` **solo** después de
**5 días de sesión en ALERT sin falsos positivos** (sin avisos por equity
normal, por ejemplo por depósitos, retiros o reinicios). Mientras tanto:
`defense_mode: report` en Python y `Mode=ALERT` en el EA.

## Comandos

```powershell
.\.venv\Scripts\lab.exe guardian export --account ftmo_demo
.\.venv\Scripts\lab.exe guardian status
```

`status` muestra la ruta, si es el destino del terminal o el respaldo, la
cuenta, la antigüedad del JSON, los límites y los magics. Si no hay JSON:
**Sin datos**.
