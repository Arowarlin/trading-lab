# TradeDay · ficha de reglas de fondeo (investigación 2026-11)

- **ID**: `tradeday` · **Fecha de consulta**: 2026-11-27 · **Cuenta de referencia**: 50K.
- **Programas analizados**: dos evaluaciones, **Quick Pay** (QP) y **Fast Pass** (FP), en tres
  formatos de drawdown a 50K: **QP Intraday**, **QP End of Day (EOD)** y **FP EOD**. Cada uno se vende
  en dos variantes de plataforma: **Tradovate** (enlace `50k-ot-…`) y **RM** (enlace `50k-ot-rm-…`).
  En la portada, las tarjetas con enlace `-rm-` llevan la etiqueta «Rithmic» y las otras «Tradovate»,
  así que **RM = Rithmic** (lectura de la estructura de [S1]; la firma no define la sigla) · confianza
  alta · estado verificado. Son **6 variantes**, con una subsección cada una (§1 a §6).
  Fase siguiente: Funded Sim → Funded Live.
- **Fuentes**: portada, «How it works» y Términos de `www.tradeday.com` («Last Modified: August 11,
  2026») y **todo** el help center oficial `tradeday.freshdesk.com` (79 artículos en 8 carpetas). Se
  amplía y corrige §3 de `docs/futures/research/prop_firms_2026-11-27.md`, que estaba `parcial`.
