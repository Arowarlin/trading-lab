"""Paridad del EA externo: motor vs historial real de MT5 (E1).

Solo lectura. El módulo no envía órdenes: actualiza la caché M5 con velas
cerradas y compara las operaciones del motor con los deals del terminal.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .config import get_settings
from .ea_registry import ExternalEA, get_ea
from .ea_us100 import CACHE, drop_forming_bar, load_setfile, params_from_set
from .ea_us100_engine import run as run_engine
from .execution import get_mt5_broker

POINT = 0.01
BAR_MINUTES = 5
TOLERANCE = pd.Timedelta(minutes=BAR_MINUTES)


class ParityError(RuntimeError):
    pass


@dataclass(frozen=True)
class Trade:
    side: str
    entry_time: pd.Timestamp
    entry_price: float
    exit_time: pd.Timestamp
    exit_price: float
    source: str = ""

    @property
    def sign(self) -> int:
        return 1 if self.side == "long" else -1

    def result_points(self, point: float = POINT) -> float:
        return (self.exit_price - self.entry_price) * self.sign / point


def _naive_ny_to_utc(stamp: Any) -> pd.Timestamp:
    value = pd.Timestamp(stamp)
    if value.tzinfo is None:
        value = value.tz_localize(
            "America/New_York", ambiguous=True, nonexistent="shift_forward"
        )
    return value.tz_convert("UTC")


def _bars_equal(left: pd.Series, right: pd.Series) -> bool:
    for column in ("open", "high", "low", "close", "tickvol", "spread"):
        if column not in left or column not in right:
            continue
        if not np.isclose(
            float(left[column]), float(right[column]), rtol=0.0, atol=1e-9
        ):
            return False
    return True


def _era(ea_id: str) -> ExternalEA:
    ea = get_ea(ea_id)
    if ea is None:
        raise ParityError(f"EA no registrado: {ea_id}")
    return ea


def _raw_frame(raw: Any, offset_hours: float) -> pd.DataFrame:
    if raw is None or len(raw) == 0:
        raise ParityError("Sin datos: copy_rates_range no devolvió velas")
    frame = pd.DataFrame(raw)
    if "time" not in frame.columns:
        raise ParityError("Sin datos: copy_rates_range sin columna time")
    server_time = pd.to_datetime(frame["time"], unit="s", utc=True)
    utc = server_time - pd.Timedelta(hours=float(offset_hours))
    frame.index = pd.DatetimeIndex(
        utc.dt.tz_convert("America/New_York").dt.tz_localize(None)
    )
    frame = frame.rename(columns={"tick_volume": "tickvol"})
    columns = [
        column
        for column in ("open", "high", "low", "close", "tickvol", "spread")
        if column in frame.columns
    ]
    missing = {"open", "high", "low", "close"} - set(columns)
    if missing:
        raise ParityError(
            "Sin datos: faltan columnas " + ", ".join(sorted(missing))
        )
    frame = frame.loc[:, columns].sort_index()
    return frame[~frame.index.duplicated(keep="first")]


def update_cache(
    ea_id: str = "us100-ftmo1",
    *,
    cache: str | Path = CACHE,
    allow_partial_last: bool = True,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Añade velas cerradas a la caché y corrige solo la última si estaba en curso."""

    ea = _era(ea_id)
    path = Path(cache)
    if not path.exists():
        raise ParityError(f"Sin datos: no existe la caché {path}")
    frame = pd.read_parquet(path)
    if frame.empty:
        raise ParityError(f"Sin datos: caché vacía {path}")
    last = frame.index[-1]
    written_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    last_utc = _naive_ny_to_utc(last)

    broker = get_mt5_broker(get_settings(), dry_run=True)
    health_before = broker.connect()
    try:
        mt5 = broker._require()
        mt5.symbol_select(ea.symbol, True)
        offset = float(broker._server_offset or 0.0)
        start_server = (
            last_utc - pd.Timedelta(days=2) + pd.Timedelta(hours=offset)
        ).tz_localize(None)
        end_server = (
            pd.Timestamp(now) + pd.Timedelta(days=1) + pd.Timedelta(hours=offset)
        ).tz_localize(None)
        raw = mt5.copy_rates_range(
            ea.symbol,
            mt5.TIMEFRAME_M5,
            start_server.to_pydatetime(),
            end_server.to_pydatetime(),
        )
        fetched = _raw_frame(raw, offset)
        fetched = drop_forming_bar(
            fetched, timeframe_minutes=BAR_MINUTES, now_utc=now
        )
        if fetched.empty:
            raise ParityError("Sin datos: el terminal no devolvió velas cerradas")
        if last not in fetched.index:
            raise ParityError(
                "Sin datos: la última vela de la caché sigue en formación"
            )

        overlap = fetched.index.intersection(frame.index)
        for stamp in overlap:
            if stamp == last:
                continue
            if not _bars_equal(frame.loc[stamp], fetched.loc[stamp]):
                raise ParityError(
                    f"Sin datos: la vela solapada {stamp} no coincide"
                )

        replaced = None
        if not _bars_equal(frame.loc[last], fetched.loc[last]):
            closed_at = last_utc + pd.Timedelta(minutes=BAR_MINUTES)
            if not allow_partial_last:
                raise ParityError(
                    f"Sin datos: la vela {last} no coincide y no hay autorización"
                )
            if closed_at <= pd.Timestamp(written_at):
                raise ParityError(
                    f"Sin datos: la vela {last} no estaba en formación "
                    f"(cierre {closed_at} <= escritura {written_at})"
                )
            if closed_at > pd.Timestamp(now):
                raise ParityError(
                    f"Sin datos: la vela {last} aún no ha cerrado"
                )
            replaced = {
                "when": str(last),
                "old": {
                    key: float(frame.loc[last, key])
                    for key in ("open", "high", "low", "close", "tickvol", "spread")
                },
                "new": {
                    key: float(fetched.loc[last, key])
                    for key in ("open", "high", "low", "close", "tickvol", "spread")
                },
            }
            frame.loc[last] = fetched.loc[last]

        new_rows = fetched.loc[fetched.index > last]
        combined = pd.concat([frame, new_rows]).sort_index()
        combined = combined[~combined.index.duplicated(keep="first")]
        health_write = broker.health()
        if not health_write.get("identity_ok"):
            raise ParityError("MT5 cambió de identidad antes de escribir")

        temporary = path.with_suffix(path.suffix + ".tmp")
        combined.to_parquet(temporary)
        temporary.replace(path)

        health_after = broker.health()
        if (
            not health_after.get("identity_ok")
            or int(health_after.get("login") or 0)
            != int(health_before.get("login") or 0)
        ):
            raise ParityError("MT5 cambió de login después de escribir")
        return {
            "symbol": ea.symbol,
            "path": str(path),
            "login_before": health_before.get("login"),
            "login_after": health_after.get("login"),
            "overlap": int(len(overlap)),
            "added": int(len(new_rows)),
            "replaced": replaced,
            "last_before": str(last),
            "last_after": str(combined.index[-1]),
            "rows_before": int(len(frame)),
            "rows_after": int(len(combined)),
        }
    finally:
        broker.shutdown()


