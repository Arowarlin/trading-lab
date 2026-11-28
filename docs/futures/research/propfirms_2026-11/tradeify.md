# Tradeify · ficha de reglas de fondeo (investigación 2026-11)

- **ID**: `tradeify` · **Fecha de consulta**: 2026-11-27 · **Cuenta de referencia**: 50K.
- **Programas analizados** (una subsección cada uno; no se trasladan reglas de uno a otro):
  §1 **Growth 50K** (evaluación y financiada) · §2 **Select 50K** (evaluación; tras aprobar, **Select
  Flex** o **Select Daily**) · §3 **Lightning Funded 50K** (sin evaluación) · §4 **Inter Miami V2
  50K** (edición limitada, solo micros). Quedan fuera de alcance Level Up (escalera de 10 niveles, no
  es 50K), Select 300K, Legacy Live y Tradeify 247/Perps.
- **Fuentes**: help center oficial servido en `intercom.help/tradeify/en/`. Su dominio canónico,
  `help.tradeify.co`, devuelve **403** (desafío de Cloudflare) y no se intentó saltar. También
  `tradeify.co/`, `tradeify.co/terms-of-use` y `tradeify.co/funded-trader-agreement`, que se titula
  «Tradeify Evaluation Services Agreement», «Last modified: October 2026».
- **Formato de cada dato**: valor · «cita literal» (≤ 25 palabras) · [T#] (URL exacta y fecha del
  artículo en §G) · confianza · estado. Todo se consultó el 2026-11-27. La aritmética sobre cifras
  oficiales se marca **(cálculo propio)**.
- **⚠ Términos de uso y acceso automático**: los Términos de uso de Tradeify **prohíben** los robots y
  el *scraping* del sitio (cita en §G). La cláusula se encontró **después** de haber descargado las
  páginas. A partir de ahí no se hizo **ninguna** petición más a Tradeify. Los campos que faltan
  requieren que el operador los lea en un navegador.

## Resumen (50K)

| Plan | Automatización | NinjaTrader 8 | Coste hasta la 1.ª cuenta financiada (1 intento) | Reparto · mínimo · máximo · frecuencia |
|---|---|---|---|---|
| Growth 50K | **Permitida con condiciones estrictas** (bot propio demostrable, vídeo en directo si lo piden, **uso exclusivo en Tradeify**, sin HFT, regla de 10 s para cobrar) | Sí, **solo con el bróker Tradovate** y la licencia de empresa de Tradeify | **$145** de referencia · ~$101.50 con el código NOV (−30 % hasta el 30-11; **cálculo propio**) · activación $0 | 90/10 · $500 · $1,500 → $2,000 → $2,500 → $3,000 (del 4.º en adelante) · un ciclo por cada 5 días rentables ≥ $150 |
| Select 50K → Flex | Igual que Growth | Igual | **$174** (consistencia del 40 %) · $145 (30 %) · $216 (add-on del 50 %) · con NOV: $121.80 / $101.50 / $151.20 **(cálculo propio)** | 90/10 · $250 · 50 % del beneficio total, con tope de **$2,500** ($2,000 con el add-on del 50 %) · cada 5 días ganadores ≥ $150 |
| Select 50K → Daily | Igual | Igual | Igual que Select | 90/10 · $250 · 2 × el beneficio del ciclo, con tope de **$1,250** · diario tras un *buffer* de $2,100 |
| Lightning 50K | Igual | Igual | **$492** (sin evaluación) · ~$344.40 con NOV **(cálculo propio)** | 90/10 · **$1,000** · $2,000 (payouts 1 a 3) / $2,500 (del 4.º en adelante) · al llegar a la meta: $3,000 la primera vez y $2,000 las siguientes |
| Inter Miami V2 50K | Igual (sin cláusula propia) | **Sin datos** (los datos embebidos solo muestran WealthCharts y Tradesea) | Lista **$628** sin DLL · $418 o $376 con DLL suave (**discrepancia**) · con el 30 %: $439.60 / $263.20 (publicado) | 80 % al trader + 10 % a un fondo Live · $600 brutos · **tope total de $12,000** · a petición, revisado al cierre del día |

- **República Dominicana**: **no figura** en la lista de 65 países prohibidos ([T21]) ni en la de
  KYC obligatorio antes de recibir la cuenta financiada ([T22]). Estado: verificado por ausencia en
  una lista cerrada · confianza media. Sin confirmar: si RD puede tener Elite Live (la lista de no
  elegibles que cita [T3] §17 no se encontró: **Sin datos**) y si Rise opera en RD (**Sin datos**;
  si no opera, se cobra por Plane).
