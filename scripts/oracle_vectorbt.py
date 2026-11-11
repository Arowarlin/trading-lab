"""Oráculo externo del motor de backtest con vectorbt.

Se ejecuta con el venv de herramientas externas:

    .venv-vbt\\Scripts\\python.exe scripts\\oracle_vectorbt.py ^
        --signals reports/research/oracles/signals_qqq-trend-f13.parquet ^
        --bot qqq-trend-f13

No modifica el motor: lee el parquet exportado por `lab backtest
--export-signals` y recomputa la curva de equity con vectorbt a partir de las
mismas primitivas (ejecución en la apertura siguiente, comisión por operación,
slippage ya aplicado en el precio de ejecución).

Salida: `reports/research/oracles/vectorbt_<bot>.json` y `.md`.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

CACHE_DIR = Path("data/cache")
MT5_CACHE = CACHE_DIR / "mt5"
OUT_DIR = Path("reports/research/oracles")
DIFF_THRESHOLD = 0.001  # 0,1 % del capital


def load_bars(
    symbol: str, timeframe: str, index: pd.Index | None = None
) -> pd.DataFrame | None:
    """Barras de la caché local; elige el fichero con más barras comunes."""
    if timeframe.upper() in {"1D", "1DAILY"}:
        candidates = sorted(CACHE_DIR.glob(f"{symbol.upper()}*.parquet"))
    else:
        path = MT5_CACHE / f"{symbol.upper()}_{timeframe.upper()}.parquet"
        candidates = [path] if path.exists() else []
    best: pd.DataFrame | None = None
    best_overlap = -1
    for path in candidates:
        try:
            frame = pd.read_parquet(path)
        except Exception:
            continue
        if not {"open", "close"} <= set(frame.columns):
            continue
        if index is None:
            return frame
        overlap = len(frame.index.intersection(index))
        if overlap > best_overlap:
            best = frame
            best_overlap = overlap
    return best


def split_orders(rows: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Convierte las ejecuciones del motor en órdenes de vectorbt.

    El motor puede girar de largo a corto en una sola barra; vectorbt necesita
    dos órdenes (cerrar y abrir). Aquí se hace esa separación explícita para no
    inventar exposición.
    """
    size = np.full(len(rows), np.nan)
    price = np.full(len(rows), np.nan)
    position = 0.0
    for index, row in enumerate(rows.itertuples()):
        qty = float(row.qty)
        if qty == 0.0:
            continue
        delta = qty if str(row.side) == "buy" else -qty
        fill = float(row.exec_price)
        if position != 0.0 and (position > 0) != (delta > 0):
            closing = min(abs(delta), abs(position))
            size[index] = -math.copysign(closing, position)
            price[index] = fill
            position += size[index]
            remainder = abs(delta) - closing
            if remainder > 0:
                size[index] = size[index] + math.copysign(remainder, delta)
                position += math.copysign(remainder, delta)
        else:
            size[index] = delta
            price[index] = fill
            position += delta
    return size, price, np.array([position])


def engine_operations(rows: pd.DataFrame, init_cash: float) -> list[dict]:
    """Re-deriva las operaciones realizadas del motor desde las primitivas.

    El motor solo realiza PnL cuando la ejecución **reduce** la posición; una
    orden que aumenta la posición no es una operación. Se recalcula aquí con
    las mismas reglas contables para alinear con los trades de vectorbt.
    """
    shares = 0.0
    avg_cost = 0.0
    operations: list[dict] = []
    for row in rows.itertuples():
        qty = float(row.qty)
        if qty == 0.0:
            continue
        delta = qty if str(row.side) == "buy" else -qty
        fill = float(row.exec_price)
        fee = float(row.commission)
        if shares != 0.0 and (shares > 0) != (delta > 0):
            closing = min(abs(delta), abs(shares))
            if shares > 0:
                pnl = (fill - avg_cost) * closing
                trade_return = (fill - avg_cost) / avg_cost if avg_cost > 0 else 0.0
            else:
                pnl = (avg_cost - fill) * closing
                trade_return = (avg_cost - fill) / avg_cost if avg_cost > 0 else 0.0
            operations.append(
                {
                    "ts": row.Index,
                    "pnl": pnl - fee,
                    "return": trade_return,
                }
            )
        new_shares = shares + delta
        if abs(new_shares) < 1e-9:
            new_shares = 0.0
            avg_cost = 0.0
        elif shares == 0.0 or (shares > 0) == (delta > 0):
            avg_cost = (abs(shares) * avg_cost + abs(delta) * fill) / abs(new_shares)
        elif (shares > 0) != (new_shares > 0):
            avg_cost = fill
        shares = new_shares
    return operations


