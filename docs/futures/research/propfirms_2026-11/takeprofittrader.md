# Take Profit Trader · ficha 50K (investigación 2026-11)

- **Id:** `takeprofittrader` · **Cuenta de referencia:** 50K · **Fecha de consulta:** 2026-11-27 (UTC).
- **Estado global:** `parcial`. Solo se pudo leer la portada oficial `https://takeprofittrader.com/`
  (HTTP 200). Los números de la tabla de planes (precio, objetivo, drawdown, DLL, contratos, reset)
  **no están en el HTML**: la página muestra `--` y los rellena con JavaScript desde APIs internas que no
  se consultaron. `/terms` respondió **403**. El centro de ayuda oficial enlazado desde la portada vive en
  `takeprofittraderhelp.zendesk.com`, que no está en la lista de hosts permitidos, así que no se intentó.
- **Método:** `curl` con el agente de usuario por defecto. Se leyó el texto visible de la portada y el JSON
  de textos de interfaz incrustado en la misma página (`<script id="ng-state">`, objeto
  `transfer-translate-en`). Es texto oficial servido por la firma, pero no siempre se sabe en qué pantalla
  aparece (portada, panel del usuario o aviso). Por eso su confianza es media o baja.
- **Programas ("Product Paths"):** Intraday, Classic y EOD. Cada uno con tres fases: TEST (evaluación,
  SIM) → PRO (financiada simulada) → PRO+ (cuenta Live). Tamaños listados: 25K, 50K y 150K.
- **Aviso:** el HTML estático muestra "Currently unavailable" en las tres tarjetas de plan. No se puede
  saber si es el estado real o el texto que aparece antes de cargar los datos.

**Fuentes abreviadas** (todas consultadas el 2026-11-27):
- **[H]** = `https://takeprofittrader.com/`, texto visible.
- **[J:clave]** = la misma URL, JSON incrustado `ng-state` → `transfer-translate-en/<clave>`.

## A. Costes (50K)

| Campo | Valor | Cita literal (≤ 25 palabras) | Fuente | Confianza | Estado |
|---|---|---|---|---|---|
| Precio de evaluación (lista) | **Sin datos**: la tarjeta muestra `--/mo` | "-- /mo" | [H] | — | no verificado |
| Precio en promoción | 40 % de descuento y sin activación con el código NOFEE40, en cualquier plan. Precio resultante **Sin datos**; no dice si el descuento es solo para el primer mes | "Get 40% Off + No Activation Fee On Any Plan. Use Code: NOFEE40" | [H] (banner) | alta | parcial |
| Modalidad | suscripción mensual de la cuenta TEST, con renovación automática | "This will stop automatic renewal for this account." | [H] ("/mo"); [J:billing/upcoming/cancel-confirm/message] | media | parcial |
| Activación (PRO) | 130 USD, pago único; sin mensualidades después | "Pay a one time $130 PRO Account setup fee, and ZERO monthly fees after that." | [J:differences-list-tooltipName-6]; [H] "One Time $130 Fee" | alta | parcial |
| Reset de TEST | **Sin datos** (`--`). La FAQ remite a un artículo del help center (no leído) | "all test reset pricing is now aligned to each account size" | [H] "Test Reset Price --"; [J:faq-desc-12] | — | no verificado |
| Reset de PRO | hasta 3 resets; precio **Sin datos** | "We give you the opportunity to reset your PRO Account up to three times." | [J:differences-list-tooltipName-5] | media | parcial |
| Datos de mercado | no lo dice la fuente oficial leída | — | [H] | — | no verificado |
| Comisiones TEST y PRO | 4,50 USD por mini (NQ) y 1,50 USD por micro (MNQ), ida y vuelta | "These are round trip rates based on whether you trade a Mini or a Micro product." | [H] "$4.50/$1.50 RT"; [J:home-page/funded-journey/rows/commissions/tooltip] | alta | parcial |
| Comisiones PRO+ | las del bróker; importe **Sin datos** | "Broker rates" | [H] | alta | parcial |
| Otros cargos | Aparece "*Paid NinjaTrader License Required" sin contexto: no se sabe a qué opción se aplica. API y retiros: no lo dice la fuente oficial leída | "*Paid NinjaTrader License Required" | [J:paid-ninjatrader-license-required] | baja | parcial |
| Coste hasta financiada (mejor caso, 1 intento) | Fórmula: 1 mes de TEST 50K (P) + 130 USD. Con NOFEE40: 0,6·P + 0 USD. **P = Sin datos**, así que el importe es **Sin datos** | — | derivado de [H] | — | parcial |
| Mantener la financiada 3 y 6 meses | 0 USD de cuotas según la firma, más las comisiones por operación | "ZERO monthly fees after that" | [J:differences-list-tooltipName-6] | media | parcial |

