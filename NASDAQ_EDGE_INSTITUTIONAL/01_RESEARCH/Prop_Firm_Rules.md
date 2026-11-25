# Reglas de firmas de fondeo · consulta 2026-11-25

Cada regla se leyó en la web oficial de la firma el 2026-11-25. Pueden cambiar en
cualquier momento. Antes de comprar o de operar se verifican en el dashboard de
la cuenta. El perfil del motor de cumplimiento guarda: fuente, fecha de consulta,
fecha de última verificación, versión (`2026-11-25.1`) y estado.

Estados:
- `verificada` = leída en la página oficial citada.
- `discrepancia` = dos páginas oficiales no coinciden.
- `Sin datos` = no encontrada.

No se mezclan las fases de evaluación, la cuenta simulada financiada y la Live.

---

## 1. Topstep · $50K

### 1.1 Trading Combine (evaluación)

| Regla | Valor | Estado | Fuente |
|---|---|---|---|
| Profit Target | $3.000 | verificada | help.topstep.com/en/articles/8284197 |
| Maximum Loss Limit (MLL) | $2.000; empieza en $48.000 | verificada | 8284197, 8284204 |
| Tipo de MLL | trailing por **balance de fin de día**; nunca baja; se bloquea al llegar al balance inicial | verificada | 8284197 |
| Vigilancia del MLL | **en tiempo real, incluye P&L no realizado**: tocarlo con una posición abierta liquida | verificada | 8284197, 8284204 |
| Daily Loss Limit | **opcional**, $1.000, elegido al comprar. Detiene el día hasta las 17:00 CT; no es violación | verificada | 8284197 |
| Consistency Target | mejor día ≤ 55 % del Profit Target (< $1.650). Si se supera, sube el objetivo. El mejor día se fija a las 15:10 CT | verificada | 8284208 |
| Días mínimos | 2 | verificada | 8284197 |
| Máximo de contratos | 5 minis / 50 micros (1 mini = 10 micros) | verificada | 8284197 |
| Cierre | todo plano a las **15:10 CT** (16:10 ET); evitar nuevas entradas desde las 15:08 CT; sin overnight | verificada | 8284206 |
| Noticias Tier 1 (CPI, PPI, NFP, FOMC decisión, FOMC rueda de prensa) | ventana de 10 min (−5/+5): **NQ sin nuevas aperturas**; MNQ con apertura máxima de **3 micros** en 50K Standard; las posiciones previas se pueden gestionar; las pendientes no se ejecutan | verificada | 13613539 |
| Horas Tier 1 (CT) | CPI/NFP/PPI 7:30 → ventana 7:25–7:35; FOMC 13:00 → 12:55–13:05; rueda de prensa 13:30 → 13:25–13:35 | verificada | 13613539 |
| Estrategia prohibida | operar el **tamaño máximo directamente hacia una noticia mayor**; explotar fills SIM; operar fuera del bid/ask; posición a menos del 2 % del price limit | verificada | 10305426, 10296582 |
| Automatización | sí, con condiciones: vía API TopstepX/ProjectX (suscripción aparte); sin VPS/VPN | verificada | 11187768, 10296582 |
| Precio 50K | $49/mes (Standard + $149 de activación XFA) o $95/mes (sin activación) | verificada | 14289835 |

### 1.2 Express Funded Account (XFA, simulada financiada)

| Regla | Valor | Estado | Fuente |
|---|---|---|---|
| Balance | empieza en $0 (50K = poder de compra) | verificada | 8284215 |
| MLL | −$2.000, trailing; se bloquea en $0 al llegar a $2.000; tras el 1er payout queda en $0 | verificada | 8284215 |
| Escalado | Scaling Plan por balance. La tabla 50K es una imagen y **no se leyó** | Sin datos | 8284223 |
| Tier 1 en XFA 50K | < $1.500 → 0 minis / 1 micro; $1.500–2.000 → 0/1; > $2.000 → 0/3 | verificada | 13613539 |
| Payout Standard | 5 días ganadores ≥ $150 netos; hasta el 50 % del balance | verificada | 8284233 |
| Payout Consistency | 3 días operados; mejor día ≤ 40 % del beneficio neto | verificada | 8284208 |
| Tope por payout 50K | Standard $2.000 / Consistency $3.000 (Payout Policy); la tabla XFA dice "hasta $5.000" | **discrepancia** | 8284233 vs 8284215 |
| Reparto | 90/10; mínimo $125 | verificada | 8284233 |