- **Comisiones ida y vuelta** (todos los planes, [T5], [T7]): NQ **$5.76** · MNQ **$1.82** · GC $6.20 ·
  MGC $2.12.

---

## Políticas de toda la firma (la fuente las declara generales, para todas las cuentas)

| Tema | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Bots y algoritmos | Permitidos si el trader demuestra ser el único dueño, la estrategia no se comparte y no es HFT | «Ownership: You must be able to prove that you are the sole owner of the bot or strategy» | [T4], [T3] §6.6 | alta · verificado |
| Verificación del bot | Rastrean órdenes similares en otras cuentas y pueden pedir un vídeo en directo activando el código | «We will also require a live video of you enabling the code on your own PC.» | [T4] | alta · verificado |
| **Exclusividad** | **Usar el mismo bot en otras firmas va contra su política** | «using it across multiple firms is against Tradeify's policy.» | [T4], [T3] §6.6 | alta · verificado |
| HFT | Prohibido; además, el acuerdo trata como manipulación los *trades* «short-term or high-frequency» | «This includes short-term or high-frequency trades.» | [T3] §6.4, [T4] | alta · verificado (sin umbral) |
| Automatización en general | Solo lo permitido expresamente; el trader responde de todo | «No trading technology exempts a trader from any Tradeify rule.» | [T23] | alta · verificado |
| Microscalping (solo en financiadas) | Para pedir un payout, más del 50 % de los *trades* y más del 50 % del beneficio deben venir de *trades* de más de 10 s. Si no se cumple, no hay payout, pero la cuenta no falla | «Over 50% of your profit must come from trades held longer than 10 seconds.» | [T4], [T17], [T25] | alta · verificado |
| Discrepancia de microscalping | [T3] §6.8 solo exige el criterio del beneficio («50% or more») | «50% or more of the Trader’s account profit must come from trades held longer than ten (10) seconds.» | [T3] | media · discrepancia (en reglas de trading prevalece el help center, [T3]) |
| DCA | El help center lo permite; [T3] §6.5 pide evitarlo | «avoiding dollar-cost averaging and high-frequency trading» | [T4], [T3] | media · discrepancia (prevalece el help center: «the Help Center rule shall prevail with respect to trading rules») |
| Copiadores | Solo entre cuentas propias y en la misma dirección; los copiadores de terceros, por cuenta y riesgo del trader; en el *Group Trading* de Tradovate no funcionan las ATM | «You may only group trade between accounts you own and manage.» | [T28], [T29], [T19] | alta · verificado |
| Hedging | Prohibido en el mismo producto o en productos del mismo grupo, en una cuenta o entre varias; se pierden los beneficios | «whether those positions sit in a single account or are spread across several of your accounts.» | [T4], [T19] | alta · verificado |
| VPS y VPN | No se puede **iniciar sesión** con VPN o VPS; después se puede operar en un VPS por cuenta propia. Los Términos prohíben el VPS que oculte el dispositivo o la ubicación | «You cannot log in with VPN/VPS. After logging in normally, you may use VPS for trading at your own risk.» | [T25], [T2] | alta · verificado |
| Anulación de beneficios | Sí: pueden «deny, cancel, or void activity», restringir payouts y cerrar cuentas asociadas | «restrict account functionality or payouts» | [T23], [T3] | alta · verificado |
| KYT | Entrevista con IA, sin ayuda de software ni de IA; pueden pedirla antes de financiar o de pagar | «Tradeify may require a KYT interview at any stage of an account's lifecycle» | [T24] | alta · verificado |
| Horario | Cerrar todo antes de las 16:45 ET (12:59 en medias sesiones); el cierre automático no rompe la cuenta | «All positions must be closed by 4:45 PM Eastern Time each trading day.» | [T18] | alta · verificado |
| Overnight y fin de semana | No, en ninguna cuenta (Live incluida) | «This applies to ALL account types including Live.» | [T18] | alta · verificado |
| Noticias | Sin restricciones | «We do not have any rules against or guidelines around trading news events.» | [T17] | alta · verificado |
| Drawdown | EOD trailing en todas las cuentas, aplicado en tiempo real sobre la *net liquidation* (con P&L no realizado) | «All Tradeify accounts use EOD Trailing Drawdown.» | [T15] | alta · verificado |
| Bloqueo en financiada (50K) | Con saldo EOD de $52,100 (o al pedir el payout) el suelo se fija en $50,100 | «your drawdown locks in place once you profit beyond the drawdown amount by $100» | [T15] | alta · verificado |
| Equivalencia de micros | 10 micros = 1 mini; se pueden combinar dentro del límite | «10 Micro contracts = 1 Mini contract» | [T35], [T12] | alta · verificado |
| Inactividad | Al menos un *trade* por semana (lunes a viernes) y por cuenta | «This is per account, not per user.» | [T4] | alta · verificado |
| Cuentas | Hasta 5 simuladas financiadas por persona **y por hogar**; evaluaciones sin límite. **Discrepancia**: [T5] limita a 15 compras de Select cada 30 días | «A household is also restricted to 5 Simulated Funded Accounts at any time» | [T20], [T5] | media · discrepancia |
| Activación | $0 en todos los planes; se activa a mano desde el panel | «There are no activation fees for Tradeify accounts.» | [T6] | alta · verificado |
| Modalidad · reembolsos | Pago único sin cobros recurrentes · sin reembolsos | «All plans are one-time purchases with no recurring billing.» · «All sales are final.» | [T5] | alta · verificado |
| Datos | L1 gratis si se firma el acuerdo No Profesional; si no, $300/mes · L2 y EUREX de pago, solo en Tradovate | «If you do not sign it, you may incur a $300/month professional data fee.» | [T5] | alta · verificado |
| KYC | Sumsub (documento y selfie) antes del 1.er payout; para algunos países, antes de financiar; con cripto, al comprar | «identity verification is required before your first payout» | [T22] | alta · verificado |
| Cobro | Rise (por defecto) y Plane como alternativa; transferencia bancaria o cripto; **sin PayPal** | «We process payouts via Riseworks and Plane. Options include bank transfer and cryptocurrency.» | [T25], [T30], [T31] | alta · verificado |
| Plazos (pedido → aprobado → pagado → recibido) | Una vez aprobado, se descuenta del saldo · pago en ≤ 24 h, una vez completado el alta en Rise (≤ 72 h fuera de horario) · en la cartera de Rise en 24–48 h · al banco por ACH en 1–3 días hábiles, en cripto en horas · Plane hasta 7 días | «Payments will be issued within 24 hours after the withdrawal has been processed, once your Rise onboarding is complete.» | [T9], [T30], [T31] | alta · verificado |
| Discrepancia de plazos | La portada anuncia «1 hour payouts» y «get paid in minutes» | — | [T1] | baja · discrepancia (publicidad) |
| Paso a Elite Live | Requisito mínimo para ser **considerado**: 3 payouts en una cuenta o 10 en total. **Discrepancia**: la portada dice 5 | «Hit 5 approved payouts to qualify for Tradeify Elite» | [T11], [T32], [T1] | media · discrepancia |
| Elite Live | 80/20 · payouts diarios · saldo inicial $0 · drawdown EOD de $2,000 en 50K · sin DLL · no puede coexistir con simuladas en el mismo hogar | «You cannot have Sim Funded and Live Funded accounts active at the same time.» | [T32] | alta · verificado |

