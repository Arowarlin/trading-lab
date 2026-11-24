# COLA-F10c · validar los futuros Databento H1 recién descargados
Modelo: DeepSeek V4.1 Flash. BLOQUE COMÚN + AGENTS.md. Repo E:\trading-lab, rama feature/prop-fund-multifirm. Sesión única en E:.
Datos (descargados por el operador 2026-11-23, coste total ~6,78 USD): data\cache\databento\{US100,US500,US30,XAUUSD,EURUSD,GBPUSD,USDJPY}_H1.parquet, GLBX.MDP3 ohlcv-1h, roll por volumen (.v.0), 2010-06-06 → 2026-11-23.
PROHIBIDO: descargar nada más (ni M1 ni otros símbolos), campañas, OOS, push, tareas programadas, borrar, umbrales, protegidos, carril del EA. No modifiques los parquet originales: cualquier derivado va a archivos nuevos.

## Tareas
1. Integridad: por símbolo, filas, primera/última vela, duplicados, velas con OHLC incoherente, precios ≤ 0. Comprueba que USDJPY (6J invertido) está en escala ~80-160 y que high ≥ low tras invertir.
2. Rolls: lista de fechas de cambio de contrato por símbolo (desde los metadatos o detectando saltos de nivel), tamaño del salto en ATR. Decide y documenta: sin ajuste para análisis de retornos dentro del mismo contrato vs back-adjust para series continuas; NO elijas por resultado de ninguna estrategia.
3. Sesiones CME reales: `lab discovery derive-sessions SYMBOL --source databento` (moda semanal por año, regla del 60 %): pausa diaria 17:00-18:00 NY, cierre viernes, apertura domingo; tramos en engine.yaml data_quality.sessions con clave databento:SYMBOL (sin tocar las de dukascopy/broker).
4. `data-check --source databento --all-tf` (H1, H4, D1 resampleados con el alineamiento 17:00 NY) y `usable-from --source databento --write` para H1/H4/D1. Sin tocar umbrales.
5. Comparación Databento vs Dukascopy por símbolo en H1/H4/D1, en el periodo común: correlación de retornos (sin las velas de roll), desfase óptimo en horas, diferencia de nivel media y su evolución (basis futuro-CFD), % de velas presentes en una fuente y no en la otra. Tabla y conclusión: ¿sirve Databento como segunda fuente para confirmar una ventaja vista en Dukascopy? Marca cualquier símbolo dudoso.
6. Tests (fixtures pequeñas), ruff, pytest -q (una vez), propfund verify (4 OK), count_tests 1730. Commit "tl2: F10c - validación Databento H1", tag tl2-f10c. RESULTADO-F10c.md y PARA.
