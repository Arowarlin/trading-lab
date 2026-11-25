# TL3 · Resumen ejecutivo

**Fecha:** 2026-11-25 · **Modo:** solo lectura (copias de las bases de datos; sin backtests, campañas ni
cambios de código o configuración; `count_tests` sin cambios). Detalle y evidencia en los otros nueve
documentos de `TL3_REPORTS/`.

## Diagnóstico en cinco frases

1. **TradingLab no lleva mucho tiempo buscando ventaja: lleva 21 días, y casi todos fueron de
   infraestructura** (433 commits, ~114.000 líneas). Discovery existe desde hace 5 días y ha ejecutado
   18 campañas que se reducen a unas 6 ideas.
2. **11 de 16 campañas no podían detectar el efecto que buscaban** (MDE de 0,09 a 0,62 R frente a
   efectos plausibles de 0,02 a 0,10 R). Su "0 finalistas" no es evidencia de nada.
3. **La única familia probada con potencia, el fix de divisas, está cerrada de verdad:** con 7.527
   operaciones y costes v2, el bruto (+0,019 R) no cubre el coste (0,032 R).
4. **El único activo con señal, el EA `us100-ftmo1`, no tiene ninguna prueba fuera de muestra
   válida.** Su +0,31 R es la muestra de diseño (2021-09 → 2026-11, la mejor de 8 variantes, unos
   70 parámetros); no transfiere a US500/US30; y la prueba NQ en curso está mal especificada.
5. **`ai_trader` no ha demostrado nada:** su ventaja frente a la gemela es, sobre todo, un artefacto
   de medición (+0,28 R de diferencia cuando ambas toman **el mismo lado con los mismos niveles**) y
   un sesgo corto durante una caída del 10 %.

**¿Existe hoy una ventaja demostrada? No.** Hay un candidato (el EA) con evidencia fuerte en muestra
y una prueba fuera de periodo gratuita pendiente que puede confirmarlo o descartarlo.

## Aviso urgente

**NQ-B se está ejecutando ahora** (OpenCode, `download_nq.py`). Su puerta de validez compara NQ 2018
con la caché US100 del EA en 2018, **que es D1, no M5**. Fallará y devolverá "Sin datos", o reescalará
los parámetros con un ATR diario. El operador debe decidir la enmienda **antes** de que se ejecute B2
y sin mirar 2010-2017. Además, los datos NQ se están guardando como `US100_M1.parquet`.

## Las diez decisiones más importantes

| # | Decisión | Evidencia clave | Documento |
|---|---|---|---|
| 1 | **Parar o enmendar NQ-B antes de B2.** Validar contra el primer tramo M5 común (2021-10 → 2022-09) o contra Dukascopy 2018; decidirlo por escrito antes de ver NQ 2010-2017 | Caché EA 2018 = D1 (258 velas) | FORENSIC G-1 |
| 2 | **Prueba fuera de periodo del EA con Dukascopy US100 2011-2021** (gratis, en disco, mismo tipo de instrumento), prerregistrada como E2. Es la prueba que separa "ventaja de US100" de "ajuste a 2021-2026" | 478 ops en muestra de diseño; no transfiere a US500/US30 | US100 §6 |
| 3 | **No subir el riesgo del EA a 0,65 %** por el Monte Carlo de P(pasar): remuestrea la muestra de diseño | `us100-ftmo1-v2.md §8` | US100 §7 |
| 4 | **Puerta de potencia obligatoria:** sin `plausible_edge_r` y `sigma_r` no se registra; MDE > δ → rechazo | 0 de 18 campañas declararon δ | STATS S1 |
| 5 | **Reetiquetar** cambio de mes y rebote como "no concluyente (costes v1, sin potencia)", no "cerrada"; mantener cerrado el fix | 17/18 campañas con costes v1; MDE 0,24–0,62 | DISCOVERY §3 |
| 6 | **Holdouts fuera de periodo o fuera de instrumento**; dejar de usar 2025-07+ de US100 M5 para hipótesis de apertura NY (contaminado por el diseño del EA) | OOS-2 común; EA ajustado hasta 2026-11 | STATS §C |
| 7 | **Separar futuros de CFD en los datos:** nombres propios, contrato por fila y roll explícito (GC vence en meses pares; el detector solo mira mar/jun/sep/dic). No investigar NQ/MNQ hasta tenerlo | `ROOT_TO_INTERNAL`; 17 de ~66 rolls de NQ detectados | DATA §3 |
| 8 | **Congelar el GA/NSGA-II, `export_mql5` y los carriles de acciones;** investigar con hipótesis económicas de pocos parámetros, priorizando las que no tienen parámetros libres (muestra completa como prueba única) | GA: 2 finalistas sobreajustados; barridos: ~450 fallidos | METHODOLOGY §3 |
| 9 | **Congelar conclusiones sobre `ai_trader`** hasta tener una gemela correcta y una regla de tendencia como benchmark | Mismo lado: IA +0,007 R vs gemela −0,271 R | AI_TRADER §2 |
| 10 | **Registro de hipótesis TL3 aparte** (identidad estructural, libro de muestras, umbrales con hash que la IA no puede tocar), reutilizando Discovery por API | Contaminación 2026-11-B declarada a mano; DSR global heterogéneo | ARCHITECTURE |

## Qué sí funciona (no tocar)

Guard y holdout sellado (0 lecturas de OOS-2), snapshots con hash, registro de miradas informales,
arnés T01 (el pipeline no fabrica falsos positivos), protocolo v2 y SPRT. El problema no es que el
sistema apruebe basura, sino que **casi nunca se le ha dado una pregunta que pudiera contestar**.

## Correcciones recomendadas e impacto

| Corrección | Impacto esperado | Esfuerzo |
|---|---|---|
| Enmienda NQ-B (decisión, no código) | Evita una prueba pagada y nula, y una reinterpretación post hoc | Minutos |
| EA fuera de periodo (Dukascopy) | Primera evidencia independiente sobre el único candidato | 1–2 días |
| Puerta de potencia + coste obligatorias | Elimina ~70 % de las campañas que no informan | 1 día |
| Manifiesto de datos y separación CFD/futuros | Elimina una clase entera de errores silenciosos | 1–2 días |
| Registro de hipótesis TL3 | Menos experimentos redundantes; historia científica reproducible | 3–4 días |
| H1/H2 sin parámetros libres | Respuestas decisivas con 1 prueba cada una | 1 día cada una |

## Limitaciones de esta auditoría

- No ejecuté el motor del EA ni ningún backtest: MAE/MFE, horario de entrada, largo/corto por año y
  bruto sin spread del EA quedan **Sin datos**.
- No verifiqué los cálculos internos de PBO ni de SPA línea a línea; me apoyo en los informes TL2 y en
  el arnés.
- Prop Fund y el riesgo FTMO solo se revisaron en lo que afecta a la investigación.
- Las cifras de potencia usan σ = 1 R salvo en el EA (σ = 1,92 R); para estrategias con RR ≥ 2 son
  optimistas.
