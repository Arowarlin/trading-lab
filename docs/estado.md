# Estado operativo

Foto del 2026-11-11 de lo que **ya está corriendo** en paper/demo, qué mide cada
proceso, desde cuándo, cuándo tiene muestra suficiente y con qué comando se
revisa. Nada de esto opera en live.

| Proceso | Qué mide | Desde | Muestra suficiente | Revisar con |
|---|---|---|---|---|
| **F13** (`TradingLab-F13`, L-V 22:20) | Operativa del bot `qqq-trend-f13`: ciclos diarios, reconciliación, slippage, error de tamaño y hash congelado. El edge solo se evalúa a 6 meses o ≥20 trades. | **2026-11-09** | 8 semanas (95 % de ciclos) y **20 trades** para opinar del edge | `lab f13 status` · `lab f13 report` · `lab f13 check` · `lab readiness` |
| **Agents** (`TradingLab-Agents`, L-V 22:45) | Decisiones de los 4 analistas (lite) y su retorno a 1/5/20 días. | **2026-11-07** | **30 decisiones** con retorno a 20 días | `lab decisions` · `lab readiness` |
| **LLMCompare** (`TradingLab-LLMCompare`, L-V 18:30) | Lite vs deep por ticker: decisión, confianza, latencia y acuerdo; tasa `schema_ok`. | **2026-11-09** | 30 comparaciones por modelo (aviso si <30) | `lab llm status` · `lab llm report` · `lab llm ranking` |
| **DeepCompare** (`TradingLab-DeepCompare`, diario 02:30) | Pasada profunda de TradingAgents (4 analistas + debate + riesgo) para el mismo ticker, en el proveedor OpenCode Go. | **2026-11-09**, **pausada 2026-11-11**, **tarea deshabilitada 2026-11-12** | 30 pasadas con el proveedor con saldo | `lab agent-compare --report` · `lab models ranking` · `lab doctor` |
| **IntradayForward** (`TradingLab-IntradayForward`, cada 5 min en ventana) | Ejecución demo de los dos candidatos fijos: EURUSD `london_pullback` y USDJPY `tokyo_breakout`; 1 trade/día por bot y cierre por sesión. Añade `us100-trend-d1` (swing H4), **encendido el 2026-11-11**, solo en la primera barra H4 del día UTC. | **2026-11-10** | **60 días** de demo | `lab mt5 positions` · `logs/intraday_forward/forward_execute_*.log` · `lab intraday forward` (dry-run) |
| **Fills MT5** (dentro del ciclo IntradayForward) | Deals del terminal desde la última lectura para los magics del laboratorio; idempotente por `deal_id`. Los deals con magic ajeno se guardan como `manual`. | **2026-11-11** | tras cada ciclo | `lab journal` · `lab tca` · `lab mt5 positions` |
| **Drill** (`TradingLab-Drill`, domingo 03:00) | Simulación mensual del simulacro R8: inventario, canales y kill-switch, sin tocar nada. El simulacro real exige operador armado. | **2026-11-15** (primera) | 1 ejecución (mensual) | `lab drill --dry-run` · `logs/drill_*.log` |
| **Guardian** (EA `TradingLabGuardian` en MT5, siempre) | Defensa de equity dentro del terminal: equity, pico trailing y límites diario/total; escribe `tradinglab_guardian.log`. En **ALERT** solo avisa. | **2026-11-10** | **5 sesiones** en ALERT sin disparos | `lab guardian status` · `logs/intraday_forward/guardian_state.txt` · `MQL5/Files/tradinglab_guardian.log` |
| **AI-London** (`TradingLab-AI-London`, L-V 03:05 DOM) | Preflight, snapshot intraday de EURUSD/GBPUSD/XAUUSD/USDJPY, propose/execute o skip con motivo. Solo demo. | **registrada 2026-11-12** | cada sesión London | `logs/ai_trader/<fecha>_london.log` · `lab doctor` (IA tareas) |
| **AI-NY** (`TradingLab-AI-NY`, L-V 09:35 y 10:35 DOM) | Igual para US100/XAUUSD intraday y plan de scalping; el script decide la apertura NY según DST y sale en la otra. | **registrada 2026-11-12** | cada sesión NY | `logs/ai_trader/<fecha>_ny.log` · `lab doctor` (IA tareas) |
| **AI-Daily** (`TradingLab-AI-Daily`, L-V 18:15 DOM) | Snapshot swing del universo y propose/execute o skip con motivo. | **registrada 2026-11-12** | diario L-V | `logs/ai_trader/<fecha>_daily.log` · `lab doctor` (IA tareas) |
| **AI-Scalp** (`TradingLab-AI-Scalp`, L-V cada minuto 09:25-13:05 DOM) | `lab ai-trader scalp` sin LLM; ventana 09:30-12:00 NY, plan activo y candado. | **registrada 2026-11-12** | cada minuto en ventana | `logs/ai_trader/<fecha>_scalp.log` · `lab doctor` (IA tareas) |
| **AI-Manage** (`TradingLab-AI-Manage`, cada 15 min dom 17:00-vie 18:00 DOM) | `lab ai-trader manage` sin LLM: BE, trailing, Donchian/SMA5 y cierres de sesión. | **registrada 2026-11-12** | cada 15 min en ventana | `logs/ai_trader/<fecha>_manage.log` · `lab doctor` (IA tareas) |

