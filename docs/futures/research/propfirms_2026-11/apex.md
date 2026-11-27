# Apex Trader Funding · ficha 50K (investigación 2026-11)

- **Id:** `apex` · **Cuenta de referencia:** 50K · **Fecha de consulta:** 2026-11-27 (UTC).
- **Estado global:** `parcial`, y solo gracias al registro del laboratorio. Hoy la web oficial respondió
  **403** (bloqueo de Cloudflare) a `curl` con el agente de usuario por defecto. **Hoy no se leyó ninguna
  página oficial de Apex.** No se suplantó un navegador ni se usaron cachés, espejos ni copias de terceros.
- **Origen de los datos `parcial`:** `NASDAQ_EDGE_INSTITUTIONAL/01_RESEARCH/Prop_Firm_Rules.md §2`.
  Son datos **verificados por el laboratorio el 2026-11-25, no releídos hoy**. Ese registro no guarda
  citas literales de Apex, solo paráfrasis en español. Además, abrevia varias rutas con "…": se copian tal
  cual, y la URL completa queda **Sin datos**.
- **Aviso de registros internos:** `config/prop_economics/firms_futures.yaml` fecha la lectura de
  `prohibited-activities` el **2026-11-19**, con `status: needs_verification`. Por su parte,
  `docs/propfund/03_matriz_empresas.md` anota "fuentes discrepan sobre evaluación". La prohibición de
  automatización tiene, por tanto, dos fechas internas y una duda abierta sobre su alcance en evaluación.
- **Programas:** dos caminos independientes que **no se mezclan**:
  (1) Evaluación EOD → Performance Account (PA) EOD;
  (2) Evaluación Intraday Trailing → PA Intraday.
- **Caducidad:** Apex cambia sus reglas a menudo. Hay que reverificar todo antes de usarlo en el motor EV.

**Fuente abreviada:** **[LAB]** = registro del laboratorio del 2026-11-25 (archivo citado arriba), con la
ruta de Apex que cita. Cita literal en todas las filas [LAB]: **ninguna**, porque el registro solo
parafrasea.

## A. Costes (50K)

| Campo | Valor | Cita literal | Fuente | Fecha | Confianza | Estado |
|---|---|---|---|---|---|---|
| Precio de evaluación (lista y promoción) | **Sin datos** (web 403; el registro del laboratorio no recoge precios) | — | https://apextraderfunding.com/ → 403 | 2026-11-27 | — | no verificado |
| ¿Suscripción mensual o pago único? | **Sin datos** | — | ídem | 2026-11-27 | — | no verificado |
| Activación de la PA | **Sin datos** | — | ídem | 2026-11-27 | — | no verificado |
| Reset | **Sin datos** | — | ídem | 2026-11-27 | — | no verificado |
| Datos de mercado | **Sin datos** | — | ídem | 2026-11-27 | — | no verificado |
| Comisiones MNQ / NQ | **Sin datos**; el laboratorio ya las tenía como pendientes (§5) | — | [LAB] §5 | 2026-11-25 | — | no verificado |
| Otros cargos (API, plataforma, retiro) | **Sin datos** | — | — | 2026-11-27 | — | no verificado |
| Coste hasta financiada (1 intento) | **Sin datos** | — | — | 2026-11-27 | — | no verificado |
| Mantener la PA 3 y 6 meses | **Sin datos** | — | — | 2026-11-27 | — | no verificado |

## B. Reglas de trading

### B.1 Evaluación EOD (End-of-Day Trailing) 50K

