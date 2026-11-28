# MyFundedFutures (MFFU) · ficha de reglas de fondeo (investigación 2026-11)

- **ID**: `myfundedfutures` · **Fecha de consulta**: 2026-11-27 · **Cuenta de referencia**: 50K.
- **Programas analizados** (una subsección cada uno; no se trasladan reglas de uno a otro):
  §1 **Rapid 50K** (intradía) · §2 **Rapid EOD 50K** (con y sin DLL) · §3 **Pro 50K** (y Pro 50K One
  Day) · §4 **Builder 50K** (Default y Add-On) · §5 **Signature** (no existe en 50K: solo 5K/10K/20K).
  Los planes *Legacy* (Flex, Core, Scale, Pro antiguo) quedan fuera de alcance.
- **Fuentes**: páginas de planes de `myfundedfutures.com`, `myfundedfutures.com/ninjatrader`,
  `myfundedfutures.com/terms` y 46 artículos del help center `help.myfundedfutures.com/en/` (el mismo
  centro de ayuda se sirve en `intercom.help/myfundedfutures/en/`). Se verifican y completan los datos
  de `docs/futures/research/prop_firms_2026-11-27.md` §2.
- **Formato de cada dato**: valor · «cita literal» (≤ 25 palabras) · [M#] (URL exacta y fecha del
  artículo en §G) · confianza · estado. Todo se consultó el 2026-11-27. La aritmética sobre cifras
  oficiales se marca **(cálculo propio)**.
- **Términos y acceso automático**: en `https://myfundedfutures.com/terms` no hay ninguna cláusula
  que prohíba robots, *scraping* ni *crawling*. Se buscaron robot, spider, scrap, crawl, data mining
  y harvest, sin resultados. Aun así, a petición del coordinador no se hizo ninguna descarga más
  después de esa comprobación (véase §G).

## Resumen (50K)

| Plan | Automatización | NinjaTrader 8 | Coste hasta la 1.ª cuenta financiada (1 intento) | Reparto · mínimo · máximo · frecuencia |
|---|---|---|---|---|
| Rapid 50K | **Permitida con condiciones** (estrategias propias; sin HFT; sin explotar los *fills* del simulador) | Sí (conexión NinjaTrader, licencia incluida) | **$125** con promoción (40 %, código CLUB) · **$209** de lista · activación $0 | 90/10 · $500 · máximo por retiro: **no lo dice la fuente oficial** · diario (cada 24 h) tras un *buffer* de $2,100 |
| Rapid EOD 50K | **Permitida con condiciones** (igual) | Sí | Lista **$275** · promoción **$165** (solo en los datos de la página; confianza baja) · con DLL: $200 de lista (baja) | 90/10 · $500 · «no cap» por ciclo · diario tras un *buffer* de $2,100 y luego $500 netos por ciclo |
| Pro 50K | **Permitida con condiciones** + *Consistent Trading Policy* (vigila HFT, ir al máximo de contratos y el *flipping*) | Sí | **$159** con promoción · **$265** de lista · One Day: $379 (solo en los datos de la página; baja) | 80/20 · $1,000 · $100,000 (discrepancia: «por usuario» o «por ciclo») · cada 14 días naturales desde el primer *trade* |
| Builder 50K | **Permitida con condiciones** (igual) | Sí | **$92** (40 %, solo 2 usos) · $107 (30 %) · **$153** de lista; Add-On (MLL de $1,500): $75 / $87 / $125 | 80/20 · $500 · **$2,000 por ciclo** · cada 48 h, **máximo 5 payouts** en simulada y después Live |
| Signature | Regla general (sin cláusula propia) | **No** (según el help center, solo Hyperprop) | **No hay 50K** | 80/20 en simulada · $100/$250 · sin máximo por retiro, con tope de beneficio diario · cuando se quiera |

- **República Dominicana**: **no figura** en la lista de países restringidos (versión del 14-10-2026,
  [M30]; la misma lista está en [M31]). Estado: verificado por ausencia en una lista cerrada ·
  confianza media. Sin confirmar: los medios de cobro desde RD (Rise) y la lista de países sin pago
  con cripto, que es una imagen ilegible (**Sin datos**).
- **Comisiones ida y vuelta** (todos los planes, [M27]): NQ **$4.68** · MNQ **$1.90** · GC $5.12 ·
  MGC $2.20.

---

## Políticas de toda la firma (la fuente las declara generales, para todas las cuentas o planes)

