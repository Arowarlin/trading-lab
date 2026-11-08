"""F13: pilot operativo de paper trading.

La decisión de F13 es deliberadamente conservadora: 4-8 semanas con una
estrategia diaria de ~2 trades/año no alcanzan para demostrar edge. Por eso
F13 mide sobre todo **operativa** (ciclos, guard, reconciliación, slippage,
fidelidad de señal) y solo extiende la evaluación de edge a 6 meses o >=20
trades. Nada se activa solo.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import date, timedelta
from pathlib import Path

import yaml

from .config import DEFAULT_DB, ROOT, Settings, get_settings
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


def _set_bot_enabled(root: Path, bot: str, enabled: bool) -> None:
    """Edita solo la línea enabled del bot, preservando el resto del YAML."""
    path = root / "config" / "bots.yaml"
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    start = None
    for index, line in enumerate(lines):
        if re.match(rf"^\s*-\s+id:\s*['\"]?{re.escape(bot)}['\"]?\s*$", line):
            start = index
            break
    if start is None:
        raise ValueError(f"Bot no encontrado en bots.yaml: {bot}")
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if re.match(r"^[^\s#]", lines[index]):
            end = index
            break
        if re.match(r"^\s*-\s+id:\s*", lines[index]):
            end = index
            break
    changed = False
    for index in range(start, end):
        match = re.match(
            r"^(\s*)enabled:\s*(true|false)\s*(#.*)?$",
            lines[index],
            flags=re.IGNORECASE,
        )
        if not match:
            continue
        indent = match.group(1)
        comment = match.group(3)
        newline = "\n" if lines[index].endswith("\n") else ""
        suffix = f" {comment.strip()}" if comment else ""
        lines[index] = (
            f"{indent}enabled: {'true' if enabled else 'false'}{suffix}{newline}"
        )
        changed = True
        break
    if not changed:
        raise ValueError(f"No encuentro enabled: en el bloque de {bot}")
    new_text = "".join(lines)
    old_data = yaml.safe_load(text) or {}
    new_data = yaml.safe_load(new_text) or {}
    expected = copy.deepcopy(old_data)
    for item in expected.get("bots", []):
        if item.get("id") == bot:
            item["enabled"] = bool(enabled)
    if new_data != expected:
        raise ValueError("La edición de bots.yaml cambió más de lo previsto.")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(new_text, encoding="utf-8")
    tmp.replace(path)


def activate(
    db_path: str | Path,
    *,
    bot: str,
    root: Path = ROOT,
    settings: Settings | None = None,
) -> dict:
    """Activa el bot F13 en paper y re-congela el hash. No live, no órdenes."""
    init_db(db_path)
    frozen = status(db_path)
    if not frozen:
        raise ValueError("F13 no está congelado.")
    if str(frozen.get("bot")) != bot:
        raise ValueError(
            f"F13 está congelado para {frozen.get('bot')}, no para {bot}."
        )
    mode = (settings or get_settings()).mode
    if mode != "paper":
        raise ValueError("F13 solo se activa en paper; mode=live está bloqueado.")
    check = config_check(db_path, root)
    if not check["ok"]:
        raise ValueError("El hash congelado no coincide con la configuración actual.")
    bots_path = root / "config" / "bots.yaml"
    if not bots_path.exists():
        raise ValueError("No existe config/bots.yaml.")
    original = bots_path.read_text(encoding="utf-8")
    data = yaml.safe_load(original) or {}
    spec = next(
        (item for item in data.get("bots", []) if item.get("id") == bot),
        None,
    )
    if spec is None:
        raise ValueError(f"Bot no encontrado: {bot}")
    if bool(spec.get("enabled")):
        raise ValueError(f"{bot} ya está enabled:true.")

    _set_bot_enabled(root, bot, True)
    try:
        row = freeze(
            db_path,
            bot=bot,
            symbol=str(frozen.get("symbol") or "QQQ"),
            start_date=str(frozen.get("start_date")),
            root=root,
        )
    except Exception:
        bots_path.write_text(original, encoding="utf-8")
        raise

    try:
        from .runtime import set_bot_enabled

        set_bot_enabled(
            db_path,
            bot=bot,
            enabled=True,
            yaml_enabled=True,
            actor="f13-activate",
            reason="activación F13 en paper",
        )
    except Exception:
        pass
    try:
        from .runtime import record_console_action

        record_console_action(
            db_path,
            action="f13_activate",
            params={"bot": bot, "start_date": row.get("start_date")},
            result="activado",
            ok=True,
            actor="cli",
            detail="re-congelado con enabled:true; paper",
        )
    except Exception:
        pass
    return row


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


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
    return ordered[index]


def execution_metrics(
    db_path: str | Path,
    *,
    bot: str,
    start_date: str,
) -> dict:
    """Slippage real vs señal y error de tamaño vs orden."""
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT o.id, o.ts, o.ticker, o.side, o.qty, o.bot, f.price AS fill_price, f.qty AS fill_qty "
            "FROM orders o JOIN fills f ON f.order_id = o.id "
            "WHERE o.bot = ? AND o.ts >= ? ORDER BY o.id",
            (bot, start_date),
        ).fetchall()
        metrics = []
        for row in rows:
            signal = con.execute(
                "SELECT price FROM signals WHERE ticker = ? AND bot = ? AND ts <= ? "
                "ORDER BY id DESC LIMIT 1",
                (row["ticker"], bot, row["ts"]),
            ).fetchone()
            if not signal or not signal["price"] or not row["fill_price"]:
                continue
            sign = 1.0 if row["side"].lower() == "buy" else -1.0
            slippage = (float(row["fill_price"]) / float(signal["price"]) - 1.0) * 10_000 * sign
            metrics.append(
                {
                    "ticker": row["ticker"],
                    "slippage_bps": slippage,
                    "size_error": abs(float(row["fill_qty"]) - float(row["qty"])),
                }
            )
    values = [m["slippage_bps"] for m in metrics]
    return {
        "fills": len(metrics),
        "slippage_p50_bps": _percentile(values, 0.50),
        "slippage_p95_bps": _percentile(values, 0.95),
        "size_error_max": max((m["size_error"] for m in metrics), default=0.0),
    }


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
    "activate",
    "config_check",
    "config_hash",
    "execution_metrics",
    "freeze",
    "load_criteria",
    "record_snapshot",
    "signal_check",
    "status",
]
