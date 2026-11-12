# Campañas de research

Una campaña es una rejilla de estrategias que se **registra una sola vez**, se
corre **una sola vez** y deja un holdout sellado. Nada de lo que produce se
activa: las confirmadas solo pueden entrar en el ciclo de vida como candidatas.

## Contrato

- **`N_total` antes de correr.** Se calcula con `lab campaign fetch` (celdas con
  historia suficiente bajo el corte común) y se escribe en
  `config/campaigns/<id>.yaml` antes de registrar. Al registrar, `count_tests`
  suma el `N_total` **completo**: el denominador del DSR no puede crecer
  mientras se miran resultados.
- **Corte común único.** Es el punto del 70 % de la serie **más corta**. La
  meseta entre activos solo usa datos anteriores a esa fecha; el 30 % final de
  cada serie queda sellado.
- **Holdout mínimo de dos años.** Si el corte común deja menos de dos años de
  holdout, no se acorta el holdout de todos: se saca del universo el activo
  cuya serie limita la ventana (la más corta o la que antes acaba), se
  recalcula el corte con las que quedan y se repite. Los excluidos se listan
  con su motivo en `reports/research/campaign/universe.md`. Si el universo se
  queda vacío o con menos de dos series, la respuesta es **Sin datos**.
- **Fetch sin círculo.** `lab campaign fetch` descarga H1/H4 con el máximo
  `CAMPAIGN_BARS` de **todos** los candidatos medidos, no solo de los ya
  elegibles; después vuelve a medir spread, ATR, datacheck y `cost_atr` con
  esas velas y solo entonces decide la elegibilidad. Solo descarga con mercado
  abierto (tick fresco) y offset del servidor confirmado.
- **Sello del holdout.** El yaml guarda el fin de cada serie sellada y
  `holdout_hash`. `run` recorta a ese fin y aborta si el hash cambió.
- **Una pasada.** `register` rechaza un segundo registro; `run` rechaza una
  segunda ejecución. Un run cortado por un fallo **de código** se reanuda con
  `--resume` (mismo `run_id`, sin reinsertar filas), nunca reiniciando.
- **Celdas con `counted = 0`.** Cada celda evaluada entra en `strategy_trials`
  con `counted = 0` para no contarse dos veces: su `N_total` ya está en
  `campaign_registry`.
- **Descubrimiento = celdas registradas.** `run_discovery` filtra por
  `eligible_by_timeframe`, `timeframes` y `applies_to`. Si corriera marcos que
  no entraron en `N_total` (p. ej. H1/H4 sin elegibles), el DSR quedaría
  desalineado. La condición de meseta y los clústeres de correlación se
  calculan **solo** con barras anteriores al corte.

## Comandos

```powershell
lab campaign universe        # mide coste y escribe universe.md/.json
lab campaign fetch           # H1/H4 máximos de todos, elegibilidad, corte ≥2 años, celdas y sello
lab campaign n-total         # N_total y celdas excluidas
lab campaign plan            # escribe el yaml, sin registrar
lab campaign register --confirm
lab campaign run --confirm   # una vez; --resume solo tras un fallo de código
lab campaign status
```

## 2026-11-A

### Plan reconstruido (2026-11-12, sin registrar)

- **Fetch sin círculo:** 51 candidatos con H1/H4 de 50.000 barras, mercado
  abierto y offset +2 h detectado; la elegibilidad se vuelve a medir con esas
  velas completas.
- **Elegibles:** **H1 0, H4 0, D1 16** (10 índices cash + 5 metales + NZDUSD).
  H1/H4 siguen fuera por coste (`cost_atr ≥ 0,05`), no por falta de datos.
- **Corte común:** `2024-08-08 00:00:00+00:00`, holdout común de **2,26 años**.
  `XCUUSD` queda fuera del universo por historia (507 barras D1, holdout de
  0,58 años); 0 celdas excluidas por historia y 48 series selladas.
