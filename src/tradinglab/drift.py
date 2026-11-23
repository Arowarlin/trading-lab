"""Deriva live/paper vs backtest por bot y por carril. Solo lectura e informativo.

No bloquea órdenes. La sección de bots compara Sharpe y expectancy del Diario
con la última evaluación, con intervalos bootstrap, y el slippage real (fills vs
señal) con el supuesto del backtest. La sección R7b reconstruye, para cada
carril demo, la operación que su regla congelada habría hecho el mismo día.
Sin muestra suficiente: "sin datos".
"""
from __future__ import annotations

import math
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yaml

from .accounts import load_accounts
from .botlab import latest_evaluations
from .config import ROOT, Settings
from .journal import load_closed_trades, summarize
from .metrics import execution_metrics
from .orchestrator import load_bots

MIN_TRADES = 20
MIN_SLIPPAGE_FILLS = 5
BOOTSTRAP_PATHS = 1_000
SEED = 42
STATUS_ORDER = {"ok": 0, "vigilar": 1, "deriva": 2}


def classify_metric(
    live: float | None,
    backtest: float | None,
    ci_low: float | None,
    ci_high: float | None,
) -> tuple[str, float | None]:
    """ok si el backtest cae en el IC; vigilar/deriva por z del IC."""
    if live is None or backtest is None or ci_low is None or ci_high is None:
        return "sin datos", None
    if ci_low <= backtest <= ci_high:
        return "ok", 0.0
    half = (ci_high - ci_low) / 2.0
    se = half / 1.96
    if se <= 0:
        return "sin datos", None
    z = abs(live - backtest) / se
    if z > 3.0:
        return "deriva", z
    if z > 1.96:
        return "vigilar", z
    return "ok", z


def classify_slippage(
    fills: int,
    p50_bps: float | None,
    p95_bps: float | None,
    *,
    backtest_bps: float,
    max_p50_bps: float = 10.0,
    max_p95_bps: float = 25.0,
    min_fills: int = MIN_SLIPPAGE_FILLS,
) -> tuple[str, list[str]]:
    if fills < min_fills or p50_bps is None:
        return "sin datos", [f"fills={fills} < {min_fills}"]
    reasons = []
    if p50_bps > max_p50_bps or (p95_bps is not None and p95_bps > max_p95_bps):
        reasons.append(
            f"slippage p50={p50_bps:.1f}bps / p95={p95_bps if p95_bps is not None else float('nan'):.1f}bps "
            f"supera máximos {max_p50_bps:.0f}/{max_p95_bps:.0f}"
        )
        return "deriva", reasons
    if p50_bps > backtest_bps + 5.0:
        reasons.append(
            f"slippage p50={p50_bps:.1f}bps > backtest {backtest_bps:.1f}bps + 5"
        )
        return "vigilar", reasons
    reasons.append(
        f"slippage p50={p50_bps:.1f}bps vs backtest {backtest_bps:.1f}bps"
    )
    return "ok", reasons


def _bootstrap_sharpe(
    trades, capital: float | None
) -> tuple[float | None, float | None, float | None]:
    if not trades or capital is None or capital <= 0:
        return None, None, None
    daily: dict[str, float] = {}
    for trade in trades:
        daily[trade.day] = daily.get(trade.day, 0.0) + trade.pnl
    if len(daily) < 2:
        return None, None, None
    returns = np.asarray(
        [daily[day] / capital for day in sorted(daily)], dtype=float
    )
    rng = np.random.default_rng(SEED)
    values = []
    for _ in range(BOOTSTRAP_PATHS):
        sample = rng.choice(returns, size=len(returns), replace=True)
        std = float(sample.std(ddof=1)) if len(sample) > 1 else 0.0
        values.append(
            float(sample.mean() / std * math.sqrt(252)) if std > 0 else 0.0
        )
    low, high = np.percentile(values, [2.5, 97.5])
    return float(np.mean(values)), float(low), float(high)


def _bootstrap_expectancy(trades) -> tuple[float | None, float | None, float | None]:
    values = np.asarray([trade.pnl for trade in trades], dtype=float)
    if values.size < 2:
        return None, None, None
    rng = np.random.default_rng(SEED)
    means = [
        float(rng.choice(values, size=values.size, replace=True).mean())
        for _ in range(BOOTSTRAP_PATHS)
    ]
    low, high = np.percentile(means, [2.5, 97.5])
    return float(np.mean(means)), float(low), float(high)


def _merge_status(statuses: list[str]) -> str:
    known = [status for status in statuses if status in STATUS_ORDER]
    if not known:
        return "sin datos"
    return max(known, key=lambda status: STATUS_ORDER[status])


