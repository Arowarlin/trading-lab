"""Trailing stop manual para posiciones demo (no abre ni cierra).

El laboratorio no tiene trailing nativo: los bots están desactivados y MT5 no
ofrece trailing por API. Este script mueve el SL de los tickets indicados:

- a **breakeven** cuando el beneficio llega a `--be-r` R;
- a **mejor_precio ± atr_mult × ATR(H4)** cuando llega a `--trail-r` R.

Nunca aleja el stop del precio y nunca lo cruza (respeta `stops_level`).
Solo demo: el bróker del laboratorio exige `require_demo` y este script no
envía órdenes de apertura.

    .venv\\Scripts\\python.exe scripts\\trail_demo_positions.py --ticket 582422264 --hours 4
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tradinglab.config import get_settings  # noqa: E402
from tradinglab.execution import get_mt5_broker  # noqa: E402
from tradinglab.indicators import atr  # noqa: E402


def _is_short(side: str) -> bool:
    """MT5 devuelve 'buy'/'sell'; las pruebas usan 'long'/'short'."""
    return str(side).lower() in {"sell", "short"}


def next_stop(
    *,
    side: str,
    entry: float,
    best: float,
    atr_value: float,
    current_sl: float,
    profit_r: float,
    be_r: float = 0.5,
    trail_r: float = 1.0,
    atr_mult: float = 1.0,
    digits: int = 2,
    min_distance: float = 0.0,
) -> float | None:
    """Nuevo SL o None. `best` es el extremo favorable (mínimo en corto)."""
    short = _is_short(side)
    candidate: float | None = None
    if profit_r >= trail_r:
        candidate = best + atr_mult * atr_value if short else best - atr_mult * atr_value
        # Nunca peor que breakeven: si el ATR es más ancho que el beneficio,
        # el trail quedaría en pérdida. En corto manda el SL más bajo.
        candidate = min(candidate, entry) if short else max(candidate, entry)
    elif profit_r >= be_r:
        candidate = entry
    if candidate is None:
        return None
    candidate = round(float(candidate), int(digits))
    if short:
        # en corto el SL va por encima: solo se mueve hacia abajo
        if current_sl and candidate >= current_sl - 1e-9:
            return None
        if candidate <= best + min_distance - 1e-9:
            return None
    else:
        if current_sl and candidate <= current_sl + 1e-9:
            return None
        if candidate >= best - min_distance + 1e-9:
            return None
    return candidate


def _log(path: Path, message: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    line = f"{stamp} {message}"
    print(line)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Trailing stop manual en demo")
    parser.add_argument("--ticket", type=int, action="append", default=[])
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--be-r", type=float, default=0.5)
    parser.add_argument("--trail-r", type=float, default=1.0)
    parser.add_argument("--atr-mult", type=float, default=1.0)
    parser.add_argument(
        "--atr-timeframe",
        default="H4",
        help="Timeframe del ATR para el trail (H1 para intradía, H4 por defecto)",
    )
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--hours", type=float, default=4.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--log", default=str(ROOT / "logs" / "trail_demo.log"))
    args = parser.parse_args()

    log_path = Path(args.log)
    settings = get_settings()
    broker = get_mt5_broker(settings, dry_run=False)
    started = time.time()
    deadline = started + args.hours * 3600
    initial: dict[int, dict] = {}
    best: dict[int, float] = {}
    _log(log_path, f"INICIO trailing tickets={args.ticket or 'todos'} horas={args.hours:g}")
    try:
        broker.connect()
        while True:
            positions = broker.positions(args.symbol)
            if args.ticket:
                positions = [p for p in positions if int(p["ticket"]) in set(args.ticket)]
            if not positions and initial:
                _log(log_path, "sin posiciones: fin")
                break
            for position in positions:
                ticket = int(position["ticket"])
                if ticket not in initial:
                    initial[ticket] = {
                        "entry": float(position["price_open"]),
                        "sl": float(position["sl"] or 0.0),
                        "side": str(position["side"]),
                    }
                    best[ticket] = initial[ticket]["entry"]
                    _log(
                        log_path,
                        f"{ticket} {position['symbol']} {position['side']} "
                        f"{position['volume']} @ {initial[ticket]['entry']:.5f} "
                        f"SL {initial[ticket]['sl']:.5f}",
                    )
                data = initial[ticket]
                if data["sl"] <= 0:
                    continue
                tick = broker.tick(position["symbol"])
                spec = broker.symbol_spec(position["symbol"])
                short = _is_short(data["side"])
                price = tick["ask"] if short else tick["bid"]
                best[ticket] = (
                    min(best[ticket], price) if short else max(best[ticket], price)
                )
                risk = abs(data["entry"] - data["sl"])
                if risk <= 0:
                    continue
                profit_r = (
                    (data["entry"] - price) / risk
                    if short
                    else (price - data["entry"]) / risk
                )
                h4 = broker.rates(position["symbol"], args.atr_timeframe, 500)
                atr_value = float(atr(h4).iloc[-1])
                min_distance = float(spec.get("stops_level") or 0) * float(
                    spec.get("point") or 0
                )
                new_sl = next_stop(
                    side=data["side"],
                    entry=data["entry"],
                    best=best[ticket],
                    atr_value=atr_value,
                    current_sl=float(position["sl"] or 0.0),
                    profit_r=profit_r,
                    be_r=args.be_r,
                    trail_r=args.trail_r,
                    atr_mult=args.atr_mult,
                    digits=int(spec["digits"]),
                    min_distance=min_distance,
                )
                if new_sl is None:
                    continue
                try:
                    broker.modify_position(ticket, sl=new_sl)
                    _log(
                        log_path,
                        f"{ticket} SL {position['sl']:.5f} -> {new_sl:.5f} "
                        f"(precio {price:.5f}, {profit_r:+.2f}R, best {best[ticket]:.5f})",
                    )
                except Exception as exc:
                    _log(log_path, f"{ticket} no se pudo mover el SL: {exc}")
            if args.once or time.time() >= deadline:
                _log(log_path, "fin (once/tiempo)")
                break
            time.sleep(max(10, int(args.interval)))
    finally:
        broker.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
