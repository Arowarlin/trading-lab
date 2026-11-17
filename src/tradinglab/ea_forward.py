"""Forward del EA externo US100_FTMO1: pre-registro, métricas y comparación.

El EA no es un bot del orquestador: sus fills llegan como `ea:<id>`. Este
módulo reconstruye sus operaciones cerradas desde el Diario, las compara con la
predicción de `ea_us100_engine` para la misma vela M5 y entrega las métricas que
consume `lifecycle`. No envía órdenes ni modifica el EA.
"""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import pandas as pd

from .config import DEFAULT_DB, ROOT, Settings, get_settings
from .db import connect, init_db
from .ea_registry import EAError, ExternalEA, get_ea
from .ea_us100 import load_bars, load_setfile, params_from_set
from .ea_us100_engine import run as run_engine
from .lifecycle import (
    LifecycleError,
    criteria_hash,
    pre_register_external,
    report_bot,
    start_external_forward,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _code_sha256(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


EA_DIR = ROOT / "integrations" / "mt5" / "us100_ftmo1"
EA_CODE = [
    EA_DIR / "US100_EA.mq5",
    EA_DIR / "US100_EntryManager.mqh",
    EA_DIR / "US100_ExitManager.mqh",
    EA_DIR / "US100_MarketAnalysis.mqh",
    EA_DIR / "US100_RiskManager.mqh",
    EA_DIR / "US100_Strategy.mqh",
    EA_DIR / "Shared_FTMO_Risk.mqh",
    EA_DIR / "Shared_Logger.mqh",
]

EA_CRITERIA = {
    "window_days": 60,
    "min_trades": 40,
    "min_trades_after_window": 40,
    "min_forward_pf": 1.15,
    "min_expectancy_r": 0.10,
    "max_forward_dd_pct": 0.06,
    "max_slippage_mean_points": 2.0,
    "min_entry_match_pct": 0.90,
    "max_guard_breaches": 0,
    "require_drift": False,
    "min_forward_sharpe": None,
    "engine_version": "3.2",
    "setfile_sha256": _sha256(EA_DIR / "US100_FTMO_v3_challenge.set"),
    "code_sha256": _code_sha256(EA_CODE),
    "replica_sha256": _sha256(ROOT / "src" / "tradinglab" / "ea_us100_engine.py"),
    "calendar_sha256": _sha256(ROOT / "src" / "tradinglab" / "nyse_calendar.py"),
}
DEFAULT_BOT = "ea:us100-ftmo1"
# Cuenta por defecto del forward. La fuente de verdad es `ea.account`
# (config/mt5_eas.yaml); la constante se conserva por compatibilidad.
FORWARD_ACCOUNT = "ftmo_demo"
POINT = 0.01


def _ea_for_bot(bot: str) -> ExternalEA:
    ea_id = bot.split(":", 1)[-1]
    ea = get_ea(ea_id)
    if ea is None:
        raise EAError(f"EA no registrado: {ea_id}")
    return ea


def _fill_ids_for_account(
    db_path: str | Path, account: str = FORWARD_ACCOUNT
) -> set[int]:
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT id FROM fills WHERE account = ?", (account,)
        ).fetchall()
    return {int(row["id"]) for row in rows}


def _closed(db_path: str | Path, ea: ExternalEA):
    from .journal import load_closed_trades

    trades, _ = load_closed_trades(
        db_path,
        tz="America/New_York",
        bots={ea.bot_id: {"account": ea.account, "profile": "intraday_fx"}},
    )
    allowed = _fill_ids_for_account(db_path, ea.account)
    return [
        trade
        for trade in trades
        if trade.bot == ea.bot_id and trade.exit_fill_id in allowed
    ]


def _first_date(trades) -> str | None:
    stamps = [str(trade.entry_ts)[:10] for trade in trades if trade.entry_ts]
    return min(stamps) if stamps else None


def _first_fill_date(
    db_path: str | Path,
    ea: ExternalEA,
    *,
    since: str | None = None,
) -> str | None:
    """Primer fill real del EA (incluye posiciones aún abiertas).

    Solo cuentan los fills posteriores al pre-registro (`frozen_at`), para que
    una operación anterior a congelar los criterios no arranque el reloj.
    """
    magics = sorted({int(ea.magic), *(int(item) for item in ea.managed_magics)})
    marks = ",".join("?" for _ in magics)
    sql = (
        "SELECT ts FROM fills WHERE (bot = ? OR magic IN ("
        f"{marks})) AND account = ? AND ts IS NOT NULL"
    )
    try:
        with connect(db_path) as con:
            rows = con.execute(
                sql, (ea.bot_id, *magics, ea.account)
            ).fetchall()
    except Exception:
        return None
    stamps = [str(row["ts"]) for row in rows if row["ts"]]
    if not stamps:
        return None
    series = pd.to_datetime(pd.Series(stamps), utc=True, format="mixed")
    if since:
        cutoff = pd.Timestamp(since)
        cutoff = (
            cutoff.tz_localize("UTC")
            if cutoff.tzinfo is None
            else cutoff.tz_convert("UTC")
        )
        series = series[series >= cutoff]
    if series.empty:
        return None
    local = series.dt.tz_convert("America/New_York")
    return local.dt.date.min().isoformat()


def ensure_forward(
    db_path: str | Path = DEFAULT_DB,
    *,
    bot: str = DEFAULT_BOT,
) -> dict:
    """Pre-registra el forward y arranca el reloj en el primer fill."""
    ea = _ea_for_bot(bot)
    init_db(db_path)
    with connect(db_path) as con:
        found = con.execute(
            "SELECT * FROM lifecycle_bots WHERE bot = ?", (bot,)
        ).fetchone()
    row = dict(found) if found is not None else None
    if row is not None and row.get("criteria_hash"):
        frozen = criteria_hash(EA_CRITERIA)
        if str(row["criteria_hash"]) != frozen:
            raise LifecycleError(
                f"{bot}: criterios ya congelados con hash {row['criteria_hash']}; "
                f"el código propone {frozen} y no se puede cambiar el forward"
            )
    if row is None:
        row = pre_register_external(
            db_path,
            bot=bot,
            asset=ea.symbol,
            criteria=EA_CRITERIA,
            note="forward EA externo; inicio al primer fill",
        )
    since = row.get("frozen_at")
    first = _first_fill_date(db_path, ea, since=since)
    if first is None and not since:
        # Filas antiguas sin `frozen_at`: se conserva el respaldo por Diario.
        first = _first_date(_closed(db_path, ea))
    if first and not row.get("start_date"):
        row = start_external_forward(db_path, bot=bot, first_date=first)
    return dict(row)


def refresh_forward_preregistration(
    db_path: str | Path = DEFAULT_DB,
    *,
    bot: str = DEFAULT_BOT,
) -> dict:
    """Actualiza el pre-registro a v3.2 antes del primer fill del forward.

    Si ya hay `start_date` o fills, se niega: cambiar el hash después del primer
    fill sería un forward nuevo, no una actualización del pre-registro.
    """
    ea = _ea_for_bot(bot)
    init_db(db_path)
    with connect(db_path) as con:
        found = con.execute(
            "SELECT * FROM lifecycle_bots WHERE bot = ?", (bot,)
        ).fetchone()
    row = dict(found) if found is not None else None
    if row is not None:
        if row.get("start_date"):
            raise LifecycleError(
                f"{bot}: el forward ya empezó; no se puede actualizar el pre-registro"
            )
        first = _first_fill_date(db_path, ea, since=row.get("frozen_at"))
        if first is not None:
            raise LifecycleError(
                f"{bot}: ya hay fills; no se puede actualizar el pre-registro"
            )
    return pre_register_external(
        db_path,
        bot=bot,
        asset=ea.symbol,
        criteria=EA_CRITERIA,
        note="v3.2: pre-registro actualizado antes de la primera operación forward",
        allow_refresh=True,
    )


def forward_metrics(
    db_path: str | Path,
    bot: str = DEFAULT_BOT,
    *,
    start_date: str | None = None,
    account_size: float = 100_000.0,
    settings: Settings | None = None,
) -> dict:
    """Métricas forward y coincidencia con el motor para la misma vela."""
    ea = _ea_for_bot(bot)
    trades = _closed(db_path, ea)
    if start_date:
        trades = [
            trade
            for trade in trades
            if str(trade.entry_ts)[:10] >= str(start_date)[:10]
        ]
    if not trades:
        return {
            "n_trades": 0,
            "pf": None,
            "expectancy": None,
            "sharpe": None,
            "max_dd_pct": 0.0,
            "slippage_mean_points": None,
            "entry_match_pct": None,
            "guard_breaches": 0,
            "first_trade": None,
            "last_trade": None,
            "engine_trades": 0,
            "engine_start": None,
            "engine_end": None,
            "drift_status": "sin datos",
        }
    cfg = settings or get_settings()
    df = load_bars(cfg)
    values = load_setfile(ea.setfile)
    # Los fills externos no traen `risk_usd`; se usa el riesgo del setfile
    # (base dinámica 1.0 % o fijo 0.35 %) para no convertir un +2,97R en 0R.
    risk_fraction = None
    try:
        if bool(values.get("InpDynRisk", False)):
            risk_fraction = float(values.get("InpDynBase", 1.0)) / 100.0
        else:
            risk_fraction = float(values.get("InpRiskPct", 0.35)) / 100.0
    except (TypeError, ValueError):
        risk_fraction = None
    predicted = run_engine(df, params_from_set(values))
    predicted = predicted.copy()
    predicted["t"] = pd.to_datetime(predicted["t"])
    points = POINT
    matched = 0
    slips: list[float] = []
    for trade in trades:
        entry = pd.Timestamp(str(trade.entry_ts))
        entry = (
            entry.tz_localize("UTC")
            if entry.tzinfo is None
            else entry.tz_convert("UTC")
        )
        entry_ny = entry.tz_convert("America/New_York").tz_localize(None)
        side = 1 if str(trade.side).lower() in {"long", "buy"} else -1
        window = predicted[
            (predicted["d"] == side)
            & ((predicted["t"] - entry_ny).abs() <= pd.Timedelta(minutes=5))
        ]
        if window.empty:
            continue
        engine_trade = window.iloc[0]
        # El motor exporta t (hora NY), d (lado) y ent (precio de entrada).
        matched += 1
        slips.append(abs(float(trade.entry_price) - float(engine_trade["ent"])) / points)
    rs = []
    pnls = []
    for trade in sorted(trades, key=lambda item: str(item.exit_ts)):
        risk = float(trade.risk_usd or 0.0)
        r = trade.r_multiple
        if r is None and risk > 0:
            r = float(trade.pnl) / risk
        if r is None and risk_fraction and account_size:
            r = float(trade.pnl) / (float(account_size) * risk_fraction)
        rs.append(float(r or 0.0))
        pnls.append(float(trade.pnl or 0.0))
    wins = [value for value in rs if value > 0]
    losses = [value for value in rs if value < 0]
    pf = sum(wins) / abs(sum(losses)) if losses and sum(losses) < 0 else None
    expectancy = sum(rs) / len(rs) if rs else None
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    daily = {}
    for trade in trades:
        day = str(trade.entry_ts)[:10]
        daily[day] = daily.get(day, 0.0) + float(
            trade.r_multiple
            if trade.r_multiple is not None
            else (float(trade.pnl) / float(trade.risk_usd or 1.0))
        )
    daily_series = pd.Series(daily, dtype=float).sort_index()
    std = float(daily_series.std(ddof=1)) if len(daily_series) > 1 else 0.0
    sharpe = (
        float(daily_series.mean() / std * (252 ** 0.5)) if std > 0 else None
    )
    first = _first_date(trades)
    last = max((str(trade.exit_ts)[:10] for trade in trades), default=None)
    try:
        with connect(db_path) as con:
            breaches = con.execute(
                "SELECT COUNT(*) AS n FROM orders WHERE bot=? AND status='bloqueado' "
                "AND ts >= ?",
                (bot, start_date or first or "1970-01-01"),
            ).fetchone()["n"]
    except Exception:
        breaches = 0
    return {
        "n_trades": len(trades),
        "pf": round(pf, 4) if pf is not None else None,
        "expectancy": round(expectancy, 4) if expectancy is not None else None,
        "sharpe": round(sharpe, 4) if sharpe is not None else None,
        "max_dd_pct": round(max_dd / float(account_size), 6) if account_size else None,
        "slippage_mean_points": (
            round(sum(slips) / len(slips), 4) if slips else None
        ),
        "entry_match_pct": round(matched / len(trades), 4),
        "guard_breaches": int(breaches),
        "first_trade": first,
        "last_trade": last,
        "engine_trades": int(len(predicted)),
        "engine_start": str(predicted["t"].min()) if len(predicted) else None,
        "engine_end": str(predicted["t"].max()) if len(predicted) else None,
        "drift_status": "sin datos",
    }


def forward_report(
    db_path: str | Path = DEFAULT_DB,
    *,
    bot: str = DEFAULT_BOT,
    today: date | None = None,
) -> dict:
    ensure_forward(db_path, bot=bot)
    return report_bot(db_path, bot, today=today)


def criteria_preview(bot: str = DEFAULT_BOT) -> dict:
    return {
        "bot": bot,
        "criteria": dict(EA_CRITERIA),
        "hash": criteria_hash(EA_CRITERIA),
    }


__all__ = [
    "DEFAULT_BOT",
    "EA_CRITERIA",
    "FORWARD_ACCOUNT",
    "POINT",
    "criteria_preview",
    "ensure_forward",
    "forward_metrics",
    "forward_report",
    "refresh_forward_preregistration",
]
