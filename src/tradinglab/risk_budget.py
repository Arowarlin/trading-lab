"""Riesgo neto por activo, clúster USD, rebanadas por bot y apagón de noticias."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from .config import ROOT
from .db import connect, init_db, utcnow

BUDGET_PATH = ROOT / "config" / "risk_budget.yaml"
USD_KEYWORDS = (
    "CPI",
    "NFP",
    "FOMC",
    "PCE",
    "GDP",
    "FED",
    "POWELL",
    "UNEMPLOYMENT",
    "RETAIL SALES",
    "ISM",
    "TREASURY",
)
JPY_KEYWORDS = ("BOJ", "BANK OF JAPAN", "JAPAN", "TOKYO", "JPY")
ASSET_CURRENCIES = {
    "EURUSD": ("USD", "EUR"),
    "USDJPY": ("USD", "JPY"),
    "XAUUSD": ("USD",),
    "US100.CASH": ("USD",),
    "NASDAQ": ("USD",),
}


class RiskBudgetError(ValueError):
    pass


def load_budget(path: str | Path | None = None) -> dict:
    target = Path(path) if path else BUDGET_PATH
    data: dict = {}
    if target.exists():
        loaded = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        data = loaded if isinstance(loaded, dict) else {}
    defaults = data.get("defaults") or {}
    assets = {}
    for canonical, item in (data.get("assets") or {}).items():
        payload = dict(item or {})
        payload.setdefault("symbol", canonical)
        payload["open_risk_pct"] = float(
            payload.get("open_risk_pct", defaults.get("open_risk_pct", 0.01))
        )
        payload["max_bot_slice_pct"] = float(
            payload.get(
                "max_bot_slice_pct", defaults.get("max_bot_slice_pct", 0.005)
            )
        )
        payload["initial_slice_pct"] = float(
            payload.get(
                "initial_slice_pct", defaults.get("initial_slice_pct", 0.0025)
            )
        )
        assets[str(canonical).upper()] = payload
    cluster = data.get("usd_cluster") or {}
    return {
        "assets": assets,
        "usd_cluster": {
            "name": str(cluster.get("name") or "USD"),
            "members": [
                str(item).upper() for item in (cluster.get("members") or [])
            ],
            "max_open_risk_pct": float(cluster.get("max_open_risk_pct", 0.015)),
        },
        "defaults": {
            "open_risk_pct": float(defaults.get("open_risk_pct", 0.01)),
            "max_bot_slice_pct": float(defaults.get("max_bot_slice_pct", 0.005)),
            "initial_slice_pct": float(defaults.get("initial_slice_pct", 0.0025)),
        },
        "source": str(target),
    }


def asset_entry(symbol: str, *, path: str | Path | None = None) -> dict | None:
    budget = load_budget(path)
    target = str(symbol or "").upper()
    for canonical, item in budget["assets"].items():
        if target in (canonical, str(item.get("symbol") or "").upper()):
            return {"canonical": canonical, **item}
    return None


def position_risk_usd(position: dict) -> float:
    """Riesgo conservador de una posición abierta (stop o 2% del nocional)."""
    explicit = position.get("risk_usd")
    if explicit is not None:
        return max(0.0, float(explicit))
    return abs(float(position.get("value") or 0.0)) * 0.02


def net_risk_by_asset(
    positions: list[dict],
    budget: dict | None = None,
) -> dict[str, float]:
    """Riesgo firmado por activo: largos positivos, cortos negativos."""
    config = budget or load_budget()
    out: dict[str, float] = {}
    for position in positions or []:
        entry = None
        symbol = str(position.get("ticker") or position.get("symbol") or "")
        target = symbol.upper()
        for canonical, item in config["assets"].items():
            if target in (canonical, str(item.get("symbol") or "").upper()):
                entry = canonical
                break
        if entry is None:
            continue
        risk = position_risk_usd(position)
        signed = risk if float(position.get("qty") or 0.0) >= 0 else -risk
        out[entry] = out.get(entry, 0.0) + signed
    return out


def usd_cluster_state(
    positions: list[dict],
    budget: dict | None = None,
) -> dict:
    """Exposición neta al USD y peor caso con todos los stops."""
    config = budget or load_budget()
    cluster = config["usd_cluster"]
    members = set(cluster["members"])
    net_usd = 0.0
    worst_risk = 0.0
    for position in positions or []:
        symbol = str(position.get("ticker") or position.get("symbol") or "").upper()
        entry = None
        for canonical, item in config["assets"].items():
            if symbol in (canonical, str(item.get("symbol") or "").upper()):
                entry = canonical
                break
        if entry not in members:
            continue
        value = abs(float(position.get("value") or 0.0))
        qty = float(position.get("qty") or 0.0)
        # EURUSD largo = corto USD; USDJPY largo = largo USD.
        if entry == "EURUSD":
            net_usd += -value if qty >= 0 else value
        elif entry == "USDJPY":
            net_usd += value if qty >= 0 else -value
        worst_risk += position_risk_usd(position)
    return {
        "name": cluster["name"],
        "net_usd": net_usd,
        "worst_risk_usd": worst_risk,
        "cap_pct": cluster["max_open_risk_pct"],
    }


def effective_slice(
    db_path: str | Path,
    asset: str,
    bot: str | None,
    *,
    budget: dict | None = None,
) -> dict:
    config = budget or load_budget()
    canonical = str(asset).upper()
    entry = config["assets"].get(canonical) or {}
    initial = float(entry.get("initial_slice_pct", config["defaults"]["initial_slice_pct"]))
    maximum = float(entry.get("max_bot_slice_pct", config["defaults"]["max_bot_slice_pct"]))
    if not bot:
        return {"pct": initial, "initial": initial, "max": maximum, "source": "config"}
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute(
            "SELECT * FROM risk_slice_overrides WHERE bot = ?", (bot,)
        ).fetchone()
    if row is not None:
        return {
            "pct": float(row["slice_pct"]),
            "initial": initial,
            "max": maximum,
            "source": "override",
        }
    return {"pct": initial, "initial": initial, "max": maximum, "source": "config"}


def assess_open(
    db_path: str | Path,
    *,
    symbol: str,
    side: str,
    proposed_risk_usd: float,
    equity: float,
    positions: list[dict] | None = None,
    limits=None,
    bot: str | None = None,
    budget_path: str | Path | None = None,
) -> dict:
    """Comprueba presupuesto por activo, rebanada por bot, total y cl?ster USD."""
    budget = load_budget(budget_path)
    entry = asset_entry(symbol, path=budget_path)
    if entry is None:
        return {
            "allowed": True,
            "reason": "sin presupuesto por activo",
            "asset": None,
            "net_before": 0.0,
            "net_after": 0.0,
            "asset_cap_usd": None,
            "total_after_usd": None,
            "total_cap_usd": None,
            "usd": usd_cluster_state(positions or [], budget),
        }
    canonical = entry["canonical"]
    risk = max(0.0, float(proposed_risk_usd))
    signed = risk if str(side).lower() in {"buy", "long"} else -risk
    nets = net_risk_by_asset(positions or [], budget)
    before = float(nets.get(canonical, 0.0))
    after = before + signed
    asset_cap = float(equity) * entry["open_risk_pct"]
    total_before = sum(abs(value) for value in nets.values())
    total_after = total_before - abs(before) + abs(after)
    total_cap = float(equity) * (
        float(limits.max_open_risk_pct) if limits is not None else 0.02
    )
    usd = usd_cluster_state(positions or [], budget)
    in_cluster = canonical in budget["usd_cluster"]["members"]
    proposed_usd = signed if in_cluster else 0.0
    usd_after = usd["net_usd"] + proposed_usd
    usd_worst = usd["worst_risk_usd"] + (risk if in_cluster else 0.0)
    usd_cap = float(equity) * usd["cap_pct"]
    usd_report = {
        **usd,
        "net_after": usd_after,
        "worst_after_usd": usd_worst,
        "cap_usd": usd_cap,
    }
    common = dict(
        entry=entry,
        before=before,
        after=after,
        asset_cap=asset_cap,
        total_after=total_after,
        total_cap=total_cap,
        usd=usd_report,
    )
    if abs(after) > asset_cap + 1e-9:
        return _report(
            False,
            f"riesgo neto {canonical} {abs(after):,.2f} > presupuesto {asset_cap:,.2f}",
            **common,
        )
    if bot:
        allowed = effective_slice(db_path, canonical, bot, budget=budget)
        bot_cap = float(equity) * float(allowed["pct"])
        if risk > bot_cap + 1e-9:
            return _report(
                False,
                f"rebanada de {bot} {risk:,.2f} > {bot_cap:,.2f} "
                f"({allowed['pct']:.2%} del equity)",
                **common,
            )
    if total_after > total_cap + 1e-9:
        return _report(
            False,
            f"riesgo abierto total {total_after:,.2f} > tope {total_cap:,.2f}",
            **common,
        )
    if in_cluster and usd_worst > usd_cap + 1e-9:
        return _report(
            False,
            f"peor caso cluster {usd['name']} {usd_worst:,.2f} > {usd_cap:,.2f}",
            **common,
        )
    return _report(True, "dentro de presupuesto", **common)


def _report(
    allowed,
    reason,
    *,
    entry,
    before,
    after,
    asset_cap,
    total_after,
    total_cap,
    usd,
):
    return {
        "allowed": bool(allowed),
        "reason": reason,
        "asset": entry["canonical"],
        "net_before": before,
        "net_after": after,
        "asset_cap_usd": asset_cap,
        "total_after_usd": total_after,
        "total_cap_usd": total_cap,
        "usd": usd,
    }


def set_bot_slice(
    db_path: str | Path,
    *,
    asset: str,
    bot: str,
    slice_pct: float,
    actor: str = "humano",
    reason: str = "",
    armed: bool = False,
    confirm: bool = False,
    budget_path: str | Path | None = None,
) -> dict:
    """Baja inmediata; subida solo con operador armado y confirmación."""
    init_db(db_path)
    entry = asset_entry(asset, path=budget_path)
    if entry is None:
        raise RiskBudgetError(f"activo sin presupuesto: {asset}")
    canonical = entry["canonical"]
    current = effective_slice(db_path, canonical, bot, budget=load_budget(budget_path))
    new = float(slice_pct)
    if new <= 0:
        raise RiskBudgetError("la rebanada debe ser > 0")
    if new > float(current["max"]) + 1e-12:
        raise RiskBudgetError(
            f"rebanada {new:.2%} > máximo {float(current['max']):.2%}"
        )
    action = "lower" if new < float(current["pct"]) else "raise"
    if action == "raise":
        if not (armed and confirm):
            raise RiskBudgetError(
                "subir la rebanada exige modo operador armado y confirmación"
            )
        try:
            from .f13 import status as f13_status

            frozen = f13_status(db_path)
        except Exception:
            frozen = None
        if frozen and str(frozen.get("bot")) == bot:
            raise RiskBudgetError(
                "no se puede subir la rebanada del bot con F13 congelado"
            )
    now = utcnow()
    with connect(db_path) as con:
        con.execute(
            "INSERT OR REPLACE INTO risk_slice_overrides"
            "(bot, asset, slice_pct, updated_at, updated_by, reason) "
            "VALUES(?,?,?,?,?,?)",
            (bot, canonical, new, now, actor, str(reason or "")[:500]),
        )
        cursor = con.execute(
            "INSERT INTO risk_slice_history"
            "(ts, asset, bot, old_slice_pct, new_slice_pct, action, actor, reason) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (
                now,
                canonical,
                bot,
                float(current["pct"]),
                new,
                action,
                actor,
                str(reason or "")[:500],
            ),
        )
        row = con.execute(
            "SELECT * FROM risk_slice_history WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
    return dict(row)


def revert_slice(
    db_path: str | Path,
    history_id: int,
    *,
    actor: str = "humano",
) -> dict:
    init_db(db_path)
    with connect(db_path) as con:
        row = con.execute(
            "SELECT * FROM risk_slice_history WHERE id = ?", (int(history_id),)
        ).fetchone()
        if row is None:
            raise RiskBudgetError(f"historial no encontrado: {history_id}")
        old = row["old_slice_pct"]
        if old is None:
            con.execute(
                "DELETE FROM risk_slice_overrides WHERE bot = ?", (row["bot"],)
            )
        else:
            con.execute(
                "INSERT OR REPLACE INTO risk_slice_overrides"
                "(bot, asset, slice_pct, updated_at, updated_by, reason) "
                "VALUES(?,?,?,?,?,?)",
                (
                    row["bot"],
                    row["asset"],
                    float(old),
                    utcnow(),
                    actor,
                    f"reversión de historial #{history_id}",
                ),
            )
        con.execute(
            "UPDATE risk_slice_history SET reverted_at = ? WHERE id = ?",
            (utcnow(), int(history_id)),
        )
        reverted = con.execute(
            "INSERT INTO risk_slice_history"
            "(ts, asset, bot, old_slice_pct, new_slice_pct, action, actor, reason) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (
                utcnow(),
                row["asset"],
                row["bot"],
                row["new_slice_pct"],
                float(old) if old is not None else 0.0,
                "revert",
                actor,
                f"reversión de historial #{history_id}",
            ),
        )
    return {"reverted": history_id, "history_id": reverted.lastrowid}


def slice_overrides(db_path: str | Path) -> list[dict]:
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT * FROM risk_slice_overrides ORDER BY asset, bot"
        ).fetchall()
    return [dict(row) for row in rows]


def slice_history(db_path: str | Path, *, limit: int = 50) -> list[dict]:
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT * FROM risk_slice_history ORDER BY id DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
    return [dict(row) for row in rows]


def news_blackout(
    db_path: str | Path,
    symbol: str,
    *,
    now: datetime | None = None,
    minutes_before: int = 30,
    minutes_after: int = 30,
) -> dict:
    """Apagón por eventos USD (y BoJ para USDJPY) usando macro_events."""
    init_db(db_path)
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    start = moment - timedelta(minutes=int(minutes_before))
    end = moment + timedelta(minutes=int(minutes_after))
    with connect(db_path) as con:
        total = con.execute("SELECT COUNT(*) AS n FROM macro_events").fetchone()["n"]
        rows = con.execute(
            "SELECT event, ts_utc, importance FROM macro_events "
            "WHERE ts_utc >= ? AND ts_utc <= ? ORDER BY ts_utc",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
    if not total:
        return {
            "blocked": False,
            "data_ok": False,
            "reason": "sin datos de macro_events",
            "events": [],
        }
    currencies = ASSET_CURRENCIES.get(str(symbol).upper(), ("USD",))
    keywords = list(USD_KEYWORDS)
    if "JPY" in currencies:
        keywords += JPY_KEYWORDS
    relevant = [
        dict(row)
        for row in rows
        if any(keyword in str(row["event"]).upper() for keyword in keywords)
    ]
    if not relevant:
        return {
            "blocked": False,
            "data_ok": True,
            "reason": "sin eventos relevantes",
            "events": [],
        }
    names = ", ".join(str(row["event"]) for row in relevant)
    return {
        "blocked": True,
        "data_ok": True,
        "reason": f"evento macro en ventana: {names}",
        "events": relevant,
    }


__all__ = [
    "BUDGET_PATH",
    "RiskBudgetError",
    "asset_entry",
    "assess_open",
    "effective_slice",
    "load_budget",
    "net_risk_by_asset",
    "news_blackout",
    "position_risk_usd",
    "revert_slice",
    "set_bot_slice",
    "slice_history",
    "slice_overrides",
    "usd_cluster_state",
]
