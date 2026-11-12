# Estado operativo

Foto del 2026-11-11 de lo que **ya está corriendo** en paper/demo, qué mide cada
proceso, desde cuándo, cuándo tiene muestra suficiente y con qué comando se
revisa. Nada de esto opera en live.

| Proceso | Qué mide | Desde | Muestra suficiente | Revisar con |
|---|---|---|---|---|
| **F13** (`TradingLab-F13`, L-V 22:20) | Operativa del bot `qqq-trend-f13`: ciclos diarios, reconciliación, slippage, error de tamaño y hash congelado. El edge solo se evalúa a 6 meses o ≥20 trades. | **2026-11-09** | 8 semanas (95 % de ciclos) y **20 trades** para opinar del edge | `lab f13 status` · `lab f13 report` · `lab f13 check` · `lab readiness` |
| **Agents** (`TradingLab-Agents`, L-V 22:45) | Decisiones de los 4 analistas (lite) y su retorno a 1/5/20 días. | **2026-11-07** | **30 decisiones** con retorno a 20 días | `lab decisions` · `lab readiness` |
| **LLMCompare** (`TradingLab-LLMCompare`, L-V 18:30) | Lite vs deep por ticker: decisión, confianza, latencia y acuerdo; tasa `schema_ok`. | **2026-11-09** | 30 comparaciones por modelo (aviso si <30) | `lab llm status` · `lab llm report` · `lab llm ranking` |
| **DeepCompare** (`TradingLab-DeepCompare`, diario 02:30) | Pasada profunda de TradingAgents (4 analistas + debate + riesgo) para el mismo ticker, en el proveedor OpenCode Go. | **2026-11-09**, **pausada 2026-11-11** | 30 pasadas con el proveedor con saldo | `lab agent-compare --report` · `lab models ranking` · `lab doctor` |
| **IntradayForward** (`TradingLab-IntradayForward`, cada 5 min en ventana) | Ejecución demo de los dos candidatos fijos: EURUSD `london_pullback` y USDJPY `tokyo_breakout`; 1 trade/día por bot y cierre por sesión. Añade `us100-trend-d1` (swing H4) solo en la primera barra H4 del día UTC, todavía `enabled:false`. | **2026-11-10** | **60 días** de demo | `lab mt5 positions` · `logs/intraday_forward/forward_execute_*.log` · `lab intraday forward` (dry-run) |
| **Fills MT5** (dentro del ciclo IntradayForward) | Deals del terminal desde la última lectura para los magics del laboratorio; idempotente por `deal_id`. Los deals con magic ajeno se guardan como `manual`. | **2026-11-11** | tras cada ciclo | `lab journal` · `lab tca` · `lab mt5 positions` |
| **Drill** (`TradingLab-Drill`, domingo 03:00) | Simulación mensual del simulacro R8: inventario, canales y kill-switch, sin tocar nada. El simulacro real exige operador armado. | **2026-11-15** (primera) | 1 ejecución (mensual) | `lab drill --dry-run` · `logs/drill_*.log` |
| **Guardian** (EA `TradingLabGuardian` en MT5, siempre) | Defensa de equity dentro del terminal: equity, pico trailing y límites diario/total; escribe `tradinglab_guardian.log`. En **ALERT** solo avisa. | **2026-11-10** | **5 sesiones** en ALERT sin disparos | `lab guardian status` · `logs/intraday_forward/guardian_state.txt` · `MQL5/Files/tradinglab_guardian.log` |

Notas de lectura:

- **Agents** y **LLMCompare** son tareas distintas: la primera genera decisiones
  con el modelo lite; la segunda compara ese lite con el deep y deja la fila en
  `agent_comparisons` (con `deep_error` si el deep falla).
- El **DeepCompare** está **pausado**: el proveedor OpenCode Go devuelve
  `402` por saldo agotado y la clave guardada devuelve `401` (inválida). La
  tarea programada se deshabilita con `Disable-ScheduledTask` (no se borra) y,
  mientras no haya permisos de administrador, `scripts\deep_compare_nightly.ps1`
  sale sin lanzar el deep si el proveedor no responde. El deep se corre **bajo
  demanda**. Para reactivarlo: **primero** recargar saldo y **después**
  regenerar `LAB_DEEP_LLM_API_KEY`; en ese orden. Las filas de error que ya
  están en `agent_comparisons` se conservan marcadas como `deep_error` y quedan
  fuera del reporte.
  - **Observación 2026-11-12:** el proveedor volvió a responder (completion de
    1 token, HTTP 200) y `lab doctor` lo ve `OK`. La tarea sigue en `Ready`
    porque deshabilitarla exige elevación (el usuario solo tiene lectura sobre
    `System32\Tasks`). Se mantiene la pausa como decisión del operador: el deep
    se corre **bajo demanda** hasta que se confirme que el saldo aguanta la
    pasada completa. El guard del script nocturno sigue ahí y solo bloquea si el
    proveedor falla de verdad.
- El **forward** no es una validación: los dos candidatos tienen Sharpe negativo
  en backtest y se usan como excepción forward documentada. El tercero
  (`us100-trend-d1`) está **incubando** y sigue `enabled:false`.
- El **guardián** no depende de Python: si el proceso se cae, el EA sigue.
- El **Diario** reconstruye operaciones cerradas desde `fills`: ahora incluye
  los deals de MT5 (magic del laboratorio → bot `forward:<id>`; magic ajeno →
  `manual`) y empareja FIFO en largo y en corto. Usa `contract_size` para el
  PnL de CFDs y suma el swap; los fills del paper siguen funcionando igual.
  `entry_order_id=0` en los deals de MT5 significa "sin orden del laboratorio".

## No construir hasta

| Condición | Qué desbloquea |
|---|---|
| **Guardián 5/5** sesiones ALERT sin disparos (hoy 2/5; 2026-11-16) | Pasar a `CLOSE` con `scripts\guardian_enable_close.ps1` y `defense: enforce` en el forward |
| **Forward US100 60 días** de demo (incubando desde 2026-11-11; `enabled:false` hasta que el operador lo encienda con `docs/encendido.md`) | Decidir si se intenta un challenge con esa exposición (k=0,75) |
| **Decisiones n ≥ 30** con retorno a 20 días (hoy 10, 0 con retorno) | Extraer lecciones automáticas y comparar modelos con muestra |
| **30 operaciones cerradas** (hoy 0 cerradas de bots; el diario reconstruye) | MFE/MAE por operación y replay del Time Machine sobre casos reales |

Mientras no se cumplan, no se añaden familias, no se sube exposición y no se
activa ningún bot: se mide y se espera.
