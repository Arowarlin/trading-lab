# EDGE-2 Y1 - plan de campanas congelado

**Congelado:** 2026-11-26T02:06:53.032778+00:00
**Hash:** `6ffd14ae2998a37ee9d6ab7cdff73b0fb2f1e3728f65c45f684ba531d85d360d`
**Campanas:** 18 · **n_total:** 7,920

## Reglas congeladas

- Fuente `dukascopy`; perfil `small`; modo `ga`; semilla = indice.
- Coste `CFD-001` + `CFD-006`, `--cost-mode worst`; US500 solo `CFD-006` porque CFD-001 no lo permite.
- M15/M30: IS 2015-01-02:2019-12-31 (Y1 decia 2014; `usable_from` manda).
- H1/H4: IS 2019-01-02:2020-12-31 (2018 tiene huecos nocturnos reales; no es error del control).
- OOS-1: 2020-01-01:2022-12-31 (M15/M30) / 2021-01-01:2022-12-31 (H1/H4). OOS-2: 2023-01-01:.
- `intraday_momentum_close_v2` excluida por Y1.1; no se toca `fastbt.py`.
- US30 fuera: spread Sin datos. US100 con swap 6,24 bps/noche pasa la cota enmendada 0,8-7,3.
- Maximo 20 campanas; cobertura 1 por plantilla y 1 por TF, resto por menor `cost_r`.

## Matriz

| # | Campana | Plantilla | Activo | TF | Semilla | IS | OOS-1 | cost_r |
|---:|---|---|---|---|---:|---|---|---:|
| 1 | `edge2-01-donchian-vol-h4-us100-h4` | donchian_vol_h4 | US100 | H4 | 1 | 2019-01-02:2020-12-31 | 2021-01-01:2022-12-31 | 0.0117 |
| 2 | `edge2-02-trend-pullback-mtf-us100-h4` | trend_pullback_mtf | US100 | H4 | 2 | 2019-01-02:2020-12-31 | 2021-01-01:2022-12-31 | 0.0117 |
| 3 | `edge2-03-vol-squeeze-breako-us100-h4` | vol_squeeze_breakout | US100 | H4 | 3 | 2019-01-02:2020-12-31 | 2021-01-01:2022-12-31 | 0.0117 |
| 4 | `edge2-04-st-reversal-idx-us100-h1` | st_reversal_idx | US100 | H1 | 4 | 2019-01-02:2020-12-31 | 2021-01-01:2022-12-31 | 0.0243 |
| 5 | `edge2-05-trend-pullback-mtf-us100-h1` | trend_pullback_mtf | US100 | H1 | 5 | 2019-01-02:2020-12-31 | 2021-01-01:2022-12-31 | 0.0243 |
| 6 | `edge2-06-vol-squeeze-breako-us100-h1` | vol_squeeze_breakout | US100 | H1 | 6 | 2019-01-02:2020-12-31 | 2021-01-01:2022-12-31 | 0.0243 |
| 7 | `edge2-07-donchian-vol-h4-us500-h4` | donchian_vol_h4 | US500 | H4 | 7 | 2019-01-02:2020-12-31 | 2021-01-01:2022-12-31 | 0.0255 |
| 8 | `edge2-08-trend-pullback-mtf-us500-h4` | trend_pullback_mtf | US500 | H4 | 8 | 2019-01-02:2020-12-31 | 2021-01-01:2022-12-31 | 0.0255 |
| 9 | `edge2-09-vol-squeeze-breako-us500-h4` | vol_squeeze_breakout | US500 | H4 | 9 | 2019-01-02:2020-12-31 | 2021-01-01:2022-12-31 | 0.0255 |
| 10 | `edge2-10-st-reversal-idx-us500-h1` | st_reversal_idx | US500 | H1 | 10 | 2019-01-02:2020-12-31 | 2021-01-01:2022-12-31 | 0.0516 |
| 11 | `edge2-11-trend-pullback-mtf-us500-h1` | trend_pullback_mtf | US500 | H1 | 11 | 2019-01-02:2020-12-31 | 2021-01-01:2022-12-31 | 0.0516 |
| 12 | `edge2-12-vol-squeeze-breako-us500-h1` | vol_squeeze_breakout | US500 | H1 | 12 | 2019-01-02:2020-12-31 | 2021-01-01:2022-12-31 | 0.0516 |
| 13 | `edge2-13-st-reversal-idx-us100-m30` | st_reversal_idx | US100 | M30 | 13 | 2015-01-02:2019-12-31 | 2020-01-01:2022-12-31 | 0.0609 |
| 14 | `edge2-14-trend-pullback-mtf-us100-m30` | trend_pullback_mtf | US100 | M30 | 14 | 2015-01-02:2019-12-31 | 2020-01-01:2022-12-31 | 0.0609 |
| 15 | `edge2-15-vol-squeeze-breako-us100-m30` | vol_squeeze_breakout | US100 | M30 | 15 | 2015-01-02:2019-12-31 | 2020-01-01:2022-12-31 | 0.0609 |
| 16 | `edge2-16-st-reversal-idx-us100-m15` | st_reversal_idx | US100 | M15 | 16 | 2015-01-02:2019-12-31 | 2020-01-01:2022-12-31 | 0.0888 |
| 17 | `edge2-17-trend-pullback-mtf-us100-m15` | trend_pullback_mtf | US100 | M15 | 17 | 2015-01-02:2019-12-31 | 2020-01-01:2022-12-31 | 0.0888 |
| 18 | `edge2-18-vol-squeeze-breako-us100-m15` | vol_squeeze_breakout | US100 | M15 | 18 | 2015-01-02:2019-12-31 | 2020-01-01:2022-12-31 | 0.0888 |