def _engine_trades(
    frame: pd.DataFrame, values: dict, *, since: pd.Timestamp
) -> list[Trade]:
    raw = run_engine(frame, params_from_set(values))
    if raw is None or raw.empty:
        return []
    out: list[Trade] = []
    for row in raw.itertuples(index=False):
        entry_time = _naive_ny_to_utc(row.t)
        if entry_time < since:
            continue
        side = "long" if int(row.d) > 0 else "short"
        exit_price = float(row.ent) + float(row.r) * float(row.risk) * int(row.d)
        out.append(
            Trade(
                side=side,
                entry_time=entry_time,
                entry_price=float(row.ent),
                exit_time=_naive_ny_to_utc(row.t_exit),
                exit_price=exit_price,
                source="engine",
            )
        )
    return sorted(out, key=lambda item: item.entry_time)


def _real_trades(deals: Iterable[dict], magics: set[int]) -> list[Trade]:
    grouped: dict[int, list[dict]] = {}
    for deal in deals:
        if int(deal.get("magic") or 0) not in magics:
            continue
        grouped.setdefault(int(deal["position_id"]), []).append(deal)
    out: list[Trade] = []
    for rows in grouped.values():
        entries = [row for row in rows if int(row.get("entry") or 0) == 0]
        exits = [row for row in rows if int(row.get("entry") or 0) == 1]
        if len(entries) != 1 or not exits:
            continue
        entry = entries[0]
        volume = sum(float(row.get("volume") or 0.0) for row in exits) or 1.0
        exit_price = sum(
            float(row["price"]) * float(row.get("volume") or 0.0)
            for row in exits
        ) / volume
        exit_time = max(pd.Timestamp(row["ts_utc"]) for row in exits)
        out.append(
            Trade(
                side="long" if entry["side"] == "buy" else "short",
                entry_time=pd.Timestamp(entry["ts_utc"]),
                entry_price=float(entry["price"]),
                exit_time=exit_time,
                exit_price=exit_price,
                source="mt5",
            )
        )
    return sorted(out, key=lambda item: item.entry_time)


