# Investigación competitiva · resumen ejecutivo

Build Alpha, Adaptrade Builder, Forex Strategy Builder y Expert Advisor Studio frente a TradingLab 2.0
(auditado en tl2-f7b, 2026-11-20). Documentos 01–12 en esta carpeta.

## Respuestas

1. **Qué hace mejor cada una:** Build Alpha → pruebas de perturbación y multi-mercado; Adaptrade →
   programación genética con objetivos y condiciones separados y planteamiento estadístico; FSB Pro →
   colecciones y criterios de aceptación reutilizables; EA Studio → cadena generar-validar-coleccionar y
   Monte Carlo de mercado y ejecución.
2. **Qué adoptar:** Noise Test, entradas/salidas retrasadas, MC de ejecución, colecciones/familias, perfiles
   de aceptación con hash, multi-mercado k-de-n pre-registrado, bloqueo de partes de plantilla.
3. **Qué tenemos ya:** generación GA multiobjetivo, paridad exacta, campañas con presupuesto, DSR global,
   PBO, WF, OOS-2 sellado, test contra azar en OOS-2, niveles deterministas, MC de challenge por cuenta.
4. **Qué falta de verdad:** gate de regímenes alcanzable (bug), simetría, pruebas de perturbación, datos
   de otros CFD y futuros, consola, colecciones, exportación.
5. **Mejorar la calidad del edge:** pruebas de perturbación antes de gastar OOS-2 y buscar en mercados con
   menor coste relativo.
6. **Reducir tiempo:** reintento de hijos (45 % del presupuesto perdido), pipeline encadenado, consola.
7. **Diversidad:** familias con causa (sweeps, rangos de sesión, día previo, calendario), clones entre
   campañas, varias plantillas por campaña.
8. **Evitar reglas absurdas:** simetría, validación semántica de dirección, plantillas con nodos bloqueados.
9. **Validación estadística:** mantener todo lo actual; añadir perturbaciones (no suman al DSR) e investigar
   Reality Check/SPA.
10. **Carteras:** correlación diaria real + exposición por subyacente (ya existe en propfund) + matriz por
    cuenta (Fase 11).
11. **Fuera de los patrones técnicos:** calendario/eventos, relaciones intermercado, sesiones; microestructura
    no es viable en CFD sin order book.
12. **Primero:** R0 (7c + 7d) → R1 Perturbation Lab → R2 datos de otros CFD.
13. **Nunca:** OOS usado para reconstruir o elegir, redes neuronales como condición, criterios copiados de
    estrategias vistas, optimizar fuera de una campaña registrada, lógica adaptativa en vivo, proyecciones
    del futuro.
14. **Evolución:** primero que el laboratorio pueda reconocer un edge (R0), después que refute antes lo falso
    (R1) y que busque donde es más probable (R2); organización y consola cuando haya material.

**Recomendación ejecutiva:** no comprar ninguna plataforma. Adoptar sus pruebas de perturbación y su
organización dentro de nuestra arquitectura, que ya es más estricta estadísticamente que las cuatro.
Ninguna de estas mejoras garantiza encontrar estrategias rentables; mejoran la probabilidad de no
engañarnos.
