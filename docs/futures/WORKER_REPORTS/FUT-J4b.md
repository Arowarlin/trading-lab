# FUT-J4b · Puente NinjaTrader 8 en Sim101

**Estado:** PARADO en el paso 2, esperando al operador (compilar y activar). 2026-11-28.

## Hecho

1. Copiado `integrations\nt8\TradingLabBridge.cs` a
   `%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\Strategies\TradingLabBridge.cs`
   (no existía antes; SHA-256 idéntico al del repo). No se movió ni borró nada.
2. Revisión estática del `.cs` antes de compilar: firmas de `SubmitOrderUnmanaged` correctas, `using`
   suficientes, guarda de cuenta Sim/Playback en `State.DataLoaded`. El extractor JSON acepta el
   espacio tras `:` que escribe `json.dumps`.

## Instrucciones al operador

En NinjaTrader: New > NinjaScript Editor > abre TradingLabBridge y pulsa F5 (compilar). Si hay errores,
cópialos aquí. Si compila: abre un gráfico de MNQ, añade la estrategia TradingLabBridge con la cuenta
Sim101, BridgeDir = `E:\tl-fut-s\data\futures\nt8_bridge`, MaxContracts = 1, y actívala.
Responde OK NT8 cuando esté activa.

## Aviso

- **BridgeDir cambia respecto al prompt:** `NT8Bridge` escribe en `<repo del código>/data/futures/nt8_bridge`.
  La prueba de humo se lanza desde `E:\tl-fut-s`, así que el directorio es `E:\tl-fut-s\data\futures\nt8_bridge`,
  no `E:\trading-lab\...`.
- **Mercado cerrado:** hoy es sábado. La estrategia solo sondea el outbox en `OnBarUpdate` en tiempo real
  (con cada tick). Sin ticks no habrá ack. La prueba necesita mercado abierto (CME reabre el domingo a las
  18:00 ET) o una conexión Playback con datos.
- Al enviar entrada a mercado y stop/objetivo a la vez, en Sim101 queda una posición de 1 MNQ con OCO.
  Cerrarla a mano tras la prueba.

## Siguiente

Tras «OK NT8» y el último precio de MNQ:
`.\.venv\Scripts\python.exe scripts\nt8_bridge_smoke.py --account Sim101 --price <precio> --stop-pts 20`