| Tema | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Automatización | Permitida si son estrategias propias y no explotan los *fills* favorables del simulador | «Traders may make use of automated trading strategies» · «so long as these automated tools do not aim to exploit the favorable fills offered in the Simulated Environment.» | [M21] | alta · verificado |
| HFT | Prohibido en todos los planes; la fuente no da umbral numérico | «High-frequency Trading is not allowed on our plans.» | [M21] | alta · verificado (sin definición) |
| Automatización en Live | Sujeta a las normas del CME | «Traders trading live accounts with automated trading must abide by CME guidelines.» | [M21] | alta · verificado |
| Técnicas de ejecución prohibidas | Varias órdenes límite al mismo precio; *fills* aislados en contratos ilíquidos o meses traseros; *brackets* estrechos que aprovechan la falta de deslizamiento | «Exploiting the absence of slippage and utilizing tight brackets to gain from favorable fills are not permitted.» | [M21] | alta · verificado |
| Anulación de beneficios | Sí, si la práctica está prohibida; los Términos permiten además quitar *trades* del historial | «Profits generated from prohibited trading practices will be confiscated.» | [M21], [M8] §23.2.1 | alta · verificado |
| Copiadores | Permitidos en todos los tipos de cuenta (Tradesyncer, copiador de grupo de Tradovate o externos), por cuenta y riesgo del trader | «MyFunded Futures allows copy trading across all account types.» | [M22] | alta · verificado |
| Copiar a otros traders y compartir dispositivo | Prohibido | «Each individual trader may not use the same device (tablet, phone or computer) as used by another trader.» | [M21], [M23] | alta · verificado |
| Hedging | Prohibido sobre el mismo subyacente (NQ y MNQ cuentan como el mismo) | «MyFunded Futures prohibits hedging of any kind.» | [M24], [M21] | alta · verificado |
| VPS | **No lo dice la fuente oficial** | — | — | — · no verificado |
| Microscalping | **No hay umbral publicado**; solo la prohibición de HFT y de explotar los *fills* | — | [M21] | media · parcial |
| Límite de precio del 2 % | No se opera a menos de un 2 % del límite de precio del CME (en simulada financiada y en Live) | «we do not allow market participation when a product is trading within 2% of a price limit.» | [M28] | alta · verificado |
| Mezclar minis y micros | Prohibido pasar del límite combinando instrumentos | «Attempting to execute 2 minis AND 20 micros will execute, but it is not allowed.» | [M29] | alta · verificado |
| Equivalencia de micros | 10 micros = 1 mini (las tablas dan 5/50, 3/30, 4/40) | «5 minis / 50 micros max» | [M1] | alta · verificado |
| Metales y commodities | Micros de metales: máximo 5 en 50K; SI, HG, PL, NG y QG restringidos | «$50k account → maximum 5 micro contracts» | [M27] | alta · verificado (restricción «temporal») |
| Horario | 18:00 a 16:10 EST; cierre automático a las 16:10 | «can remain open until the New York session closes at 4:10 PM EST.» | [M26] | alta · verificado |
| Días festivos | No hay cierre automático en las medias sesiones; si no se cierra, se rompe la cuenta | «Failure to close the positions before the market closes will result in breaching of the account» | [M26] | alta · verificado |
| Noticias T1 | Sin posiciones ni órdenes desde 2 min antes hasta 2 min después en **Rapid Sim Funded y Pro Sim Funded**; permitido en todas las evaluaciones y en Builder | «No positions or orders (including limit orders) can be open 2 minutes before and after the release.» | [M25] | alta · verificado |
| Noticias no T1 | **Ambigua**: un apartado aplica la regla de ±2 min «a todas las publicaciones» y otro dice que se puede operar en ellas | «These protocols apply to all news releases.» | [M25] | media · parcial |
| Inactividad | Si pasan 7 días naturales sin operar, la cuenta puede cerrarse; en simulada financiada se pierden los beneficios | «An inactivity breach on a Sim Funded account results in the forfeiture of all profits.» | [M37] | alta · verificado |
| Modelo de pago | Pago único desde el 25-08-2026; sin renovaciones | «transition to a one-time payment model for all new evaluation purchases.» | [M37], [M38] | alta · verificado |
| Activación | $0 en todos los planes | «all MFFU plans, regardless of account size, come with $0 activation fee.» | [M40] | alta · verificado |
| Reembolso | Solo si no se ha operado (14 días); las compras con cripto no se reembolsan | «A full refund is available when no trades have been placed after an account purchase» | [M39] | alta · verificado |
| Cuentas a la vez | Hasta 10 evaluaciones activas · hasta 5 simuladas financiadas si solo son de 25K/50K · 3 si hay alguna de 100K/150K · límites propios por plan | «Traders may hold a maximum of 10 active Evaluation Accounts at any given time.» | [M35], [M34] | alta · verificado |
| Plataforma y datos | Licencia de NinjaTrader y Tradovate y datos CME en tiempo real incluidos | «NinjaTrader and Tradovate access comes with your MFFU account. No separate license to buy.» | [M7] | alta · verificado |
| KYC | Obligatorio antes de operar la cuenta simulada financiada (Sumsub: documento, selfie y prueba de domicilio de ≤ 3 meses) | «It is a prerequisite to begin trading your simulated-funded account.» | [M31] | alta · verificado |
| Cobro | Riseworks (transferencia o cripto); Plaid/ACH solo en EE. UU. | «Note: Plaid/ACH payouts are available for US traders.» | [M20] | alta · verificado |
| Tiempo de proceso | La mayoría se aprueba al instante; la revisión manual tarda de 6 a 12 h hábiles. **Discrepancia**: la página de Rapid habla de hasta 24 h hábiles | «If a manual review is required, processing may take up to 6 to 12 business hours on weekdays.» | [M19], [M1] | media · discrepancia |
| Simulada y Live a la vez | No: al pasar a Live, las cuentas simuladas quedan dormidas | «All simulated trading accounts and additional purchases are suspended during Live account operation.» | [M11] | alta · verificado |

**Payouts: solicitado → aprobado → procesado → recibido.** Solicitado: desde el panel ([M20]).
Aprobado: «auto-approved» en la mayoría de los casos; si hay revisión manual, de 6 a 12 h hábiles
([M19]). Procesado: en el primer payout hay que firmar acuerdos en Riseworks y el dinero pasa a la
cuenta de Rise ([M20]). Recibido: de Rise al banco o a cripto, **sin plazo publicado por MFFU (Sin
datos)**.

---

## 1. Rapid 50K (drawdown intradía en la simulada financiada)

### A. Costes

