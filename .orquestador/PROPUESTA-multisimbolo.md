# Propuesta · campañas multi-símbolo (diseño, sin código)

Fecha: 2026-11-23. Documento de diseño; no se registra, aprueba ni ejecuta
ninguna campaña. El objetivo es multiplicar las operaciones IS **sin**
multiplicar las pruebas que cuenta el DSR.

## 1. Idea

Una hipótesis se evalúa sobre una **cesta** de símbolos con los mismos
parámetros. Ejemplo: `ts_momentum_d1` con SMA(50/200), stop ATR 3,0 y salida a
60 días en XAUUSD, US500, US100, EURUSD, GBPUSD y USDJPY. No se optimiza un
juego de parámetros por símbolo: se elige una vez y se aplica a todos. Eso es
una sola hipótesis con seis series de observaciones, no seis campañas.

La campaña sigue teniendo una rejilla de parámetros (p. ej. 3×3×3 = 27
combinaciones). Cada combinación se convierte internamente en un **portfolio**
de seis estrategias hermanas, una por símbolo, con el mismo genoma. El resultado
que se evalúa es el del portfolio, no el de cada pierna por separado.

## 2. Registro y DSR

- `n_total` = número de combinaciones de la rejilla (27 en el ejemplo), **no**
  27×6. Cada combinación es un ensayo; los símbolos son observaciones del mismo
  ensayo.
- `n_evaluated` y `n_finalists` cuentan combinaciones de la cesta, no piernas.
- El DSR usa `n_total` de la campaña y `n_effective` de la frontera de la cesta.
  Añadir símbolos no debe inflar el denominador: si se probaran seis rejillas
  separadas y se eligiera la mejor, serían seis campañas y seis veces el DSR;
  la cesta evita exactamente eso.
- La spec debe declarar la cesta **antes** de ver resultados:
  `basket: [XAUUSD, US500, US100, EURUSD, GBPUSD, USDJPY]`, la fuente por
  símbolo y el periodo IS común. Cambiar la cesta después de mirar IS es una
  prueba nueva y debe registrarse como tal.
- El `config_hash` incluye la cesta, los símbolos y sus fuentes; dos campañas
  con la misma rejilla pero distinta cesta no son la misma prueba.

## 3. Agregación de R y pliegues

- Cada pierna genera sus operaciones con su propio stop ATR y su propio R. Si
  cada operación arriesga 1R, el R del portfolio en una fecha es la **suma** de
  los R netos de las piernas con operaciones ese día. No se multiplica por el
  número de símbolos ni se reescala a 1R por cartera.
- Los pliegues son **fechas globales** del IS común, no pliegues por símbolo.
  Se corta el calendario en los mismos tramos para todas las piernas y se
  agrega el R diario antes de calcular expectativa, PF, DD y pliegues
  positivos. Así un pliegue con seis símbolos no se convierte en seis pliegues.
- Si una pierna no tiene datos en un tramo, se informa y se excluye de ese
  tramo; no se rellena con cero ni se inventan velas. La cobertura mínima se
  exige por símbolo antes de aceptar la cesta.
- Métricas que se reportan: portfolio (principal), atribución por símbolo
  (informativa) y correlación media entre piernas. La atribución no se usa para
  elegir parámetros; solo para detectar que el resultado depende de una sola
  pierna.

## 4. Coste por símbolo y cuenta

- Cada pierna usa el perfil de coste de **su** símbolo y su cuenta: por ejemplo,
  US100 con CFD-001/CFD-006, US500 con CFD-006, XAU/FX con CFD-001/CFD-006.
  No se usa un coste medio único para toda la cesta.
- El coste por operación se calcula con el panel del símbolo (spread, comisión,
  slippage) y se resta del R bruto de esa pierna antes de agregar.
- `cost_R` de la cesta es la mediana ponderada por operaciones de las piernas;
  `cost_by_account` agrega por cuenta para comprobar que ninguna cuenta supera
  `cost_r_max`. La cuenta más cara de la cesta manda para la viabilidad.
- El tamaño de la cesta no cambia el riesgo por operación: cada pierna arriesga
  lo que declare su perfil; la suma de riesgos abiertos se controla con las
  reglas de la cuenta (max_open_positions, max_open_risk), no con un reescalado
  silencioso.

