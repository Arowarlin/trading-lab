# COLA-carriles · arreglos AUTORIZADOS en los carriles demo (EA, forward FTMO, us100-trend-d1)
Modelo: DeepSeek V4.1 Flash. BLOQUE COMÚN + AGENTS.md. Repo E:\trading-lab, rama feature/prop-fund-multifirm. Sesión única en E: (si otra sesión está en E:, espera a que termine).
Base: RESULTADO-DIAG-carriles.md (léelo entero antes de empezar).

## AUTORIZACIÓN DEL OPERADOR (2026-11-23 ~11:35, literal de sus respuestas)
- EA: "Instalar la v3.2". → Tú NO instalas nada en MT5: preparas archivos e instrucciones; el operador instala.
- Max trades forward: "1 por bot, 2 por cuenta".
- Archivos protegidos: "Sí, los dos": (a) frescura por edad de la última vela, (b) us100-trend-d1 de 04:00 a 06:00 UTC.
- DSR: "Mantener 1730".
Esta autorización cubre SOLO estos cambios. Cualquier otro cambio en protegidos, tareas programadas o setfiles: PARA y pregunta.
PROHIBIDO: operar, enviar/cerrar órdenes, instalar/compilar/adjuntar EAs, modificar o registrar tareas programadas (si un cambio lo exige, deja el comando al operador), campañas, OOS, push, borrar, umbrales de discovery.

## Tareas
1. Forward FTMO max-trades (forward_intraday.py:1334-1441 según el diagnóstico): separar límite por bot (1) y por cuenta (2) para los carriles forward:%. Tests: USDJPY entra → EURUSD aún puede entrar ese día; un tercer forward ese día → bloqueado por cuenta; el mismo bot no entra 2 veces.
2. Frescura (freshness.py, execution/mt5.py, forward_intraday.py): bloquear por edad de last_bar_utc de la fuente/cuenta usada, no por la hora de la última descarga. Tests con el caso 11-13 (descarga vieja pero vela reciente → no bloquea; vela vieja → bloquea).
3. us100-trend-d1: la ejecución pasa de 04:00-04:04 a 06:00-06:04 UTC (scripts/intraday_forward_execute.ps1:38 y donde viva la ventana). Test de _bar_in_entry_window con velas H4 del bróker alineadas a 02:00 (invierno) y a 01:00 (verano, DST): a las 06:02 UTC debe haber vela cerrada dentro de la ventana en ambos casos. Si la tarea programada tiene su propia hora fija, NO la toques: deja el comando exacto para el operador.
4. Trazabilidad: INICIO/FIN + run_id en cada pasada de intraday_forward_execute (no protegido o dentro de la autorización si el script es protegido; si dudas, pregunta).
5. Re-sellado de protegidos: usa el procedimiento existente del manifiesto para registrar los nuevos hashes CON referencia a esta autorización (fecha, texto literal). Si el procedimiento exige un comando del operador, NO lo simules: déjalo escrito. `lab propfund verify` debe terminar 4 OK.
6. EA v3.2 (solo preparación): en .orquestador\EA-v32-instalar.md: rutas exactas del .mq5/.mqh/.set v3.2 en el repo, su sha256 (deben coincidir con criteria_preview: setfile 3f2b0fc5…, code 5f8f0751…), dónde copiarlos en el terminal FTMO (ruta MQL5 real, leída en solo lectura), pasos MetaEditor (compilar), adjuntar a US100.cash en M5 con el setfile v3.2, magics 93010001/93020001, y un comando de verificación posterior (attach-only) que compruebe versión/hashes y el gráfico M5. Indica que el forward del EA reinicia el reloj en la fecha de instalación y cómo quedará registrado.
7. R7b: corrige en su rama tl2-r7b que count_tests use la DB de discovery de E: (o falle si falta, nunca 0 silencioso). Test. Commit en tl2-r7b; NO merge.
8. ruff, pytest -q (una vez), propfund verify (4 OK), count_tests 1730. Commit "tl2: carriles - max-trades, frescura, horario us100 (autorizado 2026-11-23)", tag tl2-carriles-fix. RESULTADO-carriles.md con lo cambiado (archivo:línea), los nuevos hashes, comandos pendientes del operador, y PARA.
