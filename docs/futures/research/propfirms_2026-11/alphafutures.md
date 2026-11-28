# Alpha Futures · ficha de reglas de fondeo (investigación 2026-11)

- **ID**: `alphafutures` · **Fecha de consulta**: 2026-11-27 · **Cuenta de referencia**: 50K.
- **Firma**: Alpha Futures Limited (Inglaterra y Gales, n.º 15655643), sujeta a la ley inglesa
  ([S3]). El modelo es de «Analyst»: las cuentas son simuladas y lo que se cobra son «Performance
  Fees».
- **Planes analizados (50K)**, cada uno con su subsección: **Zero** (§1), **Standard** (§2),
  **Advanced** (§3) y **Direct** (§4, sin evaluación). Los tres primeros siguen el camino Evaluación →
  Qualified; Direct entra en Qualified desde el primer día. Después: Live o Alpha Prime.
- **Fuentes**: portada, plataformas, Términos y condiciones («Effective from July 27, 2026»), Términos
  de uso y política de devoluciones de `alpha-futures.com`, y **todo** el help center oficial (34
  artículos en 5 colecciones). El help center se leyó en
  `intercom.help/alpha-futures-limited-f14467eeaf9c/en/`; su dominio canónico es
  `help.alpha-futures.com`, que no está entre los hosts permitidos.