def build_drift(
    db_path: str | Path,
    settings: Settings | None = None,
    *,
    min_trades: int = MIN_TRADES,
    min_slippage_fills: int = MIN_SLIPPAGE_FILLS,
) -> dict:
    """Deriva informativa de todos los bots configurados."""
    settings = settings or Settings()
    specs = load_bots()
    accounts = load_accounts()
    evaluations = latest_evaluations(db_path)
    trades, _diagnostics = load_closed_trades(
        db_path,
        tz=settings.timezone,
        bots={
            spec.id: {"account": spec.account, "profile": spec.profile}
            for spec in specs
        },
    )
    by_bot: dict[str, list] = {}
    manual = [trade for trade in trades if trade.manual]
    for trade in trades:
        if trade.manual:
            continue
        by_bot.setdefault(trade.bot, []).append(trade)
    criteria = {"max_slippage_bps_p50": 10.0, "max_slippage_bps_p95": 25.0}
    max_p50 = float(criteria["max_slippage_bps_p50"])
    max_p95 = float(criteria["max_slippage_bps_p95"])
    backtest_bps = float(settings.execution.slippage_bps)

    rows = []
    for spec in specs:
        group = by_bot.get(spec.id, [])
        live = summarize(group, accounts) if group else None
        backtest = evaluations.get(spec.id)
        bt_status = str((backtest or {}).get("status") or "")
        bt_valid = bool(backtest and bt_status not in {"no_evaluable", ""})
        bt_sharpe = (
            float(backtest["sharpe"])
            if bt_valid and backtest.get("sharpe") is not None
            else None
        )
        bt_expectancy = (
            float(backtest["expectancy"])
            if bt_valid and backtest.get("expectancy") is not None
            else None
        )
        capital = float(live["capital"]) if live and live.get("capital") else None
        _, sharpe_low, sharpe_high = _bootstrap_sharpe(group, capital)
        _, exp_low, exp_high = _bootstrap_expectancy(group)
        live_sharpe = float(live["sharpe"]) if live and live.get("sharpe") is not None else None
        live_expectancy = (
            float(live["expectancy"])
            if live and live.get("expectancy") is not None
            else None
        )
        reasons: list[str] = []
        if len(group) < min_trades:
            edge_status = "sin datos"
            reasons.append(f"live N={len(group)} < mínimo {min_trades}")
        else:
            sharpe_status, sharpe_z = classify_metric(
                live_sharpe, bt_sharpe, sharpe_low, sharpe_high
            )
            exp_status, exp_z = classify_metric(
                live_expectancy, bt_expectancy, exp_low, exp_high
            )
            edge_status = _merge_status([sharpe_status, exp_status])
            reasons.append(
                f"Sharpe live {live_sharpe if live_sharpe is not None else 'sin datos'} "
                f"vs BT {bt_sharpe if bt_sharpe is not None else 'sin datos'} "
                f"(IC {sharpe_low if sharpe_low is not None else 'sin datos'}…"
                f"{sharpe_high if sharpe_high is not None else 'sin datos'}, z={sharpe_z})"
            )
            reasons.append(
                f"expectancy live {live_expectancy if live_expectancy is not None else 'sin datos'} "
                f"vs BT {bt_expectancy if bt_expectancy is not None else 'sin datos'}"
            )
        start_date = group[0].day if group else "1970-01-01"
        slippage = execution_metrics(db_path, bot=spec.id, start_date=start_date)
        slip_status, slip_reasons = classify_slippage(
            int(slippage.get("fills") or 0),
            slippage.get("slippage_p50_bps"),
            slippage.get("slippage_p95_bps"),
            backtest_bps=backtest_bps,
            max_p50_bps=max_p50,
            max_p95_bps=max_p95,
            min_fills=min_slippage_fills,
        )
        reasons.extend(slip_reasons)
        status = (
            "sin datos"
            if edge_status == "sin datos"
            else _merge_status([edge_status, slip_status])
        )
        rows.append(
            {
                "bot": spec.id,
                "account": spec.account,
                "profile": spec.profile,
                "enabled": spec.enabled,
                "backtest": {
                    "status": bt_status or "Sin datos",
                    "sharpe": bt_sharpe,
                    "expectancy": bt_expectancy,
                    "num_trades": (backtest or {}).get("num_trades"),
                    "win_rate": (backtest or {}).get("win_rate"),
                },
                "live": {
                    "n": len(group),
                    "days": len({trade.day for trade in group}),
                    "sharpe": live_sharpe,
                    "sharpe_ci95": [sharpe_low, sharpe_high],
                    "expectancy": live_expectancy,
                    "expectancy_ci95": [exp_low, exp_high],
                    "win_rate": live.get("win_rate") if live else None,
                    "net_pnl": live.get("net_pnl") if live else None,
                },
                "slippage": {
                    "fills": int(slippage.get("fills") or 0),
                    "p50_bps": slippage.get("slippage_p50_bps"),
                    "p95_bps": slippage.get("slippage_p95_bps"),
                    "backtest_bps": backtest_bps,
                },
                "edge_status": edge_status,
                "slippage_status": slip_status,
                "status": status,
                "reasons": reasons,
                "sample_ok": len(group) >= min_trades,
            }
        )
    rows.sort(key=lambda row: row["bot"])
    # El carril IA discrecional no tiene backtest comparable, pero se muestra
    # aparte para que sus fills no se confundan con operaciones manuales.
    try:
        from .ai_trader import load_config as load_ai_config

        ai_cfg = load_ai_config()
        known = {row["bot"] for row in rows}
        for name, item in ai_cfg["styles"].items():
            bot = f"ai:{name}"
            if bot in known:
                continue
            group = by_bot.get(bot, [])
            live = summarize(group, accounts) if group else None
            start_date = group[0].day if group else "1970-01-01"
            slippage = execution_metrics(db_path, bot=bot, start_date=start_date)
            slip_status, slip_reasons = classify_slippage(
                int(slippage.get("fills") or 0),
                slippage.get("slippage_p50_bps"),
                slippage.get("slippage_p95_bps"),
                backtest_bps=backtest_bps,
                max_p50_bps=max_p50,
                max_p95_bps=max_p95,
                min_fills=min_slippage_fills,
            )
            rows.append({
                "bot": bot,
                "account": "ftmo_demo",
                "profile": "ia_discrecional",
                "enabled": bool(item["enabled"]),
                "backtest": {"status": "Sin datos", "sharpe": None,
                             "expectancy": None, "num_trades": None,
                             "win_rate": None},
                "live": {
                    "n": len(group),
                    "days": len({trade.day for trade in group}),
                    "sharpe": live.get("sharpe") if live else None,
                    "sharpe_ci95": [None, None],
                    "expectancy": live.get("expectancy") if live else None,
                    "expectancy_ci95": [None, None],
                    "win_rate": live.get("win_rate") if live else None,
                    "net_pnl": live.get("net_pnl") if live else None,
                },
                "slippage": {
                    "fills": int(slippage.get("fills") or 0),
                    "p50_bps": slippage.get("slippage_p50_bps"),
                    "p95_bps": slippage.get("slippage_p95_bps"),
                    "backtest_bps": backtest_bps,
                },
                "edge_status": "sin datos",
                "slippage_status": slip_status,
                "status": "sin datos",
                "reasons": [
                    f"carril IA {name}: sin backtest comparable",
                    *slip_reasons,
                ],
                "sample_ok": len(group) >= min_trades,
            })
        rows.sort(key=lambda row: row["bot"])
    except Exception:
        pass
    try:
        from .tca import attach_to_drift

        rows = attach_to_drift(rows, db_path)
    except Exception:
        pass
    counts = {"ok": 0, "vigilar": 0, "deriva": 0, "sin datos": 0}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "min_trades": int(min_trades),
        "min_slippage_fills": int(min_slippage_fills),
        "bootstrap_paths": BOOTSTRAP_PATHS,
        "seed": SEED,
        "backtest_slippage_bps": backtest_bps,
        "manual_excluded": len(manual),
        "summary": counts,
        "bots": rows,
    }


# ---------------------------------------------------------------------------
# R7b · deriva demo vs backtest por carril operativo
# ---------------------------------------------------------------------------
#
# Esta sección solo lee: base SQLite en modo ro, barras/ticks/deals de MT5
# attach-only y configs congeladas. No envía órdenes, no escribe `lab.db` ni
# modifica el carril del EA, el forward o ai_trader.

LANE_TIMEFRAME_MINUTES = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H4": 240,
    "D1": 1440,
}
LANE_POINTS = {
    "US100": 0.01,
    "XAUUSD": 0.01,
    "EURUSD": 0.00001,
    "GBPUSD": 0.00001,
    "USDJPY": 0.001,
}
LANE_ENTRY_RE = re.compile(r"open_(long|short) executed")
LANE_CLOSE_RE = re.compile(r"closed ticket=(\d+) reason=(.*)")
LANE_ACCOUNT_SIZE = 100_000.0


class LaneDriftError(RuntimeError):
    """No se puede medir la deriva de un carril."""


@dataclass(frozen=True)
class LaneSpec:
    """Regla congelada de un carril y cómo reconstruir su backtest."""

    id: str
    label: str
    kind: str
    bot: str
    symbol: str
    timeframe: str
    strategy: str | None = None
    params: tuple[tuple[str, object], ...] = ()
    stop_atr: float = 0.0
    entry_start: time | None = None
    entry_end: time | None = None
    force_exit: time | None = None
    max_trades_per_day: int = 1
    magic: int | None = None
    account: str = "ftmo_demo"
    backtest: str = "none"

    @property
    def params_dict(self) -> dict:
        return dict(self.params)

    @property
    def timeframe_minutes(self) -> int:
        return LANE_TIMEFRAME_MINUTES.get(self.timeframe.upper(), 0)


@dataclass
class DemoTrade:
    """Operación demo reconstruida, cerrada o todavía abierta."""

    side: int
    entry_ts: datetime
    entry: float
    qty: float
    exit_ts: datetime | None = None
    exit: float | None = None
    stop: float | None = None
    r: float | None = None
    pnl: float | None = None
    ticket: int | None = None
    source: str = ""
    note: str = ""

    @property
    def day(self) -> date:
        return self.entry_ts.date()

    @property
    def closed(self) -> bool:
        return self.exit is not None and self.exit_ts is not None


def _parse_stamp(value) -> datetime:
    if isinstance(value, datetime):
        stamp = value
    else:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def _point_for(symbol: str) -> float:
    key = str(symbol).upper().replace(".CASH", "")
    return LANE_POINTS.get(key, 0.0001)


def _symbol_book_key(symbol: str) -> str:
    key = str(symbol).upper()
    if key.startswith("US100"):
        return "US100"
    if key.startswith("US500"):
        return "US500"
    if key.startswith("US30"):
        return "US30"
    if key.startswith("XAU"):
        return "XAUUSD"
    return key.split(".")[0]


@lru_cache(maxsize=8)
def _profile_costs(account: str = "CFD-001") -> dict:
    path = ROOT / "config" / "propfund" / "costs.yaml"
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError:
        return {}
    accounts = raw.get("accounts") or {}
    return ((accounts.get(account) or {}).get("symbols") or {})


def _assumed_costs(symbol: str, reference: float, settings: Settings) -> dict:
    book = _profile_costs().get(_symbol_book_key(symbol)) or {}
    spread_price = book.get("spread_price")
    slippage_price = book.get("slippage_price")
    spread_bps = (
        float(spread_price) / float(reference) * 10_000.0
        if spread_price is not None and reference
        else None
    )
    if slippage_price is not None and reference:
        slippage_bps = float(slippage_price) / float(reference) * 10_000.0
    else:
        slippage_bps = float(settings.execution.slippage_bps)
    return {
        "spread_price": float(spread_price) if spread_price is not None else None,
        "spread_bps": spread_bps,
        "slippage_price": (
            float(slippage_price) if slippage_price is not None else None
        ),
        "slippage_bps": slippage_bps,
        "source": "config/propfund/costs.yaml CFD-001",
    }