- **Formato de cada dato**: valor · «cita literal» · [S#] (URL exacta y fecha en §G) · confianza ·
  estado. Todo se consultó el 2026-11-27. Lo que es aritmética sobre cifras oficiales se marca
  **(cálculo propio)**. Freshdesk muestra «Modified on Tue, 1 Sep» sin año cuando es del año en curso;
  esas fechas se leen como 2026.

## Resumen (50K)

| Campo | Valor |
|---|---|
| **Automatización** | **Permitida con condiciones**: un sistema propio (no comprado a terceros) en una plataforma soportada (NinjaTrader, Tradovate, TradingView, Jigsaw o Quantower); sin API; **sin VPS**; no más de 200 operaciones al día (más de 200 está prohibido); sin microscalping (operaciones de menos de 10 s que dominen la cuenta) ni order splitting. TradeDay confisca los beneficios obtenidos con prácticas prohibidas |
| **NinjaTrader 8** | **Sí, solo en las variantes Tradovate** (NT8 gratuito sobre Tradovate/CQG). **No en las RM**: «we do not support NinjaTrader Desktop with Rithmic accounts». NinjaScript y ATM no se nombran: permitidos de forma implícita, como ATS en NinjaTrader · parcial |
| **República Dominicana** | **No figura** en la lista de países prohibidos (actualizada el 1-10-2026). No hay confirmación positiva; el KYC lo hacen Riseworks, el bróker y el FCM. Estado: **parcial** (ausencia en la lista) · confianza media |
| Coste hasta la primera cuenta financiada, mejor caso (pago único, sin activación) | QP Intraday **$124** lista / **$49** promo · QP EOD **$174** / **$69** · FP EOD **$248** / **$99**. Promoción `SALE60` hasta «2026-12-01 6:00». Iguales en Tradovate y RM |
| Reparto / mínimo / máximo / frecuencia | **QP**: 50/50 por debajo de $4,000 de beneficio actual y 80/20 por encima · mínimo $250 · máximo **no lo dice la fuente oficial** · desde el día 1, cualquier día. **FP**: 80/20 · mínimo $250 · máximo 50 % del saldo con tope de **$1,500** · cada 5 días rentables de $150 o más. **Funded Live**: 90/10 |
| Comisiones por lado | NQ **$2.88** · MNQ **$0.95** (ida y vuelta: $5.76 y $1.90, cálculo propio) |
| Tasa de aprobados | 36 % de enero a junio de 2026, según la propia firma ([S1]) |

---

## Variantes 50K (registro y precio)

| § | Variante | Drawdown en evaluación | Drawdown en Funded Sim | Plataforma | Enlace de registro (no leído) | Lista → promoción |
|---|---|---|---|---|---|---|
| 1 | QP Intraday · Tradovate | $2,000 intradía | $2,000 intradía | Tradovate/CQG | `members.tradeday.com/en/user_registration/50k-ot-intraday-evaluation-qp` | $124 → $49 |
| 2 | QP Intraday · RM | $2,000 intradía | $2,000 intradía | Rithmic | `…/50k-ot-rm-intraday-evaluation-qp` | $124 → $49 |
| 3 | QP EOD · Tradovate | $2,000 EOD | **$2,000 intradía** | Tradovate/CQG | `…/50k-ot-eod-evaluation-qp` | $174 → $69 |
| 4 | QP EOD · RM | $2,000 EOD | **$2,000 intradía** | Rithmic | `…/50k-ot-rm-eod-evaluation-qp` | $174 → $69 |
| 5 | FP EOD · Tradovate | $2,000 EOD | $2,000 EOD | Tradovate/CQG | `…/50k-ot-eod-evaluation-fp` | $248 → $99 |
| 6 | FP EOD · RM | $2,000 EOD | $2,000 EOD | Rithmic | `…/50k-ot-rm-eod-evaluation-fp` | $248 → $99 |

Fuente: tarjetas de precios de [S1], leídas en el HTML (cada tarjeta enlaza a su registro y lleva la
etiqueta de plataforma y de programa) · confianza alta · verificado. Una misma persona no puede
mezclar brókers: «you cannot have a 50k evaluation on Tradovate and a 50k evaluation on Rithmic» [S21].

---

## A. Costes (50K)

### A.0 Común a las 6 variantes

| Concepto | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Modalidad | **Pago único**, sin suscripción | «No subscription required - one-time fee only» | [S1] | alta · verificado |
| Activación | **$0** | «There are no activation fees, and you can purchase a new evaluation account after failing.» | [S6], [S7] | alta · verificado |
| Promoción vigente | 60 % de descuento con el código `SALE60`; contador hasta «2026-12-01 6:00» (zona horaria no indicada) | «November Sale 60% off + no activation fee … Use code SALE60» | [S1] | alta · verificado (temporal) |
| Reset | **Discrepancia**. Help center y portada: tras fallar se compra una cuenta nueva. Términos: reset de **$99** o reinicio con la siguiente cuota mensual (texto de cuando había suscripción) | «the cost of a reset is $99» | [S3] frente a [S6], [S51] | media · parcial |
| Datos de mercado (evaluación y Funded Sim) | Nivel 1 de CME gratis; nivel 2 opcional, **$49/mes** (paquete de todas las bolsas, mes natural) | «Level 1 (Top of Book) market data for all CME Exchanges is free to traders on evaluations.» | [S27] | alta · verificado |
| Datos de mercado (Funded Live) | **$156/mes por bolsa** (profesional); Tradovate cobra además $2/mes por procesar la tarjeta | «Market data is $156 per month, per Exchange for Funded Live traders.» | [S27], [S28] | alta · verificado |
| Comisiones (evaluación, Funded Sim y Live) | Por contrato y por lado, todo incluido: **NQ $2.88 · MNQ $0.95** · ES $2.88 · MES $0.95 · MGC $1.20 | «Prices are per lot traded (per side), and include brokerage fee, NFA fee, Clearing fee and Exchange fee.» | [S26] | alta · verificado |
| Licencia NT8 | Gratis en evaluación y financiada; una licencia propia no rebaja las comisiones | «Q. What are the costs of NinjaTrader when I am funded? A. Free» | [S24] | alta · verificado |
| Otras plataformas | TradingView y Jigsaw con licencia propia; Bookmap, Sierra Chart y la mayoría de plataformas Rithmic también; ATAS y R\|Trader Pro con licencia gratuita | «TradingView & Jigsaw (You will need your own license for each)» | [S23] | alta · verificado |
| API | No hay: «We do not make platform APIs available to traders.» | ídem | [S19] | alta · verificado |
| Cuota mensual una vez financiado | Ninguna | «we will not charge you the monthly membership fee to TradeDay» | [S28] | alta · verificado |
| Cargos por retiro (Riseworks) | Transferencia EE. UU. gratis · **transferencia internacional $15** · cripto L1 $2.5 más gas · cripto L2 gratis | «International bank wire withdrawals: $15/withdrawal» | [S40], [S33] | alta · verificado |
| Reembolso | En general no. Excepción: en las primeras 72 h, sin operar ni conectar plataformas de terceros, con un 20 % de deducción. Si falla el KYC tras aprobar, se devuelve la evaluación aprobada | «there is a 20% deduction in the refund» | [S46], [S44] | alta · verificado |
| Inactividad | Sin cuota. Tradovate archiva la cuenta tras un mes natural sin iniciar sesión (cuenta perdida); 30 días sin actividad → posible baja | «any TradeDay account that remains dormant or inactive for 30 days will be considered inactive and may be offboarded.» | [S45] | alta · verificado |

**Mantener la cuenta financiada** (cálculo propio con las cifras de arriba):

| Fase | 3 meses | 6 meses |
|---|---|---|
| Funded Sim (todas las variantes) | **$0** fijos ($147 con L2) | **$0** ($294 con L2) |
| Funded Live, solo CME (NQ/MNQ) | **$468** ($474 con el cargo de $2/mes de Tradovate) | **$936** ($948) |

A esto se suman las comisiones, que se descuentan del P&L.

### A.1 a A.6 por variante (coste hasta la primera Funded Sim, 1 intento, mejor caso)

| § | Variante | Lista | Con `SALE60` | Con L2 durante el mes de la evaluación (opcional) |
|---|---|---|---|---|
| 1 | QP Intraday · Tradovate | **$124** | **$49** | +$49 |
| 2 | QP Intraday · RM | **$124** | **$49** | L2 en Rithmic: **no lo dice la fuente oficial** (el paquete de $49 se compra en Tradovate) |
| 3 | QP EOD · Tradovate | **$174** | **$69** | +$49 |
| 4 | QP EOD · RM | **$174** | **$69** | ídem §2 |
| 5 | FP EOD · Tradovate | **$248** | **$99** | +$49 |
| 6 | FP EOD · RM | **$248** | **$99** | ídem §2 |

Cita de los precios: «Intraday 50k $ 124 $ 49 one-time fee» · «End of Day … 50k $ 174 $ 69» ·
«End of Day 50k $ 248 $ 99» [S1] · alta · verificado.
**Discrepancia** con la tabla del help center (modificada el 1-9-2026): QP EOD $175, QP Intraday $125,
**Fast Pass $180** [S4]. La portada de hoy es más reciente, así que prevalece; la diferencia de Fast
Pass ($248 frente a $180) es material · confianza media · `discrepancia`.

---

## B. Reglas de trading

### B.0 Común a las 6 variantes

| Regla | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Objetivo de beneficio | **$3,000** netos de comisión simulada | «in the $50k evaluation, the balance starts at $50,000, and the profit target is $3,000» | [S5], [S6], [S7] | alta · verificado |
| Drawdown máximo | **$2,000**, trailing. Deja de subir al llegar al saldo inicial ($50,000) | «Trailing max drawdown limits continues to trail your account growth until they reach the starting account balance.» | [S9] | alta · verificado |
| Cumplimiento del drawdown | En tiempo real, también en las cuentas EOD: la equidad intradía no puede cruzar el nivel vigente | «you must never let your equity fall below the active drawdown level at any point during the day» | [S9] | alta · verificado |
| DLL | **No hay DLL de la firma** («TradeDay has just one rule»). El trader puede fijar en Tradovate límites diarios o semanales propios, que no se pueden levantar en la sesión | «You can set a Daily Loss Limit, Weekly Loss Limit … directly in Tradovate.» | [S5], [S47] | alta · verificado |
| Contratos máximos (evaluación) | **5 contratos o 50 micros**, combinables; los micros nunca pasan de 50 | «we limit the maximum Micro position to 50 lots» | [S13], [S1] | alta · verificado |
| Infracciones accidentales | No se suspende por exceder sin querer horarios, productos o tamaño; quien abusa pierde la cuenta | «We do not fail a trader for accidental breaches of these three guidelines» | [S5] | alta · verificado |
| Productos | Solo CME, CBOT, COMEX y NYMEX, de una lista cerrada (incluye NQ, MNQ, ES, MES, GC, MGC) | «TradeDay only allows its traders to trade the CME Group futures products» | [S14] | alta · verificado |
| Horario y cierre | Día de 17:00 a 16:00 CT. Estar plano **10 min antes del cierre**: liquidación automática a las 15:50 CT. Se permite operar de noche dentro de la sesión; nada de pasar el cierre | «Exit all positions 10 minutes before the close. No holding positions when the market closes.» | [S12] | alta · verificado |
| Overnight y fin de semana | No se puede mantener una posición más allá del cierre diario, así que tampoco el fin de semana | «Traders cannot carry positions into the close» | [S12] | alta · verificado |
| Noticias | Prohibido operar las publicaciones Tier 1: FOMC (13:00 CT), CPI y NFP (7:30 CT), y otras por producto. Liquidación automática **2 min antes**, reapertura 2 min después | «TradeDay will auto-liquidate all open positions 2 minutes before TradeDay's tier 1 economic data releases» | [S15] | alta · verificado |
| Efecto de operar noticias | No suspende si es accidental. Al perder una cuenta financiada, no se devuelven los beneficios de operar Tier 1 | «All profits from trading tier 1 data releases, trading in breach of our permitted times.» | [S15], [S29] | alta · verificado |
| Límite de precio (financiadas) | Prohibido operar a menos del 2 % de un límite de precio de CME, bajo pena de perder la cuenta | «Funded Traders are not permitted to trade within 2% of a price limit.» | [S48], [S29] | alta · verificado |
| Días mínimos «normales» | En los días mínimos hay que operar igual que antes; nada de «sentarse en la zona de fondeo» con 1 micro | «NO sitting in a funding zone scratching 1 lot micros.» | [S11] | alta · verificado |
| **Discrepancia (Términos)** | Los Términos aún hablan de «minimum 7-day period», «Day-trading only» y solo de drawdown EOD; el help center actual dice 5 días (QP) o 3 (FP) y ofrece drawdown intradía | «reach profit targets set for you over a minimum 7-day period» | [S3] | media · `discrepancia` |
| Cuenta Funded Live | Partida nueva, con regla de slippage: liquidación si el saldo baja del colchón (**$500** en 50K) | «$25K & $50K account: $500» | [S39] | alta · verificado |

### §1 · QP Intraday 50K · Tradovate

| Regla | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Tipo de drawdown (evaluación) | **Trailing intradía**: sigue el máximo de equidad, P&L no realizado incluido | «the TMD limit is calculated on unrealized profits within the trading day, in real-time» | [S8] | alta · verificado |
| Drawdown en Funded Sim | Intradía, $2,000. Se calcula sobre el **beneficio bruto** (beneficio actual + retiros), así que sigue subiendo aunque se retire | «the TMD is calculated off of gross profits, not the net profits» | [S6], [S31] | alta · verificado |
| Dónde se bloquea | En el saldo inicial ($50,000) | ver B.0 | [S9], [S34] | alta · verificado |
| Consistencia (evaluación) | **30 %**: ningún día puede pasar del 30 % del beneficio total. No suspende; sube el objetivo (mejor día ÷ 0.30) | «No day greater than 30% of your total profits.» | [S5], [S10] | alta · verificado |
| Consistencia (Funded Sim) | **Ninguna** | «Consistency: None» | [S1], [S6] | alta · verificado |
| Días mínimos (evaluación) | **5** (no consecutivos) | «Trade for a minimum of 5 trading days.» | [S5], [S11] | alta · verificado |
| Contratos en Funded Sim | 5 contratos o 50 micros (los mismos que en la evaluación) | «Position Limit: 5 Contracts (50 Micros)» | [S1] | alta · verificado |
| Escalado | Ninguno en Funded Sim. En Funded Live depende del saldo que se lleve: $0–3K → 2 minis/20 micros; $3K–6K → 3/30; $6K–10K → 4/40 | tabla «Balance brought over · Mini · Micro · Slippage» | [S38] | alta · verificado |
| Tope de beneficio en Funded Sim | Revisión al llegar a **$10,000 de beneficio bruto**: la cuenta se pausa a las 16:30 CT y se recorta lo que pase del umbral | «any excess profits above the threshold will be removed» | [S36] | alta · verificado |

### §2 · QP Intraday 50K · RM (Rithmic)

Mismas reglas que §1 ([S1]: tarjeta idéntica salvo la etiqueta «Rithmic»; [S5], [S6]). Diferencias:
la plataforma (§E: sin NinjaTrader Desktop) y la conexión «Rithmic Paper Trading», gateway Chicago
Area [S25]. El help center **no** publica reglas propias de RM · confianza alta · verificado.

### §3 · QP EOD 50K · Tradovate

| Regla | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Tipo de drawdown (evaluación) | **Trailing EOD**: sube solo con el saldo realizado al cierre de las 16:00 CT; se cumple en tiempo real | «calculates the maximum drawdown from the realized profits on the end-of-day balance (at the 16.00 CT futures market close)» | [S8], [S9] | alta · verificado |
| Drawdown en Funded Sim | **Pasa a intradía**, $2,000, sobre beneficio bruto | «All Quick Pay Funded Sim accounts will have an intraday drawdown, regardless of the drawdown had on the evaluation.» | [S29], [S1] | alta · verificado |
| Consistencia, días, contratos, escalado, tope de $10,000 | Igual que §1: 30 % en evaluación, ninguna en Funded Sim, 5 días, 5/50, revisión a $10,000 brutos | «Consistency 30% · Min Trading Days 5» | [S1], [S5], [S36] | alta · verificado |

### §4 · QP EOD 50K · RM (Rithmic)

Mismas reglas que §3 (tarjeta idéntica con la etiqueta «Rithmic» [S1]). Única diferencia: plataforma
Rithmic, sin NinjaTrader Desktop (§E) · alta · verificado.

### §5 · FP EOD 50K · Tradovate

| Regla | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Tipo de drawdown | **EOD** en la evaluación **y** en la Funded Sim | «All drawdowns are calculated at the End-of-Day.» · «Funded Sim account with the same End of Day drawdown» | [S5], [S7] | alta · verificado |
| Bloqueo del drawdown al primer retiro | Si aún no ha llegado al saldo inicial, sube hasta él y se queda fijo | «it will automatically move up to the starting account balance and remain fixed there moving forward» | [S32] | alta · verificado |
| Consistencia (evaluación) | **45 %** | «No day greater than 45% of your total profits.» | [S5], [S10] | alta · verificado |
| Consistencia (Funded Sim) | **45 % del beneficio bruto** para las cuentas abiertas desde el 26-7-2026; antes no había | «no single day can make up more than 45% of your total gross profits» | [S32] | alta · verificado |
| Días mínimos (evaluación) | **Discrepancia**: 3 en [S5] y en la tarjeta de [S1], «no minimum trading days» en [S7] y «No minimum on Fast Pass» en [S2]. Con un 45 % de consistencia, en la práctica son 3 días | «Objective 1: 3 Minimum Trading days» | [S5] frente a [S7], [S2] | media · `discrepancia` |
| Contratos (evaluación) | 5 contratos o 50 micros | «Position Limits - 5 Contracts (50 Micros)» | [S1], [S7] | alta · verificado |
| Contratos y escalado (Funded Sim) | Empieza con **2 contratos (20 micros)** y suma 1 por cada $2,000 de beneficio al cierre. Máximo a 50K: **no lo dice la fuente oficial** (a 25K pone «max 2 minis») | «scales +1 contract per $2k profit at EOD» | [S1], [S7] | alta · parcial (máximo) |
| Paso a Funded Live | En la **5.ª solicitud de payout**, o antes a criterio de TradeDay. Cuenta Live nueva con saldo $0 y 2 contratos | «You will be moved to funded live on your fifth payout request.» | [S7], [S37] | alta · verificado |
| **Discrepancia del drawdown en Live** | «the same End of Day drawdown from your original account tier» ($2,000), pero el ejemplo de 50K dice «the TMD is $1500» | ídem | [S37], [S38] | media · `discrepancia` |

### §6 · FP EOD 50K · RM (Rithmic)

Mismas reglas que §5 (tarjeta idéntica con la etiqueta «Rithmic» [S1]). Única diferencia: plataforma
Rithmic, sin NinjaTrader Desktop (§E) · alta · verificado.

---

## C. Payouts

### C.0 Común

| Campo | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Solicitud | Funded Sim: botón «Request Withdrawal» del dashboard (solo aparece si se cumplen los requisitos). Funded Live: por email a fundedtrader@ | «If you are not eligible for a payout, the button will not appear.» | [S35] | alta · verificado |
| Aprobación | La **primera** solicitud pasa una revisión de seguridad (prácticas prohibidas); en las solicitudes puede haber control de IP y VPN | «All first payout requests are run through our security processes» | [S18], [S20] | alta · verificado |
| Proceso | Solicitudes antes de las **17:30 CT**: procesadas en 24 h (días hábiles). **Discrepancia**: [S31] dice «5:30 pm ET» | «Requests received before 5:30 pm CT will be processed within 24 hours (business days only).» | [S35], [S33] frente a [S31] | media · `discrepancia` (CT/ET) |
| Recibido | Tras el proceso, un email pide entrar en Riseworks y retirar. Plazo desde Riseworks hasta el banco: **no lo dice la fuente oficial** | «you will receive a confirmation email instructing you to log into your Riseworks account to withdraw the funds» | [S35] | alta · parcial |
| Métodos | Riseworks: transferencia bancaria o cripto (USDC en Arbitrum, entre otros) | «Riseworks has 2 options for payouts: Bank wire and Crypto.» | [S40] | alta · verificado |
| KYC | Riseworks y, para Live, bróker y FCM: documento oficial y justificante de domicilio (extracto bancario o factura) | «You will also be required to provide a bank statement or utility bill as proof of address, and a government-issued ID.» | [S43], [S41] | alta · verificado |
| Transición a Live | KYC y AML del bróker; alta en unos 5 días; 30 días para entregar los documentos; datos profesionales a $156/mes por bolsa | «Setting up takes around five days» | [S30], [S45] | alta · verificado |
| Pérdida de una Live | 3 meses sin poder hacer evaluaciones | «a mandatory 3-month cooling-off period» | [S6], [S37] | alta · verificado |
| Solicitud nueva sobre una pendiente | La nueva sustituye a la anterior | «the new request will override the previous one» | [S35] | alta · verificado |
| **Discrepancia (buffer)** | [S35] dice «traders must have cleared the Buffer Zone», mientras [S1], [S6] y [S32] dicen «No Payout Buffer» en Funded Sim | ídem | [S35] frente a [S6] | media · `discrepancia` (texto antiguo) |

### §1–§4 · Quick Pay (Intraday y EOD; Tradovate y RM: mismas reglas de payout)

| Campo | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Días necesarios | **1** | «You can request your first payout after just one day of trading» | [S6], [S1] | alta · verificado |
| Beneficio mínimo por día | Ninguno; basta con tener beneficio | «A trader can request a payout as soon as the account has any positive profit.» | [S33] | alta · verificado |
| Número de retiros | Sin límite declarado (cualquier día con saldo positivo) | «you can withdraw at any time as long as your account balance is positive» | [S6] | alta · verificado |
| Mínimo | **$250** | «The minimum payout request is $250» | [S31] | alta · verificado |
| Máximo por retiro | **No lo dice la fuente oficial**; nunca por debajo del saldo inicial | «You cannot withdraw below the starting account balance at any time.» | [S33] | alta · parcial |
| Reparto (Funded Sim) | **50/50** con menos de $4,000 de beneficio actual; **80/20** en la parte que deja más de $4,000; reparto proporcional si una solicitud cruza el umbral. Se calcula por cuenta | «Below the $4,000 current profit level, payouts are split 50/50.» | [S6], [S31] | alta · verificado |
| Buffer | Ninguno en Funded Sim | «no payout buffer» | [S6] | alta · verificado |
| Tope acumulado | Revisión a **$10,000 brutos** (recorte del exceso) y, casi siempre, paso a Live; el traspaso puede tardar hasta 10 días hábiles | «Once approved for Funded Live, the transfer may take up to 10 business days to complete.» | [S36] | alta · verificado |
| Traspaso a Live | Lo que queda en la cuenta se traspasa aplicando el reparto (80/20 sobre $4,000, 50/50 por debajo); el drawdown en Live arranca en $0 | «The maximum drawdown limit will be set to $0.» | [S34] | alta · verificado |
| Reparto en Live (QP) | 50 % sobre el colchón traspasado y **90 %** sobre el beneficio nuevo | «Any profit earned above the required buffer is subject to a 90% split.» | [S38] | alta · verificado |

### §5–§6 · Fast Pass (Tradovate y RM: mismas reglas de payout)

| Campo | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Días necesarios | **5 días rentables**, no consecutivos, en cada ciclo | «The trader must complete a minimum of 5 individual profitable trading days» | [S32] | alta · verificado |
| Beneficio mínimo por día | **$150** a 50K | «$50K Account: 5 days with at least $150 profit per day» | [S32] | alta · verificado |
| Otras condiciones | Saldo por encima del inicial; beneficio neto desde el retiro anterior; consistencia del 45 % (cuentas desde el 26-7-2026); no operar hasta cobrar | «Once you submit a payout request, do not resume trading until you have received your payout.» | [S32] | alta · verificado |
| Mínimo | **$250** | «The minimum payout request amount is $250» | [S32] | alta · verificado |
| Máximo por retiro | 50 % del saldo, con tope de **$1,500** (cuentas abiertas desde el 26-7-2026; antes, $2,000). Los ejemplos aplican el 50 % al beneficio, no a los $50,000: **ambiguo** | «$1,500 on a 50K» | [S32], [S1] | alta · verificado (tope) / media (base del 50 %) |
| Reparto | **80/20** en Funded Sim · **90/10** en Live | «All Funded Sim payouts are made at an 80/20 profit split.» | [S7], [S32] | alta · verificado |
| Número de retiros en Sim | A la **5.ª solicitud** la cuenta pasa a Live (tope práctico: 5 en Sim) | «Upon a trader's 5th payout request, the Funded Sim account will transition to a Funded Live account.» | [S37] | alta · verificado |
| Buffer en Live | Saldo inicial $0; retiro posible al llegar a **$2,000**; suelo protegido de $500 | «To clear the buffer, you need to grow the account to $2000» | [S37] | alta · verificado (con la discrepancia del drawdown de §5) |

---

## D. Automatización (crítico) · común a las 6 variantes

**Veredicto: permitida con condiciones, riesgo medio.** Encaja un bot propio en NinjaScript sobre
NT8 conectado por Tradovate (variantes §1, §3 y §5), ejecutado en el PC del trader desde la dirección
registrada (sin VPS), con no más de 200 operaciones al día (más de 200 está prohibido), operaciones de más de 10 s, sin order
splitting, plano 10 min antes del cierre y fuera de las noticias Tier 1. En las variantes RM (§2, §4 y
§6) NT8 no sirve; solo quedarían las plataformas Rithmic.

| Pregunta | Respuesta | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| ¿Bots y estrategias automáticas? | **Sí, si son propios** y en una plataforma soportada | «To use an automated trading system, you must use one of the platforms we support: NinjaTrader, Tradovate, TradingView, Jigsaw and Quantower.» | [S19] | alta · verificado |
| ¿Bots de terceros? | **Prohibidos**; si varios usuarios hacen las mismas operaciones, se cierran todas las cuentas | «Algos and Bots purchased from a third party and employed by the trader are forbidden.» | [S19], [S18], [S3] | alta · verificado |
| ¿NT8 Automated Strategies / NinjaScript? | No se nombran. NinjaTrader figura entre las plataformas válidas para un ATS, así que una estrategia NinjaScript propia queda permitida **de forma implícita**. Solo con cuentas Tradovate/CQG | ver la fila anterior y §E | [S19], [S23] | media · parcial |
| ¿ATM Strategies? | **No lo dice la fuente oficial**. [S17] da por normales las salidas troceadas por NT («NinjaTrader trailing stop features») | «This can occur due to platform order management and does not automatically indicate order splitting.» | [S17] | media · parcial |
| ¿API? | **No** (tampoco la de Tradovate) | «TradeDay does not expose the Tradovate API to allow traders to connect automated trading systems directly.» | [S19] | alta · verificado |
| ¿Copiadores? | **Sí**: de una cuenta personal externa a TradeDay, y entre 2 y 10 cuentas de evaluación o Funded Sim; entre un máximo de 5 Live. **No** entre Live y Sim o evaluación, ni con posiciones abiertas a la vez en ambas | «Funded Live, Evaluation & Funded Sim: Copy trading between these account types is not permitted.» | [S22], [S21] | alta · verificado |
| ¿Varias cuentas? | Hasta **10**, con 5 Funded Sim activas (el resto en cola) y 5 Funded Live; un solo bróker; un usuario por hogar; no se compran más con una Live activa. **Discrepancia interna** en [S22]: «10 … across all account types» frente a «max of 10 evaluation accounts, 5 Funded Sim … 5 Funded live» | «Traders can have up to 10 accounts at any one time.» | [S21], [S22] | alta · verificado (con discrepancia menor) |
| ¿VPS? | **Prohibido**; VPN y enmascarar la IP, también. Hay controles de IP al pasar a Live, en las solicitudes de payout y en la revisión de $10,000 | «TradeDay does not allow the use of virtual private servers (VPS)» | [S20], [S18] | alta · verificado |
| Límites de frecuencia | **Más de 200 operaciones al día, prohibido** | «We do not allow strategies that produce more than 200 trades in a day.» | [S18], [S16], [S3] | alta · verificado |
| ¿HFT prohibido? | Sí: «automated trading systems designed to scalp at an extremely high frequency» | ídem | [S16], [S18] | alta · verificado |
| ¿Microscalping prohibido? (umbral) | Sí: operaciones de menos de **10 s** (orientativo: 5–10 s) cuando dominan la cuenta por número o por beneficio. Ejemplo sancionable: 72 % del beneficio en operaciones de menos de 10 s. También «Strategies that trade in a few seconds, designed to capture just a couple of ticks» | «positions are opened and closed within extremely short timeframes, typically under 10 seconds» | [S17], [S16] | alta · verificado |
| Técnicas de ejecución prohibidas | Order splitting (órdenes límite o stop idénticas a la vez y al mismo precio); explotar la cola del simulador; operar huecos o mercados ilíquidos; brackets sobre noticias; operar fuera del mejor bid/offer; feeds lentos; spoofing y layering; hedging entre cuentas; «any software, artificial intelligence, ultra-high speed, or mass Data entry» que dé ventaja | «Order splitting. Entering multiple orders at the same price at the same time.» | [S18], [S17], [S3] | alta · verificado |
| ¿Pueden anular beneficios? | **Sí**: confiscan los beneficios de prácticas prohibidas, pueden no financiar sin reembolso y revisan toda evaluación aprobada. Escala del microscalping y el order splitting: reset y aviso → deducción de beneficios o suspensión → suspensión inmediata si es intencionado | «All profits generated from prohibited trade practices will be confiscated.» | [S18], [S17], [S3] | alta · verificado |
| Diferencias entre evaluación, Funded Sim y Live | Las prácticas prohibidas valen en todas; en Live se añaden la regla de slippage y los datos profesionales, y no se pueden tener Tradovate y NT abiertos a la vez | «Funded Live traders will not be able to have Tradovate and NinjaTrader open at the same time because of market data restrictions.» | [S38], [S39], [S24] | alta · verificado |

---

## E. Plataformas

| Plataforma | Variantes Tradovate (§1, §3, §5) | Variantes RM (§2, §4, §6) | Cita | Fuente | Estado |
|---|---|---|---|---|---|
| **NinjaTrader 8** | **Sí**: licencia gratuita, solo la última versión de NT8, en modo Multi Provider, vía Tradovate/CQG | **No** | «we do not support NinjaTrader Desktop with Rithmic accounts. Users who wish to use NinjaTrader Desktop must have a Tradovate/CQG account.» | [S23], [S24] | verificado |
| Tradovate | Sí (licencia gratuita) | No | «Tradovate (free license available)» | [S23] | verificado |
| CQG | Datos CQG por debajo de Tradovate, NT, TradingView y Jigsaw | — | «The platforms run using the CQG data feed.» | [S23] | verificado |
| Rithmic | — | Sí («Rithmic Paper Trading», Chicago Area) | «System: Rithmic Paper Trading» | [S25], [S23] | verificado |
| TradingView | Sí (licencia propia) | No figura | «TradingView is free to connect, but you will need your own TradingView license» | [S23] | verificado |
| Quantower | El ATS lo admite, pero en la lista de plataformas Quantower solo figura con Rithmic | Sí (licencia propia) | «Quantower - Rithmic» | [S23], [S19] | parcial |
| Sierra Chart | No figura | Sí (licencia propia) | «Rithmic Direct - DTC [Trading]» | [S23] | verificado |
| Bookmap | No figura | Sí (licencia de pago con futuros y L2) | «You will need your own paid Bookmap license» | [S23] | verificado |
| ATAS | No figura | Sí (licencia gratuita, no vale para Live) | «Please note that the free license cannot be used for live accounts.» | [S23] | verificado |
| Otras (Rithmic) | — | R\|Trader Pro, MotiveWave, Jigsaw-Rithmic, EdgeProX, Finamark, Volfix, WealthCharts, MultiCharts, Overcharts | lista «Rithmic Platforms» | [S23] | verificado |
| APIs | No | No | «We do not make platform APIs available to traders.» | [S19] | verificado |
| Conexiones simultáneas | En Live, Tradovate y NT no a la vez; Jigsaw con Tradovate en una financiada pide 2 feeds. Por lo demás, **no lo dice la fuente oficial** | — | «you will need 2 separate data feeds to run this setup» | [S23], [S24] | parcial |
| App móvil de NinjaTrader | No funciona con la evaluación | — | «NinjaTrader's own mobile application does not work with the evaluation account.» | [S23] | verificado |

---

## F. Elegibilidad internacional

| Campo | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| **República Dominicana** | **No figura** en la lista de países prohibidos (modificada el 1-10-2026). Sí figuran Barbados, Cuba, Haití, Jamaica, Puerto Rico, Trinidad y Tobago y ambas Islas Vírgenes. Ninguna página nombra a RD de forma expresa | «we cannot accept traders who are citizens or residents of the countries listed below» | [S43] | media · **parcial** (el silencio no es autorización; el FCM y el bróker deciden en el KYC) |
| Regla de ciudadanía y residencia | Prohibido si se es ciudadano **o** residente de un país de la lista, o si se opera sobre todo desde él | «this applies if you are a citizen or resident of any country on the list» | [S43] | alta · verificado |
| Jurisdicciones limitadas | Canadá (fuera de Ontario) y Alemania: solo Funded Sim, nunca Live | «not eligible for Funded Live accounts» | [S43] | alta · verificado |
| Edad y antecedentes | 18 años o más; sin condenas por delito grave; no estar en la lista OFAC SDN | «You represent and warrant that you have not been convicted of a felony» | [S3], [S44] | alta · verificado |
| KYC | Riseworks (payouts) y bróker/FCM (Live): documento oficial y justificante de domicilio; mismo nombre y email que en TradeDay | «You must be onboard with the same email address and name that TradeDay has on file.» | [S41], [S49] | alta · verificado |
| Cobrar desde RD | Transferencia internacional por Riseworks a **$15** por retiro, o cripto. Riseworks avisa de posibles cargos según el país. Si Riseworks da servicio en RD: **no lo dice la fuente oficial** (riseworks.io queda fuera de los hosts permitidos) | «Additional fees might be added, which are related to the legislation of the country and the bank» | [S40] | media · parcial |
| Empresas | Solo LLC unipersonales de EE. UU.; no se aceptan empresas extranjeras | «We cannot accept applications for international businesses, or make payouts to international businesses.» | [S42] | alta · verificado |
| Impuestos y formularios | Contratista independiente. Solo los ciudadanos de EE. UU. reciben el 1099-NEC; no hay documentos para Haciendas extranjeras. W-8BEN: **no lo dice la fuente oficial** | «Non-US citizens will not receive this form» | [S42] | alta · verificado (W-8BEN: sin datos) |
| VPN y geolocalización | Operar desde la dirección registrada; no saltarse restricciones geográficas | «Circumventing geographical restrictions of availability or any other technical restrictions» | [S18], [S20] | alta · verificado |

---

## G. Fuentes

Todas consultadas el **2026-11-27** con `curl` (agente de usuario por defecto). Todas respondieron
HTTP 200. Base del help center:
`https://tradeday.freshdesk.com/en/support/solutions/articles/`. La columna «Modif.» es la fecha de
modificación que muestra la propia página.

| # | Dato principal | URL | Modif. | Fecha consulta | Confianza | Estado |
|---|---|---|---|---|---|---|
| S1 | Precios, tarjetas por variante (Tradovate/Rithmic), promoción, tasa de aprobados | https://www.tradeday.com/ | — | 2026-11-27 | alta | verificado |
| S2 | «How it works» (días: «No minimum on Fast Pass») | https://www.tradeday.com/how-it-works | — | 2026-11-27 | alta | verificado |
| S3 | Términos (reset $99, conducta prohibida §23) | https://www.tradeday.com/terms-and-conditions | 11-08-2026 | 2026-11-27 | alta | verificado |
| S4 | Tabla de tamaños y precios (antigua) | https://tradeday.freshdesk.com/en/support/solutions/articles/103000304248-what-are-the-differences-between-each-account-size- | 01-09-2026 | 2026-11-27 | media | discrepancia |
| S5 | Objetivos y reglas QP/FP | https://tradeday.freshdesk.com/en/support/solutions/articles/103000008847-what-are-the-objectives-and-rules-of-the-quick-pay-and-fast-pass-evaluation- | 12-11-2026 | 2026-11-27 | alta | verificado |
| S6 | Quick Pay (programa completo) | https://tradeday.freshdesk.com/en/support/solutions/articles/103000405228-what-is-quick-pay- | 12-11-2026 | 2026-11-27 | alta | verificado |
| S7 | Fast Pass (programa completo) | https://tradeday.freshdesk.com/en/support/solutions/articles/103000405229-what-is-fast-pass- | 12-11-2026 | 2026-11-27 | alta | verificado |
| S8 | Drawdown EOD frente a intradía | https://tradeday.freshdesk.com/en/support/solutions/articles/103000335948-definition-and-differences-between-end-of-day-trailing-max-drawdown-and-intraday-trailing-maximum-dr | 31-05-2026 | 2026-11-27 | alta | verificado |
| S9 | Regla de drawdown máximo | https://tradeday.freshdesk.com/en/support/solutions/articles/103000008855-what-is-the-maximum-drawdown-rule- | 31-05-2026 | 2026-11-27 | alta | verificado |
| S10 | Consistencia | https://tradeday.freshdesk.com/en/support/solutions/articles/103000008849-what-is-the-consistency-objective- | 28-07-2026 | 2026-11-27 | alta | verificado |
| S11 | Días mínimos | https://tradeday.freshdesk.com/en/support/solutions/articles/103000008850-what-is-the-trade-for-a-minimum-number-of-days-objective- | 01-06-2026 | 2026-11-27 | alta | verificado |
| S12 | Horarios permitidos | https://tradeday.freshdesk.com/en/support/solutions/articles/103000018874-what-is-the-permitted-trading-times-guideline- | 27-04-2026 | 2026-11-27 | alta | verificado |
| S13 | Límites de posición y micros | https://tradeday.freshdesk.com/en/support/solutions/articles/103000008891-what-are-the-position-limits-guidelines-and-contracts-vs-micros- | 01-07-2025 | 2026-11-27 | alta | verificado |
| S14 | Productos permitidos | https://tradeday.freshdesk.com/en/support/solutions/articles/103000008862-what-are-the-permitted-products-guidelines- | 06-10-2026 | 2026-11-27 | alta | verificado |
| S15 | Noticias Tier 1 | https://tradeday.freshdesk.com/en/support/solutions/articles/103000063272-why-do-we-ban-tier-1-news-and-data-release-trading- | 07-07-2025 | 2026-11-27 | alta | verificado |
| S16 | Scalping | https://tradeday.freshdesk.com/en/support/solutions/articles/103000008883-will-tradeday-evaluate-and-fund-scalpers- | 03-01-2025 | 2026-11-27 | alta | verificado |
| S17 | Order splitting y microscalping | https://tradeday.freshdesk.com/en/support/solutions/articles/103000397952-order-splitting-and-microscalping | 03-09-2026 | 2026-11-27 | alta | verificado |
| S18 | Prácticas prohibidas | https://tradeday.freshdesk.com/en/support/solutions/articles/103000121031-prohibited-trade-practices | 10-06-2025 | 2026-11-27 | alta | verificado |
| S19 | Trading automatizado, algos y bots | https://tradeday.freshdesk.com/en/support/solutions/articles/103000085101-automated-algo-and-bot-trading | 28-11-2025 | 2026-11-27 | alta | verificado |
| S20 | VPN, VPS y enmascarar la IP | https://tradeday.freshdesk.com/en/support/solutions/articles/103000295384-using-a-vpn-vps-or-ip-masking-add-on | 31-05-2026 | 2026-11-27 | alta | verificado |
| S21 | Varias cuentas | https://tradeday.freshdesk.com/en/support/solutions/articles/103000354796-multiple-accounts | 08-09-2026 | 2026-11-27 | alta | verificado |
| S22 | Varias cuentas y copiadores | https://tradeday.freshdesk.com/en/support/solutions/articles/103000008833-can-i-have-multiple-accounts-can-i-use-copy-trader- | 22-09-2026 | 2026-11-27 | alta | verificado |
| S23 | Plataformas | https://tradeday.freshdesk.com/en/support/solutions/articles/103000008813-which-trading-platforms-does-tradeday-use- | 18-11-2026 | 2026-11-27 | alta | verificado |
| S24 | Configuración de NinjaTrader | https://tradeday.freshdesk.com/en/support/solutions/articles/103000025471-how-to-set-up-the-ninjatrader-trading-platform | 18-08-2026 | 2026-11-27 | alta | verificado |
| S25 | Configuración de Rithmic | https://tradeday.freshdesk.com/en/support/solutions/articles/103000408636-how-to-set-up-the-rithmic-trading-platform | 10-08-2026 | 2026-11-27 | alta | verificado |
| S26 | Comisiones | https://tradeday.freshdesk.com/en/support/solutions/articles/103000008893-how-much-are-trading-commissions- | 20-08-2026 | 2026-11-27 | alta | verificado |
| S27 | Coste de los datos de mercado | https://tradeday.freshdesk.com/en/support/solutions/articles/103000008840-how-much-does-market-data-cost-and-can-i-add-another-feed- | 27-04-2026 | 2026-11-27 | alta | verificado |
| S28 | Cargos una vez financiado | https://tradeday.freshdesk.com/en/support/solutions/articles/103000008894-are-there-any-fees-when-i-am-funded- | 31-05-2026 | 2026-11-27 | alta | verificado |
| S29 | Reglas de Funded Sim y Live | https://tradeday.freshdesk.com/en/support/solutions/articles/103000008889-what-are-the-rules-for-funded-funded-sim-and-funded-live-traders- | 31-05-2026 | 2026-11-27 | alta | verificado |
| S30 | Funded Sim frente a Funded Live | https://tradeday.freshdesk.com/en/support/solutions/articles/103000180686-what-is-a-funded-sim-account-and-what-is-a-funded-live-account- | 31-05-2026 | 2026-11-27 | alta | verificado |
| S31 | Política de payout de QP (Funded Sim) | https://tradeday.freshdesk.com/en/support/solutions/articles/103000335937-quick-pay-funded-sim-payout-policy | 22-07-2026 | 2026-11-27 | alta | verificado |
| S32 | Política de payout de FP (Funded Sim) | https://tradeday.freshdesk.com/en/support/solutions/articles/103000404096-fast-pass-funded-sim-payout-policy | 08-09-2026 | 2026-11-27 | alta | verificado |
| S33 | Frecuencia de retiros y cargos de Riseworks | https://tradeday.freshdesk.com/en/support/solutions/articles/103000008897-how-often-can-i-withdraw-profits-from-funded-sim-account- | 31-05-2026 | 2026-11-27 | alta | verificado |
| S34 | Retiros y drawdown; traspaso a Live | https://tradeday.freshdesk.com/en/support/solutions/articles/103000250682-funded-accounts-withdrawals-and-the-impact-of-drawdowns | 31-05-2026 | 2026-11-27 | alta | verificado |
| S35 | Cómo pedir un payout y plazos | https://tradeday.freshdesk.com/en/support/solutions/articles/103000262630-how-do-i-request-a-payout-withdrawal-and-how-long-does-it-take- | 25-11-2026 | 2026-11-27 | alta | verificado |
| S36 | QP: camino a Live ($10,000) | https://tradeday.freshdesk.com/en/support/solutions/articles/103000353468-quick-pay-funded-sim-path-to-live-trading | 31-08-2026 | 2026-11-27 | alta | verificado |
| S37 | FP: camino a Live | https://tradeday.freshdesk.com/en/support/solutions/articles/103000404097-fast-pass-funded-sim-route-to-funded-live | 01-09-2026 | 2026-11-27 | alta | verificado |
| S38 | Reglas de Funded Live (QP y FP) | https://tradeday.freshdesk.com/en/support/solutions/articles/103000411652-quick-pay-and-fast-pass-funded-live-trading-rules | 09-09-2026 | 2026-11-27 | alta | verificado |
| S39 | Regla de slippage en Live | https://tradeday.freshdesk.com/en/support/solutions/articles/103000089243-slippage-rule-for-funded-live-traders | 09-09-2026 | 2026-11-27 | alta | verificado |
| S40 | Métodos de pago (Riseworks) | https://tradeday.freshdesk.com/en/support/solutions/articles/103000008898-what-are-the-payment-methods-for-my-trading-profits- | 09-01-2025 | 2026-11-27 | alta | verificado |
| S41 | Alta en Riseworks y KYC | https://tradeday.freshdesk.com/en/support/solutions/articles/103000262631-how-do-i-get-set-up-on-riseworks- | 03-09-2026 | 2026-11-27 | alta | verificado |
| S42 | Situación laboral y fiscal | https://tradeday.freshdesk.com/en/support/solutions/articles/103000008901-what-is-my-employment-and-tax-status-as-a-funded-trader-with-tradeday- | 09-01-2025 | 2026-11-27 | alta | verificado |
| S43 | Países prohibidos | https://tradeday.freshdesk.com/en/support/solutions/articles/103000123294-prohibited-countries | 01-10-2026 | 2026-11-27 | alta | verificado |
| S44 | Quién puede unirse | https://tradeday.freshdesk.com/en/support/solutions/articles/103000008683-can-anyone-join-tradeday- | 21-07-2025 | 2026-11-27 | alta | verificado |
| S45 | Inactividad y plazo de documentos para Live | https://tradeday.freshdesk.com/en/support/solutions/articles/103000008899-are-there-any-inactivity-fees-or-minimum-trading-requirements- | 30-09-2026 | 2026-11-27 | alta | verificado |
| S46 | Reembolsos | https://tradeday.freshdesk.com/en/support/solutions/articles/103000008910-refund-policy | 18-11-2026 | 2026-11-27 | alta | verificado |
| S47 | Ajustes de riesgo en Tradovate | https://tradeday.freshdesk.com/en/support/solutions/articles/103000244846-can-i-access-risk-settings- | 09-03-2026 | 2026-11-27 | alta | verificado |
| S48 | Límites de precio y circuit breakers | https://tradeday.freshdesk.com/en/support/solutions/articles/103000307192-price-limits-and-circuit-breakers | 17-07-2025 | 2026-11-27 | alta | verificado |
| S49 | ¿Fondeo garantizado al aprobar? | https://tradeday.freshdesk.com/en/support/solutions/articles/103000008875-if-i-pass-the-evaluation-challenge-am-i-guaranteed-funding- | 22-04-2026 | 2026-11-27 | alta | verificado |
| S50 | Proceso tras aprobar | https://tradeday.freshdesk.com/en/support/solutions/articles/103000008887-what-is-the-process-after-completing-the-evaluation- | 10-06-2026 | 2026-11-27 | alta | verificado |
| S51 | Qué pasa al fallar | https://tradeday.freshdesk.com/en/support/solutions/articles/103000008876-what-happens-if-i-fail-any-of-the-evaluation-challenge- | 12-11-2026 | 2026-11-27 | alta | verificado |
| S52 | Resets por fallos técnicos | https://tradeday.freshdesk.com/en/support/solutions/articles/103000121140-does-tradeday-offer-a-free-reset-after-a-technical-issue- | 05-06-2026 | 2026-11-27 | alta | verificado |

Además se leyeron, sin datos que cambien la ficha, el índice del help center
(`https://tradeday.freshdesk.com/en/support/solutions`), sus 8 carpetas y las páginas 2, y el resto de
artículos (educación, contraseña, CoPilot, facturación).

### Discrepancias abiertas (resumen)
1. Precio del FP 50K: **$248** de lista en la portada frente a **$180** en [S4]. QP: $124/$174 frente
   a $125/$175.
2. Días mínimos del FP: 3 ([S5], [S1]) frente a «no minimum» ([S7], [S2]).
3. Los Términos ([S3]) mantienen texto de cuando había suscripción: reset de $99, mínimo de 7 días y
   solo drawdown EOD. Otros artículos hablan aún de «monthly subscription» ([S28], [S50]).
4. Hora de corte del payout: 17:30 **CT** ([S33], [S35]) frente a 17:30 **ET** ([S31]).
5. «Buffer Zone» en [S35] frente a «No Payout Buffer» en Funded Sim ([S1], [S6], [S32]).
6. Drawdown de la Live de FP a 50K: $2,000 («same EOD drawdown») frente a «$1500» en el ejemplo
   ([S37], [S38]).
7. Plataformas del ATS: [S19] incluye NinjaTrader, pero [S23] la excluye con Rithmic. Para RM, NT8 = no.

### Páginas que no se pudieron leer o que quedan incompletas
- Ninguna respondió 403 ni otro error.
- **`members.tradeday.com`** (registro, checkout, dashboard y curso «Rules and Regulations»): fuera de
  los hosts permitidos y exige registro; no se intentó. Allí estarían las condiciones de compra y el
  acuerdo de la cuenta financiada → **Sin datos**.
- **Riseworks** (`riseworks.io`, cobertura por países y plazos de retiro): fuera de los hosts
  permitidos; no se leyó.
- Calendario Tier 1 de TradeDay y páginas de CME enlazadas: no se siguieron (no hacían falta para la
  ficha).

### Aviso de método: término contra el acceso automatizado (descargas detenidas)
- Los Términos de TradeDay (https://www.tradeday.com/terms-and-conditions, §24 «Other prohibited
  uses», Last Modified: August 11, 2026) prohíben: «Using any manual or automated software, devices,
  or other processes to "crawl" or "spider" any web pages contained in the Sites or Services».
- Por ese término, **se dejó de descargar de TradeDay** en cuanto el coordinador fijó la regla.
  Antes ya se habían descargado con `curl`, una a una y con pausas, unas 95 páginas públicas
  (artículos, carpetas, portada y Términos). Esta ficha se escribe solo con ellas y no se hizo
  ninguna petición más.
- **Lo que queda pendiente necesita que el operador lo lea con un navegador**, o que pregunte a
  soporte: (a) las condiciones de compra y el acuerdo de la cuenta financiada en `members.tradeday.com`;
  (b) si existe un reset y cuánto cuesta (los $99 de los Términos frente a «comprar una cuenta nueva»);
  (c) el precio real del FP 50K en el checkout ($248 o $180) y la zona horaria del fin de `SALE60`;
  (d) la confirmación expresa de que se aceptan las estrategias NinjaScript y las ATM de NT8; (e) el
  máximo de contratos del escalado del FP 50K en Funded Sim; (f) el máximo por retiro en QP; (g) si
  Riseworks da servicio en República Dominicana.
- Que las descargas ya hechas sean compatibles con ese término lo decide el operador.
- No se creó ninguna cuenta, no se aceptaron términos y no se abrió ningún enlace de registro.
