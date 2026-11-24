# COLA-NOCHE · trabajo desatendido (operador durmiendo)
Modelo: DeepSeek V4.1 Flash. BLOQUE COMÚN (docs/tradinglab2/10) + AGENTS.md. Repo E:\trading-lab, rama feature/prop-fund-multifirm.
Se ejecuta DESPUÉS de C1-informe, en la MISMA sesión, en orden N1 → N2 → N3. Antes de pasar a la siguiente: su RESULTADO escrito y commit+tag si cambió el repo.
Si CUALQUIER check falla (pytest, ruff, propfund verify 4 OK, count_tests != 1703) o algo exige decisión humana: escribe el RESULTADO con el problema y PARA TODO.
PROHIBIDO: register, approve, run, confirm, supersede, leer OOS-1/OOS-2, push, tareas programadas, borrar, copiar el repo, tocar .venv, archivos protegidos (propfund verify), carril del EA, umbrales, y tocar el worktree tl2-f12. Ningún backtest que muestre rendimiento (expectativa, PF, equity): solo preflight/feasibility (operaciones y coste). pytest -q completo solo al cerrar cada tarea.

## N1 · FundingPips CFD-006 = 2-Step Standard (dato del operador)
Reglas públicas (fuentes de terceros; el operador las verificará en su panel):
- Fase 1 objetivo 8 %, fase 2 objetivo 5 %, mínimo 3 días de trading por fase.
- Pérdida diaria máx 5 %, medida desde el MAYOR de balance o equidad al inicio del día; cuenta flotante + cerrado; reinicio diario a medianoche del servidor.
- Pérdida máxima 10 % ESTÁTICA (desde el balance inicial).
- Comisión 5 USD por lote ida y vuelta en forex y metales; índices y energía 0.
- Cuenta fondeada: riesgo máx por idea de trade 3 % (<50K) / 2 % (>=50K).
Tarea: compara con la configuración de firma/cuenta de CFD-006 y con cómo el overlay de firma y el MC prop calculan la pérdida diaria. Tabla regla | configurado | público | ¿coincide?. Si el archivo NO es protegido, corrige lo que no coincida con tests; si es protegido, NO lo toques y lístalo. Si cambió algo, recalcula onboarding-mtf de CFD-006 y muestra qué celdas cambian. Commit "tl2: N1 - reglas FundingPips 2-Step Standard", tag tl2-n1. RESULTADO-N1.md.

## N2 · Plantillas H4/D1 (de PROPUESTAS-plantillas-H4D1.md de C1-informe)
- Implementa las 3 plantillas propuestas, cada una con valid_timeframes H4/D1, symmetric declarado, bloques DSL nuevos si hacen falta (con tests de paridad fastbt/backtest y test de sesgo de anticipación como los existentes), máx. 3 parámetros.
- Para cada plantilla, 1-2 specs en .orquestador\specs\ (historia larga dentro de usable_from, grid 24-48 combinaciones, hipótesis escrita en el spec) SOLO sobre símbolo×TF viables en el cribado. NO registres.
- preflight --spec y feasibility --spec de cada spec; pega salida (válidos, factibles %, operaciones IS por combinación, cost_R operaciones).
- No toques la incubación us100-trend-d1 del carril FTMO; si una plantilla se le parece, dilo.
- Commit "tl2: N2 - plantillas H4/D1", tag tl2-n2. RESULTADO-N2.md.

## N3 · Propuestas para la mañana (solo papel)
.orquestador\PROPUESTAS-manana.md: tabla de los specs de N2 que pasan preflight 100 % y feasibility >= 50 %, ordenados por operaciones IS (más es mejor) y coste (menos es mejor), con n_total, cuentas viables y contador DSR si se aprueba cada uno (base 1703). Recomienda UNA para empezar y por qué (sin mirar rendimiento). Comandos exactos register/approve/run para el operador.

Al terminar: "COLA-NOCHE TERMINADA" o "COLA-NOCHE PARADA EN Nx: motivo" en .orquestador\RESULTADO-cola-noche.md y PARA.