---

## 1. Growth 50K

### A. Costes

| Concepto | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Precio (referencia oficial, sin código) | **$145**, pago único | «Growth 50K costs $145, and a reset costs $95.» | [T5] | alta · verificado |
| Reset | **$95**; los códigos promocionales no se aplican | «promo codes and discount codes do not apply to reset purchases.» | [T5], [T33] | alta · verificado |
| Promoción vigente | Código NOV: −30 % hasta el 30-11-2026 → **$101.50 (cálculo propio, cifra no publicada)** | «Get 30% Off with code "NOV"» · «ENDS 30 NOVEMBER, 11:59PM EST» | [T1] | media · parcial |
| Precio en la portada | Las tarjetas visibles muestran «$359 $251» y «Save $X with code DASH» en todos los tamaños: es una **plantilla, ambigua**, y no se usa | — | [T1] | baja · ambiguo |
| Paquete | 5 cuentas iguales: −5 %, acumulable con códigos | «receive an automatic 5% discount» | [T5] | alta · verificado |
| Activación · cuota mensual | $0 · ninguna | «Q: Are there any monthly fees after funding? A: No» | [T6], [T25] | alta · verificado |
| Comisiones | NQ $5.76 · MNQ $1.82 | «$5.76 for NQ (E-mini Nasdaq)» | [T5] | alta · verificado |
| Coste hasta la financiada (mejor caso) | **$145** ($101.50 con NOV) **(cálculo propio)** | — | — | alta |
| Mantenerla 3 y 6 meses | **$0 fijos** más comisiones; TradingView opcional desde $12.95/mes **(cálculo propio)** | «Paid TradingView subscriptions start at $12.95/month» | [T5] | alta |

### B. Reglas de trading

