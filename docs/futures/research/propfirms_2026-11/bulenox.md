# Bulenox · ficha de reglas de fondeo (investigación 2026-11)

- **ID**: `bulenox` · **Fecha de consulta**: 2026-11-27 · **Cuenta de referencia**: 50K.
- **Programas analizados, cada uno por separado**: **Qualification** (evaluación → Master), **Momentum**
  (evaluación de pago único → Momentum Master gratis) y **Fast Track** (directa a cuenta financiada
  simulada). En los tres hay que elegir un modelo de drawdown, fijo para toda la vida de la cuenta:
  **Option 1 · Trailing** u **Option 2 · End-of-Day (EOD)**.
- **Fuentes leídas**: portada, FAQ (respuestas en el JSON-LD `acceptedAnswer` del HTML), Accounts &
  Pricing, los PDF legales `Terms_of_Use.pdf` («Updated October 2026») y `Bulenox-Rates.pdf` («Updated
  Aug/11/2026»), y dos ficheros JavaScript que sirve la propia web (los datos de las tarjetas de precios
  y los textos de la web).
- **No leído**: el **Help Center** (`/help-center`). Su contenido (reglas detalladas de Master, Fast
  Track, Momentum, Funded, Payment, Warning) se carga en el navegador desde el CMS de la web y no está en
  el HTML. La consulta a ese CMS quedó bloqueada por el control de permisos de esta sesión, no por la
  web. Por eso faltan, entre otros, la **activación del Master**, los **mínimos, máximos y topes del
  payout del Master** y el **% de consistencia del Master y del Fast Track** (Sin datos).
