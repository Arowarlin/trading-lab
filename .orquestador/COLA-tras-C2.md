# COLA-tras-C2 · nueva cuenta FundingPips Trial (CFD-006) y reglas confirmadas en el panel
Modelo: DeepSeek V4.1 Flash. Misma sesión que C2-informe, DESPUÉS de cerrar C2. BLOQUE COMÚN + AGENTS.md.
PROHIBIDO: operar, campañas, OOS, push, tareas programadas (ni modificarlas), borrar, archivos protegidos, carril del EA. NUNCA pidas, leas, guardes ni escribas contraseñas: TradingLab es attach-only.

## Datos del operador (panel FundingPips, 2026-11-23)
- La cuenta anterior 40000453530 desapareció del panel. Cuenta nueva: login 40000459328, servidor FundingPips-Trial, MetaTrader 5 (mismo terminal que usaba CFD-006).
- Tamaño 100.000 USD. Pérdida diaria máx 5.000 (panel: "Todays Starting Equity 100,000 · Balance Threshold 95,000"). Pérdida máxima 10.000 estática (umbral 90.000). Objetivo 8.000. Mínimo 3 días de trading.
- NUEVO: duración máxima del reto 14 días; fin 2026-12-07.
- Reinicio diario: el panel marcaba "Resets in 08:04:39" a las 09:57 hora de Santo Domingo (UTC-4) → reinicio ≈ 22:00 UTC = 17:00 Nueva York (= 00:00 UTC+2 en invierno). Comprueba que coincide con el reset configurado (Etc/GMT-2) y documenta el verano (DST).

## Tareas
1. CFD-006 en config/propfund/accounts.yaml (y donde se referencie el login, p. ej. la medición de spreads): login 40000453530 → 40000459328; nota "cuenta anterior retirada del panel 2026-11-23". Estado de las reglas: de `needs_verification` a `verified_operator_panel_2026-11-23` para las que coinciden con el panel; añade la regla de duración máxima 14 días (fin 2026-12-07) como regla del programa Trial.
2. Verificación attach-only: si el terminal FundingPips está abierto y logueado en 40000459328, comprueba login y servidor (antes y después), símbolos NDX100/SPX500/DJI30/XAUUSD/EURUSD/GBPUSD/USDJPY visibles y especificaciones (contract size, tick, comisión si la expone). Si NO está logueado en esa cuenta: no hagas nada en MT5, escribe "pendiente: el operador debe iniciar sesión" y sigue.
3. Si la tarea programada de spreads usa el login viejo, NO la modifiques: escribe en el RESULTADO qué archivo/config cambiar y el comando exacto para que el operador lo haga.
4. Tests (cuenta y reglas), ruff, pytest -q, propfund verify (4 OK), count_tests 1730. Commit "tl2: CFD-006 nueva cuenta trial y reglas verificadas", tag tl2-cfd006-v2. RESULTADO-CFD006.md y PARA.
