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

from ..config import DEFAULT_DB
from ..propfund.costs import CostProfile, SwapSpec, broker_symbol, load_profile
from ..propfund.instruments import resolve
from ..propfund.models import ConnectionState, Market
from ..propfund.registry import load_registry
from . import fastbt
from .config import EngineConfig, load_engine_config

# Misma ruta que config.DEFAULT_DB: ROOT/data/lab.db salvo en la suite de tests
# (TRADINGLAB_DB), que los workers del pool heredan (ENG-1 F2b).
LAB_DB = DEFAULT_DB
ROUTABLE = {ConnectionState.DEMO, ConnectionState.PAPER}


@dataclass(frozen=True)
class LocalSpread:
    account: str
    instrument: str
    broker_symbol: str
    source: str
    p75_bps: dict[int, float]
    median_bps: dict[int, float]
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
    cost: fastbt.CfdProfileCosts
    assumed_slippage: float
    slippage_source: str

    def panel(self, bars: pd.DataFrame) -> fastbt.CostPanel:
        return self.cost.panel(bars)

    def p75_panel(self, bars: pd.DataFrame) -> fastbt.CostPanel:
        return self.cost.p75_panel(bars)

    @property
    def swap(self) -> SwapSpec | None:
        return SwapSpec.from_profile(self.profile)


