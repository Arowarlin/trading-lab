# Plantilla de ficha · firma de fondeo de futuros (investigación 2026-11)

Una ficha por firma: `docs/futures/research/propfirms_2026-11/<id>.md`. Cuenta de referencia **50K**;
si la firma tiene varios programas, una subsección por programa (no se generalizan reglas entre
programas).

## Reglas de evidencia
- Solo fuentes **oficiales** (web, help center, términos, política de payouts). Afiliados, blogs y
  reseñas: nunca como evidencia; como mucho "pista no verificada".
- Cada dato lleva: valor · URL exacta · fecha de consulta (2026-11-27) · cita literal corta (≤ 25
  palabras) · confianza (alta/media/baja) · estado (`verificado` / `parcial` / `no verificado`).
- El silencio de la firma **no** es autorización: escribir "no lo dice la fuente oficial".
- Si la web responde 403 al acceso automático: anotarlo y parar. **No** suplantar un navegador ni usar
  cachés o espejos.
- Payouts: distinguir solicitado, aprobado, procesado y recibido.

## Campos

### A. Costes (50K)
Precio de evaluación (lista y promoción por separado) · ¿suscripción mensual o pago único? ·
activación · reset · datos de mercado · comisiones por contrato (MNQ, NQ) · otros cargos (API,
plataforma, retiro) · coste hasta tener una cuenta financiada en el mejor caso (1 intento) ·
coste de mantenerla 3 y 6 meses.

### B. Reglas de trading
Profit target · drawdown máximo · tipo (estático / trailing EOD / trailing intradía; ¿incluye P&L no
realizado?; dónde se bloquea) · DLL (importe y efecto: pausa o rotura) · consistencia (evaluación y
financiada) · contratos máximos y equivalencia de micros · horarios (cierre obligatorio) · noticias ·
overnight y fin de semana · escalado.

### C. Payouts
Días necesarios · beneficio mínimo por día · número máximo de retiros · mínimo · máximo por retiro ·
reparto · buffer · topes acumulados · tiempo de proceso · métodos de pago · KYC · transición a Live.

### D. Automatización (crítico)
¿Bots y estrategias automáticas? · ¿NinjaTrader 8 Automated Strategies / NinjaScript? · ¿ATM
Strategies? · ¿copiadores de operaciones? · ¿varias cuentas (cuántas)? · ¿VPS? · límites de
frecuencia · ¿HFT prohibido? · ¿microscalping prohibido (umbral)? · técnicas de ejecución
prohibidas · ¿pueden anular beneficios por automatización? · diferencias evaluación / simulada
financiada / Live.

### E. Plataformas
NinjaTrader 8 · Rithmic · CQG · Tradovate · TradingView · Quantower · Sierra Chart · Bookmap · ATAS ·
APIs · conexiones simultáneas.

### F. Elegibilidad internacional
¿Acepta residentes de **República Dominicana**? (lista de países restringidos o prohibidos, con URL) ·
KYC · métodos de pago para cobrar desde RD · impuestos o formularios (W-8BEN u otros) si la fuente lo
dice.

### G. Fuentes
Tabla: dato · URL · fecha · confianza · estado. Y lista de páginas que no se pudieron leer (código HTTP).
