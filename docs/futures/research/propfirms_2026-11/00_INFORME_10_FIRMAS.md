# Informe · 10 firmas de fondeo de futuros para TradingLab (2026-11-27/28)

**Autor:** Claude Code (síntesis) a partir de 10 fichas escritas por investigadores con fuentes oficiales
(`<firma>.md` en esta carpeta). **Perfil:** residente en República Dominicana, NQ/MNQ (después ES/MES y
GC/MGC), cuenta de 50K, NinjaTrader 8, bots propios, retiros netos sostenibles.
**Estados:** `verificado` (fuente oficial leída) · `parcial` · `no verificado`. Nada de esto compra,
abre cuentas ni acepta términos.

## 1. Resumen ejecutivo

1. **Ninguna firma confirma de forma positiva que acepte residentes de República Dominicana.** En las
   siete cuyas listas se leyeron, RD **no aparece** entre los países restringidos: Topstep, Lucid, My
   Funded Futures, Tradeify, TradeDay, Alpha Futures y Bulenox. Antes de pagar, hay que pedir
   confirmación por escrito al soporte.
2. **Bots:**

   | Situación | Firmas |
   |---|---|
   | Permite bots y copiadores | Lucid (sin HFT) |
   | Bots propios con condiciones | My Funded Futures, TradeDay, Tradeify (exclusivo de Tradeify), Bulenox (aprobación previa según sus términos), Topstep (solo por API TopstepX, no en Live, sin VPS) |
   | No permite bots: modo semimanual | Alpha Futures, Take Profit Trader |
   | Sin verificar: modo semimanual | Apex y Earn2Trade (sus webs rechazan el acceso automático) |

3. **NinjaTrader 8:**

   | Situación | Firmas |
   |---|---|
   | Sí | My Funded Futures (menos Signature), Bulenox (licencia gratis en la Master), Lucid (por CQG) |
   | Solo vía Tradovate | TradeDay, Tradeify |
   | **No** | Topstep (solo TopstepX), Alpha Futures |

4. **Mejor encaje para TradingLab hoy** (bots NQ/MNQ con NT8), con evidencia y pendientes:
   1. **Lucid · LucidFlex**: la que menos restringe la automatización y sin consistencia en la
      financiada. **Pendiente:** precios (web 403) y confirmación de RD.
   2. **My Funded Futures · Rapid/Pro**: bots propios, NT8, payouts diarios en Rapid.
   3. **Tradeify** o **Bulenox**, con sus condiciones (bot exclusivo de Tradeify; aprobación previa por
      escrito en Bulenox).

   **Topstep** queda como la mejor opción para un bot **Python** propio por la API de ProjectX, que
   encaja con la arquitectura de TradingLab, pero sin NT8.
5. **El valor esperado neto solo está calculado para Topstep** (`docs/futures/risk/01_INVESTIGACION_RIESGO.md`).
   Sin ventaja validada es **negativo en mediana con cualquier perfil**. El resto se calcula con el motor
   FUT-A cuando los YAML de cada programa estén verificados.
6. **Hallazgo de cumplimiento:** los términos de Topstep, Bulenox, TradeDay, Alpha Futures y Tradeify
   **prohíben el acceso automatizado a sus webs**. Los investigadores pararon al encontrar la cláusula,
   pero antes se descargaron unas 280 páginas con `curl`, una a una. Lo que falte se leerá con navegador
   (operador), y el motor de inteligencia queda rediseñado para no descargar esas webs
   (`12_PROP_FIRM_INTELLIGENCE_ENGINE.md`).

## 2. Comparación (50K o el plan de referencia)

