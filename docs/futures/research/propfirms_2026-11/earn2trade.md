# Earn2Trade · ficha 50K (investigación 2026-11)

- **Id:** `earn2trade` · **Cuenta de referencia:** 50K · **Fecha de consulta:** 2026-11-27 (UTC).
- **Estado global:** `no verificado` (bloqueado). La web y el help center respondieron **403** (bloqueo de
  Cloudflare) a `curl` con el agente de usuario por defecto. **No se leyó ninguna fuente oficial.** No se
  suplantó un navegador ni se usaron cachés, espejos ni copias de terceros.
- **Registro previo del laboratorio:** `config/prop_economics/firms_futures.yaml` tiene la automatización
  como `sin_datos` (mismo bloqueo, 2026-11-27). No hay otra lectura oficial previa en el repositorio.
- **Programas:** **Sin datos.** Pista no verificada, que no es evidencia porque viene del conocimiento
  previo del agente: los programas de 50K que conviene buscar al guardar las páginas son "Trader Career
  Path" y "Gauntlet Mini". No se usa ningún valor de esa pista.

Todos los campos de la plantilla quedan **Sin datos** porque la web oficial no se pudo leer. El silencio
no es autorización: nada de lo que sigue permite suponer que una regla falte o que algo esté permitido.

## A. Costes (50K)

| Campo | Valor | Estado |
|---|---|---|
| Precio de evaluación (lista / promoción) | **Sin datos** | no verificado |
| ¿Suscripción mensual o pago único? | **Sin datos** | no verificado |
| Activación | **Sin datos** | no verificado |
| Reset | **Sin datos** | no verificado |
| Datos de mercado | **Sin datos** | no verificado |
| Comisiones por contrato (MNQ, NQ) | **Sin datos** | no verificado |
| Otros cargos (API, plataforma, retiro) | **Sin datos** | no verificado |
| Coste hasta financiada (mejor caso, 1 intento) | **Sin datos** | no verificado |
| Coste de mantenerla 3 y 6 meses | **Sin datos** | no verificado |

## B. Reglas de trading

| Campo | Valor | Estado |
|---|---|---|
| Profit target | **Sin datos** | no verificado |
| Drawdown máximo | **Sin datos** | no verificado |
| Tipo (estático / trailing EOD / intradía; P&L no realizado; bloqueo) | **Sin datos** | no verificado |
| DLL (importe y efecto) | **Sin datos** | no verificado |
| Consistencia (evaluación y financiada) | **Sin datos** | no verificado |
| Contratos máximos y equivalencia de micros | **Sin datos** | no verificado |
| Horarios (cierre obligatorio) | **Sin datos** | no verificado |
| Noticias | **Sin datos** | no verificado |
| Overnight y fin de semana | **Sin datos** | no verificado |
| Escalado | **Sin datos** | no verificado |

## C. Payouts

| Campo | Valor | Estado |
|---|---|---|
| Días necesarios · beneficio mínimo por día | **Sin datos** | no verificado |
| Número máximo de retiros · mínimo · máximo por retiro | **Sin datos** | no verificado |
| Reparto · buffer · topes acumulados | **Sin datos** | no verificado |
| Solicitado → aprobado → procesado → recibido | **Sin datos** | no verificado |
| Métodos de pago · KYC | **Sin datos** | no verificado |
| Transición a Live | **Sin datos** | no verificado |

## D. Automatización (crítico)

**Veredicto: Sin datos.** No se leyó ningún texto oficial. Mientras tanto se trata como **no
autorizada**: el silencio no es permiso.

| Campo | Valor | Estado |
|---|---|---|
| Bots y estrategias automáticas | **Sin datos** | no verificado |
| NinjaTrader 8 Automated Strategies / NinjaScript | **Sin datos** | no verificado |
| ATM Strategies | **Sin datos** | no verificado |
| Copiadores de operaciones | **Sin datos** | no verificado |
| Varias cuentas (cuántas) | **Sin datos** | no verificado |
| VPS | **Sin datos** | no verificado |
| Límites de frecuencia · HFT · microscalping (umbral) | **Sin datos** | no verificado |
| Técnicas de ejecución prohibidas | **Sin datos** | no verificado |
| ¿Pueden anular beneficios por automatización? | **Sin datos** | no verificado |
| Diferencias evaluación / simulada financiada / Live | **Sin datos** | no verificado |

## E. Plataformas

| Campo | Valor | Estado |
|---|---|---|
| NinjaTrader 8 · Rithmic · CQG · Tradovate · TradingView · Quantower · Sierra Chart · Bookmap · ATAS | **Sin datos** | no verificado |
| APIs · conexiones simultáneas | **Sin datos** | no verificado |

## F. Elegibilidad internacional

**República Dominicana: no verificado (Sin datos).**

| Campo | Valor | Estado |
|---|---|---|
| ¿Acepta residentes de RD? (lista de países restringidos) | **Sin datos** | no verificado |
| KYC | **Sin datos** | no verificado |
| Métodos de cobro desde RD | **Sin datos** | no verificado |
| Impuestos y formularios (W-8BEN u otros) | **Sin datos** | no verificado |

## G. Fuentes

### Leídas
Ninguna.

### No leídas

| URL | Código | Hora (UTC) | Nota |
|---|---|---|---|
| https://www.earn2trade.com/ | **403** (Cloudflare "Sorry, you have been blocked", Ray ID a614e6bc4cf2d6bb) | 2026-11-27 23:27:02 | un solo intento con `curl` y el agente por defecto |
| https://help.earn2trade.com/ | **403** (Cloudflare, Ray ID a614e6bdbb23e635) | 2026-11-27 23:27:03 | un solo intento |
| earn2trade.com (portada) | **403** (Cloudflare, Ray ID a614d5e128d3dc30) | 2026-11-27 ~23:15 (sesión principal) | no se reintentó |
| help.earn2trade.com | **403** (Cloudflare, Ray ID a614dd45ffd4ff28) | 2026-11-27 ~23:20 (sesión principal) | no se reintentó |

### Para completar la ficha
Hace falta todo. El operador puede guardar estas páginas desde un navegador (Ctrl+S) en
`docs/futures/research/fuentes/earn2trade/`, o pedir que una sesión con navegador las lea:
1. La página de precios y programas 50K: precio de lista y promoción, mensual o pago único, activación,
   reset y datos.
2. Las reglas de cada programa 50K: objetivo, drawdown y su tipo, DLL, consistencia, contratos, horarios,
   noticias y escalado.
3. Los artículos del help center sobre la cuenta financiada y los payouts.
4. Los artículos sobre automatización: bots, NinjaScript, ATM, copiadores, varias cuentas, VPS y HFT.
5. Términos y condiciones, y la lista de países restringidos (RD), KYC, métodos de cobro y formularios
   fiscales.
6. La lista de plataformas y comisiones por contrato.