def _slip_bps(side: int, fill: float, reference: float | None) -> float | None:
    if reference is None or reference <= 0 or fill is None:
        return None
    return float(side) * (float(fill) - float(reference)) / float(reference) * 10_000.0


def _quantile(values: list[float], q: float) -> float | None:
    clean = sorted(float(value) for value in values if value is not None)
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    position = (len(clean) - 1) * float(q)
    low = int(math.floor(position))
    high = int(math.ceil(position))
    if low == high:
        return clean[low]
    weight = position - low
    return clean[low] * (1.0 - weight) + clean[high] * weight


def _metric_summary(values: list[float | None]) -> dict:
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return {"n": 0, "mean": None, "p50": None, "p95": None}
    return {
        "n": len(clean),
        "mean": sum(clean) / len(clean),
        "p50": _quantile(clean, 0.50),
        "p95": _quantile(clean, 0.95),
    }


def _readonly_connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path).resolve()
    if not path.exists():
        raise LaneDriftError(f"no existe la base: {path}")
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def lane_specs() -> list[LaneSpec]:
    """Carriles ya en marcha, leídos de sus configs congeladas."""
    from .ea_registry import get_ea
    from .forward_intraday import load_forward_bots

    specs: list[LaneSpec] = []
    for bot in load_forward_bots():
        kind = "incubation" if bot.id == "us100-trend-d1" else "forward"
        specs.append(
            LaneSpec(
                id=bot.id,
                label=f"forward {bot.id}",
                kind=kind,
                bot=bot.signal_bot,
                symbol=bot.canonical_symbol,
                timeframe=bot.timeframe,
                strategy=bot.strategy,
                params=tuple(sorted(bot.params.items())),
                stop_atr=float(bot.stop_atr),
                entry_start=bot.entry_start,
                entry_end=bot.entry_end,
                force_exit=bot.force_exit,
                max_trades_per_day=int(bot.max_trades_per_day),
                magic=int(bot.magic),
                account=bot.account,
                backtest="forward_replay",
            )
        )
    ea = get_ea("us100-ftmo1")
    if ea is not None:
        specs.append(
            LaneSpec(
                id=ea.id,
                label=f"EA {ea.name}",
                kind="ea",
                bot=ea.bot_id,
                symbol=ea.symbol,
                timeframe=ea.timeframe,
                max_trades_per_day=3,
                magic=int(ea.magic),
                account=ea.account,
                backtest="ea_engine",
            )
        )
    specs.append(
        LaneSpec(
            id="ai-trader",
            label="ai_trader (solo registro)",
            kind="ai",
            bot="ai:",
            symbol="*",
            timeframe="*",
            account="ftmo_demo",
            backtest="none",
        )
    )
    return specs


def _lane_matches(spec: LaneSpec, needle: str | None) -> bool:
    if not needle:
        return True
    text = str(needle).strip().lower()
    return any(
        text in value
        for value in (spec.id.lower(), spec.bot.lower(), spec.label.lower())
    )


class MarketData:
    """Barras, ticks y deals de MT5 en solo lectura, con caché por proceso."""

    def __init__(
        self,
        settings: Settings,
        *,
        db_path: str | Path | None = None,
        offline: bool = False,
    ) -> None:
        self.settings = settings
        self.db_path = db_path
        self.offline = bool(offline)
        self.broker = None
        self.login_before: int | None = None
        self.login_after: int | None = None
        self.server: str | None = None
        self.used = False
        self.errors: list[str] = []
        self._bars: dict[tuple[str, str, int], pd.DataFrame] = {}
        self._ticks: dict[tuple[str, str, str], pd.DataFrame | None] = {}

    def connect(self) -> None:
        if self.offline:
            return
        try:
            from .execution import get_mt5_broker

            self.broker = get_mt5_broker(
                self.settings, db_path=self.db_path, dry_run=True
            )
            self.broker.connect()
            health = self.broker.health()
            self.login_before = int(health.get("login") or 0) or None
            self.server = str(health.get("server") or "") or None
            self.used = True
        except Exception as exc:
            self.errors.append(f"MT5 no disponible: {exc}")
            self.broker = None

    def close(self) -> None:
        if self.broker is None:
            return
        try:
            health = self.broker.health()
            self.login_after = int(health.get("login") or 0) or None
        except Exception:
            pass
        try:
            self.broker.shutdown()
        except Exception:
            pass
        self.broker = None

    def __enter__(self) -> "MarketData":
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def bars(self, symbol: str, timeframe: str, count: int = 6000) -> pd.DataFrame:
        key = (symbol.upper(), timeframe.upper(), int(count))
        if key in self._bars:
            return self._bars[key]
        frame: pd.DataFrame | None = None
        if self.broker is not None:
            try:
                frame = _raw_bars(symbol, timeframe, count)
            except Exception as exc:
                self.errors.append(f"{symbol} {timeframe}: {exc}")
        if frame is None or frame.empty:
            try:
                from .intraday import load_bars

                cache_symbol = (
                    "US100.CASH" if symbol.upper().startswith("US100") else symbol
                )
                frame = load_bars(
                    self.settings.data.cache_dir, cache_symbol, timeframe
                )
                self.errors.append(
                    f"{symbol} {timeframe}: sin MT5, se usa caché local"
                )
            except Exception as exc:
                raise LaneDriftError(
                    f"Sin datos de bróker para {symbol} {timeframe}: {exc}"
                ) from exc
        if not isinstance(frame.index, pd.DatetimeIndex):
            frame.index = pd.to_datetime(frame.index, utc=True)
        if frame.index.tz is None:
            frame.index = frame.index.tz_localize("UTC")
        else:
            frame.index = frame.index.tz_convert("UTC")
        frame = frame[~frame.index.duplicated(keep="last")].sort_index()
        self._bars[key] = frame
        return frame

    def ticks(
        self, symbol: str, start: datetime, end: datetime
    ) -> pd.DataFrame | None:
        key = (symbol, start.isoformat(), end.isoformat())
        if key in self._ticks:
            return self._ticks[key]
        if self.broker is None:
            self._ticks[key] = None
            return None
        try:
            frame = self.broker.copy_ticks(symbol, start, end)
        except Exception as exc:
            self.errors.append(f"ticks {symbol}: {exc}")
            self._ticks[key] = None
            return None
        self._ticks[key] = frame
        return frame

    def deals(self, start: datetime, end: datetime) -> list[dict]:
        if self.broker is None:
            return []
        try:
            return self.broker.history_deals(start, end)
        except Exception as exc:
            self.errors.append(f"deals MT5: {exc}")
            return []


def _raw_bars(symbol: str, timeframe: str, count: int) -> pd.DataFrame:
    """Barras MT5 con el mismo offset por periodo que usa el forward.

    No se llama a ``MT5Broker.rates`` porque ese método escribe el registro de
    frescura en ``lab.db``; aquí solo se leen velas.
    """
    try:
        import MetaTrader5 as mt5
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise LaneDriftError("MetaTrader5 no instalado") from exc
    tf_map = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }
    key = timeframe.upper()
    if key not in tf_map:
        raise LaneDriftError(f"timeframe no soportado: {timeframe}")
    raw = mt5.copy_rates_from_pos(symbol, tf_map[key], 0, int(count))
    if raw is None or len(raw) == 0:
        raise LaneDriftError(
            f"sin histórico para {symbol} {key}: {mt5.last_error()}"
        )
    from .execution.mt5_offsets import infer_bar_offsets

    frame = pd.DataFrame(raw)
    server_time = pd.to_datetime(frame["time"], unit="s", utc=True)
    offsets = infer_bar_offsets(server_time, key)
    frame["time"] = server_time - pd.to_timedelta(offsets.to_numpy(), unit="h")
    frame = frame.set_index("time").rename(columns={"tick_volume": "volume"})
    cols = ["open", "high", "low", "close", "volume", "spread"]
    return frame[[column for column in cols if column in frame]].astype(float).sort_index()