| Firma (plan) | Precio 50K | Drawdown | Reparto | Payout (mín. / máx. / frecuencia) | Bots | NT8 | RD | Estado |
|---|---|---|---|---|---|---|---|---|
| Topstep (Combine → XFA Standard) | 49 USD/mes + 149 activación (o 95/mes sin activación) | 2.000 EOD; XFA: bloqueo en 0 al llegar a +2.000 o tras un payout | 90/10 | 125 / 2.000 (50 % del balance) / 5 días ≥ 150 | API TopstepX solamente | **No** | ausente de la lista | verificado |
| My Funded Futures (Rapid) | 125 promoción / 209 lista, pago único, sin activación | evaluación 2.000 EOD; financiada **intradía** | 90/10 | 500 / no dice / diario tras buffer de 2.100 | Propios, sin HFT | Sí | ausente | verificado/parcial |
| My Funded Futures (Pro) | 159 / 265 | EOD | 80/20 | 1.000 / 100.000 por ciclo (páginas en desacuerdo) / 14 días | Propios | Sí | ausente | parcial |
| Lucid (Flex) | **Sin datos** (403) | 2.000 EOD; bloqueo en 50.100 al primer payout | 90/10 | — / 2.000 (50 % del beneficio) / 5 días ≥ 150 | **Permitidos** (+ copiadores), sin HFT ni microscalping de ≤ 5 s | Sí (CQG) | ausente | verificado salvo precio |
| TradeDay (Quick Pay EOD) | 174 lista / 69 promoción, pago único | EOD en evaluación; financiada intradía sobre beneficio **bruto** | **50/50** hasta 4.000, luego 80/20 | 250 / no dice / desde el día 1 | Propios, sin API, ≤ 200 operaciones/día | Solo variantes Tradovate | ausente | verificado |
| Tradeify (Select Flex) | 174 | EOD trailing en tiempo real | 90/10 | 250 / 2.500 / 5 días ganadores | Propios y **exclusivos** de Tradeify; vídeo de verificación | Vía Tradovate | ausente | verificado |
| Bulenox (Momentum) | 143 (activación Master: Sin datos) | 2.000-2.500 trailing o EOD | 90/10 | Sin datos | Propios; los términos piden aprobación previa | Sí (licencia gratis) | ausente | parcial |
| Alpha Futures (Standard) | 129 USD/mes | 2.000 EOD; **el MLL no se mueve al retirar** | 90/10 | 500 / 3.000 / hasta 4 al mes, cada 5 días ≥ 200 | **Prohibidos** (semimanual permitido) | **No** | ausente | verificado |
| Take Profit Trader | Sin datos | Sin datos | 80/20 (PRO) · 90/10 (PRO+) | PayPal o Wise para internacionales; KYC | **"No trading bots"** | Sin datos | Sin datos | parcial |
| Apex | Sin datos (403) | lab 2026-11-25: 2.000 EOD o intradía | Sin datos hoy | Sin datos hoy | prohibidos según el laboratorio (no releído) | Sí, según el laboratorio | Sin datos | parcial |
| Earn2Trade | Sin datos (403) | Sin datos | Sin datos | Sin datos | Sin datos | Sin datos | Sin datos | no verificado |

Detalle, citas y URL de cada celda: la ficha de la firma, secciones A-G.

## 3. Auditoría de automatización (el silencio no es permiso)

| Firma | Modo TradingLab | Condiciones que obligan | Riesgo de anulación de beneficios |
|---|---|---|---|
| Lucid | `automated` | sin HFT; microscalping (> 50 % del beneficio en operaciones de ≤ 5 s); sin hedging entre cuentas | sí, por HFT o microscalping |
| My Funded Futures | `automated_conditional` | configuración propia; sin HFT; sin explotar fills simulados; CME en Live | sí |
| TradeDay | `automated_conditional` | sistema propio en plataforma soportada; sin API; ≤ 200 operaciones/día; sin microscalping (≈ 10 s); sin dividir órdenes | sí ("confiscated") |
| Tradeify | `automated_conditional` | dueño único demostrable; **no usar el mismo bot en otra firma**; sin HFT; > 50 % de operaciones y de beneficio en posiciones de más de 10 s | sí |
| Bulenox | `automated_conditional` | herramientas propias; aprobación previa por escrito (términos); sin algoritmos de scalping ni DTC Bridge; +100 USD/mes por API de terceros a Rithmic | sí |
| Topstep | `automated_conditional` | solo API TopstepX (29 USD/mes); no en Live; sin VPS/VPN; sin HFT | sí |
| Alpha Futures | `semi_manual` | bots, IA y automatización prohibidos; señales permitidas si la persona coloca, vigila y gestiona cada operación | sí |
| Take Profit Trader | `semi_manual` | "No trading bots" | — |
| Apex, Earn2Trade | `semi_manual` | política no verificada hoy | — |

**Conflicto importante para TradingLab:** Tradeify exige que el bot sea **exclusivo** de Tradeify. No se
puede usar la misma estrategia automática en Tradeify y en otra firma.

## 4. Elegibilidad internacional (República Dominicana)