| Regla | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Evaluación | Objetivo de $3,000 · DLL de $1,250 (suave) · drawdown trailing EOD de $2,000 · 4 contratos (40 micros) · sin consistencia · 1 día mínimo · sin plazo | «the profit target is $3,000, the Daily Loss Limit is $1,250, the trailing max drawdown is $2,000» | [T8] | alta · verificado |
| DLL | Suave: pausa hasta las 18:00 ET y no rompe la cuenta. En la financiada sube a $2,000 cuando el saldo llega a $53,000 | «If you hit it, trading stops for the day but your account is not failed.» | [T8], [T14] | alta · verificado |
| Consistencia en financiada | **35 %** ([T9], [T16], [T5]). **Discrepancia**: [T10] dice que Growth no tiene consistencia «at any stage» | «Consistency Rule: Abide by the 35% Consistency Rule» | [T9], [T10] | media · discrepancia (prevalece el 35 %: 3 fuentes, la política de payouts incluida) |
| Contratos en financiada | El máximo desde el primer día (4/40) | «Growth and Lightning use their maximum position size from day one» | [T35] | alta · verificado |
| Activaciones | Máximo 5 activaciones de Growth por día | «You can activate a maximum of 5 GROWTH™ Funded accounts per day.» | [T8] | alta · verificado |
| Reset de la financiada | No existe | «the Simulated Funded counterpart cannot be reset.» | [T8] | alta · verificado |

### C. Payouts

| Concepto | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Días | 5 días con beneficio > $150; el conteo vuelve a cero tras cada payout | «$150 in profit for 50k accounts» | [T9] | alta · verificado |
| Saldo mínimo | $53,000 | «$53,000 on a $50,000 account» | [T9] | alta · verificado |
| Mínimo · máximo | $500 · $1,500 / $2,000 / $2,500 / $3,000 (del 4.º payout en adelante) | «it is $1,500 for Payout 1, $2,000 for Payout 2, $2,500 for Payout 3, and $3,000 for Payout 4 and later.» | [T9] | alta · verificado |
| Número máximo de retiros | No publicado (Tradeify puede pasar la cuenta a Live tras un payout) | «Tradeify reserves the right to move you to a Live Funded Account at any time after a successful payout.» | [T9] | alta · verificado |
| Reparto | 90/10 | «Traders receive 90% of the payout amount requested.» | [T9] | alta · verificado |
| Margen tras el 1.er payout (cálculo de la fuente) | $53,000 − $1,500 = $51,500, frente a un suelo de $50,100 | «you would leave yourself with $1,400 in drawdown room.» | [T9] | alta · verificado |

### D. Automatización
**Permitida con condiciones estrictas** (reglas generales [T4], [T3] §6.6, [T23]; Growth no tiene
cláusula propia). La regla de 10 s solo cuenta en la financiada. NinjaTrader 8: sí, con el bróker
Tradovate ([T26], [T27]). **Las NinjaScript Automated Strategies y las ATM de NinjaTrader no se
mencionan expresamente**; se aplica la regla general de bots · confianza media. Las ATM de Tradovate
están documentadas ([T28]). Hasta 5 financiadas. VPS: véase la tabla general. Pueden anular
beneficios ([T23]).

### E. Plataformas
Se elige el bróker al comprar y no se puede cambiar: **Tradovate** (Tradovate, NinjaTrader y
TradingView) · **Rithmic** (Tradesea, Quantower, Sierra Chart con suscripción de pago, R|Trader) ·
**WealthCharts** ([T26]). NinjaTrader 8 solo con Tradovate y **solo con la licencia de empresa de
Tradeify** ([T27]: «Users are NOT able to use their personal license (or any other) on Tradeify
accounts.»). CQG, Bookmap, ATAS y la API: **no los menciona la fuente oficial**. Conexiones
simultáneas: NinjaTrader y Tradovate se sincronizan ([T27]); límite: no lo dice.

---

## 2. Select 50K (evaluación → Select Flex o Select Daily)

### A. Costes

| Concepto | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Precio con consistencia del 40 % | **$174** · reset $119 | «Select 50K costs $174, and a reset costs $119.» | [T5] | alta · verificado |
| Precio con consistencia del 30 % | $145 · reset $105 | «Select 50K costs $145, and a reset costs $105.» | [T5] | alta · verificado |
| Add-on de consistencia del 50 % | $216 · reset $152 | «Select 50K costs $216, and a reset costs $152.» | [T5] | alta · verificado |
| Discrepancia | Los datos embebidos de la portada dan un precio por defecto de $165 para Select 50K | — | [T1] | baja · discrepancia |
| Promoción NOV (−30 %) | $121.80 / $101.50 / $151.20 **(cálculo propio)** | — | [T1] | media · parcial |
| Funded Reset (si se rompe la Select financiada) | Disponible en 50K, dentro de los 30 días y como mucho 2 veces; no si ya hubo un payout. **El precio no se publica** («The second use costs 10% more than the first.») | «Select simulated-funded accounts at 50K, 100K and 150K» | [T34] | media · parcial (Sin datos de precio) |
| Coste hasta la financiada | **$174** (40 %) · $145 (30 %) · $216 (50 %) **(cálculo propio)** | — | — | alta |
| Mantenerla 3 y 6 meses | $0 fijos más comisiones **(cálculo propio)** | — | [T10] | alta |

