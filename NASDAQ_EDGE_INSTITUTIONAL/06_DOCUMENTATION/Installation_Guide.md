# Instalación

1. En TradingView abre el **Pine Editor**. Hace falta una cuenta de TradingView.
2. Copia el contenido completo de `04_PINE_SCRIPT/Nasdaq_Edge_Indicator.pine`, pégalo y pulsa **Add to chart**.
3. Abre un gráfico de `CME_MINI:MNQ1!`, `CME_MINI:NQ1!` o de un contrato concreto (recomendado en la semana de roll), en 1, 3, 5 o 15 minutos.
   - En un CFD US100, rellena "Valor por punto US100/CFD" con el valor de tu bróker.
4. En los ajustes:
   - elige el perfil de la firma;
   - introduce saldo, umbral, P&L de hoy, operaciones y pérdidas seguidas;
   - pon la **fecha del estado**;
   - configura la **comisión por contrato**. Mientras sea 0 el indicador muestra NO TRADE.
5. Alertas: crea una alerta del indicador con "Any alert() function call" para
   los cambios WAIT ↔ NO TRADE y noticias próximas (mensaje JSON), o una alerta
   por cada `alertcondition` (SL, TP1, TP2, noticias, máximos).

## Actualizar el calendario de noticias

El bloque embebido caduca el **2027-11-30**. Para renovarlo:

1. Añade las nuevas fechas oficiales (BLS, BEA, Census, Fed) a `02_DATA/future_events.csv`.
2. Ejecuta:

   ```powershell
   .\.venv\Scripts\python.exe -I NASDAQ_EDGE_INSTITUTIONAL\tools\build_pine_news.py --valid-until AAAA-MM-DD
   ```

3. Vuelve a pegar el script.

Si una fecha cambia (por ejemplo, por un cierre del gobierno), corrige el CSV y
regenera. El indicador no lo detecta solo.
