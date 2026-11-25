# Manual de usuario · NASDAQ EDGE INSTITUTIONAL V1.0

## Qué es y qué no es

- **Es** un panel de contexto de sesión y una calculadora de riesgo para
  cuentas de fondeo, con protección de noticias.
- **No es** un sistema de señales. La investigación (Fase C) no encontró ventaja
  estadística: 0 de 22 variantes. Por eso no hay BUY ni SELL y la cabecera
  muestra siempre **NO EDGE VALIDATED**.

## Estados

| Estado | Significado |
|---|---|
| **NO TRADE · motivo** | Alguna regla de cuenta, noticias, horario o datos impide abrir. El motivo es la primera regla que falla |
| **WAIT · sin señal** | Ninguna regla bloquea. **No** es una invitación a entrar: no hay edge validado |
| BUY / SELL | **No existen en la V1** |

## Panel

- Instrumento y hora de Nueva York.
- Régimen: ADX de 15 min (cerrado), percentil del ATR diario.
- Compresión: OR15 frente al ATR, con los umbrales p25/p50 medidos en la Fase B.
- Sesgo: precio frente a VWAP. Es solo descriptivo.
- Niveles: VWAP, OR, ONH/ONL, PDH/PDL, ATR y RVOL de barra (solo CME).
- Noticias: estado y cuenta atrás hasta el próximo evento.
- Perfil de la firma con versión y fecha de verificación.
- Cuenta: distancia al umbral, DLL restante, pérdida diaria restante, operaciones y pérdidas.
- Operación planificada: presupuesto, stop, coste por contrato, contratos, riesgo previsto, TP1/TP2 de referencia (1R/2R) y reglas de cierre y noticias de la firma.

## Operación planificada

1. Activa "Operación planificada", elige la dirección y fija entrada y stop.
2. El indicador calcula los contratos con el presupuesto disponible.
3. Si da 0 → NO TRADE. **No amplíes el stop para que quepa.**
4. TP1 y TP2 son referencias de 1R y 2R, no objetivos validados.

## Alertas

Son informativas y no hay ejecución automática.

- **Mensaje JSON en cada cambio WAIT ↔ NO TRADE y ante una noticia próxima.**
  Campos: instrumento, hora NY, estado, motivo, dirección, entrada, stop, TP1,
  TP2, contratos, riesgo y justificación.
- **Condiciones con alerta propia:** SL, TP1 (revisar break-even), TP2, noticia
  en ≤ 10 min, bloqueo de noticias, máximo de operaciones, pérdidas seguidas,
  NO TRADE y WAIT.