### B. Reglas de trading

| Regla | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Evaluación | $3,000 · $2,000 EOD · sin DLL · 4/40 · consistencia del 40 % (3 días mínimos), del 30 % (4 días) o del 50 % (2 días) | «Profit Target: $3,000 Maximum Drawdown: $2,000 (End of Day)» | [T10] | alta · verificado |
| Objetivo antiguo | Las cuentas compradas antes del nuevo panel mantienen $2,500 | «retain their original $2,500 profit target» | [T10] | alta · verificado |
| Consistencia en financiada | Ninguna (ni Flex ni Daily) | «the consistency rule is removed regardless of which payout policy» | [T10] | alta · verificado |
| Flex (financiada) | Drawdown EOD de $2,000 · **sin DLL** | «Daily Loss Limit None» | [T11] | alta · verificado |
| Daily (financiada) | Drawdown EOD de $2,000 · **DLL suave de $1,000** | «Daily Loss Limit $500 $1,000 $1,250 $1,750» | [T11], [T14] | alta · verificado |
| Escalado (Flex y Daily) | Empieza en 2/20; con +$1,500 al cierre pasa a 3/30 y con +$2,000 a 4/40 | «Start trading with 2 minis / 20 micros» | [T11] | alta · verificado |
| Elección de la vía | Al activar; definitiva para esa cuenta | «Your choice is permanent» | [T10], [T11] | alta · verificado |

### C. Payouts

| Concepto | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| **Flex**: frecuencia | Cada 5 días ganadores (≥ $150) · sin saldo mínimo | «Payout Frequency: Every 5 winning days» | [T11] | alta · verificado |
| **Flex**: importe | 50 % del beneficio total, con tope de **$2,500** (compras desde el 1-9-2026; antes, $3,000) · **$2,000 con el add-on del 50 %** · mínimo $250 | «capped at $2,500 per payout» | [T11] | alta · verificado |
| **Daily**: buffer | $2,100 (no se puede retirar por debajo) | «You cannot withdraw profits that would bring your account balance below the buffer amount.» | [T11] | alta · verificado |
| **Daily**: importe | Hasta 2 × el beneficio desde el último payout, con tope de **$1,250** (compras desde el 1-9-2026; antes, $1,000) · mínimo $250 | «They may request up to 2× the profit earned between each payout request» | [T11] | alta · verificado |
| Ciclo con pérdidas | Hay que volver a estar en positivo en el ciclo (Flex y Daily) | «neither policy allows payouts while your cycle profit is negative.» | [T11] | alta · verificado |
| Solicitudes abiertas | Solo una a la vez por cuenta | «Only one payout request can be open on an account at a time» | [T11] | alta · verificado |
| Reparto | 90/10 | — | [T11] | alta · verificado |

### D. Automatización
**Permitida con condiciones estrictas** (reglas generales; Select no tiene cláusula propia). En Daily,
la DLL de $1,000 detiene el bot el resto del día. La regla de 10 s cuenta en la financiada y no en la
evaluación. NinjaTrader 8: igual que en §1.

### E. Plataformas
Las mismas que en §1 ([T26]).

---

## 3. Lightning Funded 50K (sin evaluación)

### A. Costes

| Concepto | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Precio | **$492**, pago único, sin reset | «Lightning 50K costs $492.» | [T5] | alta · verificado |
| Promoción NOV | ~$344.40 **(cálculo propio)** | — | [T1], [T25] | media · parcial |
| Reset | No existe: si falla, se compra otra | «No resets are available — if the account fails, a new one must be purchased.» | [T5] | alta · verificado |
| Coste hasta la financiada | **$492** (es directa) | — | — | alta |
| Mantenerla 3 y 6 meses | $0 fijos más comisiones **(cálculo propio)** | — | [T5] | alta |

### B. Reglas de trading

| Regla | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Parámetros | Sin días mínimos · DLL suave de $1,250 (pasa a $2,000 con $53,000) · drawdown trailing EOD de $2,000 · 4 contratos (40 micros) desde el primer día | «$50k None $1,250 $2,000 4 Contracts (40 Micros)» | [T12], [T14], [T35] | alta · verificado |
| Consistencia | 20 % en el 1.er payout, 25 % en el 2.º y 30 % del 3.º en adelante | «20% Consistency Rule for the first payout, then 25% for the second payout, and 30% for all subsequent payouts.» | [T13], [T16] | alta · verificado |
| Bloqueo | $52,100 → suelo de $50,100 | — | [T15] | alta · verificado |