| Firma | Lista de países leída | RD en la lista | Cobro desde fuera de EE. UU. |
|---|---|---|---|
| Topstep | sí (actualizada 2026-11-17) | no | transferencia internacional: 30 USD, 5-10 días hábiles + 1-3 de aprobación |
| Lucid | sí (2026-10-08) | no | WorkMarket by ADP (transferencia o PayPal) o cripto |
| My Funded Futures | sí | no | Rise (que pague a RD: Sin datos) |
| Tradeify | sí (programa sim) | no | Rise (Sin datos para RD); lista del programa Live: no encontrada |
| TradeDay | sí | no | Sin datos |
| Alpha Futures | sí | no | Sin datos |
| Bulenox | sí | no | Sin datos |
| Take Profit Trader, Apex, Earn2Trade | no | Sin datos | TPT: PayPal o Wise; KYC y formulario fiscal antes del payout |

**Acción:** antes de comprar en cualquier firma, pedir al soporte por escrito: "¿aceptan residentes de
República Dominicana y qué método de cobro tienen para RD?". Guardar la respuesta como evidencia.

## 5. Simulación de cuentas de 50K y valor esperado

- **Topstep 50K**, con reglas verificadas:
  - perfiles, Kelly, ratio negativo, horizontes de 6, 12 y 24 meses y varias cuentas:
    `docs/futures/risk/01_INVESTIGACION_RIESGO.md`;
  - simulación base: `sim/` de esta carpeta.
- **Resto de firmas:** la simulación espera el motor FUT-A y los YAML de cada programa (esquema de
  `docs/futures/04_SPEC_PROP_EV.md §8`). Faltan datos que cambian el resultado:
  - precio de Lucid;
  - payout mínimo y máximo de Bulenox;
  - escalado de la financiada en Topstep;
  - drawdown exacto de MFF Rapid;
  - comisiones por contrato en casi todas.
- **Variables por firma** que el motor necesita:
  - precio y cuotas;
  - activación y reset;
  - tipo y bloqueo del drawdown;
  - consistencia;
  - día ganador mínimo;
  - fracción, mínimo y tope del payout, y reparto;
  - comisión de retiro y plazo;
  - escalado y límite de cuentas.

## 6. Ranking ponderado

**Rúbrica (0-5):**

| Criterio (peso) | Escala |
|---|---|
| Reglas y protección del trader (15 %) | claridad y verificación; DLL que pausa en vez de romper; peso de la consistencia |
| Payouts y retiros (20 %) | reparto, mínimo, tope, frecuencia, cobro internacional |
| Automatización (20 %) | permitida 5 · condicional leve 4 · condicional estricta 3 · solo API sin NT8 2 · prohibida 1 |
| Drawdown y gestión del riesgo (15 %) | EOD 4 · intradía 2, ±1 según el bloqueo |
| Costes totales (10 %) | pago único bajo 5 … mensual alto 2 |
| Plataforma para TradingLab (10 %) | NT8 completo 5 · solo vía Tradovate 3 · sin NT8 1 |
| Elegibilidad internacional (10 %) | lista leída sin RD 3; sin leer → **sin nota** |

**Una firma con un criterio sin nota no entra en el ranking general.**

| Puesto | Firma (plan) | Reglas | Payouts | Bots | Drawdown | Costes | Plataforma | Elegib. | Total |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | My Funded Futures (Rapid) | 3 | 4 | 4 | 2 | 4 | 5 | 3 | **3,55** |
| 2 | Tradeify (Select Flex) | 3 | 4 | 3 | 4 | 4 | 3 | 3 | **3,45** |
| 3 | TradeDay (QP EOD) | 3 | 2 | 3 | 3 | 5 | 3 | 3 | **3,00** |
| 4 | Topstep (Combine → XFA) | 4 | 3 | 2 | 3 | 4 | 1 | 3 | **2,85** |
| 5 | Alpha Futures (Standard) | 4 | 4 | 1 | 4 | 2 | 1 | 3 | **2,80** |
| — | Lucid (Flex) | 4 | 4 | 5 | 4 | **sin nota** | 4 | 3 | (3,70 sobre el 90 % del peso; **provisional 4,11**: sería 1.º si sus precios no lo hunden) |
| — | Bulenox (Momentum) | 2 | **sin nota** | 3 | 3 | 3 | 5 | 3 | (2,45 sobre el 80 %; provisional 3,06) |
| — | Take Profit Trader | — | — | 1 | — | — | — | — | **no puntuable** (precios y reglas sin leer) |
| — | Apex | — | — | — | — | — | — | — | **no puntuable** (web 403) |
| — | Earn2Trade | — | — | — | — | — | — | — | **no puntuable** (web 403) |

