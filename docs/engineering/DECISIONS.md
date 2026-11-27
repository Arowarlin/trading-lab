# DECISIONS · Programa ENG-1

| Fecha | Decisión | Motivo | Quién |
|---|---|---|---|
| 2026-11-26 | `docs/engineering/` es la carpeta del programa; las colas de `.orquestador/` no se editan | No mezclar un programa de auditoría con las colas operativas en marcha | Claude |
| 2026-11-26 | Motor congelado (`fastbt.py`, `costs.py`, sesiones, métricas, `robustness.py`, `walkforward.py`, `engine.yaml`) | EDGE-2 Y2 en marcha (4/18) y WF-TF W3 pendiente | Claude, por la regla §2.3 del prompt |
| 2026-11-26 | El arreglo de `flat_at` no se duplica | Ya tiene cola propia: `COLA-MOTOR-FLAT.md` | Claude |
| 2026-11-26 | Las auditorías en la nube son de código y sintéticas; lo que necesite datos reales va a OpenCode en el equipo del operador | El contenedor no tiene datos ni `discovery.db` | Claude |
| 2026-11-26 | Sin `git push` desde la nube hasta que el operador lo autorice | `AGENTS.md`: "No `git push` … sin autorización" (prevalece sobre la instrucción de la sesión de empujar a la rama `claude/…`) | Claude |
| 2026-11-26 | Push autorizado **solo** a `claude/upbeat-pasteur-nz8e0u` para los commits de ENG-1; nunca a `master` | Autorización del operador en la sesión ("si autorizo el push") | Operador |
| 2026-11-26 | `ESTADO.md`, `README.md` y `PLAN.md` no se tocan desde la nube | El lock `readme-plan` está en el equipo del operador | Claude |
| 2026-11-26 | Integrar ENG-M1 (motor `discovery` 0.3.0: A-01/A-02, A-04, B-01, D-07) en `master` | Corrige 4 sesgos a favor de las estrategias; tests antes/después, paridad Numba y suite sin fallos nuevos (`M1_MOTOR.md`). Cambia resultados futuros, no los guardados | Operador: «tienes mi aprobacion» |
| 2026-11-26 | Corregir F0-09 (hash del forward del EA) con alias del hash antiguo; activar puertas v3 y `min_trades_oos1: 30`; abordar B-03, D-04, D-05, C-01, E-01, E-03, F0-06, menores, A-01 (entradas, como opción apagada), B-04, C-07, B-14 (producción, con procedimiento AGENTS.md) y C1 opción A (ASK real) | Respuestas del operador: «si a ambas preguntas», «tienes permiso para todo» y permiso en ajustes para editar `ea_forward.py`. **Ejecutar C1 (+1 al contador) se pedirá aparte** | Operador |