| Concepto | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Precio de lista | **$209** (pago único) | «Starting at $125 Based on current promotions $209» · datos estructurados: «Rapid Plan 50,000 Account","price":"209.00"» | [M1] | media · parcial (la página no rotula cuál es el de lista; el *schema* sí da $209) |
| Precio con promoción | **$125** (≈ 40 % de descuento; el banner dice «Save 40% On Any Plan With Code CLUB.») | ídem | [M1] | media · parcial |
| Otra promoción | «New to MFFU? Get 50% off your first eval.» → $104.50 **(cálculo propio, cifra no publicada)** | banner | [M1] | baja · no verificado |
| Suscripción o pago único | Pago único, sin renovaciones | «No activation fee · One-time payment, no renewals» | [M1] | alta · verificado |
| Activación | $0 | «Activation fee$0» | [M1], [M40] | alta · verificado |
| Reset | Existe; **el importe no aparece en el texto visible**. Los datos embebidos de la portada dan `reset_price` = 209 | «you can reset it for a specific fee» | [M1], [M6] | baja · no verificado |
| Datos y plataforma | Incluidos | véase la tabla general | [M7] | alta · verificado |
| Comisiones | NQ $4.68 · MNQ $1.90 ida y vuelta | «Total Cost Round Trip» | [M27] | alta · verificado |
| Coste hasta la 1.ª cuenta financiada (mejor caso) | **$125** con CLUB · **$209** sin promoción **(cálculo propio)** | — | — | media |
| Mantenerla 3 y 6 meses | **$0 fijos** más comisiones; hay que operar al menos una vez cada 7 días **(cálculo propio)** | — | [M37], [M7] | media |

### B. Reglas de trading

| Regla | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Profit target | $3,000 | «Profit Target $3,000» | [M9], [M1] | alta · verificado |
| Drawdown en evaluación | $2,000 **EOD** | «Maximum Loss Limit (EOD) $2,000» | [M9] | alta · verificado |
| Drawdown en simulada financiada | $2,000 **intradía trailing** desde el máximo de *equity*, P&L no realizado incluido | «Floor follows unrealized gains» · «Drawdown Type: Intra-day trailing» | [M1], [M9], [M10] | alta · verificado |
| Bloqueo del MLL | **Discrepancia**. [M9]: se bloquea cuando el MLL llega a +$100. FAQ de [M1]: «after your first payout». Otra línea de [M1]: tras construir el *buffer* | «Once your trailing Max Loss reaches $100, it locks there.» | [M9], [M1] | media · discrepancia |
| DLL | Ninguno, ni en evaluación ni en financiada | «Rapid has no daily loss limit in either the evaluation or the funded stage.» | [M1] | alta · verificado |
| Consistencia | 50 % solo en evaluación; ninguna en financiada | «Consistency 50% (Eval Only)» | [M9] | alta · verificado |
| Días mínimos (evaluación) | 2 | «Minimum Trading Days 2 Days» | [M9] | alta · verificado |
| Contratos | Evaluación y simulada: 5 minis / 50 micros · Live: 3/30. **Discrepancia**: el ejemplo de [M29] habla de 2 contratos iniciales «due to the scaling plan» | «Max Contracts: 5 minis / 50 micros» | [M9], [M11], [M29] | media · discrepancia |
| Noticias | T1 permitido en evaluación y **no** en la simulada financiada | «No T1 news trading is allowed on this Sim Funded account.» | [M9], [M25] | alta · verificado |
| Overnight y fin de semana | No; romper la regla rompe la cuenta | «Holding overnight will breach the account.» | [M1] | alta · verificado |
| Cuentas | Hasta 5 simuladas financiadas de 25K/50K | «you can hold up to five active sim funded accounts at once.» | [M1], [M35] | alta · verificado |
| Escalado | Sin plan de escalado publicado para Rapid 50K (salvo la discrepancia de [M29]) | — | [M29] | baja · parcial |

### C. Payouts

| Concepto | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Buffer | $2,100 en beneficio realizado antes del primer retiro; solo se retira tras una ruptura en Live | «You must first build at least $2,100 in realized profits in the account before requesting any payout.» | [M9], [M12] | alta · verificado |
| Días | 1.º payout 24 h después del primer *trade*; después, cada 24 h | «Your first payout becomes available exactly 24 hours after your first trade» | [M9] | alta · verificado |
| Mínimo | $500 | «Minimum Payout Request: $500» | [M9] | alta · verificado |
| Máximo por retiro | **No lo dice la fuente oficial** | — | — | — · no verificado |
| Número máximo de retiros | No publicado; Live automático con **$10,000 de beneficio neto en un día** (lo que pase de $10,000 ese día se pierde) | «any profit exceeding $10,000 for that trading day is forfeited.» | [M11] | alta · verificado |
| Reparto | 90/10 en simulada y en Live | «90% to the trader» | [M9], [M11] | alta · verificado |
| Live | Saldo inicial $0, MLL de $2,000 EOD que se para en $0, 3/30 contratos, payouts diarios; reserva de hasta $5,000 | «Up to $5,000 of Sim Funded profits are allocated to Reserve upon transition.» | [M11], [M12] | alta · verificado |
| Bono de reserva | 20 días rentables en Live y $10,000 en payouts brutos de Live | «20 profitable trading days on the Live account» | [M12] | alta · verificado |

