"""Control cruzado MT5 H1 vs ticks Dukascopy agregados a H1.

Solo lectura. Si faltan ticks, el resultado es ``Sin datos``; no se rellena con
otra fuente. El informe queda en ``reports/data/crosscheck``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ..config import ROOT, get_settings
from ..intraday import load_bars

DEFAULT_OUT = ROOT / "reports" / "data" / "crosscheck"
TICKS_DIR = ROOT / "data" / "cache" / "ticks"


def _utc_index(frame: pd.DataFrame, column: str = "ts") -> pd.DataFrame:
    data = frame.copy()
    if column in data.columns:
        data[column] = pd.to_datetime(data[column], utc=True, errors="coerce")
        data = data.dropna(subset=[column]).set_index(column)
    else:
        data.index = pd.to_datetime(data.index, utc=True)
    return data.sort_index()


def ticks_to_h1(ticks: pd.DataFrame) -> pd.DataFrame:
    data = _utc_index(ticks)
    if not {"bid", "ask"}.issubset(data.columns):
        raise ValueError("ticks sin bid/ask")
    mid = (
        pd.to_numeric(data["bid"], errors="coerce")
        + pd.to_numeric(data["ask"], errors="coerce")
    ) / 2.0
    mid = mid.dropna()
    if mid.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close"])
    h1 = mid.resample("1h").agg(["first", "max", "min", "last"]).dropna()
    h1.columns = ["open", "high", "low", "close"]
    return h1


def compare_frames(
    mt5: pd.DataFrame,
    ticks: pd.DataFrame,
    *,
    threshold: float = 3.0,
) -> dict:
    """Compara retornos 1h/1d y marca |z| > threshold."""
    left = _utc_index(mt5)
    if "close" not in left.columns:
        raise ValueError("MT5 sin close")
    right = ticks_to_h1(ticks)
    if right.empty:
        return {"status": "Sin datos", "reason": "sin ticks Dukascopy"}
    joined = pd.concat(
        {
            "mt5": pd.to_numeric(left["close"], errors="coerce"),
            "duk": pd.to_numeric(right["close"], errors="coerce"),
        },
        axis=1,
        join="inner",
    ).dropna()
    if len(joined) < 10:
        return {"status": "Sin datos", "reason": "menos de 10 horas alineadas"}
    returns = joined.pct_change().dropna()
    diff = returns["mt5"] - returns["duk"]
    std = float(diff.std(ddof=1)) if len(diff) > 1 else 0.0
    z = diff / std if std > 0 else diff * 0.0
    divergences = [
        {
            "ts": str(stamp),
            "z": round(float(z.loc[stamp]), 3),
            "diff": round(float(diff.loc[stamp]), 8),
        }
        for stamp in diff.index
        if abs(float(z.loc[stamp])) > float(threshold)
    ]
    daily = joined.resample("1D").last().pct_change().dropna()
    daily_diff = (
        daily["mt5"] - daily["duk"]
        if {"mt5", "duk"}.issubset(daily.columns)
        else pd.Series(dtype=float)
    )
    return {
        "status": "ok",
        "n_hours": int(len(returns)),
        "corr_1h": round(float(returns["mt5"].corr(returns["duk"])), 4),
        "corr_1d": (
            round(float(daily["mt5"].corr(daily["duk"])), 4)
            if len(daily) >= 3 else None
        ),
        "mean_diff_1h": round(float(diff.mean()), 8),
        "std_diff_1h": round(std, 8),
        "n_divergences": len(divergences),
        "divergences": divergences[:200],
        "daily": [
            {
                "date": str(pd.Timestamp(stamp).date()),
                "diff_1d": round(float(value), 8),
            }
            for stamp, value in daily_diff.items()
        ],
    }


def _tick_files(symbol: str, ticks_dir: str | Path) -> list[Path]:
    root = Path(ticks_dir)
    if not root.exists():
        return []
    return sorted(root.glob(f"{str(symbol).upper()}_*.parquet"))


def crosscheck_symbol(
    symbol: str,
    *,
    cache_dir: str | Path | None = None,
    ticks_dir: str | Path | None = None,
    out_dir: str | Path | None = None,
    threshold: float = 3.0,
) -> dict:
    settings = get_settings()
    cache = Path(cache_dir) if cache_dir else settings.data.cache_dir
    try:
        mt5 = load_bars(cache, symbol, "H1")
    except (FileNotFoundError, OSError, ValueError):
        return {"symbol": str(symbol).upper(), "status": "Sin datos", "reason": "sin caché MT5 H1"}
    files = _tick_files(symbol, ticks_dir or TICKS_DIR)
    if not files:
        return {
            "symbol": str(symbol).upper(), "status": "Sin datos",
            "reason": "sin ticks Dukascopy",
        }
    frames = []
    for path in files:
        try:
            frames.append(pd.read_parquet(path))
        except OSError:
            continue
    if not frames:
        return {
            "symbol": str(symbol).upper(), "status": "Sin datos",
            "reason": "ticks ilegibles",
        }
    ticks = pd.concat(frames, ignore_index=True)
    result = compare_frames(mt5, ticks, threshold=threshold)
    result["symbol"] = str(symbol).upper()
    result["tick_files"] = len(files)
    target = Path(out_dir) if out_dir else DEFAULT_OUT
    target.mkdir(parents=True, exist_ok=True)
    (target / f"{str(symbol).upper()}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        f"# Crosscheck {str(symbol).upper()}",
        f"- Estado: {result.get('status')}",
    ]
    if result.get("status") == "ok":
        lines += [
            f"- Horas alineadas: {result['n_hours']}",
            f"- Correlación 1h: {result['corr_1h']}",
            f"- Correlación 1d: {result['corr_1d']}",
            f"- Divergencias >{threshold}σ: {result['n_divergences']}",
            "",
            "| Hora | z | diferencia |",
            "|---|---:|---:|",
        ]
        for row in result["divergences"]:
            lines.append(f"| {row['ts']} | {row['z']} | {row['diff']} |")
    else:
        lines.append(f"- Motivo: {result.get('reason')}")
    (target / f"{str(symbol).upper()}.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    return result


def latest_correlation(
    symbol: str,
    *,
    out_dir: str | Path | None = None,
) -> float | None:
    target = Path(out_dir) if out_dir else DEFAULT_OUT
    path = target / f"{str(symbol).upper()}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    value = data.get("corr_1h")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


__all__ = [
    "DEFAULT_OUT",
    "TICKS_DIR",
    "compare_frames",
    "crosscheck_symbol",
    "latest_correlation",
    "ticks_to_h1",
]