**Suma n_total:** 7,920 (18 x 440).

- Por TF: {'H1': 6, 'H4': 6, 'M15': 3, 'M30': 3}
- Por activo: {'US100': 12, 'US500': 6}
- Por plantilla: {'donchian_vol_h4': 2, 'st_reversal_idx': 4, 'trend_pullback_mtf': 6, 'vol_squeeze_breakout': 6}

## Pasada 2

Maximo 4 campanas con al menos 1 finalista que pase Y3 completo; perfil `medium`, semilla `1000 + indice`.

## Registro

- Dry-run: **18/18 OK** (TL3_REPORTS/edge2_register_dry.log).
- Registro real: **18/18 draft**, suma 
_total = **7.920**; 12 nuevas y 6 reutilizadas del primer intento (mismos activo/TF/segmentos/coste/semilla).
- edge2-13 a edge2-18 (US100 M15/M30) ya estaban registradas con el mismo dataset; el resto se registro con el frame recortado al IS para que data-check no contara 2012-2018 fuera de tramo.
- US500 usa solo CFD-006: CFD-001 no lo permite.

## Coherencia Y0 → Y1 (ROBUST-1 R5)

Comparados `edge2_costes.md` / `edge2_data.json` de `49551da` (plan Y1) y
`768e572` (corrección de huecos Y0):

- **No cambia** `cost_r`, `viable`, `useful_start`, `is_start_effective` ni el
  inicio de desarrollo de ninguna de las 18 campañas.
- Solo cambia la **clasificación de huecos** (`non_scheduled_gaps_full`):
  los huecos nocturnos pre-2018 y los huecos de historia >1 día se separan.
- Por tanto, el plan Y1 **sigue congelado y válido**. No hay Y1b, no se
  cancelan ni registran borradores y las 18 campañas siguen en `draft`.
- H1/H4 mantienen IS 2019-01-02:2020-12-31: 2018 sigue sin ser válido según
  `is_start_effective` (los huecos nuevos son de historia/cierre, no una
  corrección que habilite 2018).