### D. Automatización
**Veredicto: permitida con condiciones** (política general [M21]). Para Rapid no hay cláusula propia.
NinjaTrader 8 está soportado ([M7], [M42]). **Las NinjaScript Automated Strategies no se mencionan
expresamente**: [M7] solo habla de «NinjaScript add-ons» («Bring the indicators and add-ons you
already run on NinjaTrader Desktop.»), así que quedan bajo la regla general · confianza media. Las ATM
Strategies están soportadas («Brackets, OCO and ATM templates…», [M7]). Copiadores entre cuentas
propias: sí ([M22]). Cuentas: hasta 5. VPS: no lo dice. Para un bot, en la simulada financiada pesan
dos cosas: la prohibición de T1 con ±2 min sin órdenes y el drawdown intradía.

### E. Plataformas
NinjaTrader 8 sí · Tradovate sí · TradingView sí (vía Tradovate) · Quantower, Volumetrica,
DeepChart/DeepDom, ATAS y Hyperprop sí ([M41]) · **Rithmic, CQG, Sierra Chart y Bookmap: no los
menciona la fuente oficial** · datos: Tradovate y dxFeed ([M35], [M10]) · API y conexiones
simultáneas: no lo dice.

---

## 2. Rapid EOD 50K (versión por defecto sin DLL y versión con DLL)

### A. Costes

| Concepto | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Precio de lista (sin DLL) | **$275** | datos estructurados: «Rapid EOD Plan 50,000 Account","price":"275.00"» | [M2] | media · parcial (no aparece en el texto visible; la página muestra el de 25K: «$97 … $162») |
| Precio con promoción (sin DLL) | **$165** (`priceDiscountedCents: 16500`, solo en datos embebidos) | — | [M2] | baja · no verificado |
| Versión con DLL | $200 de lista (`price_data` «Rapid EOD 50K DLL», solo embebido) | «Q. What is the default version? A. The default is No DLL, at the updated price.» | [M14], [M6] | baja · no verificado |
| Activación y modalidad | $0 · pago único | «No activation fee · One-time payment, no renewals» | [M2] | alta · verificado |
| Reset | Importe no publicado en texto | — | — | — · no verificado |
| Comisiones | NQ $4.68 · MNQ $1.90 | — | [M27] | alta · verificado |
| Coste hasta la 1.ª cuenta financiada | $165 con promoción / $275 de lista **(cálculo propio; precios de confianza baja o media)** | — | — | baja |
| Mantenerla 3 y 6 meses | $0 fijos más comisiones **(cálculo propio)** | — | [M37] | media |

### B. Reglas de trading

| Regla | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Profit target · drawdown | $3,000 · $2,000 EOD (en evaluación y en simulada) | «Drawdown Type End-of-Day (EOD) Trailing» | [M13] | alta · verificado |
| P&L no realizado | Cuenta para la ruptura (regla general del EOD) | «open equity losses are taken into consideration» | [M45] | media · verificado (artículo genérico) |
| Bloqueo | Cuando el MLL llega a +$100 | «Once your trailing Max Loss reaches $100, it locks there.» | [M13] | alta · verificado |
| DLL | Ninguno por defecto · versión con DLL: $1,000 de pausa suave en evaluación y en simulada, se reinicia a las 18:00 ET | «$1,000 (Soft Pause)» | [M13], [M14] | alta · verificado |
| Consistencia · días | 30 % solo en evaluación · mínimo 4 días | «Consistency 30% (Eval Only)» | [M13] | alta · verificado |
| Contratos | 3/30 en evaluación y en simulada. Live: **discrepancia** entre 4/40 ([M2]) y «same rules as standard Rapid 50k» (3/30, [M13]/[M11]) | «Max Contract 3 mini / 30 micro» | [M13], [M2], [M11] | media · discrepancia |
| Noticias | T1 permitido en evaluación y no en la simulada | «T1 News Trading No» | [M13] | alta · verificado |
| Cuentas | Máximo **3** simuladas de Rapid EOD 50K | «Rapid EOD $50K: Maximum of 3 Sim-Funded Accounts» | [M35], [M13] | alta · verificado |
| Inactividad | 7 días | «Inactivity Rule 7 Days» | [M13] | alta · verificado |

### C. Payouts

| Concepto | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Buffer | $2,100 antes del 1.º; después, $500 netos desde el último payout | «each payout after that unlocks once your net profit since your last payout reaches $500.» | [M13] | alta · verificado |
| Frecuencia · mínimo · máximo | Diario · $500 · sin tope por ciclo | «There is no cap on how much you can request per payout cycle.» | [M13] | alta · verificado |
| Reparto | 90/10 | — | [M13] | alta · verificado |
| Live | Las mismas reglas que Rapid 50K ($10,000 en un día o revisión, reserva de hasta $5,000) | «Live transition on Rapid EOD 50k follows the same rules as standard Rapid 50k.» | [M13], [M11] | alta · verificado |

### D. Automatización
Igual que §1, por la regla general [M21]: **permitida con condiciones**. Sin cláusula propia.
NinjaTrader 8 sí, porque [M7] incluye Rapid EOD en la misma plataforma. Las NinjaScript Automated
Strategies no se mencionan expresamente. La DLL opcional actúa como pausa y no rompe la cuenta.

### E. Plataformas
Las mismas que en §1 ([M7]: «Builder, Rapid, Rapid EOD and Pro all trade on the same platforms»).

---

## 3. Pro 50K (y Pro 50K One Day)

### A. Costes