### C. Payouts

| Concepto | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Meta de beneficio | $3,000 para el 1.º · $2,000 para cada uno de los siguientes (beneficio nuevo; lo sobrante no se arrastra) | «Leftover profit from the previous cycle does not carry over.» | [T13] | alta · verificado |
| Días | Sin mínimo | «Minimum Days Traded: No Minimum Trading Day Count.» | [T13] | alta · verificado |
| Mínimo · máximo | **$1,000** · $2,000 (payouts 1 a 3) / $2,500 (del 4.º en adelante) | «On a $50K account, it is $2,000 for Payouts 1, 2, and 3, and $2,500 for Payout 4 and later.» | [T13] | alta · verificado |
| Reparto | 90/10 | «Traders receive 90% of the payout amount requested.» | [T13] | alta · verificado |

### D. Automatización
Reglas generales: **permitida con condiciones estrictas**. La regla de 10 s se aplica desde el primer
día, porque la cuenta ya es financiada. NinjaTrader 8: igual que en §1 ([T27]: «Sim Funded (aka
Lightning Funded)»).

### E. Plataformas
Las mismas que en §1.

---

## 4. Inter Miami V2 50K (edición limitada, solo micros)

| Concepto | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| Precio de lista | Sin DLL **$628** · con DLL suave **$418** («Price, soft DLL (list)») · **discrepancia**: la tabla del código del 30 % da como lista $376 | «50K soft DLL $376 30% off $263.20» | [T36] | media · discrepancia |
| Con el código del 30 % | $439.60 (sin DLL) / $263.20 (con DLL) | «50K no DLL $628 30% off $439.60» | [T36] | alta · verificado |
| Compra | KYC obligatorio · una persona por hogar · máximo 10 evaluaciones por versión · máximo 3 Miami financiadas | «KYC is required for every user at purchase.» | [T36] | alta · verificado |
| Reglas | Objetivo de $3,500 · drawdown **estático** de $1,500 · 30 micros · sin días mínimos ni consistencia · DLL suave opcional de $900 | «It is static: the floor sits the drawdown amount below your starting balance and never moves» | [T36] | alta · verificado |
| Payouts | 80 % al trader, 10 % al fondo Live y 10 % a Tradeify · mínimo de $600 brutos · tope total de **$12,000** (lo que pase se pierde) · revisión al cierre del día | «Requests are capped at $12,000 in total across all your Miami accounts» | [T36] | alta · verificado |
| Live | Bróker Slay Markets · saldo de $1,500 (no retirable) · 20 micros · 90/10 · diario, mínimo $250 · al pasar a Live se pausan todas las demás cuentas | «Every account you hold is paused» | [T36] | alta · verificado |
| Automatización y plataformas | Sin cláusula propia: se aplican las reglas generales. Plataforma: **Sin datos** | — | — | baja |

---

## F. Elegibilidad internacional (toda la firma, según la fuente)

| Concepto | Valor | Cita | Fuente | Confianza · estado |
|---|---|---|---|---|
| **República Dominicana** | **No figura** en la lista de 65 países completamente restringidos. Sí figuran Bahamas, Barbados, Jamaica, Trinidad y Tobago, Panamá, Nicaragua, Cuba, Ecuador y Venezuela | «Full alphabetical list (65 countries)» | [T21] | media · verificado (por ausencia) |
| Criterio | Residencia permanente, no ubicación ([T21]). **Discrepancia**: [T3] §17 incluye a «citizens, residents, or are otherwise located in». En asuntos que no son reglas de trading prevalece el acuerdo | «These restrictions apply to your country of residency (where you permanently live), not your current physical location.» | [T21], [T3] | media · discrepancia |
| Elite Live | Hay jurisdicciones que pueden evaluar pero no ir a Elite Live; la lista «se mantiene en el Help Center» y **no se encontró** | «certain jurisdictions are eligible to purchase an evaluation account but are not eligible for a Tradeify Elite Live account» | [T3] §17 | — · **Sin datos** (lista) |
| KYC antes de financiar | Brasil, China, Italia, México, Rumanía, Corea del Sur, España, Taiwán, Tailandia, India, EAU y Reino Unido; **RD no está** | «identity verification is required before you receive a funded account» | [T22] | alta · verificado |
| Pago de compras | Tarjeta a nombre propio; cripto (Confirmo), con KYC al comprar | «You can only pay with a credit or debit card in your own name.» | [T25] | alta · verificado |
| Cobro desde RD | Rise, «primary payout provider for most countries», o Plane si Rise no opera en el país. **Si Rise cubre RD: Sin datos** | «if Rise is not available in your country, Tradeify will use Plane» | [T22], [T31] | — · no verificado |
| Impuestos | Rise pide el Tax ID del país y el **W-8BEN** a los no residentes en EE. UU.; el 1099 lo emite Rise | «Tax information (W-9 for US residents, W-8BEN for international)» | [T22], [T25] | alta · verificado |
| Documentos para Elite | Los documentos que no estén en inglés necesitan traducción profesional firmada y sellada (el pasaporte, no) | «Any document not in English must be professionally translated, signed and stamped.» | [T37] | alta · verificado |

