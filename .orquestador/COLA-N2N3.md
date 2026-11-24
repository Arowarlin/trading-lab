# COLA-N2N3 · cestas + informes (continuación de COLA-NOCHE2, que paró en N1)
Modelo: DeepSeek V4.1 Flash. BLOQUE COMÚN (docs/tradinglab2/10) + AGENTS.md. Sesión NUEVA y única en E:\trading-lab (HEAD con tag tl2-tom-anclaje; contador 1865 o 1883 si el operador ya registró r9b-tom).
N1 ya está hecho (anclaje corregido). NO toques supersede ni las campañas r9-tom / r9b-tom.
Ejecuta N2 → N3 en orden. Tras cada una: su sección en .orquestador\RESULTADO-n2n3.md y commit+tag. Si algo falla o exige decisión humana: escríbelo y PARA TODO.
PROHIBIDO: register/approve/run/confirm/supersede (los comandos quedan escritos para el operador), leer OOS-2, calcular rendimiento de specs NO aprobadas (guard de R9b), push, tareas programadas, borrar, umbrales, protegidos, carril del EA, operar, descargar. pytest -q completo una sola vez al final.
En N3, los informes r9-tom-* deben decir "ejecutadas con el anclaje D1 antiguo (desplazado); resultado no válido; sustituidas por r9b-tom" y no analizar su rendimiento.

## N2 · Cablear la ejecución de campañas de cesta (excepción mínima del PLAN-BUSQUEDA, hipótesis 3)
- register --spec / approve / run / results para specs con `basket:`: una campaña, n_total = combinaciones (18 para q3-tsmom-cesta-d1), evaluación por cesta (R agregado por fecha, coste y swap por símbolo/cuenta con swap_credit=false, pliegues globales, control de deriva por cesta con la misma mezcla de lados por símbolo, OOS-1 por cesta, OOS-2 sellado como siempre). Todo rendimiento pasa por guard.require_approved.
- Tests SOLO con datos sintéticos y DB temporal: cesta con ventaja conocida → pasa; sin ventaja → no; n_total no se multiplica por símbolos; guard impide rendimiento sin aprobar.
- NO registres ni ejecutes q3-tsmom-cesta-d1: deja los 4 comandos para el operador.
- Commit "tl2: N2 - run de cestas", tag tl2-noche2-n2.

## N3 · Informes cortos de las 7 campañas de hoy (solo lectura; IS y el OOS-1 que el pipeline ya leyó)
Un informe de UNA página por campaña en reports/discovery/: q2-fix-usdjpy-h1, q2-fix-eurusd-h1, q2-fix-gbpusd-h1, r9-tom-us500-d1, r9-tom-us100-d1, q1-rebote-us500-d1, q1-rebote-us100-d1. Cada uno: veredicto en una frase (sin edge bruto / edge bruto que el coste elimina / muestra insuficiente / pendiente de anclaje), tabla bruto vs coste vs neto, percentil de deriva, operaciones, pliegues. Para el fix de Londres añade: bruto por año 2010-2024 y por cuenta (FTMO vs FundingPips) y el coste que haría falta para que el neto fuese > 0 (en R y en pips), solo como información. Marca las 3 hipótesis como probadas en el Edge Map (suggest no las repropone). NO propongas variantes nuevas ni re-optimizaciones.
- Commit "tl2: N3 - informes campañas 23-nov", tag tl2-noche2-n3.

## Cierre
ruff, pytest -q (una vez), propfund verify (4 OK), count_tests (el que haya; no debe cambiar por ti). Al final de RESULTADO-n2n3.md: "N2N3 TERMINADA" o "PARADA EN Nx: motivo", y el bloque PowerShell con los comandos pendientes del operador (la cesta q3-tsmom-cesta-d1). PARA.