Nota: la FAQ dice que un test fallido cuesta "at MOST, $360", pero no da tamaño ni fecha, y el mismo
párrafo cita datos de 2023 ([J:faq-desc-7]). **No se usa.**

## B. Reglas de trading

### B.0 Lo que la fuente presenta como común a las tres rutas

| Campo | Valor | Cita literal | Fuente | Confianza | Estado |
|---|---|---|---|---|---|
| Profit target 50K | importe **Sin datos** (`--`). La firma dice que el objetivo es el mismo en las tres rutas | "Same profit targets" | [H] | alta (igualdad) | parcial / importe no verificado |
| Drawdown 50K (importe) | **Sin datos** | "Drawdown Amount --" | [H] | — | no verificado |
| Fin del trailing | en las tres fases deja de subir al llegar al balance inicial | "The drawdown across all three account types will STOP trailing once it has reached the initial account balance." | [J:home-page/funded-journey/rows/drawdown/tooltip] | alta | parcial |
| Días mínimos de TEST | 3 | "Days to Pass Test 3" | [H] (las tres tarjetas) | alta | parcial |
| Consistencia en TEST | mejor día ≤ 50 % del beneficio total | "Your biggest trading day cannot be more than 50% of your total profit." | [J:home-page/funded-journey/rows/consistency-rule/tooltip]; [H] "Consistency Rule in Test Yes" | alta | parcial |
| Consistencia en PRO y PRO+ | ninguna | "No funded consistency rule" | [H] | alta | parcial |
| Contratos máximos 50K | minis y micros **Sin datos** (`--`). La capacidad es la misma en TEST y PRO | "you get the exact same buying power in your PRO Account that you had in your test account" | [H] "Max Mini Contracts --"; [J:differences-list-tooltipName-4] | alta (regla) | parcial / cifra no verificada |
| Equivalencia de micros | **Sin datos**: la tarjeta tiene dos campos separados, los dos vacíos | — | [H] | — | no verificado |
| Regla de las 17:00 ("5PM Rule") | se aplica en las tres rutas. Texto del panel: no mantener posiciones abiertas después de las 17:00 EST | "Don't hold open positions past 17:00 EST" | [H] "5PM Rule Yes"; [J:rules-open-positions] | media | parcial |
| Cierre con CQG | los avisos de infracción de CQG dicen: sin posiciones después de las 16:55 ET y sin aperturas entre las 16:55 y las 17:00 ET. Puede chocar con la regla general de las 17:00 | "Don’t try to open positions between 16:55 - 17:00 ET" | [J:cqg-violation/notification/rule/prohibited-trade-detected] y […/no-position-after-close] | media | parcial · **discrepancia** potencial |
| Noticias | En TEST se puede operar. En PRO y PRO+ hay que estar plano y sin órdenes desde 1 minuto antes hasta 1 minuto después de una noticia mayor. La lista de noticias está en el help center (no leído) | "must be out of all positions, and have no open orders, one minute before, during, and after the major news event" | [J:home-page/funded-journey/rows/news-rule/tooltip] | media | parcial |
| Overnight y fin de semana | La regla de las 17:00 impide mantener posiciones después del cierre diario. El fin de semana no se trata por separado: no lo dice la fuente oficial leída | — | [J:rules-open-positions] | media | parcial |
| Escalado | ninguno | "No scaling plan" | [H] | alta | parcial |
| Posiciones contrarias | prohibidas entre cuentas | "Counter positions is when you hold opposing positions in the same, or similar products, across multiple accounts." | [H] "Counter Positions Rule Yes"; [J:no-counter-positions-description] | alta | parcial |
| Regla de 50 ejecuciones | existe en el panel; el detalle es **Sin datos** | "Don't break 50 executions rule" | [J:rules-executions-rule] | baja | parcial |
| Cooldown | Si se alcanza un límite de pérdida ajustada acumulada (importe **Sin datos**), hay 30 días de cooldown. Durante ese tiempo no se pueden comprar ni resetear TEST, activar PRO o PRO+ ni resetear PRO. Se puede seguir operando | "Reaching the ${{limit}} rolling adjusted loss limit … triggers a 30-day Cooldown period" | [J:cooldown/threshold/description] | media | parcial |
| Límite de beneficio diario en PRO | el campo existe en la tarjeta; valor **Sin datos** (`--`) | "Daily Profit Limit in PRO --" | [H] | — | no verificado |
| Productos | futuros de CME, COMEX, NYMEX y CBOT | "exclusively listed on esteemed exchanges, including CME, COMEX, NYMEX, and CBOT" | [H] (disclaimer) | alta | parcial |
| Entorno | TEST y PRO son SIM; PRO+ es Live | "Yes, all PRO accounts are simulated (SIM)." | [H] (FAQ) | alta | parcial |

