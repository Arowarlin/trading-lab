# Estado operativo

Foto del 2026-11-11 de lo que **ya está corriendo** en paper/demo, qué mide cada
proceso, desde cuándo, cuándo tiene muestra suficiente y con qué comando se
revisa. Nada de esto opera en live.

| Proceso | Qué mide | Desde | Muestra suficiente | Revisar con |
|---|---|---|---|---|
| **F13** (`TradingLab-F13`, L-V 22:20) | Operativa del bot `qqq-trend-f13`: ciclos diarios, reconciliación, slippage, error de tamaño y hash congelado. El edge solo se evalúa a 6 meses o ≥20 trades. | **2026-11-09** | 8 semanas (95 % de ciclos) y **20 trades** para opinar del edge | `lab f13 status` · `lab f13 report` · `lab f13 check` · `lab readiness` |
| **Agents** (`TradingLab-Agents`, L-V 22:45) | Decisiones de los 4 analistas (lite) y su retorno a 1/5/20 días. | **2026-11-07** | **30 decisiones** con retorno a 20 días | `lab decisions` · `lab readiness` |
| **LLMCompare** (`TradingLab-LLMCompare`, L-V 18:30) | Lite vs deep por ticker: decisión, confianza, latencia y acuerdo; tasa `schema_ok`. | **2026-11-09** | 30 comparaciones por modelo (aviso si <30) | `lab llm status` · `lab llm report` · `lab llm ranking` |
| **DeepCompare** (`TradingLab-DeepCompare`, diario 02:30) | Pasada profunda de TradingAgents (4 analistas + debate + riesgo) para el mismo ticker. | **2026-11-09** | 30 pasadas (y con el modelo de ≥16k de contexto) | `lab agent-compare --report` · `lab models ranking` |
| **IntradayForward** (`TradingLab-IntradayForward`, cada 5 min en ventana) | Ejecución demo de los dos candidatos fijos: EURUSD `london_pullback` y USDJPY `tokyo_breakout`; 1 trade/día por bot y cierre por sesión. | **2026-11-10** | **60 días** de demo | `lab mt5 positions` · `logs/intraday_forward/forward_execute_*.log` · `lab intraday forward` (dry-run) |
| **Drill** (`TradingLab-Drill`, domingo 03:00) | Simulación mensual del simulacro R8: inventario, canales y kill-switch, sin tocar nada. El simulacro real exige operador armado. | **2026-11-15** (primera) | 1 ejecución (mensual) | `lab drill --dry-run` · `logs/drill_*.log` |
| **Guardian** (EA `TradingLabGuardian` en MT5, siempre) | Defensa de equity dentro del terminal: equity, pico trailing y límites diario/total; escribe `tradinglab_guardian.log`. En **ALERT** solo avisa. | **2026-11-10** | **5 sesiones** en ALERT sin disparos | `lab guardian status` · `logs/intraday_forward/guardian_state.txt` · `MQL5/Files/tradinglab_guardian.log` |

Notas de lectura:

- **Agents** y **LLMCompare** son tareas distintas: la primera genera decisiones
  con el modelo lite; la segunda compara ese lite con el deep y deja la fila en
  `agent_comparisons` (con `deep_error` si el deep falla).
- El **DeepCompare** necesita LM Studio con ≥16k de contexto; con 8k falla y la
  fila queda marcada como error.
- El **forward** no es una validación: los dos candidatos tienen Sharpe negativo
  en backtest y se usan como excepción forward documentada.
- El **guardián** no depende de Python: si el proceso se cae, el EA sigue.
- El **Diario** reconstruye operaciones cerradas desde `fills` (solo largos: los
  bots del laboratorio son long-only). MT5 registra la orden y el TCA, pero
  todavía no escribe `fills`, así que las operaciones de MT5 no aparecen en el
  Diario; cuando lo hagan, la columna `manual` las separa por magic. Health,
  TCA y guardián sí ven esas operaciones (la equity real es la que es).

## No construir hasta

| Condición | Qué desbloquea |
|---|---|
| **Guardián 5/5** sesiones ALERT sin disparos (hoy 2/5; 2026-11-16) | Pasar a `CLOSE` con `scripts\guardian_enable_close.ps1` y `defense: enforce` en el forward |
| **Forward US100 60 días** de demo (hoy no existe: `us100-trend-d1` está `enabled:false`) | Decidir si se intenta un challenge con esa exposición (k=0,75) |
| **Decisiones n ≥ 30** con retorno a 20 días (hoy 10, 0 con retorno) | Extraer lecciones automáticas y comparar modelos con muestra |
| **30 operaciones cerradas** (hoy 0 cerradas de bots; el diario reconstruye) | MFE/MAE por operación y replay del Time Machine sobre casos reales |

Mientras no se cumplan, no se añaden familias, no se sube exposición y no se
activa ningún bot: se mide y se espera.
