"""F13: pilot operativo de paper trading.

La decisión de F13 es deliberadamente conservadora: 4-8 semanas con una
estrategia diaria de ~2 trades/año no alcanzan para demostrar edge. Por eso
F13 mide sobre todo **operativa** (ciclos, guard, reconciliación, slippage,
fidelidad de señal) y solo extiende la evaluación de edge a 6 meses o >=20
trades. Nada se activa solo.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import yaml

from .config import DEFAULT_DB, ROOT, Settings
from .db import connect, init_db, utcnow

DEFAULT_CRITERIA: dict = {
    "window_weeks": 8,
    "min_cycles_pct": 0.95,
    "min_reconciliation_ok_pct": 0.95,
    "max_slippage_bps_p50": 10,
    "max_slippage_bps_p95": 25,
    "max_size_error_shares": 1,
    "expected_trades_8w_low": 0,
    "expected_trades_8w_high": 3,
    "edge_extension": "6 meses o >=20 trades",
    "hard_stops": [
        "cualquier breach de guard o kill-switch",
        "cualquier orden no autorizada o intento de live",
        "reconciliación con diferencia no explicada",
        "hash de configuración distinto al congelado",
        "dos ciclos diarios consecutivos perdidos",
    ],
}


def config_files(root: Path = ROOT) -> list[Path]:
    return [
        root / "config" / "lab.yaml",
        root / "config" / "bots.yaml",
        root / "config" / "prop.yaml",
        root / "config" / "f13.yaml",
    ]


def config_hash(root: Path = ROOT) -> str:
    digest = hashlib.sha256()
    for path in config_files(root):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes() if path.exists() else b"")
    return digest.hexdigest()


def load_criteria(root: Path = ROOT) -> dict:
    path = root / "config" / "f13.yaml"
    if not path.exists():
        return dict(DEFAULT_CRITERIA)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    criteria = dict(DEFAULT_CRITERIA)
    criteria.update(data.get("criteria") or {})
    return criteria


def freeze(
    db_path: str | Path,
    *,
    bot: str,
    symbol: str,
    start_date: str,
    root: Path = ROOT,
) -> dict:
    """Congela configuración y criterios. No activa el bot."""
    init_db(db_path)
    criteria = load_criteria(root)
    digest = config_hash(root)
    with connect(db_path) as con:
        con.execute(
            "INSERT OR REPLACE INTO f13_config"
            "(id, bot, symbol, start_date, config_hash, criteria, frozen_at) "
            "VALUES(1, ?, ?, ?, ?, ?, ?)",
            (bot, symbol, start_date, digest, json.dumps(criteria, ensure_ascii=False), utcnow()),
        )
    return status(db_path) or {}


def status(db_path: str | Path) -> dict | None:
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute("SELECT * FROM f13_config WHERE id = 1").fetchone()
    return dict(row) if row else None


def config_check(db_path: str | Path, root: Path = ROOT) -> dict:
    frozen = status(db_path)
    if not frozen:
        return {"ok": True, "status": "not_started", "current": config_hash(root)}
    current = config_hash(root)
    return {
        "ok": current == frozen["config_hash"],
        "status": "ok" if current == frozen["config_hash"] else "changed",
        "frozen": frozen["config_hash"],
        "current": current,
    }


def record_snapshot(
    db_path: str | Path,
    broker,
    *,
    bot: str,
    spy_close: float | None = None,
) -> dict:
    init_db(db_path)
    snap = broker.snapshot({})
    equity = float(snap.get("equity") or 0.0)
    with connect(db_path) as con:
        last = con.execute("SELECT equity FROM f13_metrics ORDER BY id DESC LIMIT 1").fetchone()
        prev = float(last["equity"]) if last else equity
        daily = equity / prev - 1.0 if prev > 0 else 0.0
        peak_row = con.execute("SELECT MAX(equity) AS peak FROM f13_metrics").fetchone()
        peak = max(equity, float(peak_row["peak"] or equity))
        drawdown = equity / peak - 1.0 if peak > 0 else 0.0
        spy_row = con.execute(
            "SELECT spy_close FROM f13_metrics WHERE spy_close IS NOT NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        last_spy = float(spy_row["spy_close"]) if spy_row and spy_row["spy_close"] else None
        spy_return = (
            spy_close / last_spy - 1.0 if spy_close is not None and last_spy and last_spy > 0 else None
        )
        con.execute(
            "INSERT INTO f13_metrics"
            "(ts, trade_date, equity, cash, positions_value, daily_return, drawdown, "
            "spy_close, spy_return, open_positions, trades, notes) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                utcnow(),
                utcnow()[:10],
                equity,
                float(snap.get("cash") or 0.0),
                float(snap.get("positions_value") or 0.0),
                daily,
                drawdown,
                spy_close,
                spy_return,
                len(snap.get("positions") or []),
                0,
                bot,
            ),
        )
    return {"equity": equity, "daily_return": daily, "drawdown": drawdown, "spy_return": spy_return}


def signal_check(
    settings: Settings,
    spec,
    db_path: str | Path = DEFAULT_DB,
) -> dict:
    """Recalcula la señal de hoy y la compara con la última señal registrada."""
    from . import data as data_mod
    from .indicators import atr
    from .strategies import STRATEGIES

    df = data_mod.fetch(
        spec.universe[0],
        (date.today() - timedelta(days=365 * 8)).isoformat(),
        date.today().isoformat(),
        settings.data.cache_dir,
    )
    strategy = STRATEGIES.get(spec.strategy)
    if strategy is None:
        return {"ok": False, "error": f"estrategia desconocida: {spec.strategy}"}
    result = strategy(df, **spec.params)
    target = float(result.target.iloc[-1])
    price = float(df["close"].iloc[-1])

    last_signal = None
    try:
        with connect(db_path) as con:
            row = con.execute(
                "SELECT ts, side, strength FROM signals WHERE bot = ? ORDER BY id DESC LIMIT 1",
                (spec.id,),
            ).fetchone()
        last_signal = dict(row) if row else None
    except Exception:
        last_signal = None

    match = None
    if last_signal and last_signal.get("strength") is not None:
        match = abs(float(last_signal["strength"]) - target) < 1e-6

    return {
        "ok": True,
        "ticker": spec.universe[0],
        "strategy": spec.strategy,
        "target": target,
        "price": price,
        "atr": float(atr(df).iloc[-1]),
        "last_signal": last_signal,
        "match": match,
    }


__all__ = [
    "DEFAULT_CRITERIA",
    "config_check",
    "config_hash",
    "freeze",
    "load_criteria",
    "record_snapshot",
    "signal_check",
    "status",
]