def _tick_spread(
    market: MarketData | None, symbol: str, moment: datetime
) -> dict | None:
    if market is None:
        return None
    stamp = _parse_stamp(moment)
    ticks = market.ticks(
        symbol, stamp - timedelta(seconds=60), stamp + timedelta(seconds=60)
    )
    if ticks is None or ticks.empty:
        return None
    stamps = pd.to_datetime(ticks["ts"], utc=True)
    window = ticks[
        (stamps >= pd.Timestamp(stamp - timedelta(seconds=60)))
        & (stamps <= pd.Timestamp(stamp + timedelta(seconds=60)))
    ]
    if window.empty:
        window = ticks
    spread = float((window["ask"] - window["bid"]).median())
    mid = float(((window["ask"] + window["bid"]) / 2.0).median())
    if mid <= 0:
        return None
    return {"price": spread, "bps": spread / mid * 10_000.0, "n": int(len(window))}


def _tick_execution_slip(
    market: MarketData | None,
    symbol: str,
    moment: datetime,
    side: int,
    fill: float,
) -> dict | None:
    """Deslizamiento puro: fill frente al ask/bid del tick de ejecución."""
    if market is None or fill is None or fill <= 0:
        return None
    stamp = _parse_stamp(moment)
    ticks = market.ticks(
        symbol, stamp - timedelta(seconds=15), stamp + timedelta(seconds=15)
    )
    if ticks is None or ticks.empty:
        return None
    stamps = pd.to_datetime(ticks["ts"], utc=True)
    position = int((stamps - pd.Timestamp(stamp)).abs().argmin())
    row = ticks.iloc[position]
    expected = float(row["ask"] if side > 0 else row["bid"])
    if expected <= 0:
        return None
    return {
        "slip_bps": float(side) * (float(fill) - expected) / expected * 10_000.0,
        "expected_price": expected,
        "spread_price": float(row["ask"]) - float(row["bid"]),
        "tick_ts": pd.Timestamp(row["ts"]).isoformat(),
    }


def _execution_reference(bars: pd.DataFrame, moment: datetime) -> float | None:
    if bars.empty:
        return None
    stamps = bars.index
    position = int(stamps.searchsorted(pd.Timestamp(moment), side="right") - 1)
    if position < 0:
        return None
    return float(bars["open"].iloc[position])


def _signal_index(
    bars: pd.DataFrame, moment: datetime, timeframe_minutes: int
) -> int | None:
    if bars.empty or timeframe_minutes <= 0:
        return None
    close_times = bars.index + pd.Timedelta(minutes=timeframe_minutes)
    position = int(close_times.searchsorted(pd.Timestamp(moment), side="right") - 1)
    if position < 0:
        return None
    return position


def _entry_minute(value: time | None) -> int | None:
    if value is None:
        return None
    return int(value.hour) * 60 + int(value.minute)


def replay_forward_trade(
    bars: pd.DataFrame,
    target: pd.Series,
    atr_series: pd.Series,
    signal_idx: int,
    side: int,
    *,
    stop_atr: float,
    max_hold: int | None,
    force_exit: time | None,
    timeframe_minutes: int,
) -> dict | None:
    """Reconstruye la operación del forward desde la barra de señal.

    Entra en el open siguiente, stop intrabar (peor precio si hay hueco), y
    sale por señal contraria/plana, ``max_hold`` o corte de sesión.
    """
    if side not in {-1, 1} or signal_idx < 0 or signal_idx >= len(bars):
        return None
    atr_value = float(atr_series.iloc[signal_idx])
    if not math.isfinite(atr_value) or atr_value <= 0 or stop_atr <= 0:
        return None
    entry_idx = signal_idx + 1
    if entry_idx >= len(bars):
        return None
    entry = float(bars["open"].iloc[entry_idx])
    stop = entry - float(side) * float(stop_atr) * atr_value
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    entry_ts = bars.index[entry_idx]
    exit_reason = "fin de datos"
    exit_price = float(bars["close"].iloc[-1])
    exit_idx = len(bars) - 1
    for position in range(entry_idx, len(bars)):
        row = bars.iloc[position]
        if side > 0 and float(row["low"]) <= stop:
            exit_reason = "stop"
            exit_price = (
                float(row["open"]) if float(row["open"]) < stop else stop
            )
            exit_idx = position
            break
        if side < 0 and float(row["high"]) >= stop:
            exit_reason = "stop"
            exit_price = (
                float(row["open"]) if float(row["open"]) > stop else stop
            )
            exit_idx = position
            break
        desired = float(target.iloc[position]) if position < len(target) else 0.0
        held = position - entry_idx
        reason: str | None = None
        if desired == 0.0 or desired == -float(side):
            reason = "señal"
        elif max_hold is not None and int(max_hold) > 0 and held >= int(max_hold):
            reason = "max_hold"
        elif force_exit is not None:
            close_ts = bars.index[position] + pd.Timedelta(
                minutes=timeframe_minutes
            )
            cutoff = close_ts.replace(
                hour=int(force_exit.hour),
                minute=int(force_exit.minute),
                second=0,
                microsecond=0,
            )
            if close_ts >= cutoff:
                reason = "corte de sesión"
        if reason is not None:
            exit_reason = reason
            if reason in {"señal", "max_hold"} and position + 1 < len(bars):
                exit_idx = position + 1
                exit_price = float(bars["open"].iloc[exit_idx])
            else:
                exit_idx = position
                exit_price = float(row["close"])
            break
    exit_ts = bars.index[exit_idx] + pd.Timedelta(minutes=timeframe_minutes)
    signal_ts = bars.index[signal_idx] + pd.Timedelta(minutes=timeframe_minutes)
    return {
        "signal_ts": _parse_stamp(signal_ts),
        "entry_ts": _parse_stamp(entry_ts),
        "exit_ts": _parse_stamp(exit_ts),
        "entry": entry,
        "exit": float(exit_price),
        "stop": float(stop),
        "risk": float(risk),
        "r": float(side) * (float(exit_price) - entry) / risk,
        "side": int(side),
        "reason": exit_reason,
    }


def scan_forward_days(
    bars: pd.DataFrame,
    target: pd.Series,
    atr_series: pd.Series,
    spec: LaneSpec,
    start_day: date,
    end_day: date,
) -> dict[date, dict]:
    """Primera señal de cada día dentro de la ventana congelada del carril."""
    if spec.entry_start is None or spec.entry_end is None:
        return {}
    start_minute = _entry_minute(spec.entry_start)
    end_minute = _entry_minute(spec.entry_end)
    if start_minute is None or end_minute is None:
        return {}
    max_hold = spec.params_dict.get("max_hold")
    out: dict[date, dict] = {}
    last_exit: date | None = None
    for day in pd.date_range(start_day, end_day, freq="D"):
        if day.weekday() >= 5:
            continue
        if last_exit is not None and day.date() <= last_exit:
            continue
        indices = np.flatnonzero(bars.index.date == day.date())
        signal_idx: int | None = None
        side = 0
        for position in indices:
            close_ts = bars.index[position] + pd.Timedelta(
                minutes=spec.timeframe_minutes
            )
            minute = int(close_ts.hour) * 60 + int(close_ts.minute)
            if not (start_minute <= minute < end_minute):
                continue
            value = float(target.iloc[position]) if position < len(target) else 0.0
            if value != 0.0:
                signal_idx = int(position)
                side = 1 if value > 0 else -1
                break
        if signal_idx is None:
            continue
        trade = replay_forward_trade(
            bars,
            target,
            atr_series,
            signal_idx,
            side,
            stop_atr=spec.stop_atr,
            max_hold=int(max_hold) if max_hold is not None else None,
            force_exit=spec.force_exit,
            timeframe_minutes=spec.timeframe_minutes,
        )
        out[day.date()] = {"index": signal_idx, "side": side, "trade": trade}
        if trade is not None and trade.get("exit_ts") is not None:
            last_exit = _parse_stamp(trade["exit_ts"]).date()
    return out


def _entry_side(value: str) -> int:
    return 1 if str(value).lower() in {"long", "buy", "b"} else -1