### 1.3 Live Funded Account (LFA)

- Arranca con el 20 % disponible y el 80 % en reserva.
- DLL estándar $2.000 en 50K.
- Se liquida si el balance baja de $1.000.
- **Automatización no disponible** en LFA.
- El scaling de micros a minis no aplica.

Estado: verificada. Fuente: 10657969.

---

## 2. Apex Trader Funding · $50K

Hay dos caminos independientes; **no se mezclan**.

### 2.1 Evaluación EOD (End-of-Day Trailing)

| Regla | Valor | Estado | Fuente |
|---|---|---|---|
| Profit Target | $3.000 | verificada | apextraderfunding.com/help-center/eod-trailing-drawdown-accounts/eod-evaluations/ |
| Max Drawdown | $2.000 | verificada | ídem |
| Cálculo | umbral recalculado una vez al día (16:59:59 ET) con el balance de cierre; **se aplica en tiempo real** en la sesión siguiente; nunca baja | verificada | …/eod-drawdown-explained/ |
| Fin del trailing (evaluación) | Rithmic/Wealthcharts: se fija en el balance objetivo ($53.000). Tradovate: **trailing indefinido** | verificada | ídem |
| DLL | $1.000, fijo en la sesión; pausa el día, no suspende la evaluación | verificada | …/daily-loss-limit-explained/ |
| Contratos máximos | 6 (la equivalencia con micros **no** se lee en esa página) | verificada / Sin datos | eod-evaluations |
| Consistencia / escalado | no aplicados en la evaluación | verificada | ídem |
| Días mínimos | ninguno; plazo de 30 días | verificada | ídem |

### 2.2 Evaluación Intraday Trailing

| Regla | Valor | Estado | Fuente |
|---|---|---|---|
| Profit Target | $3.000 | verificada | …/intraday-trailing-drawdown-evaluations/ |
| Max Drawdown | $2.000, sigue el **pico intradía incluido el no realizado** | verificada | …/intraday-trailing-drawdown-explained/ |
| DLL | **no hay** | verificada | ídem, daily-loss-limit-explained |
| Contratos máximos | 6 | verificada | ídem |
| Fin del trailing (evaluación) | Rithmic/Wealthcharts: $53.000. Tradovate: indefinido | verificada | ídem |

Diferencia operativa clave: en Intraday Trailing una operación que llega a +$900
**no realizados** y vuelve a 0 sube el umbral $900 aunque cierre en 0. Para un
sistema con TP2 y trailing esto consume drawdown. El motor de riesgo debe modelar
cada tipo por separado.

### 2.3 Performance Account (PA, simulada)

| Regla | EOD PA 50K | Intraday PA 50K | Fuente |
|---|---|---|---|
| Max DD | $2.000 EOD | $2.000 intradía | páginas PA |
| Trailing se detiene | en $50.100 | en $50.100 | drawdown-explained |
| Contratos y DLL por nivel | L1 $0–1.499: 2 contratos, DLL $1.000; L2 $1.500–2.999: 3 contratos, $1.000; L3 $3.000–5.999: 4 contratos, $2.000; L4 ≥ $6.000: 4 contratos, $3.000 | igual | scaling-levels-pa-explained |
| Payout | 5 días con ≥ $250 (EOD) / ≥ $200 (Intraday); consistencia 50 %; mínimo $500; safety net $52.100; máximo 6 payouts | | payouts |
| Inactividad | cerrada si no hay 2 días de ≥ $50 en 30 días | | intraday PA FAQ |

### 2.4 Conducta (todas las cuentas Apex)

Fuente: `help-center/getting-started/prohibited-activities/`.

- **Automatización y algoritmos prohibidos.** El indicador de este proyecto
  solo emite alertas; la ejecución es manual.
- Noticias: se permite operar con la estrategia normal. Se prohíben las
  estrategias de "news trading" que persiguen el mercado o ponen órdenes a ambos
  lados.
- Obligatorio el stop (pendiente o mental).
- Prohibido el riesgo desproporcionado (ejemplo oficial: TP 5 ticks con SL 150).
- Prohibido usar el umbral como stop, hacer hedging y mantener posiciones
  abiertas al cierre del mercado.

---

## 3. Tradeify · $50K

Fuentes: help.tradeify.co, leído con el navegador. La portada tradeify.co muestra
tarjetas "50K Evaluation" con DD $1.000 y DLL $600 que **contradicen** el help
center. Pueden ser una plantilla de 25K mal etiquetada. Se toman como válidos los
artículos del help center y se marca **discrepancia**.

