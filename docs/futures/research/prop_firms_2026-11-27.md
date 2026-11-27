# FUT-R1 · Reglas de las firmas de fondeo de futuros (consulta 2026-11-27)

**Autor:** Claude Code. **Método:** descarga con `curl` de las páginas oficiales desde la sesión en la
nube (tras abrir sus dominios en la red del entorno, con aprobación del operador), conversión a texto y
lectura de los pasajes. Sin fuentes de terceros. **No** se intentó saltar ninguna protección contra
bots: las webs que respondieron 403 al acceso automático quedan como bloqueadas.

**Estados:** `verified` = leído hoy en la página oficial citada · `parcial` = leído en una portada o
página de plan, sin la página de reglas detallada · `bloqueado` = la web rechazó el acceso automático ·
`Sin datos` = no está en lo leído.

## 0. Resumen

| Firma | Estado | Usable en el motor EV v1 |
|---|---|---|
| **Topstep** | `verified` (11 artículos del help center) | **Sí**: 50K Combine + XFA Standard |
| MyFundedFutures | `parcial` (páginas de planes) | No: faltan elegibilidad de payout y precios inequívocos |
| TradeDay | `parcial` (portada) | No: faltan precios y reglas por tamaño |
| Take Profit Trader | `parcial` (portada); `/terms` → 403 | No |
| Apex Trader Funding | **`bloqueado`** (403 a `curl`) | Solo con las reglas del 2026-11-25 (`verified_repo`) |
| Earn2Trade | **`bloqueado`** (403 a `curl`) | No |

Para completar las cuatro restantes hace falta leerlas con un navegador real. La opción sin saltarse
nada: que el operador guarde las páginas (Ctrl+S) en `docs/futures/research/fuentes/` o que una sesión
con el navegador de Claude las lea.

## 1. Topstep (`verified`, 2026-11-27)

Fuentes: `help.topstep.com/en/articles/` 8284197 (Combine), 8284204 (MLL), 8284208 (consistencia),
8284215 (XFA), 8284223 (Scaling Plan), 8284233 (payouts), 14289835 (precios), 13613539 (noticias),
11187768 (API), 10657969 (Live).

### 1.1 Trading Combine

| Regla | 50K | 100K | 150K | Cita |
|---|---|---|---|---|
| Profit Target | 3.000 | 6.000 | 9.000 | "Profit Target · $3,000 · $6,000 · $9,000" |
| Maximum Loss Limit | 2.000 | 3.000 | 4.500 | "It trails up with your end-of-day balance, never down. Once it reaches your starting balance, it locks permanently." |
| Vigilancia del MLL | en tiempo real con P&L no realizado | | | "Touch it at any point, even on unrealized P&L, and your account is liquidated" |
| Consistencia | mejor día < 55 % del objetivo; si se supera, el objetivo sube | | | "A $2,200 best day raises it to $4,000" (= 2.200 / 0,55) |
| Mejor día | se fija a las 15:10 CT | | | "Your best day locks in at 3:10 PM CT." |
| Contratos | 5 minis / 50 micros (1 mini = 10 micros) | 10 / 100 | 15 / 150 | "Minis and micros share the same limit at a 10:1 ratio" |
| DLL (opcional, al comprar) | 1.000 | 2.000 | 3.000 | "It is not a rule violation… no new trades are allowed until 5 PM CT" |
| Días mínimos | 2 | 2 | 2 | — |
| Plazo | ninguno | | | "Time limit to pass · None" |

### 1.2 Precios

| Tamaño | Vía Standard | Vía sin activación | Activación XFA (Standard) | Reset | Reactivación XFA |
|---|---|---|---|---|---|
| 50K | 49 USD/mes | 95 USD/mes | 149 USD una vez | igual que la mensualidad | 599 USD |
| 100K | 99 | 149 | 149 | ídem | 699 |
| 150K | 199 | 229 | 149 | ídem | 829 |

"Paths cannot be changed after purchase." Datos L1 incluidos en la membresía; L2 es un extra.

### 1.3 Express Funded Account (XFA)

| Regla | Valor | Cita |
|---|---|---|
| Balance inicial | 0 USD (poder de compra = tamaño de la cuenta) | "Your balance starts at $0" |
| MLL 50K | empieza en −2.000, sube con el balance y se bloquea en 0 al llegar a +2.000 | "Once your balance reaches $2,000, the MLL locks at $0 permanently." |
| Tras cada payout | MLL a 0 para siempre; el conteo de días se reinicia | "After each Payout: Your Maximum Loss Limit (MLL) resets to $0 permanently" |
| Vía Standard | 5 días ganadores ≥ 150 USD netos; beneficio > 0 desde el último payout | "5 winning days of $150+" |
| Vía Consistency | ≥ 3 días operados; mejor día ÷ beneficio neto ≤ 40 %; se reinicia tras cada payout | "Consistency = Largest Winning Day ÷ Total Net Profit" |
| Importe | 50 % del balance hasta el tope | "Max Payout per request: 50% of your account balance up to the cap below." |
| **Tope 50K** | **Standard 2.000 · Consistency 3.000** (100K: 3.000/4.000; 150K: 5.000/6.000) | tabla "Payout caps by account size" |
| Tope con DLL añadido al comprar | doble (50K: 4.000 / 6.000), oferta temporal para compras nuevas | "Traders who voluntarily add a Daily Loss Limit… unlock double per-request payout caps" |
| Mínimo | 125 USD | "Minimum Payout: $125" |
| Reparto | 90/10 | "90/10 profit split — you keep 90%" |
| Cuentas a la vez | hasta 5 XFA | "You can hold up to 5 active XFAs at a time." |
| Inactividad | > 30 días sin operar → puede cerrarse | "XFAs with no trading activity for more than 30 days may be closed." |
| Back2Funded | reactivar hasta 2 veces (599 USD en 50K) | "Back2Funded lets you reactivate up to 2 times" |
| Scaling Plan | por balance; los contratos no suben dentro de la sesión. **La tabla es una imagen: Sin datos** | "Your max contracts do not increase mid-session." |
| Tiempo de proceso del payout | **Sin datos** en lo leído | — |
| Comisiones por contrato | **Sin datos** en lo leído | — |

