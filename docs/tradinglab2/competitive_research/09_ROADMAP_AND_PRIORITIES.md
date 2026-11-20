# 09 · Roadmap y prioridades

Supuestos de tiempo: una sesión de OpenCode (DeepSeek V4.1 Flash) por fase, con revisión del operador; los
tiempos son orientativos (horas de trabajo efectivo), no compromisos.

| Fase | Contenido | Prioridad | Beneficio | Coste | Riesgo estadístico | Tiempo |
|---|---|---|---|---|---|---|
| **R0 = 7c + 7d** | Commit/push de 7c; regímenes alcanzables; simetría; reintento de hijos; serie diaria del EA | **P0** | Sin esto el nivel 4 es inalcanzable y se desperdicia 45 % del presupuesto | Bajo | Ninguno (corrige) | 3–5 h |
| **R1 · Perturbation Lab** | Noise Test, entradas/salidas retrasadas, MC de ejecución; requisito de nivel 3 | **P1** | Refuta más estrategias falsas **antes** de gastar OOS-2 | Medio | Bajo (no suma al DSR; IS+OOS-1) | 5–8 h |
| **R2 · Datos 1c** | M5 de los demás CFD con attach-only | **P1** | Buscar donde el coste relativo es menor (oro, otras sesiones) | Bajo-medio | Ninguno | 3–4 h |
| R3 · Databank v2 | Colecciones, etiquetas, familias, clones entre campañas, perfil de aceptación con hash | P1 | Orden y reutilización; evita repetir hipótesis | Medio | Ninguno | 4–6 h |
| R4 · Consola (Fase 8) | Evolución, databank, detalle, robustez, presupuesto, mapas de calor, veredicto | P1 | Comprensión rápida | Medio-alto | Ninguno | 8–12 h |
| R5 · Generador v2 | Bloques causales (sweeps, rangos, día previo, calendario), `locked`, multi-mercado k-de-n | P2 | Más diversidad con sentido | Medio | Medio (más pruebas; se cuentan) | 6–10 h |
| R6 · Futuros (Fase 10) | Databento, continuo, costes por contrato | P2 | Mercado con coste bajo y datos limpios | Medio | Ninguno | 6–8 h |
| R7 · Cartera y fondeo (Fase 11) | Matriz estrategia × cuenta, correlación, contraste con simulador abierto | P2 | Pasar challenges, no solo backtests | Medio | Bajo | 6–8 h |
| R8 · IA (Fase 9) | Hipótesis → AST validado | P2 | Ideas nuevas con causa | Medio | Medio (control por campaña) | 5–8 h |
| R9 · Export MQL5 (Fase 12) | Plantillas, determinismo, CSV de señales | P2 | Llevar a MT5 | Medio | Ninguno | 6–10 h |
| R10 | Editor visual, MCP de solo lectura, Reality Check/SPA | P3 | Comodidad / rigor adicional | Alto | — | — |

**Orden recomendado:** R0 → R1 → R2 → (campañas nuevas en otros mercados) → R3 → R4 → R6 → R7 → R5 → R8 → R9.

Razonamiento: primero que el laboratorio **pueda reconocer** un edge real (R0), después que **refute antes**
las falsas (R1), después que **busque donde hay más probabilidad** de encontrarlo (R2). La consola y la
organización vienen cuando haya algo que organizar.
