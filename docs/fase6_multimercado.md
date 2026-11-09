# Fase 6 — Multi-mercado: evaluación previa

Fecha: 2026-11-07. **No se ha añadido ningún mercado ni adaptador nuevo.**
Este documento fija qué falta, qué se verificó y qué decisiones dependen del
usuario.

## TradeStation SIM (alternativa elegida a IBKR)

- WebAPI v3, entorno SIM: `https://sim-api.tradestation.com/v3`; misma API que
  live pero con cuentas simuladas y sin ejecución real.
- OAuth 2.0: API Key (`client_id`), `client_secret`, refresh token con
  `offline_access`; el access token dura **20 minutos**.
- La cuenta de trading por sí sola no habilita la API: hay que solicitar una
  **API Key/WebAPI** a TradeStation.
- Alcance de la API: acciones/ETF, opciones y futuros. **No se asume forex**;
  para FX/CFD se mantiene MT5 demo.
- Implementado en modo **solo lectura**:
  - `execution/tradestation.py` con refresh OAuth, cuentas, balances,
    posiciones y quotes;
  - guard: solo `sim-api`, cuenta esperada y `dry_run=True`;
  - `lab tradestation setup|status|accounts|positions`;
  - `submit_market`/`close_position` responden `dry_run` y **no envían nada**.
- Bloqueado para conectar: `TRADESTATION_CLIENT_ID`, `_CLIENT_SECRET`,
  `_REFRESH_TOKEN` y `_ACCOUNT_ID` no están configurados; soporte debe habilitar
  la API Key. Los secretos van a keyring, nunca a `.env` ni logs.

## IBKR paper (descartado por ahora)

- `ib_async` **2.1.0** (PyPI, 2025-12-08), Python >=3.10, mantenido.
- Requiere **IB Gateway o TWS** abierto; sin conexión el adaptador debe fallar
  con un error claro.
- Interfaz propuesta, gemela de los brokers actuales:
  - contratos de acciones/ETF, futuros y forex;
  - guard de identidad: cuenta **paper** obligatoria;
  - stop obligatorio en aperturas;
  - cierre siempre permitido, incluso con kill-switch;
  - `health()`, `positions()`, `snapshot()`, `submit_market()`, `close_position()`.
- No se implementa hasta tener cuenta paper y confirmar el país/cuenta para CFD.
- **CFD en IBKR no se asume**: depende del país, permisos y tipo de cuenta. Hay
  que confirmarlo en el dashboard antes de escribir código.

## CFD vía MT5

- Reutiliza `execution/mt5.py`; no hace falta un bróker nuevo.
- Falta registrar en `instruments.py` los símbolos reales que ofrezca el bróker
  (p. ej. índices/metales), con `tick_size`, `tick_value`, contrato, lote y
  horario de sesión.
- No se inventan especificaciones: se leen con `mt5.spec` y se contrastan.
- Los CFDs pueden tener horarios y gaps distintos al forex; el guard debe
  bloquear aperturas fuera de sesión y permitir cierres.

## Futuros

- Ya existe adaptador ProjectX/TopstepX en dry-run.
- Pendiente: preset Topstep en `prop.yaml`, guard de MLL (bloquear aperturas
  cerca del límite, permitir cierres), barras continuas con rollover.
- Sin cuenta Topstep/API key no se puede probar; no se simula como si existiera.

## Catálogo y agentes

- `instruments.py` ya tiene `Instrument` por clase; falta un catálogo único con
  horario, multiplicador, moneda y fuente de datos para acciones/ETF, forex,
  futuros y CFD.
- Agentes por mercado (`agents/roles/`) y coordinador determinista: pendiente.
- Regla: cada mercado nuevo pasa su propio **mini-F13** en paper antes de
  combinarse con los demás.

## Decisión

Orden recomendado: **TradeStation SIM** (acciones/ETF/opciones/futuros) → CFD
MT5 con specs reales → agentes por mercado. IBKR queda descartado por ahora
porque el usuario ya tiene cuenta TradeStation. Nada se activa sin aprobación
y sin mini-F13; TradeStation espera API Key/soporte.
