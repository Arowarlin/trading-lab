# Lucid Trading · ficha de reglas de fondeo (investigación 2026-11)

- **ID**: `lucid` · **Fecha de consulta**: 2026-11-27 · **Cuenta de referencia**: 50K.
- **Programas analizados, cada uno por separado**: LucidPro, LucidFlex y LucidDirect, más la
  transición a **LucidLive**. LucidDaily, LucidMaxx y LucidBlack (legacy) aparecen en el help center,
  pero quedan fuera de alcance y **no** se usan para deducir reglas de los otros programas.
- **Fuentes leídas**: el help center oficial `support.lucidtrading.com`, que es el mismo que sirve
  `intercom.help/lucid-trading/en/` (sus enlaces apuntan a `support.lucidtrading.com`).
- **Bloqueo**: la web principal `lucidtrading.com` (y `www.`) respondió **403** (desafío de Cloudflare
  «Just a moment...») en todas las rutas probadas. Por eso **no hay precios** (Sin datos) y no se han
  leído los Términos y Condiciones ni los «Account Agreement» que citan los artículos de payouts.
- **Formato de cada dato**: valor · «cita literal» · [S#] (URL exacta y fecha en §G) · confianza ·
  estado. Todas las fuentes se consultaron el 2026-11-27.
- **Cálculo propio**: lo que no es cita sino aritmética sobre cifras oficiales se marca así.

## Resumen comparativo (50K)

| Campo | LucidPro | LucidFlex | LucidDirect |
|---|---|---|---|
| Evaluación | Sí, objetivo $3,000 | Sí, objetivo $3,000 | No: directa a financiada |
| Precio (lista / promoción) | Sin datos (web 403) | Sin datos (web 403) | Sin datos (web 403) |
| Pago | Único, sin rebilling | Único, sin rebilling | Único |
| Max Loss Limit (MLL) | $2,000, trailing EOD | $2,000, trailing EOD | $2,000, trailing EOD |
| Bloqueo del MLL | $50,100 al superar $52,100 | $50,100 al superar $52,100 **o al pedir un payout** | $50,100 al superar $52,100 |
| DLL | Opcional: $1,200 fija → 60 % del pico EOD | Opcional: importe Sin datos | Obligatoria en 50K: $1,200 → 60 % |
| Consistencia en evaluación | No figura («pasar en 1 día») | 40 % (50 % con add-on) | No aplica |
| Consistencia en financiada | 40 % por ciclo | Ninguna | 20 % por ciclo |
| Buffer | $52,100 (MLL inicial + $100) | Ninguno | No lo dice la fuente |
| Requisito del payout | ≥ $500 de beneficio en el ciclo | 5 días ≥ $150 y neto > 0 | Objetivo de $3,000 (1.º) y $2,500 (2.º+) |
| Payout máximo | $2,000 (1.º) · $2,500 (2.º+) | 50 % del beneficio hasta $2,000 | $2,000 (1.º–3.º) · $2,500 (4.º–5.º) |
| Payouts antes de Live | 5 | 5 | 5 |
| Tamaño máximo | 4 NQ / 40 MNQ desde el día 1 | Evaluación 4/40; financiada con plan de escalado 2/20 → 4/40 | 4 NQ / 40 MNQ desde el día 1 |
| Reparto | 90/10 | 90/10 | 90/10 |
| Automatización | Permitida (regla general) | Permitida (regla general) | Permitida (regla general) |

---

## Reglas comunes (solo las que la fuente aplica de forma explícita a todas las cuentas o nombra los tres programas)

- **Horario y cierre obligatorio (Pro, Flex y Direct)**: cierre a las 16:45 ET, de lunes a viernes; la
  firma cierra la posición, pero no es rotura. «All positions must be closed by 4:45 PM EST, Monday
  through Friday» · «Holding a position past this time does not result in a failed account» [S11] ·
  alta · verificado. Reapertura a las 18:00 ET, de domingo a jueves; en festivos con cierre anticipado
  hay que cerrar antes del cierre del mercado [S11] · alta · verificado.
- **Overnight y fin de semana**: no se puede mantener una posición después de las 16:45 ET, así que no
  hay posiciones entre sesiones ni en fin de semana (deducido de [S11]) · alta · verificado.
- **Noticias (Pro, Flex y Direct)**: permitido. «Allowed on Flex, Pro and Direct» [S10] · alta ·
  verificado (en LucidDaily es una rotura, pero ese programa queda fuera de alcance).
- **Comisiones por lado (todas las cuentas)**: NQ **$1.75**, MNQ **$0.50**. «Commission (Per Side)»
  [S4] · alta · verificado. Ida y vuelta: NQ $3.50, MNQ $1.00 (cálculo propio).
- **Límites de cuentas (por hogar o familia)**: hasta 10 de evaluación; 10 en total entre evaluación y
  financiadas; hasta 5 financiadas sumando todos los tipos; hasta 5 LucidLive. «Up to 5 active funded
  accounts per household or family.» · «Different types of funded accounts combined may not exceed 5
  accounts total.» [S3] · alta · verificado.
- **Inactividad**: si una cuenta no registra al menos ±$1 de P&L neto en 30 días naturales, se borra.
  Una cuenta rota se borra a los 30 días si no se resetea. «Accounts that have not been traded
  resulting in at least a net profit or loss of 1$ within 30 calendar days will be deemed abandoned»
  [S9] · alta · verificado.
- **Integridad**: prohibido aprovechar errores del sistema, retrasos o discrepancias de los precios
  simulados. «Exploiting discrepancies in simulated prices» [S12] · alta · verificado.

---

## Programa 1 · LucidPro

### A. Costes (50K)
- **Precio de evaluación (lista / promoción)**: **Sin datos**. El help center no publica precios y la
  web principal da 403. La única referencia es relativa: con DLL On «Results in a lower evaluation
  purchase price»; con DLL Off el precio es más alto [S22] · alta (relativo) · no verificado (importe).
- **Modelo de pago**: pago único, sin suscripción. «LucidPro Evaluation and LucidDirect accounts are
  purchased by paying a one-time fee.» · «There is no subscription and no automatic rebilling.» [S5] ·
  alta · verificado.
- **Activación**: $0. «There is no activation fee to upgrade a LucidPro Evaluation to a LucidPro
  Funded.» [S5] · alta · verificado.
- **Reset**: es de pago y se compra desde el dashboard; importe Sin datos. «Resets are not automatic
  or free.» [S5] · alta · parcial.
- **Datos de mercado**: no lo dice la fuente oficial. Pista: un anuncio del help center dice «No
  monthly fees.» [S2] · baja · no verificado.
- **Comisiones**: NQ $1.75 y MNQ $0.50 por lado (ver reglas comunes) [S4] · alta · verificado.
- **Otros cargos (API, plataforma, retiro)**: no lo dice la fuente oficial.
- **Coste hasta tener la cuenta financiada (mejor caso, 1 intento)**: precio de la evaluación (Sin
  datos) + $0 de activación + comisiones.
- **Coste de mantenerla 3 y 6 meses**: la fuente no indica cargos recurrentes («no monthly rebilling»
  [S16]). Coste fijo declarado: $0, más comisiones · media · parcial (no hay datos sobre la cuota de
  datos).

### B. Reglas de trading (50K)
- **Profit target**: $3,000. Tabla «$50,000 | $3,000 | $2,000 | $1,200 | 4 mini or 40 micros» [S16]
  · alta · verificado.
- **Drawdown máximo (MLL)**: $2,000, en evaluación y en financiada [S16][S17][S21] · alta ·
  verificado.
- **Tipo**: trailing por fin de día (EOD), calculado sobre el saldo de cierre máximo. «At the end of
  each trading session, the system calculates the account’s highest closing balance» [S21] · alta ·
  verificado. La fuente no aclara si la rotura se evalúa intradía con el P&L no realizado: solo dice
  «If your account balance reached the MLL, your account will be breached.» [S21] · media · parcial.
- **Bloqueo**: al superar el Initial Trail Balance ($52,100), el MLL queda fijo en $50,100. «Once the
  account exceeds the trail, the MLL locks at the initial balance plus $100» [S21] · alta ·
  verificado.
- **DLL**: opcional, se elige al comprar y no se puede cambiar después [S22].
  - En la evaluación, $1,200 fija [S20].
  - En la financiada, $1,200 fija hasta cerrar por encima de $52,100; después pasa a LucidScale =
    60 % del mayor beneficio EOD, y nunca baja. «Highest end-of-day account profit × 60% = LucidScale
    DLL» · «It does not decrease, even if the account draws down» [S20].
  - Efecto: es una **pausa**, no una rotura. «All DLLs at Lucid Trading are considered soft breaches»
    [S20].
  - Alta · verificado. Discrepancia menor: [S17] dice «60% of Peak EOD Balance» y [S20] habla de
    beneficio; manda la fórmula de [S20].
- **Consistencia en la evaluación**: ningún artículo de LucidPro la impone en esa fase; la evaluación
  dice «Pass the evaluation in one trading day» [S16] · media · parcial (deducido).
- **Consistencia en la financiada**: 40 % por ciclo de payout, y se reinicia tras cada payout. Las
  cuentas compradas o reseteadas antes del 28-11-2025 tienen el 35 %. «Largest Single Day Profit /
  Account Profit = Consistency Percentage» [S19] · alta · verificado. Es un requisito para cobrar, no
  causa rotura.
- **Contratos máximos**: 4 NQ o 40 MNQ (1 mini = 10 micros). Sin plan de escalado en la financiada:
  «No scaling plan, access to max contract size immediately» [S17] · alta · verificado.
- **Horario, noticias, overnight y fin de semana**: ver reglas comunes [S10][S11].
- **Escalado**: no hay plan de escalado [S17].

### C. Payouts (50K)
- **Días necesarios**: la fuente no pide un mínimo de días. Con la consistencia del 40 % hacen falta,
  matemáticamente, ≥ 3 días con beneficio en el ciclo (cálculo propio) · media · parcial.
- **Beneficio mínimo por ciclo**: $500 («Minimum Profit Goal») [S18] · alta · verificado.
- **Número máximo de retiros**: 5; después, revisión para pasar a Live. «Payout 5 represents the
  maximum payout level» · «This maximum payout level applies to Flex, Pro, and Direct plans.» [S38] ·
  alta · verificado.
- **Mínimo por retiro**: $500. «Minimum payout request: $500» [S18] · alta · verificado.
- **Máximo por retiro**: $2,000 el 1.º (exige un saldo de $54,100) y $2,500 del 2.º en adelante (exige
  $54,600) [S18] · alta · verificado.
- **Reparto**: 90/10. Las cuentas compradas o reseteadas antes del 28-11-2025 cobran el 100 % de los
  primeros $10k. «All funded account payouts are split 90% to the trader and 10% to Lucid Trading.»
  [S18] · alta · verificado.
- **Buffer**: MLL inicial + $100 = saldo de $52,100; no se puede cobrar del buffer y el 1.er payout de
  $500 exige $52,600. «The buffer is equal to: Initial Max Loss Limit + $100» [S18] · alta ·
  verificado.
- **Topes acumulados**: «No simulated payout caps» [S17]. Tope práctico con 5 payouts: $2,000 +
  4 × $2,500 = $12,000 brutos (cálculo propio; la fuente no aclara si el 90/10 se aplica sobre el
  importe solicitado).
- **Ventana de cobro**: cualquier día en que se cumplan los criterios. «There is no fixed payout
  window» [S18].
  - Con DLL On hay payouts *On Demand* dentro de la sesión (18:00–15:45 ET), y la cuenta queda en pausa
    hasta el final del día: «After requesting an intraday payout, trading on your funded LucidPro
    account is paused until the end of the trading day.» [S22].
  - Con DLL Off se cobra con el calendario EOD normal [S22].
  - Alta · verificado.
- **Estados del payout**:
  - *Solicitado*: es definitivo. «Payout requests are final once submitted, they cannot be edited or
    canceled.» [S18].
  - *Aprobado*: el plazo no lo dice la fuente. El artículo de métodos de pago resume «payouts
    averaging about 15 minutes once approved» [S7].
  - *Procesado*: se descuenta de la cuenta en unos minutos y se envía «within 2 business days» [S18].
  - *Recibido*: según el método (ver §F).
  - Alta · parcial.
- **Métodos de pago y KYC**: ver §F. La fuente no menciona KYC para LucidPro.
- **Transición a Live**: ver «Transición a LucidLive».

### D. Automatización (aspectos propios de LucidPro)
- **Bots y estrategias automáticas**: permitidos por la regla general [S10] (ver §D común), sin
  excepciones para LucidPro · alta · verificado.
- **Fricciones para un bot**:
  1. La DLL (si está On) bloquea el resto de la sesión.
  2. Pedir un payout *On Demand* pausa la cuenta hasta el final del día [S22].
  3. La consistencia del 40 % retrasa el cobro si hay un día muy grande, pero no rompe la cuenta
     [S19].
  4. Un trade entre la solicitud y la aprobación que meta el saldo en el buffer puede hacer que se
     deniegue el payout [S18].

---

## Programa 2 · LucidFlex

### A. Costes (50K)
- **Precio de evaluación (lista / promoción)**: **Sin datos** (web 403; el help center no publica
  precios). Relativo: DLL On + 40 % es la «Cheapest version of LucidFlex» y DLL Off + 50 % es la
  «Highest pricing version of LucidFlex» [S30] · alta (relativo) · no verificado (importe).
- **Add-on de consistencia del 50 %**: «Added at checkout for a small fee.» [S30]; importe Sin datos ·
  alta · parcial.
- **Modelo de pago**: «One-time fee, no monthly rebilling, take as long as you need to pass» [S24] ·
  alta · verificado.
- **Activación**: «No activation fees to upgrade to funded account» [S24] · alta · verificado.
- **Reset**: de pago, según la política general de resets [S5]; importe Sin datos · media · parcial
  ([S5] nombra LucidPro y LucidDirect, no Flex).
- **Datos de mercado, API, plataforma, retiro**: no lo dice la fuente oficial.
- **Comisiones**: NQ $1.75 y MNQ $0.50 por lado [S4] · alta · verificado.
- **Coste hasta tener la cuenta financiada (mejor caso)**: precio (Sin datos) + add-on opcional + $0
  de activación.
- **Coste de mantenerla 3 y 6 meses**: sin cargo recurrente declarado; $0 más comisiones · media ·
  parcial.

### B. Reglas de trading (50K)
- **Profit target**: $3,000; MLL $2,000. «$50,000 | $3,000 | $2,000 | 40% (50% with add-on) | 4 mini
  or 40 micros» [S24] · alta · verificado.
- **Tipo de drawdown**: trailing EOD sobre el saldo de cierre máximo; se bloquea en $50,100 al superar
  $52,100 [S29] · alta · verificado.
- **Bloqueo adicional**: el MLL se bloquea en $50,100 al pedir un payout, aunque no se haya llegado a
  $52,100. «Once you request a payout from LucidFlex, your MLL automatically adjusts to the Locked MLL
  Balance» [S29] · alta · verificado.
- **P&L no realizado**: la fuente no lo aclara (mismo texto que en Pro) [S29] · media · parcial.
- **DLL**: opcional en evaluación y financiada; se elige al comprar y no se puede cambiar [S30]. Es una
  pausa, no una rotura: «The DLL is a soft breach» [S30]. **Importe: Sin datos**; ningún artículo de
  LucidFlex lo publica [S24][S25][S30] · alta (existe) · no verificado (importe).
- **Consistencia en la evaluación**: 40 %, o 50 % con el add-on; se puede pasar en un mínimo de 3 días,
  o de 2 con el add-on. «Pass in as few as 3 days with 40% consistency, or 2 days with the 50%
  consistency add-on» [S24] · alta · verificado. Con el 50 % hay un pequeño margen («cushion») sobre la
  tabla [S27].
- **Consistencia en la financiada**: **ninguna**. «Consistency applies to the evaluation only. Funded
  LucidFlex accounts have no consistency rule.» [S30] · alta · verificado.
- **Contratos máximos**: 4 NQ o 40 MNQ en la evaluación, sin escalado [S24][S28]. En la financiada hay
  un plan de escalado que se actualiza al final de cada sesión. Para 50K:

  | Beneficio simulado | Límite |
  |---|---|
  | $0–$999 | 2 NQ o 20 MNQ |
  | $1,000–$1,999 | 3 NQ o 30 MNQ |
  | $2,000+ | 4 NQ o 40 MNQ |

  Fuente [S28] · alta · verificado. Un payout puede bajar el escalón. Si se supera el límite de forma
  intencionada, se puede perder el beneficio del día: «may result in having profit wiped for the day»
  [S28] · alta · verificado.
- **Horario, noticias, overnight y fin de semana**: ver reglas comunes [S10][S11].

### C. Payouts (50K)
- **Días necesarios**: 5 días con al menos $150 de beneficio cada uno en el ciclo, y el contador se
  reinicia tras cada payout. «Traders must earn at least the minimum required profit on 5 separate
  days during the payout cycle.» [S26] · alta · verificado.
- **Otro requisito**: beneficio neto positivo en el ciclo (basta $1) [S26] · alta · verificado.
- **Número máximo de retiros**: 5, y después pasa a Live. «Traders may take up to 5 payouts from each
  LucidFlex account after which they will be moved live.» [S26]; coincide con [S38] · alta ·
  verificado.
- **Mínimo por retiro**: $500 [S26] · alta · verificado.
- **Máximo por retiro**: 50 % del beneficio, con un tope de $2,000, y no sube con más payouts. «the
  maximums here do not scale up with more payouts» [S26] · alta · verificado.
  - Discrepancia: el texto dice «50% of their account balance» y la tabla dice «50% of Profit». Se toma
    la tabla; confianza media en la base del 50 %.
- **Reparto**: 90/10 [S26] · alta · verificado.
- **Buffer**: ninguno. «There is no buffer balance that must be maintained in LucidFlex funded
  accounts.» [S26] · alta · verificado. A cambio, el MLL se bloquea en $50,100 al pedir el payout
  [S29].
- **Topes acumulados**: 5 × $2,000 = $10,000 brutos por cuenta (cálculo propio).
- **Ventana y tiempos**: no hay ventana fija; se descuenta en unos minutos y se envía en un plazo de
  2 días hábiles [S26]. *On Demand* intradía solo con DLL On, con pausa hasta el final del día [S30] ·
  alta · verificado. Estados: igual que en Pro (solicitud definitiva; plazo de aprobación no indicado)
  [S26][S7].
- **KYC**: la fuente no lo menciona para LucidFlex.

### D. Automatización (aspectos propios de LucidFlex)
- **Bots y estrategias automáticas**: permitidos por la regla general [S10], sin excepción para Flex ·
  alta · verificado.
- **Fricciones para un bot**:
  1. El bot debe leer el escalón del plan de escalado, que cambia por EOD, y limitar el tamaño en
     consecuencia [S28].
  2. Con DLL On, el importe de la DLL es desconocido, así que no se puede calibrar el riesgo diario
     contra ella.
  3. Pedir un payout *On Demand* pausa la cuenta [S30].

---

## Programa 3 · LucidDirect (directa a financiada)

### A. Costes (50K)
- **Precio (lista / promoción)**: **Sin datos** (web 403; el help center no publica precios).
- **Modelo de pago**: pago único [S5] · alta · verificado. No hay evaluación: «The LucidDirect is a
  simulated straight-to-funded account which does not have an evaluation phase.» [S32] · alta ·
  verificado.
- **Activación**: no aplica (no hay evaluación). La fuente no menciona ningún cargo de activación.
- **Reset**: de pago [S5]; importe Sin datos · media · parcial.
- **Add-ons**: no tiene. «LucidDirect has no add-ons; the Daily Loss Limit is set by account size.»
  [S35] · alta · verificado.
- **Comisiones**: NQ $1.75 y MNQ $0.50 por lado [S4].
- **Datos de mercado y otros cargos**: no lo dice la fuente oficial.
- **Coste hasta tener la cuenta financiada (mejor caso)**: el precio de compra (Sin datos).
- **Coste de mantenerla 3 y 6 meses**: sin cargo recurrente declarado; $0 más comisiones · media ·
  parcial.

### B. Reglas de trading (50K)
- **Profit target**: no hay (no tiene evaluación).
- **MLL**: $2,000, trailing EOD; se bloquea en $50,100 al superar $52,100. Tabla «$50,000 | $2,000 |
  $52,100 | $50,100» [S36] · alta · verificado. El P&L no realizado no se aclara [S36] · media ·
  parcial.
- **DLL**: obligatoria en 50K. Empieza fija en $1,200 y, tras superar $52,100, pasa a LucidScale
  (60 % del mayor beneficio EOD). Es una pausa, no una rotura [S35][S32] · alta · verificado.
  - Discrepancia en 25K, fuera de la referencia: [S35] da «None» como Initial Trail Balance y [S36] da
    $26,100.
- **Consistencia en la financiada**: **20 %** por ciclo. «Your largest single-day profit must be no
  more than 20% of your total profit during the payout cycle.» [S33][S34] · alta · verificado.
- **Contratos máximos**: 4 NQ o 40 MNQ desde el día 1, sin plan de escalado. «No scaling plan, access
  to max contract size immediately» [S32] · alta · verificado.
- **Horario, noticias, overnight y fin de semana**: ver reglas comunes [S10][S11].

### C. Payouts (50K)
- **Objetivo de beneficio por ciclo**: $3,000 en el 1.º y $2,500 del 2.º en adelante; se reinicia
  tras cada payout [S33] · alta · verificado.
- **Días necesarios**: la fuente no pide un mínimo explícito. Con el 20 % de consistencia hacen falta
  ≥ 5 días con beneficio por ciclo (cálculo propio).
- **Número máximo de retiros**: 5 (la tabla llega a «Payouts 4-5») [S33][S38] · alta · verificado.
- **Mínimo por retiro**: $500 [S33] · alta · verificado.
- **Máximo por retiro**: $2,000 del 1.º al 3.º y $2,500 en el 4.º y el 5.º [S33] · alta · verificado.
- **Reparto**: 90/10 [S33] · alta · verificado.
- **Buffer**: el artículo de payouts de Direct no menciona ninguno (no lo dice la fuente oficial). Sí
  avisa de que un trade antes del procesamiento que baje del objetivo puede hacer que se deniegue la
  solicitud [S33].
- **Topes acumulados**: «No simulated payout caps» [S32]. Tope práctico: 3 × $2,000 + 2 × $2,500 =
  $11,000 brutos (cálculo propio).
- **Ventana y tiempos**: no hay ventana fija; se envía en un plazo de 2 días hábiles [S33]. *On
  Demand* intradía en 50K, porque tiene DLL: «$50,000, $100,000 and $150,000 LucidDirect accounts have
  a Daily Loss Limit, so they can request payouts during the trading session» [S35] · alta ·
  verificado.
- **KYC**: la fuente no lo menciona para LucidDirect.

### D. Automatización (aspectos propios de LucidDirect)
- **Bots y estrategias automáticas**: permitidos por la regla general [S10], sin excepción para Direct
  · alta · verificado.
- **Fricciones para un bot**: la consistencia del 20 % es la más dura de los tres programas: un solo
  día grande bloquea el cobro hasta que se diluya. A eso se suman la DLL obligatoria en 50K y un
  objetivo de $3,000 en el primer ciclo.

---

## Transición a LucidLive (estructura nueva; cuentas compradas o reseteadas después del 27-02-2026)

- **Cómo se entra**: es discrecional. Se entra en el pool de revisión, entre otros casos, tras el
  payout 5 de Flex, Pro o Direct. «All live transitions occur at the discretion of the Lucid risk
  team.» [S38] · alta · verificado.
- **Requisito por cuenta**: cada cuenta financiada necesita al menos un payout, y da una cuenta Live.
  «Each funded account must have received at least one payout to qualify» [S38] · alta · verificado.
- **Arranque de la cuenta Live**: saldo de $0, payouts diarios, drawdown EOD y sin DLL. «$0 starting
  balance … Daily payouts … End of Day (EOD) drawdown … No daily loss limit» [S38] · alta · verificado.
- **Drawdown en Live (50K)**: $2,000. Se bloquea en $100 cuando el beneficio Live iguala ese drawdown,
  o al primer payout Live si es antes. «the Max Loss Limit locks at $100 and no longer moves» [S38] ·
  alta · verificado.
- **Escalado en Live (50K, productos CME como NQ/MNQ)** [S39] · alta · verificado:

  | Beneficio | Límite |
  |---|---|
  | $0–$1,999.99 | 2 NQ o 20 MNQ |
  | $2,000–$3,999 | 3 NQ o 30 MNQ |
  | $4,000+ | 4 NQ o 40 MNQ |

- **Consistencia en Live**: ninguna, en ningún programa [S38][S19][S34] · alta · verificado.
- **Horario en Live**: no se permite swing. En Tradovate Live se puede mantener la posición hasta las
  16:45 ET y en Rithmic Live hasta las 16:15 ET; la autoliquidación se configura en el onboarding.
  «Swing trading is not allowed in the new LucidLive accounts» [S11] · alta · verificado.
- **Reparto en Live**: no lo dice la fuente oficial para los payouts diarios. El bonus y el cashout sí
  son 90/10 [S38].
- **Bonus repetible (50K)**: $2,000 al llegar a $4,000 de beneficio Live y completar 20 días de
  trading (90/10). La fuente advierte contra el «contract flipping» [S38] · alta · verificado.
- **Cashout en lugar de ir a Live**: «equal to 50% of a traders live starting balance and is subject
  to a 90/10 profit split»; hay 24 h para elegirlo [S38]. Ambigüedad: el saldo inicial en Live es $0,
  así que la base del 50 % no está clara · media · parcial.
- **Efectos colaterales**:
  1. Se cierran todas las cuentas simuladas, también las evaluaciones en reserva.
  2. Si otro miembro del hogar está en Live, los demás no pueden operar en simulado.
  3. Hay un cooldown de 2 semanas tras quemar una cuenta Live.
  4. Si una cuenta financiada no es elegible y conserva ≥ 50 % del drawdown, se reembolsa su
     evaluación.
  - Fuente [S38] · alta · verificado. Máximo de 5 cuentas Live por hogar [S3].
- **Automatización en Live**: **la fuente no la autoriza expresamente**. [S10] describe los
  evaluation y funded accounts. La FAQ de Live solo menciona copiadores al prohibir el hedging: «This
  includes any copytrader issues that may arise.» [S38] · media · **no verificado**.
- **Plataformas en Live**: Tradovate Live o Rithmic Live [S11]. Si NinjaTrader se puede usar en Live,
  no lo dice la fuente oficial · media · parcial.
- **KYC en Live (Pro, Flex, Direct)**: no lo dice la fuente oficial. Pista que no se generaliza: el
  artículo de LucidDaily Live menciona «KYC with the broker partner» [S41] · baja · no verificado.
- **Legacy (cuentas compradas o reseteadas hasta el 27-02-2026)**: estructura con escrow y topes de
  traspaso por programa [S23][S31][S37]. No aplica a compras nuevas.

---

## D. Automatización · reglas comunes (crítico)

- **Bots y estrategias automáticas**: permitidos. «Automated trading systems and trade copiers are
  permitted» · «All automated activity must comply with Lucid Trading rules» [S10] · alta · verificado.
  - Alcance: el artículo describe las cuentas de evaluación y financiadas, sin excepciones por programa
    en esta sección.
  - Nota de URL: la URL conocida `.../11404728-permitted-activities` redirige al mismo artículo, que
    ahora se llama «Other Trading Activities».
- **Responsabilidad**: los errores de software corren por cuenta del trader. «Traders are fully
  responsible for any software errors, malfunctions, or unintended outcomes» [S10] · alta · verificado.
- **NinjaTrader 8 Automated Strategies / NinjaScript / ATM**: no lo dice la fuente oficial. La fuente
  dice que NinjaTrader está soportado (por CQG) [S2] y que los sistemas automáticos están permitidos
  [S10], pero no nombra la versión 8, NinjaScript ni ATM · media · parcial.
- **Copiadores de operaciones**: permitidos [S10]. Está prohibido el hedging entre cuentas, incluido
  mini contra micro del mismo subyacente y entre activos correlacionados (por ejemplo, ES largo en una
  cuenta y NQ corto en otra). «you cannot go long / short the same contract but one is minis or micros
  in separate accounts» [S13] · alta · verificado. El hedging se detecta de forma automática; la
  primera vez se resetea la cuenta al saldo del día anterior y se pierde el acceso a *On Demand*; la
  reincidencia rompe la cuenta [S13].
- **Varias cuentas**: hasta 5 financiadas por hogar [S3] · alta · verificado.
- **VPS**: no lo dice la fuente oficial (la búsqueda «vps» en el help center no da resultados).
- **APIs**: no lo dice la fuente oficial (la búsqueda «api» no da resultados).
- **HFT**: prohibido. La definición es cualitativa, sin umbral numérico: «submitting and executing a
  high volume of trades within extremely short time frames, often measured in seconds or even
  milliseconds» [S14].
  - Sanción: aviso la primera vez; si se repite, «All profits generated from HFT activity will be
    removed», cierre de cuentas y veto [S14].
  - Alta · verificado.
- **Microscalping**: prohibido. El umbral es objetivo: «More than 50% of your profits are generated
  from trades held for 5 seconds or less» [S15].
  - Sanción: revisión manual, aviso y, si se repite, se pierden los beneficios [S15].
  - Alta · verificado. El «genuine scalping» sí está permitido [S10].
- **Otras técnicas prohibidas**:
  - Aprovechar errores o discrepancias del simulador [S12].
  - Martingala: «strongly discouraged», es decir, desaconsejada, no prohibida [S10].
  - El DCA y el «flipping» para sumar días están permitidos [S10].
- **¿Pueden anular beneficios?**: sí, por HFT o microscalping reincidentes [S14][S15], por superar el
  escalado de Flex [S28] y por hedging (reset de saldo) [S13] · alta · verificado.
- **Diferencias entre evaluación, financiada simulada y Live**:
  - Evaluación y financiada: la automatización está permitida de forma explícita [S10].
  - Live: no consta una autorización expresa (ver la transición a LucidLive) · media · parcial.

## E. Plataformas

- **Todas las cuentas**: «All listed platforms work with all Lucid account types.» [S2] · alta ·
  verificado.
- **Por CQG**: NinjaTrader, Tradovate y TradingView [S2] · alta · verificado.
- **Por Rithmic**: Quantower, Tradesea, MotiveWave, Sierra Chart, Jigsaw, Bookmap, ATAS, R|Trader Pro y
  MultiCharts [S2] · alta · verificado.
- **NinjaTrader 8**: aparece «NinjaTrader», listado solo bajo CQG; la fuente no indica la versión 8 de
  forma explícita · media · parcial.
- **APIs, conexiones simultáneas, ATM, NinjaScript**: no lo dice la fuente oficial.
- **Live**: solo Tradovate Live y Rithmic Live [S11].

## F. Elegibilidad internacional

- **República Dominicana**: **no figura** en la lista de países restringidos (actualizada el
  2026-10-08). «If you are a citizen or resident of any of the countries listed below, you are not
  eligible to use Lucid Trading services» [S8] · alta (lista) · **parcial**.
  - Motivos de que no sea «verificado»: no hay confirmación positiva y no se pudieron leer los Términos
    y Condiciones (403).
  - Sí están restringidos países cercanos: Bahamas, Barbados, Belice, Cuba, Ecuador, Haití, Jamaica,
    Nicaragua, Panamá, Trinidad y Tobago y Venezuela [S8].
- **KYC**: para Pro, Flex y Direct no lo dice la fuente oficial. La búsqueda «kyc» solo encuentra el
  artículo de LucidDaily Live [S41].
- **Métodos para comprar**: tarjetas (Visa, Mastercard, American Express, Discover, Diners Club,
  Maestro) [S6] · alta · verificado. No se citan otros métodos.
- **Métodos para cobrar desde RD** [S7]:
  - WorkMarket by ADP: «Available for both U.S. and international traders», por transferencia o PayPal,
    con recepción «as early as the next business day».
  - Cripto: «Available for International Traders» (BTC, ETH, LTC, USDT, USDC).
  - Plaid es solo para EE. UU. y Echlon solo para Reino Unido, Alemania y España.
  - Alta · verificado como métodos internacionales; que WorkMarket opere con RD en concreto no lo dice
    la fuente · parcial.
- **Impuestos y formularios (W-8BEN u otros)**: no lo dice la fuente oficial (las búsquedas «tax» y
  «w-8ben» no dan resultados).

---

## Conclusión: qué programa encaja con una estrategia automatizada NQ/MNQ en NinjaTrader 8

**Recomendación: LucidFlex 50K**, con LucidPro como alternativa. Se basa solo en las reglas: sin
precios (Sin datos) no se puede calcular el EV, que queda pendiente.

1. **La automatización es igual en los tres programas**: está permitida [S10], con las mismas
   prohibiciones (HFT [S14], microscalping de ≤ 5 s con más del 50 % del beneficio [S15], hedging
   entre cuentas [S13]) y el mismo cierre forzoso a las 16:45 ET [S11]. NinjaTrader por CQG funciona
   en todas las cuentas [S2]. Lo que decide es la estructura de cobro.
2. **LucidFlex es la que menos penaliza la varianza diaria de un bot**:
   - La financiada no tiene consistencia ni buffer [S25][S26][S30].
   - El cobro se reduce a una regla mecánica: 5 días ≥ $150 y neto > 0 [S26].
   - La consistencia del 40 % (o 50 %) solo cuenta para aprobar la evaluación [S27][S30].
3. **Costes de LucidFlex que hay que asumir**:
   - El escalado de la financiada (2 NQ / 20 MNQ hasta $1,000 de beneficio [S28]), que obliga al bot a
     limitar el tamaño por escalón EOD.
   - El payout máximo, que no sube: 50 % del beneficio hasta $2,000 [S26].
   - El MLL, que se bloquea en $50,100 al primer payout [S29].
   - El importe desconocido de su DLL opcional. Con DLL Off desaparece esa incógnita, a un precio más
     alto [S30].
4. **LucidPro es preferible si el P&L diario del bot es suave**: la evaluación se puede pasar en un día
   sin consistencia [S16], el tamaño máximo está disponible desde el día 1 [S17] y los payouts 2.º+
   llegan a $2,500 [S18]. En cambio, exige un 40 % de consistencia por ciclo [S19] y un buffer de
   $52,100 [S18].
5. **LucidDirect es la peor opción para un bot**: tiene un 20 % de consistencia por ciclo [S33], un
   objetivo de $3,000 en el primer ciclo [S33] y una DLL obligatoria en 50K [S35].
6. **Riesgos abiertos que pueden cambiar la elección**:
   - Live no autoriza la automatización de forma explícita y usa Tradovate o Rithmic Live; el soporte
     de NinjaTrader en Live no se ha verificado [S11][S38].
   - No se han leído los Términos y Condiciones (403).
   - La elegibilidad desde RD no se ha confirmado de forma positiva.

---

## G. Fuentes

Todas consultadas el 2026-11-27. «Act.» es la fecha `lastUpdatedDate` del artículo.

| ID | URL | Datos | Act. | Confianza | Estado |
|---|---|---|---|---|---|
| S1 | https://support.lucidtrading.com/en/ · https://intercom.help/lucid-trading/en/ | Índice de colecciones | — | alta | verificado |
| S2 | https://support.lucidtrading.com/en/articles/11404614-lucid-trading-supported-platforms | Plataformas, «No monthly fees» | 2026-10-12 | alta | verificado |
| S3 | https://support.lucidtrading.com/en/articles/11404617-maximum-number-of-accounts | Límites de cuentas | 2026-08-26 | alta | verificado |
| S4 | https://support.lucidtrading.com/en/articles/11508978-approved-products-and-commissions | Comisiones NQ/MNQ | 2026-08-26 | alta | verificado |
| S5 | https://support.lucidtrading.com/en/articles/11404620-simulated-account-fees | Pago único, activación, reset | 2026-08-26 | alta | verificado |
| S6 | https://support.lucidtrading.com/en/articles/11404628-accepted-payments-methods | Métodos de compra | 2026-08-26 | alta | verificado |
| S7 | https://support.lucidtrading.com/en/articles/12890325-payout-methods | Métodos de cobro | 2026-11-16 | alta | verificado |
| S8 | https://support.lucidtrading.com/en/articles/11404636-restricted-countries | Países restringidos | 2026-10-08 | alta | verificado |
| S9 | https://support.lucidtrading.com/en/articles/11404632-inactivity-policy | Inactividad | 2026-08-26 | alta | verificado |
| S10 | https://support.lucidtrading.com/en/articles/11404728-other-trading-activities (viene de https://intercom.help/lucid-trading/en/articles/11404728-permitted-activities) | Automatización, copiadores, noticias, scalping | 2026-11-16 | alta | verificado |
| S11 | https://support.lucidtrading.com/en/articles/11404729-allowed-trading-times | Horario, cierre, Live | 2026-08-26 | alta | verificado |
| S12 | https://support.lucidtrading.com/en/articles/11404732-trade-with-integrity | Prácticas prohibidas | 2026-08-26 | alta | verificado |
| S13 | https://support.lucidtrading.com/en/articles/11404734-prohibited-hedging | Hedging | 2026-11-16 | alta | verificado |
| S14 | https://intercom.help/lucid-trading/en/articles/11404736-prohibited-high-frequency-trading | HFT | 2026-08-26 | alta | verificado |
| S15 | https://support.lucidtrading.com/en/articles/11404742-prohibited-microscalping | Microscalping | 2026-08-26 | alta | verificado |
| S16 | https://support.lucidtrading.com/en/articles/12890029-lucidpro-evaluation-account | Pro: evaluación | 2026-08-26 | alta | verificado |
| S17 | https://support.lucidtrading.com/en/articles/12890069-lucidpro-funded-account | Pro: financiada | 2026-08-26 | alta | verificado |
| S18 | https://support.lucidtrading.com/en/articles/12890092-lucidpro-payouts | Pro: payouts y buffer | 2026-10-21 | alta | verificado |
| S19 | https://support.lucidtrading.com/en/articles/12890109-lucidpro-consistency-percentage | Pro: consistencia | 2026-08-26 | alta | verificado |
| S20 | https://support.lucidtrading.com/en/articles/12890122-lucidpro-daily-loss-limit | Pro: DLL | 2026-07-26 | alta | verificado |
| S21 | https://support.lucidtrading.com/en/articles/12890136-lucidpro-drawdown | Pro: MLL EOD y bloqueo | 2026-08-26 | alta | verificado |
| S22 | https://support.lucidtrading.com/en/articles/16226068-lucidpro-customization | Pro: DLL On/Off, On Demand | 2026-11-17 | alta | verificado |
| S23 | https://support.lucidtrading.com/en/articles/13432107-lucidpro-live-legacy | Pro: Live legacy | 2026-08-26 | alta | verificado |
| S24 | https://support.lucidtrading.com/en/articles/12945790-lucidflex-evaluation-account | Flex: evaluación | 2026-10-19 | alta | verificado |
| S25 | https://support.lucidtrading.com/en/articles/12945795-lucidflex-funded-account | Flex: financiada | 2026-10-13 | alta | verificado |
| S26 | https://support.lucidtrading.com/en/articles/12945796-lucidflex-payouts | Flex: payouts | 2026-07-28 | alta | verificado |
| S27 | https://support.lucidtrading.com/en/articles/12945805-lucidflex-consistency-percentage | Flex: consistencia | 2026-10-19 | alta | verificado |
| S28 | https://support.lucidtrading.com/en/articles/12945808-lucidflex-scaling-plan | Flex: escalado | 2026-05-06 | alta | verificado |
| S29 | https://support.lucidtrading.com/en/articles/12945815-lucidflex-drawdown | Flex: MLL y bloqueo | 2026-08-26 | alta | verificado |
| S30 | https://support.lucidtrading.com/en/articles/16226050-lucidflex-customization | Flex: DLL y consistencia, add-on | 2026-10-20 | alta | verificado |
| S31 | https://support.lucidtrading.com/en/articles/13424914-lucidflex-live-legacy | Flex: Live legacy | 2026-08-26 | alta | verificado |
| S32 | https://support.lucidtrading.com/en/articles/12890148-luciddirect-funded-account | Direct: financiada | 2026-08-26 | alta | verificado |
| S33 | https://support.lucidtrading.com/en/articles/12890164-luciddirect-payout-objectives | Direct: payouts | 2026-08-26 | alta | verificado |
| S34 | https://support.lucidtrading.com/en/articles/12890178-luciddirect-consistency-percentage | Direct: consistencia | 2026-08-26 | alta | verificado |
| S35 | https://support.lucidtrading.com/en/articles/12890185-luciddirect-daily-loss-limit | Direct: DLL, On Demand | 2026-10-19 | alta | verificado |
| S36 | https://support.lucidtrading.com/en/articles/12890192-luciddirect-drawdown | Direct: MLL y bloqueo | 2026-08-26 | alta | verificado |
| S37 | https://support.lucidtrading.com/en/articles/13425070-luciddirect-live-legacy | Direct: Live legacy | 2026-08-26 | alta | verificado |
| S38 | https://support.lucidtrading.com/en/articles/16558826-new-live-structure | LucidLive (estructura nueva) | 2026-10-14 | alta | verificado |
| S39 | https://support.lucidtrading.com/en/articles/15245873-live-scaling-plan | Escalado en Live | 2026-10-04 | alta | verificado |
| S40 | https://support.lucidtrading.com/en/articles/13425130-legacy-live-structure | Live legacy (contexto) | 2026-10-04 | alta | verificado |
| S41 | https://support.lucidtrading.com/en/articles/16010520-luciddaily-live | Solo pista de KYC (otro programa) | 2026-10-16 | baja | no verificado |

### Páginas que no se pudieron leer
| URL | Código | Nota |
|---|---|---|
| https://lucidtrading.com/ | 403 | Desafío de Cloudflare «Just a moment...» |
| https://www.lucidtrading.com/ | 403 | Ídem |
| https://lucidtrading.com/pricing | 403 | Ídem: precios Sin datos |
| https://lucidtrading.com/terms | 403 | Ídem |
| https://lucidtrading.com/terms-and-conditions | 403 | Ídem: T&C no leídos |
| https://lucidtrading.com/privacy-policy | 403 | Ídem |
| https://lucidtrading.com/robots.txt | 403 | Ídem |
| https://lucidtrading.com/sitemap.xml | 403 | Ídem |

**Búsquedas sin resultados** en el help center (`support.lucidtrading.com/en/?q=...`, HTTP 200 pero sin
artículos): `dominican`, `tax`, `w-8ben`, `vps`, `api`, `ninjascript`, `weekend`.