### B.1 Ruta Intraday (50K)

| Fase | Drawdown | DLL | Cita literal | Fuente | Confianza | Estado |
|---|---|---|---|---|---|---|
| TEST, PRO y PRO+ | Intradía: sigue en tiempo real el P&L no realizado. Deja de subir al llegar al balance inicial | ninguno | "On the Intraday path, the drawdown is intraday on test, PRO, and PRO+ accounts, meaning it trails your unrealized profit in real time." | [J:home-page/funded-journey-product-path/tooltips/intraday/drawdown] y […/intraday/daily-loss-rule] | alta | parcial |

Descripción oficial de la ruta: "For traders who manage risk well and want the lowest cost of entry." [H]

### B.2 Ruta Classic (50K)

| Fase | Drawdown | DLL | Cita literal | Fuente | Confianza | Estado |
|---|---|---|---|---|---|---|
| TEST | EOD: se actualiza al cierre (17:00 EST) | ninguno | "the drawdown is End Of Day on test accounts, meaning it updates at the end of the trading day (5PM EST)" | [J:…/tooltips/classic/drawdown] | alta | parcial |
| PRO | Intradía: sigue el P&L no realizado en tiempo real | ninguno | "On the PRO accounts, the drawdown is intraday, meaning it trails your unrealized profit in real time." | ídem | alta | parcial |
| PRO+ | EOD | ninguno | "There is no daily loss limit on the Classic path for test, PRO, and PRO+ accounts." | [J:…/tooltips/classic/daily-loss-rule] | alta | parcial |

En la tarjeta aparece como "Drawdown Type Mixed" [H]. La fuente no dice si en las fases EOD se vigila
el umbral con el P&L no realizado durante la sesión.

### B.3 Ruta EOD (50K)

