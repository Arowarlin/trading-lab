# PARALELO · hipótesis 4-10 del PLAN-BUSQUEDA en papel (SOLO DOCUMENTO)
Modelo: DeepSeek V4.1 Flash. BLOQUE COMÚN (docs/tradinglab2/10) + AGENTS.md.
Otra sesión (R9c) trabaja en E:\trading-lab. TÚ NO TOCAS CÓDIGO, CONFIG, DATOS NI GIT. Solo LEES el repo y escribes UN archivo: E:\trading-lab\.orquestador\HIPOTESIS-4-10.md (más, opcionalmente, E:\trading-lab\.orquestador\fomc-fechas.md).
PROHIBIDO: ejecutar backtests, calcular expectativa/PF/percentiles o cualquier rendimiento (aunque sea "rápido" o "informativo"), preflight/feasibility (no son necesarios aquí), register/approve/run, OOS, editar archivos del repo, commits, push.

## Para cada hipótesis 4-10 de .orquestador/PLAN-BUSQUEDA.md
1. Hipótesis literal (2-3 frases: qué efecto, por qué existiría, qué debe superar) y referencia(s) académica(s) o de práctica. Si una referencia no la puedes verificar, márcala "por verificar"; no inventes.
2. Reglas exactas: entrada, salida, lado (¿simétrica?), stop de catástrofe fijo (no optimizado) y por qué.
3. Parámetros: máximo 2-3, con 2-3 valores cada uno, razonados ANTES de ver datos; n_total resultante (≤ 27).
4. Datos: símbolo(s), TF, fuente (Dukascopy/Databento), rango IS dentro de usable_from (consulta config/discovery/engine.yaml: data_quality.usable_from); qué falta (p. ej. fechas FOMC, calendario).
5. Operaciones IS esperadas por año, estimadas SOLO por reglas/calendario (p. ej. "8 reuniones FOMC/año"), nunca contando señales sobre los datos.
6. Bloques DSL/plantillas existentes que sirven (lee config/discovery/templates y src/tradinglab/discovery/blocks.py) y qué faltaría construir (lo mínimo).
7. Coste esperado: si mantiene posiciones de un día para otro (swap) y cuántas noches.
8. Riesgo principal (deriva del mercado, pocas operaciones, solape con otra hipótesis o con carriles demo).

## Extra (opcional)
Fechas de anuncios del FOMC 2010-2026 con hora, SOLO si puedes leerlas de la web oficial (federalreserve.gov, calendario/historial de reuniones). Lista en fomc-fechas.md con la URL de origen. Si no puedes acceder a la web, escribe "Sin datos" y no las reconstruyas de memoria.

Al final: tabla resumen (hipótesis, símbolo·TF, n_total, ops/año, qué falta, riesgo) y PARA.
