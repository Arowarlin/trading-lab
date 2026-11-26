# EDGE-2 - progreso

Plan Y1: `6ffd14ae2998a37ee9d6ab7cdff73b0fb2f1e3728f65c45f684ba531d85d360d` (18 campanas, n_total 7.920).
Iniciado Y2: 2026-11-26 08:30 -04:00.

**Estado:** Y2 en espera. `edge1` presente; falta el tag `robust-1` (ROBUST-1 R6). Si ROBUST-1 publica
Y1b, se usa el plan recongelado. Comprobacion cada 10 min; sin lanzar campanas hasta que exista `robust-1`.

## Espera

- 2026-11-26 08:30 -04:00: `edge1` = si, `robust-1` = no. 18 borradores `edge2-*` en `draft`, ninguno ejecutado.
- 2026-11-26 08:33 -04:00: ROBUST-1 arranco en paralelo (`robust1: cola`, tag `robust-pre`, lock
  `proyecto-robust`). `count_tests` antes de EDGE-2 = **12.694**.

## Pasada 1

| # | Campana | Activo | TF | Plantilla | Eval | Efect | Finalistas | Estado | Consola | Tiempo |
|---:|---|---|---|---|---:|---:|---:|---|---|---:|
| 1 | `edge2-01-donchian-vol-h4-us100-h4` | US100 | H4 | donchian_vol_h4 | 434 | 22 | 0 | done | si | 6.4 min |
| 2 | `edge2-02-trend-pullback-mtf-us100-h4` | US100 | H4 | trend_pullback_mtf | 435 | 53 | 5 | done | si | 6.7 min |
| 3 | `edge2-03-vol-squeeze-breako-us100-h4` | US100 | H4 | vol_squeeze_breakout | 432 | 39 | 1 | done | si | 6.7 min |
| 4 | `edge2-04-st-reversal-idx-us100-h1` | US100 | H1 | st_reversal_idx | 440 | 30 | 0 | done | si | 6.7 min |
| 5 | `edge2-05-trend-pullback-mtf-us100-h1` | US100 | H1 | trend_pullback_mtf | 440 | 73 | 2 | done | si | 8.3 min |
| 6 | `edge2-06-vol-squeeze-breako-us100-h1` | US100 | H1 | vol_squeeze_breakout | 438 | 75 | 1 | done | si | 8.0 min |
| 7 | `edge2-07-donchian-vol-h4-us500-h4` | US500 | H4 | donchian_vol_h4 | 435 | 49 | 0 | done | si | 7.3 min |
| 8 | `edge2-08-trend-pullback-mtf-us500-h4` | US500 | H4 | trend_pullback_mtf | 435 | 58 | 2 | done | si | 7.2 min |
| 9 | `edge2-09-vol-squeeze-breako-us500-h4` | US500 | H4 | vol_squeeze_breakout | 437 | 38 | 0 | done | si | 6.7 min |
| 10 | `edge2-10-st-reversal-idx-us500-h1` | US500 | H1 | st_reversal_idx | Sin datos | Sin datos | Sin datos | bloqueado: CalledProcessError: Command '['E:\\trading-lab\\.venv\\Scripts\\lab.exe', 'discovery', 'approve', 'edge2-10-st-reversal-idx-us500-h1', '--approved-by-operator']' returned non-zero exit status 1. | si | 0.4 min |
| 11 | `edge2-11-trend-pullback-mtf-us500-h1` | US500 | H1 | trend_pullback_mtf | 440 | 80 | 1 | done | si | 9.4 min |
| 12 | `edge2-12-vol-squeeze-breako-us500-h1` | US500 | H1 | vol_squeeze_breakout | 438 | 78 | 0 | done | si | 10.5 min |