| Campo | Valor | Cita literal | Fuente | Confianza | Estado |
|---|---|---|---|---|---|
| Drawdown | EOD en TEST, PRO y PRO+; se actualiza a las 17:00 EST. La fuente no dice si se vigila con el P&L no realizado durante la sesión | "On the EOD path, the drawdown is End Of Day on test, PRO, and PRO+ accounts" | [J:…/tooltips/eod/drawdown] | alta | parcial |
| DLL (importe) | **Sin datos** (`--`) | "Daily Loss Limit --" | [H] | — | no verificado |
| DLL (efecto) | Incluye el P&L realizado y el no realizado. Si se toca con el balance igual o por encima del inicial, se pausa el día (soft breach) y se puede volver a operar tras el reset de las 18:00 ET. Por debajo del inicial, se cierra la cuenta (hard breach) | "If you hit the limit with your balance at or above the starting balance, trading stops for the day." · "Below the starting balance, your account is closed." | [J:…/tooltips/eod/daily-loss-rule]; [J:rules-daily-loss-limit-soft-breach-tooltip] | alta | parcial |
| Discrepancia | El tooltip genérico dice que tocar el DLL liquida la cuenta de inmediato. El de la ruta EOD distingue entre pausa y cierre. Se toma el de la ruta, que es más específico | "If you breach the daily loss limit, it will liquidate your account immediately." | [J:home-page/funded-journey/rows/daily-loss-rule/tooltip] | media | **discrepancia** |

Descripción oficial: "For traders who want end-of-day flexibility and a fixed daily loss limit." [H]

