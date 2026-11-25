# Limitaciones

- **No hay edge validado.** Las 22 variantes A–E fallaron (Fase C). El indicador no emite señales.
- **No hay Strategy Tester.** Sin reglas de entrada validadas no hay nada que probar. Construir uno solo produciría una curva de una estrategia ya descartada. El backtest real está en `tools/phase_c.py`.
- **El indicador no lee la cuenta.** Saldo, umbral, P&L y operaciones se introducen a mano. Si están desactualizados, los cálculos también.
  - En Apex Intraday, el umbral sube con el pico no realizado, así que el valor introducido puede quedarse viejo en minutos.
- **Noticias:** tabla embebida de fuentes oficiales, válida hasta el 2027-11-30.
  - No incluye ISM, Jobless Claims, subastas del Tesoro ni discursos de Powell (hay 2 eventos manuales).
  - No detecta cambios de fecha.
  - Pine no puede consultar calendarios externos.
- **Festivos y medias sesiones:** el indicador no los conoce. Tradeify cierra a las 12:59 ET en festivos cortos.
- **Rolls:** `NQ1!` y `MNQ1!` cambian de contrato con la regla de TradingView. La semana de roll puede mezclar niveles PDH/ONH de dos contratos.
- **US100 / CFD:** el volumen es tick volume; el VWAP es un proxy y no hay RVOL. El valor por punto depende del bróker.
- **Reglas de las firmas:** verificadas el 2026-11-25. No verificadas:
  - las comisiones;
  - el Scaling Plan XFA de Topstep;
  - la equivalencia mini/micro de Apex;
  - la hora exacta del cierre forzoso de Apex.
- **Compilación:** pendiente de hacerla en TradingView con cuenta (ver `07_AUDIT/Pine_Compilation_Report.md`).
