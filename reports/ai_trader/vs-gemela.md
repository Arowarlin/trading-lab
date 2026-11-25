# ai_trader frente a su gemela aleatoria

Generado: 2026-11-24 · **solo lectura**, sin campañas ni órdenes.

## Muestra

- Tabla `ai_trades`: 46 propuestas; **42 con R de la IA y R de la gemela**.
- Periodo: 2026-11-13 14:46 → 2026-11-23 15:55 UTC.
- Gemela: `shadow_r` (misma entrada/stop/objetivo, lado aleatorio con semilla).

| Métrica | IA | Gemela | Diferencia (IA − gemela) |
|---|---:|---:|---:|
| n | 42 | 42 | 42 |
| R medio | +0,1135 | −0,2006 | **+0,3141** |
| sd de la diferencia | — | — | 1,3183 |

IC95 de la diferencia por bootstrap (10.000 remuestreos, semilla 7):
**[−0,0686; +0,7060]**. Incluye el 0.

## Coste del carril

| Concepto | Valor |
|---|---:|
| Llamadas LLM registradas | 115 |
| Tokens de prompt | 42.660 |
| Tokens de completion | 75.016 |
| Latencia mediana | 77,8 s |
| Latencia media | 481,2 s (un outlier de 11,4 h) |
| Llamadas correctas | 92 / 115 |
| Coste monetario | **Sin datos** (no hay precio por token registrado) |

## Veredicto

**No se distingue del azar.** La diferencia media es positiva (+0,314 R) pero
su IC95 incluye el 0 y n=42; no hay evidencia de que la IA aporte sobre su
gemela. El coste del carril (115 llamadas, ~78 s de mediana por llamada) no
está compensado por una ventaja demostrada.

No se toca `ai_trader`, ni su configuración, ni sus tareas.