---

## G. Fuentes

Consultadas el **2026-11-27** con `curl` (agente de usuario por defecto). Todas dieron HTTP 200,
salvo la marcada. Las páginas del help center se leyeron en `https://intercom.help/tradeify/en/…`;
su dominio canónico, `help.tradeify.co`, responde 403.

| # | Dato principal | URL | Fecha del artículo | Confianza | Estado |
|---|---|---|---|---|---|
| T1 | Portada (banner NOV, tarjetas, datos embebidos) | https://tradeify.co/ | — | baja | parcial (tarjetas = plantilla) |
| T2 | Términos de uso (scraping, VPS) | https://tradeify.co/terms-of-use | sin fecha visible | alta | verificado |
| T3 | Evaluation Services Agreement (§6, §17) | https://tradeify.co/funded-trader-agreement | «Last modified: October 2026» | alta | verificado |
| T4 | Normas para traders (bots, 10 s, DCA) | https://intercom.help/tradeify/en/articles/10468318-guidelines-for-traders | 2026-10-17 | alta | verificado |
| T5 | Referencia de precios | https://intercom.help/tradeify/en/articles/14369021-tradeify-pricing-reference | «Updated this week» | alta | verificado |
| T6 | Activación | https://intercom.help/tradeify/en/articles/10468246-are-there-activation-fees | 2026-10-17 | alta | verificado |
| T7 | Comisiones | https://intercom.help/tradeify/en/articles/10468315-trading-commission-fees | 2026-10-17 | alta | verificado |
| T8 | Evaluación Growth | https://intercom.help/tradeify/en/articles/10495915-growth-evaluation-accounts | 2026-10-20 | alta | verificado |
| T9 | Payouts de Growth | https://intercom.help/tradeify/en/articles/11083796-growth-funded-account-payout-policy | 2026-10-17 | alta | verificado |
| T10 | Evaluación Select | https://intercom.help/tradeify/en/articles/12853921-select-evaluation-accounts | «Updated this week» | alta | verificado |
| T11 | Payouts de Select Flex y Daily | https://intercom.help/tradeify/en/articles/12853966-select-flex-and-select-daily-payout-policies | «over 3 weeks ago» | alta | verificado |
| T12 | Lightning Funded | https://intercom.help/tradeify/en/articles/10495938-lightning-funded-accounts | «Updated this week» | alta | verificado |
| T13 | Payouts de Lightning | https://intercom.help/tradeify/en/articles/10495932-lightning-funded-account-payout-policy | 2026-10-17 | alta | verificado |
| T14 | DLL | https://intercom.help/tradeify/en/articles/10468321-rules-daily-loss-limit | 2026-10-17 | alta | verificado |
| T15 | Drawdown trailing | https://intercom.help/tradeify/en/articles/10495897-rules-trailing-max-drawdowns | 2026-10-15 | alta | verificado |
| T16 | Consistencia | https://intercom.help/tradeify/en/articles/10468320-rules-consistency-rule | 2026-10-17 | alta | verificado |
| T17 | Noticias | https://intercom.help/tradeify/en/articles/10495874-rules-news-trading | 2026-08-12 | alta | verificado |
| T18 | Horarios | https://intercom.help/tradeify/en/articles/10495876-rules-permitted-times-to-trade | 2026-10-17 | alta | verificado |
| T19 | Hedging y productos correlacionados | https://intercom.help/tradeify/en/articles/10495868-rules-hedging-correlated-products | 2026-08-19 | alta | verificado |
| T20 | Límite de cuentas | https://intercom.help/tradeify/en/articles/10468251-how-many-simulated-funded-accounts-can-i-have-at-once | «over a week ago» | alta | verificado |
| T21 | Países restringidos | https://intercom.help/tradeify/en/articles/10495888-rules-restricted-countries | «over a week ago» | alta | verificado |
| T22 | KYC/AML, Rise, W-8BEN | https://intercom.help/tradeify/en/articles/11384149-kyc-and-aml-policy | «over 3 weeks ago» | alta | verificado |
| T23 | Riesgo y cumplimiento | https://intercom.help/tradeify/en/articles/17069653-risk-compliance-guidelines-faq | 2026-10-01 | alta | verificado |
| T24 | KYT | https://intercom.help/tradeify/en/articles/17229690-know-your-trader-kyt-policy | 2026-10-17 | alta | verificado |
| T25 | Preguntas frecuentes (VPS, PayPal, plazos) | https://intercom.help/tradeify/en/articles/12268494-common-faqs | «Updated today» | alta | verificado |
| T26 | Plataformas soportadas | https://intercom.help/tradeify/en/articles/10468221-supported-platforms | 2026-10-17 | alta | verificado |
| T27 | NinjaTrader 8 | https://intercom.help/tradeify/en/articles/12268716-ninjatrader-8-setup-guide | 2026-07-31 | alta | verificado |
| T28 | Tradovate: ATM y *Group Trading* | https://intercom.help/tradeify/en/articles/13196343-tradovate-order-entry-copy-trading | 2026-01-22 | alta | verificado |
| T29 | WealthCharts: copiador | https://intercom.help/tradeify/en/articles/13825156-wealthcharts-order-entry-trade-copier | 2026-07-21 | alta | verificado |
| T30 | Rise | https://intercom.help/tradeify/en/articles/12844518-rise-payouts-main-payout-method | «Updated today» | alta | verificado |
| T31 | Plane | https://intercom.help/tradeify/en/articles/10495945-plane-payouts-an-alternative-payout-option | 2025-12-19 | media | verificado |
| T32 | Elite Live | https://intercom.help/tradeify/en/articles/12969284-tradeify-elite-program | «Updated this week» | alta | verificado |
| T33 | Reset de la evaluación | https://intercom.help/tradeify/en/articles/10468256-how-do-i-reset-a-failed-evaluation | 2026-10-17 | alta | verificado |
| T34 | Funded Reset | https://intercom.help/tradeify/en/articles/17780377-funded-reset-faq | «over a week ago» | media | parcial (sin precio) |
| T35 | Resumen de reglas | https://intercom.help/tradeify/en/articles/12268167-essential-trading-rules-overview | 2026-10-17 | alta | verificado |
| T36 | Miami V1/V2 | https://intercom.help/tradeify/en/articles/18370624-miami-plan-v1-v2-faq | «over a week ago» | media | discrepancia de precio |
| T37 | Alta en Elite: documentos | https://intercom.help/tradeify/en/articles/18534475-elite-live-onboarding-documents-payouts | «Updated this week» | alta | verificado |
| T38 | Help center canónico | https://help.tradeify.co/en/ | — | — | **403** (Cloudflare «Just a moment...») |

