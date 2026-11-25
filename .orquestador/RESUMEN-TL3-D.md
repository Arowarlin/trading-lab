Hecho
- TL3-D D0-D5b completos y cerrados en commits pequeños: D1 protecciones, D2 línea base sin ventaja, D3 cobertura de datos, D3b correcciones, D4 plan de potencia de ai_trader, D5 plan del forward del EA, D5b diagnóstico de la TCA.
- Sin campañas, OOS, órdenes, push ni cambios en prop/. TL3-D no suma al contador.
- Cierre: ruff limpio; pytest 2000 passed + 1 skipped; lab propfund verify OK.

1. Protecciones y resultados
- Swap 2,008 bps/noche; nights(fecha); UTF-8 en TL3_REPORTS; add_status/status_table.
- T5-bis: 12 TP / 13 SL / 23 otro; 23/48 coincidencias; #27 y #51 terminan en barreras opuestas.
- Cobertura T7 2012-2021: US100 1116, US500 800, US30 1068 sesiones válidas (US30 desde 2013-09-30).
- P(financiada) sin ventaja, riesgo 0,5 %, b=2: FTMO 2-Step 17,44 %; FTMO 1-Step 30,34 %; FundingPips 22,46 % corregido (15,86 % antiguo no fiable).
- ai_trader: evaluación única a n=180 (Δ_t 177), estimada ~2027-01-04; H-2026-012 draft.
- EA: 3 operaciones cerradas en el forward (16, 18 y 24-11); puntos de control 30/60/515 (~2027-03-16, ~2027-07-13, ~2032-06-14).
- TCA: 68 filas, 66 con slippage 0, 2 sin fill, 0 con latencia; decisión→fill real 0,44 bps de mediana (45/48), 3 Sin datos.

Aviso
- FundingPips: error del simulador anterior confirmado (30.672/45.000 caminos afectados; 0 con el corregido en TL2-DIARIO 020b41b). La tabla D2 queda marcada como no fiable.
- TCA: mide envío→fill, no decisión→fill; el fill_px de la TCA difiere del fill real (mediana 0,43 bps, máximo 2,90 bps). Propuesta no aplicada: exige otra cola con baseline, regresión y changelog.
- T7 y T8 no confirman; no se cambia el EA ni el riesgo.
- lab doctor: Frescura FAIL 7/17 (datos de mercado), resto OK; lab propfund verify OK.
- Bloqueo: count_tests 1926, no 1897 (+29 por informal_trials 6 y 7 de NASDAQ EDGE, ajenas a TL3-D); bloqueado: contador cambiado.

Siguiente
- Cierre 1e y tag tl3-ciclo1e. Fin de la cola: no se empieza nada más.
