# Estado operativo

Foto del 2026-11-11 de lo que **ya está corriendo** en paper/demo, qué mide cada
proceso, desde cuándo, cuándo tiene muestra suficiente y con qué comando se
revisa. Nada de esto opera en live.

| Proceso | Qué mide | Desde | Muestra suficiente | Revisar con |
|---|---|---|---|---|
| **F13** (`TradingLab-F13`, L-V 22:20) | Operativa del bot `qqq-trend-f13`: ciclos diarios, reconciliación, slippage, error de tamaño y hash congelado. El edge solo se evalúa a 6 meses o ≥20 trades. | **2026-11-13** (reinicio; antes 2026-11-09 en `paper_main`) | 8 semanas (95 % de ciclos) y **20 trades** para opinar del edge | `lab f13 status` · `lab f13 report` · `lab f13 check` · `lab readiness` |
| **Vector** (proceso local, opcional) | Lee logs del lab, diario MT5 (UTF-16 LE), Experts y guardián; clasifica warn/critical y escribe `logs/vector/all-*.jsonl` y `alerts.jsonl`. Solo observa. | **instalado 2026-11-13** (0.61.0) | 14 días de `all-*.jsonl`; revisión con `lab doctor` | `scripts/vector_test.ps1` · `lab alerts relay` · `docs/vector.md` |
| **EA US100 FTMO1** (MT5 externo) | EA del operador en `US100.cash`, magics `93010001`/`93020001`, setfile v3 challenge. El laboratorio lo registra, mide sus fills y lo pasa por DSR/PBO/WF/regímenes/MC; **no lo ejecuta**. Sus magics entran en el guardián y en el stop diario de cuenta; el tope por símbolo es 2 % en `US100.cash`. | **2026-11-14** | validación completa; forward pre-registrado (`2bfad45c…`), reloj pendiente del primer fill | `lab ea status` · `lab ea forward` · `lab ea horizon` · `docs/ea_us100_ftmo1.md` |
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
actual, sin elevación, solo con sesión iniciada). Las cinco quedan `Ready`
salvo **`AI-Scalp`, deshabilitada hasta el primer plan**: se habilita con
`Enable-ScheduledTask -TaskName 'TradingLab-AI-Scalp'` después de crear el plan
con `lab ai-trader plan`. El script de sesión sale sin LLM fuera de
ventana/mercado/kill-switch y deja log y estado en `logs/ai_trader/`;
`lab doctor` muestra `IA tareas` si una tarea no corrió o falló.

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
  El **aprendizaje diario** (`lab ai-trader learn`, sin LLM al final del daily)
  solo aplica cambios que reducen riesgo (pausa, exclusión de hora/día/
  condición y mitad de riesgo por símbolo), con máximo 2 por semana y subida de
  `playbook_version`; reactivar, subir riesgo o ampliar quedan como lección
  `proposed`. Cada cambio actualiza el YAML, el skill y deja evidencia en
  `ai_learn_changes`.
- **Destilación semanal**: `lab ai-trader distill` corre domingos 12:00 DOM sin
  LLM. De una celda ganadora aprende un filtro de profundidad ≤2, escribe un
  candidato `ai-<estrategia>-<símbolo>-<tf>` con `enabled:false` y magic propio,
  y lo valida con/sin filtro (costes, DSR +2, PBO, walk-forward y Monte Carlo
  FTMO). Si pasa, incuba 60 días y la celda IA queda `destilada`; el LLM no la
  opera. El panel muestra el embudo IA → destilado → validado → incubando →
  promovible. `TradingLab-AI-Distill` está en el script de registro pero **no
  registrada**.
- **Scalping**: primer plan activo para US100.cash y XAUUSD (4 setups M1/M5,
  bias both, horas prohibidas 09:30-09:45 y 11:30-12:00 NY). `TradingLab-AI-Scalp`
  quedó `Ready` el 2026-11-12; próxima ejecución 2026-11-13 09:25 DOM. Sin plan
  no opera; el plan se recrea cada sesión.
  - **Orden real en hora de República Dominicana (invierno):** apertura de NY
    **10:30**, sesión `ny` **10:35**, y el primer scalp con plan **después de
    esa hora** (la tarea corre cada minuto). En verano el orden es 09:30 /
    09:35 / después. La sesión `ny` crea el plan del día para US100.cash y
    XAUUSD con `lab ai-trader plan` si aún no existe; los planes de días
    anteriores no valen.
- **2026-11-B**: **ejecutada el 2026-11-12** con 232 pruebas DSR ya
  contadas. `run_id=0315bb0089ea`, 232 celdas, 23 candidatas tras la
  meseta y **0 confirmadas** en el holdout; no se registró ningún bot.
  Informe: `reports/research/campaign/2026-11-B.md`. **Contaminada**: su
  holdout se solapa con el descubrimiento de `2026-11-A` y la regla (c) se
  decidió tras ver el anexo; el tramo `2024-08-08 → hoy` queda consumido para
  esos activos y no se reutiliza. Las pruebas siguen contando. `2026-11-A`
  sigue intacta.