- **`N_total = 232`** (H1 0 / H4 0 / D1 232), `config_hash = 0edeff2f…`,
  `holdout_hash = 768204bd…`. El yaml se reescribió con `lab campaign plan
  --force` y **no se registró**: la campaña sigue con el registro histórico de
  la primera pasada.
- **Decisión de id (2026-11-12):** este plan reconstruido se registrará como
  **`2026-11-B`**; `2026-11-A` queda como registro histórico y no se toca.
  Antes de registrar hay que fijar por escrito la regla de (c) (H4 no tiene
  elegibles) y generar el yaml con
  `lab campaign plan --campaign 2026-11-B --force`. **No se registra ahora.**

### Primera pasada registrada (histórica, 0 candidatas)

- **Universo por coste:** 55 activos medidos, 49 con comisión verificada, 28
  convertibles a bps. Elegibles: **H1 0, H4 0, D1 16** (9 índices cash + 6
  metales + cobre). Exóticos, cripto, acciones, agrícolas y materias primas
  quedan fuera con `Sin datos`.
- **Corte común:** `2026-04-14 00:00:00+00:00` (lo fija `XCUUSD D1`, la serie
  más corta). 47 series selladas, holdout D1 de 146–152 barras.
- **`N_total = 228`** (H1 0 / H4 0 / D1 228), 0 celdas excluidas por historia.
- `config_hash = 8e715fb1…`, `holdout_hash = 2ecf219c…`.
- **Run:** `a6d18fda4c42`, 228 celdas, 0 candidatas, 0 confirmadas.
  `count_tests` 568 → 796 al registrar y 801 al cerrar (5 de un `sweep` ajeno).
- Informe: `reports/research/campaign/2026-11-A.md` (no versionado).

### Por qué 0 candidatas

La condición (c) de meseta exige un positivo en un timeframe **adyacente**
(D1 → H4). Como H4 no tiene ningún activo elegible, (c) falla en **228/228**
celdas. No es falta de señal en D1: es que el diseño pedía un vecino que no
existe. Filtros que fallan: (a) 176, (b) 74, (c) 228, (d) 38.

### Anexo: las 47 celdas que solo fallan (c)

Análisis del descubrimiento ya pagado (sin pruebas nuevas de DSR). **47 celdas
pasan (a)+(b)+(d) y solo fallan (c)**. Sharpe neto in-sample (70 %), celdas con
≥30 trades:

| Familia | n | Mediana Sharpe | Sharpe > 0 |
|---|---|---|---|
| tsmom | 64 | **+0,443** | 60/64 |
| vol_breakout | 51 | **+0,342** | 46/51 |
| st_reversal | 64 | −0,153 | 21/64 |
| calendar | 36 | +0,006 | 18/36 |

Mejores celdas: XAUEUR lb250 +1,239 (1.175 trades), XAUAUD lb60 +1,227
(1.174), XAUEUR lb120 +1,150 (1.121), XCUUSD lb250 +1,015 (52), XAGAUD n10
+0,998 (116).

**Decisión: no se persigue.** Es in-sample y el DSR ya acumula 801 pruebas;
elegir estas 47 *después* de verlas es selección post-hoc. Si en el futuro hay
una razón independiente, se pre-registra `2026-11-B` con una regla de (c)
escrita **antes** de correr (p. ej. "no aplica si el timeframe adyacente no
tiene elegibles") y su propio `N_total`, y se corre una sola vez.

## Lecciones de 2026-11-A

- El descubrimiento debe correr **exactamente** las celdas de `N_total`; si no,
  el DSR miente.
- Un fallo de código a mitad de run no es una segunda pasada: se reanuda con el
  mismo `run_id` y `--resume`, y solo si aún no se ha visto el holdout.
- Una condición de meseta que depende de un timeframe vacío convierte la
  campaña en un cero garantizado. Antes de registrar, comprobar que cada
  condición tiene datos con los que cumplirse.