def _load_orders(con: sqlite3.Connection, bot: str) -> list[dict]:
    rows = con.execute(
        "SELECT ts, side, stop_price, risk_usd, qty, broker_id "
        "FROM orders WHERE bot = ? ORDER BY ts",
        (bot,),
    ).fetchall()
    return [dict(row) for row in rows]


def _nearest_order(
    orders: list[dict], moment: datetime, side: int, tolerance_s: int = 180
) -> dict | None:
    best = None
    best_delta = None
    for row in orders:
        if _entry_side(row.get("side")) != side:
            continue
        try:
            stamp = _parse_stamp(row["ts"])
        except Exception:
            continue
        delta = abs((stamp - moment).total_seconds())
        if delta > tolerance_s:
            continue
        if best_delta is None or delta < best_delta:
            best = row
            best_delta = delta
    return best


def _fill_near(
    con: sqlite3.Connection,
    bot: str,
    moment: datetime,
    side: int,
    tolerance_s: int = 180,
) -> dict | None:
    rows = con.execute(
        "SELECT ts, price, qty, contract_size, commission, swap "
        "FROM fills WHERE bot = ? AND side = ? ORDER BY ts",
        (bot, "buy" if side > 0 else "sell"),
    ).fetchall()
    best = None
    best_delta = None
    for row in rows:
        try:
            stamp = _parse_stamp(row["ts"])
        except Exception:
            continue
        delta = abs((stamp - moment).total_seconds())
        if delta > tolerance_s:
            continue
        if best_delta is None or delta < best_delta:
            best = dict(row)
            best_delta = delta
    return best


def _deal_exit(
    market: MarketData | None,
    spec: LaneSpec,
    entry_ts: datetime,
    side: int,
) -> dict | None:
    if market is None or spec.magic is None:
        return None
    deals = market.deals(entry_ts, entry_ts + timedelta(days=7))
    wanted = "sell" if side > 0 else "buy"
    for deal in sorted(deals, key=lambda item: str(item.get("ts_utc") or "")):
        if int(deal.get("magic") or 0) != int(spec.magic):
            continue
        if str(deal.get("symbol") or "").upper() != spec.symbol.upper():
            continue
        if str(deal.get("side") or "").lower() != wanted:
            continue
        return deal
    return None


def load_forward_trades(
    con: sqlite3.Connection,
    spec: LaneSpec,
    *,
    market: MarketData | None = None,
) -> list[DemoTrade]:
    """Reconstruye operaciones del forward desde ``signals`` + ``fills``."""
    rows = con.execute(
        "SELECT ts, ticker, side, strength, price, reason FROM signals "
        "WHERE bot = ? ORDER BY ts",
        (spec.bot,),
    ).fetchall()
    entries: list[dict] = []
    closes: list[dict] = []
    for row in rows:
        reason = str(row["reason"] or "")
        entry_match = LANE_ENTRY_RE.search(reason)
        if entry_match:
            entries.append(
                {
                    "ts": _parse_stamp(row["ts"]),
                    "side": 1 if entry_match.group(1) == "long" else -1,
                    "price": float(row["price"]) if row["price"] is not None else None,
                    "reason": reason,
                }
            )
            continue
        close_match = LANE_CLOSE_RE.search(reason)
        if close_match:
            closes.append(
                {
                    "ts": _parse_stamp(row["ts"]),
                    "ticket": int(close_match.group(1)),
                    "reason": close_match.group(2).strip(),
                    "price": float(row["price"]) if row["price"] is not None else None,
                }
            )
    orders = _load_orders(con, spec.bot)
    used_closes: set[int] = set()
    trades: list[DemoTrade] = []
    for entry in sorted(entries, key=lambda item: item["ts"]):
        order = _nearest_order(orders, entry["ts"], entry["side"])
        fill = _fill_near(con, spec.bot, entry["ts"], entry["side"])
        ticket = None
        if order is not None and order.get("broker_id") is not None:
            try:
                ticket = int(order["broker_id"])
            except (TypeError, ValueError):
                ticket = None
        if fill is not None and fill.get("qty") is not None:
            qty = abs(float(fill["qty"]))
        elif order is not None and order.get("qty") is not None:
            qty = abs(float(order["qty"]))
        else:
            qty = 0.0
        entry_price = (
            float(fill["price"])
            if fill is not None and fill.get("price") is not None
            else entry["price"]
        )
        if entry_price is None:
            continue
        exit_ts = None
        exit_price = None
        exit_source = "sin datos"
        for index, close in enumerate(closes):
            if index in used_closes:
                continue
            if close["ts"] <= entry["ts"]:
                continue
            if ticket is not None and close["ticket"] != ticket:
                continue
            used_closes.add(index)
            exit_ts = close["ts"]
            exit_price = close["price"]
            exit_source = "signals"
            break
        if exit_ts is None:
            deal = _deal_exit(market, spec, entry["ts"], entry["side"])
            if deal is not None:
                exit_ts = _parse_stamp(deal["ts_utc"])
                exit_price = float(deal["price"])
                exit_source = "mt5_deal"
        stop = (
            float(order["stop_price"])
            if order is not None and order.get("stop_price") is not None
            else None
        )
        risk = abs(entry_price - stop) if stop is not None else None
        r_value = None
        pnl = None
        if exit_price is not None and risk is not None and risk > 0:
            r_value = float(entry["side"]) * (float(exit_price) - entry_price) / risk
            contract = 100_000.0 if spec.symbol.upper() != "US100.CASH" else 1.0
            pnl = (
                float(entry["side"])
                * (float(exit_price) - entry_price)
                * qty
                * contract
            )
        trades.append(
            DemoTrade(
                side=int(entry["side"]),
                entry_ts=entry["ts"],
                entry=float(entry_price),
                qty=float(qty),
                exit_ts=exit_ts,
                exit=float(exit_price) if exit_price is not None else None,
                stop=stop,
                r=r_value,
                pnl=pnl,
                ticket=ticket,
                source=exit_source,
                note=(
                    "cierre sin fill registrado"
                    if exit_price is None
                    else ""
                ),
            )
        )
    return sorted(trades, key=lambda item: item.entry_ts)


def _ea_risk_fraction(ea) -> float:
    from .ea_us100 import load_setfile

    values = load_setfile(ea.setfile)
    if bool(values.get("InpDynRisk", False)):
        return float(values.get("InpDynBase", 1.0)) / 100.0
    return float(values.get("InpRiskPct", 0.35)) / 100.0


def load_ea_trades(
    con: sqlite3.Connection,
    spec: LaneSpec,
    *,
    risk_fraction: float,
) -> list[DemoTrade]:
    """Operaciones cerradas del EA por FIFO de ``fills`` (una posición)."""
    rows = con.execute(
        "SELECT ts, qty, price, commission, swap, contract_size, side "
        "FROM fills WHERE bot = ? ORDER BY ts, id",
        (spec.bot,),
    ).fetchall()
    lots: list[dict] = []
    trades: list[DemoTrade] = []
    risk_usd = LANE_ACCOUNT_SIZE * float(risk_fraction)
    for row in rows:
        side = _entry_side(row["side"])
        qty = abs(float(row["qty"] or 0.0))
        price = float(row["price"] or 0.0)
        if qty <= 0 or price <= 0:
            continue
        contract = float(row["contract_size"] or 1.0)
        fee = float(row["commission"] or 0.0) + float(row["swap"] or 0.0)
        if not lots or lots[0]["side"] == side:
            lots.append(
                {
                    "side": side,
                    "qty": qty,
                    "remaining": qty,
                    "price": price,
                    "ts": _parse_stamp(row["ts"]),
                    "fee": fee,
                    "contract": contract,
                }
            )
            continue
        remaining = qty
        while remaining > 1e-12 and lots and lots[0]["side"] != side:
            lot = lots[0]
            take = min(remaining, float(lot["remaining"]))
            pnl = (
                float(lot["side"])
                * (price - float(lot["price"]))
                * take
                * float(lot["contract"])
            )
            pnl += float(lot["fee"]) * (take / float(lot["qty"])) + fee * (
                take / qty
            )
            risk_price = risk_usd / (take * float(lot["contract"]))
            trades.append(
                DemoTrade(
                    side=int(lot["side"]),
                    entry_ts=lot["ts"],
                    entry=float(lot["price"]),
                    qty=float(take),
                    exit_ts=_parse_stamp(row["ts"]),
                    exit=price,
                    stop=(
                        float(lot["price"]) - float(lot["side"]) * risk_price
                        if risk_price > 0
                        else None
                    ),
                    r=pnl / risk_usd if risk_usd > 0 else None,
                    pnl=pnl,
                    source="fills",
                )
            )
            lot["remaining"] = float(lot["remaining"]) - take
            remaining -= take
            if lot["remaining"] <= 1e-12:
                lots.pop(0)
    for lot in lots:
        trades.append(
            DemoTrade(
                side=int(lot["side"]),
                entry_ts=lot["ts"],
                entry=float(lot["price"]),
                qty=float(lot["remaining"]),
                source="fills",
                note="posición abierta o cierre sin datos",
            )
        )
    return sorted(trades, key=lambda item: item.entry_ts)


