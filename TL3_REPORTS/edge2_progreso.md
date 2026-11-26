# EDGE-2 - progreso

Plan Y1: `6ffd14ae2998a37ee9d6ab7cdff73b0fb2f1e3728f65c45f684ba531d85d360d` (18 campanas, n_total 7.920).
Iniciado Y2: 2026-11-26 08:30 -04:00.

**Estado:** Y2 en espera. `edge1` presente; falta el tag `robust-1` (ROBUST-1 R6). Si ROBUST-1 publica
Y1b, se usa el plan recongelado. Comprobacion cada 10 min; sin lanzar campanas hasta que exista `robust-1`.

## Espera

- 2026-11-26 08:30 -04:00: `edge1` = si, `robust-1` = no. 18 borradores `edge2-*` en `draft`, ninguno ejecutado.
- 2026-11-26 08:33 -04:00: ROBUST-1 arranco en paralelo (`robust1: cola`, tag `robust-pre`, lock
  `proyecto-robust`). `count_tests` antes de EDGE-2 = **12.694**.