Las tareas **AI-*** se registraron el **2026-11-12** con
`scripts/register_ai_trader_tasks.ps1` (hora de República Dominicana, usuario
actual, sin elevación, solo con sesión iniciada). Las cinco quedan `Ready`;
`AI-Scalp` está habilitada y sin plan solo registra `no_plan`. El script de
sesión sale sin LLM fuera de ventana/mercado/kill-switch y deja log y estado en
`logs/ai_trader/`; `lab doctor` muestra `IA tareas` si una tarea no corrió o
falló.

Notas de lectura:

- **Agents** y **LLMCompare** son tareas distintas: la primera genera decisiones
  con el modelo lite; la segunda compara ese lite con el deep y deja la fila en
  `agent_comparisons` (con `deep_error` si el deep falla).
- El **DeepCompare** está **pausado**: el proveedor OpenCode Go devolvió
  `402` por saldo agotado y la clave guardada `401` (inválida). La tarea
  programada quedó **deshabilitada** (`Disable-ScheduledTask`, no se borra) el
  **2026-11-12**, ejecutada desde un proceso elevado. `scripts\deep_compare_nightly.ps1`
  mantiene el guard: sale sin lanzar el deep si el proveedor no responde. El deep
  se corre **bajo demanda**. Para reactivarlo: **primero** recargar saldo y
  **después** regenerar `LAB_DEEP_LLM_API_KEY`; en ese orden. Las filas de error
  que ya están en `agent_comparisons` se conservan marcadas como `deep_error` y
  quedan fuera del reporte.
  - **Observación 2026-11-12:** el proveedor volvió a responder (completion de
    1 token, HTTP 200) y `lab doctor` lo ve `OK`. Aun así se mantiene la pausa
    como decisión del operador: el deep se corre **bajo demanda** hasta que se
    confirme que el saldo aguanta la pasada completa. Estado verificado de la
    tarea: `State = Disabled`, `Settings.Enabled = False`. Para volver a
    programarla: recargar saldo, regenerar la clave y después
    `Enable-ScheduledTask -TaskName 'TradingLab-DeepCompare'` (requiere elevación,
    igual que deshabilitarla).
- El **forward** no es una validación: los dos candidatos tienen Sharpe negativo
  en backtest y se usan como excepción forward documentada. El tercero
  (`us100-trend-d1`) está **incubando**; se encendió el 2026-11-11 y sigue en
  demo, sin live.