def match_trades(
    engine: list[Trade],
    real: list[Trade],
    *,
    tolerance: pd.Timedelta = TOLERANCE,
) -> tuple[list[tuple[Trade, Trade]], list[Trade], list[Trade]]:
    """Empareja por lado y entrada ±1 vela; devuelve matches y huérfanos."""

    used: set[int] = set()
    matches: list[tuple[Trade, Trade]] = []
    for real_trade in real:
        candidates = []
        for index, engine_trade in enumerate(engine):
            if index in used or engine_trade.side != real_trade.side:
                continue
            distance = abs(real_trade.entry_time - engine_trade.entry_time)
            if distance <= tolerance:
                candidates.append((distance, index, engine_trade))
        if not candidates:
            continue
        _, index, engine_trade = min(candidates, key=lambda item: item[0])
        used.add(index)
        matches.append((engine_trade, real_trade))
    engine_only = [
        trade for index, trade in enumerate(engine) if index not in used
    ]
    matched_real = {id(real_trade) for _, real_trade in matches}
    real_only = [trade for trade in real if id(trade) not in matched_real]
    return matches, engine_only, real_only


def _row(engine_trade: Trade, real_trade: Trade) -> dict[str, Any]:
    sign = engine_trade.sign
    entry_diff = (real_trade.entry_price - engine_trade.entry_price) / POINT
    exit_diff = (real_trade.exit_price - engine_trade.exit_price) / POINT
    engine_result = engine_trade.result_points()
    real_result = real_trade.result_points()
    return {
        "side": engine_trade.side,
        "engine_entry": engine_trade.entry_time.isoformat(),
        "real_entry": real_trade.entry_time.isoformat(),
        "entry_diff_pts": entry_diff,
        "exit_diff_pts": exit_diff,
        "engine_result_pts": engine_result,
        "real_result_pts": real_result,
        "result_diff_pts": real_result - engine_result,
        "entry_slip_pts": entry_diff * sign,
        "exit_slip_pts": -exit_diff * sign,
    }


def parity_payload(
    ea_id: str = "us100-ftmo1",
    *,
    since: str = "2026-11-23",
    cache: str | Path = CACHE,
) -> dict[str, Any]:
    ea = _era(ea_id)
    path = Path(cache)
    if not path.exists():
        raise ParityError(f"Sin datos: no existe la caché {path}")
    frame = pd.read_parquet(path)
    setfile = ea.setfile if ea.setfile.exists() else (
        Path("integrations/mt5/us100_ftmo1/US100_FTMO_v3_challenge.set")
    )
    values = load_setfile(setfile)
    since_ts = pd.Timestamp(since)
    if since_ts.tzinfo is None:
        since_ts = since_ts.tz_localize("America/New_York")
    since_utc = since_ts.tz_convert("UTC")
    engine = _engine_trades(frame, values, since=since_utc)

    broker = get_mt5_broker(get_settings(), dry_run=True)
    health_before = broker.connect()
    try:
        start = (since_utc - pd.Timedelta(days=2)).to_pydatetime()
        end = datetime.now(timezone.utc) + timedelta(days=1)
        deals = broker.history_deals(start, end)
        health_after = broker.health()
    finally:
        broker.shutdown()
    if (
        not health_after.get("identity_ok")
        or int(health_after.get("login") or 0)
        != int(health_before.get("login") or 0)
    ):
        raise ParityError("MT5 cambió de identidad al leer el historial")

    real = _real_trades(deals, {int(ea.magic), *ea.managed_magics})
    matches, engine_only, real_only = match_trades(engine, real)
    rows = [_row(engine_trade, real_trade) for engine_trade, real_trade in matches]
    matched = len(matches)
    return {
        "ea": ea.id,
        "symbol": ea.symbol,
        "since": since,
        "login": health_before.get("login"),
        "engine_trades": len(engine),
        "real_trades": len(real),
        "matched": matched,
        "matched_pct": (
            100.0 * matched / len(real) if real else 0.0
        ),
        "engine_only": [trade.__dict__ for trade in engine_only],
        "real_only": [trade.__dict__ for trade in real_only],
        "rows": rows,
        "mean_entry_slip_pts": (
            float(np.mean([row["entry_slip_pts"] for row in rows]))
            if rows
            else None
        ),
        "mean_exit_slip_pts": (
            float(np.mean([row["exit_slip_pts"] for row in rows]))
            if rows
            else None
        ),
    }


__all__ = [
    "CACHE",
    "POINT",
    "ParityError",
    "Trade",
    "match_trades",
    "parity_payload",
    "update_cache",
]
