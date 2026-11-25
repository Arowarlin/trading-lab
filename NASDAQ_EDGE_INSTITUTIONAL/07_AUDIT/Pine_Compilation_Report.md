# Informe de compilación Pine

Estado al 2026-11-25: **NO COMPILADO en TradingView.**

## Qué se intentó

- Se abrió el Pine Editor en el navegador integrado (`CME_MINI:MNQ1!`) y se
  insertaron las 414 líneas del script.
- TradingView pidió una cuenta ("Join for free") para añadirlo al gráfico. No hay
  sesión iniciada, y crear una cuenta no corresponde al agente. Sin "Add to
  chart" no hay compilación.
- El pegado automático en el editor pudo alterar la indentación. Para compilar,
  pegar a mano desde el archivo.

## Revisión estática hecha (sin compilador)

Correcciones aplicadas antes de compilar:
1. Las declaraciones `var` múltiples en una línea, que Pine no admite, se
   separaron en líneas individuales.
2. `ta.sma` llamado dentro de un ternario (aviso de consistencia) se sacó a una
   variable global (`volSma20`).
3. `request.security` en temporalidad superior usa `[1]` + `lookahead_on`
   (patrón sin repintado).

Puntos que el compilador debe confirmar:
- tipos en `math.min` y `math.max` (int/float);
- la división `int / int` en `minsToNext`;
- `str.startswith`;
- `ta.vwap` con 3 retornos en v6;
- longitud de `array.from` con 82 timestamps.

## Compilación 1 (operador, TradingView, MNQ1! 1m, 2026-11-25)

- **Compila sin errores de sintaxis ni de tipos.** Los argumentos de los inputs se ven en la leyenda.
- **Error de ejecución RE10110:** el script superaba el límite de 0,5 s.
  - Causa: el bucle de noticias recorría los 83 eventos en cada vela, con llamadas a funciones de zona horaria. Con ~20.000 velas de 1 min eran ~1,7 M de iteraciones.
  - Corrección: puntero monótono sobre el calendario ordenado (`evPtr`) y función `evalEv`. Cada vela evalúa solo los eventos de su día y se detiene en el siguiente Tier 1–2. El día se calcula una vez por vela con `dayStart` y `dayEnd`.
## Compilación 2 (operador, NQ1! 5m, 2026-11-25 16:10 ET)

- **Compila y se ejecuta sin errores.** El panel se muestra completo.
- Comprobado en pantalla:
  - NO TRADE por comisión sin configurar (comportamiento esperado);
  - "Fuera de RTH" a las 16:10 ET y VWAP en Sin datos fuera de RTH;
  - NEWS CLEAR con calendario válido hasta el 2027-11-30;
  - próximo evento NFP 12-04 08:30 (12.500 min, correcto);
  - distancia al umbral $2.000 y presupuesto $150.
- Ajustes cosméticos tras la compilación 2:
  - RVOL con cero inicial (`0.00`);
  - cuenta atrás en días y horas.
- Pendiente: verificación 3 de esos dos cambios.

## Pendiente (operador, con cuenta de TradingView)

1. Pegar `04_PINE_SCRIPT/Nasdaq_Edge_Indicator.pine` y pulsar **Add to chart**.
2. Anotar aquí cada error con línea y mensaje, o "0 errores".
3. Comprobar visualmente en MNQ1! 1m:
   - OR15 entre 9:30 y 9:45 ET;
   - ONH/ONL;
   - PDH/PDL;
   - panel sin "Sin datos" en RTH.