## Operación, datos y respaldo

- **Campañas**: `lab campaign run` exige `--confirm` y
  `--approved-by-operator`; `register` rechaza holdouts que solapan con el
  descubrimiento o el holdout de campañas ejecutadas sobre los mismos activos.
  `2026-11-B` queda marcada como contaminada y no se reutiliza su tramo
  `2024-08-08 → hoy`.
- **Slippage y límites IA**: `slippage_price` por símbolo y coste/R con
  `2 × slippage_price`; sin dato, `propose`/`scalp` rechazan. `max_open` 2 por
  estilo, global 5; swing 2 trades/día y coste/R 0,05.
- **Stop de cuenta**: `account_daily_stop: 0.04` en `config/accounts.yaml`.
  Suma realizada + flotante de todos los magics; si se toca, ningún carril abre
  hasta el reset. `PropGuard`, forward y `ai_trader` lo consultan; el panel
  muestra lo consumido por carril y `guardian.json` exporta 0,04 con los seis
  magics.
- **Latidos**: `lab heartbeat` gestiona 12 checks de Healthchecks.io en keyring.
  Las tareas F13, Agents, LLMCompare, IntradayForward, AI-London/NY/Daily/
  Scalp/Manage, Drill y backup hacen `start` + `ok|fail`; sin URL se omiten y
  `lab doctor` avisa. `TradingLab-Heartbeat` (cada 5 min, solo si MT5 y SQLite
  abren) está registrada como `TradingLab-Heartbeat` (cada 5 min).
- **Backup offsite**: `backup.ps1 -Offsite` cifra AES-256-CBC con contraseña
  de keyring (`BACKUP_PASSWORD`), copia al `backup.offsite_dir` configurado
  (`C:/Users/PC/OneDrive/TradingLabBackups`),
  comprueba el 50 % de espacio libre, verifica descifrado y retiene 14 diarias
  + 8 semanales. `restore_test.ps1` descifra y prueba el zip.
- **Lease**: `execution_lease` con host/hora y caducidad de 2 minutos. `ai_trader`
  y `forward_intraday` se niegan a operar si el lease vigente es de otro host.
- **Control cruzado**: `lab data crosscheck` compara H1 de MT5 con ticks
  Dukascopy; informe en `reports/data/crosscheck/`. `datacheck` avisa si la
  correlación de retornos 1h baja de 0,95.
- **COT**: `lab data cot` guarda el informe público de la CFTC con fecha de
  referencia y fecha de publicación; `latest_as_of` impide lookahead.
- **VIX**: `lab data vix` actualiza VIXCLS/VXVCLS desde FRED, ratio VIX/VIX3M y
  flag contango/backwardation. Se expone en `conditioners.today_flags` y en el
  snapshot IA, sin tocar tablas de multiplicadores.
- **Campañas nuevas**: no se abre ninguna ahora. El holdout de `2026-11-B`
  está consumido y `register` rechaza solapamientos; hay que esperar datos
  posteriores al `2026-11-12` o activos fuera del universo consumido. En este
  bloque no se ejecutó ninguna campaña ni barrido.
- **F13**: migrado de `paper_main` a `alpaca_paper` el **2026-11-13** para
  medir slippage, reconciliación y tamaño contra un bróker real. Informe de los
  4 días archivado en `reports/f13/paper_main_2026-11-09_a_13.md`; la parte de
  F13 (5 QQQ) se cerró con una orden auditada del bróker interno. Nueva ventana
  de 8 semanas: **2026-11-13 → 2027-01-08**. Hash `26fd15fdbebd3db4…`;
  `f13 config-check` OK. La reconciliación de `alpaca_paper` separa los fills
  de F13 (QQQ) y del daytrader (AAPL).

## No construir hasta

| Condición | Qué desbloquea |
|---|---|
| **Guardián 5/5** sesiones ALERT sin disparos (hoy 2/5; 2026-11-16) | Pasar a `CLOSE` con `scripts\guardian_enable_close.ps1` y `defense: enforce` en el forward |
| **Forward US100 60 días** de demo (incubando desde 2026-11-11; **encendido el 2026-11-11**, ventana hasta 2027-01-10) | Decidir si se intenta un challenge con esa exposición (k=0,75) |
| **Decisiones n ≥ 30** con retorno a 20 días (hoy 10, 0 con retorno) | Extraer lecciones automáticas y comparar modelos con muestra |
| **30 operaciones cerradas** (hoy 0 cerradas de bots; el diario reconstruye) | MFE/MAE por operación y replay del Time Machine sobre casos reales |

Mientras no se cumplan, no se añaden familias, no se sube exposición y no se
activa ningún bot: se mide y se espera.
