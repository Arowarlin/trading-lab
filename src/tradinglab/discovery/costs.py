"""Costes multifirma del Discovery Lab.

* ``broker_spreads`` se mide por hora UTC; aquí se convierte a hora **local de
  Nueva York** para que el cambio de horario no desplace el spread.
* ``worst`` usa el máximo entre cuentas por operación (entrada + salida); el
  panel por vela es el máximo de las cuentas y solo fija la senda del motor.
* ``target`` usa una sola cuenta declarada antes de registrar.
* El slippage no medido se toma de ``engine.yaml::assumed_slippage`` y se marca
  como ``assumption``.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from ..config import ROOT
from ..propfund.costs import CostProfile, broker_symbol, load_profile
from ..propfund.instruments import resolve
from ..propfund.models import ConnectionState, Market
from ..propfund.registry import load_registry
from . import fastbt
from .config import EngineConfig, load_engine_config

LAB_DB = ROOT / "data" / "lab.db"
ROUTABLE = {ConnectionState.DEMO, ConnectionState.PAPER}


@dataclass(frozen=True)
class LocalSpread:
    account: str
    instrument: str
    broker_symbol: str
    source: str
    p75_bps: dict[int, float]
    days_by_hour: dict[int, float]
    from_ts_by_hour: dict[int, str]
    to_ts_by_hour: dict[int, str]
    missing_hours: tuple[int, ...]
    issues: tuple[str, ...]

    @property
    def max_p75_bps(self) -> float:
        return max(self.p75_bps.values())


@dataclass(frozen=True)
class AccountCost:
    account: str
    instrument: str
    profile: CostProfile
    spread: LocalSpread
    cost: fastbt.CfdHourlyCosts
    assumed_slippage: float
    slippage_source: str

    def panel(self, bars: pd.DataFrame) -> fastbt.CostPanel:
        return self.cost.panel(bars)


@dataclass(frozen=True)
class CostApplication:
    trades: list[fastbt.Trade]
    daily_r: pd.Series
    cost_by_account: dict[str, float | None]
    worst_account: str | None
    worst_share: float


def _canonical_instrument(instrument: str) -> str:
    try:
        return str(resolve(instrument).id).upper()
    except Exception:  # noqa: BLE001 - se informa como Sin datos
        return str(instrument or "").strip().upper()


def eligible_cost_accounts(instrument: str) -> list[str]:
    """Cuentas CFD no plantilla, demo/paper, que permiten el instrumento."""

    canonical = _canonical_instrument(instrument)
    registry = load_registry()
    return sorted(
        account_id
        for account_id, account in registry.accounts.items()
        if (
            not account.template
            and account.market is Market.CFD
            and account.connection_state in ROUTABLE
            and canonical in account.allowed_instruments
        )
    )


def resolve_cost_accounts(
    instrument: str,
    cost_accounts: Iterable[str] | None = None,
    cost_mode: str = "worst",
) -> tuple[list[str], str]:
    """Valida la lista de cuentas y el modo; devuelve (cuentas, modo)."""

    mode = str(cost_mode or "worst").strip().lower()
    if mode not in {"worst", "target"}:
        raise ValueError(f"cost_mode desconocido: {cost_mode}")
    canonical = _canonical_instrument(instrument)
    registry = load_registry()
    if cost_accounts is None:
        accounts = eligible_cost_accounts(instrument)
    else:
        source = [cost_accounts] if isinstance(cost_accounts, str) else cost_accounts
        accounts = []
        for raw in source:
            account_id = str(raw or "").strip().upper()
            if account_id and account_id not in accounts:
                accounts.append(account_id)
    if not accounts:
        raise ValueError(
            f"Sin datos: no hay cuenta CFD no plantilla que permita {canonical}"
        )
    for account_id in accounts:
        account = registry.accounts.get(account_id)
        if account is None:
            raise ValueError(f"{account_id}: cuenta no registrada en propfund")
        if account.template:
            raise ValueError(f"{account_id}: cuenta plantilla; no se usa para costes")
        if account.market is not Market.CFD:
            raise ValueError(f"{account_id}: no es una cuenta CFD")
        if account.connection_state not in ROUTABLE:
            raise ValueError(
                f"{account_id}: estado {account.connection_state.value}; "
                "solo DEMO/PAPER"
            )
        if canonical not in account.allowed_instruments:
            raise ValueError(f"{account_id}: no permite {canonical}")
    if mode == "target" and len(accounts) != 1:
        raise ValueError("cost_mode target exige exactamente una cuenta")
    return accounts, mode


def assumed_slippage_for(
    instrument: str,
    config: EngineConfig | None = None,
) -> tuple[float, str]:
    """Slippage asumido por lado en unidades de precio; Sin datos si es null."""

    config = config or load_engine_config()
    canonical = _canonical_instrument(instrument)
    value = config.assumed_slippage.for_instrument(canonical)
    if value is None:
        raise ValueError(
            f"Sin datos: slippage asumido de {canonical}; "
            "configura engine.yaml::assumed_slippage"
        )
    return float(value), str(config.assumed_slippage.source or "assumption")


def _read_spread_rows(db_path: Path, symbol: str, source: str) -> list[sqlite3.Row]:
    if not db_path.exists():
        return []
    uri = f"file:{db_path.as_posix()}?mode=ro"
    try:
        con = sqlite3.connect(uri, uri=True, timeout=5)
        con.row_factory = sqlite3.Row
        try:
            return list(
                con.execute(
                    "SELECT hour_utc, median_bps, p75_bps, n_ticks, from_ts, to_ts"
                    " FROM broker_spreads WHERE symbol = ? AND source = ?"
                    " ORDER BY hour_utc",
                    (str(symbol).upper(), str(source)),
                )
            )
        finally:
            con.close()
    except sqlite3.Error:
        return []


def load_local_hour_spreads(
    account_id: str,
    instrument: str,
    *,
    db_path: str | Path | None = None,
    session_tz: str = "America/New_York",
) -> LocalSpread:
    """p75 por hora local NY desde ``broker_spreads``; faltantes → máximo."""

    registry = load_registry()
    account = registry.accounts.get(str(account_id).upper())
    if account is None:
        raise ValueError(f"{account_id}: cuenta no registrada en propfund")
    canonical = _canonical_instrument(instrument)
    broker_name = (account.broker_symbols or {}).get(canonical) or broker_symbol(
        canonical
    )
    source = str(account.spread_source or "broker")
    rows = _read_spread_rows(Path(db_path or LAB_DB), broker_name, source)
    if not rows:
        raise ValueError(
            f"Sin datos: broker_spreads[{source}] sin filas para {broker_name}"
        )
    p75: dict[int, float] = {}
    days: dict[int, float] = {}
    from_ts: dict[int, str] = {}
    to_ts: dict[int, str] = {}
    issues: list[str] = []
    for row in rows:
        value = row["p75_bps"]
        if value is None or not np.isfinite(float(value)):
            continue
        start = pd.Timestamp(row["from_ts"]) if row["from_ts"] else None
        end = pd.Timestamp(row["to_ts"]) if row["to_ts"] else None
        if start is not None and start.tzinfo is None:
            start = start.tz_localize("UTC")
        if end is not None and end.tzinfo is None:
            end = end.tz_localize("UTC")
        local_from = start.tz_convert(session_tz).hour if start is not None else None
        local_to = end.tz_convert(session_tz).hour if end is not None else None
        hour = local_to if local_to is not None else local_from
        if hour is None:
            hour = int(row["hour_utc"])
        if (
            local_from is not None
            and local_to is not None
            and local_from != local_to
        ):
            issues.append(
                f"hora UTC {int(row['hour_utc'])} cruza cambio de hora local "
                f"({local_from}->{local_to}); se usa {local_to}"
            )
        hour = int(hour)
        value = float(value)
        if hour in p75:
            p75[hour] = max(p75[hour], value)
            issues.append(
                f"hora local {hour}: dos filas UTC; se usa el máximo p75"
            )
        else:
            p75[hour] = value
        if start is not None and end is not None:
            span = max(0.0, (end - start).total_seconds() / 86400.0)
            days[hour] = max(days.get(hour, 0.0), float(max(1, math.ceil(span))))
            from_ts[hour] = start.isoformat()
            to_ts[hour] = end.isoformat()
    if not p75:
        raise ValueError(
            f"Sin datos: broker_spreads[{source}] sin p75 para {broker_name}"
        )
    missing = tuple(hour for hour in range(24) if hour not in p75)
    return LocalSpread(
        account=str(account_id).upper(),
        instrument=canonical,
        broker_symbol=broker_name,
        source=source,
        p75_bps=p75,
        days_by_hour=days,
        from_ts_by_hour=from_ts,
        to_ts_by_hour=to_ts,
        missing_hours=missing,
        issues=tuple(issues),
    )


def build_account_cost(
    account_id: str,
    instrument: str,
    *,
    session_tz: str = "America/New_York",
    db_path: str | Path | None = None,
    config: EngineConfig | None = None,
) -> AccountCost:
    config = config or load_engine_config()
    registry = load_registry()
    account = registry.accounts.get(str(account_id).upper())
    if account is None:
        raise ValueError(f"{account_id}: cuenta no registrada en propfund")
    canonical = _canonical_instrument(instrument)
    assumed, source = assumed_slippage_for(canonical, config)
    firm = registry.firm_of(str(account_id).upper()).id
    profile = load_profile(str(account_id).upper(), canonical, firm=firm)
    profile = replace(profile, slippage_price=assumed)
    spread = load_local_hour_spreads(
        str(account_id).upper(),
        canonical,
        db_path=db_path,
        session_tz=session_tz,
    )
    cost = fastbt.CfdHourlyCosts(
        profile,
        spread_bps_by_local_hour=spread.p75_bps,
        session_tz=session_tz,
        missing_hours=spread.missing_hours,
    )
    return AccountCost(
        account=str(account_id).upper(),
        instrument=canonical,
        profile=profile,
        spread=spread,
        cost=cost,
        assumed_slippage=assumed,
        slippage_source=source,
    )


class CostBook:
    """Libro de costes por cuenta; ``worst`` aplica el máximo por operación."""

    market = "cfd"

    def __init__(
        self,
        accounts: list[AccountCost],
        *,
        mode: str,
        session_tz: str,
    ) -> None:
        if not accounts:
            raise ValueError("Sin datos: CostBook sin cuentas")
        self.accounts = list(accounts)
        self.mode = str(mode).lower()
        if self.mode not in {"worst", "target"}:
            raise ValueError(f"cost_mode desconocido: {mode}")
        if self.mode == "target" and len(self.accounts) != 1:
            raise ValueError("target exige exactamente una cuenta")
        self.session_tz = str(session_tz)
        self._panels: list[fastbt.CostPanel] | None = None
        self._bars_id: int | None = None
        self._worst_panel: fastbt.CostPanel | None = None

    @property
    def account_ids(self) -> list[str]:
        return [item.account for item in self.accounts]

    def label(self) -> str:
        return f"{self.mode}:{'+'.join(self.account_ids)}:{self.accounts[0].instrument}"

    def panel(self, bars: pd.DataFrame) -> fastbt.CostPanel:
        if self._panels is not None and self._bars_id == id(bars):
            assert self._worst_panel is not None
            return self._worst_panel
        panels = [item.panel(bars) for item in self.accounts]
        entry = np.max(np.vstack([item.entry_bps for item in panels]), axis=0)
        stop = np.max(np.vstack([item.stop_bps for item in panels]), axis=0)
        target = np.max(np.vstack([item.target_bps for item in panels]), axis=0)
        spread = np.max(np.vstack([item.spread_bps for item in panels]), axis=0)
        self._panels = panels
        self._bars_id = id(bars)
        self._worst_panel = fastbt.CostPanel(
            entry_bps=entry,
            stop_bps=stop,
            target_bps=target,
            spread_bps=spread,
        )
        return self._worst_panel

    def apply(
        self,
        trades: Iterable[fastbt.Trade],
        *,
        session_tz: str | None = None,
        point: float = 0.01,
    ) -> CostApplication:
        if self._panels is None:
            raise ValueError("CostBook.apply necesita panel(bars) antes")
        tz = str(session_tz or self.session_tz)
        adjusted: list[fastbt.Trade] = []
        cost_values: dict[str, list[float]] = {item.account: [] for item in self.accounts}
        worst_flags: list[str | None] = []
        for trade in trades:
            per_account: dict[str, tuple[float, float, float]] = {}
            for item, panel in zip(self.accounts, self._panels):
                entry_bps = float(panel.entry_bps[trade.entry_index])
                exit_bps = (
                    float(panel.target_bps[trade.exit_index])
                    if trade.reason == "target"
                    else float(panel.stop_bps[trade.exit_index])
                )
                risk = trade.risk_price
                if risk is None or not np.isfinite(float(risk)) or float(risk) <= 0:
                    continue
                rc = (entry_bps + exit_bps) / 10_000.0 * trade.entry_price / float(risk)
                per_account[item.account] = (rc, entry_bps, exit_bps)
                cost_values[item.account].append(rc)
            if not per_account:
                adjusted.append(trade)
                worst_flags.append(None)
                continue
            worst_account = max(per_account, key=lambda name: per_account[name][0])
            rc, entry_bps, exit_bps = per_account[worst_account]
            r_net = trade.r_gross - rc if trade.r_gross is not None else None
            adjusted.append(
                replace(
                    trade,
                    entry_cost_bps=entry_bps,
                    exit_cost_bps=exit_bps,
                    r_cost=rc,
                    r_net=r_net,
                )
            )
            worst_flags.append(worst_account)
        daily: dict[Any, float] = {}
        for trade in adjusted:
            if trade.r_net is None or not np.isfinite(float(trade.r_net)):
                continue
            day = trade.exit_time.tz_convert(tz).date()
            daily[day] = daily.get(day, 0.0) + float(trade.r_net)
        daily_r = pd.Series(daily, dtype=float).sort_index()
        if len(daily_r):
            daily_r.index = pd.to_datetime(daily_r.index)
        daily_r.name = "r"
        cost_by_account = {
            name: (float(np.median(values)) if values else None)
            for name, values in cost_values.items()
        }
        if self.mode == "target":
            worst_account = self.accounts[0].account
        else:
            valid = {
                name: value
                for name, value in cost_by_account.items()
                if value is not None
            }
            worst_account = (
                max(valid, key=lambda name: valid[name]) if valid else None
            )
        valid_flags = [name for name in worst_flags if name is not None]
        worst_share = (
            sum(1 for name in valid_flags if name == worst_account) / len(valid_flags)
            if valid_flags and worst_account is not None
            else 0.0
        )
        return CostApplication(
            trades=adjusted,
            daily_r=daily_r,
            cost_by_account=cost_by_account,
            worst_account=worst_account,
            worst_share=worst_share,
        )


def build_cost_book(
    instrument: str,
    *,
    accounts: Iterable[str] | None = None,
    mode: str = "worst",
    session_tz: str = "America/New_York",
    db_path: str | Path | None = None,
    config: EngineConfig | None = None,
) -> CostBook:
    selected, selected_mode = resolve_cost_accounts(instrument, accounts, mode)
    items = [
        build_account_cost(
            account,
            instrument,
            session_tz=session_tz,
            db_path=db_path,
            config=config,
        )
        for account in selected
    ]
    return CostBook(items, mode=selected_mode, session_tz=session_tz)


def build_cost_book_for_setup(setup: Any) -> CostBook:
    """Para workers de campañas nuevas; las antiguas usan la ruta legacy."""

    return build_cost_book(
        setup.instrument,
        accounts=setup.cost_accounts,
        mode=setup.cost_mode,
        session_tz=setup.session_tz,
        db_path=LAB_DB,
    )


def apply_result(
    book: CostBook,
    result: fastbt.FastResult,
    *,
    session_tz: str,
    point: float = 0.01,
) -> tuple[CostApplication, dict[str, Any]]:
    """Aplica el peor por operación y devuelve métricas con metadatos."""

    from . import metrics as metrics_module

    applied = book.apply(result.trades, session_tz=session_tz, point=point)
    payload = metrics_module.summarize(
        applied.trades, applied.daily_r, point=point
    )
    costs = [
        float(trade.r_cost)
        for trade in applied.trades
        if trade.r_cost is not None and np.isfinite(float(trade.r_cost))
    ]
    payload["cost_r"] = float(np.median(costs)) if costs else None
    payload["cost_by_account"] = applied.cost_by_account
    payload["worst_account"] = applied.worst_account
    payload["worst_share"] = applied.worst_share
    payload["cost_accounts"] = book.account_ids
    payload["cost_mode"] = book.mode
    payload["slippage_assumption"] = {
        item.instrument: {
            "value": item.assumed_slippage,
            "source": item.slippage_source,
        }
        for item in book.accounts
    }
    return applied, payload


__all__ = [
    "AccountCost",
    "CostApplication",
    "CostBook",
    "LocalSpread",
    "apply_result",
    "assumed_slippage_for",
    "build_account_cost",
    "build_cost_book",
    "build_cost_book_for_setup",
    "eligible_cost_accounts",
    "load_local_hour_spreads",
    "resolve_cost_accounts",
]