| Concepto | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Precio de lista | **$265** | «Starting at $159 Based on current promotions $265» · *schema* «Pro Plan 50,000 Account","price":"265.00"» | [M3] | media · parcial |
| Precio con promoción | **$159** (≈ 40 %) | ídem | [M3] | media · parcial |
| Pro 50K One Day | $379 de lista (solo embebido) · objetivo $4,000 · sin consistencia · 1 día | «*Pro Plan One Day Add-On has a $4,000 evaluation profit target.» | [M6], [M34], [M15] | baja (precio) · alta (reglas) |
| Activación y modalidad | $0 · pago único | «No activation fee · One-time payment, no renewals» | [M3] | alta · verificado |
| Reset | Importe no publicado en texto | — | — | — · no verificado |
| Coste hasta la 1.ª cuenta financiada | **$159** con promoción · **$265** de lista **(cálculo propio)** | — | — | media |
| Mantenerla 3 y 6 meses | $0 fijos más comisiones; un *trade* cada 7 días | «the account requires at least one trade every 7 calendar days to stay active.» | [M3] | alta · verificado |

### B. Reglas de trading

| Regla | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Evaluación | $3,000 · $2,000 EOD · sin DLL · consistencia del 50 % · 2 días · 3/30 contratos · T1 permitido | «Scaling / Max Contacts 3 mini / 30 micro» | [M15] | alta · verificado |
| Simulada financiada | $2,000 EOD trailing · sin DLL · sin consistencia · T1 no permitido | «Daily Loss Limit (DLL) None» | [M15] | alta · verificado |
| Contratos en simulada | **«3 mini / 3 micro»**, literal en [M3] y [M15]: **ambiguo** (¿3 micros?) | «Scaling / Max Contacts 3 mini / 3 micro» | [M15], [M3] | media · ambiguo |
| Bloqueo del MLL | Tras el 1.er payout, el MLL pasa a $50,100 y queda estático | «After first payout, MLL moves to $50,100 and remains static.» | [M15], [M3] | alta · verificado |
| Política de consistencia | *Consistent Trading Policy*: vigila operar siempre al máximo de contratos, el *flipping*, el tamaño irregular y el HFT; sanciones posibles | «high-frequency strategies not aligned with your stated approach.» | [M3], [M16] | alta · verificado |
| Cuentas | Una simulada Pro activa por tamaño (desde el 23-11-2026) | «A trader can hold one active Sim Funded Pro account at each size: 50K, 100K and 150K.» | [M15] | alta · verificado |
| Overnight | No: regla horaria general (cierre a las 16:10) | — | [M26] | media · verificado (regla general) |

### C. Payouts

| Concepto | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Días | 14 días naturales desde el primer *trade* y *buffer* cubierto | «14 calendar days from day of first trade.» | [M15], [M3] | alta · verificado |
| Buffer | $2,100. **Discrepancia**: [M19] permite retirar el 60 % antes de cubrirlo | «You can withdraw up to 60% of your profits before fully clearing the buffer.» | [M19], [M15] | media · discrepancia |
| Mínimo | $1,000 | «Minimum Payout Request $1,000» | [M15] | alta · verificado |
| Máximo | $100,000. **Discrepancia**: «per user» ([M15], [M19]) frente a «per payout cycle» ([M3]) | «Up to $100,000 per payout cycle.» | [M3], [M15] | media · discrepancia |
| Reparto | 80/20 | «Profit Split 80/20» | [M15] | alta · verificado |
| Paso a Live (revisión) | 3 payouts consecutivos, tope de $100K, invitación o $20,000 de beneficio (solo revisión) | «Three (3) consecutive payouts on the same Pro account.» | [M15] | alta · verificado |
| Live | Blue Row Capital · saldo $0 · MLL de −$2,000 EOD trailing · **2 contratos** · mínimo $250 · 80/20 · DLL «None» según [M15]. **Discrepancia**: la FAQ de [M3] dice que Live lleva DLL, menos contratos y suelo estático | «live account parameters differ from sim funded, including a daily loss limit» | [M15], [M3] | media · discrepancia |
| Reserva | Hasta $5,000; bono con 20 días rentables y $10,000 en payouts de Live (50K) | «Up to $5,000 is placed in the Reserve Program» | [M15] | alta · verificado |

### D. Automatización
**Permitida con condiciones** (regla general [M21]), **más** la *Consistent Trading Policy* de Pro
([M3], [M16]): un bot que entre siempre con el máximo de contratos o con estilo HFT puede acabar en
restricción o cierre. NinjaTrader 8 sí; las NinjaScript Automated Strategies no se mencionan
expresamente. En Live, CME ([M21]).

### E. Plataformas
Las mismas que en §1 ([M7]).

---

## 4. Builder 50K (Default: MLL $2,000 · Add-On: MLL $1,500)

### A. Costes

| Concepto | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Precio de lista | Default **$153** · Add-On **$125** | «Price $153 $125» | [M17] | alta · verificado |
| Promociones | 30 %: $107 / $87 · 40 % (solo 2 usos): **$92** / $75 | «Discounted Price (40% OFF - 2 uses only) $92 $75» | [M17], [M4] | alta · verificado |
| Activación · modalidad | $0 · pago único | «Activation Fee $0 $0» | [M17] | alta · verificado |
| Reset | Importe no publicado en texto | — | — | — · no verificado |
| Coste hasta la 1.ª cuenta financiada | **$92** (Default con 40 %) · $75 (Add-On con 40 %) · $153 de lista **(cálculo propio)** | — | — | alta |
| Mantenerla 3 y 6 meses | $0 fijos más comisiones; inactividad de 7 días | «Inactivity Rule 7 Calendar Days» | [M17] | alta · verificado |

### B. Reglas de trading