### Rankings por categoría (solo con evidencia)

| Categoría | Orden |
|---|---|
| Mejor para bots | Lucid > My Funded Futures > TradeDay ≈ Bulenox > Tradeify > Topstep > Alpha / TPT |
| Mejor para NinjaTrader 8 | My Funded Futures ≈ Bulenox > Lucid > TradeDay ≈ Tradeify |
| Mejor para NQ/MNQ automatizado | Lucid Flex (pendiente de precio) > My Funded Futures > Tradeify |
| Mejor para residentes de RD | **Sin ganador verificado**: ninguna lo confirma de forma positiva |
| Mejor relación coste-beneficio | My Funded Futures Rapid (pago único, sin activación, 90/10); TradeDay es la más barata, pero su reparto 50/50 hasta 4.000 penaliza |
| Mejor política de payouts | Alpha Futures (90 %, hasta 4 al mes, el MLL no se mueve) ≈ My Funded Futures Rapid (diario) > Lucid Flex ≈ Tradeify |
| Varias cuentas | Topstep: hasta 5 XFA a la vez. El resto, ver la ficha de cada firma; con el mismo bot, Tradeify lo impide entre firmas y Lucid, MFF y Tradeify prohíben el hedging entre cuentas |

## 7. Riesgos y restricciones

- Las reglas cambian a menudo: cada YAML caduca a los 30 días (ADR-F09).
- Sin RD confirmada, una compra puede acabar en un KYC rechazado.
- La automatización mal configurada puede activar las reglas de HFT o microscalping y llevar a la
  anulación de beneficios.
- Varias cuentas con el mismo bot son **una sola apuesta**
  (`docs/futures/risk/01_INVESTIGACION_RIESGO.md §4.3`).
- El valor esperado sin ventaja validada es **negativo en mediana**.

## 8. Recomendación final para TradingLab

1. **No comprar todavía:** falta una estrategia validada (forward NQF desde el 2026-11-30).
2. **Preparar ya**, sin coste:
   - pedir por escrito a Lucid, My Funded Futures, Tradeify y Bulenox la confirmación de RD y del método
     de cobro;
   - pedir a Bulenox la aprobación previa del bot;
   - leer con navegador los precios de Lucid y las páginas de Apex, Earn2Trade y Take Profit Trader.
3. **Cuando haya ventaja validada** (escalera de evidencia de `docs/futures/risk/01_INVESTIGACION_RIESGO.md §5`):
   - **Automático, en este orden:** Lucid Flex, My Funded Futures Rapid y Tradeify, con una estrategia
     distinta en Tradeify por la exclusividad.
   - **Topstep:** si el bot se ejecuta en Python por la API de ProjectX.
   - **Semimanual:** Alpha Futures y Take Profit Trader, con tickets de TradingLab y ejecución manual.
     Apex y Earn2Trade, también en semimanual, cuando se verifiquen.

## 9. Respuestas a los criterios de éxito

| Pregunta | Respuesta con evidencia |
|---|---|
| Las tres mejores para mi situación | Lucid Flex (provisional, falta el precio), My Funded Futures Rapid y Tradeify |
| La que permite automatizar con menos restricciones | Lucid |
| La de mejores condiciones de retiro | Alpha Futures (90 %, hasta 4 al mes, el MLL no se mueve) ≈ My Funded Futures Rapid (diario), pero Alpha prohíbe bots |
| La que acepta realmente a residentes de RD | **Ninguna confirmada**; siete no la excluyen en su lista |
| La de menor coste total | TradeDay (49-99 USD de pago único con promoción), con reparto 50/50 hasta 4.000 |
| La de mayor EV neto | **No calculable** sin ventaja validada; solo Topstep está modelado y su mediana es negativa sin ventaja |
| La mejor para escalar TradingLab | My Funded Futures y Lucid para bots en NT8; Topstep para un bot Python por API; varias firmas con estrategias **independientes** |

## 10. Fuentes

La sección G de cada ficha recoge URL, fecha, confianza y estado de cada dato, más las páginas que no
se pudieron leer.
