# Fase 7 — Aprendizaje controlado

Fecha: 2026-11-07. **7.1/7.2 implementados; 7.3 parcial.**

## Modelos pequeños (7.2)

Implementado sin añadir dependencias: ridge determinista en numpy.

- Features: retornos 1/5/20, volatilidad 20, SMA20/50 y rango 20.
- Reentrenamiento walk-forward con ventanas móviles; train pasado, test posterior.
- `model_registry` guarda features, ventanas, métricas, coeficientes, hash,
  versión y estado; `model_registry_history` audita promociones/rollbacks.
- Todo modelo nace `challenger`; promover/rollback exige confirmación y **no
  activa bots ni cambia `enabled`**.
- `lab models train|list|show|promote|rollback|compare|qlib`.
- Qlib solo se comprueba en `.venv-qlib`; no se instala en `.venv`.
- Challenger SPY v1 registrado el 2026-11-07 sin promoción.

## Límites versionados (7.3)

- `account_limit_versions` con snapshot, hash y rollback confirmado.
- Con F13 congelado solo se permite rollback que apriete.
- `bot_capital_limits` + historial; el orquestador recorta el tamaño por el
  capital máximo del bot.

## Job semanal (7.1)

- `lab lessons weekly`: analiza `decision_outcomes` con n≥30.
- Qwen solo redacta la hipótesis; evidencia numérica aparte; estado `proposed`.
- Sin muestra/LLM: **Sin datos** y no crea lecciones.
- Aprobación humana exclusiva en el panel Aprendizaje.
- Script `scripts/lessons_weekly.ps1` listo pero no registrado.

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