def _ny_to_utc(value) -> datetime:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize(ZoneInfo("America/New_York"))
    return _parse_stamp(stamp.tz_convert("UTC"))


def run_ea_backtest(bars: pd.DataFrame, ea) -> tuple[list[dict], float]:
    """Replica congelada del EA sobre las mismas velas del bróker."""
    from .ea_us100 import load_setfile, params_from_set
    from .ea_us100_engine import run as run_engine

    frame = bars.copy().rename(columns={"volume": "tickvol"})
    if "tickvol" not in frame:
        frame["tickvol"] = 0.0
    if "spread" not in frame:
        frame["spread"] = 0.0
    frame.index = (
        pd.DatetimeIndex(frame.index)
        .tz_convert("America/New_York")
        .tz_localize(None)
    )
    values = load_setfile(ea.setfile)
    params = params_from_set(values)
    raw = run_engine(frame, params)
    trades: list[dict] = []
    for row in raw.to_dict("records"):
        side = int(row["d"])
        entry = float(row["ent"])
        risk = float(row["risk"])
        r_value = float(row["r"])
        trades.append(
            {
                "entry_ts": _ny_to_utc(row["t"]),
                "exit_ts": _ny_to_utc(row["t_exit"]),
                "side": side,
                "entry": entry,
                "exit": entry + side * r_value * risk,
                "risk": risk,
                "r": r_value,
                "reason": str(row.get("why") or ""),
            }
        )
    trades.sort(key=lambda item: item["entry_ts"])
    return trades, _ea_risk_fraction(ea)


def _demo_day_map(trades: list[DemoTrade]) -> dict[date, DemoTrade]:
    out: dict[date, DemoTrade] = {}
    for trade in trades:
        out.setdefault(trade.day, trade)
    return out


def _operation(
    *,
    day: date,
    demo: DemoTrade | None,
    bt: dict | None,
    bt_signal: int,
    match: bool | None,
    slip_bps: float | None,
    slip_vs_bt_bps: float | None,
    tick_spread: dict | None,
    costs: dict | None,
    note: str,
    blocked_reason: str | None = None,
    slip_reference: str | None = None,
) -> dict:
    delay = None
    if demo is not None and bt is not None:
        reference = bt.get("signal_ts") or bt.get("entry_ts")
        if reference is not None:
            delay = (demo.entry_ts - reference).total_seconds() / 60.0
    return {
        "day": day.isoformat(),
        "demo_ts": demo.entry_ts.isoformat() if demo else None,
        "demo_side": (
            "long" if demo and demo.side > 0 else "short" if demo else None
        ),
        "demo_entry": demo.entry if demo else None,
        "demo_exit": demo.exit if demo else None,
        "demo_r": demo.r if demo else None,
        "demo_closed": bool(demo and demo.closed),
        "bt_ts": bt["entry_ts"].isoformat() if bt else None,
        "bt_signal_ts": (
            bt["signal_ts"].isoformat()
            if bt and bt.get("signal_ts") is not None
            else None
        ),
        "bt_side": "long" if bt and bt["side"] > 0 else "short" if bt else None,
        "bt_entry": bt["entry"] if bt else None,
        "bt_exit": bt["exit"] if bt else None,
        "bt_r": bt["r"] if bt else None,
        "bt_signal": int(bt_signal),
        "match": match,
        "delay_minutes": delay,
        "slip_bps": slip_bps,
        "slip_vs_bt_bps": slip_vs_bt_bps,
        "spread_bps": tick_spread["bps"] if tick_spread else None,
        "spread_price": tick_spread["price"] if tick_spread else None,
        "assumed_slip_bps": costs["slippage_bps"] if costs else None,
        "assumed_spread_bps": costs["spread_bps"] if costs else None,
        "slip_reference": slip_reference,
        "blocked_reason": blocked_reason,
        "note": note,
    }


def _summarize_lane(
    *,
    spec: LaneSpec,
    demo: list[DemoTrade],
    operations: list[dict],
    bt_signals: int,
    bt_trades: list[dict],
    status_note: str = "",
) -> dict:
    demo_days = {trade.day.isoformat() for trade in demo}
    bt_days = {op["day"] for op in operations if op["bt_signal"] != 0}
    union = demo_days | bt_days
    matched = sum(1 for op in operations if op["match"] is True)
    timely_limit = max(2 * spec.timeframe_minutes, 30)
    timely = sum(
        1
        for op in operations
        if op["match"] is True
        and op.get("delay_minutes") is not None
        and abs(float(op["delay_minutes"])) <= timely_limit
    )
    opposite = sum(
        1
        for op in operations
        if op["match"] is False and op["bt_signal"] != 0
    )
    extra = sum(
        1
        for op in operations
        if op["demo_ts"] is not None and op["bt_signal"] == 0
    )
    missed = sum(
        1 for op in operations if op["demo_ts"] is None and op["bt_signal"] != 0
    )
    slip = _metric_summary([op["slip_bps"] for op in operations])
    slip_vs_bt = _metric_summary(
        [op.get("slip_vs_bt_bps") for op in operations]
    )
    spread = _metric_summary(
        [
            op["spread_bps"]
            for op in operations
            if op["demo_ts"] is not None
        ]
    )
    demo_r = [op["demo_r"] for op in operations if op["demo_r"] is not None]
    bt_r = [
        op["bt_r"]
        for op in operations
        if op["match"] is True and op["bt_r"] is not None
    ]
    drift = [
        float(op["bt_r"]) - float(op["demo_r"])
        for op in operations
        if op["match"] is True
        and op["bt_r"] is not None
        and op["demo_r"] is not None
    ]
    if not demo:
        status = "sin datos"
        reasons = ["0 operaciones demo en la ventana"]
    elif spec.backtest == "none":
        status = "registro"
        reasons = ["sin backtest equivalente"]
    elif bt_signals == 0:
        status = "sin datos"
        reasons = ["el backtest congelado no generó señales en la ventana"]
    else:
        status = "medido"
        reasons = []
    if status_note:
        reasons.append(status_note)
    return {
        "id": spec.id,
        "label": spec.label,
        "kind": spec.kind,
        "symbol": spec.symbol,
        "timeframe": spec.timeframe,
        "account": spec.account,
        "backtest": spec.backtest,
        "backtest_available": spec.backtest != "none",
        "status": status,
        "reasons": reasons,
        "demo": {
            "n": len(demo),
            "closed": sum(1 for trade in demo if trade.closed),
            "open": sum(1 for trade in demo if not trade.closed),
            "first": demo[0].entry_ts.isoformat() if demo else None,
            "last": demo[-1].entry_ts.isoformat() if demo else None,
        },
        "backtest_signals": int(bt_signals),
        "backtest_trades": len(bt_trades),
        "match": {
            "matched": int(matched),
            "timely": int(timely),
            "timely_limit_minutes": int(timely_limit),
            "opposite": int(opposite),
            "missed": int(missed),
            "extra": int(extra),
            "union_days": len(union),
            "match_pct": (matched / len(union)) if union else None,
            "timely_pct": (timely / len(union)) if union else None,
            "precision": (matched / len(demo)) if demo else None,
            "recall": (matched / bt_signals) if bt_signals else None,
        },
        "slippage_bps": slip,
        "slippage_vs_bt_bps": slip_vs_bt,
        "spread_bps": spread,
        "r": {
            "n_pairs": len(drift),
            "demo_total": sum(float(value) for value in demo_r) if demo_r else None,
            "backtest_total": sum(float(value) for value in bt_r) if bt_r else None,
            "drift_total": sum(drift) if drift else None,
            "demo_mean": (
                sum(float(value) for value in demo_r) / len(demo_r)
                if demo_r
                else None
            ),
            "backtest_mean": (
                sum(float(value) for value in bt_r) / len(bt_r) if bt_r else None
            ),
        },
        "operations": operations,
    }


