# COLA-tom-anclaje · comprobar el anclaje fecha NYSE → barra D1 en month_turn
Modelo: DeepSeek V4.1 Flash. BLOQUE COMÚN + AGENTS.md. Sesión NUEVA y única en E:\trading-lab (HEAD 4d6f2c0 o posterior).
PROHIBIDO: register/approve/run/confirm/supersede, OOS, calcular rendimiento de nada (solo fechas de señales y entradas/salidas), push, tareas programadas, borrar, umbrales, protegidos.

## Sospecha (de HIPOTESIS-4-10.md)
La barra D1 se etiqueta por su apertura a las 17:00 NY y cubre la sesión del día SIGUIENTE. `month_turn` mapearía por etiqueta y su test comprueba la etiqueta, no la sesión. Si es así, la entrada y la salida del cambio de mes estarían desplazadas un día.

## Tareas
1. Con datos reales D1 de US500 (Dukascopy) de enero a marzo de 2023 y 2024, lista para cada fin de mes: fecha NYSE del último día hábil, la barra D1 donde se genera la señal (etiqueta UTC y NY y sesión que cubre), hora/fecha de entrada, día hábil M del mes siguiente y barra/fecha de salida. Usa N=1, M=2 y N=2, M=4. Solo fechas: NO calcules precios de resultado, R ni nada de rendimiento.
2. Responde: ¿entra al CIERRE de la sesión NYSE del día hábil N antes de fin de mes y sale al CIERRE de la sesión del día hábil M? ¿O hay desfase de un día? Explica con archivo:línea.
3. Si hay desfase: corrige el mapeo por SESIÓN (no por etiqueta), con tests que comprueben la sesión NYSE real (incluidos fin de mes en fin de semana y festivo). Las specs r9-tom-* NO se modifican (mismos parámetros); si ya hubiera campañas r9-tom registradas/ejecutadas con el código viejo, NO las toques: lista su estado y deja escrito que hace falta `supersede` (lo decide y ejecuta el operador) y re-registro.
4. Comprueba lo mismo para d1_extension_reversion (q1-rebote) solo si usa calendario; si no usa calendario, dilo.
5. ruff, pytest -q, propfund verify (4 OK), count_tests. Commit "tl2: month_turn - anclaje por sesión" si hubo cambio, tag tl2-tom-anclaje. RESULTADO-tom-anclaje.md y PARA.