| Regla | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Evaluación | $3,000 · MLL EOD trailing de $2,000 ($1,500 en Add-On) · DLL de $1,000 con pausa suave · 4/40 · sin consistencia · 1 día · noticias permitidas | «Daily Loss Limit $1,000 - soft pause» | [M17] | alta · verificado |
| Días mínimos | **Discrepancia**: la tarjeta de [M4] dice «One phase · min 2 days» y la tabla «1 Day» | «Min Trading Days 1 Day» | [M4], [M17] | media · discrepancia |
| Simulada financiada | Saldo $0 · MLL de $2,000 EOD · DLL de $1,000 con pausa suave · 4/40 · noticias libres | «News trading is fully unrestricted during the evaluation and sim funded stage.» | [M17] | alta · verificado |
| Bloqueo | El MLL se bloquea al llegar a +$100 | «The MLL locks permanently once it reaches $100 above the starting balance.» | [M17] | alta · verificado |
| Discrepancia DLL | [M19] dice «No daily loss limits on Builder, Rapid or Pro plans»; [M17] y [M4] dan $1,000 de pausa suave | — | [M19], [M17] | — · discrepancia (prevalece [M17]) |
| Cuentas | **1** simulada Builder 50K por usuario | «Only one Sim Funded account may be active per user at any time on the Builder Plan.» | [M17], [M35] | alta · verificado |
| Overnight | No | «Q: Can I hold positions overnight? No.» | [M17] | alta · verificado |

### C. Payouts

| Concepto | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Primer payout | 48 h después del primer *trade*, *buffer* de $2,100 ($1,600 en Add-On) cubierto y $500 por encima | «You may request a payout 48 hours after your first trade has been placed» | [M17] | alta · verificado |
| Ciclo | Mínimo 2 días cualificados · $500 netos desde el último · consistencia del 50 % en el ciclo | «Minimum Qualifying Days / Cycle 2 Days» | [M17] | alta · verificado |
| Mínimo · máximo | $500 · $2,000 por ciclo | «flat $2,000 payout cap, up to 5 sim payouts, each paid at 80/20» | [M17] | alta · verificado |
| Número máximo | **5 payouts** en simulada; después, Live | «After your 5th approved sim payout, you are eligible for promotion to a live funded account.» | [M17] | alta · verificado |
| Live | Blue Row Capital · MLL de $2,000 EOD, estático cuando llega a $0 · DLL de $1,000 · 80/20 · diario · mínimo $250 · 1 cuenta · enfriamiento de 21 días si se rompe | «Daily Loss Limit (Live) $1,000» | [M17] | alta · verificado |

### D. Automatización
**Permitida con condiciones** (regla general [M21]). Sin cláusula propia. La DLL con pausa suave
hace de corte diario y no rompe la cuenta. NinjaTrader 8 sí ([M7]); las NinjaScript Automated
Strategies no se mencionan expresamente. Con una sola cuenta, los copiadores apenas importan.

### E. Plataformas
Las mismas que en §1 ([M7]).

---

## 5. Signature (sin tamaño 50K: fuera del caso de referencia)

| Concepto | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Tamaños | Solo 5K, 10K y 20K, micros únicamente | «Signature 5k, Signature 10k and Signature 20k» | [M18] | alta · verificado |
| Precio (20K) | **Discrepancia**: $280 («Price (one-time)», [M18]); $467 en el *schema* de [M5]; $233.50 con promoción en [M7]. En los datos embebidos, $280 aparece como `reset_price` | «Price (one-time) $75 $140 $280» | [M18], [M5], [M7], [M6] | baja · discrepancia |
| Reglas | MLL estático · sin DLL · sin consistencia · sin días mínimos · tope de beneficio diario en simulada ($10,000 en 20K) | «There is no trailing drawdown and no end-of-day reset of the floor» | [M18] | alta · verificado |
| Payouts | 80/20 en simulada · cuando se quiera · mínimo de $250 (10K/20K) · Live tras 5 payouts o $5,000 solicitados · 90/10 en Live | «Payouts anytime» | [M18] | alta · verificado |
| Plataforma | **Solo Hyperprop** → **NinjaTrader 8 no**. Discrepancia: [M7] incluye Signature en el selector de planes de la página de NinjaTrader | «Hyperprop only. More platforms coming soon.» | [M18], [M7] | media · discrepancia |
| Cuentas | 1 cuenta Signature (evaluación o simulada) | «One active Signature account at a time» | [M18] | alta · verificado |
| Automatización | Regla general [M21]; sin cláusula propia | — | [M21] | media |

---

## F. Elegibilidad internacional (toda la firma, según la fuente)

