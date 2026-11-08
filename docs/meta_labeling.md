# Meta-labeling y triple barrera (solo requisitos)

No se implementa en código todavía. Este documento fija los requisitos mínimos
antes de añadirlo a `models.py` o a un bot.

## Triple barrera

Para cada evento (señal primaria) se definen tres barreras:

- **Superior**: precio de beneficio (p. ej. `entry + k_up · ATR`).
- **Inferior**: precio de stop (p. ej. `entry - k_down · ATR`).
- **Tiempo**: número máximo de barras (`max_hold`).

La etiqueta es `+1` si toca la superior primero, `-1` si toca la inferior y `0`
si vence el tiempo. Se usa high/low de barras posteriores **solo para etiquetar**
el evento; la señal primaria debe haberse generado sin mirar el futuro. Si una
barra toca ambas barreras, se aplica una regla explícita y conservadora
(primero la inferior).

## Meta-labeling

- La señal primaria decide el lado; el meta-modelo estima la probabilidad de que
  esa señal tenga éxito.
- Las predicciones del meta-modelo deben ser **out-of-fold**; nunca se entrena
  con la misma observación que luego se evalúa.
- Validación con Purged K-Fold/CPCV y `embargo >= horizonte de la etiqueta`.
- La etiqueta de éxito/fracaso no puede filtrarse a las features.

## Muestra mínima

- **≥500 eventos etiquetados** para el primer estudio.
- **≥100 eventos por clase** (`éxito`/`fracaso`) para meta-labeling.
- Si no se cumple: **Sin datos**; no se implementa ni se propone.
- El tramo final sellado de research no se usa para entrenar ni ajustar.

## Datos necesarios

Barras intradía y, cuando aplique, bid/ask/mid/spread y horario de sesión. Si el
activo no tiene esos datos, el estudio queda bloqueado; no se inventan barras ni
spreads. F13 no depende de esta etapa.

## Estado

- Documento: **sí**.
- Implementación: **no**.
- Motivo: muestra y datos insuficientes; se reevalúa cuando existan ≥500 eventos
  etiquetados y validación purgada disponible.

## Referencias internas

- `models.py`: `PurgedKFold`, `CombinatorialPurgedCV`, `train_purged_cv`.
- `validation.py`: CSCV/PBO.
- `docs/datacheck.md`: calidad de la caché.