| Campo | Valor | Cita | Fuente | Fecha | Confianza | Estado |
|---|---|---|---|---|---|---|
| Profit target | 3.000 USD | sin cita | [LAB] https://apextraderfunding.com/help-center/eod-trailing-drawdown-accounts/eod-evaluations/ | 2026-11-25 | media | parcial |
| Drawdown máximo | 2.000 USD | sin cita | [LAB] ídem | 2026-11-25 | media | parcial |
| Tipo | EOD trailing. El umbral se recalcula una vez al día (16:59:59 ET) con el balance de cierre, se aplica **en tiempo real** durante la sesión siguiente y nunca baja | sin cita | [LAB] "…/eod-drawdown-explained/" (ruta abreviada) | 2026-11-25 | media | parcial |
| ¿Incluye P&L no realizado? | Sí, durante la sesión: el umbral fijo se vigila en tiempo real. Es la conclusión del laboratorio en §4.1: "La pérdida flotante cuenta" | sin cita | [LAB] §2.1 y §4.1 | 2026-11-25 | media | parcial |
| Dónde se bloquea | Con Rithmic y WealthCharts, en el balance objetivo (53.000 USD). Con Tradovate, el trailing es **indefinido** | sin cita | [LAB] "…/eod-drawdown-explained/" | 2026-11-25 | media | parcial |
| DLL | 1.000 USD, fijo durante la sesión. Pausa el día; no suspende la evaluación | sin cita | [LAB] "…/daily-loss-limit-explained/" | 2026-11-25 | media | parcial |
| Consistencia | no se aplica en la evaluación | sin cita | [LAB] eod-evaluations | 2026-11-25 | media | parcial |
| Contratos máximos | 6. La equivalencia con micros **Sin datos** (no figura en esa página) | sin cita | [LAB] eod-evaluations | 2026-11-25 | media | parcial / Sin datos |
| Días mínimos y plazo | sin mínimo de días; plazo de 30 días | sin cita | [LAB] eod-evaluations | 2026-11-25 | media | parcial |
| Escalado | no se aplica en la evaluación | sin cita | [LAB] eod-evaluations | 2026-11-25 | media | parcial |

### B.2 Evaluación Intraday Trailing 50K

| Campo | Valor | Cita | Fuente | Fecha | Confianza | Estado |
|---|---|---|---|---|---|---|
| Profit target | 3.000 USD | sin cita | [LAB] "…/intraday-trailing-drawdown-evaluations/" | 2026-11-25 | media | parcial |
| Drawdown máximo | 2.000 USD | sin cita | [LAB] ídem | 2026-11-25 | media | parcial |
| Tipo | Trailing intradía: sigue el **pico intradía, incluido el P&L no realizado**. Ejemplo del laboratorio: +900 USD no realizados que vuelven a 0 suben el umbral 900 USD | sin cita | [LAB] "…/intraday-trailing-drawdown-explained/" | 2026-11-25 | media | parcial |
| Dónde se bloquea | con Rithmic y WealthCharts, en 53.000 USD; con Tradovate, indefinido | sin cita | [LAB] ídem | 2026-11-25 | media | parcial |
| DLL | **no hay** | sin cita | [LAB] ídem y "daily-loss-limit-explained" | 2026-11-25 | media | parcial |
| Contratos máximos | 6; equivalencia con micros **Sin datos** | sin cita | [LAB] ídem | 2026-11-25 | media | parcial / Sin datos |
| Consistencia, días mínimos y escalado | **Sin datos**: el registro no los repite para Intraday y no se generalizan desde EOD | — | — | 2026-11-25 | — | no verificado |

### B.3 Performance Account (PA, simulada financiada) 50K, EOD e Intraday

| Campo | PA EOD | PA Intraday | Cita | Fuente | Fecha | Confianza | Estado |
|---|---|---|---|---|---|---|---|
| Drawdown máximo | 2.000 USD EOD | 2.000 USD intradía | sin cita | [LAB] "páginas PA" | 2026-11-25 | media | parcial |
| Dónde se bloquea | en 50.100 USD | en 50.100 USD | sin cita | [LAB] "drawdown-explained" | 2026-11-25 | media | parcial |
| Contratos y DLL por nivel (L1 a L4) | L1 (0–1.499 USD): 2 contratos, DLL 1.000. L2 (1.500–2.999): 3 contratos, DLL 1.000. L3 (3.000–5.999): 4 contratos, DLL 2.000. L4 (≥ 6.000): 4 contratos, DLL 3.000 | igual | sin cita | [LAB] "scaling-levels-pa-explained" | 2026-11-25 | media | parcial |
| Inactividad | Se cierra si no hay 2 días con ≥ 50 USD en 30 días. El registro lo cita de la FAQ de PA Intraday; para EOD, **Sin datos** | ídem | sin cita | [LAB] "intraday PA FAQ" | 2026-11-25 | media | parcial |

### B.4 Conducta (todas las cuentas, según el laboratorio)