def _blocked_context(
    con: sqlite3.Connection | None, spec: LaneSpec, day: date
) -> str | None:
    if con is None:
        return None
    rows = con.execute(
        "SELECT ts, reason FROM signals WHERE bot = ? AND ts LIKE ? ORDER BY ts",
        (spec.bot, f"{day.isoformat()}%"),
    ).fetchall()
    for row in rows:
        reason = str(row["reason"] or "")
        low = reason.lower()
        if any(
            token in low
            for token in ("blocked", "guard", "skip", "fuera de", "reloj", "sesión")
        ):
            return reason
    return None


def _compare_forward_lane(
    spec: LaneSpec,
    demo: list[DemoTrade],
    bars: pd.DataFrame,
    market: MarketData | None,
    settings: Settings,
    con: sqlite3.Connection | None = None,
) -> dict:
    from .indicators import atr
    from .intraday import STRATEGIES

    if spec.strategy is None or spec.strategy not in STRATEGIES:
        raise LaneDriftError(f"{spec.id}: estrategia desconocida {spec.strategy!r}")
    result = STRATEGIES[spec.strategy](bars, **spec.params_dict)
    target = result.target.reindex(bars.index).fillna(0.0)
    atr_series = atr(bars)
    start_day = min(trade.day for trade in demo)
    end_day = max(trade.day for trade in demo)
    bt_by_day = scan_forward_days(
        bars, target, atr_series, spec, start_day, end_day
    )
    demo_by_day = _demo_day_map(demo)
    operations: list[dict] = []
    for trade in demo:
        bt = bt_by_day.get(trade.day)
        bt_trade = bt["trade"] if bt else None
        bt_signal = int(bt["side"]) if bt else 0
        match = bt_signal == trade.side
        reference = (
            float(bt_trade["entry"])
            if bt_trade is not None
            else _execution_reference(bars, trade.entry_ts)
        )
        slip = _slip_bps(trade.side, trade.entry, reference)
        spread = _tick_spread(market, spec.symbol, trade.entry_ts)
        costs = _assumed_costs(spec.symbol, trade.entry, settings)
        if match:
            note = "coincide"
            if (
                bt_trade is not None
                and bt_trade.get("signal_ts") is not None
            ):
                delay = (
                    trade.entry_ts - bt_trade["signal_ts"]
                ).total_seconds() / 60.0
                if delay > max(2 * spec.timeframe_minutes, 30):
                    note = (
                        f"coincide; entrada demo {delay:.0f} min "
                        "después de la señal BT"
                    )
                    blocked = _blocked_context(con, spec, trade.day)
                    if blocked:
                        note += f"; primer bloqueo: {blocked[:100]}"
        elif bt_signal == -trade.side:
            note = "señal contraria"
        else:
            note = "señal extra (backtest 0)"
        operations.append(
            _operation(
                day=trade.day,
                demo=trade,
                bt=bt_trade,
                bt_signal=bt_signal,
                match=match,
                slip_bps=(
                    _tick_execution_slip(
                        market, spec.symbol, trade.entry_ts, trade.side, trade.entry
                    ) or {}
                ).get("slip_bps"),
                slip_vs_bt_bps=slip,
                tick_spread=spread,
                costs=costs,
                note=note,
                slip_reference="bt_entry" if bt_trade is not None else "bar_open",
            )
        )
    for day, bt in sorted(bt_by_day.items()):
        if day in demo_by_day:
            continue
        bt_trade = bt["trade"]
        spread = _tick_spread(market, spec.symbol, bt_trade["entry_ts"]) if bt_trade else None
        costs = _assumed_costs(
            spec.symbol, bt_trade["entry"] if bt_trade else 0.0, settings
        )
        blocked = _blocked_context(con, spec, day)
        note = "señal perdida (demo no entró)"
        if blocked:
            note = f"señal perdida; demo bloqueado: {blocked[:120]}"
        operations.append(
            _operation(
                day=day,
                demo=None,
                bt=bt_trade,
                bt_signal=int(bt["side"]),
                match=None,
                slip_bps=None,
                slip_vs_bt_bps=None,
                tick_spread=spread,
                costs=costs,
                note=note,
                blocked_reason=blocked,
            )
        )
    operations.sort(key=lambda item: (item["day"], item["demo_ts"] or ""))
    return _summarize_lane(
        spec=spec,
        demo=demo,
        operations=operations,
        bt_signals=len(bt_by_day),
        bt_trades=[bt["trade"] for bt in bt_by_day.values() if bt["trade"]],
    )


def _match_ea_demo(
    demo: list[DemoTrade],
    backtest: list[dict],
    *,
    tolerance_minutes: int = 20,
) -> list[dict]:
    used: set[int] = set()
    operations: list[dict] = []
    for trade in demo:
        same_side: list[tuple[float, int]] = []
        opposite_side: list[tuple[float, int]] = []
        for index, bt in enumerate(backtest):
            if index in used:
                continue
            delta = abs(
                (bt["entry_ts"] - trade.entry_ts).total_seconds()
            ) / 60.0
            if delta > tolerance_minutes:
                continue
            if bt["side"] == trade.side:
                same_side.append((delta, index))
            elif bt["side"] == -trade.side:
                opposite_side.append((delta, index))
        if same_side:
            _, index = min(same_side)
            used.add(index)
            operations.append(
                {
                    "demo": trade,
                    "bt": backtest[index],
                    "match": True,
                    "note": "coincide",
                }
            )
            continue
        if opposite_side:
            _, index = min(opposite_side)
            used.add(index)
            operations.append(
                {
                    "demo": trade,
                    "bt": backtest[index],
                    "match": False,
                    "note": "señal contraria",
                }
            )
            continue
        operations.append(
            {
                "demo": trade,
                "bt": None,
                "match": None,
                "note": "señal extra (backtest 0)",
            }
        )
    return operations


def _compare_ea_lane(
    spec: LaneSpec,
    demo: list[DemoTrade],
    bars: pd.DataFrame,
    market: MarketData | None,
    settings: Settings,
) -> dict:
    from .ea_registry import get_ea

    ea = get_ea(spec.id)
    if ea is None:
        raise LaneDriftError(f"{spec.id}: EA no registrado")
    backtest, risk_fraction = run_ea_backtest(bars, ea)
    start_day = min(trade.day for trade in demo)
    end_day = max(trade.day for trade in demo)
    window = [
        bt
        for bt in backtest
        if start_day <= bt["entry_ts"].date() <= end_day
    ]
    pairs = _match_ea_demo(demo, window)
    demo_by_day = _demo_day_map(demo)
    used_ids = {
        id(item["bt"]) for item in pairs if item["bt"] is not None
    }
    operations: list[dict] = []
    for pair in pairs:
        trade = pair["demo"]
        bt = pair["bt"]
        reference = (
            float(bt["entry"])
            if bt is not None
            else _execution_reference(bars, trade.entry_ts)
        )
        slip = _slip_bps(trade.side, trade.entry, reference)
        spread = _tick_spread(market, spec.symbol, trade.entry_ts)
        costs = _assumed_costs(spec.symbol, trade.entry, settings)
        operations.append(
            _operation(
                day=trade.day,
                demo=trade,
                bt=bt,
                bt_signal=int(bt["side"]) if bt else 0,
                match=pair["match"],
                slip_bps=(
                    _tick_execution_slip(
                        market, spec.symbol, trade.entry_ts, trade.side, trade.entry
                    ) or {}
                ).get("slip_bps"),
                slip_vs_bt_bps=slip,
                tick_spread=spread,
                costs=costs,
                note=pair["note"],
                slip_reference="bt_entry" if bt is not None else "bar_open",
            )
        )
    for bt in window:
        if id(bt) in used_ids:
            continue
        spread = _tick_spread(market, spec.symbol, bt["entry_ts"])
        costs = _assumed_costs(spec.symbol, bt["entry"], settings)
        if bt["entry_ts"].date() in demo_by_day:
            note = "señal BT no emparejada (demo hizo otra cosa)"
        else:
            note = "señal perdida (demo no entró)"
        operations.append(
            _operation(
                day=bt["entry_ts"].date(),
                demo=None,
                bt=bt,
                bt_signal=int(bt["side"]),
                match=None,
                slip_bps=None,
                slip_vs_bt_bps=None,
                tick_spread=spread,
                costs=costs,
                note=note,
            )
        )
    operations.sort(key=lambda item: (item["day"], item["demo_ts"] or ""))
    report = _summarize_lane(
        spec=spec,
        demo=demo,
        operations=operations,
        bt_signals=len(window),
        bt_trades=window,
    )
    report["r"]["risk_fraction"] = risk_fraction
    report["r"]["risk_usd"] = LANE_ACCOUNT_SIZE * risk_fraction
    return report


