"""Artefacto `qqq-trend-cfd`: la misma regla del run d2316a4be339 en QQQ diario.

No es research nuevo: no registra en `strategy_trials` ni suma al DSR. Es la
misma hipótesis (trend 50/200 + stop ATR 3) sobre otro vehículo, QQQ diario
desde 1999, con los costes de US100.cash en FTMO (comisión 0, spread mediano
0,58 bps, slippage 2 bps por lado).

    .venv\\Scripts\\python.exe scripts\\build_qqq_trend_cfd_artifact.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tradinglab import data as data_mod  # noqa: E402
from tradinglab.backtest import run as run_backtest  # noqa: E402
from tradinglab.config import get_settings  # noqa: E402
from tradinglab.datacheck import check_frame  # noqa: E402
from tradinglab.exposure_sweep import save_artifact  # noqa: E402
from tradinglab.strategies.swing import atr_close_stop  # noqa: E402
from tradinglab.strategies.trend import trend_signal  # noqa: E402
from tradinglab.swing import (  # noqa: E402
    _daily_metrics,
    daily_returns,
    save_variant_artifact,
    trading_day,
)

OUT = ROOT / "reports" / "research" / "swing_cfd"
BOT = "qqq-trend-cfd"
SYMBOL = "QQQ"
PARAMS = {"fast": 50, "slow": 200, "regime": 200, "stop_atr": 3.0, "atr_window": 14}
SPREAD_BPS = 0.5767  # mediana de US100.cash en los últimos 3 años (caché MT5)
SLIPPAGE_BPS = 2.0
COMMISSION_BPS = 0.0
START = "1999-01-01"


def main() -> int:
    settings = get_settings()
    end = datetime.now(timezone.utc).date().isoformat()
    frame = data_mod.fetch(SYMBOL, START, end, settings.data.cache_dir)
    if len(frame) < 260:
        print(f"Sin datos suficientes: {len(frame)} barras")
        return 1
    check = check_frame(frame, SYMBOL, timeframe="1d")
    print(f"datacheck {SYMBOL}: {check['status']} · {check['rows']} barras · {check['reasons']}")
    if check["status"] == "falla":
        return 1

    signal = trend_signal(
        frame,
        fast=PARAMS["fast"],
        slow=PARAMS["slow"],
        regime=PARAMS["regime"],
    )
    target = atr_close_stop(
        signal.target,
        frame,
        stop_atr=PARAMS["stop_atr"],
        atr_window=PARAMS["atr_window"],
    )
    bt = run_backtest(
        frame,
        target,
        starting_cash=100_000.0,
        commission_bps=COMMISSION_BPS + SPREAD_BPS,
        slippage_bps=SLIPPAGE_BPS,
        flat_dates=[],
    )
    daily_ret = daily_returns(bt.returns)
    daily_equity = bt.equity.astype(float).groupby(
        trading_day(bt.equity.index)
    ).last()
    daily_equity.index = daily_ret.index
    stats = _daily_metrics(bt, daily_ret)

    variant = save_variant_artifact(
        OUT, SYMBOL, {"fast": 50, "slow": 200, "stop_atr": 3.0}, daily_ret, daily_equity
    )
    meta = {
        "bot": BOT,
        "symbol": SYMBOL,
        "params": {**PARAMS, "timeframe": "1D"},
        "source": (
            "QQQ diario desde 1999 (caché Yahoo) · misma regla trend 50/200 + "
            "ATR 3 que us100-trend-d1 · costes de US100.cash en FTMO"
        ),
        "note": (
            "no es research nuevo: no entra en strategy_trials ni suma al DSR; "
            "es la misma hipótesis ya evaluada, con otro vehículo"
        ),
        "num_trades": int(bt.metrics["num_trades"]),
        "sharpe": stats["sharpe"],
        "cagr": stats["cagr"],
        "max_drawdown": stats["max_drawdown"],
        "total_return": stats["total_return"],
        "sample_days": int(len(daily_ret)),
        "start": str(daily_ret.index[0].date()),
        "end": str(daily_ret.index[-1].date()),
        "costs": {
            "commission_bps": COMMISSION_BPS,
            "spread_bps": SPREAD_BPS,
            "slippage_bps": SLIPPAGE_BPS,
            "session": None,
        },
        "datacheck": {"status": check["status"], "reasons": check["reasons"]},
        "variant_artifact": str(variant),
    }
    saved = save_artifact(BOT, OUT, daily_ret, meta=meta)
    print(
        f"{BOT}: {meta['num_trades']} trades · Sharpe {stats['sharpe']:.3f} · "
        f"CAGR {stats['cagr']:.2%} · MaxDD {stats['max_drawdown']:.2%} · "
        f"{meta['sample_days']} días ({meta['start']} → {meta['end']})"
    )
    print("artefacto variante:", variant)
    print("artefacto bot:", saved["path"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
