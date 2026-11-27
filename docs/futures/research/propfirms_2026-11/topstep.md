# Topstep · ficha de reglas de fondeo (investigación 2026-11)

- **ID**: `topstep` · **Fecha de consulta**: 2026-11-27 · **Cuenta de referencia**: 50K.
- **Programa analizado**: Trading Combine® 50K (dos vías de precio: *Standard* y *No Activation Fee*)
  → Express Funded Account® (XFA, dos vías de payout: *Standard* y *Consistency*) → Live Funded
  Account® (LFA). Los programas *Static*, *Labs* y *Challenges* aparecen en el help center, pero quedan
  fuera de alcance y **no** se usan para deducir reglas del Combine estándar.
- **Fuentes**: help center oficial `help.topstep.com/en/` (31 artículos) y los Términos de uso de
  `www.topstep.com/terms-of-use/` («Last updated: November 4, 2026»). Se reutiliza §1 de
  `docs/futures/research/prop_firms_2026-11-27.md` (verificado hoy) y se completan los campos que allí
  faltaban.
- **Formato de cada dato**: valor · «cita literal» · [S#] (URL exacta y fecha en §G) · confianza ·
  estado. Todo se consultó el 2026-11-27. Lo que es aritmética sobre cifras oficiales se marca
  **(cálculo propio)**.

## Resumen (50K)

| Campo | Valor |
|---|---|
| **Automatización** | **Permitida con condiciones, solo por la API de TopstepX/ProjectX**: bot propio, sin HFT, sin explotar el SIM, sin VPS, VPN ni servidores remotos que envíen órdenes, y con las órdenes saliendo del dispositivo personal del trader |
| **NinjaTrader 8 / NinjaScript** | **No soportado**: «TopstepX™ is the only available trading platform.» Quantower solo entra conectado a TopstepX (Combine y XFA), sin Strategy Manager ni Strategy Runner |
| **República Dominicana** | **Elegible según la lista oficial** (no figura entre los países no elegibles ni entre los «solo XFA»; lista actualizada el 17-11-2026). Estado: verificado (por ausencia en una lista cerrada) · confianza media |
| Coste hasta la primera XFA, mejor caso | **$95** (vía No Activation Fee) · $85 con DLL añadido al comprar · $198 en la vía Standard ($49 + $149) |
| Reparto / mínimo / máximo | 90/10 · $125 · 50 % del balance hasta **$2,000** (Standard) o **$3,000** (Consistency); el doble con DLL al comprar (oferta temporal) |
| Comisiones ida y vuelta | NQ **$3.78** · MNQ **$1.22** |
| Payout internacional | Transferencia (wire), 5–10 días hábiles, $30; aprobación interna de 1–3 días hábiles; Wise no disponible en nov-2026 |

---

## A. Costes (50K)

| Concepto | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Precio de lista, vía Standard | **$49/mes** | «50K · $49/month · $95/month» | [S7] | alta · verificado |
| Precio de lista, vía No Activation Fee | **$95/mes** | ídem | [S7] | alta · verificado |
| Modalidad | Suscripción mensual; se renueva cada 30 días hasta aprobar o cancelar; sin plazo para aprobar | «It Rebills every 30 days from your original sign-up date.» | [S22] | alta · verificado |
| Cambio de vía | No se puede cambiar después de comprar | «Paths cannot be changed after purchase.» | [S7] | alta · verificado |
| Activación de la XFA | Standard: **$149** una vez por XFA · No Activation Fee: $0 | «$149 Activation Fee charged once per Express Funded Account (XFA) earned.» | [S7], [S23] | alta · verificado |
| Reset | Igual que la mensualidad: $49 (Standard) / $95 (No Activation Fee); máximo 2 resets por cuenta y día | «2 Resets per account per calendar day» | [S7], [S29] | alta · verificado |
| Descuento por DLL al comprar | −$10/mes en el Combine 50K No Activation Fee; −$50 en la reactivación Back2Funded | «$10 off → 50K» · «Discount recurs monthly.» | [S7], [S25] | alta · verificado |
| Promociones (aparte del precio de lista) | Código de referido: 15 % en la primera compra (50 % del 16-11 a fin de noviembre de 2026, «Friendsgiving»); código de afiliado: 20 % en una compra elegible; sin acumular | «your Referral Code will offer 50% off (up from the standard 15%)!» | [S7] | alta · verificado (promoción temporal) |
| Datos de mercado | L1 incluido en Combine y XFA; L2 (DOM) **$38/mes**, sin prorrateo | «Level 2 (Depth of Market) is available as an upgrade for $38/month.» | [S24], [S7] | alta · verificado |
| Comisiones (Combine, XFA y LFA en TopstepX) | NQ **$3.78** ida y vuelta · MNQ **$1.22** ida y vuelta (incluyen bolsa, NFA $0.02 y comisión: minis $1.00, micros $0.50) | «E-mini NASDAQ 100 (NQ) · $3.78» · «Micro E-mini NASDAQ 100 (MNQ) · $1.22» | [S12] | alta · verificado |
| Discrepancia de comisiones | El artículo de costes de la LFA habla de «$3.70/lot simulated fee» en el Combine y de NQ $3.80 en Live. Prevalece la tabla de [S12], más detallada | «a $3.70/lot simulated fee is charged to emulate these real-world costs» | [S13] | media · parcial |
| API (necesaria para automatizar) | **$29/mes**; **$14.50/mes** con el código `topstep`, sin fecha de fin; se factura aparte (ProjectX) | «API Access is $29/month. Topstep Traders get 50% off with code topstep — that's $14.50/month» | [S9] | alta · verificado |
| Cargo por retiro | ACH $30 (solo EE. UU.), wire $30 (internacional); Aeropay y Prop-to-Brokerage sin cargo de Topstep (solo EE. UU.) | tabla «Payout Methods» | [S6] | alta · verificado |
| Plataforma | Combine y XFA: Topstep cubre la plataforma; LFA: licencia a cargo del trader | «In the Live Funded Account®, you are responsible for your own platform license cost.» | [S13] | alta · verificado |
| Impuestos indirectos | IVA o impuesto sobre ventas según el país, calculado al pagar | «applicable taxes — VAT, GST, or sales tax — will be calculated and shown at checkout» | [S7] | alta · verificado |
| Medios de pago (compras) | Visa, Mastercard, American Express, Discover, Google Wallet, Apple Pay; **no PayPal**; la tarjeta tiene que estar a nombre del trader | «PayPal is not supported.» | [S7], [S22] | alta · verificado |
| Reembolso | Garantía de 14 días solo en el primer Combine, si no se ha aprobado | «14-Day "I Get It" Guarantee» | [S28] | alta · verificado |

**Coste hasta tener una XFA, mejor caso: 1 intento, aprobado en el primer ciclo de 30 días (mínimo 2
días operados)** (cálculo propio):

| Vía | Discrecional | Con automatización (API con código) |
|---|---|---|
| No Activation Fee | **$95** ($85 si se añade DLL al comprar) | $109.50 ($99.50 con DLL) |
| Standard | **$198** ($49 + $149) | $212.50 |

Sin impuestos ni promociones. Sumar $38 si hace falta L2 (DOM).

**Mantener la XFA** (cálculo propio): la XFA no tiene mensualidad («No monthly subscription fee after
passing.» [S4]). Coste base a 3 y 6 meses: **$0**. Con API: $43.50 y $87. Con L2: +$114 y +$228. Si no
se opera en 30 días, la XFA puede cerrarse [S4].

## B. Reglas de trading (50K)

| Regla | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Profit target (Combine) | **$3,000** | «Profit Target · $3,000» | [S1] | alta · verificado |
| Drawdown máximo (MLL) | **$2,000** | «Maximum Loss Limit · $2,000» | [S1], [S2] | alta · verificado |
| Tipo de MLL (Combine) | Trailing con el balance **de cierre del día**; se bloquea al llegar al balance inicial ($50,000); se vigila **en tiempo real, con P&L no realizado** | «Rises as your end-of-day balance grows. Never moves down. Locks permanently once it reaches your starting balance.» | [S2] | alta · verificado |
| Rotura del MLL | Liquidación inmediata; cuenta no elegible hasta un reset | «including on unrealized P&L, your account is liquidated immediately» | [S2] | alta · verificado |
| MLL en la XFA | El balance empieza en $0; el MLL empieza en −$2,000, sube y se fija en $0 al llegar a +$2,000; tras el primer payout queda en $0 | «Once your balance reaches $2,000, the MLL locks at $0 permanently.» | [S2] | alta · verificado |
| DLL | Opcional al comprar: **$1,000**. Es una **pausa**, no una rotura: aplana y bloquea hasta las 17:00 CT. Es fijo y pasa a la XFA. En la LFA es automático ($2,000 en 50K) | «Triggering it is not a rule violation — it's a forced break for the rest of that session.» | [S25], [S10] | alta · verificado |
| Consistencia (Combine) | Mejor día < 55 % del objetivo (< $1,650); si se supera, el objetivo sube (mejor día ÷ 0,55) | «A $2,200 best day raises it to $4,000.» | [S1] | alta · verificado |
| Consistencia (XFA) | Vía Standard: ninguna. Vía Consistency: mejor día ≤ 40 % del beneficio neto del ciclo | «Consistency = Largest Winning Day ÷ Total Net Profit» | [S4] | alta · verificado |
| Contratos máximos | Combine: 5 minis / 50 micros (1 mini = 10 micros). XFA: según el Scaling Plan | «Minis and micros share the same limit at a 10:1 ratio.» | [S1], [S5] | alta · verificado |
| Días mínimos / plazo | 2 días · sin plazo | «Minimum trading days · 2» · «Time limit to pass · None» | [S1] | alta · verificado |
| Cierre obligatorio | Todo cerrado a las 15:10 CT; no abrir posiciones después de las 15:08 CT; reapertura a las 17:00 CT. Day trading solamente | «All positions must be closed by 3:10 PM CT every weekday.» | [S11], [S30] | alta · verificado |
| Overnight y fin de semana | **No** («No swing trading.»); el viernes cierra a las 15:10 CT y reabre el domingo a las 17:00 CT | «No swing trading. No Forex.» | [S11] | alta · verificado |
| Noticias (Tier 1: CPI, FOMC, NFP, PPI) | Ventana de 10 min (±5 min): minis de índices **sin nuevas aperturas**; MNQ y demás micros limitados a **3** en Combine 50K; en la XFA 50K, 1 o 3 micros según el balance. Las posiciones abiertas antes se pueden gestionar | «Minis (ES, RTY, YM, NQ, NKD, GC, SI, HG, PL): No new opening transactions permitted during the 10-minute window» | [S8] | alta · verificado |
| Noticias (conducta) | Prohibido entrar con el tamaño máximo de forma deliberada en una noticia importante programada | «Purposefully trading your full Maximum Position Size directly into a scheduled major news event.» | [S16] | alta · verificado |
| Volatilidad extrema | Topstep puede recortar límites de posición de forma temporal | «we may temporarily tighten position limits on affected products» | [S8] | alta · verificado |
| Escalado (XFA) | Por balance; no sube dentro de la sesión. **La tabla general es una imagen: Sin datos.** Lo que sí se lee, en margen: 50K XFA < $1,500 → $20,000; $1,500–$2,000 → $30,000; > $2,000 → $50,000 | «Your max contracts do not increase mid-session.» | [S5], [S8] | media · parcial |

## C. Payouts (XFA 50K, salvo que se indique)

| Campo | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Días necesarios | Vía Standard: 5 días ganadores de ≥ $150 netos (no consecutivos). Vía Consistency: 3 días con al menos 1 operación y consistencia ≤ 40 % | «5 winning days of $150+ Net P&L. Days don't need to be consecutive.» | [S6] | alta · verificado |
| Beneficio mínimo por día | $150 netos (vía Standard); el día se cierra a las 16:00 CT | «A day locks in at 4:00 PM CT.» | [S6] | alta · verificado |
| Condición adicional | Beneficio > $0 desde el último payout (el primero está exento); el día de la solicitud no cuenta para el ciclo siguiente | «You must have earned at least $0.01 since your last Payout.» | [S6] | alta · verificado |
| Número máximo de retiros | La fuente oficial no lo dice para la XFA. En países «solo XFA», tope total de $200,000 (no afecta a RD) | «take up to $200,000 in total payouts» | [S14] | media · parcial |
| Mínimo | **$125** | «Minimum Payout: $125» | [S6] | alta · verificado |
| Máximo por retiro | 50 % del balance hasta **$2,000** (Standard) / **$3,000** (Consistency); con DLL añadido al comprar un Combine nuevo, **$4,000 / $6,000** (oferta temporal desde el 2 de junio, sin fecha de fin) | «Max Payout per request: 50% of your account balance up to the cap below.» | [S6] | alta · verificado |
| Errata en la fuente | La tabla de vías dice «up to $5000*» / «$6,000*»; esos son los topes de 150K, y la tabla por tamaño fija los de 50K | — | [S6], [S4] | alta · verificado |
| Reparto | **90/10** (quienes se unieron al dashboard nuevo antes del 12-01-2026: 100 % de los primeros $10,000) | «90/10 profit split — you keep 90%» | [S6] | alta · verificado |
| Buffer | No hay buffer obligatorio. Recomendación: esperar a tener el MLL en $0 (balance de $2,000) | «We recommend reaching a balance where your MLL is at $0 first.» | [S6] | alta · verificado |
| Topes acumulados | XFA: no lo dice la fuente oficial (salvo los $200,000 de los países «solo XFA»). LFA: sin tope por retiro; tras 30 días ganadores, payouts diarios | «Live Funded Account Payouts are not capped.» | [S6] | alta · verificado |
| Solicitud | En el dashboard, en horario CME (domingo 17:00 CT – viernes 17:00 CT); el importe se descuenta al momento | «Once you request a Payout, the funds are transferred immediately» | [S6] | alta · verificado |
| Aprobación | Revisión interna de 1–3 días hábiles (reglas de payout, conducta prohibida, estrategias prohibidas) | «Internal approval can take 1-3 business days.» | [S6] | alta · verificado |
| Proceso y recepción | Wire internacional: **5–10 días hábiles**, $30. Solo EE. UU.: ACH 1–3 días ($30), Aeropay instantáneo tras aprobar, Prop-to-Brokerage en el día | «Wire · International · 5-10 business days · $30» | [S6] | alta · verificado |
| Métodos de pago | Wire para internacionales. **Wise no está disponible en noviembre de 2026.** Solo a una cuenta bancaria propia | «Wise is currently unavailable as a payout option.» | [S6] | alta · verificado |
| Ejemplo neto con wire | Retiro de $2,000 → $1,800 tras el reparto → **$1,770** tras el cargo de $30 (cálculo propio, con el mismo método que el ejemplo ACH de la fuente) | «$500 minus $50 (10% split) minus $30 (processing fee) = $420 received» | [S6] | alta · verificado |
| KYC | Verificación de identidad con documento oficial físico y selfie, obligatoria antes de la segunda compra y para pedir payouts | «identity verification is also required for requesting Payouts» | [S15] | alta · verificado |
| Formularios fiscales | W-8BEN para no estadounidenses, dentro de la solicitud de payout | «W-9 for US persons, W-8BEN for non-US persons.» | [S6], [S27] | alta · verificado |
| Transición a Live | Llamada discrecional del equipo de riesgo; al pasar a Live se cierran todas las XFA; 20 % operable (mínimo $10,000) y 80 % en reserva; crear la LFA lleva 7–10 días hábiles; solo 1 LFA | «When the call-up comes, all Express Funded Accounts (XFA) close.» | [S10] | alta · verificado |

## D. Automatización (crítico)

**Veredicto: permitida con condiciones, solo por la API de TopstepX/ProjectX. Con NinjaTrader 8 no es
posible, porque Topstep no ofrece NT8.**

| Pregunta | Respuesta | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| ¿Bots y estrategias automáticas? | **Sí, por la API de TopstepX/ProjectX**, con las reglas de la plataforma y la prohibición de HFT. El trader responde del bot | «Custom automated strategies and bots are allowed via the TopstepX / ProjectX API, subject to standard platform rules and our prohibition on highfrequency trading (HFT).» | [S9] | alta · verificado |
| ¿Misma regla para manual y automático? | Sí: una infracción cuenta igual, venga de donde venga | «A rule violation is treated the same whether it originates from manual trading or third-party automation.» | [S9] | alta · verificado |
| ¿NinjaTrader 8 Automated Strategies / NinjaScript? | **No.** TopstepX es la única plataforma; NinjaTrader no aparece en ninguno de los 31 artículos leídos | «TopstepX™ is the only available trading platform.» | [S20] | alta · verificado |
| ¿ATM Strategies? | No aplica (son de NT8, que no está soportado). TopstepX tiene sus propias brackets y Auto-OCO, con una distancia mínima de 4 ticks | «The minimum distance Position Brackets can be placed is 4 ticks from the entry price.» | [S19] | alta · verificado |
| ¿Copiador de operaciones? | **Sí, el nativo de TopstepX**, solo en Combine y XFA (no en LFA): un grupo líder→seguidores; el líder debe tener el menor tamaño máximo. Los copiadores de terceros **no** tienen permiso explícito: [S18] solo dice que el trader responde de lo que creen | «Live Funded Account® accounts cannot use the Trade Copier.» | [S19], [S18] | alta · verificado |
| ¿Varias cuentas? | Combines: sin límite. XFA: **hasta 5** activas. LFA: 1. Un solo perfil por persona. Una suscripción de API cubre todas las cuentas elegibles | «You can hold up to 5 active XFAs at a time.» | [S4], [S1], [S9] | alta · verificado |
| ¿Hedging entre cuentas? | Prohibido (por ejemplo, MNQ/NQ en sentidos opuestos); se detecta en tiempo real, con liquidación y cierre si se repite | «holding opposite positions across multiple accounts simultaneously» | [S17], [S18] | alta · verificado |
| ¿VPS? | **Prohibido** para enviar órdenes. Un servidor privado solo puede guardar datos, investigar o registrar | «All trading activity must originate from your personal device. The use of VPS, VPNs, and remote servers is prohibited» | [S9], [S30] | alta · verificado |
| Límites de frecuencia | Los «fair-use limits» de ProjectX (cifras Sin datos). Sesión única: 1 dispositivo o navegador a la vez | «Your API access remains governed by the ProjectX Terms of Use, including fair-use limits.» | [S9], [S19] | media · parcial |
| ¿HFT prohibido? | **Sí** (sin umbral numérico) | «engaging in any short term or high frequency trades» | [S30], [S9] | alta · verificado |
| ¿Microscalping prohibido (umbral)? | Prohibido el scalping algorítmico que explota los fills del SIM. No hay umbral numérico; la señal que da la fuente son cientos o miles de operaciones al día con duraciones de segundos | «usually hundreds or thousands of trades per day, with average durations measured in seconds, not minutes.» | [S16] | alta · verificado (umbral: Sin datos) |
| Técnicas de ejecución prohibidas | Brackets muy ajustadas o auto-breakeven para aprovechar los fills del SIM; operar fuera del mejor bid/offer; feed lento o externo; spoofing; tecnología «injusta» (software, IA, ultra alta velocidad) | «Using tight brackets or auto-breakeven to take advantage of favorable SIM fills» | [S16], [S17] | alta · verificado |
| ¿Pueden anular beneficios? | **Sí**: borrar el día y los beneficios, resetear o cerrar la cuenta, denegar el payout | «Topstep may, in its sole determination, remove any Simulated Account profits, delete a trading day, reset an Account, or ban a User» | [S30], [S17] | alta · verificado |
| Sandbox | No hay; se prueba en una cuenta Practice | «No. There is currently no sandbox environment available.» | [S9] | alta · verificado |
| Diferencias Combine / XFA / Live | El copiador y Quantower solo están en Combine y XFA. En la LFA: DLL automático, datos profesionales ($133 por bolsa al mes; Topstep cubre una), licencia de plataforma propia y sin ratio micro:mini. Si la API sirve en la LFA, **no lo dice la fuente oficial** | «Quantower via TopstepX is available for the Trading Combine® and Express Funded Account® (XFA) only.» | [S21], [S13], [S1] | alta · verificado |

## E. Plataformas

| Plataforma | ¿Soportada? | Cita / nota | Fuente | Confianza · estado |
|---|---|---|---|---|
| TopstepX (web, ProjectX) | **Sí, la única** | «TopstepX™ is the only available trading platform.» | [S20], [S19] | alta · verificado |
| NinjaTrader 8 | **No** | No aparece en ningún artículo; TopstepX es la única plataforma | [S20] | alta · verificado |
| Rithmic | No (los datos llegan por ProjectX, «direct CME feed») | «This links your account to ProjectX data — a direct CME feed» | [S21] | alta · verificado |
| CQG | No lo dice la fuente oficial; implícitamente no | — | [S20] | media · parcial |
| Tradovate | No lo dice la fuente oficial; implícitamente no | — | [S20] | media · parcial |
| TradingView | No se puede conectar | «Cannot connect to external platforms like TradingView» | [S19] | alta · verificado |
| Quantower | Sí, conectado a ProjectX/TopstepX, solo en Combine y XFA; **sin** Strategy Manager, Strategy Runner, Market Replay ni simulador | «Not included: Market Replay · Strategy Manager · Strategy Runner · Trading Simulator» | [S21] | alta · verificado |
| Sierra Chart · Bookmap · ATAS | No lo dice la fuente oficial; implícitamente no | — | [S20] | media · parcial |
| API | ProjectX Gateway (REST y WebSocket): $29/mes o $14.50 con código; datos en vivo e históricos | «work with REST and WebSocket APIs» | [S9] | alta · verificado |
| Conexiones simultáneas | 1 sesión de usuario en todos los dispositivos (varias pestañas del mismo navegador sí) | «limit your access to one concurrent user session across all devices» | [S19] | alta · verificado |

## F. Elegibilidad internacional

| Campo | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Regla general | La elegibilidad depende de la ciudadanía **y** de la residencia; mínimo 18 años | «Eligibility is based on both citizenship and permanent residency.» | [S14] | alta · verificado |
| **República Dominicana** | **No figura** en la lista de países no elegibles ni en la de «solo XFA, sin LFA» (actualizada el 17-11-2026). Por la lista oficial, RD es elegible para Combine, XFA y LFA | «Citizens or residents of OFAC-sanctioned or partner-restricted countries are not eligible to trade, earn funding, or receive payouts» | [S14] | **media · verificado por ausencia en la lista** |
| Cautela | La lista puede cambiar en cualquier momento y hay «partner restrictions». Conviene confirmarlo por escrito con Trader Support antes de comprar | «This list can change at any time based on updates from brokerages and other circumstances.» | [S14] | alta · verificado |
| Viajes | No operar desde un país no elegible, ni siquiera de paso | «Trading from an ineligible country — even briefly — may trigger a review» | [S14] | alta · verificado |
| VPN | Prohibida; perjudica además la verificación de identidad | «Do not use a VPN.» | [S17], [S15] | alta · verificado |
| KYC | Documento oficial físico vigente y selfie; antes de la segunda compra y para los payouts | «A valid, unexpired original physical government-issued ID» | [S15] | alta · verificado |
| Cobro desde RD | Wire internacional (5–10 días hábiles, $30) a una cuenta bancaria a nombre propio; Wise no disponible (nov-2026) | «Payouts can only be sent to a bank account in your own name.» | [S6] | alta · verificado |
| Impuestos | W-8BEN; Topstep no emite formulario fiscal a no estadounidenses. Los traders son contratistas independientes | «Non-US citizen living outside the US · W-8 BEN» | [S27] | alta · verificado |
| Pago de las compras desde RD | Tarjeta a nombre propio con la dirección de facturación del banco; pueden fallar las prepago | «Use a card in your name — must match your Topstep profile exactly.» | [S7], [S22] | alta · verificado |

## G. Fuentes

Todas consultadas el **2026-11-27** con `curl` (agente de usuario por defecto) y respuesta HTTP 200.

| # | Dato principal | URL | Fecha | Confianza | Estado |
|---|---|---|---|---|---|
| S1 | Parámetros del Combine | https://help.topstep.com/en/articles/8284197-trading-combine-parameters | 2026-11-27 | alta | verificado |
| S2 | MLL (Combine y XFA) | https://help.topstep.com/en/articles/8284204-what-is-the-maximum-loss-limit | 2026-11-27 | alta | verificado |
| S3 | Consistencia (usada en el FUT-R1) | https://help.topstep.com/en/articles/8284208-consistency-at-topstep | 2026-11-27 | alta | verificado |
| S4 | Parámetros de la XFA | https://help.topstep.com/en/articles/8284215-express-funded-account-parameters | 2026-11-27 | alta | verificado |
| S5 | Scaling Plan (tabla en imagen) | https://help.topstep.com/en/articles/8284223-what-is-the-scaling-plan | 2026-11-27 | media | parcial |
| S6 | Política de payouts, métodos y plazos | https://help.topstep.com/en/articles/8284233-topstep-payout-policy | 2026-11-27 | alta | verificado |
| S7 | Precios, medios de pago, promociones | https://help.topstep.com/en/articles/14289835-topstep-pricing-and-payment-questions | 2026-11-27 | alta | verificado |
| S8 | Noticias Tier 1 y límites por volatilidad | https://help.topstep.com/en/articles/13613539-risk-adjustments-high-risk-high-volatility | 2026-11-27 | alta | verificado |
| S9 | API, bots y VPS | https://help.topstep.com/en/articles/11187768-topstepx-api-access | 2026-11-27 | alta | verificado |
| S10 | Live Funded Account | https://help.topstep.com/en/articles/10657969-live-funded-account-parameters | 2026-11-27 | alta | verificado |
| S11 | Horarios y productos | https://help.topstep.com/en/articles/8284206-when-and-what-products-can-i-trade | 2026-11-27 | alta | verificado |
| S12 | Comisiones TopstepX | https://help.topstep.com/en/articles/8284213-topstepx-commissions-and-fees | 2026-11-27 | alta | verificado |
| S13 | Costes de la LFA | https://help.topstep.com/en/articles/8284229-what-are-the-costs-in-the-live-funded-account | 2026-11-27 | alta | verificado |
| S14 | Elegibilidad por país | https://help.topstep.com/en/articles/8284116-am-i-eligible-to-trade-with-topstep | 2026-11-27 | alta | verificado |
| S15 | Verificación de identidad | https://help.topstep.com/en/articles/12578731-how-identity-verification-works | 2026-11-27 | alta | verificado |
| S16 | Estrategias prohibidas | https://help.topstep.com/en/articles/10305426-prohibited-trading-strategies-at-topstep | 2026-11-27 | alta | verificado |
| S17 | Conducta prohibida | https://help.topstep.com/en/articles/10296582-prohibited-conduct | 2026-11-27 | alta | verificado |
| S18 | Hedging y copiadores | https://help.topstep.com/en/articles/13747047-understanding-hedging | 2026-11-27 | alta | verificado |
| S19 | TopstepX (copiador, brackets, sesiones) | https://help.topstep.com/en/articles/14434175-topstepx | 2026-11-27 | alta | verificado |
| S20 | «TopstepX is the only available trading platform» | https://help.topstep.com/en/articles/8284199-new-to-topstep-start-here | 2026-11-27 | alta | verificado |
| S21 | Quantower vía TopstepX | https://help.topstep.com/en/articles/8284179-quantower-connection-instructions | 2026-11-27 | alta | verificado |
| S22 | Suscripción del Combine | https://help.topstep.com/en/articles/8284121-trading-combine-subscriptions | 2026-11-27 | alta | verificado |
| S23 | Activación de la XFA | https://help.topstep.com/en/articles/8284217-express-funded-account-activation | 2026-11-27 | alta | verificado |
| S24 | Datos L1/L2 | https://help.topstep.com/en/articles/8284120-level-1-and-level-2-market-data | 2026-11-27 | alta | verificado |
| S25 | DLL | https://help.topstep.com/en/articles/10490293-daily-loss-limit-in-the-trading-combine-and-express-funded-account | 2026-11-27 | alta | verificado |
| S26 | Publicaciones económicas | https://help.topstep.com/en/articles/8284211-economic-releases | 2026-11-27 | alta | verificado |
| S27 | Impuestos | https://help.topstep.com/en/articles/8284238-funded-trader-tax-questions | 2026-11-27 | alta | verificado |
| S28 | Reembolsos | https://help.topstep.com/en/articles/8284117-topstep-refund-policies | 2026-11-27 | alta | verificado |
| S29 | Límite de resets | https://help.topstep.com/en/articles/10370307-reset-purchase-limits | 2026-11-27 | alta | verificado |
| S30 | Términos de uso (§27 conducta prohibida, §28 VPN/VPS) | https://www.topstep.com/terms-of-use/ | 2026-11-27 | alta | verificado |
| S31 | Problemas de plataforma (navegadores, conexión) | https://help.topstep.com/en/articles/8284136-general-platform-troubleshooting | 2026-11-27 | alta | verificado |

### Páginas que no se pudieron leer o que quedan incompletas
- Ninguna respondió 403 ni otro error.
- **Tabla del Scaling Plan** ([S5]): es una imagen, sin texto alternativo → **Sin datos** de contratos
  por tramo (solo los márgenes de [S8]).
- **ProjectX Terms of Use** («fair-use limits»): en `dashboard.projectx.com`, fuera de los hosts
  permitidos; no se leyó.
- **Acuerdo de la XFA** (XFA Agreement): solo se muestra dentro del dashboard; no se leyó.

### Aviso de método
- Los Términos de uso de Topstep ([S30], §28) prohíben «Using any manual or automated software,
  devices, or other processes to "crawl" or "spider" any web pages». Esta investigación descargó unas
  50 páginas públicas con `curl` (artículos, colecciones y portada). Que esto sea o no compatible con ese término lo decide el operador. Si
  no lo es, las próximas lecturas deberían hacerse con un navegador.