def _ai_report(con: sqlite3.Connection, spec: LaneSpec) -> dict:
    rows = con.execute(
        "SELECT style, status, COUNT(*) AS n, MIN(ts) AS first, MAX(ts) AS last, "
        "SUM(COALESCE(result_r, r_multiple, 0.0)) AS total_r, "
        "SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END) AS closed "
        "FROM ai_trades GROUP BY style, status ORDER BY style, status"
    ).fetchall()
    styles = []
    total = 0
    first = None
    last = None
    total_r = 0.0
    for row in rows:
        item = dict(row)
        total += int(item["n"])
        total_r += float(item["total_r"] or 0.0)
        if item["first"] and (first is None or str(item["first"]) < first):
            first = str(item["first"])
        if item["last"] and (last is None or str(item["last"]) > last):
            last = str(item["last"])
        styles.append(
            {
                "style": item["style"],
                "status": item["status"],
                "n": int(item["n"]),
                "closed": int(item["closed"] or 0),
                "total_r": float(item["total_r"] or 0.0),
                "first": item["first"],
                "last": item["last"],
            }
        )
    return {
        "id": spec.id,
        "label": spec.label,
        "kind": spec.kind,
        "symbol": spec.symbol,
        "timeframe": spec.timeframe,
        "account": spec.account,
        "backtest": spec.backtest,
        "backtest_available": False,
        "status": "registro",
        "reasons": ["ai_trader no tiene backtest equivalente"],
        "demo": {
            "n": total,
            "closed": sum(item["closed"] for item in styles),
            "open": sum(
                item["n"] - item["closed"] for item in styles
            ),
            "first": first,
            "last": last,
        },
        "backtest_signals": None,
        "backtest_trades": None,
        "match": {
            "matched": None,
            "timely": None,
            "timely_limit_minutes": None,
            "opposite": None,
            "missed": None,
            "extra": None,
            "union_days": None,
            "match_pct": None,
            "timely_pct": None,
            "precision": None,
            "recall": None,
        },
        "slippage_bps": {"n": 0, "mean": None, "p50": None, "p95": None},
        "slippage_vs_bt_bps": {"n": 0, "mean": None, "p50": None, "p95": None},
        "spread_bps": {"n": 0, "mean": None, "p50": None, "p95": None},
        "r": {
            "n_pairs": 0,
            "demo_total": total_r,
            "backtest_total": None,
            "drift_total": None,
            "demo_mean": (total_r / total) if total else None,
            "backtest_mean": None,
        },
        "operations": [],
        "styles": styles,
    }


def build_lane_drift(
    db_path: str | Path,
    *,
    lane: str | None = None,
    settings: Settings | None = None,
    offline: bool = False,
    market: MarketData | None = None,
    specs: list[LaneSpec] | None = None,
) -> dict:
    """Deriva demo vs backtest congelado de los carriles que ya operan."""
    settings = settings or Settings()
    selected = [spec for spec in (specs or lane_specs()) if _lane_matches(spec, lane)]
    if not selected:
        raise LaneDriftError(f"no hay carril que coincida con {lane!r}")
    con = _readonly_connect(db_path)
    own_market = market is None
    market = market or MarketData(settings, db_path=db_path, offline=offline)
    if own_market:
        market.connect()
    reports: list[dict] = []
    try:
        for spec in selected:
            try:
                if spec.kind == "ai":
                    reports.append(_ai_report(con, spec))
                    continue
                if spec.kind == "ea":
                    demo = load_ea_trades(
                        con, spec, risk_fraction=_ea_risk_fraction_for(spec)
                    )
                else:
                    demo = load_forward_trades(con, spec, market=market)
                if not demo:
                    report = _summarize_lane(
                        spec=spec,
                        demo=demo,
                        operations=[],
                        bt_signals=0,
                        bt_trades=[],
                        status_note="sin operaciones demo",
                    )
                    reports.append(report)
                    continue
                bars = market.bars(spec.symbol, spec.timeframe, count=6000)
                if spec.kind == "ea":
                    report = _compare_ea_lane(spec, demo, bars, market, settings)
                else:
                    report = _compare_forward_lane(
                        spec, demo, bars, market, settings, con
                    )
                reports.append(report)
            except Exception as exc:
                reports.append(
                    {
                        "id": spec.id,
                        "label": spec.label,
                        "kind": spec.kind,
                        "symbol": spec.symbol,
                        "timeframe": spec.timeframe,
                        "account": spec.account,
                        "backtest": spec.backtest,
                        "backtest_available": spec.backtest != "none",
                        "status": "sin datos",
                        "reasons": [str(exc)],
                        "demo": {"n": 0, "closed": 0, "open": 0, "first": None, "last": None},
                        "backtest_signals": None,
                        "backtest_trades": None,
                        "match": {
                            "matched": None,
                            "timely": None,
                            "timely_limit_minutes": None,
                            "opposite": None,
                            "missed": None,
                            "extra": None,
                            "union_days": None,
                            "match_pct": None,
                            "timely_pct": None,
                            "precision": None,
                            "recall": None,
                        },
                        "slippage_bps": {"n": 0, "mean": None, "p50": None, "p95": None},
                        "slippage_vs_bt_bps": {"n": 0, "mean": None, "p50": None, "p95": None},
                        "spread_bps": {"n": 0, "mean": None, "p50": None, "p95": None},
                        "r": {
                            "n_pairs": 0,
                            "demo_total": None,
                            "backtest_total": None,
                            "drift_total": None,
                            "demo_mean": None,
                            "backtest_mean": None,
                        },
                        "operations": [],
                    }
                )
    finally:
        con.close()
        if own_market:
            market.close()
    measured = sum(1 for report in reports if report["status"] == "medido")
    summary = {
        "lanes": len(reports),
        "measured": measured,
        "registro": sum(1 for report in reports if report["status"] == "registro"),
        "sin_datos": sum(1 for report in reports if report["status"] == "sin datos"),
        "demo_trades": sum(int(report["demo"]["n"] or 0) for report in reports),
        "matched": sum(
            int(report["match"]["matched"] or 0) for report in reports
        ),
        "missed": sum(int(report["match"]["missed"] or 0) for report in reports),
        "extra": sum(int(report["match"]["extra"] or 0) for report in reports),
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "db": str(Path(db_path).resolve()),
        "read_only": True,
        "mt5": {
            "used": bool(market.used),
            "login_before": market.login_before,
            "login_after": market.login_after,
            "server": market.server,
            "errors": market.errors,
        },
        "summary": summary,
        "lanes": reports,
    }


def _ea_risk_fraction_for(spec: LaneSpec) -> float:
    from .ea_registry import get_ea

    ea = get_ea(spec.id)
    if ea is None:
        raise LaneDriftError(f"{spec.id}: EA no registrado")
    return _ea_risk_fraction(ea)


__all__ = [
    "LANE_ACCOUNT_SIZE",
    "LaneDriftError",
    "LaneSpec",
    "MIN_SLIPPAGE_FILLS",
    "MIN_TRADES",
    "MarketData",
    "build_drift",
    "build_lane_drift",
    "classify_metric",
    "classify_slippage",
    "lane_specs",
    "load_ea_trades",
    "load_forward_trades",
    "replay_forward_trade",
    "run_ea_backtest",
    "scan_forward_days",
]