Otra discrepancia: un texto antiguo de la portada atribuye drawdown EOD a todo PRO+ ("You’ll enjoy EOD
drawdown" [J:about-trading-text-5]). La FAQ actual dice que PRO+ Intraday usa drawdown intradía
([J:faq-desc-6]). Se toma la FAQ.

## C. Payouts

Común a las tres rutas, salvo que se indique otra cosa.

| Campo | Valor | Cita literal | Fuente | Confianza | Estado |
|---|---|---|---|---|---|
| Días necesarios | 0: se puede retirar desde el primer día en PRO | "You can initiate withdrawals from your PRO account on the first day" | [H] (FAQ); [H] "Minimum Days Until First Withdrawal 0 Days" | alta | parcial |
| Beneficio mínimo por día | no hay mínimo de días ganadores | "No minimum amount of profitable days you need to trade" | [H] | alta | parcial |
| Frecuencia y número máximo de retiros | diaria; sin límite de retiros | "True daily payouts" · "No withdrawal limits" | [H] | alta | parcial |
| Mínimo por retiro | **Sin datos**: el panel valida "Amount must be greater than '{{value}}'" sin dar la cifra | — | [J:amount-must-be-greater-than] | — | no verificado |
| Máximo por retiro | sin máximo | "there is NO maximum withdrawal amount at TakeProfit." | [J:home-page/funded-journey/rows/max-withdrawal-amount/tooltip] | alta | parcial |
| Límite diario de retiro | el panel tiene un aviso "Daily Limit Reached" sin cifra: **Sin datos** | "Daily Limit Reached" | [J:withdraw-sub-modal/error/daily-limit-reached/title] | baja | parcial |
| Reparto | PRO 80/20; PRO+ 90/10 | "In the PRO accounts you keep 80% of your profits above the buffer and 90% in PRO+ accounts." | [J:home-page/funded-journey/rows/profit-split/tooltip] | alta | parcial |
| Buffer | En PRO es igual al drawdown máximo, y solo se retira lo que está por encima. En PRO+ no hay buffer. Lo que queda dentro del buffer se puede retirar de una PRO deshabilitada al día siguiente de la liquidación | "Buffer zone is equal to your maximum drawdown amount." | [J:home-page/funded-journey/rows/buffer-requirement/tooltip]; [J:you-will-be-able-to-withdraw-profits] | alta | parcial |
| Topes acumulados | la firma dice que no hay máximo; no menciona topes acumulados | — | [H] | media | parcial |
| Solicitado | Automático desde el panel. No debe haber posiciones ni órdenes abiertas: si las hay, la solicitud se rechaza | "please ensure your trading account has no open positions or working orders before confirming." | [J:withdraw-sub-modal/withdrawal-note] | media | parcial |
| Aprobado | la solicitud se aprueba; el plazo es **Sin datos** | "Once your automated withdrawal request is approved" | [J:differences-list-tooltipName-3] | media | parcial |
| Procesado y recibido | Plaid: "within minutes". FAQ: "typically within one business day". Panel: unos minutos y hasta 48 h. Transferencia internacional: 1 a 5 días hábiles | "Processing usually takes a few minutes, but can take up to 48 hours depending on your bank." | [J:differences-list-tooltipName-3]; [H] (FAQ); [J:success-withdraw/general/description-2]; [J:success-withdraw/routable/description-2] | media | parcial |
| Métodos | Plaid a bancos de EE. UU. Internacional: PayPal o Wise. El panel también ofrece "International bank transfer" | "For international withdrawals, you have the option to select either PayPal or Wise." | [J:differences-list-tooltipName-3]; [J:routable/international-bank-transfer] | alta | parcial |
| KYC | Obligatorio. La cuenta bancaria debe estar a nombre del titular. Hay que firmar un formulario fiscal antes de cobrar | "To complete your withdrawal, you need to sign the required tax form." · "Payouts to third-party accounts will be rejected." | [J:please-complete-a-KYC]; [J:comply/to-complete-your-withdrawal]; [J:routable-match-identity-verification/description-2] | media | parcial |
| Transición a Live | PRO+ es Live, con Tradovate o AMP Futures. Los requisitos para pasar de PRO a PRO+ son **Sin datos** | "Elevate your experience by upgrading to PRO+." · "Tradovate or AMP Futures for PRO+ account" | [H]; [J:tradovate-or-amp] | media | parcial |

## D. Automatización (crítico)

**Veredicto: prohibida** (lectura conservadora). La única fuente oficial leída es texto incrustado en la
portada. No se pudo leer ni el reglamento ni el help center.

- Encabezado: **"No trading bots"** [J:no-trading-bots].
- Texto: **"We are looking for discretionary traders, not automated trading robots. Any account traded
  using trading algos/automated trading systems on very short time frames (seconds) will be considered
  unsuccessful."** [J:we-are-looking].
- La segunda frase solo nombra "very short time frames (seconds)". El encabezado, en cambio, es general.
  El silencio no es permiso: **no se asume** que un bot en marcos de tiempo más largos esté permitido.
- No se sabe en qué pantalla se muestra el texto. Sus claves vecinas son resúmenes de reglas del TEST
  ("Be consistent", "Trade for a minimum of 3 trading days"). Confianza **media**; estado `parcial`.
- Pista previa del laboratorio (no es evidencia): `config/propfund/firms.yaml` (2026-11-19, fuente
  secundaria) anota "Universal Trading Policies #1: no se permiten bots ni algoritmos (Test, PRO, PRO+)".
  Coincide con lo leído hoy.

| Campo | Valor | Cita literal | Fuente | Confianza | Estado |
|---|---|---|---|---|---|
| Bots y estrategias automáticas | prohibidos | "No trading bots" | [J:no-trading-bots] | media | parcial |
| NinjaTrader 8 Automated Strategies / NinjaScript | la fuente no las nombra; quedan cubiertas por "No trading bots": se tratan como **prohibidas** | — | [J:we-are-looking] | media | parcial |
| ATM Strategies | no lo dice la fuente oficial leída | — | — | — | no verificado |
| Copiadores de operaciones | permitidos en las tres rutas; no se leyeron condiciones. Siguen prohibidas las posiciones contrarias entre cuentas | "Copy Trading Allowed" | [H] (las tres tarjetas) | alta | parcial |
| Varias cuentas | Hasta 5 financiadas (PRO y PRO+) a la vez. TEST ilimitadas, con un máximo de 10 activaciones de TEST cada 30 días | "You can trade up to five funded accounts while continuing to trade Test accounts alongside them." · "limit of 10 test activations per 30 days" | [H] (FAQ); [J:in-queue-limit-test]; [J:youve-reached-the] | alta | parcial |
| VPS | No admite el **registro** desde VPN, VPS o proxy. Si se puede operar desde un VPS: no lo dice la fuente oficial leída | "We don't support registrations over VPN, VPS, or Proxy." | [J:we-dont-support-registrations] | media | parcial |
| Límites de frecuencia | "50 executions rule"; detalle **Sin datos** | "Don't break 50 executions rule" | [J:rules-executions-rule] | baja | parcial |
| HFT | Algoritmos en marcos de segundos hacen que la cuenta se considere "unsuccessful". El HFT no se nombra | "on very short time frames (seconds) will be considered unsuccessful" | [J:we-are-looking] | media | parcial |
| Microscalping (umbral) | sin umbral numérico; solo dice "seconds" | — | [J:we-are-looking] | baja | parcial |
| Técnicas de ejecución prohibidas | posiciones contrarias entre cuentas; operar noticias en PRO y PRO+ | ver B.0 | [J:no-counter-positions-description] | alta | parcial |
| ¿Pueden anular beneficios? | La cuenta "will be considered unsuccessful". No dice si se anulan payouts ya cobrados | — | [J:we-are-looking] | media | parcial |
| Diferencias TEST / PRO / PRO+ | el texto leído no distingue fases | — | — | — | no verificado |

## E. Plataformas

| Campo | Valor | Cita literal | Fuente | Confianza | Estado |
|---|---|---|---|---|---|
| Número de plataformas | "15+". La lista se carga con JavaScript: **Sin datos** | "Connect to any of our 15+ available trading platforms and get started today." | [H] | alta | parcial |
| Rithmic | sí, como data feed | "Rithmic Data Feed" | [H] | alta | parcial |
| CQG | sí, como data feed; en el panel aparece "CQG (Beta)". Mantenimiento: 16:05–16:30 CT entre semana y desde el viernes 18:05 hasta el domingo 9:00 CT | "CQG Data Feed" | [H]; [J:cqg-beta]; [J:cqg-weekdays] | alta | parcial |
| NinjaTrader 8 | Figura como tipo de plataforma. También aparece "*Paid NinjaTrader License Required", sin contexto | "*Paid NinjaTrader License Required" | [J:platform-type/1]; [J:paid-ninjatrader-license-required] | media | parcial |
| Tradovate | proveedor de SIM según la FAQ; bróker de PRO+ | "Take Profit uses Tradovate as its regulated broker for live (PRO+) accounts." | [H] (FAQ) | alta | parcial |
| AMP Futures | alternativa para PRO+ | "PRO+ live market account powered by AMP Futures" | [J:pro-live-amp] | media | parcial |
| TradingView · Quantower · Sierra Chart · Bookmap · ATAS | no lo dice la fuente oficial leída | — | — | — | no verificado |
| APIs | no lo dice la fuente oficial leída | — | — | — | no verificado |
| Conexiones simultáneas | no lo dice la fuente oficial leída | — | — | — | no verificado |

## F. Elegibilidad internacional

**República Dominicana: no verificado.** En lo leído no hay lista de países. `/terms` respondió 403.

| Campo | Valor | Cita literal | Fuente | Confianza | Estado |
|---|---|---|---|---|---|
| Residentes de RD | **Sin datos**. Hay indicios de que algunos países quedan fuera de la verificación, pero la lista no se pudo leer | "Verification is not available for this country." | [J:error/validation/change-personal-info/country/pattern] | baja | no verificado |
| KYC | obligatorio antes de continuar | "Please complete a KYC procedure before continuing with your trading journey." | [J:please-complete-a-KYC] | media | parcial |
| Métodos de cobro desde RD | Para retiros internacionales: PayPal o Wise. No dice si están disponibles para RD | "For international withdrawals, you have the option to select either PayPal or Wise." | [J:differences-list-tooltipName-3] | media | parcial |
| Formularios fiscales | Hay que firmar un formulario fiscal. El formulario distingue entre ciudadano o residente de EE. UU. y quien no lo es. No nombra el W-8BEN | "I am not a U.S. citizen or resident alien" | [J:i-am-not-a-USA-citizen-or-resident-alien]; [J:comply/sign-tax-form] | media | parcial |
| Cobro como empresa | KYB solo para residentes y empresas de EE. UU. | "KYB verification is available only for U.S. residents and U.S. registered companies" | [J:kyb-flow/access-restricted-heading] | media | parcial |

Un testimonio de la portada es de un trader marroquí. **No** es evidencia de que se acepte a residentes de RD.

## G. Fuentes

### Leídas

| Dato | URL | Fecha | HTTP | Confianza | Estado |
|---|---|---|---|---|---|
| Portada: texto visible, tarjetas de plan (sin cifras), tabla "Funded Journey", FAQ, disclaimers | https://takeprofittrader.com/ | 2026-11-27, ~23:15 UTC (descarga de la sesión principal) | 200 | alta | parcial |
| JSON de textos de interfaz incrustado en la portada (`ng-state` → `transfer-translate-en`): tooltips, reglas del panel, automatización, KYC, cobros | https://takeprofittrader.com/ | 2026-11-27 | 200 | media | parcial |
| Bundle de arranque: no tiene datos de planes. Muestra que los valores salen de APIs internas (`/store/api/`, `/cms/api/`), que no se consultaron | https://takeprofittrader.com/main-FOCEQK4J.js | 2026-11-27 23:26:22 UTC | 200 | — | — |

### No leídas

| URL | Código | Hora (UTC) | Nota |
|---|---|---|---|
| https://takeprofittrader.com/terms | **403** (Cloudflare "Sorry, you have been blocked", Ray ID a614d63a18d54c80) | 2026-11-27 ~23:15 (sesión principal) | no se reintentó |
| https://help.takeprofittrader.com/ | **404** (nginx) | 2026-11-27 23:26:22 | el host no aloja el help center |
| https://takeprofittraderhelp.zendesk.com/hc/en-us/articles/15170316538013-Rule-6-Be-Consistent | no intentado | — | host fuera de la lista permitida |
| https://takeprofittraderhelp.zendesk.com/hc/en-us/articles/15171769361053-Are-the-rules-the-same (lista de noticias) | no intentado | — | ídem |
| https://takeprofittraderhelp.zendesk.com/hc/en-us/articles/15172219527581-PRO-Account-Profit-Split-Withdrawal-Rules | no intentado | — | ídem |
| https://takeprofittraderhelp.zendesk.com/hc/en-us/articles/15140989806493-Resetting-Your-Test-Account | no intentado | — | ídem |
| https://takeprofittraderhelp.zendesk.com/hc/en-us/articles/40739474201501-Classic-vs-EOD-vs-Intraday-Which-Plan-Is-Right-for-You | no intentado | — | ídem |
| APIs internas de planes (`/store/api/`, `/cms/api/`) | no intentado | — | no son páginas públicas de reglas |

### Para completar la ficha
1. **Tabla de planes 50K** de las tres rutas, renderizada en un navegador: precio, objetivo, drawdown,
   DLL, contratos mini/micro, reset y "Daily Profit Limit in PRO". Vale la página guardada (Ctrl+S)
   después de cargar o una captura.
2. **`/terms`** guardado desde el navegador: países restringidos, reglas de conducta y automatización.
3. Los **5 artículos del help center** listados arriba, más los de automatización ("Universal Trading
   Policies"), la regla de 50 ejecuciones, el Cooldown, los países admitidos y PRO → PRO+. Otra opción:
   que el operador apruebe el host oficial `takeprofittraderhelp.zendesk.com` en la red del entorno.