- **Formato de cada dato**: valor · «cita literal» · [B#] (URL y fecha en §G) · confianza · estado. Lo
  que sale de los ficheros JavaScript de la web lleva confianza **media**: es contenido oficial, pero no
  es texto visible en el HTML estático. **(cálculo propio)** marca la aritmética sobre cifras oficiales.

## Resumen (50K)

| Campo | Qualification | Momentum | Fast Track |
|---|---|---|---|
| Precio (pago único) | **$175** (acceso de 30 días) | **$143** (acceso de 30 días) | **$488** |
| Activación del Master | Única; importe **Sin datos** | **$0** (Momentum Master gratis) | No aplica (sin activación) |
| Profit target | $3,000 | $3,000 | No hay (primer objetivo de payout: $3,000) |
| Drawdown | $2,500 | $2,000 | $2,000 |
| Contratos (Trailing / EOD) | 7 / 7 | 7 / 4 | 7 / 4 |
| DLL (solo en EOD) | $1,100 | $1,200 | $1,200 |
| Días mínimos | Ninguno | Ninguno | Ninguno |
| Proceso del payout | Master: **los miércoles** | En el día | En el día |
| Consistencia en la financiada | Master: % **Sin datos** | **35 %** por ciclo y 5 días rentables | % **Sin datos** |
| Reparto | 90/10 | 90/10 | 90/10 |

**Veredicto de automatización: permitida con condiciones, y la documentación se contradice.** La FAQ
permite bots, algoritmos y copiadores hechos por el propio trader para su uso personal; usar la API de
Rithmic por un tercero o un software «composite» cuesta $100 al mes. Los Términos prohíben los
algoritmos de «scalping», el DTC Protocol Bridge API, el «automated discretional trading» y abrir y
cerrar cientos o miles de operaciones rápidas, y exigen que **Bulenox apruebe antes** cualquier
algoritmo o software automático de terceros. Si sospechan abuso, pueden negarse a pagar beneficios.
**NinjaTrader 8: soportado** (socio de plataforma, licencia gratis en el Master). **República
Dominicana: no figura entre los países restringidos** (verificado por ausencia en la lista).

---

## Reglas comunes (la fuente las aplica a todas las cuentas o habla de la web en general)

- **Modelo Trailing (Option 1)**: el límite sigue el máximo, **con posiciones abiertas y en tiempo
  real**, comisiones incluidas, y nunca baja; tamaño completo desde el primer día; sin DLL. «Your loss
  limit follows your highest point — including open positions, in real time.» · «Tracked live during
  the session, commissions included.» [B1], [B3] · alta · verificado. **Dónde se bloquea: Sin datos**
  (Help Center no leído).
- **Modelo EOD (Option 2)**: el límite se mueve una vez al día, al cierre y con lo realizado; durante la
  sesión no se mueve; el tamaño escala con el *Cash On Hand*; el DLL **pausa** el día, no cierra la
  cuenta. «The daily loss limit pauses your trading for the day instead of closing the account.» [B1],
  [B2] · alta · verificado. **La tabla de escalado: Sin datos.** En Fast Track y Momentum, la tarjeta EOD
  dice «Option 2 — no scaling» [B4] · media · parcial.
- **El modelo es irreversible**: «The choice is locked for the life of the account.» [B2] · alta ·
  verificado.
- **Horario y cierre obligatorio**: el día de trading va de 17:00 a 16:00 CT y todo se cierra a las
  **15:59 CT**. «all positions must be closed by 3:59 pm CT.» [B2] · alta · verificado.
- **Overnight y fin de semana**: no, porque hay que cerrar a las 15:59 CT (deducido de [B2]) · alta ·
  verificado.
- **Noticias**: **permitido**, sin ventanas de bloqueo ni cierres forzosos. «No blackout windows, no
  forced position closing, no penalties.» [B2], [B1] · alta · verificado.
- **Micros**: 1 mini = 10 micros, y se pueden mezclar. «1 standard = 10 micros.» [B2], [B3] · alta ·
  verificado.
- **Comisiones (todo incluido: bolsa y compensación)**: NQ **$2.09 por lado / $4.18 ida y vuelta**;
  MNQ **$0.61 por lado / $1.22 ida y vuelta**. Cuentan para el drawdown y el DLL. «Rates are all-in:
  exchange and clearing fees are already included.» · «count toward your drawdown and daily loss
  limit.» [B7] · alta · verificado.
- **Datos de mercado**: si el trader se declara **no profesional** en el acuerdo de Rithmic, $0; si se
  declara profesional, **$116/mes**. La declaración es irreversible para Qualification, Master y Funded.
  «CME, CBOT, NYMEX and COMEX data is billed at $116/month on top of your account.» [B3] · alta ·
  verificado.
- **Reset (Qualification)**: **$78**; el balance vuelve al inicio y la cuenta sigue. «On a
  Qualification account a reset costs $78» [B2] · alta · verificado. Si Momentum y Fast Track tienen
  reset: no lo dice la fuente oficial.
- **Cuentas**: hasta **5** de nivel Master (Master, Fast Track y Momentum Master combinados);
  Qualification sin límite; todas con un único Rithmic User ID. «You can have up to 5 accounts in total
  — Master, Fast Track and Momentum Master in any combination.» [B2], [B3] · alta · verificado.
- **Un perfil por hogar**: «you are the sole authorized Bulenox trader profile holder within your
  household» [B6] · alta · verificado.
- **Payouts (general)**: 90/10; por ACH, wire o PayPal; «No payout processing fees». «The split is 90/10
  in your favour.» · «Payouts are sent by ACH or wire transfer and by PayPal.» [B2], [B1] · alta ·
  verificado.
- **Consistencia (general)**: si no se cumple, no hay rotura; se sigue operando. «If a request does not
  meet it, nothing is violated and your account stays open» [B2] · alta · verificado.
- **Cancelación y reembolso**: las Qualification no se renuevan solas; no hay reembolso una vez usado
  el servicio. «Payments are non-refundable once the service has been used.» [B2] · alta · verificado.
- **Cupón permanente**: `BULENOX`, «this code never expires»; aplica «the best available discount». **El
  porcentaje no se publica: Sin datos** [B3] · alta · parcial.

---

## Programa 1 · Qualification → Master

### A. Costes (50K)
| Concepto | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Precio de lista | **$175**, pago único | «$175one-time» | [B3] | alta · verificado |
| Promoción | Cupón `BULENOX` (descuento Sin datos) | «Always-on coupon» | [B3] | alta · parcial |
| Suscripción o pago único | Pago único; acceso de 30 días; no se renueva | «Access valid for 30 days» | [B3], [B2] | alta · verificado |
| Activación del Master | Única, según el tamaño; **importe Sin datos** | «A Master Account has no monthly fee — only a one-time activation, depending on account size.» | [B2] | alta · parcial |
| Reset | $78 | ver Reglas comunes | [B2] | alta · verificado |
| Datos | $0 (no profesional) / $116/mes (profesional) | ver Reglas comunes | [B3] | alta · verificado |
| Comisiones | NQ $4.18 · MNQ $1.22 ida y vuelta | [B7] | [B7] | alta · verificado |
| API de terceros / composite | $100/mes | «an additional $100 per month applies» | [B2], [B6] | alta · verificado |
| Coste hasta el Master, mejor caso | $175 + activación (**Sin datos**) → **total Sin datos** | — | — | — |
| Mantener el Master 3 / 6 meses | $0 de cuotas; +$300 / +$600 con API de terceros; +$348 / +$696 con datos profesionales (cálculo propio) | «No Monthly Fees on Master Accounts» | [B1] | alta · verificado |

### B. Reglas de trading (Qualification 50K)
| Regla | Valor | Fuente | Confianza · estado |
|---|---|---|---|
| Profit target | $3,000 | [B3] | alta · verificado |
| Drawdown | $2,500 («Drawdown up to» en Trailing; «EOD Drawdown» en EOD) | [B3], [B4] | alta · verificado |
| DLL | Trailing: ninguno («No daily loss limit»). EOD: **$1,100** (pausa) | [B3], [B4] | alta (Trailing) / media (EOD) · verificado / parcial |
| Contratos | 7 (Trailing) · 7 (EOD, escalando con el Cash On Hand) | [B3], [B4] | alta / media · verificado / parcial |
| Consistencia en la evaluación | No lo dice la fuente oficial | — | Sin datos |
| Días mínimos / plazo | Ninguno; el acceso dura 30 días | [B2], [B3] | alta · verificado |
| Escalado (Master) | Sin datos | — | Sin datos |

### C. Payouts (Master 50K)
| Campo | Valor | Fuente | Confianza · estado |
|---|---|---|---|
| Días necesarios, mínimo, máximo, buffer, topes | **Sin datos** (están en el Help Center, no leído) | — | Sin datos |
| Consistencia | Existe; el % del Master está en el Help Center: **Sin datos** | [B2] | alta · parcial |
| Solicitud | Cualquier día de la semana | «You can request a payout any day of the week.» [B2] | alta · verificado |
| Proceso | **Los miércoles** | «on a regular Master Account they are processed every Wednesday.» [B2] | alta · verificado |
| Recepción | Sin datos (plazos de ACH, wire y PayPal no publicados en lo leído) | — | Sin datos |
| Reparto | 90/10 | [B2] | alta · verificado |
| Transición a Funded (Live) | «trade your way to a Funded Account»; condiciones **Sin datos** | [B1] | alta · parcial |

## Programa 2 · Momentum → Momentum Master

### A. Costes (50K)
| Concepto | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Precio de lista | **$143**, pago único | `price: $143` (tarjeta 50K de Momentum) | [B4] | media · parcial |
| Modalidad | Pago único, sin suscripción; acceso de 30 días | «One-time fee, no monthly subscription» | [B5], [B4] | media · parcial |
| Activación del Momentum Master | **$0** | «your Momentum Master has no fee at all: it is activated free of charge.» | [B2] | alta · verificado |
| Coste hasta la primera cuenta que paga, mejor caso | **$143** (cálculo propio; sin cupón; +$100/mes si se usa una API de terceros) | — | [B4], [B2] | media · parcial |
| Mantener 3 / 6 meses | $0 de cuotas (+$300 / +$600 con API de terceros) (cálculo propio) | «No Monthly Fees on Master Accounts» | [B1] | alta · verificado |

### B. Reglas de trading (Momentum 50K)
| Regla | Valor | Fuente | Confianza · estado |
|---|---|---|---|
| Profit target | $3,000 | [B4] | media · parcial |
| Drawdown | $2,000 | [B4] | media · parcial |
| DLL | Solo en EOD: $1,200 | [B4] | media · parcial |
| Contratos | 7 (Trailing) · 4 (EOD) | [B4] | media · parcial |
| Consistencia en la evaluación | Ninguna: «No minimum trading days and no consistency rule at this stage» | [B5] | media · parcial |

### C. Payouts (Momentum Master 50K)
| Campo | Valor | Fuente | Confianza · estado |
|---|---|---|---|
| Días y consistencia | **5 días rentables que cuenten y consistencia del 35 %** por ciclo: «5 qualifying profitable days and 35% consistency per payout cycle» | [B5] | media · parcial |
| Contradicción | La portada dice que en Fast Track y Momentum no hay «minimum number of trading days before your first request». Choca con los 5 días de arriba; el Help Center lo aclararía | [B1], [B5] | media · parcial |
| Beneficio mínimo por día, mínimo, máximo, topes | Sin datos | — | Sin datos |
| Proceso | En el día: «requests are processed the same day» | [B2] | alta · verificado |
| Reparto | 90/10 | [B2] | alta · verificado |

## Programa 3 · Fast Track (directa a financiada simulada)

### A. Costes (50K)
| Concepto | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Precio de lista | **$488**, pago único | `price: $488` (tarjeta 50K de Fast Track) | [B4] | media · parcial |
| Activación y cuotas | Ninguna | «One-time fee — no activation fee, no monthly fee» | [B5] | media · parcial |
| Coste hasta la primera cuenta que paga | **$488** (cálculo propio) | — | [B4] | media · parcial |

### B. Reglas de trading (Fast Track 50K)
| Regla | Valor | Fuente | Confianza · estado |
|---|---|---|---|
| Profit target | No hay; «First payout goal» de $3,000 | [B4], [B2] | media · parcial |
| Drawdown | $2,000 | [B4] | media · parcial |
| DLL | Solo en EOD: $1,200 | [B4] | media · parcial |
| Contratos | 7 (Trailing) · 4 (EOD, «no scaling») | [B4] | media · parcial |

### C. Payouts (Fast Track 50K)
| Campo | Valor | Fuente | Confianza · estado |
|---|---|---|---|
| Primer payout | Objetivo de $3,000; sin mínimo de días | [B4], [B1] | media · parcial |
| Consistencia | % Sin datos (Help Center) | [B2] | alta · parcial |
| Proceso | En el día | [B2] | alta · verificado |
| Transición a Funded | Revisión tras 3 payouts: «After 3 payouts the account is reviewed for a Funded Account.» | [B2] | alta · verificado |
| Mínimo, máximo, topes | Sin datos | — | Sin datos |

## C. Payouts · aspectos comunes
- **Métodos**: ACH, wire y PayPal [B2] · alta · verificado. Cuáles sirven desde RD: no lo dice la
  fuente oficial.
- **Cargos**: «No payout processing fees» [B1] · alta · verificado (lo que cobren el banco o PayPal no
  se publica).
- **KYC**: el registro no exige comprobación de antecedentes: «No background check» [B1]. Qué
  verificación de identidad piden para cobrar o para la cuenta Funded: **no lo dice la fuente oficial**
  en lo leído · Sin datos.
- **Impuestos**: «U.S. citizens receive Form 1099-NEC, while non-U.S. citizens receive Form W-8BEN.»
  Los traders son contratistas independientes [B2] · alta · verificado.

## D. Automatización (crítico)

**Veredicto: permitida con condiciones, y la FAQ y los Términos se contradicen.** Para un bot NinjaScript
propio en NT8 lo prudente es **pedir antes a Bulenox una aprobación por escrito** (los Términos la
exigen para «automated trading software» de terceros, y NT8 es software de terceros) y confirmar si se
paga la cuota de $100/mes.

| Pregunta | Respuesta | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| ¿Bots y estrategias automáticas? | **Sí (FAQ)**, solo herramientas hechas por el propio trader y para uso personal | «Yes. Bots, algorithms and trade copiers are permitted.» · «Only user-built tools intended solely for the account owner's personal use are permitted.» | [B2] | alta · verificado |
| Herramientas comerciales | **Prohibidas**: comerciales, compartidas, alquiladas o distribuidas públicamente | «Commercial, shared, rented or publicly distributed automation tools are not allowed.» | [B2] | alta · verificado |
| Aprobación previa | **Obligatoria (Términos)** para cualquier algoritmo o software automático de terceros, con posibles condiciones extra | «any third-party algorithm, automated trading software, or other third-party trading technology must be reviewed and approved by the Bulenox management team before use.» | [B6] | alta · verificado |
| Prohibiciones de los Términos | Algoritmos de «scalping», DTC Protocol Bridge API y «automated discretional trading» (término ambiguo); abrir y cerrar cientos o miles de operaciones rápidas con algoritmos; operaciones temerarias en mercados agitados | «using "scalping" algorithms, DTC Protocol Bridge API or automated discretional trading in any of the trading environments.» | [B6] | alta · verificado |
| Coste | $100/mes por conectarse a Rithmic con una API de terceros o software composite; pagarlo no aprueba ningún algoritmo | «does not constitute approval of any specific algorithm, strategy, or software.» | [B6], [B2] | alta · verificado |
| ¿NT8 Automated Strategies / NinjaScript? | NT8 está soportado. Si NinjaScript paga los $100/mes o necesita aprobación previa: **no lo dice la fuente oficial de forma explícita**; aplica la regla general de arriba | «NinjaTrader 8 comes with a free licence on the Master Account.» | [B2] | alta (NT8) / baja (NinjaScript) · parcial |
| ¿ATM Strategies? | No lo dice la fuente oficial | — | — | Sin datos |
| ¿Copiadores? | **Sí** (FAQ), con la misma limitación de uso personal | «Bots, algorithms and trade copiers are permitted.» | [B2] | alta · verificado |
| ¿Varias cuentas? | Hasta 5 de nivel Master; Qualification sin límite; un Rithmic User ID; un perfil por hogar | ver Reglas comunes | [B2], [B6] | alta · verificado |
| ¿VPS? | **No lo dice la fuente oficial** (el silencio no es autorización) | — | — | Sin datos |
| Límites de frecuencia / HFT | No hay umbral; prohibido abrir y cerrar «hundreds or thousand of rapid trades» con algoritmos | «Open and close hundreds or thousand of rapid trades by using any trading algorithms.» | [B6] | alta · verificado (umbral: Sin datos) |
| ¿Microscalping (umbral)? | Prohibidos los algoritmos de «scalping»; sin umbral numérico | ídem | [B6] | alta · verificado (umbral: Sin datos) |
| ¿Pueden anular beneficios? | **Sí**, si sospechan abuso; y en perfiles duplicados del mismo hogar | «If abuse is suspected, we reserve the right to refuse to claim any profit.» | [B6] | alta · verificado |
| Soporte | Bulenox no da soporte ni responde de las herramientas | «we cannot provide support or accept responsibility for any issues arising from their use.» | [B2] | alta · verificado |
| Diferencias Qualification / Master / Funded | Los Términos aplican la prohibición «in any of the trading environments»; otras diferencias: Sin datos | [B6] | [B6] | alta · parcial |

## E. Plataformas

| Plataforma | ¿Soportada? | Fuente | Confianza · estado |
|---|---|---|---|
| **Rithmic** (R\|Trader Pro) | **Sí**: proveedor de datos; el alta exige instalar R\|Trader Pro | [B1], [B5] | alta · verificado |
| **NinjaTrader 8** | **Sí**: socio de plataforma; licencia gratis en el Master | [B2], [B5] | alta · verificado |
| Quantower · Sierra Chart · MultiCharts · ATAS | Sí (FAQ) | [B2] | alta · verificado |
| Tradovate | Su logo sale en la lista de plataformas de la portada; cómo conecta: Sin datos | [B5] | baja · parcial |
| Bookmap · MotiveWave · Tiger.Trade · Optimus Flow · Photon Trader · MintCharts · OverCharts · Trade Navigator · QST · Inside Edge · Investor/RT · Medved Trader · QScalp · ScalpTool · TSLab · VolFix | Logos en la lista de plataformas de la portada | [B5] | media · parcial |
| CQG | No lo dice la fuente oficial | — | Sin datos |
| TradingView | No lo dice la fuente oficial | — | Sin datos |
| APIs | API de Rithmic por terceros / composite: $100/mes; DTC Protocol Bridge API prohibida | [B2], [B6] | alta · verificado |
| Conexiones simultáneas | Sin datos («all of your accounts run under one Rithmic User ID») | [B2] | alta · parcial |

## F. Elegibilidad internacional

| Campo | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| **República Dominicana** | **No figura** en la lista de países restringidos (que sí incluye a vecinos del Caribe como Haití, Jamaica, Bahamas, Barbados, Cuba y Trinidad y Tobago). Por la lista oficial, RD es elegible | «we are prohibited from conducting business with residents of certain countries.» | [B2] | **media · verificado por ausencia en la lista** |
| Cautela | La lista puede cambiar; conviene confirmarlo por escrito con soporte antes de comprar | «this list is subject to change at any time, based on updates from brokerages and other regulatory developments.» | [B2] | alta · verificado |
| KYC | Registro sin comprobación de antecedentes; la verificación para cobrar o para la Funded: Sin datos | «No background check» | [B1] | alta · parcial |
| Cobro desde RD | ACH, wire o PayPal; cuáles funcionan desde RD: Sin datos | — | [B2] | alta · parcial |
| Impuestos | W-8BEN para no estadounidenses | ver §C | [B2] | alta · verificado |
| Pago de las compras | Medios aceptados: Sin datos | — | — | Sin datos |

## G. Fuentes

Todas consultadas el **2026-11-27** con `curl` (agente de usuario por defecto) y respuesta HTTP 200.

| # | Dato principal | URL | Fecha | Confianza | Estado |
|---|---|---|---|---|---|
| B1 | Portada: modelos de drawdown, noticias, payouts diarios, sin cuotas en el Master, sin cargos por payout, sin comprobación de antecedentes | https://bulenox.com/ | 2026-11-27 | alta | verificado |
| B2 | FAQ (JSON-LD `acceptedAnswer`): bots, cuentas, payouts, países, plataformas, reset, impuestos | https://bulenox.com/faq | 2026-11-27 | alta | verificado |
| B3 | Accounts & Pricing (HTML): tarjetas de Qualification, datos pro/no pro, cupón | https://bulenox.com/accounts-pricing | 2026-11-27 | alta | verificado |
| B4 | Datos de las tarjetas de precios (Fast Track, Momentum, valores EOD) | https://bulenox.com/assets/AccountsPricing-BYFXn4Zl.js | 2026-11-27 | media | parcial |
| B5 | Textos de la web (cómo funciona Momentum Master, lista de plataformas) | https://bulenox.com/assets/index-B9yR_oWp.js | 2026-11-27 | media | parcial |
| B6 | Términos de uso («Updated October 2026»): «Algorithms and auto trading», perfil por hogar | https://bulenox.com/legal/Terms_of_Use.pdf | 2026-11-27 | alta | verificado |
| B7 | Comisiones («Updated Aug/11/2026») | https://bulenox.com/legal/Bulenox-Rates.pdf | 2026-11-27 | alta | verificado |
| B8 | Help Center (solo se ve «About Us» en el HTML) | https://bulenox.com/help-center | 2026-11-27 | baja | no verificado |

### Páginas que no se pudieron leer
- **Help Center, secciones Qualification, Fast Track, Momentum, Master, Funded, Connection, Payment y
  Warning** (`https://bulenox.com/help-center`, HTTP 200): el contenido se carga en el navegador desde
  el CMS de la web (`/cms/items/help_items`) y no está en el HTML. La petición directa al CMS **la
  bloqueó el control de permisos de esta sesión** (no respondió la web), así que no hay código HTTP.
  Quedan en Sin datos la activación del Master 50K, los mínimos, máximos y topes de payout, el % de
  consistencia del Master y del Fast Track, dónde se bloquea el trailing, la tabla de escalado EOD, el
  KYC de cobro y la transición del Master a Funded.
- Páginas `es/`, `fr/` y `ru/`: no se consultaron (son traducciones de las mismas páginas).

### Aviso de método
- Los Términos de Bulenox ([B6], «Prohibited activities» E y O) prohíben «engaging in any automated use
  of the system, such as using any data mining, robots or similar data gathering and extraction tools»,
  salvo el uso normal de un navegador o buscador. Esta investigación descargó unos 10 recursos públicos
  con `curl`. Que esto sea o no compatible con ese término lo decide el operador. El Help Center que
  falta debería leerse con un navegador real.