## 5. Control de deriva por cesta

- Para cada símbolo se generan las mismas 1.000 réplicas de entradas aleatorias
  con su proporción de lados, número de operaciones, duración media y stop ATR.
  La semilla se deriva del id de campaña y de un sufijo estable por símbolo, de
  modo que todas las combinaciones de la misma cesta se comparan contra las
  mismas secuencias.
- El R de cada réplica es la suma de las piernas en las mismas fechas; la
  distribución de referencia es la del **portfolio aleatorio**, no la de un
  símbolo suelto. Así el percentil mide si la cesta aporta algo frente a entrar
  al azar en los mismos seis mercados con la misma exposición.
- El percentil de la cesta se guarda en `metrics.drift` y se exige ≥90 para
  pasar a candidata, igual que una campaña de un símbolo. Si una pierna tiene
  menos de `min_trades` en IS, la cesta no se evalúa: no se compensa con las
  otras piernas.
- Para plantillas long-only (p. ej. `turn_of_month`), el control usa entradas
  aleatorias **solo largas** con la misma duración; ya está cubierto por
  `drift.py` al tomar la proporción de lados de las operaciones reales y tiene
  test propio.

## 6. Riesgos

- **Correlación:** US100 y US500 comparten casi el mismo factor; XAU y los
  índices pueden divergir; USDJPY/EURUSD/GBPUSD comparten el dólar. Seis
  piernas no son seis pruebas independientes. Se reporta la correlación media y
  el peor par; si dos piernas correlacionan >0,9, la cesta aporta poco y puede
  convertirse en una apuesta concentrada.
- **P-hacking por símbolo:** elegir la cesta después de ver qué símbolo funciona
  invalida el DSR. La cesta se congela en la spec.
- **Coste y liquidez:** el símbolo barato en teoría puede ser caro en la cuenta
  real; el `cost_R` por pierna debe pasar el umbral, no solo la media.
- **Datos:** fuentes distintas (Dukascopy/Databento), zonas horarias, festivos
  y huecos distintos. La cesta exige el mismo IS y la misma convención de
  cierre; no se mezclan fuentes dentro de una misma pierna.
- **Riesgo agregado:** seis posiciones simultáneas pueden superar el riesgo
  diario de la cuenta aunque cada una sea 1R. El portfolio debe pasar por las
  reglas de la cuenta antes de operar; el laboratorio solo mide.
- **Selección de la mejor pierna:** si el resultado de la cesta depende de una
  sola pierna, se documenta; no se convierte esa pierna en una campaña nueva
  sin registrarla como prueba separada.

## 7. Estimación de operaciones IS

Con las plantillas D1 existentes y un IS de ~10-20 años:

| Plantilla | Ops IS por símbolo y combinación | Cesta de 6 símbolos |
|---|---:|---:|
| `ts_momentum_d1` | ~26–48 (SIGUIENTE R9) | ~156–288 |
| `d1_extension_reversion` | ~26–48 (SIGUIENTE R9) | ~156–288 |
| `turn_of_month` | ~50–100 (medido en R9) | ~300–600 |

El mínimo D1 es 15 operaciones IS por combinación y 3 por pliegue; la cesta de
6 símbolos lo supera con holgura incluso en el caso conservador. El cuello de
botella deja de ser el número de operaciones y pasa a ser la correlación entre
piernas y la calidad del dato por símbolo.

## 8. Qué falta para implementarlo

1. Añadir `basket` a la spec y al `config_hash` (hoy una campaña es un solo
   instrumento).
2. Un evaluador de portfolio que compile la misma combinación en cada símbolo,
   alinee por fecha y agregue R diario antes de métricas y pliegues.
3. Un `CostBook` por pierna y una tabla de atribución por símbolo.
4. Extender el control de deriva para generar réplicas por pierna con semilla
   estable y agregar el portfolio aleatorio.
5. Tests de agregación (dos piernas con R conocido → portfolio exacto),
   cobertura incompleta, correlación y DSR (`n_total` = combinaciones, no
   combinaciones × símbolos).

No se implementa en R9: este documento es la propuesta para que el operador
decida si quiere una campaña de cesta en una fase posterior.
