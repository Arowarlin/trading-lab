"""Reconstruye y verifica el artefacto de la variante US100 50/200/ATR 3.

El run `d2316a4be339` no guardó los retornos diarios (el research no los
persistía todavía). Este script regenera la serie con el mismo código y los
mismos datos, la compara con las métricas guardadas del run y solo si coinciden
escribe el artefacto que lee `lab prop exposure-sweep`.

    .venv\\Scripts\\python.exe scripts\\rebuild_swing_artifact.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tradinglab.backtest import run as run_backtest  # noqa: E402
from tradinglab.config import get_settings  # noqa: E402
from tradinglab.exposure_sweep import artifact_file, save_artifact  # noqa: E402
from tradinglab.intraday import load_bars  # noqa: E402
from tradinglab.prop.rules import ftmo  # noqa: E402
from tradinglab.prop.simulator import monte_carlo  # noqa: E402
from tradinglab.strategies.swing import trend_daily_atr  # noqa: E402
from tradinglab.swing import _daily_metrics, daily_returns  # noqa: E402

OUT = ROOT / "reports" / "research" / "swing_cfd"
RUN_ID = "d2316a4be339"
SYMBOL = "US100.CASH"
PARAMS = {"fast": 50, "slow": 200, "stop_atr": 3.0}
EXPECTED = {
    "sharpe": 0.8012767425852404,
    "cagr": 0.11608909557573499,
    "max_drawdown": -0.26373814456355793,
    "num_trades": 10,
    "pass_rate": 0.546,
    "sample_days": 2145,
}
TOLERANCES = {
    "sharpe": 0.01,
    "cagr": 0.002,
    "max_drawdown": 0.002,
    "num_trades": 0,
    "pass_rate": 0.02,
    "sample_days": 0,
}
# Costes del run: comisión 0 (índices) + spread mediano de 3 años, slippage 2.
COSTS = {"commission": 0.0, "spread_recent_3y": 0.5767, "slippage": 2.0}


def main() -> int:
    settings = get_settings()
    rules = ftmo(100_000.0, "challenge")
    frame = load_bars(settings.data.cache_dir, SYMBOL, "H4")
    signal = trend_daily_atr(
        frame,
        fast=PARAMS["fast"],
        slow=PARAMS["slow"],
        regime=200,
        stop_atr=PARAMS["stop_atr"],
        atr_window=14,
    )
    bt = run_backtest(
        frame,
        signal.target,
        starting_cash=rules.account_size,
        commission_bps=COSTS["commission"] + COSTS["spread_recent_3y"],
        slippage_bps=COSTS["slippage"],
        session=("00:00", "23:59"),
        session_tz="UTC",
        flat_dates=[],
    )
    daily = daily_returns(bt.returns)
    stats = _daily_metrics(bt, daily)
    mc = monte_carlo(rules, daily, n_paths=2000, horizon=120, block_size=5, seed=42)
    observed = {
        "sharpe": stats["sharpe"],
        "cagr": stats["cagr"],
        "max_drawdown": stats["max_drawdown"],
        "num_trades": int(bt.metrics["num_trades"]),
        "pass_rate": mc["pass_rate"],
        "sample_days": len(daily),
    }
    print("observado:", observed)
    bad = [
        key
        for key, expected in EXPECTED.items()
        if abs(float(observed[key]) - float(expected)) > TOLERANCES[key]
    ]
    if bad:
        print(f"NO COINCIDE: {bad}")
        return 1
    meta = {
        "bot": "us100-trend-d1",
        "symbol": SYMBOL,
        "params": {**PARAMS, "regime": 200, "atr_window": 14, "timeframe": "H4"},
        "run_id": RUN_ID,
        "source": "reconstruido del run d2316a4be339 y verificado contra sus metricas",
        "verified": observed,
        "costs": COSTS,
        "sample_days": len(daily),
        "start": str(daily.index[0].date()),
        "end": str(daily.index[-1].date()),
    }
    saved = save_artifact("us100-trend-d1", OUT, daily, meta=meta)
    print("guardado:", saved)
    print("existe:", artifact_file(OUT, "us100-trend-d1").exists())
    return 0


if __name__ == "__main__":
    sys.exit(main())
