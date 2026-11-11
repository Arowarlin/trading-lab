"""Exporta la traza de ejecución de un backtest a parquet.

Sirve para que un motor externo (vectorbt, prop-ev) pueda recomputar el mismo
camino con primitives idénticos: fecha, símbolo, objetivo de exposición, precio
de ejecución, comisión, spread y slippage.

No modifica `backtest.py`: lee su resultado (`BacktestResult`) y replica solo el
filtro de sesión/fechas que el motor aplica, para que el objetivo exportado sea
exactamente el que el motor usó en la apertura de cada barra.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .backtest import BacktestResult, _inside_session, _local_stamp, _session_bounds

SIGNAL_COLUMNS = (
    "symbol",
    "strategy",
    "target",
    "exec_price",
    "commission",
    "spread",
    "slippage",
    "qty",
    "side",
    "equity",
    "open",
    "close",
    "commission_bps",
    "slippage_bps",
    "spread_bps",
    "exposure",
)


@dataclass(frozen=True)
class SignalExport:
    path: Path
    meta_path: Path
    rows: int
    executions: int
    symbol: str
    strategy: str
    start: str
    end: str

    def summary(self) -> dict:
        return {
            "path": str(self.path),
            "meta_path": str(self.meta_path),
            "rows": self.rows,
            "executions": self.executions,
            "symbol": self.symbol,
            "strategy": self.strategy,
            "start": self.start,
            "end": self.end,
        }


def effective_target(
    df: pd.DataFrame,
    target: pd.Series,
    *,
    session: tuple[str, str] | None = None,
    session_tz: str = "UTC",
    flat_dates: Iterable[str] | None = None,
    max_gross: float = 1.0,
) -> pd.Series:
    """Objetivo que el motor aplica en la apertura de cada barra.

    Reproduce el filtro de sesión y de fechas planas del motor: fuera de la
    ventana el objetivo forzado es 0.
    """
    tgt = (
        target.reindex(df.index)
        .astype(float)
        .clip(-abs(max_gross), abs(max_gross))
        .fillna(0.0)
    )
    pos = tgt.shift(1).fillna(0.0)
    bounds = _session_bounds(session)
    flat = {str(value) for value in (flat_dates or [])}
    values: list[float] = []
    for stamp, value in pos.items():
        local = _local_stamp(stamp, session_tz)
        if local.date().isoformat() in flat or not _inside_session(local, bounds):
            values.append(0.0)
        else:
            values.append(float(value))
    return pd.Series(values, index=df.index, name="target", dtype=float)


def build_export(
    df: pd.DataFrame,
    target: pd.Series,
    bt: BacktestResult,
    *,
    symbol: str,
    strategy: str,
    commission_bps: float,
    slippage_bps: float,
    spread_bps: float = 0.0,
    exposure: float = 1.0,
    session: tuple[str, str] | None = None,
    session_tz: str = "UTC",
    flat_dates: Iterable[str] | None = None,
    max_gross: float = 1.0,
) -> pd.DataFrame:
    """Traza por barra con los precios y costes realmente usados."""
    index = bt.equity.index
    effective = effective_target(
        df,
        target,
        session=session,
        session_tz=session_tz,
        flat_dates=flat_dates,
        max_gross=max_gross,
    ).reindex(index)

    exec_price = pd.Series(np.nan, index=index, dtype=float)
    qty = pd.Series(0.0, index=index, dtype=float)
    side = pd.Series("", index=index, dtype=object)
    commission = pd.Series(0.0, index=index, dtype=float)

    trades = bt.trades
    if trades is not None and not trades.empty:
        for _, row in trades.iterrows():
            stamp = row["ts"]
            if stamp not in exec_price.index:
                continue
            exec_price.loc[stamp] = float(row["price"])
            qty.loc[stamp] = float(row["qty"])
            side.loc[stamp] = str(row["side"])
            commission.loc[stamp] = float(row["fee"])

    traded = qty.abs() > 0
    frame = pd.DataFrame(
        {
            "symbol": symbol,
            "strategy": strategy,
            "target": effective.astype(float),
            "exec_price": exec_price,
            "commission": commission,
            "spread": pd.Series(
                np.where(traded, float(spread_bps), 0.0), index=index, dtype=float
            ),
            "slippage": pd.Series(
                np.where(traded, float(slippage_bps), 0.0), index=index, dtype=float
            ),
            "qty": qty,
            "side": side,
            "equity": bt.equity.astype(float),
            "open": df["open"].reindex(index).astype(float),
            "close": df["close"].reindex(index).astype(float),
            "commission_bps": float(commission_bps),
            "slippage_bps": float(slippage_bps),
            "spread_bps": float(spread_bps),
            "exposure": float(exposure),
        }
    )
    frame.index.name = "date"
    return frame


def export_signals(
    df: pd.DataFrame,
    target: pd.Series,
    bt: BacktestResult,
    out_path: str | Path,
    *,
    symbol: str,
    strategy: str,
    commission_bps: float,
    slippage_bps: float,
    spread_bps: float = 0.0,
    exposure: float = 1.0,
    session: tuple[str, str] | None = None,
    session_tz: str = "UTC",
    flat_dates: Iterable[str] | None = None,
    max_gross: float = 1.0,
    meta: dict | None = None,
) -> SignalExport:
    """Escribe el parquet y un sidecar `.meta.json` con las métricas del motor."""
    frame = build_export(
        df,
        target,
        bt,
        symbol=symbol,
        strategy=strategy,
        commission_bps=commission_bps,
        slippage_bps=slippage_bps,
        spread_bps=spread_bps,
        exposure=exposure,
        session=session,
        session_tz=session_tz,
        flat_dates=flat_dates,
        max_gross=max_gross,
    )
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path)

    meta_path = path.with_suffix(".meta.json")
    payload = {
        "symbol": symbol,
        "strategy": strategy,
        "exposure": float(exposure),
        "commission_bps": float(commission_bps),
        "slippage_bps": float(slippage_bps),
        "spread_bps": float(spread_bps),
        "session": list(session) if session else None,
        "session_tz": session_tz,
        "rows": int(len(frame)),
        "executions": int((frame["qty"].abs() > 0).sum()),
        "engine_metrics": bt.metrics,
        "trade_pnls": [float(value) for value in bt.trade_pnls],
        "trade_returns": [float(value) for value in bt.trade_returns],
        "trade_days": list(bt.trade_days),
        "final_equity": float(bt.equity.iloc[-1]) if len(bt.equity) else 0.0,
    }
    payload.update(meta or {})
    meta_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )

    return SignalExport(
        path=path,
        meta_path=meta_path,
        rows=int(len(frame)),
        executions=payload["executions"],
        symbol=symbol,
        strategy=strategy,
        start=str(frame.index[0]) if len(frame) else "",
        end=str(frame.index[-1]) if len(frame) else "",
    )


__all__ = [
    "SIGNAL_COLUMNS",
    "SignalExport",
    "build_export",
    "effective_target",
    "export_signals",
]
