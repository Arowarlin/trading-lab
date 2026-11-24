# 15 · Arnés de autoevaluación del pipeline (T01)

Mide dos cosas que antes eran opinión: la probabilidad de aprobar del pipeline
y si el motor de ejecución recupera una ventaja conocida.

## Uso

```powershell
lab discovery harness --mode gates --freq 12,50,250,1000 `
  --edge 0,0.05,0.1,0.2 --sims 2000 --seed 7

lab discovery harness --mode bars --edge 0,0.05,0.1,0.2 `
  --sims 2000 --seed 7 --output reports/discovery/harness-bars.md
```

- **No escribe en `discovery.db` ni toca el contador.** Todo corre en memoria.
- El informe por defecto es `reports/discovery/harness-current.md`.

## Modo `gates`

Genera flujos de R por operación para IS, OOS-1 y OOS-2 con el número de
operaciones de `freq` × duración de cada tramo por defecto de `engine.yaml`
(IS 2,75 años, OOS-1 1 año, OOS-2 hasta hoy). Dos distribuciones: normal con
media `δ` y desviación 1, y t de Student con 4 grados de libertad escalada a
desviación 1.

Aplica las reglas puras de `discovery/decisions.py`, extraídas de
`engine._rank1_candidates`, `engine._select_finalists` y `levels.evaluate`:

- deriva (`percentil ≥ 90`, aproximada con `Φ(media_IS·√n)` frente a entradas
  nulas);
- IS completa > 0;
- pliegues positivos ≥ `folds − 1`;
- OOS-1: expectativa > 0 y PF > 1,1 (finalista);
- OOS-2: n ≥ 30, media > 0 y z ≥ 1,645 (equivalente a percentil aleatorio ≥ 95).

Las puertas que no se pueden simular con flujos de R —PBO, WF, régimen,
perturbaciones, coste x1,5, challenge, DSR de confirmación— se marcan como
aprobadas. Por eso la probabilidad es una **cota superior optimista**.

Salida: tabla P(aprobar) = P(nivel 4) con intervalo de Wilson al 95 % y
P(nivel 3) por frecuencia, ventaja y distribución.

## Modo `bars`

Construye barras BID sintéticas con un spread conocido y una señal larga que
inyecta una ventaja `δ` exacta sobre el riesgo de la operación. Pasa las
operaciones por `fastbt` v2 y `CostBook` (versión 2). El resultado debe
recuperar `δ − coste` dentro del intervalo de confianza al 95 %.

Esto valida también T10: si el motor cobrara dos spreads, el intervalo no
contendría `δ − coste`.

## Aceptación (2026-11-24, semilla 7, 2.000 simulaciones)

- Nulo (`δ = 0`): P(aprobar) < 0,05 en todas las frecuencias. Obtenido:
  0,000 (12), 0,000–0,001 (50), 0,001–0,002 (250), 0,000 (1000).
- Órdenes de magnitud frente a `evidencia/potencia_validacion.salida.txt`:
  coinciden en 250 y 1000 operaciones/año. En 50 son algo menores porque el
  arnés añade IS, pliegues y deriva, que la evidencia original ignoraba.
- `bars`: recupera `δ − coste` en 0, 0,05, 0,1 y 0,2 R
  (`reports/discovery/harness-bars.md`).

## Límites conocidos

- La deriva se aproxima con la normal; no reproduce el bootstrap de entradas
  aleatorias del control real.
- DSR, PBO, WF, régimen, perturbaciones y challenge no se simulan.
- El modo `gates` no sustituye a una campaña: mide el pipeline, no una
  hipótesis.