| Concepto | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| **República Dominicana** | **No figura** en la lista de países restringidos. Sí figuran Haití, Jamaica, Bahamas, Barbados, Trinidad y Tobago, Panamá, Nicaragua, Guyana, Cuba y Venezuela | «we are unable to accept traders from the below countries» | [M30] (14-10-2026), [M31] | media · verificado (por ausencia en la lista) |
| Criterio | Ciudadanía o residencia en países sancionados por la OFAC o restringidos por los socios | «Anyone with citizenship or residency in a country on OFAC's Sanctioned Countries list, or those restricted by our partners» | [M31] | alta · verificado |
| Términos | Jurisdicciones restringidas por ley u OFAC; existen «participantes restringidos» que solo acceden a la simulada, con payouts limitados, y **no se dice quiénes son** | «Restricted participants may only access simulated accounts, with limited payouts.» | [M8] §24 | media · parcial |
| Viajes | Se puede operar estando de viaje en un país restringido, pero no comprar ni hacer reset | «traders cannot purchase new accounts or reset current accounts during their stay there.» | [M30] | alta · verificado |
| KYC | Sumsub · documento de identidad, selfie en vivo y prueba de domicilio de ≤ 3 meses · AML (OFAC, ONU, UE…) | «cannot be older than 3 months» | [M31] | alta · verificado |
| Compra | Visa/Mastercard a nombre propio; cripto. Hay una lista de países sin pago con cripto **en una imagen ilegible** | «cryptocurrency is not an accepted form of payment for customers in the following jurisdictions.» | [M32] | — · **Sin datos** (lista) |
| Cobro desde RD | Riseworks (banco o cripto); Plaid/ACH solo en EE. UU. **Si Rise está disponible en RD: no lo dice la fuente oficial** | «You can withdraw funds via bank transfer or cryptocurrency.» | [M20] | — · no verificado |
| Impuestos | 1099 por Rise (EE. UU.). **W-8BEN: no lo dice la fuente oficial** | «Traders who successfully achieved payouts through the Rise payment platform will be sent their 1099 tax documents» | [M33] | media · parcial |
| Live desde RD | No lo dice la fuente oficial | — | — | — · no verificado |

---

## G. Fuentes

Todas consultadas el **2026-11-27** con `curl` (agente de usuario por defecto) y respuesta HTTP 200.
La columna «Fecha» es la que muestra el propio artículo; la fecha de consulta es la de hoy.