| Campo | Valor | Cita | Fuente | Fecha | Confianza | Estado |
|---|---|---|---|---|---|---|
| Horario y cierre obligatorio | Prohibido mantener posiciones abiertas al cierre del mercado. El laboratorio anota que el mercado cierra a las 17:00 ET; la hora exacta de liquidación es **Sin datos** | sin cita | [LAB] §2.4 y §4.4 · https://apextraderfunding.com/help-center/getting-started/prohibited-activities/ | 2026-11-25 | media | parcial |
| Noticias | Se puede operar con la estrategia habitual. Están prohibidas las estrategias de "news trading" que persiguen el mercado o ponen órdenes a ambos lados | sin cita | [LAB] prohibited-activities | 2026-11-25 | media | parcial |
| Overnight y fin de semana | no se permiten, porque está prohibido mantener posiciones al cierre del mercado | sin cita | [LAB] ídem | 2026-11-25 | media | parcial |
| Stop | obligatorio (de orden o mental) | sin cita | [LAB] ídem | 2026-11-25 | media | parcial |
| Riesgo desproporcionado | prohibido. Ejemplo oficial: TP de 5 ticks con SL de 150 | sin cita | [LAB] ídem | 2026-11-25 | media | parcial |
| Otras prohibiciones | usar el umbral de drawdown como stop; hedging | sin cita | [LAB] ídem | 2026-11-25 | media | parcial |

## C. Payouts (PA 50K)

| Campo | Valor | Cita | Fuente | Fecha | Confianza | Estado |
|---|---|---|---|---|---|---|
| Días necesarios y beneficio mínimo por día | 5 días con ≥ 250 USD (EOD) o ≥ 200 USD (Intraday) | sin cita | [LAB] "payouts" | 2026-11-25 | media | parcial |
| Consistencia en la PA | 50 % | sin cita | [LAB] "payouts" | 2026-11-25 | media | parcial |
| Mínimo por retiro | 500 USD | sin cita | [LAB] "payouts" | 2026-11-25 | media | parcial |
| Buffer ("safety net") | 52.100 USD | sin cita | [LAB] "payouts" | 2026-11-25 | media | parcial |
| Número máximo de retiros | 6 payouts | sin cita | [LAB] "payouts" | 2026-11-25 | media | parcial |
| Máximo por retiro | **Sin datos** | — | — | — | — | no verificado |
| Reparto | **Sin datos** (el registro no lo recoge) | — | — | — | — | no verificado |
| Topes acumulados | **Sin datos** | — | — | — | — | no verificado |
| Solicitado → aprobado → procesado → recibido | **Sin datos** | — | — | — | — | no verificado |
| Métodos de pago | **Sin datos** | — | — | — | — | no verificado |
| KYC | **Sin datos** | — | — | — | — | no verificado |
| Transición a Live | **Sin datos** | — | — | — | — | no verificado |

## D. Automatización (crítico)

**Veredicto: prohibida**, según el registro del laboratorio (2026-11-25, no releído hoy). Hoy no se leyó
ningún texto oficial de Apex. La prohibición tiene dos fechas internas (2026-11-19 y 2026-11-25) y hay
una nota de que "fuentes discrepan sobre evaluación". Por eso **no se asume** ningún permiso en ninguna
fase hasta releer la página.

| Campo | Valor | Cita | Fuente | Fecha | Confianza | Estado |
|---|---|---|---|---|---|---|
| Bots y estrategias automáticas | **prohibidos** ("Automatización y algoritmos prohibidos") | sin cita | [LAB] §2.4 · https://apextraderfunding.com/help-center/getting-started/prohibited-activities/ | 2026-11-25 (yaml: 2026-11-19) | media | parcial |
| NinjaTrader 8 Automated Strategies / NinjaScript | **Sin datos** por nombre; quedan dentro de la prohibición general | — | [LAB] | 2026-11-25 | baja | parcial |
| ATM Strategies | **Sin datos** | — | — | — | — | no verificado |
| Copiadores de operaciones | **Sin datos** | — | — | — | — | no verificado |
| Varias cuentas (cuántas) | **Sin datos** | — | — | — | — | no verificado |
| VPS | **Sin datos** | — | — | — | — | no verificado |
| Límites de frecuencia | **Sin datos** | — | — | — | — | no verificado |
| HFT | **Sin datos** | — | — | — | — | no verificado |
| Microscalping (umbral) | **Sin datos** | — | — | — | — | no verificado |
| Técnicas de ejecución prohibidas | news trading que persigue el mercado o pone órdenes a ambos lados; hedging; usar el umbral como stop; riesgo desproporcionado | sin cita | [LAB] §2.4 | 2026-11-25 | media | parcial |
| ¿Pueden anular beneficios por automatización? | **Sin datos** | — | — | — | — | no verificado |
| Diferencias evaluación / PA / Live | **Sin datos**; hay una duda interna sobre la evaluación | — | `docs/propfund/03_matriz_empresas.md` | — | baja | no verificado |