- **Formato de cada dato**: valor · «cita literal» · [S#] (URL exacta y fecha en §G) · confianza ·
  estado. Todo se consultó el 2026-11-27. Lo que es aritmética sobre cifras oficiales se marca
  **(cálculo propio)**.
- **Aviso**: los Términos de uso de Alpha prohíben el acceso automatizado y el scraping (§G). Por esa
  cláusula, **las descargas se detuvieron** y esta ficha se escribe solo con lo ya descargado.

## Resumen (50K)

| Campo | Valor |
|---|---|
| **Automatización** | **Prohibida** en todos los tipos de cuenta: «The use of AI, bots, and other automated trading mechanisms is strictly prohibited across all account types.» Solo se permite la semiautomatización: indicadores con señales, pero la orden la pone y la gestiona el trader a mano. Además, no aceptan estrategias de más de 100 operaciones al día |
| **NinjaTrader 8** | **No soportado**: las únicas plataformas son AlphaTrader, TradingView (vía Plus500), WealthCharts, DeepChart (Volumetrica) y Quantower (dxFeed). La plataforma queda fijada al comprar |
| **República Dominicana** | **No figura** en la lista de países restringidos (actualizada el 12-8-2026). Ninguna página la nombra de forma expresa. Estado: **parcial** (ausencia en una lista cerrada) · confianza media |
| Coste hasta la primera cuenta Qualified, mejor caso (1 intento) | Zero **$169** · Standard **$129** · Advanced **$209** (precio mensual; aprobando en el primer ciclo) · Direct **$519** (pago único, Qualified desde el día 1). Activación $0 en los cuatro. A 50K no hay ninguna promoción con alcance claro |
| Reparto / mínimo / máximo / frecuencia | **90 %** en Qualified (Live: 80 %; Alpha Prime: 60 %) · mín./máx. por retiro: Zero $200/**$1,500** · Standard $500/**$3,000** · Advanced $1,000/**$15,000** · Direct $500/**$2,000** · hasta **4 al mes**, cada 5 días ganadores de $200 o más (Direct: al alcanzar su objetivo de retiro), y como mucho el 50 % del beneficio por solicitud |
| Comisiones | **Sin datos**: están en un PDF («Permitted Products and Fees.pdf») alojado en un host no permitido, que no se leyó |

---

## A. Costes (50K)

### A.0 Común

| Concepto | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Modalidad (Zero, Standard, Advanced) | **Suscripción mensual** hasta aprobar o cancelar; se acaba al aprobar | «Your Monthly Evaluation Fee will rebill monthly from the sign-up date until you pass.» | [S10], [S3] | alta · verificado |
| Modalidad (Direct) | **Pago único** | «All Direct Accounts are one time fee, no monthly subscription.» | [S9] | alta · verificado |
| Cuota una vez Qualified | Ninguna | «Qualified Traders do not pay a monthly subscription.» | [S10], [S1] | alta · verificado |
| Activación | **$0** en Zero, Standard y Direct; Advanced, $0 si se compró después del 8-7-2026 | «Accounts Purchased after July 8, 2026 enjoy No Activation Fees» | [S8], [S7], [S6] | alta · verificado |
| Reembolso | Ninguno. Excepción: si falla el KYC, se devuelve la evaluación aprobada o en curso. El desistimiento de 14 días de los Términos se renuncia al hacer la primera operación | «All sales are final, no refunds will be issued.» | [S5], [S25], [S3] §15.2 | alta · verificado |
| Promociones vigentes | Black Friday: `BOGO40` (25K Zero, 2x1 + 40 %) y `BOGO50` (25K Direct, 2x1 + 50 %), ninguna a 50K. Hay además un bloque `ALPHA50` «50% off» que no dice a qué plan ni hasta cuándo se aplica | «BOGO40 25K Zero BOGO + 40% off · BOGO50 25K Direct BOGO + 50% off» | [S1] | alta · verificado (alcance de `ALPHA50`: **no lo dice la fuente oficial**) |
| Datos de mercado | Hay que firmar un acuerdo de no profesional en la plataforma. Precio: **no lo dice la fuente oficial** | «you MUST sign your Non-Professional Agreement before your account will receive real-time data» | [S35], [S36] | alta · parcial |
| Comisiones (MNQ, NQ) | **Sin datos**: enlace «Permitted Products and Fees.pdf» desde [S19], en `…intercom-attachments-1.com`, que no se leyó | — | [S19] | — · no verificado |
| Plataforma | DeepChart incluye gratis el paquete «OrderFlow»; Quantower tiene versión gratuita; TradingView pide una cuenta personal. Licencias de pago: **no lo dice la fuente oficial** | «Complimentary access to "OrderFlow" package» | [S23], [S2] | media · parcial |
| Pagos de las compras | Tarjeta o cuenta a nombre propio (se cruza con el KYC); también cripto por CoinPayments, sin cobro automático de las renovaciones | «we do not accept payments made via a third-party card or account» | [S33], [S34] | alta · verificado |
| Inactividad | Hay que operar al menos una vez cada 10 días de trading | «you must place a trade at least once every 10 trading days» | [S32] | alta · verificado |

### §1 · Zero 50K

| Concepto | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Evaluación | **$169/mes** (precio de lista, sin promoción a 50K) | «50K Zero Eval $169/month» | [S1], [S6], [S10] | alta · verificado |
| Reset de la evaluación | **$149** (no cambia la fecha de renovación) | «Resets DO NOT change or affect your monthly rebill date.» | [S11], [S1] | alta · verificado |
| Reset de la Qualified | **$499**, como mucho 2 veces y solo si la cuenta nunca llegó a pedir un payout; hay 7 días tras la rotura | «Traders may use a Qualified Reset 2 times on a singular account, if the account has never reached payout request.» | [S11] | alta · verificado |
| Mejor caso hasta la Qualified | **$169** (aprobando en el primer ciclo; mínimo 1 día) (cálculo propio) | — | — | alta |
| Mantener 3 y 6 meses | **$0** de cuota; datos y comisiones **Sin datos** | — | [S10] | media · parcial |

### §2 · Standard 50K

| Concepto | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Evaluación | **$129/mes** | «50K Standard Eval $129/month» | [S1], [S7], [S10] | alta · verificado |
| Extra opcional | Quitar la regla de consistencia en la Qualified: **+$70** (no dice si es un pago único o mensual) | «No Consistency RuleOn your Qualified account OffOn+$70» | [S1] | alta · parcial |
| Reset de la evaluación | **$109** | «Evaluation Reset $109» | [S7], [S11] | alta · verificado |
| Reset de la Qualified | **$599** (mismas condiciones que en Zero) | «50k Qualified Account $599» | [S11], [S1] | alta · verificado |
| Mejor caso hasta la Qualified | **$129**, o $199 con el extra (cálculo propio; mínimo 2 días) | — | — | alta |
| Mantener 3 y 6 meses | **$0** de cuota; datos y comisiones **Sin datos** | — | [S10] | media · parcial |

### §3 · Advanced 50K

| Concepto | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Evaluación | **$209/mes** | «50K Advanced Eval $209/month» | [S1], [S8], [S10] | alta · verificado |
| Reset de la evaluación | **$189** | «Reset $189» | [S8], [S11] | alta · verificado |
| Reset de la Qualified | No existe | «Qualified Resets are only available on Zero and Standard Accounts.» | [S11] | alta · verificado |
| Mejor caso hasta la Qualified | **$209** (cálculo propio; mínimo 3 días) | — | — | alta |
| Mantener 3 y 6 meses | **$0** de cuota; datos y comisiones **Sin datos** | — | [S10] | media · parcial |

### §4 · Direct 50K

| Concepto | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Precio | **$519, pago único**; no hay evaluación | «50K Direct Qualified $519one-time» | [S1], [S9] | alta · verificado |
| Reset | **No lo dice la fuente oficial** (no figura en [S11]) | — | [S11] | media · no verificado |
| Mejor caso hasta la cuenta financiada | **$519**: la cuenta es Qualified desde el primer día | «No Evaluation, jump straight into a Qualified Account from day one» | [S9] | alta · verificado |
| Mantener 3 y 6 meses | **$0** de cuota; datos y comisiones **Sin datos** | — | [S9] | media · parcial |

Si `ALPHA50` se aplicara a 50K, el primer mes saldría a Zero $84.50, Standard $64.50, Advanced $104.50
y Direct $259.50 (cálculo propio, **hipotético**: la web no dice que se aplique).

---

## B. Reglas de trading

### B.0 Común

| Regla | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Tipo de drawdown (MLL) | **Trailing EOD** en todas las cuentas, sin trailing intradía; se calcula con el saldo de cierre | «None of our accounts utilize intraday trailing drawdown you will see elsewhere in industry.» | [S12] | alta · verificado |
| ¿Incluye P&L no realizado? | Para mover el MLL, no (saldo EOD). Para romperlo, **sí**: la equidad flotante cuenta en tiempo real | «If you break MLL at any point, floating equity or closed balance of account, your account will be liquidated.» | [S12] | alta · verificado |
| Dónde se bloquea | En el saldo inicial (50K: cuando el saldo EOD llega a $52,000, el MLL se queda en $50,000) | «Once the Maximum Loss Limit reaches the initial starting balance, it won't continue to trail.» | [S12] | alta · verificado |
| MLL y retiros | No se mueve al retirar | «If MLL was at $49,200 before payout, it will be after as well.» | [S6], [S7] | alta · verificado |
| DLG o DLL (efecto) | **Rotura blanda**: cierra posiciones y bloquea hasta las 18:00 ET; incluye P&L no realizado y comisiones | «If you hit the Daily Loss Guard, you do not lose your Account, but your account will be locked until the next trading day (6PM ET).» | [S13] | alta · verificado |
| Horarios | Día de 18:00 a 17:00 ET; **todo cerrado antes de las 16:20 ET** (cierre automático); mercado cerrado de viernes 17:00 a domingo 18:00 | «all trades must be closed before 4:20PM EST every day» | [S19], [S3] | alta · verificado |
| Overnight y fin de semana | No en las cuentas simuladas. En Live, sí | «Trades do not need to be closed by 4:20pm EST (like they do on sim accounts).» | [S29] | alta · verificado |
| Productos | CME Group (CME, CBOT, NYMEX, COMEX); MBT y MET cuentan como minis | «due to volatility these contracts are treated as full mini contracts» | [S19] | alta · verificado |
| Límite de precio | Prohibido operar a menos del 2 % de un límite de CME, en todas las cuentas | «This prohibited conduct is enforced on ALL Alpha Futures Accounts, not just Evaluations.» | [S31] | alta · verificado |
| Noticias (evaluaciones) | Sin restricciones | «There are no news trading restrictions for any Evaluation Accounts.» | [S18] | alta · verificado |
| Noticias (Qualified Direct, Standard y Zero) | Ninguna orden entre 2 min antes y 2 min después de un evento rojo de ForexFactory; se puede mantener la posición. La primera vez es un aviso y se anulan esos beneficios; la siguiente, rotura | «no orders may be executed within 2 minutes before or 2 minutes after high impact news events» | [S18] | alta · verificado |
| Precedencia | Si los anexos de los Términos y la web discrepan, manda la web | «In the case of any discrepancy between the Challenge requirements listed in the Schedules and our Site, then our Site shall take precedence.» | [S3] §1.4 | alta · verificado |

### §1 · Zero 50K

| Regla | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Objetivo de beneficio | **$3,000** | «Profit Target $3,000» | [S6], [S1] | alta · verificado |
| MLL | **$2,000** EOD | «Maximum Loss Limit $2,000» | [S6] | alta · verificado |
| DLG | **$1,000** (2 %) en evaluación y en Qualified. **Discrepancia**: los Términos dicen «soft breach rule on Qualified Analyst Accounts only» | «Daily Loss Guard $1,000» | [S6], [S13], [S1] frente a [S3] | media · `discrepancia` |
| Consistencia | Evaluación: **ninguna** (se puede aprobar en 1 día) · Qualified: **40 %** desde el último retiro | «No Consistency Rule on Zero Evaluations means you may pass in one day.» | [S6], [S15] | alta · verificado |
| Días mínimos | Evaluación 1 · Qualified 5 | «Minimum Trading Days 1» · «Minimum Trading Days 5» | [S1] | alta · verificado |
| Contratos | **3 minis o 30 micros** | «3 minis, 30 micros» | [S6], [S3] | alta · verificado |
| Escalado (Qualified) | Menos de $1,500 de beneficio: 1 mini/10 micros · de $1,500 a $2,000: 2/20 · de $2,000 a $3,000: 3/30 | tabla «Zero Qualified Accounts» | [S14] | alta · verificado |
| Noticias en Qualified | Restricción de ±2 min (B.0) | — | [S18] | alta · verificado |

### §2 · Standard 50K

| Regla | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Objetivo de beneficio | **$3,000** | «Profit Target $3,000» | [S7] | alta · verificado |
| MLL | **$2,000** EOD | «Maximum Loss Limit $2,000» | [S7] | alta · verificado |
| DLG | Evaluación: **ninguno** · Qualified: **$1,000** | «Daily Loss Guard (NONE on Evaluation!) $1,000» | [S7], [S1] | alta · verificado |
| Consistencia | Evaluación **50 %** · Qualified **40 %** (se puede quitar con el extra de $70) | «50% on Evaluation 40% on Qualified» | [S7], [S15], [S1] | alta · verificado |
| Días mínimos | Evaluación 2 · Qualified 5 | «The standard and advanced account assessments consist of 2 and 3 minimum trading days» | [S3] §8.1.9, [S1] | alta · verificado |
| Contratos | **5 minis o 50 micros** | «5 minis, 50 micros» | [S7] | alta · verificado |
| Escalado (Qualified) | Menos de $1,500: 2/20 · de $1,500 a $2,000: 3/30 · $2,000 o más: 5/50 | tabla «Standard Qualified Accounts» | [S14] | alta · verificado |
| Noticias en Qualified | Restricción de ±2 min | — | [S18] | alta · verificado |

### §3 · Advanced 50K

| Regla | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Objetivo de beneficio | **$4,000** | «Profit Target $4,000» | [S8], [S1] | alta · verificado |
| MLL | **$1,750** EOD. **Discrepancia**: el Anexo 2 de los Términos pone «4%» ($2,000) para la Advanced Qualified; según §1.4 manda la web | «Maximum Loss Limit $1,750» | [S8], [S1] frente a [S3] | media · `discrepancia` |
| DLG | **Ninguno**, ni en evaluación ni en Qualified (el trader puede fijarse uno) | «No Daily Loss Guard on Evaluation or Qualified Accounts» | [S8], [S13] | alta · verificado |
| Consistencia | Evaluación **40 %** · Qualified **ninguna** | «40% on Evaluation only» | [S8], [S15] | alta · verificado |
| Días mínimos | Evaluación 3 · Qualified 5 | «Minimum Trading Days 3» | [S1], [S3] | alta · verificado |
| Contratos y escalado | **5 minis o 50 micros**, sin escalado | «No Scaling Plan on Advanced Accounts. Get access to full contract limit at all times.» | [S8], [S14] | alta · verificado |
| Noticias | Sin restricciones, pero vale lo de «all or nothing» y la conducta de apuesta | «Advanced Qualified Accounts do not have News Trading Restrictions» | [S18] | alta · verificado |

### §4 · Direct 50K

| Regla | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Evaluación | No hay | «Users that select the Direct Account can skip the Evaluation stage» | [S9] | alta · verificado |
| MLL | **$2,000** EOD | «Max Loss Limit (EOD) $2,000» | [S1], [S9] | alta · verificado |
| DLL | **$1,000** | «Daily Loss Limit $1,000» | [S1], [S9] | alta · verificado |
| Consistencia | **20 %** desde el último retiro | «There is a 20% Consistency Rule on Direct Qualified Accounts.» | [S15], [S9] | alta · verificado |
| Contratos y escalado | **4 minis o 40 micros**, sin escalado | «4 minis, 40 micros» | [S9], [S1] | alta · verificado |
| Días mínimos | **Discrepancia**: [S16] dice que Direct no tiene requisito de días ganadores; el Anexo 2 de [S3] pone «5» días mínimos | «Direct Accounts have the same profit split, but no winning day requirement» | [S16] frente a [S3] | media · `discrepancia` |
| Noticias | Restricción de ±2 min | «Restrictions on Major Events» | [S9], [S18] | alta · verificado |

---

## C. Payouts

### C.0 Común

| Campo | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Frecuencia (Zero, Standard, Advanced) | Hasta **4 al mes**, cada **5 días ganadores de $200 o más** (no consecutivos), sin fechas fijas | «Request every 5 winning trading days of $200 profit, or more» | [S16] | alta · verificado |
| Tope por solicitud | **50 % del beneficio** de la cuenta, hasta el máximo del plan | «You may request up to 50% of the profit in your account each withdrawal request (up to withdrawal limit)» | [S16] | alta · verificado |
| Reparto | **90 %** al trader sobre lo que se retira de la cuenta | «All withdrawal requests are the amount that will be removed from your trading account, trader received 90% of this request.» | [S16] | alta · verificado |
| Buffer | No existe: el MLL no cambia al retirar (B.0) | — | [S6], [S7] | alta · verificado |
| Estado al pedirlo | Todas las posiciones cerradas; se pausa el trading hasta que se descuenta el retiro | «all virtual trading will be paused and can only resume once the withdrawal amount has been withdrawn» | [S3] Anexo 4 §1.2.5 | alta · verificado |
| Aprobación → pago | **Discrepancia**: portada «paid in five business days or less» frente a Términos «within 3 Business Days» (hasta 14 si hay comprobaciones). Lo que tarda en llegar al banco: **no lo dice la fuente oficial** | «Approved requests are paid in five business days or less.» | [S1] frente a [S3] Anexo 4 §1.2.7 | media · `discrepancia` |
| Métodos | ACH (solo EE. UU.), transferencia, SWIFT, Wise, Rise; en USD. Los Términos citan también Checkout.com, CoinPayments y Nuvei | «- ACH (US bank accounts) - Wire Transfer -SWIFT - Wise - Rise» | [S27], [S3] | media · parcial (listas distintas) |
| KYC | Con Veriff: documento oficial (no en papel) y selfie; **sin VPS ni VPN durante el KYC**; revisión en hasta 48 h; contrato firmado en 30 días; la Qualified llega en 24 h | «The use of VPS/VPN during the KYC process is not permitted.» | [S25], [S26] | alta · verificado |
| Paso a Live | Por invitación; por ejemplo, tras **5 Performance Fees en una misma Qualified**. Se cierran todas las Qualified. Live 50K: saldo $0, drawdown EOD $2,000, 2 minis/20 micros (4/40 cuando el MLL llega a $0) | «5 performance fees on a single Qualified Account» | [S28] | alta · verificado |
| Reparto en Live | Live Program **80 %**, diario y sin tope · Alpha Prime **60 %** más un bonus mensual (50 % del beneficio simulado, hasta $75,000, repartido en 12 meses) | «at an 80% profit split, with daily, uncapped withdrawals» | [S28], [S17] | alta · verificado |
| Pérdida de la Live | Pausa de hasta 3 meses, menor cuanto más tiempo se estuvo en Live | «The baseline target for a live account is 3 months.» | [S30] | alta · verificado |

### Por plan (50K)

| § | Plan | Días y requisito | Beneficio mín./día | Mínimo | Máximo por retiro | Consistencia | Reparto | Fuente |
|---|---|---|---|---|---|---|---|---|
| 1 | Zero | 5 días ganadores por ciclo | $200 | **$200** | **$1,500** | 40 % | 90 % | [S6], [S16], [S17] |
| 2 | Standard | 5 días ganadores | $200 | **$500** | **$3,000** | 40 % (o ninguna con el extra) | 90 % | [S7], [S16], [S17] |
| 3 | Advanced | 5 días ganadores | $200 | **$1,000** | **$15,000** | ninguna | 90 % | [S8], [S16], [S17] |
| 4 | Direct | Objetivo de retiro: **$3,000** el 1.º y **$2,000** los siguientes, con beneficio nuevo (el sobrante no se arrastra) | — | **$500** | **$2,000** | 20 % | 90 % | [S9], [S16], [S17] |

Citas: «50k Zero Qualified Account maximum withdrawal is $1,500» · «50k Standard Qualified Account
maximum withdrawal is $3,000» · «The maximum withdrawal request on all Advanced Account sizes is
$15,000.» · «50k Direct Qualified Account maximum withdrawal is $2,000» [S17] · alta · verificado.
Número máximo de retiros: hasta 4 al mes ([S16]); sin tope acumulado en Qualified, más allá de la
invitación a Live ([S28]) · alta · verificado.

---

## D. Automatización (crítico) · común a los 4 planes

**Veredicto: prohibida.** No hay sitio para un bot de TradingLab. Además, no hay NT8.

| Pregunta | Respuesta | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| ¿Bots y estrategias automáticas? | **No**, en ninguna cuenta (evaluación, Qualified, Direct) | «The use of AI, bots, and other automated trading mechanisms is strictly prohibited across all account types.» | [S20], [S3] | alta · verificado |
| ¿Semiautomatización? | Sí: indicadores con señales, pero el trader pone, vigila y gestiona la orden a mano | «is permissible under the condition that the user manually places, monitors, and manages the trade» | [S20] | alta · verificado |
| ¿Automatización total? | Prohibida | «Any form of hands-off, continuous day and night trading, or any other type of full automation is strictly forbidden.» | [S20], [S3] | alta · verificado |
| ¿NT8 Automated Strategies / NinjaScript? | No aplica: NT8 no está soportado (§E) | — | [S23] | alta · verificado |
| ¿ATM Strategies? | **No lo dice la fuente oficial**; NT8 no existe en la firma | — | — | — |
| ¿Copiadores? | **Discrepancia**. [S21]: se permiten si un solo usuario ejecuta en sus propias cuentas, con «Automated, Group, and Reverse Trading» prohibidos. Términos §8.1.5: «the only copy trading allowed is that from your own external account to your Alpha Futures Account» | «Copy trading in general is permitted as long as it is a single user executing the trades» | [S21] frente a [S3] | media · `discrepancia` |
| ¿Varias cuentas? | Qualified: 5 por usuario (Zero, Standard o Direct); Advanced, 3. **Discrepancia**: [S22] limita a 3 si hay una Advanced activa; los Términos, si hay una Standard **o** una Advanced activa. Una persona por hogar. Evaluaciones: «no maximum total allocation limit» | «Only one username per individual is permitted, and one individual per household may use our services.» | [S22], [S3] | media · `discrepancia` |
| ¿VPS? | **Permitido para operar**; VPN, no. Durante el KYC, ni VPS ni VPN | «The use of VPS is permitted in your trading, however the use of VPN attempting to hide or change you IP address is not.» | [S20], [S25] | alta · verificado |
| Límites de frecuencia | **100 o más operaciones al día**: no las aceptan, automatizadas o no | «Alpha Futures & Alpha Prime team are not interested in working with strategies taking 100+ trades per day, automated or not.» | [S20], [S3] | alta · verificado |
| ¿HFT prohibido? | Sí | «restricts the use of automated systems designed for high-frequency trading (HFT)» | [S20] | alta · verificado |
| ¿Microscalping prohibido? (umbral) | Sí: operaciones de **menos de 10 ticks y menos de 2 min**, cuando son un patrón claro (el **50 % o más** del beneficio) | «"Tick or Micro Scalping" (trades less than 10 ticks AND less than 2 minutes)» | [S20] | alta · verificado |
| Técnicas de ejecución prohibidas | «All or nothing» (usar el DLL como stop); order book spamming; varias límite al mismo precio; brackets ajustados para aprovechar la falta de slippage; hedging (también NQ contra MNQ en la misma cuenta); account rolling o stacking; operar huecos o mercados ilíquidos; group trading | «Simultaneously placing multiple limit orders at the same price to manipulate order fills is prohibited.» | [S20] | alta · verificado |
| ¿Pueden anular beneficios? | **Sí**: anulación de los beneficios, rescisión inmediata y sin pasar a Qualified tras la revisión | «Profits generated from prohibited trading practices will be void.» | [S20] | alta · verificado |
| Diferencias entre evaluación, Qualified y Live | Las prohibiciones valen «in Evaluation and Qualified stages». En Alpha Prime (Live) se ofrece «Developing automated strategies with our in house Quantitative Team»: es un programa interno por invitación, **no** un permiso para bots del trader | ídem | [S20], [S28] | media · parcial |

---

## E. Plataformas

| Plataforma | ¿Soportada? | Cita | Fuente | Estado |
|---|---|---|---|---|
| **NinjaTrader 8** | **No** (no figura en ninguna lista) | «At Alpha Futures, our traders have their choice of using:» (siguen las cinco de abajo) | [S23], [S2] | verificado (ausencia en lista cerrada) |
| AlphaTrader (propia, web y móvil) | Sí; copiador integrado, límites de riesgo personales | «Our in house developed platform» | [S23], [S2] | verificado |
| TradingView | Sí, vía Plus500 (broker «Plus500US», modo demo); Pine Script e indicadores propios | «Connection powered by Plus500» | [S23], [S36], [S2] | verificado |
| WealthCharts | Sí; copiador integrado | «Built-In Trade Copier & OmniProp Support» | [S2] | verificado |
| DeepChart (Volumetrica) | Sí | «Deepchart by Volumetrica Trading» | [S23] | verificado |
| Quantower | Sí, por dxFeed («dxFeed Prop») y la cámara de Volumetrica | «Quantower is available via dxFeed and utilizing the Volumetrica Trading clearing house.» | [S35] | verificado |
| Rithmic · CQG · Tradovate | **No figuran** | — | [S23] | verificado (ausencia) |
| Sierra Chart · Bookmap · ATAS | **No figuran** | — | [S23] | verificado (ausencia) |
| APIs | **No lo dice la fuente oficial** (y la automatización está prohibida) | — | — | sin datos |
| Cambio de plataforma | No se puede después de comprar | «Please note, platform choices are not interchangeable after purchase.» | [S23], [S2] | verificado |
| Conexiones simultáneas | **No lo dice la fuente oficial** | — | — | sin datos |

---

## F. Elegibilidad internacional

| Campo | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| **República Dominicana** | **No figura** en la lista de países restringidos (actualizada el 12-8-2026). En el Caribe sí figuran Cuba, Haití y Jamaica. Ninguna página nombra a RD | «you need to be either a resident or a citizen of a non-restricted country» | [S24] | media · **parcial** (el silencio no es autorización) |
| Regla de presencia | Prohibido operar incluso de visita o de paso por un país restringido | «even if only visiting or traveling through any of the countries below, trading is not permitted» | [S24] | alta · verificado |
| Alcance | «more than 150 countries» | «Alpha Futures is available in more than 150 countries» | [S24] | alta · verificado |
| Edad y residencia | 18 años o más, residiendo en un país donde se ofrece el servicio | «only intended for persons over the age of 18 residing in the country for which the Services are available» | [S3] §7.3 | alta · verificado |
| KYC | Veriff: documento oficial y selfie, hecho por el titular en persona | «it is mandatory that the account holder personally completes the KYC requirements» | [S25] | alta · verificado |
| Cobrar desde RD | Transferencia, SWIFT, Wise o Rise (ACH solo EE. UU.), en USD; el proveedor cobra el cambio de moneda. Si cada método funciona en RD: **no lo dice la fuente oficial** | «An exchange rate fee, as set by the provider from time to time, applies when receiving Analyst Performance Fees in your domestic currencies.» | [S27], [S3] Anexo 4 §1.2.4 | media · parcial |
| Impuestos y formularios (W-8BEN u otros) | **No lo dice la fuente oficial** (los Términos no tratan impuestos ni formularios) | — | [S3] | — · sin datos |
| Regulación | No está regulada por la FCA ni por reguladores de EE. UU.; toda la actividad es simulada | «We are not registered with any U.S. federal or state financial regulatory authority.» | [S4] | alta · verificado |

---

## G. Fuentes

Todas consultadas el **2026-11-27** con `curl` (agente de usuario por defecto), sin seguir
redirecciones a otros hosts. Todas respondieron HTTP 200. Base del help center:
`https://intercom.help/alpha-futures-limited-f14467eeaf9c/en/articles/`. La columna «Fecha página» es
la que muestra el artículo; Intercom da algunas en relativo («hace más de N semanas»).

| # | Dato principal | URL | Fecha página | Fecha consulta | Confianza | Estado |
|---|---|---|---|---|---|---|
| S1 | Precios y tarjetas de los 4 planes; promociones; plazo de pago | https://alpha-futures.com/ | — | 2026-11-27 | alta | verificado |
| S2 | Plataformas | https://alpha-futures.com/platforms | — | 2026-11-27 | alta | verificado |
| S3 | Términos y condiciones (anexos 1–5, reglas virtuales, Performance Fees) | https://alpha-futures.com/terms-and-conditions | 27-07-2026 (efectivos) | 2026-11-27 | alta | verificado |
| S4 | Términos de uso (cláusula contra el acceso automatizado) | https://alpha-futures.com/terms-of-use | sin fecha visible | 2026-11-27 | alta | verificado |
| S5 | Devoluciones | https://alpha-futures.com/return-policy | — | 2026-11-27 | alta | verificado |
| S6 | Zero (parámetros) | https://intercom.help/alpha-futures-limited-f14467eeaf9c/en/articles/11771813-zero-account-overview | 28-10-2026 | 2026-11-27 | alta | verificado |
| S7 | Standard (parámetros) | https://intercom.help/alpha-futures-limited-f14467eeaf9c/en/articles/11632512-standard-account-overview | 27-07-2026 | 2026-11-27 | alta | verificado |
| S8 | Advanced (parámetros) | https://intercom.help/alpha-futures-limited-f14467eeaf9c/en/articles/11634907-advanced-account-overview | 22-07-2026 | 2026-11-27 | alta | verificado |
| S9 | Direct (parámetros) | https://intercom.help/alpha-futures-limited-f14467eeaf9c/en/articles/15838742-direct-account-overview | 09-07-2026 | 2026-11-27 | alta | verificado |
| S10 | Suscripción mensual | https://intercom.help/alpha-futures-limited-f14467eeaf9c/en/articles/9492068-monthly-subscription | 28-10-2026 | 2026-11-27 | alta | verificado |
| S11 | Resets | https://intercom.help/alpha-futures-limited-f14467eeaf9c/en/articles/9492077-reset | 28-10-2026 | 2026-11-27 | alta | verificado |
| S12 | MLL | https://intercom.help/alpha-futures-limited-f14467eeaf9c/en/articles/9491999-maximum-loss-limit-mll | 15-07-2026 | 2026-11-27 | alta | verificado |
| S13 | Daily Loss Guard | https://intercom.help/alpha-futures-limited-f14467eeaf9c/en/articles/9492014-daily-loss-guard | 15-07-2026 | 2026-11-27 | alta | verificado |
| S14 | Scaling Plan | https://intercom.help/alpha-futures-limited-f14467eeaf9c/en/articles/9492025-scaling-plan | 24-07-2026 | 2026-11-27 | alta | verificado |
| S15 | Consistencia | https://intercom.help/alpha-futures-limited-f14467eeaf9c/en/articles/9492048-consistency-rule | 27-07-2026 | 2026-11-27 | alta | verificado |
| S16 | Política de payout | https://intercom.help/alpha-futures-limited-f14467eeaf9c/en/articles/9492051-payout-policy | 27-07-2026 | 2026-11-27 | alta | verificado |
| S17 | Retiro máximo | https://intercom.help/alpha-futures-limited-f14467eeaf9c/en/articles/10491202-maximum-withdrawal-request | hace más de 3 semanas | 2026-11-27 | alta | verificado |
| S18 | Noticias | https://intercom.help/alpha-futures-limited-f14467eeaf9c/en/articles/9492063-news-trading-policy | 27-07-2026 | 2026-11-27 | alta | verificado |
| S19 | Horarios y productos (enlace al PDF de comisiones) | https://intercom.help/alpha-futures-limited-f14467eeaf9c/en/articles/9492096-what-and-when-you-can-trade | 17-07-2026 | 2026-11-27 | alta | verificado |
| S20 | Prácticas prohibidas y automatización | https://intercom.help/alpha-futures-limited-f14467eeaf9c/en/articles/9508585-prohibited-trading-practices | hace más de 1 semana | 2026-11-27 | alta | verificado |
| S21 | Copy trading | https://intercom.help/alpha-futures-limited-f14467eeaf9c/en/articles/10573989-copy-trading | 17-07-2026 | 2026-11-27 | alta | verificado |
| S22 | Asignación máxima | https://intercom.help/alpha-futures-limited-f14467eeaf9c/en/articles/9492088-maximum-allocation | 27-07-2026 | 2026-11-27 | alta | verificado |
| S23 | Plataformas (help) | https://intercom.help/alpha-futures-limited-f14467eeaf9c/en/articles/10525305-trading-platforms | 30-09-2026 | 2026-11-27 | alta | verificado |
| S24 | Países restringidos | https://intercom.help/alpha-futures-limited-f14467eeaf9c/en/articles/9523389-countries-with-limitations | 12-08-2026 | 2026-11-27 | alta | verificado |
| S25 | KYC | https://intercom.help/alpha-futures-limited-f14467eeaf9c/en/articles/9867976-completing-kyc | 08-07-2026 | 2026-11-27 | alta | verificado |
| S26 | Activar la Qualified | https://intercom.help/alpha-futures-limited-f14467eeaf9c/en/articles/9820801-activating-your-qualified-account | hace más de 2 semanas | 2026-11-27 | alta | verificado |
| S27 | Métodos de payout | https://intercom.help/alpha-futures-limited-f14467eeaf9c/en/articles/10443600-payout-methods | 27-05-2025 | 2026-11-27 | media | parcial |
| S28 | Camino a Live y Alpha Prime | https://intercom.help/alpha-futures-limited-f14467eeaf9c/en/articles/10743344-path-to-live-structure | hace más de 2 semanas | 2026-11-27 | alta | verificado |
| S29 | Reglas Live (antiguas) | https://intercom.help/alpha-futures-limited-f14467eeaf9c/en/articles/11023753-live-account-rules-and-parameters | 20-06-2026 | 2026-11-27 | media | verificado |
| S30 | Pausa tras perder la Live | https://intercom.help/alpha-futures-limited-f14467eeaf9c/en/articles/15855255-live-cool-down-period | 07-07-2026 | 2026-11-27 | alta | verificado |
| S31 | Límites de precio | https://intercom.help/alpha-futures-limited-f14467eeaf9c/en/articles/9806068-price-limit-trading | 30-08-2024 | 2026-11-27 | alta | verificado |
| S32 | Inactividad | https://intercom.help/alpha-futures-limited-f14467eeaf9c/en/articles/12757982-inactivity-rule | 05-11-2025 | 2026-11-27 | alta | verificado |
| S33 | Pagos de terceros | https://intercom.help/alpha-futures-limited-f14467eeaf9c/en/articles/10126067-third-party-payments | 13-11-2024 | 2026-11-27 | alta | verificado |
| S34 | Pagos con cripto | https://intercom.help/alpha-futures-limited-f14467eeaf9c/en/articles/13709629-crypto-payments | 25-03-2026 | 2026-11-27 | alta | verificado |
| S35 | Quantower | https://intercom.help/alpha-futures-limited-f14467eeaf9c/en/articles/14135839-getting-started-with-quantower | 20-03-2026 | 2026-11-27 | alta | verificado |
| S36 | TradingView | https://intercom.help/alpha-futures-limited-f14467eeaf9c/en/articles/10525620-how-to-trade-with-tradingview | 30-09-2026 | 2026-11-27 | alta | verificado |
| S37 | Índice y 5 colecciones del help center | https://intercom.help/alpha-futures-limited-f14467eeaf9c/en/ | — | 2026-11-27 | alta | verificado |

También se leyeron, sin datos que cambien la ficha, las guías de AlphaTrader, DeepChart y WealthCharts.

### Discrepancias abiertas (resumen)
1. MLL de la Advanced Qualified 50K: $1,750 ([S8], [S1]) frente a «4%» ($2,000) en el Anexo 2 de
   [S3]. Prevalece la web (§1.4).
2. Plazo de pago: «five business days or less» ([S1]) frente a «within 3 Business Days» ([S3]).
3. DLG en la evaluación Zero: sí ([S6], [S13], [S1]) frente a «Qualified Analyst Accounts only» ([S3]).
4. Copy trading: entre cuentas propias ([S21]) frente a solo «from your own external account» ([S3]).
5. Límite de 3 Qualified: con una Advanced activa ([S22]) frente a con una Standard o una Advanced ([S3]).
6. Días del Direct: sin requisito ([S16]) frente a 5 días mínimos ([S3] Anexo 2).
7. Reset de la evaluación: precio propio, sin cambiar la fecha de renovación ([S11]), frente a «paying
   an additional monthly evaluation fee» con cambio de fecha ([S3] §7.4.1(h)).
8. Métodos de payout: listas distintas en [S27] y [S3].
9. Alcance del código `ALPHA50` («50% off»): no se dice ([S1]).

### Páginas que no se pudieron leer o que quedan incompletas
- Ninguna respondió 403 ni otro error.
- **`help.alpha-futures.com`** (dominio canónico del help center): no está entre los hosts permitidos.
  Se leyeron los mismos artículos en `intercom.help/alpha-futures-limited-f14467eeaf9c/` (el help center
  oficial que sirve Intercom, permitido por el coordinador).
- **«Permitted Products and Fees.pdf»** (comisiones por contrato), en
  `alpha-futures-limited-e4a6e0d6046c.intercom-attachments-1.com`: host no permitido; no se leyó →
  comisiones **Sin datos**.
- **`app.alpha-futures.com`** (dashboard, contrato de la Qualified, checkout): no se intentó.
- `consistencycalculator.alpha-futures.com` y ForexFactory: no se siguieron.

### Aviso de método: término contra el acceso automatizado (descargas detenidas)
- Los Términos de uso de Alpha Futures (https://alpha-futures.com/terms-of-use, lista de usos
  prohibidos) dicen: «use, launch, develop, or distribute any automated system, including without
  limitation, any AI, spider, robot, cheat utility, scraper, or offline reader that accesses the Site».
  Y también: «using any data mining, web scraping robots, or similar data gathering and extraction
  tools».
- Esos Términos se descargaron en la última tanda, junto con la portada de plataformas y las
  devoluciones. Para entonces ya se habían descargado unas 45 páginas: portada, índice, 5 colecciones,
  34 artículos y 4 páginas legales o de producto, una a una y con pausas. En cuanto el coordinador
  fijó la regla, **no se hizo ninguna petición más** a Alpha Futures ni a su help center. Que las
  descargas ya hechas sean compatibles con esa cláusula lo decide el operador.
- **Lo que queda pendiente necesita que el operador lo lea con un navegador**, o que pregunte a
  soporte: (a) las comisiones por contrato (el PDF); (b) el coste de los datos de mercado en
  evaluación y Qualified; (c) si `ALPHA50` vale para 50K y hasta cuándo; (d) el reset del Direct;
  (e) si el extra de $70 de Standard es un pago único o mensual; (f) si cada método de cobro funciona
  en República Dominicana, y la fiscalidad; (g) las discrepancias de arriba.
- No se creó ninguna cuenta, no se aceptaron términos y no se abrió ningún enlace de registro.