| Regla | Growth (eval) | Select (eval) | Lightning (financiada directa) |
|---|---|---|---|
| Profit Target | $3.000 | $3.000 (las cuentas antiguas mantienen $2.500) | objetivos de payout por tabla (no leída al completo) |
| Drawdown | $2.000, EOD trailing, aplicado en tiempo real | $2.000 EOD | $2.000 EOD |
| DLL (soft) | $1.250 | ninguno en evaluación | $1.250 |
| Consistencia | ninguna | 40 % (o 30 %; complemento del 50 % opcional) | progresiva 20 % → 25 % → 30 % por payout |
| Días mínimos | 1 | 3 (40 %) / 4 (30 %) | sin mínimo |
| Contratos máximos | 4 minis / 40 micros | 4 / 40 | 4 / 40 |

Fuentes: artículos 10495915, 12853921, 10495938, 10468320, 10495897 y 10468321.

Financiadas:

| Regla | Growth Funded | Select Flex | Select Daily |
|---|---|---|---|
| DLL | $1.250; sube a $2.000 al alcanzar $53.000 | ninguno | $1.000 |
| Consistencia | 35 % | ninguna | ninguna |
| Payout | 5 días > $150; balance ≥ $53.000 | cada 5 días ganadores ≥ $150 | diario |
| Contratos | 4 / 40 | 2 → 4 minis con escalado | ídem |
| Bloqueo del DD | $52.100 → suelo $50.100, o al pedir payout | ídem | ídem |

Fuentes: 11083796, 12853966 y 10495897.

Común:
- **Noticias sin restricción** (10495874).
- Todo cerrado a las **16:45 ET**; 12:59 ET en festivos cortos (10495876).
- Microscalping en financiadas: > 50 % de las operaciones **y** > 50 % del
  beneficio en operaciones de más de 10 s. Si no se cumple, se bloquea el payout
  (10468318).
- Bots propios permitidos con condiciones: propiedad exclusiva, uso solo en
  Tradeify, nada de HFT.
- Hedging prohibido.
- Al menos 1 operación por semana.
- Máximo 5 cuentas financiadas.
- Reparto 90/10.

---

## 4. Implicaciones para el sistema

1. **La pérdida flotante cuenta en las tres firmas.** El riesgo se calcula sobre
   el peor caso abierto: stop × contratos + slippage + comisión. No sobre el P&L
   cerrado.
2. Distancia al umbral = equity actual − umbral vigente.
   - Topstep y Apex EOD: el umbral se fija al cierre.
   - Apex Intraday: el umbral se mueve con el pico no realizado, así que el
     motor lo recalcula en cada vela.
3. Noticias: la regla interna del proyecto (Tier 1 ±15 min) es **más estricta**
   que Topstep (±5 min) y que Apex y Tradeify, que no tienen bloqueo. Si una
   firma se vuelve más estricta que la regla interna, prevalece la firma.
4. Hora de cierre por perfil:
   - Topstep: sin entradas desde 16:08 ET.
   - Tradeify: sin entradas desde 16:40 ET [HIPÓTESIS de margen].
   - Apex: cierre de mercado 17:00 ET; hora exacta de liquidación **Sin datos**;
     por prudencia, flat 16:55 ET [HIPÓTESIS].
5. Consistencia:
   - Topstep Combine: mejor día < $1.650.
   - Tradeify Select: ≤ 40 %.
   - Apex PA: < 50 %.
   - Con objetivo 2R × $150 = $300 por operación y máximo 3 operaciones, el
     tope teórico diario (~$900) queda por debajo de $1.650. En Select, 40 % de
     $3.000 = $1.200, también compatible.
6. Apex prohíbe la automatización. Topstep LFA no admite API. Por eso la V1 es
   **solo alertas**, como pide el encargo.

## 5. Pendiente de verificar

- Comisiones de MNQ/NQ en Topstep y Apex, y de MNQ en Tradeify.
- Tabla del Scaling Plan XFA 50K de Topstep (es una imagen).
- Equivalencia mini/micro en Apex.
- Hora exacta de cierre forzoso de Apex.
- Tabla de objetivos de payout de Lightning.
- Lista de "Product Groups" de Tradeify.
- Discrepancias: portada vs help center de Tradeify; tope de payout XFA de Topstep.