@dataclass(frozen=True)
class CostApplication:
    trades: list[fastbt.Trade]
    daily_r: pd.Series
    cost_by_account: dict[str, float | None]
    worst_account: str | None
    worst_share: float
    best_account: str | None
    best_share: float
    selected_account: str | None
    selected_share: float

    @property
    def cost_values(self) -> dict[str, float | None]:
        """Alias heredado de la rama de cesta; mismo contenido que cost_by_account."""

        return self.cost_by_account


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
    cost_mode: str = "best",
) -> tuple[list[str], str]:
    """Valida la lista de cuentas y el modo; devuelve (cuentas, modo)."""

    mode = str(cost_mode or "best").strip().lower()
    if mode not in {"worst", "best", "target"}:
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
    median: dict[int, float] = {}
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
        median_value = row["median_bps"]
        if median_value is not None and np.isfinite(float(median_value)):
            median[hour] = max(
                median.get(int(hour), 0.0), float(median_value)
            )
        if start is not None and end is not None:
            span = max(0.0, (end - start).total_seconds() / 86400.0)
            days[hour] = max(days.get(hour, 0.0), float(max(1, math.ceil(span))))
            from_ts[hour] = start.isoformat()
            to_ts[hour] = end.isoformat()
    if not p75:
        raise ValueError(
            f"Sin datos: broker_spreads[{source}] sin p75 para {broker_name}"
        )
    for hour, value in p75.items():
        median.setdefault(int(hour), float(value))
    missing = tuple(hour for hour in range(24) if hour not in p75)
    return LocalSpread(
        account=str(account_id).upper(),
        instrument=canonical,
        broker_symbol=broker_name,
        source=source,
        p75_bps=p75,
        median_bps=median,
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
    spread_model: str | None = None,
    cost_model_version: int = 1,
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
    from .spread_history import (
        choose_spread_model,
        has_historical_ask,
        historical_spread_provider,
    )

    has_ask = has_historical_ask(canonical)
    model = choose_spread_model(
        cost_model_version=cost_model_version,
        configured=spread_model or config.discovery.spread_model,
        has_ask=has_ask,
    )
    swap_override = None
    if int(cost_model_version) >= 2 and config.swap.mode == "historical":
        from .swap_history import historical_swap_spec

        swap_override, _reason = historical_swap_spec(profile)
    if model == "hourly_median":
        cost = fastbt.CfdHourlyCosts(
            profile,
            spread_bps_by_local_hour=spread.median_bps,
            session_tz=session_tz,
            missing_hours=spread.missing_hours,
            swap_override=swap_override,
        )
    elif model == "historical_scaled":
        starts = [value for value in spread.from_ts_by_hour.values() if value]
        ends = [value for value in spread.to_ts_by_hour.values() if value]
        provider = historical_spread_provider(
            canonical,
            session_tz=session_tz,
            broker_median_by_hour=spread.median_bps,
            start=min(starts) if starts else None,
            end=max(ends) if ends else None,
        )
        cost = fastbt.CfdHourlyMedianCosts(
            profile,
            spread_bps_by_local_hour=spread.median_bps,
            p75_bps_by_local_hour=spread.p75_bps,
            session_tz=session_tz,
            provider=provider,
            missing_hours=spread.missing_hours,
            swap_override=swap_override,
        )
    else:
        cost = fastbt.CfdHourlyCosts(
            profile,
            spread_bps_by_local_hour=spread.p75_bps,
            session_tz=session_tz,
            missing_hours=spread.missing_hours,
            swap_override=swap_override,
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
    swap_managed = True

    def __init__(
        self,
        accounts: list[AccountCost],
        *,
        mode: str,
        session_tz: str,
        cost_model_version: int = 1,
    ) -> None:
        if not accounts:
            raise ValueError("Sin datos: CostBook sin cuentas")
        self.accounts = list(accounts)
        self.cost_model_version = int(cost_model_version)
        if self.cost_model_version not in {1, 2}:
            raise ValueError(
                f"cost_model_version inválida: {cost_model_version}"
            )
        self.mode = str(mode).lower()
        if self.mode not in {"worst", "best", "target"}:
            raise ValueError(f"cost_mode desconocido: {mode}")
        if self.mode == "target" and len(self.accounts) != 1:
            raise ValueError("target exige exactamente una cuenta")
        self.session_tz = str(session_tz)
        self.swap_allow_credit = bool(
            load_engine_config().discovery.swap_credit
        )
        self._panels: list[fastbt.CostPanel] | None = None
        self._bars_id: int | None = None
        self._worst_panel: fastbt.CostPanel | None = None

    @property
    def account_ids(self) -> list[str]:
        return [item.account for item in self.accounts]

    @property
    def swap(self):
        """Swap representativo de la primera cuenta para el control de deriva."""

        return self.accounts[0].swap

    def label(self) -> str:
        return f"{self.mode}:{'+'.join(self.account_ids)}:{self.accounts[0].instrument}"

    def panel(self, bars: pd.DataFrame) -> fastbt.CostPanel:
        if self._panels is not None and self._bars_id == id(bars):
            assert self._worst_panel is not None
            return self._worst_panel
        panels = [item.panel(bars) for item in self.accounts]
        reducer = np.min if self.mode == "best" else np.max
        spread = reducer(np.vstack([item.spread_bps for item in panels]), axis=0)
        slip = reducer(np.vstack([item.slip_bps for item in panels]), axis=0)
        comm = reducer(np.vstack([item.comm_bps for item in panels]), axis=0)
        legacy: dict[str, np.ndarray] = {}
        if self.cost_model_version == 1:
            legacy = {
                "legacy_entry_bps": reducer(
                    np.vstack([item.entry_bps for item in panels]), axis=0
                ),
                "legacy_stop_bps": reducer(
                    np.vstack([item.stop_bps for item in panels]), axis=0
                ),
                "legacy_target_bps": reducer(
                    np.vstack([item.target_bps for item in panels]), axis=0
                ),
            }
        self._panels = panels
        self._bars_id = id(bars)
        self._worst_panel = fastbt.CostPanel(
            spread_bps=spread,
            slip_bps=slip,
            comm_bps=comm,
            **legacy,
        )
        return self._worst_panel

    def p75_panel(self, bars: pd.DataFrame) -> fastbt.CostPanel:
        """Panel de estrés con el p75 de cada cuenta (escenario ``spread_p75``)."""

        panels = [item.p75_panel(bars) for item in self.accounts]
        reducer = np.min if self.mode == "best" else np.max
        spread = reducer(np.vstack([item.spread_bps for item in panels]), axis=0)
        slip = reducer(np.vstack([item.slip_bps for item in panels]), axis=0)
        comm = reducer(np.vstack([item.comm_bps for item in panels]), axis=0)
        legacy: dict[str, np.ndarray] = {}
        if self.cost_model_version == 1:
            legacy = {
                "legacy_entry_bps": reducer(
                    np.vstack([item.entry_bps for item in panels]), axis=0
                ),
                "legacy_stop_bps": reducer(
                    np.vstack([item.stop_bps for item in panels]), axis=0
                ),
                "legacy_target_bps": reducer(
                    np.vstack([item.target_bps for item in panels]), axis=0
                ),
            }
        return fastbt.CostPanel(
            spread_bps=spread,
            slip_bps=slip,
            comm_bps=comm,
            **legacy,
        )

    def apply(
        self,
        trades: Iterable[fastbt.Trade],
        *,
        session_tz: str | None = None,
        point: float | None = None,
    ) -> CostApplication:
        """Aplica coste por operación. ``point`` se conserva por compatibilidad
        y no se usa aquí; el slippage del escenario vive en ``retester``."""
        if self._panels is None:
            raise ValueError("CostBook.apply necesita panel(bars) antes")
        tz = str(session_tz or self.session_tz)
        adjusted: list[fastbt.Trade] = []
        cost_values: dict[str, list[float]] = {item.account: [] for item in self.accounts}
        best_flags: list[str | None] = []
        worst_flags: list[str | None] = []
        selected_flags: list[str | None] = []
        for trade in trades:
            per_account: dict[str, tuple[float, float, float, float, float, float, float, str | None]] = {}
            for item, panel in zip(self.accounts, self._panels):
                risk = trade.risk_price
                if risk is None or not np.isfinite(float(risk)) or float(risk) <= 0:
                    continue
                e = int(trade.entry_index)
                x = int(trade.exit_index)
                spread_r = slip_r = comm_r = None
                if self.cost_model_version >= 2:
                    comm_bps_sum = float(
                        panel.comm_bps[e] + panel.comm_bps[x]
                    )
                    slip_bps_sum = float(panel.slip_bps[e] + panel.slip_bps[x])
                    entry_bps = float(
                        panel.comm_bps[e]
                        + panel.slip_bps[e]
                        + (panel.spread_bps[e] if trade.side == "long" else 0.0)
                    )
                    if trade.reason == "target":
                        exit_bps = float(panel.comm_bps[x])
                        spread_trade = (
                            float(panel.spread_bps[e])
                            if trade.side == "long"
                            else 0.0
                        )
                    elif trade.reason == "stop":
                        exit_bps = float(panel.comm_bps[x] + panel.slip_bps[x])
                        spread_trade = (
                            float(panel.spread_bps[e])
                            if trade.side == "long"
                            else 0.0
                        )
                    else:
                        exit_bps = float(
                            panel.comm_bps[x]
                            + panel.slip_bps[x]
                            + (
                                panel.spread_bps[x]
                                if trade.side == "short"
                                else 0.0
                            )
                        )
                        spread_trade = (
                            float(panel.spread_bps[e])
                            if trade.side == "long"
                            else float(panel.spread_bps[x])
                        )
                    factor = trade.entry_price / float(risk) / 10_000.0
                    comm_r = comm_bps_sum * factor
                    slip_r = slip_bps_sum * factor
                    spread_r = spread_trade * factor
                else:
                    entry_bps = float(panel.entry_bps[e])
                    exit_bps = (
                        float(panel.target_bps[x])
                        if trade.reason == "target"
                        else float(panel.stop_bps[x])
                    )
                rc = (entry_bps + exit_bps) / 10_000.0 * trade.entry_price / float(risk)
                swap_r = 0.0
                swap_source = None
                swap = getattr(item, "swap", None)
                if swap is not None:
                    if hasattr(swap, "r_with_source"):
                        swap_r, swap_source = swap.r_with_source(
                            side=trade.side,
                            entry_price=trade.entry_price,
                            risk_price=float(risk),
                            entry_time=trade.entry_time,
                            exit_time=trade.exit_time,
                            allow_credit=self.swap_allow_credit,
                        )
                    else:
                        swap_r = swap.r(
                            side=trade.side,
                            entry_price=trade.entry_price,
                            risk_price=float(risk),
                            entry_time=trade.entry_time,
                            exit_time=trade.exit_time,
                            allow_credit=self.swap_allow_credit,
                        )
                rc -= swap_r
                per_account[item.account] = (
                    rc, entry_bps, exit_bps, swap_r, spread_r, slip_r, comm_r,
                    swap_source,
                )
                cost_values[item.account].append(rc)
            if not per_account:
                adjusted.append(trade)
                best_flags.append(None)
                worst_flags.append(None)
                selected_flags.append(None)
                continue
            best_name = min(per_account, key=lambda name: per_account[name][0])
            worst_name = max(per_account, key=lambda name: per_account[name][0])
            if self.mode == "best":
                selected_name = best_name
            elif self.mode == "worst":
                selected_name = worst_name
            else:
                selected_name = self.accounts[0].account
            rc, entry_bps, exit_bps, swap_r, spread_r, slip_r, comm_r, swap_source = per_account[selected_name]
            r_net = trade.r_gross - rc if trade.r_gross is not None else None
            adjusted.append(
                replace(
                    trade,
                    entry_cost_bps=entry_bps,
                    exit_cost_bps=exit_bps,
                    r_cost=rc,
                    r_net=r_net,
                    swap_r=swap_r,
                    swap_source=swap_source,
                    selected_account=selected_name,
                    spread_r=spread_r,
                    slip_r=slip_r,
                    comm_r=comm_r,
                )
            )
            best_flags.append(best_name)
            worst_flags.append(worst_name)
            selected_flags.append(selected_name)
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
        valid = {
            name: value for name, value in cost_by_account.items() if value is not None
        }
        if self.mode == "target":
            best_account = self.accounts[0].account
            worst_account = best_account
            selected_account = best_account
        else:
            best_account = min(valid, key=lambda name: valid[name]) if valid else None
            worst_account = max(valid, key=lambda name: valid[name]) if valid else None
            selected_account = (
                best_account if self.mode == "best" else worst_account
            )
        valid_best = [name for name in best_flags if name is not None]
        valid_worst = [name for name in worst_flags if name is not None]
        valid_selected = [name for name in selected_flags if name is not None]

        def _share(values: list[str], account: str | None) -> float:
            if not values or account is None:
                return 0.0
            return sum(1 for name in values if name == account) / len(values)

        return CostApplication(
            trades=adjusted,
            daily_r=daily_r,
            cost_by_account=cost_by_account,
            worst_account=worst_account,
            worst_share=_share(valid_worst, worst_account),
            best_account=best_account,
            best_share=_share(valid_best, best_account),
            selected_account=selected_account,
            selected_share=_share(valid_selected, selected_account),
        )


def build_cost_book(
    instrument: str,
    *,
    accounts: Iterable[str] | None = None,
    mode: str = "best",
    session_tz: str = "America/New_York",
    db_path: str | Path | None = None,
    config: EngineConfig | None = None,
    cost_model_version: int = 1,
    spread_model: str | None = None,
) -> CostBook:
    selected, selected_mode = resolve_cost_accounts(instrument, accounts, mode)
    items = [
        build_account_cost(
            account,
            instrument,
            session_tz=session_tz,
            db_path=db_path,
            config=config,
            cost_model_version=cost_model_version,
            spread_model=spread_model,
        )
        for account in selected
    ]
    return CostBook(
        items,
        mode=selected_mode,
        session_tz=session_tz,
        cost_model_version=cost_model_version,
    )


def build_cost_book_for_setup(setup: Any) -> CostBook:
    """Para workers de campañas nuevas; las antiguas usan la ruta legacy."""

    return build_cost_book(
        setup.instrument,
        accounts=setup.cost_accounts,
        mode=setup.cost_mode,
        session_tz=setup.session_tz,
        db_path=LAB_DB,
        cost_model_version=int(getattr(setup, "cost_model_version", 1)),
        spread_model=getattr(setup, "spread_model", None),
    )


def default_cost_model_version() -> int:
    """Versión para evaluaciones nuevas sin campaña guardada."""

    return int(load_engine_config().discovery.default_cost_model_version)


def apply_result(
    book: CostBook,
    result: fastbt.FastResult,
    *,
    session_tz: str,
    point: float,
    max_cost_r: float | None = None,
) -> tuple[CostApplication, dict[str, Any]]:
    """Aplica el coste del modo y devuelve métricas con metadatos."""

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
    payload["best_account"] = applied.best_account
    payload["best_share"] = applied.best_share
    payload["selected_account"] = applied.selected_account
    payload["selected_share"] = applied.selected_share
    payload["cost_accounts"] = book.account_ids
    payload["cost_mode"] = book.mode
    payload["cost_viable_by_account"] = {
        name: (
            None
            if value is None or max_cost_r is None
            else bool(float(value) <= float(max_cost_r))
        )
        for name, value in applied.cost_by_account.items()
    }
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
