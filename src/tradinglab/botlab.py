"""Ciclo de vida de bots: proponer, evaluar y archivar (sin borrar).

Un bot archivado no se ejecuta y conserva su historial. Nada se activa solo:
`propose` crea `enabled: false`; `archive` solo desactiva.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from .backtest import run as run_backtest
from .config import ROOT, Settings
from .db import connect, init_db, utcnow
from .orchestrator import BotSpec, load_bots
from .strategies import STRATEGIES

PROPOSED_FILE = ROOT / "config" / "bots_proposed.yaml"
ARCHIVE_FILE = ROOT / "config" / "bots_archive.yaml"


def load_proposed(path: Path | None = None) -> list[BotSpec]:
    path = path or PROPOSED_FILE
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    specs = []
    for item in raw.get("bots", []):
        specs.append(
            BotSpec(
                id=item["id"],
                type=item.get("type", "deterministic"),
                strategy=item["strategy"],
                universe=[t.upper() for t in item.get("universe", [])],
                timeframe=item.get("timeframe", "1d"),
                enabled=False,
                params=item.get("params", {}) or {},
                description=item.get("description", ""),
                exposure=float(item.get("exposure", 1.0)),
            )
        )
    return specs


def propose_bot(
    *,
    id: str,
    strategy: str,
    universe: list[str],
    params: dict | None = None,
    exposure: float = 1.0,
    description: str = "",
) -> BotSpec:
    if strategy not in STRATEGIES:
        raise ValueError(f"estrategia desconocida: {strategy}")
    if not id or not id.replace("-", "").replace("_", "").isalnum():
        raise ValueError("id inválido: usa letras, números, guion o guion bajo")
    if not universe:
        raise ValueError("el universo no puede estar vacío")
    existing = {spec.id for spec in load_bots()} | {spec.id for spec in load_proposed()}
    if id in existing:
        raise ValueError(f"ya existe un bot con id {id}")

    spec = BotSpec(
        id=id,
        type="deterministic",
        strategy=strategy,
        universe=[t.upper() for t in universe],
        enabled=False,
        params=params or {},
        description=description,
        exposure=max(0.0, min(float(exposure), 1.0)),
    )
    path = PROPOSED_FILE
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    raw = raw or {}
    bots = list(raw.get("bots", []))
    bots.append(
        {
            "id": spec.id,
            "type": spec.type,
            "strategy": spec.strategy,
            "universe": spec.universe,
            "timeframe": spec.timeframe,
            "enabled": False,
            "exposure": spec.exposure,
            "params": spec.params,
            "description": spec.description,
        }
    )
    raw["bots"] = bots
    path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return spec


def load_archive(path: Path | None = None) -> set[str]:
    path = path or ARCHIVE_FILE
    if not path.exists():
        return set()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(x) for x in raw.get("archived", [])}


def _write_archive(ids: set[str], path: Path | None = None) -> None:
    path = path or ARCHIVE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump({"archived": sorted(ids)}, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def archive_bot(bot: str, reason: str = "") -> list[str]:
    ids = load_archive()
    ids.add(bot)
    _write_archive(ids)
    meta_path = ROOT / "config" / "bots_archive_reasons.yaml"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    meta = meta or {}
    meta[bot] = {"reason": reason[:500], "archived_at": utcnow()}
    meta_path.write_text(yaml.safe_dump(meta, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return sorted(ids)


def restore_bot(bot: str) -> list[str]:
    ids = load_archive()
    ids.discard(bot)
    _write_archive(ids)
    return sorted(ids)


def _metrics_for(spec: BotSpec, settings: Settings, start: str) -> dict:
    if spec.type != "deterministic":
        return {
            "status": "no_evaluable",
            "details": f"tipo {spec.type}: sin backtest determinista",
            "num_trades": 0,
        }
    strategy = STRATEGIES.get(spec.strategy)
    if strategy is None:
        return {"status": "no_evaluable", "details": "estrategia desconocida", "num_trades": 0}

    per_ticker = []
    errors = []
    from . import data as data_mod

    for ticker in spec.universe:
        try:
            df = data_mod.fetch(ticker, start, utcnow()[:10], settings.data.cache_dir)
            result = strategy(df, **spec.params)
            bt = run_backtest(
                df,
                result.target,
                starting_cash=settings.starting_cash,
                commission_bps=settings.execution.commission_bps,
                slippage_bps=settings.execution.slippage_bps,
                max_gross=spec.exposure,
            )
            per_ticker.append({"ticker": ticker, **bt.metrics})
        except Exception as exc:
            errors.append(f"{ticker}: {exc}")

    if not per_ticker:
        return {
            "status": "no_evaluable",
            "details": "; ".join(errors)[:500] or "sin datos",
            "num_trades": 0,
        }

    n = len(per_ticker)
    total_return = sum(float(x["total_return"]) for x in per_ticker) / n
    sharpe = sum(float(x["sharpe"]) for x in per_ticker) / n
    max_dd = min(float(x["max_drawdown"]) for x in per_ticker)
    trades = sum(int(x["num_trades"]) for x in per_ticker)
    win_rate = sum(float(x["win_rate"]) for x in per_ticker) / n
    expectancy = (
        sum(float(x.get("expectancy") or 0.0) * int(x.get("num_trades") or 0) for x in per_ticker)
        / trades
        if trades
        else None
    )

    if trades < 15:
        status = "muestra_insuficiente"
    elif sharpe <= 0 or total_return <= 0 or max_dd <= -0.20:
        status = "archivar"
    else:
        status = "mantener"

    return {
        "status": status,
        "total_return": round(total_return, 6),
        "sharpe": round(sharpe, 4),
        "max_drawdown": round(max_dd, 6),
        "num_trades": trades,
        "win_rate": round(win_rate, 4),
        "expectancy": round(expectancy, 4) if expectancy is not None else None,
        "details": json.dumps(per_ticker, ensure_ascii=False)[:4000],
    }


def evaluate_all(
    settings: Settings,
    db_path: str | Path,
    *,
    start: str = "2015-01-01",
    include_proposed: bool = True,
) -> list[dict]:
    init_db(db_path)
    specs = load_bots() + (load_proposed() if include_proposed else [])
    results: list[dict] = []
    for spec in specs:
        metrics = _metrics_for(spec, settings, start)
        row = {
            "bot": spec.id,
            "strategy": spec.strategy,
            "universe": ",".join(spec.universe),
            "params": json.dumps(spec.params, ensure_ascii=False),
            "exposure": spec.exposure,
            "status": metrics["status"],
            **{k: metrics.get(k) for k in ("total_return", "sharpe", "max_drawdown", "num_trades", "win_rate", "expectancy")},
            "details": metrics.get("details", ""),
        }
        with connect(db_path) as con:
            con.execute(
                "INSERT INTO bot_evaluations"
                "(ts, bot, strategy, universe, params, exposure, start_date, end_date, "
                "total_return, sharpe, max_drawdown, num_trades, win_rate, expectancy, status, details) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    utcnow(),
                    row["bot"],
                    row["strategy"],
                    row["universe"],
                    row["params"],
                    row["exposure"],
                    start,
                    utcnow()[:10],
                    row.get("total_return"),
                    row.get("sharpe"),
                    row.get("max_drawdown"),
                    row.get("num_trades"),
                    row.get("win_rate"),
                    row.get("expectancy"),
                    row["status"],
                    row["details"],
                ),
            )
        results.append(row)
    return results


def latest_evaluations(db_path: str | Path) -> dict[str, dict]:
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT * FROM bot_evaluations e WHERE id = "
            "(SELECT MAX(id) FROM bot_evaluations x WHERE x.bot = e.bot)"
        ).fetchall()
    return {row["bot"]: dict(row) for row in rows}


__all__ = [
    "archive_bot",
    "evaluate_all",
    "latest_evaluations",
    "load_archive",
    "load_proposed",
    "propose_bot",
    "restore_bot",
]
