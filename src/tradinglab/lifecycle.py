"""Ciclo de vida e incubadora: candidato → incubando → evaluado → promovible.

Nunca activa bots ni envía órdenes. La decisión final (promover/rechazar) es
del operador; este módulo solo mide y propone.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import yaml

from .accounts import load_accounts
from .config import ROOT, Settings
from .db import connect, init_db, utcnow

CONFIG_PATH = ROOT / "config" / "lifecycle.yaml"
STATES = ("candidato", "incubando", "evaluado", "promovible", "rechazado", "archivado")
FINAL_STATES = {"promovible", "rechazado", "archivado"}
DRIFT_ORDER = {"ok": 0, "vigilar": 1, "deriva": 2}


class LifecycleError(ValueError):
    pass


def load_config(path: str | Path | None = None) -> dict:
    target = Path(path) if path else CONFIG_PATH
    data: dict = {}
    if target.exists():
        loaded = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        data = loaded if isinstance(loaded, dict) else {}
    gate = data.get("gate") or {}
    criteria = data.get("criteria") or {}
    return {
        "max_concurrent": int(data.get("max_concurrent", 3)),
        "gate": {
            "require_datacheck_ok": bool(gate.get("require_datacheck_ok", True)),
            "min_trades": int(gate.get("min_trades", 10)),
            "min_breakeven_multiple": float(gate.get("min_breakeven_multiple", 1.5)),
            "forbid_catastrophic_regime": bool(
                gate.get("forbid_catastrophic_regime", True)
            ),
        },
        "criteria": {
            "window_weeks": int(criteria.get("window_weeks", 4)),
            "min_trades": int(criteria.get("min_trades", 10)),
            "min_forward_sharpe": float(criteria.get("min_forward_sharpe", 0.5)),
            "max_slippage_bps": float(criteria.get("max_slippage_bps", 10.0)),
            "max_drift_status": str(criteria.get("max_drift_status", "ok")),
            "max_guard_breaches": int(criteria.get("max_guard_breaches", 0)),
        },
        "source": str(target),
    }


def _hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def gate_eligible(evidence: dict, config: dict | None = None) -> dict:
    """Puerta de incubación: solo marca elegible, nunca activa."""
    cfg = (config or load_config())["gate"]
    reasons: list[str] = []
    if cfg["require_datacheck_ok"] and not bool(evidence.get("datacheck_ok")):
        reasons.append("datacheck no ok")
    trades = int(evidence.get("n_trades") or 0)
    if trades < cfg["min_trades"]:
        reasons.append(f"trades {trades} < {cfg['min_trades']}")
    breakeven = evidence.get("breakeven_cost_bps")
    calibrated = evidence.get("calibrated_cost_bps")
    if breakeven is None or calibrated in (None, 0):
        reasons.append("coste de equilibrio sin datos")
    elif float(breakeven) < cfg["min_breakeven_multiple"] * float(calibrated):
        reasons.append(
            f"equilibrio {float(breakeven):.2f} < "
            f"{cfg['min_breakeven_multiple']:.1f}× calibrado {float(calibrated):.2f}"
        )
    if cfg["forbid_catastrophic_regime"] and bool(
        evidence.get("catastrophic_regime")
    ):
        reasons.append("régimen catastrófico")
    return {"eligible": not reasons, "reasons": reasons}


def register_candidate(
    db_path: str | Path,
    *,
    bot: str,
    asset: str,
    evidence: dict | None = None,
    note: str = "",
) -> dict:
    init_db(db_path)
    now = utcnow()
    with connect(db_path) as con:
        cursor = con.execute(
            "INSERT OR IGNORE INTO lifecycle_bots"
            "(bot, asset, state, created_at, updated_at, evidence, note) "
            "VALUES(?,?,?,?,?,?,?)",
            (
                bot,
                asset,
                "candidato",
                now,
                now,
                json.dumps(evidence or {}, ensure_ascii=False, sort_keys=True),
                str(note or "")[:1000],
            ),
        )
        if cursor.rowcount:
            con.execute(
                "INSERT INTO lifecycle_events"
                "(ts, bot, from_state, to_state, actor, reason, criteria_hash) "
                "VALUES(?,?,?,?,?,?,?)",
                (now, bot, None, "candidato", "humano", "registro", None),
            )
        row = con.execute("SELECT * FROM lifecycle_bots WHERE bot = ?", (bot,)).fetchone()
    return dict(row)


def start_incubation(
    db_path: str | Path,
    *,
    bot: str,
    start_date: str | None = None,
    actor: str = "humano",
    reason: str = "",
    config: dict | None = None,
) -> dict:
    cfg = config or load_config()
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute("SELECT * FROM lifecycle_bots WHERE bot = ?", (bot,)).fetchone()
        if row is None:
            raise LifecycleError(f"bot no registrado: {bot}")
        if row["state"] != "candidato":
            raise LifecycleError(f"{bot} está en estado {row['state']}, no candidato")
        incubating = con.execute(
            "SELECT COUNT(*) AS n FROM lifecycle_bots WHERE state = 'incubando'"
        ).fetchone()["n"]
        if int(incubating) >= cfg["max_concurrent"]:
            raise LifecycleError(
                f"límite de incubación alcanzado ({cfg['max_concurrent']})"
            )
        evidence = json.loads(row["evidence"] or "{}")
        gate = gate_eligible(evidence, cfg)
        if not gate["eligible"]:
            raise LifecycleError(
                "no elegible para incubar: " + "; ".join(gate["reasons"])
            )
        start = date.fromisoformat(start_date) if start_date else date.today()
        end = start + timedelta(weeks=int(cfg["criteria"]["window_weeks"]))
        criteria = {
            **cfg["criteria"],
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        }
        digest = _hash(criteria)
        now = utcnow()
        con.execute(
            "UPDATE lifecycle_bots SET state='incubando', updated_at=?, start_date=?, "
            "end_date=?, criteria=?, criteria_hash=?, frozen_at=? WHERE bot=?",
            (
                now,
                start.isoformat(),
                end.isoformat(),
                json.dumps(criteria, ensure_ascii=False, sort_keys=True),
                digest,
                now,
                bot,
            ),
        )
        con.execute(
            "INSERT INTO lifecycle_events"
            "(ts, bot, from_state, to_state, actor, reason, criteria_hash) "
            "VALUES(?,?,?,?,?,?,?)",
            (now, bot, "candidato", "incubando", actor, reason, digest),
        )
        updated = con.execute(
            "SELECT * FROM lifecycle_bots WHERE bot = ?", (bot,)
        ).fetchone()
    return dict(updated)


def _drift_for(db_path: str | Path, bot: str, settings: Settings) -> dict:
    try:
        from .drift import build_drift

        report = build_drift(db_path, settings)
    except Exception:
        return {"status": "sin datos", "reason": "drift no disponible"}
    for row in report.get("bots") or []:
        if row.get("bot") == bot:
            return row
    return {"status": "sin datos", "reason": "bot sin evaluación"}


def _guard_breaches(db_path: str | Path, bot: str, start_date: str) -> int:
    with connect(db_path) as con:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM orders "
            "WHERE bot = ? AND ts >= ? AND status = 'bloqueado'",
            (bot, start_date),
        ).fetchone()
    return int(row["n"])


def report_bot(
    db_path: str | Path,
    bot: str,
    *,
    settings: Settings | None = None,
    today: date | None = None,
) -> dict:
    settings = settings or Settings()
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute("SELECT * FROM lifecycle_bots WHERE bot = ?", (bot,)).fetchone()
    if row is None:
        raise LifecycleError(f"bot no registrado: {bot}")
    data = dict(row)
    start = data.get("start_date")
    end = data.get("end_date")
    if not start or not end:
        return {
            **data,
            "progress_pct": 0.0,
            "days_left": None,
            "metrics": {"n_trades": 0, "sharpe": None, "expectancy": None},
            "slippage_p95_bps": None,
            "drift": {"status": "sin datos"},
            "guard_breaches": 0,
            "proposal": None,
            "failures": ["incubación no iniciada"],
        }
    from .journal import load_closed_trades, summarize
    from .orchestrator import load_bots

    specs = {spec.id: spec for spec in load_bots()}
    spec = specs.get(bot)
    trades, _ = load_closed_trades(
        db_path,
        tz=settings.timezone,
        bots=(
            {bot: {"account": spec.account, "profile": spec.profile}}
            if spec is not None
            else None
        ),
    )
    trades = [trade for trade in trades if trade.bot == bot]
    summary = summarize(trades, load_accounts())
    from .f13 import execution_metrics

    execution = execution_metrics(db_path, bot=bot, start_date=start)
    drift = _drift_for(db_path, bot, settings)
    breaches = _guard_breaches(db_path, bot, start)
    current = today or date.today()
    start_day = date.fromisoformat(start)
    end_day = date.fromisoformat(end)
    total_days = max(1, (end_day - start_day).days)
    elapsed = min(total_days, max(0, (current - start_day).days))
    criteria = json.loads(data.get("criteria") or "{}")
    metrics = {
        "n_trades": int(summary.get("n") or 0),
        "sharpe": summary.get("sharpe"),
        "expectancy": summary.get("expectancy"),
    }
    failures = evaluate_criteria(
        {
            **metrics,
            "slippage_p95_bps": execution.get("slippage_p95_bps"),
            "drift_status": drift.get("status"),
            "guard_breaches": breaches,
        },
        criteria,
    )
    return {
        **data,
        "progress_pct": round(elapsed / total_days * 100, 1),
        "days_left": max(0, (end_day - current).days),
        "metrics": metrics,
        "slippage_p95_bps": execution.get("slippage_p95_bps"),
        "drift": drift,
        "guard_breaches": breaches,
        "proposal": None if current < end_day else ("rechazado" if failures else "promovible"),
        "failures": failures,
        "criteria": criteria,
    }


def evaluate_criteria(metrics: dict, criteria: dict) -> list[str]:
    failures: list[str] = []
    if int(metrics.get("n_trades") or 0) < int(criteria.get("min_trades", 10)):
        failures.append(
            f"trades {int(metrics.get('n_trades') or 0)} < {criteria.get('min_trades')}"
        )
    sharpe = metrics.get("sharpe")
    if sharpe is None or float(sharpe) < float(criteria.get("min_forward_sharpe", 0.5)):
        failures.append(
            f"Sharpe forward {sharpe if sharpe is not None else 'sin datos'} "
            f"< {criteria.get('min_forward_sharpe')}"
        )
    slippage = metrics.get("slippage_p95_bps")
    if slippage is None or float(slippage) > float(
        criteria.get("max_slippage_bps", 10.0)
    ):
        failures.append(
            f"slippage p95 {slippage if slippage is not None else 'sin datos'} "
            f"> {criteria.get('max_slippage_bps')}"
        )
    drift = str(metrics.get("drift_status") or "sin datos")
    max_drift = str(criteria.get("max_drift_status", "ok"))
    if drift == "sin datos":
        failures.append("deriva sin datos")
    elif DRIFT_ORDER.get(drift, 9) > DRIFT_ORDER.get(max_drift, 0):
        failures.append(f"deriva {drift} > {max_drift}")
    if int(metrics.get("guard_breaches") or 0) > int(
        criteria.get("max_guard_breaches", 0)
    ):
        failures.append(
            f"brechas de guard {metrics.get('guard_breaches')} > "
            f"{criteria.get('max_guard_breaches')}"
        )
    return failures


def evaluate_incubation(
    db_path: str | Path,
    bot: str,
    *,
    settings: Settings | None = None,
    today: date | None = None,
) -> dict:
    data = report_bot(db_path, bot, settings=settings, today=today)
    if data.get("state") != "incubando":
        raise LifecycleError(f"{bot} no está incubando")
    if data.get("proposal") is None:
        return data
    proposal = str(data["proposal"])
    evidence = json.loads(data.get("evidence") or "{}")
    evidence.update(
        {
            "proposal": proposal,
            "failures": data.get("failures") or [],
            "metrics": data.get("metrics"),
            "slippage_p95_bps": data.get("slippage_p95_bps"),
            "drift_status": (data.get("drift") or {}).get("status"),
            "guard_breaches": data.get("guard_breaches"),
        }
    )
    now = utcnow()
    with connect(db_path) as con:
        con.execute(
            "UPDATE lifecycle_bots SET state='evaluado', updated_at=?, evidence=? "
            "WHERE bot=?",
            (now, json.dumps(evidence, ensure_ascii=False, sort_keys=True), bot),
        )
        con.execute(
            "INSERT INTO lifecycle_events"
            "(ts, bot, from_state, to_state, actor, reason, criteria_hash) "
            "VALUES(?,?,?,?,?,?,?)",
            (
                now,
                bot,
                "incubando",
                "evaluado",
                "sistema",
                f"propuesta: {proposal}",
                data.get("criteria_hash"),
            ),
        )
    return report_bot(db_path, bot, settings=settings, today=today)


def set_final_state(
    db_path: str | Path,
    bot: str,
    state: str,
    *,
    actor: str = "humano",
    reason: str = "",
) -> dict:
    if state not in {"promovible", "rechazado", "archivado"}:
        raise LifecycleError(f"estado final inválido: {state}")
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute("SELECT * FROM lifecycle_bots WHERE bot = ?", (bot,)).fetchone()
        if row is None:
            raise LifecycleError(f"bot no registrado: {bot}")
        if row["state"] not in {"evaluado", "promovible", "rechazado"}:
            raise LifecycleError(
                f"{bot} está en {row['state']}; evalúa la incubación primero"
            )
        now = utcnow()
        con.execute(
            "UPDATE lifecycle_bots SET state=?, updated_at=?, note=? WHERE bot=?",
            (state, now, str(reason or row["note"] or "")[:1000], bot),
        )
        con.execute(
            "INSERT INTO lifecycle_events"
            "(ts, bot, from_state, to_state, actor, reason, criteria_hash) "
            "VALUES(?,?,?,?,?,?,?)",
            (now, bot, row["state"], state, actor, reason, row["criteria_hash"]),
        )
        updated = con.execute(
            "SELECT * FROM lifecycle_bots WHERE bot = ?", (bot,)
        ).fetchone()
    return dict(updated)


def status(db_path: str | Path, *, settings: Settings | None = None) -> list[dict]:
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute("SELECT * FROM lifecycle_bots ORDER BY bot").fetchall()
    out = []
    for row in rows:
        try:
            out.append(report_bot(db_path, row["bot"], settings=settings))
        except Exception:
            out.append(dict(row))
    return out


def events(db_path: str | Path, *, limit: int = 50) -> list[dict]:
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT * FROM lifecycle_events ORDER BY id DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
    return [dict(row) for row in rows]


__all__ = [
    "CONFIG_PATH",
    "FINAL_STATES",
    "LifecycleError",
    "STATES",
    "evaluate_criteria",
    "evaluate_incubation",
    "events",
    "gate_eligible",
    "load_config",
    "register_candidate",
    "report_bot",
    "set_final_state",
    "start_incubation",
    "status",
]
