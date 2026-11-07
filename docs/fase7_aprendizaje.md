# Fase 7 — Aprendizaje controlado (evaluación)

Fecha: 2026-11-07. **No se implementa todavía.**

## Lecciones

- Un job semanal revisará `decision_outcomes` y propondrá textos breves con
  evidencia en `lessons` con estado `proposed`.
- Solo las `approved` por el usuario se inyectan en prompts.
- El panel tendrá aprobar/rechazar; nada se aplica solo.

## Modelos pequeños

- LightGBM sobre features de precio, volatilidad, sentimiento y macro.
- Reentrenamiento walk-forward con ventana móvil.
- `model_registry`: versión, datos, métricas, hash y fecha.
- Campeón/retador: el nuevo corre en paper en paralelo; solo reemplaza al
  vigente si el usuario lo aprueba.
- Rollback a la versión anterior con un comando.

## Qlib / FinRL

- `pyqlib` **0.9.7** (PyPI, 2025-08-15), Python >=3.8. Si se usa, instalar en un
  venv aparte (`.venv-qlib`) para no romper `.venv`.
- FinRL/RL solo como experimento de investigación, nunca bot real: alto riesgo
  de sobreajuste y de comportamiento errático fuera de muestra.
- No se añaden dependencias en esta fase.

## Decisión

Esperar a tener F13 en marcha y una muestra de decisiones suficiente. El
aprendizaje automático no sustituye la validación walk-forward ni la aprobación
humana.