### Prohibición de acceso automático en los Términos y campos pendientes
- **Cláusula** (Términos de uso de Tradeify, https://tradeify.co/terms-of-use, consultados el
  2026-11-27). Define el «Site» como «The www.tradeify.co website and all contents thereof» y prohíbe:
  «use any robot, spider, scraper or other automatic device … to access, harvest, monitor, copy or use
  the Site without the express written permission of Tradeify».
- **Qué se hizo**: las páginas de este informe (unas 80 peticiones: 76 páginas guardadas más
  3 comprobaciones de acceso a `tradeify.co`, `help.tradeify.co` e `intercom.help/tradeify`) se descargaron **antes** de comprobar esta cláusula. Al encontrarla, se
  dejó de descargar y no se hizo **ninguna** petición más a Tradeify. El help center se sirve en
  `intercom.help`, pero por prudencia se trata como parte del mismo sitio.
- **Pendiente de que el operador lo lea en un navegador**: (1) precios reales de la portada y del
  checkout por tamaño, con y sin código (las tarjetas descargadas son plantilla); (2) el precio del
  Funded Reset de Select 50K; (3) la lista de jurisdicciones no elegibles para Elite Live que cita
  [T3] §17; (4) si Rise opera en República Dominicana o si toca Plane; (5) el precio de lista de Miami
  V2 50K con DLL ($418 o $376); (6) las plataformas de Miami; (7) si las NinjaScript Automated
  Strategies o las ATM de NinjaTrader tienen alguna restricción propia (lo más prudente es preguntar
  por escrito a soporte, porque la regla de bots exige poder demostrar la propiedad); (8) el
  artículo canónico en `help.tradeify.co` (403).

### Otras páginas incompletas
- Las imágenes (ejemplos de consistencia y capturas) no se leyeron.
- Tradeify 247/Perps, Level Up y Select 300K se leyeron solo de pasada, porque quedan fuera de alcance.