def run_oracle(signals_path: Path, bot: str, out_dir: Path) -> dict:
    import vectorbt as vbt

    frame = pd.read_parquet(signals_path)
    meta_path = signals_path.with_suffix(".meta.json")
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    symbol = str(meta.get("symbol") or frame["symbol"].iloc[0])
    timeframe = "1d"
    if "M15" in str(meta.get("strategy") or ""):
        timeframe = "M15"

    size, price, final_position = split_orders(frame)
    close = frame["close"].astype(float)
    commission_bps = float(frame["commission_bps"].iloc[0])
    init_cash = float(meta.get("init_cash") or 100_000.0)

    portfolio = vbt.Portfolio.from_orders(
        close=close,
        size=size,
        price=price,
        fees=commission_bps / 10_000.0,
        direction="both",
        init_cash=init_cash,
        size_type="amount",
        cash_sharing=False,
        group_by=False,
        freq="1D" if timeframe == "1d" else "15min",
    )

    value = portfolio.value()
    engine_equity = frame["equity"].astype(float)
    trades = portfolio.trades
    vbt_trades = trades.records_readable if len(trades) else None

    vbt_pnls: list[float] = []
    vbt_exits: list[pd.Timestamp] = []
    if vbt_trades is not None:
        vbt_pnls = [float(value) for value in vbt_trades["PnL"].to_numpy()]
        vbt_exits = [pd.Timestamp(value) for value in vbt_trades["Exit Timestamp"]]

    operations = engine_operations(frame, init_cash)
    vbt_by_exit: dict[pd.Timestamp, float] = {}
    for stamp, pnl in zip(vbt_exits, vbt_pnls):
        vbt_by_exit[stamp] = vbt_by_exit.get(stamp, 0.0) + pnl

    aligned = 0
    unmatched = 0
    diffs: list[float] = []
    for operation in operations:
        stamp = pd.Timestamp(operation["ts"])
        if stamp in vbt_by_exit:
            aligned += 1
            diffs.append((vbt_by_exit[stamp] - operation["pnl"]) / init_cash)
        else:
            unmatched += 1
    big = [abs(value) for value in diffs if abs(value) > DIFF_THRESHOLD]

    engine_total = float(engine_equity.iloc[-1]) - init_cash
    vbt_total = float(value.iloc[-1]) - init_cash
    engine_dd = float((engine_equity / engine_equity.cummax() - 1.0).min())
    vbt_dd = float((value / value.cummax() - 1.0).min())

    bars = load_bars(symbol, timeframe, frame.index)
    bars_check = "sin datos"
    if bars is not None:
        try:
            cached = bars["close"].astype(float)
            common = cached.index.intersection(frame.index)
            if len(common):
                diff = float(
                    (cached.reindex(common) - frame["close"].reindex(common)).abs().max()
                )
                bars_check = f"{len(common)} barras comunes, diff máx {diff:.2e}"
        except Exception as exc:  # pragma: no cover - solo informe
            bars_check = f"error: {exc}"

    result = {
        "bot": bot,
        "symbol": symbol,
        "timeframe": timeframe,
        "signals": str(signals_path),
        "vectorbt_version": vbt.__version__,
        "rows": int(len(frame)),
        "engine": {
            "operations": int((meta.get("engine_metrics") or {}).get("num_trades", 0)),
            "operations_rederived": len(operations),
            "executions": int((frame["qty"].abs() > 0).sum()),
            "final_equity": float(engine_equity.iloc[-1]),
            "total_pnl": engine_total,
            "max_drawdown": engine_dd,
        },
        "vectorbt": {
            "operations": int(len(vbt_pnls)),
            "orders": int(portfolio.orders.count()),
            "final_equity": float(value.iloc[-1]),
            "total_pnl": vbt_total,
            "max_drawdown": vbt_dd,
            "final_position": float(final_position[-1]) if len(final_position) else 0.0,
        },
        "difference": {
            "operations_compared": aligned,
            "operations_unmatched": unmatched,
            "max_abs_diff_pct": float(max((abs(v) for v in diffs), default=0.0)),
            "mean_abs_diff_pct": float(
                sum(abs(v) for v in diffs) / len(diffs) if diffs else 0.0
            ),
            "operations_over_threshold": len(big),
            "threshold_pct": DIFF_THRESHOLD,
        },
        "bars_check": bars_check,
    }
    result["match"] = (
        result["engine"]["operations"] == result["engine"]["operations_rederived"]
        and unmatched == 0
        and len(big) == 0
        and abs(engine_total - vbt_total) / init_cash <= DIFF_THRESHOLD
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"vectorbt_{bot}.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    curve = pd.DataFrame(
        {
            "engine": engine_equity,
            "vectorbt": value.reindex(engine_equity.index).ffill().bfill(),
        }
    )
    curve.to_csv(out_dir / f"vectorbt_{bot}_equity.csv", encoding="utf-8")

    lines = [
        f"# Oráculo vectorbt · {bot}",
        "",
        f"- Símbolo: {symbol} · timeframe {timeframe} · barras {len(frame)}",
        f"- vectorbt {vbt.__version__} (venv externo `.venv-vbt`)",
        f"- Señales: `{signals_path}`",
        f"- Comprobación contra la caché local: {bars_check}",
        "",
        "## Resultado",
        "",
        "| Métrica | Motor propio | vectorbt |",
        "|---|---:|---:|",
        f"| Operaciones cerradas | {result['engine']['operations']} | {result['vectorbt']['operations']} |",
        f"| Órdenes | {result['engine']['executions']} | {result['vectorbt']['orders']} |",
        f"| Equity final | {result['engine']['final_equity']:,.2f} | {result['vectorbt']['final_equity']:,.2f} |",
        f"| PnL total | {result['engine']['total_pnl']:,.2f} | {result['vectorbt']['total_pnl']:,.2f} |",
        f"| Max drawdown | {result['engine']['max_drawdown']:.2%} | {result['vectorbt']['max_drawdown']:.2%} |",
        "",
        "## Diferencias por operación",
        "",
        f"- Operaciones del motor: **{result['engine']['operations']}** "
        f"(re-derivadas del parquet: {result['engine']['operations_rederived']})",
        f"- Operaciones de vectorbt: **{result['vectorbt']['operations']}**",
        f"- Alineadas por marca de salida: **{aligned}** · sin pareja: **{unmatched}**",
        f"- Diferencia máxima: **{result['difference']['max_abs_diff_pct']:.4%}** del capital",
        f"- Diferencia media: **{result['difference']['mean_abs_diff_pct']:.4%}**",
        f"- Operaciones con diferencia > {DIFF_THRESHOLD:.1%}: "
        f"**{result['difference']['operations_over_threshold']}**",
        "",
        f"- Veredicto: **{'coincide' if result['match'] else 'difiere'}**",
        "",
        "### Causa probable del conteo",
        "",
        "El motor solo realiza PnL cuando una ejecución **reduce** la posición; "
        "una orden que aumenta la posición ya abierta no cuenta como operación. "
        "vectorbt registra un trade por cada orden que toca una posición, "
        "incluidas las que solo la amplían. Por eso vectorbt puede mostrar más "
        "operaciones que el motor con las mismas ejecuciones. El PnL total y la "
        "curva de equity sí se comparan 1 a 1.",
        "",
        "## Curva de equity",
        "",
        "CSV con las dos curvas (engine y vectorbt).",
        "",
        "```",
        f"vectorbt_{bot}_equity.csv",
        "```",
        "",
    ]
    (out_dir / f"vectorbt_{bot}.md").write_text("\n".join(lines), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Oráculo vectorbt del backtester")
    parser.add_argument("--signals", required=True, help="Parquet exportado")
    parser.add_argument("--bot", required=True, help="Nombre del bot para el informe")
    parser.add_argument("--out", default=str(OUT_DIR), help="Carpeta de salida")
    args = parser.parse_args()
    result = run_oracle(Path(args.signals), args.bot, Path(args.out))
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