## E. Plataformas

| Campo | Valor | Cita | Fuente | Fecha | Confianza | Estado |
|---|---|---|---|---|---|---|
| Rithmic | mencionada: el bloqueo del trailing en 53.000 USD depende de la plataforma | sin cita | [LAB] §2.1 | 2026-11-25 | media | parcial |
| WealthCharts | mencionada, igual que Rithmic | sin cita | [LAB] §2.1 | 2026-11-25 | media | parcial |
| Tradovate | mencionada: con Tradovate el trailing de la evaluación es indefinido | sin cita | [LAB] §2.1 | 2026-11-25 | media | parcial |
| NinjaTrader 8 · CQG · TradingView · Quantower · Sierra Chart · Bookmap · ATAS | **Sin datos** | — | — | — | — | no verificado |
| APIs y conexiones simultáneas | **Sin datos** | — | — | — | — | no verificado |

## F. Elegibilidad internacional

**República Dominicana: no verificado (Sin datos).** La web oficial respondió 403 y el registro del
laboratorio no trata la elegibilidad por país.

| Campo | Valor | Fuente | Estado |
|---|---|---|---|
| Residentes de RD (lista de países restringidos) | **Sin datos** | — | no verificado |
| KYC | **Sin datos** | — | no verificado |
| Métodos de cobro desde RD | **Sin datos** | — | no verificado |
| Impuestos y formularios (W-8BEN u otros) | **Sin datos** | — | no verificado |

## G. Fuentes

### Leídas

| Dato | URL | Fecha | Confianza | Estado |
|---|---|---|---|---|
| B.1–B.4, C, D y E (filas [LAB]) | registro `NASDAQ_EDGE_INSTITUTIONAL/01_RESEARCH/Prop_Firm_Rules.md §2`, que cita páginas de `apextraderfunding.com/help-center/` (eod-evaluations, eod-drawdown-explained, daily-loss-limit-explained, intraday-trailing-drawdown-evaluations, intraday-trailing-drawdown-explained, scaling-levels-pa-explained, payouts, intraday PA FAQ, prohibited-activities) | 2026-11-25 (laboratorio; **no releído hoy**) | media | parcial |
| Fecha alternativa de la lectura de automatización | `config/prop_economics/firms_futures.yaml` (`prior.consulted_at: 2026-11-19`) | 2026-11-19 | — | needs_verification |

### No leídas hoy

| URL | Código | Hora (UTC) | Nota |
|---|---|---|---|
| https://apextraderfunding.com/ | **403** (Cloudflare "Sorry, you have been blocked", Ray ID a614e6bafdd5f282) | 2026-11-27 23:27:02 | un solo intento con `curl` y el agente por defecto; no se insistió |
| https://apextraderfunding.com/ | 403 | 2026-11-27, antes (sesión principal) | según el encargo |
| Páginas del help center (todas) | no intentadas | — | todo el dominio está bloqueado |

### Para completar la ficha
El operador puede guardar estas páginas desde un navegador (Ctrl+S) en
`docs/futures/research/fuentes/apex/`, o pedir que una sesión con navegador las lea:
1. `help-center/getting-started/prohibited-activities/` y cualquier página sobre bots o automatización,
   para cerrar la duda sobre evaluación frente a PA.
2. Las páginas de evaluación EOD e Intraday, y las de drawdown, DLL, niveles de la PA y payouts. Así se
   releen las filas [LAB] y se obtienen citas literales, reparto, máximo por retiro y paso a Live.
3. Precios de la 50K (lista y promoción), activación, reset, datos y comisiones MNQ/NQ.
4. Términos y condiciones, y la lista de países restringidos (RD), KYC y métodos de pago.
5. La lista de plataformas admitidas.