| # | Dato principal | URL | Fecha del artículo | Confianza | Estado |
|---|---|---|---|---|---|
| M1 | Plan Rapid (tablas, FAQ, precio) | https://myfundedfutures.com/plans/rapid | — | media | parcial (precios sin rótulo) |
| M2 | Plan Rapid EOD | https://myfundedfutures.com/plans/rapid-eod | — | media | parcial (50K solo en datos embebidos) |
| M3 | Plan Pro | https://myfundedfutures.com/plans/pro | — | media | parcial |
| M4 | Plan Builder | https://myfundedfutures.com/plans/builder | — | alta | verificado |
| M5 | Plan Signature | https://myfundedfutures.com/plans/signature | — | baja | parcial (el texto se pinta con JS; solo datos estructurados) |
| M6 | Portada (datos embebidos `price_data`) | https://myfundedfutures.com/ | — | baja | no verificado (no es texto visible) |
| M7 | NinjaTrader, licencia, datos, ATM, NinjaScript | https://myfundedfutures.com/ninjatrader | — | alta | verificado |
| M8 | Términos generales (§23 conducta, §24 geografía) | https://myfundedfutures.com/terms | sin fecha visible | alta | verificado |
| M9 | Rapid 50K | https://help.myfundedfutures.com/en/articles/13134709-rapid-plan-50k-a-comprehensive-look | 2026-08-24 | alta | verificado |
| M10 | Drawdown intradía | https://help.myfundedfutures.com/en/articles/12802721-intraday-drawdown-explained | 2026-01-08 | alta | verificado |
| M11 | Rapid Live | https://help.myfundedfutures.com/en/articles/13134718-understanding-rapid-live | 2026-09-08 | alta | verificado |
| M12 | Reserva y bono | https://help.myfundedfutures.com/en/articles/13286746-rapid-plan-reserve-program-performance-bonus-structure | «Updated this week» | alta | verificado |
| M13 | Rapid EOD 50K | https://help.myfundedfutures.com/en/articles/16158363-rapid-eod-50k-a-comprehensive-look | 2026-08-24 | alta | verificado |
| M14 | Rapid EOD con DLL | https://help.myfundedfutures.com/en/articles/18337038-rapid-eod-with-dll-a-detailed-look | «over 2 weeks ago» | alta | verificado |
| M15 | Pro rediseñado | https://help.myfundedfutures.com/en/articles/17573707-comprehensive-look-into-redesigned-pro-plan | «Updated this week» | alta | verificado |
| M16 | Consistencia en Pro | https://help.myfundedfutures.com/en/articles/8694840-balancing-freedom-and-responsibility-consistency-for-sim-funded-pro-accounts-at-mffu | 2026-08-24 | alta | verificado |
| M17 | Builder 50K | https://help.myfundedfutures.com/en/articles/14290805-builder-plan-50k-a-comprehensive-guide | 2026-10-21 | alta | verificado |
| M18 | Signature | https://help.myfundedfutures.com/en/articles/18543937-signature-plans-a-comprehensive-guide | «Updated this week» | alta | verificado |
| M19 | Política de payouts | https://help.myfundedfutures.com/en/articles/13745661-payout-policy-overview-best-and-fastest-prop-firm-payouts | «Updated this week» | media | discrepancias con [M15]/[M17] |
| M20 | Primer payout, Rise, Plaid | https://help.myfundedfutures.com/en/articles/11542406-guide-to-your-first-payout-quick-and-easy-process | 2026-08-26 | alta | verificado |
| M21 | Fair Play y automatización (también en https://intercom.help/myfundedfutures/en/articles/8444599-fair-play-and-prohibited-trading-practices) | https://help.myfundedfutures.com/en/articles/8444599-fair-play-and-prohibited-trading-practices | «over a month ago» | alta | verificado |
| M22 | Copy trading | https://help.myfundedfutures.com/en/articles/10771500-copy-trading-at-myfundedfutures | 2026-08-24 | alta | verificado |
| M23 | Terceros y dispositivos | https://help.myfundedfutures.com/en/articles/8230018-can-someone-else-trade-my-account | 2026-08-24 | alta | verificado |
| M24 | Hedging | https://help.myfundedfutures.com/en/articles/12011241-hedging-what-you-should-know | 2025-11-10 | alta | verificado |
| M25 | Noticias | https://help.myfundedfutures.com/en/articles/8230009-news-trading-policy | 2026-08-31 | media | parcial (calendario T1 en imagen) |
| M26 | Horarios | https://help.myfundedfutures.com/en/articles/9558251-permitted-times-to-trade | 2026-08-24 | alta | verificado |
| M27 | Instrumentos y comisiones | https://help.myfundedfutures.com/en/articles/9735811-futures-instrument-list | 2026-08-24 | alta | verificado |
| M28 | Regla del 2 % | https://help.myfundedfutures.com/en/articles/9698984-2-price-limit-rule | 2026-08-24 | alta | verificado |
| M29 | Política entre instrumentos | https://help.myfundedfutures.com/en/articles/10244682-cross-instrument-policy | 2026-08-24 | media | ejemplo desfasado |
| M30 | Países restringidos | https://help.myfundedfutures.com/en/articles/8229993-restricted-countries-policy | 2026-10-14 | alta | verificado |
| M31 | KYC/AML | https://help.myfundedfutures.com/en/articles/9717961-kyc-aml-policies | 2026-10-13 | alta | verificado |
| M32 | Medios de pago | https://help.myfundedfutures.com/en/articles/17339138-accepted-payment-methods | 2026-10-05 | media | parcial (lista de cripto en imagen) |
| M33 | 1099 | https://help.myfundedfutures.com/en/articles/13337287-your-1099-tax-documents | 2026-03-04 | alta | verificado |
| M34 | Evaluaciones (todas) | https://help.myfundedfutures.com/en/articles/11802636-traders-evaluation-simplified | 2026-09-24 | alta | verificado |
| M35 | De evaluación a simulada · límites de cuentas | https://help.myfundedfutures.com/en/articles/16498635-moving-from-evaluation-to-sim-funded-account | 2026-09-04 | alta | verificado |
| M36 | Consistencia | https://help.myfundedfutures.com/en/articles/11994562-consistency-rule-at-my-fundedfutures | 2026-09-25 | alta | verificado |
| M37 | Inactividad y pago único | https://help.myfundedfutures.com/en/articles/16596524-inactivity-rule-one-time-payment-model | «over 3 weeks ago» | alta | verificado |
| M38 | Resets y renovaciones | https://help.myfundedfutures.com/en/articles/16596406-understanding-the-difference-between-account-resets-and-renewals | 2026-09-24 | alta | verificado (sin importes) |
| M39 | Reembolsos | https://help.myfundedfutures.com/en/articles/11542523-refund-cancellation-policy-transparent-and-trader-first | 2026-08-27 | alta | verificado |
| M40 | Activación | https://help.myfundedfutures.com/en/articles/12398151-does-myfundedfutures-charge-activation-fees | 2026-08-25 | alta | verificado |
| M41 | Plataformas soportadas | https://help.myfundedfutures.com/en/articles/8528335-overview-of-supported-platforms-at-mffu | 2026-10-08 | alta | verificado |
| M42 | Conexión de NinjaTrader | https://help.myfundedfutures.com/en/articles/10082979-ninjatrader-login-instructions | 2026-08-24 | alta | verificado |
| M43 | Conexión a plataformas | https://help.myfundedfutures.com/en/articles/8528337-connecting-to-different-platforms-at-mffu | 2026-08-24 | alta | verificado |
| M44 | FAQ de Live (antigua, planes Legacy) | https://help.myfundedfutures.com/en/articles/12109396-comprehensive-faq-live-accounts-at-myfunded-futures | 2025-11-10 | baja | desfasado |
| M45 | Drawdown EOD | https://help.myfundedfutures.com/en/articles/8348565-end-of-day-eod-drawdown-explained | 2026-08-24 | media | verificado (genérico) |
| M46 | Paso instantáneo a simulada | https://help.myfundedfutures.com/en/articles/13523548-instant-sim-funded-upgrade | 2026-08-24 | alta | verificado |

### Páginas que no se pudieron leer o que quedan incompletas
- `/plans/signature` [M5]: el HTML estático solo trae el pie de página; las reglas salen de [M18].
- Las tablas de precios por tamaño de `/plans/rapid-eod` y del Pro One Day: el 50K **solo** está en
  datos embebidos, no en el texto visible (confianza baja).
- El importe de los **resets** no aparece en ningún texto visible (Sin datos).
- La lista de países sin pago con cripto [M32] y el calendario de noticias T1 de 2026 [M25] son
  imágenes en `downloads.intercomcdn.com`, un host no autorizado: **Sin datos**.
- No se encontró ninguna página de MFFU que diga si Rise opera en República Dominicana.
- Ninguna página respondió 403.

### Aviso de método
- Se leyeron 46 artículos del help center, 5 páginas de planes, la portada, `/ninjatrader`, `/terms`,
  `/disclaimer`, `/cancellation` y `/how-it-works`. Las descargas se hicieron **antes** de que llegara
  la instrucción de revisar los términos. Al revisarlos, `/terms` **no** contiene ninguna prohibición
  expresa de acceso automático; aun así, después de esa comprobación no se hizo **ninguna** petición
  más.
- Lo que falta (precios por tamaño pintados con JS, importes de reset y las imágenes) necesita que el
  operador lo lea en un navegador.
- Los descuentos son temporales (banner del 2026-11-27: «Save 40% On Any Plan With Code CLUB.»). Los
  precios de lista se toman de los datos estructurados (`schema.org Offer`) de cada página.