**Cambios frente a lo que tenía el laboratorio (2026-11-25):** la "discrepancia" del tope (2.000 frente a
5.000) queda resuelta: 5.000 es el tope de 150K; el de 50K Standard es 2.000. Son nuevos: la vía
Consistency (3 días, 40 %), los topes dobles con DLL, el límite de 5 XFA, la inactividad de 30 días y
Back2Funded.

## 2. MyFundedFutures (`parcial`)

Fuentes: `myfundedfutures.com/plans/rapid`, `/plans/rapid-eod`, `/plans/pro`. Planes listados también:
`builder` y `signature`. Help center: `help.myfundedfutures.com/en/` (solo se leyó el índice).

| Plan | Regla | Valor | Certeza |
|---|---|---|---|
| Rapid 50K | objetivo / drawdown | 3.000 / 2.000 "Trailing Max Drawdown" | parcial (no dice si es intradía o EOD) |
| Rapid | reparto · payouts · días mínimos · activación | 90/10 · diarios · 2 · 0 USD; pago único | parcial |
| Rapid 50K | contratos | 5 minis / 50 micros | parcial |
| Rapid EOD | drawdown EOD en evaluación y financiada, sin DLL (opcional), consistencia 30 %, mín. 4 días | 25K: 1.500 / 1.000; 50K: 3 minis / 30 micros | parcial |
| Pro 50K | objetivo / drawdown EOD / reparto | 3.000 / 2.000 / **80/20** | parcial |
| Pro | sin DLL ni consistencia en financiada; payout hasta 100.000 USD por ciclo; a Live tras 3 payouts consecutivos | — | parcial |
| Pro 50K | contratos | "3 mini / 3 micro" (texto tal cual; **ambiguo**) | parcial |
| Precios | Rapid muestra 125 y 209 USD; Pro 159 y 265 USD | **ambiguo**: no se distingue precio rebajado de precio de lista ni el tamaño | parcial |

Falta: elegibilidad exacta de payout, mínimos, buffers, reglas de noticias y automatización (la política
"Fair Play" del registro se consultó el 2026-11-19).

## 3. TradeDay (`parcial`)

Fuente: portada `www.tradeday.com` (muestra planes EOD e Intraday; los enlaces de compra van a
`members.tradeday.com`, que no se leyó).

| Regla | Valor | Certeza |
|---|---|---|
| 50K Intraday: objetivo / drawdown / contratos | 3.000 / 2.000 "calculated intraday" / 5 (50 micros) | parcial |
| 25K: objetivo / drawdown / contratos / consistencia / días mín. | 1.500 / 1.000 intradía / 2 (20 micros) / 30 % / 5 | parcial |
| Financiada: consistencia · buffer · días hasta payout · mínimo | ninguna · sin buffer · 1 · 250 USD | parcial |
| Reparto | 50/50 hasta 4.000 USD netos, 80/20 por encima, 90/10 en Live | parcial |
| Precio | "60% off… accounts from $39" (promoción; precio de lista **Sin datos**) | parcial |

## 4. Take Profit Trader (`parcial`)

Fuente: portada `takeprofittrader.com`. `/terms` respondió 403.

| Regla | Valor | Certeza |
|---|---|---|
| Planes | 3, uno con drawdown EOD | parcial |
| PRO | retiro desde el día 1; reparto 80 % | parcial |
| PRO+ | drawdown EOD, 90/10, sin buffer | parcial |
| Tarifas | "One Time $130 Fee" frente a "Monthly Recurring" (no queda claro a qué se refieren) | **ambiguo** |
| Promoción | "40% Off + No Activation Fee" | parcial |
| Tabla de reglas por tamaño (25K/50K/150K) | los valores no salen en el texto | **Sin datos** |

## 5. Apex Trader Funding y Earn2Trade (`bloqueado`)

Ambas webs responden **403** al acceso automático con el agente de usuario de `curl`. No se suplantó un
navegador. Para Apex sigue valiendo, como `verified_repo` y con caducidad, lo leído el 2026-11-25
(`NASDAQ_EDGE_INSTITUTIONAL/01_RESEARCH/Prop_Firm_Rules.md §2`); conviene re-verificarlo antes de
usarlo, porque las reglas de Apex cambian a menudo. Earn2Trade: **Sin datos**.

## 6. Consecuencias para el motor EV

- El programa de referencia de v1 es **Topstep 50K Combine → XFA Standard**, ahora `verified` a fecha
  2026-11-27 (caduca el 2026-12-27 con `expires_after_days: 30`).
- Siguen bloqueando una ejecución sin `--assume`: comisiones por contrato, tiempo de proceso del payout y
  la tabla del Scaling Plan.
- MyFundedFutures, TradeDay y Take Profit Trader entran como **segunda ola** cuando se lean sus páginas
  de reglas completas.