- El **guardián** no depende de Python: si el proceso se cae, el EA sigue.
- El **Diario** reconstruye operaciones cerradas desde `fills`: ahora incluye
  los deals de MT5 (magic del laboratorio → bot `forward:<id>`; magic ajeno →
  `manual`) y empareja FIFO en largo y en corto. Usa `contract_size` para el
  PnL de CFDs y suma el swap; los fills del paper siguen funcionando igual.
  `entry_order_id=0` en los deals de MT5 significa "sin orden del laboratorio".
- **IA discrecional (3 estilos)**: biblioteca de 10 estrategias con reglas
  exactas en `ai_setups.py`; el LLM solo elige estilo, símbolo, estrategia,
  timeframe y dirección. La asignación del playbook v1 está en
  `config/ai_trader.yaml` (`scalping`: M1/M5; `intraday`: M15/H1; `swing`:
  H4/D1). `scalping` usa cuatro estrategias propias (`ema_ribbon_pullback`,
  `vwap_bounce`, `orb_5m`, `momentum_burst`) solo en US100 y XAUUSD, con un
  `plan` diario por símbolo (setups, bias, horas prohibidas y motivo) y el
  comando `scalp` sin LLM, pensado para ejecutarse cada minuto dentro de
  09:30–12:00 NY. Sin plan activo, el scalper no opera; si MT5 no responde, el
  dato tiene más de dos velas de antigüedad o el kill-switch está activo,
  registra el `skip` y no envía nada. `snapshot --style --symbols` devuelve el
  JSON compacto (≤3.000 tokens) con indicadores, setups válidos, coste/R,
  eventos 24 h, posiciones y presupuesto. `manage` aplica breakeven a 0,5R,
  trailing de 1 ATR desde 1R, el canal de 10 días de `donchian_turtle`, la
  salida D1 sobre SMA5 de `rsi2_connors` y los cierres de sesión de `orb_ny`
  (16:00 NY) y `london_breakout` (16:00 Londres), sin alejar nunca el stop y
  solo sobre los magics 20261191/92/93. El marcador (`lab ai-trader scoreboard`)
  compara cada celda con su sombra aleatoria y, en scalping, con la sombra «sin
  plan», con IC bootstrap del 90 % y estados explorando/ganadora/perdedora/
  neutral; solo cuenta `source=forward`. El panel web «IA discrecional» muestra
  posiciones por estilo, presupuesto diario por estilo/global, marcador y plan
  de scalping activo, de solo lectura. El skill `trading-lab-operador` contiene
  el procedimiento London/NY/daily y su copia está en `docs/ai_trader_skill.md`.
  El **replay ciego** (`lab ai-trader replay --style intraday|swing`) muestrea
  setups históricos anteriores al corte de `2026-11-A`, pide take/skip a
  DeepSeek V4.1 Flash en lotes y guarda `ai_decisions` con `source=replay`;
  queda fuera del marcador forward, del panel y de la destilación, y solo
  puede pausar celdas con n≥50 y IC90 de la diferencia vs sombra < 0.

## No construir hasta

| Condición | Qué desbloquea |
|---|---|
| **Guardián 5/5** sesiones ALERT sin disparos (hoy 2/5; 2026-11-16) | Pasar a `CLOSE` con `scripts\guardian_enable_close.ps1` y `defense: enforce` en el forward |
| **Forward US100 60 días** de demo (incubando desde 2026-11-11; **encendido el 2026-11-11**, ventana hasta 2027-01-10) | Decidir si se intenta un challenge con esa exposición (k=0,75) |
| **Decisiones n ≥ 30** con retorno a 20 días (hoy 10, 0 con retorno) | Extraer lecciones automáticas y comparar modelos con muestra |
| **30 operaciones cerradas** (hoy 0 cerradas de bots; el diario reconstruye) | MFE/MAE por operación y replay del Time Machine sobre casos reales |

Mientras no se cumplan, no se añaden familias, no se sube exposición y no se
activa ningún bot: se mide y se espera.
