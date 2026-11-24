"""Motor rápido de eventos del Discovery Lab, con paridad verificada.

La semántica del modo ``open_next`` copia la de ``tradinglab.intraday.
run_event_backtest`` (protegido, solo lectura): entrada en el open de la
primera vela permitida posterior a la señal; stop antes que objetivo; huecos
al peor precio; salida forzada al cierre; costes en bps del nocional de
entrada. El modo ``close_signal`` existe **solo** para replicar la serie
close-to-close de ``backtest_intraday`` en el test de paridad.

El núcleo se escribe una sola vez y se compila con numba (``@njit``) si está
disponible; si no, la misma función corre en Python puro. Los costes CFD se
construyen con ``tradinglab.propfund.costs`` y los futuros con comisión y fees
por contrato; si falta un componente se lanza ``MissingCostData`` ("Sin
datos"), nunca se asume 0.

Esto no carga datos ni envía órdenes: recibe barras ya cargadas (Fase 1b,
``discovery.data_sources``) y devuelve operaciones y métricas.

Una sola posición simultánea: las señales que llegan con una posición abierta
se ignoran. La fecha de ``max_trades_per_day`` y los cortes de sesión,
``flat_at`` y cierre forzado se evalúan en la zona del instrumento
(``RunLimits.session_tz``); ``time_exit_bars`` cuenta barras desde la entrada.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any, Mapping

import numpy as np
import pandas as pd

from ..indicators import atr as atr_series
from ..propfund.costs import CostProfile, SwapSpec, estimate_cfd, estimate_futures
from ..propfund.instruments import resolve
from ..propfund.models import Market
from .compiler import Signals
from .config import load_engine_config
from .metrics import summarize

try:  # pragma: no cover - la rama depende del entorno
    from numba import njit
except ImportError:  # pragma: no cover
    njit = None

HAVE_NUMBA = njit is not None
_BACKEND_ENV = "TRADINGLAB_FASTBT_BACKEND"
_DISABLED = os.environ.get(_BACKEND_ENV, "").strip().lower() in {"python", "off", "0"}

REASONS = {
    1: "stop",
    2: "target",
    3: "force_exit",
    4: "time_exit",
    5: "opposite_signal",
    6: "end_of_data",
    7: "signal_end",
    8: "calendar_exit",
}


class FastBtError(ValueError):
    pass


class MissingCostData(FastBtError):
    """Falta un dato de coste: nunca se sustituye por 0."""


# ---------------------------------------------------------------------------
# Entradas
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExitSpec:
    """Stops, objetivos y salidas extra.

    ``stop_kind``: ``atr``, ``pct``, ``fixed`` o ``None`` (solo close_signal).
    ``target_kind``: ``rr``, ``pct``, ``fixed`` o ``None``.
    """

    stop: str | None = "atr"
    stop_mult: float = 1.5
    stop_n: int = 14
    stop_price: float | None = None
    target: str | None = "rr"
    target_rr: float = 2.0
    target_pct: float | None = None
    target_price: float | None = None
    breakeven_at_r: float | None = None
    trail_atr_mult: float | None = None
    trail_n: int = 14
    time_exit_bars: int | None = None
    opposite_signal: bool = False
    on_signal_end: bool = False

    def validated(self) -> "ExitSpec":
        if self.stop not in {None, "atr", "pct", "fixed"}:
            raise FastBtError(f"stop inválido: {self.stop!r}")
        if self.target not in {None, "rr", "pct", "fixed"}:
            raise FastBtError(f"objetivo inválido: {self.target!r}")
        if self.stop == "atr" and (self.stop_mult <= 0 or self.stop_n < 1):
            raise FastBtError("stop atr necesita mult > 0 y n >= 1")
        if self.stop == "pct" and (self.stop_mult <= 0):
            raise FastBtError("stop pct necesita mult > 0")
        if self.stop == "fixed" and (self.stop_price is None or self.stop_price <= 0):
            raise FastBtError("stop fixed necesita stop_price > 0")
        if self.target == "rr" and self.target_rr <= 0:
            raise FastBtError("objetivo rr necesita rr > 0")
        if self.target == "pct" and (self.target_pct is None or self.target_pct <= 0):
            raise FastBtError("objetivo pct necesita target_pct > 0")
        if self.target == "fixed" and (
            self.target_price is None or self.target_price <= 0
        ):
            raise FastBtError("objetivo fixed necesita target_price > 0")
        if self.breakeven_at_r is not None and self.breakeven_at_r <= 0:
            raise FastBtError("breakeven_at_r debe ser > 0")
        if self.trail_atr_mult is not None and (
            self.trail_atr_mult <= 0 or self.trail_n < 1
        ):
            raise FastBtError("trailing necesita mult > 0 y n >= 1")
        if self.time_exit_bars is not None and self.time_exit_bars < 1:
            raise FastBtError("time_exit_bars debe ser >= 1")
        return self


@dataclass(frozen=True)
class RunLimits:
    """Sesión (zona del instrumento), límites y modo de ejecución."""

    session_tz: str = "UTC"
    session_start: str = "00:00"
    session_end: str = "00:00"
    flat_at: str | None = None
    weekdays: tuple[int, ...] = (0, 1, 2, 3, 4)
    max_trades_per_day: int | None = None
    cooldown_bars: int = 0
    # D1: la señal del cierre se ejecuta en el open del día siguiente; no se
    # cancela al cambiar ``day_id``. En intradía se mantiene la cancelación.
    allow_next_day_entry: bool = False
    close_at_end: bool = True
    end_index: int | None = None
    execution: str = "open_next"  # open_next | close_signal
    series_ledger: bool = False
    # 1 = modelo histórico (spread en la entrada y otra vez en la salida).
    # 2 = BID/ASK: un solo spread por operación. Las campañas nuevas fijan 2.
    cost_model_version: int = 1


# ---------------------------------------------------------------------------
# Costes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CostPanel:
    """Coste por barra desglosado: spread, slippage y comisión (bps).

    ``entry_bps``, ``stop_bps`` y ``target_bps`` son propiedades de
    compatibilidad con el modelo v1. En v2 el motor usa los componentes.
    Los overrides ``legacy_*`` solo existen para que ``CostBook`` reproduzca
    exactamente la agregación de la v1 (mínimo/máximo de la suma, no suma de
    mínimos/máximos).
    """

    spread_bps: np.ndarray
    slip_bps: np.ndarray
    comm_bps: np.ndarray
    fut_price: float = 0.0
    legacy_entry_bps: np.ndarray | None = None
    legacy_stop_bps: np.ndarray | None = None
    legacy_target_bps: np.ndarray | None = None

    @property
    def entry_bps(self) -> np.ndarray:
        if self.legacy_entry_bps is not None:
            return self.legacy_entry_bps
        return self.comm_bps + self.slip_bps + self.spread_bps

    @property
    def stop_bps(self) -> np.ndarray:
        if self.legacy_stop_bps is not None:
            return self.legacy_stop_bps
        return self.comm_bps + self.slip_bps + self.spread_bps

    @property
    def target_bps(self) -> np.ndarray:
        if self.legacy_target_bps is not None:
            return self.legacy_target_bps
        return self.comm_bps


def _non_negative(name: str, value: float | None, *, allow_zero: bool = True) -> float:
    if value is None:
        raise MissingCostData(f"Sin datos: falta {name}")
    number = float(value)
    if not np.isfinite(number) or number < 0 or (not allow_zero and number == 0):
        raise MissingCostData(f"Sin datos: {name} inválido ({value!r})")
    return number


def _hour_values(
    bars: pd.DataFrame, values: Mapping[int, float] | pd.Series | None
) -> np.ndarray:
    hours = bars.index.tz_convert("UTC").hour.to_numpy()
    if values is None:
        return np.full(len(bars), np.nan)
    if isinstance(values, pd.Series):
        mapping = {
            int(k): float(v)
            for k, v in pd.to_numeric(values, errors="coerce").dropna().items()
        }
    else:
        mapping = {int(k): float(v) for k, v in dict(values).items()}
    clean = {k: v for k, v in mapping.items() if np.isfinite(v) and v >= 0}
    if not clean:
        raise MissingCostData("Sin datos: spread horario vacío")
    default = float(np.median(list(clean.values())))
    return np.array([clean.get(int(h), default) for h in hours], dtype=float)


class CfdBpsCosts:
    """Costes CFD ya expresados en bps por lado (modo paridad)."""

    market = "cfd"

    def __init__(
        self,
        *,
        commission_bps: float | None = None,
        slippage_bps: float | None = None,
        spread_bps: float | None = None,
        spread_bps_by_hour: Mapping[int, float] | pd.Series | None = None,
        source: str = "bps",
    ) -> None:
        self.commission_bps = _non_negative("commission_bps", commission_bps)
        self.slippage_bps = _non_negative("slippage_bps", slippage_bps)
        self.spread_bps = (
            _non_negative("spread_bps", spread_bps)
            if spread_bps is not None
            else None
        )
        if self.spread_bps is None and spread_bps_by_hour is None:
            raise MissingCostData("Sin datos: falta spread (bps o por hora)")
        self.spread_bps_by_hour = spread_bps_by_hour
        self.source = source

    def label(self) -> str:
        return f"CFD bps · {self.source}"

    def panel(self, bars: pd.DataFrame) -> CostPanel:
        if self.spread_bps_by_hour is not None:
            spread = _hour_values(bars, self.spread_bps_by_hour)
        else:
            spread = np.full(len(bars), float(self.spread_bps))
        commission = np.full(len(bars), self.commission_bps)
        slippage = np.full(len(bars), self.slippage_bps)
        return CostPanel(
            spread_bps=spread,
            slip_bps=slippage,
            comm_bps=commission,
        )

    def ledger_bps(self, bars: pd.DataFrame) -> pd.Series:
        panel = self.panel(bars)
        return pd.Series(
            panel.entry_bps, index=bars.index, dtype=float, name="cost_bps"
        )


class CfdProfileCosts:
    """Costes CFD desde un ``CostProfile`` de ``propfund.costs``."""

    market = "cfd"

    def __init__(
        self,
        profile: CostProfile,
        *,
        contract_size: float | None = None,
        spread_bps_by_hour: Mapping[int, float] | pd.Series | None = None,
        use_p75: bool = True,
    ) -> None:
        if profile.market is not Market.CFD:
            raise MissingCostData("Sin datos: el perfil no es CFD")
        self.profile = profile
        self.contract_size = contract_size or _resolve_contract_size(profile.symbol)
        self.spread_bps_by_hour = spread_bps_by_hour
        self.use_p75 = use_p75
        self.swap = SwapSpec.from_profile(profile)
        self.swap_allow_credit = bool(
            load_engine_config().discovery.swap_credit
        )
        spread = (
            profile.spread_p75_price
            if use_p75 and profile.spread_p75_price is not None
            else profile.spread_price
        )
        self.spread_price = spread
        if spread is None and spread_bps_by_hour is None:
            raise MissingCostData(
                f"Sin datos: spread CFD de {profile.symbol} (mide broker_spreads)"
            )
        if profile.commission_type is None:
            raise MissingCostData(f"Sin datos: comisión CFD de {profile.symbol}")
        if profile.commission_type not in {
            "zero",
            "per_lot_usd",
            "per_contract_usd",
            "percent_of_volume",
        }:
            raise MissingCostData(
                f"Sin datos: commission_type {profile.commission_type!r} no soportado"
            )
        if profile.commission_type in {"per_lot_usd", "per_contract_usd"}:
            if profile.commission_value is None:
                raise MissingCostData(f"Sin datos: comisión CFD de {profile.symbol}")
            if self.contract_size is None:
                raise MissingCostData(
                    f"Sin datos: contract_size de {profile.symbol}"
                )
        if profile.commission_type == "percent_of_volume" and (
            profile.commission_value is None
        ):
            raise MissingCostData(f"Sin datos: comisión CFD de {profile.symbol}")
        if profile.slippage_price is None:
            raise MissingCostData(f"Sin datos: slippage CFD de {profile.symbol}")

    def label(self) -> str:
        return f"CFD perfil · {self.profile.account} · {self.profile.symbol}"

    def _commission_bps(self, prices: np.ndarray) -> np.ndarray:
        profile = self.profile
        side_factor = 0.5 if profile.commission_side == "round_turn" else 1.0
        if profile.commission_type == "zero":
            return np.zeros_like(prices)
        if profile.commission_type == "percent_of_volume":
            return np.full_like(
                prices, float(profile.commission_value or 0.0) * 100.0 * side_factor
            )
        per_lot = float(profile.commission_value or 0.0) * side_factor
        return per_lot / (prices * float(self.contract_size)) * 10_000.0

    def panel(self, bars: pd.DataFrame) -> CostPanel:
        prices = pd.to_numeric(bars["close"], errors="coerce").to_numpy(dtype=float)
        if np.isnan(prices).any() or (prices <= 0).any():
            raise MissingCostData("Sin datos: precios inválidos para convertir costes")
        if self.spread_bps_by_hour is not None:
            spread = _hour_values(bars, self.spread_bps_by_hour)
        else:
            spread = float(self.spread_price) / prices * 10_000.0
        commission = self._commission_bps(prices)
        slippage = float(self.profile.slippage_price) / prices * 10_000.0
        return CostPanel(
            spread_bps=spread,
            slip_bps=slippage,
            comm_bps=commission,
        )

    def ledger_bps(self, bars: pd.DataFrame) -> pd.Series:
        panel = self.panel(bars)
        return pd.Series(
            panel.entry_bps, index=bars.index, dtype=float, name="cost_bps"
        )


class CfdHourlyCosts(CfdProfileCosts):
    """Coste CFD con spread p75 por hora **local** de la sesión.

    ``spread_bps_by_local_hour`` se indexa por hora 0-23 en ``session_tz``.
    Las horas sin medición usan el máximo de las horas medidas (cota
    conservadora); el llamador guarda la lista de horas ausentes para el
    informe.
    """

    def __init__(
        self,
        profile: CostProfile,
        *,
        spread_bps_by_local_hour: Mapping[int, float],
        session_tz: str,
        use_p75: bool = True,
        missing_hours: tuple[int, ...] = (),
    ) -> None:
        mapping = {
            int(hour): float(value)
            for hour, value in dict(spread_bps_by_local_hour).items()
            if np.isfinite(float(value)) and float(value) >= 0.0
        }
        if not mapping:
            raise MissingCostData("Sin datos: spread p75 por hora local")
        # El padre exige un spread global o un mapping; el global puede ser
        # None hasta que se mida, pero el mapping local ya es obligatorio.
        super().__init__(
            profile,
            spread_bps_by_hour={0: 0.0},
            use_p75=use_p75,
        )
        self.spread_bps_by_local_hour = mapping
        self.session_tz = str(session_tz)
        self.missing_hours = tuple(int(hour) for hour in missing_hours)

    def label(self) -> str:
        return f"CFD horario · {self.profile.account} · {self.profile.symbol}"

    def panel(self, bars: pd.DataFrame) -> CostPanel:
        prices = pd.to_numeric(bars["close"], errors="coerce").to_numpy(dtype=float)
        if np.isnan(prices).any() or (prices <= 0).any():
            raise MissingCostData("Sin datos: precios inválidos para costes")
        local_hours = bars.index.tz_convert(self.session_tz).hour.to_numpy()
        fallback = max(self.spread_bps_by_local_hour.values())
        spread = np.array(
            [
                self.spread_bps_by_local_hour.get(int(hour), fallback)
                for hour in local_hours
            ],
            dtype=float,
        )
        commission = self._commission_bps(prices)
        if self.profile.slippage_price is None:  # pragma: no cover - validado
            raise MissingCostData("Sin datos: slippage CFD")
        slippage = float(self.profile.slippage_price) / prices * 10_000.0
        return CostPanel(
            spread_bps=spread,
            slip_bps=slippage,
            comm_bps=commission,
        )


class FuturesCosts:
    """Costes de futuros: comisión + fees por contrato y slippage en ticks."""

    market = "futures"

    def __init__(
        self,
        *,
        commission_per_contract: float | None = None,
        exchange_fee_per_side: float | None = None,
        clearing_fee_per_side: float | None = None,
        nfa_fee_per_side: float | None = None,
        slippage_ticks: float | None = None,
        tick_size: float | None = None,
        tick_value: float | None = None,
        commission_side: str = "per_side",
        source: str = "",
    ) -> None:
        self.commission = _non_negative(
            "commission_per_contract", commission_per_contract
        )
        self.exchange = _non_negative("exchange_fee_per_side", exchange_fee_per_side)
        self.clearing = _non_negative("clearing_fee_per_side", clearing_fee_per_side)
        self.nfa = _non_negative("nfa_fee_per_side", nfa_fee_per_side)
        self.slippage_ticks = _non_negative("slippage_ticks", slippage_ticks)
        self.tick_size = _non_negative("tick_size", tick_size, allow_zero=False)
        self.tick_value = _non_negative("tick_value", tick_value, allow_zero=False)
        self.commission_side = commission_side
        self.source = source
        side_factor = 0.5 if commission_side == "round_turn" else 1.0
        self.usd_per_side = (
            self.commission * side_factor
            + self.exchange
            + self.clearing
            + self.nfa
            + self.slippage_ticks * self.tick_value
        )
        self.unit_value = self.tick_value / self.tick_size
        self.fut_price = self.usd_per_side / self.unit_value

    def label(self) -> str:
        return f"Futuros · {self.source or 'perfil'}"

    def panel(self, bars: pd.DataFrame) -> CostPanel:
        zeros = np.zeros(len(bars), dtype=float)
        return CostPanel(
            spread_bps=zeros.copy(),
            slip_bps=zeros.copy(),
            comm_bps=zeros.copy(),
            fut_price=self.fut_price,
        )

    def ledger_bps(self, bars: pd.DataFrame) -> pd.Series:
        raise MissingCostData("Sin datos: los futuros no usan una serie de bps")


def _resolve_contract_size(symbol: str) -> float | None:
    try:
        return resolve(symbol).contract_size
    except Exception:
        return None


def cfd_costs_from_bps(
    *,
    commission_bps: float,
    slippage_bps: float,
    spread_bps: float | None = None,
    spread_bps_by_hour: Mapping[int, float] | pd.Series | None = None,
    source: str = "bps",
) -> CfdBpsCosts:
    return CfdBpsCosts(
        commission_bps=commission_bps,
        slippage_bps=slippage_bps,
        spread_bps=spread_bps,
        spread_bps_by_hour=spread_bps_by_hour,
        source=source,
    )


def cost_from_profile(
    profile: CostProfile,
    *,
    contract_size: float | None = None,
    spread_bps_by_hour: Mapping[int, float] | pd.Series | None = None,
    use_p75: bool = True,
) -> CfdProfileCosts | FuturesCosts:
    """Convierte un ``CostProfile`` en un modelo del motor rápido.

    Usa ``estimate_cfd``/``estimate_futures`` (``propfund.costs``) para
    detectar componentes ausentes y los enumera en el error "Sin datos".
    """

    if profile.market is Market.CFD:
        size = contract_size or _resolve_contract_size(profile.symbol)
        estimate = estimate_cfd(
            profile,
            lots=1.0,
            price=1.0,
            contract_size=size if size is not None else 1.0,
            use_p75=use_p75,
        )
        missing = list(estimate.missing)
        if size is None and profile.commission_type == "zero":
            missing = [item for item in missing if item != "contract_size"]
        if missing:
            raise MissingCostData(
                "Sin datos: coste CFD incompleto: " + ", ".join(missing)
            )
        return CfdProfileCosts(
            profile,
            contract_size=size,
            spread_bps_by_hour=spread_bps_by_hour,
            use_p75=use_p75,
        )
    if profile.market is Market.FUTURES:
        estimate = estimate_futures(profile, contracts=1)
        if not estimate.complete:
            raise MissingCostData(
                "Sin datos: coste de futuros incompleto: " + ", ".join(estimate.missing)
            )
        item = resolve(profile.symbol)
        return FuturesCosts(
            commission_per_contract=profile.commission_value,
            exchange_fee_per_side=profile.exchange_fee_per_side,
            clearing_fee_per_side=profile.clearing_fee_per_side,
            nfa_fee_per_side=profile.nfa_fee_per_side,
            slippage_ticks=profile.slippage_ticks,
            tick_size=item.tick_size,
            tick_value=item.tick_value,
            commission_side=profile.commission_side,
            source=profile.source,
        )
    raise MissingCostData(f"Sin datos: mercado {profile.market!r} no soportado")


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Trade:
    side: str
    entry_index: int
    exit_index: int
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    stop: float
    target: float | None
    reason: str
    bars_held: int
    risk_price: float | None
    entry_cost_bps: float
    exit_cost_bps: float
    r_gross: float | None
    r_cost: float | None
    r_net: float | None
    swap_r: float | None = None
    spread_r: float | None = None
    slip_r: float | None = None
    comm_r: float | None = None

    @property
    def side_sign(self) -> int:
        return 1 if self.side == "long" else -1

    @property
    def cost_bps(self) -> float:
        return self.entry_cost_bps + self.exit_cost_bps


@dataclass
class FastResult:
    trades: list[Trade]
    daily_r: pd.Series
    metrics: dict[str, Any]
    bar_returns: pd.Series | None = None
    rejected: int = 0
    backend: str = "python"
    cost_label: str = ""


# ---------------------------------------------------------------------------
# Núcleo: una sola implementación para numba y Python
# ---------------------------------------------------------------------------


def _core(
    open_,
    high,
    low,
    close,
    long_sig,
    short_sig,
    allowed,
    allowed_entry,
    flat_flag,
    day_id,
    atr,
    trail_dist,
    entry_bps,
    stop_bps,
    target_bps,
    spread_bps,
    slip_bps,
    comm_bps,
    cost_model_version,
    fut_price,
    stop_kind,
    stop_mult,
    stop_pct,
    stop_fixed,
    target_kind,
    target_rr,
    target_pct,
    target_fixed,
    be_at_r,
    trail_on,
    time_exit_bars,
    opposite,
    on_signal_end,
    max_per_day,
    cooldown,
    allow_next_day,
    close_mode,
    close_at_end,
    market_cfd,
    start_idx,
    end_idx,
):
    n = close.shape[0]
    ent_i = np.full(n, -1, dtype=np.int64)
    ex_i = np.full(n, -1, dtype=np.int64)
    side_arr = np.zeros(n, dtype=np.int64)
    ent_px = np.zeros(n, dtype=np.float64)
    ex_px = np.zeros(n, dtype=np.float64)
    stop0 = np.zeros(n, dtype=np.float64)
    tgt0 = np.zeros(n, dtype=np.float64)
    reason_arr = np.zeros(n, dtype=np.int64)
    ent_cost = np.zeros(n, dtype=np.float64)
    ex_cost = np.zeros(n, dtype=np.float64)
    risk_arr = np.full(n, np.nan, dtype=np.float64)
    r_gross = np.full(n, np.nan, dtype=np.float64)
    r_cost = np.full(n, np.nan, dtype=np.float64)
    r_net = np.full(n, np.nan, dtype=np.float64)
    held = np.zeros(n, dtype=np.int64)
    count = 0
    rejected = 0

    pos = 0
    entry_i = -1
    entry_p = 0.0
    stop_entry = 0.0
    stop_p = 0.0
    tgt_p = 0.0
    risk_d = 0.0
    ent_b = 0.0
    last_entry_i = -1_000_000_000

    if close_mode == 1:
        for i in range(end_idx + 1):
            if pos == 0:
                if i >= start_idx and allowed_entry[i] and (long_sig[i] or short_sig[i]):
                    pos = 1 if long_sig[i] else -1
                    entry_i = i
                    entry_p = close[i]
                    if cost_model_version >= 2:
                        ent_b = (
                            comm_bps[i]
                            + slip_bps[i]
                            + (spread_bps[i] if pos == 1 else 0.0)
                        )
                    else:
                        ent_b = entry_bps[i]
                continue
            if long_sig[i] == 0 and short_sig[i] == 0:
                ex_i[count] = i
                ent_i[count] = entry_i
                side_arr[count] = pos
                ent_px[count] = entry_p
                ex_px[count] = close[i]
                stop0[count] = np.nan
                tgt0[count] = np.nan
                reason_arr[count] = 7
                ent_cost[count] = ent_b
                if cost_model_version >= 2:
                    ex_cost[count] = (
                        comm_bps[i]
                        + slip_bps[i]
                        + (spread_bps[i] if pos == -1 else 0.0)
                    )
                else:
                    ex_cost[count] = stop_bps[i]
                held[count] = i - entry_i
                count += 1
                pos = 0
        if close_at_end == 1 and pos != 0 and end_idx >= 0:
            last = end_idx
            if last > entry_i:
                ex_i[count] = last
                ent_i[count] = entry_i
                side_arr[count] = pos
                ent_px[count] = entry_p
                ex_px[count] = close[last]
                stop0[count] = np.nan
                tgt0[count] = np.nan
                reason_arr[count] = 6
                ent_cost[count] = ent_b
                if cost_model_version >= 2:
                    ex_cost[count] = (
                        comm_bps[last]
                        + slip_bps[last]
                        + (spread_bps[last] if pos == -1 else 0.0)
                    )
                else:
                    ex_cost[count] = stop_bps[last]
                held[count] = last - entry_i
                count += 1
        return (
            count,
            rejected,
            ent_i,
            ex_i,
            side_arr,
            ent_px,
            ex_px,
            stop0,
            tgt0,
            reason_arr,
            ent_cost,
            ex_cost,
            risk_arr,
            r_gross,
            r_cost,
            r_net,
            held,
        )

    pending = 0
    pending_day = -1
    pending_sig_i = -1
    cur_day = -1
    day_count = 0

    for i in range(end_idx + 1):
        if day_id[i] != cur_day:
            cur_day = day_id[i]
            day_count = 0
        if allow_next_day == 0 and pending != 0 and day_id[i] != pending_day:
            pending = 0

        # 1) Salidas al open: señal opuesta o fin de señal (sin look-ahead).
        if pos != 0 and i > entry_i and allowed[i] and i > 0:
            do_exit = False
            reason_open = 0
            if opposite == 1:
                if (pos == 1 and short_sig[i - 1]) or (pos == -1 and long_sig[i - 1]):
                    do_exit = True
                    reason_open = 5
            if (
                not do_exit
                and on_signal_end == 1
                and long_sig[i - 1] == 0
                and short_sig[i - 1] == 0
            ):
                do_exit = True
                reason_open = 7
            if do_exit:
                if cost_model_version >= 2:
                    ex_b = (
                        comm_bps[i]
                        + slip_bps[i]
                        + (spread_bps[i] if pos == -1 else 0.0)
                    )
                else:
                    ex_b = stop_bps[i]
                px = open_[i]
                stock_i = entry_i
                ent_i[count] = stock_i
                ex_i[count] = i
                side_arr[count] = pos
                ent_px[count] = entry_p
                ex_px[count] = px
                stop0[count] = stop_entry
                tgt0[count] = tgt_p
                reason_arr[count] = reason_open
                ent_cost[count] = ent_b
                ex_cost[count] = ex_b
                held[count] = i - entry_i
                if risk_d > 0:
                    if pos == 1:
                        gross_frac = px / entry_p - 1.0
                    else:
                        gross_frac = 1.0 - px / entry_p
                    rg = gross_frac * entry_p / risk_d
                    rc = (
                        (ent_b + ex_b) / 10_000.0 * entry_p / risk_d
                        + 2.0 * fut_price / risk_d
                    )
                    risk_arr[count] = risk_d
                    r_gross[count] = rg
                    r_cost[count] = rc
                    r_net[count] = rg - rc
                count += 1
                pos = 0
                pending = 0

        # 2) Entrada pendiente (señal de la vela anterior).
        if pos == 0 and pending != 0 and allowed_entry[i]:
            take = False
            if max_per_day <= 0 or day_count < max_per_day:
                if cooldown <= 0 or i - last_entry_i >= cooldown:
                    take = True
            if take:
                side = pending
                ep = open_[i]
                sp = 0.0
                tp = np.nan
                dist = 0.0
                if stop_kind == 0:
                    a = atr[pending_sig_i]
                    if not np.isnan(a) and a > 0.0:
                        dist = stop_mult * a
                        sp = ep - side * dist
                elif stop_kind == 1:
                    dist = ep * stop_pct / 100.0
                    sp = ep - side * dist
                else:
                    sp = stop_fixed
                    dist = (ep - sp) * side
                valid = dist > 0.0 and np.isfinite(dist)
                if valid and target_kind != 3:
                    if target_kind == 0:
                        tp = ep + side * target_rr * dist
                    elif target_kind == 1:
                        tp = ep + side * ep * target_pct / 100.0
                    else:
                        tp = target_fixed
                    if (side == 1 and tp <= ep) or (side == -1 and tp >= ep):
                        valid = False
                if valid:
                    pos = side
                    entry_i = i
                    entry_p = ep
                    stop_entry = sp
                    stop_p = sp
                    tgt_p = tp
                    risk_d = dist
                    if cost_model_version >= 2:
                        ent_b = (
                            comm_bps[i]
                            + slip_bps[i]
                            + (spread_bps[i] if side == 1 else 0.0)
                        )
                    else:
                        ent_b = entry_bps[i]
                    day_count += 1
                    last_entry_i = i
                    pending = 0
                else:
                    rejected += 1
                    pending = 0
            else:
                pending = 0

        # 3) Stop -> objetivo -> salida forzada -> tiempo.
        if pos != 0 and allowed[i]:
            hit_stop = False
            hit_tgt = False
            if pos == 1:
                hit_stop = low[i] <= stop_p
            else:
                if cost_model_version >= 2:
                    hit_stop = (
                        high[i] + high[i] * spread_bps[i] / 10_000.0 >= stop_p
                    )
                else:
                    hit_stop = high[i] >= stop_p
            if target_kind != 3:
                if pos == 1:
                    hit_tgt = high[i] >= tgt_p
                else:
                    hit_tgt = low[i] <= tgt_p
                    if hit_tgt and market_cfd == 1:
                        if low[i] + low[i] * spread_bps[i] / 10_000.0 > tgt_p:
                            hit_tgt = False
            exit_now = False
            px = 0.0
            ex_b = 0.0
            reason = 0
            if hit_stop:
                if pos == 1:
                    px = min(stop_p, open_[i])
                else:
                    if cost_model_version >= 2:
                        open_ask = open_[i] + open_[i] * spread_bps[i] / 10_000.0
                        px = max(stop_p, open_ask)
                    else:
                        px = max(stop_p, open_[i])
                if cost_model_version >= 2:
                    # En el corto el ASK ya está en el precio de salida.
                    ex_b = comm_bps[i] + slip_bps[i]
                else:
                    ex_b = stop_bps[i]
                reason = 1
                exit_now = True
            elif hit_tgt:
                if pos == 1:
                    px = min(tgt_p, high[i])
                else:
                    px = max(tgt_p, low[i])
                ex_b = comm_bps[i] if cost_model_version >= 2 else target_bps[i]
                reason = 2
                exit_now = True
            elif flat_flag[i]:
                px = close[i]
                if cost_model_version >= 2:
                    ex_b = (
                        comm_bps[i]
                        + slip_bps[i]
                        + (spread_bps[i] if pos == -1 else 0.0)
                    )
                else:
                    ex_b = stop_bps[i]
                reason = 3
                exit_now = True
            elif time_exit_bars > 0 and (i - entry_i) >= time_exit_bars:
                px = close[i]
                if cost_model_version >= 2:
                    ex_b = (
                        comm_bps[i]
                        + slip_bps[i]
                        + (spread_bps[i] if pos == -1 else 0.0)
                    )
                else:
                    ex_b = stop_bps[i]
                reason = 4
                exit_now = True

            if exit_now:
                ent_i[count] = entry_i
                ex_i[count] = i
                side_arr[count] = pos
                ent_px[count] = entry_p
                ex_px[count] = px
                stop0[count] = stop_entry
                tgt0[count] = tgt_p
                reason_arr[count] = reason
                ent_cost[count] = ent_b
                ex_cost[count] = ex_b
                held[count] = i - entry_i
                if pos == 1:
                    gross_frac = px / entry_p - 1.0
                else:
                    gross_frac = 1.0 - px / entry_p
                rg = gross_frac * entry_p / risk_d
                rc = (
                    (ent_b + ex_b) / 10_000.0 * entry_p / risk_d
                    + 2.0 * fut_price / risk_d
                )
                risk_arr[count] = risk_d
                r_gross[count] = rg
                r_cost[count] = rc
                r_net[count] = rg - rc
                count += 1
                pos = 0

        # 4) BE y trailing al cierre, efectivos desde la vela siguiente.
        if pos != 0 and allowed[i]:
            if be_at_r > 0.0:
                cur_r = (close[i] - entry_p) * pos / risk_d
                if cur_r >= be_at_r:
                    if pos == 1 and entry_p > stop_p:
                        stop_p = entry_p
                    if pos == -1 and entry_p < stop_p:
                        stop_p = entry_p
            if trail_on == 1 and trail_dist[i] > 0.0:
                level = close[i] - pos * trail_dist[i]
                if pos == 1 and level > stop_p:
                    stop_p = level
                if pos == -1 and level < stop_p:
                    stop_p = level

        # 5) Cola de señal para la vela siguiente.
        if pos == 0:
            if i >= start_idx and allowed_entry[i] and long_sig[i]:
                pending = 1
                pending_day = day_id[i]
                pending_sig_i = i
            elif i >= start_idx and allowed_entry[i] and short_sig[i]:
                pending = -1
                pending_day = day_id[i]
                pending_sig_i = i
        else:
            pending = 0

    if close_at_end == 1 and pos != 0 and end_idx >= 0:
        last = end_idx
        if last > entry_i:
            if cost_model_version >= 2:
                ex_b = (
                    comm_bps[last]
                    + slip_bps[last]
                    + (spread_bps[last] if pos == -1 else 0.0)
                )
            else:
                ex_b = stop_bps[last]
            px = close[last]
            ent_i[count] = entry_i
            ex_i[count] = last
            side_arr[count] = pos
            ent_px[count] = entry_p
            ex_px[count] = px
            stop0[count] = stop_entry
            tgt0[count] = tgt_p
            reason_arr[count] = 6
            ent_cost[count] = ent_b
            ex_cost[count] = ex_b
            held[count] = last - entry_i
            if pos == 1:
                gross_frac = px / entry_p - 1.0
            else:
                gross_frac = 1.0 - px / entry_p
            rg = gross_frac * entry_p / risk_d
            rc = (
                (ent_b + ex_b) / 10_000.0 * entry_p / risk_d
                + 2.0 * fut_price / risk_d
            )
            risk_arr[count] = risk_d
            r_gross[count] = rg
            r_cost[count] = rc
            r_net[count] = rg - rc
            count += 1

    return (
        count,
        rejected,
        ent_i,
        ex_i,
        side_arr,
        ent_px,
        ex_px,
        stop0,
        tgt0,
        reason_arr,
        ent_cost,
        ex_cost,
        risk_arr,
        r_gross,
        r_cost,
        r_net,
        held,
    )


def _calendar_core(
    open_,
    high,
    low,
    close,
    long_sig,
    short_sig,
    allowed,
    allowed_entry,
    atr,
    entry_bps,
    stop_bps,
    target_bps,
    spread_bps,
    slip_bps,
    comm_bps,
    cost_model_version,
    fut_price,
    stop_kind,
    stop_mult,
    stop_pct,
    stop_fixed,
    target_kind,
    target_rr,
    target_pct,
    target_fixed,
    close_at_end,
    start_idx,
    end_idx,
    calendar_exit,
):
    """Entrada al cierre y salida al cierre de ``calendar_exit``.

    Variante mínima del motor de eventos para ``month_turn``: una posición,
    stop/objetivo opcionales y salida de calendario. No usa señales de salida
    ni límites diarios; la estrategia genera como máximo una entrada al mes.
    """

    n = len(open_)
    ent_i = np.full(n, -1, dtype=np.int64)
    ex_i = np.full(n, -1, dtype=np.int64)
    side_arr = np.zeros(n, dtype=np.int64)
    ent_px = np.full(n, np.nan, dtype=np.float64)
    ex_px = np.full(n, np.nan, dtype=np.float64)
    stop0 = np.full(n, np.nan, dtype=np.float64)
    tgt0 = np.full(n, np.nan, dtype=np.float64)
    reason_arr = np.zeros(n, dtype=np.int64)
    ent_cost = np.full(n, np.nan, dtype=np.float64)
    ex_cost = np.full(n, np.nan, dtype=np.float64)
    risk_arr = np.full(n, np.nan, dtype=np.float64)
    r_gross = np.full(n, np.nan, dtype=np.float64)
    r_cost = np.full(n, np.nan, dtype=np.float64)
    r_net = np.full(n, np.nan, dtype=np.float64)
    held = np.zeros(n, dtype=np.int64)
    count = 0
    pos = 0
    entry_i = -1
    entry_p = 0.0
    stop_p = 0.0
    tgt_p = 0.0
    risk_d = 0.0
    ent_b = 0.0
    exit_target = -1

    for i in range(end_idx + 1):
        if pos == 0:
            if i >= start_idx and allowed_entry[i] and (long_sig[i] or short_sig[i]):
                side = 1 if long_sig[i] else -1
                ep = close[i]
                if stop_kind == 0:
                    dist = stop_mult * atr[i]
                elif stop_kind == 1:
                    dist = ep * stop_pct / 100.0
                else:
                    dist = (ep - stop_fixed) * side
                if dist > 0.0 and np.isfinite(dist):
                    sp = ep - side * dist
                    tp = 0.0
                    has_target = target_kind != 3
                    if has_target:
                        if target_kind == 0:
                            tp = ep + side * target_rr * dist
                        elif target_kind == 1:
                            tp = ep + side * ep * target_pct / 100.0
                        else:
                            tp = target_fixed
                        if (side == 1 and tp <= ep) or (side == -1 and tp >= ep):
                            has_target = False
                    pos = side
                    entry_i = i
                    entry_p = ep
                    stop_p = sp
                    tgt_p = tp if has_target else np.nan
                    risk_d = dist
                    if cost_model_version >= 2:
                        ent_b = (
                            comm_bps[i]
                            + slip_bps[i]
                            + (spread_bps[i] if side == 1 else 0.0)
                        )
                    else:
                        ent_b = entry_bps[i]
                    exit_target = (
                        int(calendar_exit[i]) if calendar_exit[i] > i else -1
                    )
            continue

        exit_now = False
        price = 0.0
        exit_bps = 0.0
        reason = 0
        if exit_target >= 0 and i >= exit_target:
            price = close[i]
            if cost_model_version >= 2:
                exit_bps = (
                    comm_bps[i]
                    + slip_bps[i]
                    + (spread_bps[i] if pos == -1 else 0.0)
                )
            else:
                exit_bps = stop_bps[i]
            reason = 8
            exit_now = True
        elif allowed[i]:
            hit_stop = False
            hit_target = False
            if pos == 1:
                hit_stop = low[i] <= stop_p
            else:
                if cost_model_version >= 2:
                    hit_stop = (
                        high[i] + high[i] * spread_bps[i] / 10_000.0 >= stop_p
                    )
                else:
                    hit_stop = high[i] >= stop_p
            if target_kind != 3:
                if pos == 1:
                    hit_target = high[i] >= tgt_p
                else:
                    hit_target = low[i] <= tgt_p
            if hit_stop:
                if pos == 1:
                    price = stop_p if stop_p < open_[i] else open_[i]
                else:
                    if cost_model_version >= 2:
                        open_ask = open_[i] + open_[i] * spread_bps[i] / 10_000.0
                        price = stop_p if stop_p > open_ask else open_ask
                    else:
                        price = stop_p if stop_p > open_[i] else open_[i]
                if cost_model_version >= 2:
                    exit_bps = comm_bps[i] + slip_bps[i]
                else:
                    exit_bps = stop_bps[i]
                reason = 1
                exit_now = True
            elif hit_target:
                if pos == 1:
                    price = tgt_p if tgt_p < high[i] else high[i]
                else:
                    price = tgt_p if tgt_p > low[i] else low[i]
                exit_bps = comm_bps[i] if cost_model_version >= 2 else target_bps[i]
                reason = 2
                exit_now = True
        if not exit_now and close_at_end and i == end_idx:
            price = close[i]
            if cost_model_version >= 2:
                exit_bps = (
                    comm_bps[i]
                    + slip_bps[i]
                    + (spread_bps[i] if pos == -1 else 0.0)
                )
            else:
                exit_bps = stop_bps[i]
            reason = 6
            exit_now = True

        if exit_now:
            ent_i[count] = entry_i
            ex_i[count] = i
            side_arr[count] = pos
            ent_px[count] = entry_p
            ex_px[count] = price
            stop0[count] = stop_p
            tgt0[count] = tgt_p
            reason_arr[count] = reason
            ent_cost[count] = ent_b
            ex_cost[count] = exit_bps
            held[count] = i - entry_i
            if pos == 1:
                gross_frac = price / entry_p - 1.0
            else:
                gross_frac = 1.0 - price / entry_p
            rg = gross_frac * entry_p / risk_d
            rc = (
                (ent_b + exit_bps) / 10_000.0 * entry_p / risk_d
                + 2.0 * fut_price / risk_d
            )
            risk_arr[count] = risk_d
            r_gross[count] = rg
            r_cost[count] = rc
            r_net[count] = rg - rc
            count += 1
            pos = 0
            exit_target = -1

    if pos != 0 and close_at_end and end_idx >= 0:
        price = close[end_idx]
        if cost_model_version >= 2:
            exit_bps = (
                comm_bps[end_idx]
                + slip_bps[end_idx]
                + (spread_bps[end_idx] if pos == -1 else 0.0)
            )
        else:
            exit_bps = stop_bps[end_idx]
        ent_i[count] = entry_i
        ex_i[count] = end_idx
        side_arr[count] = pos
        ent_px[count] = entry_p
        ex_px[count] = price
        stop0[count] = stop_p
        tgt0[count] = tgt_p
        reason_arr[count] = 6
        ent_cost[count] = ent_b
        ex_cost[count] = exit_bps
        held[count] = end_idx - entry_i
        if pos == 1:
            gross_frac = price / entry_p - 1.0
        else:
            gross_frac = 1.0 - price / entry_p
        rg = gross_frac * entry_p / risk_d
        rc = (
            (ent_b + exit_bps) / 10_000.0 * entry_p / risk_d
            + 2.0 * fut_price / risk_d
        )
        risk_arr[count] = risk_d
        r_gross[count] = rg
        r_cost[count] = rc
        r_net[count] = rg - rc
        count += 1

    return (
        count,
        0,
        ent_i,
        ex_i,
        side_arr,
        ent_px,
        ex_px,
        stop0,
        tgt0,
        reason_arr,
        ent_cost,
        ex_cost,
        risk_arr,
        r_gross,
        r_cost,
        r_net,
        held,
    )


_calendar_core_compiled = (
    njit(cache=True)(_calendar_core)
    if (HAVE_NUMBA and not _DISABLED)
    else _calendar_core
)


_core_compiled = njit(cache=True)(_core) if (HAVE_NUMBA and not _DISABLED) else _core


def backend() -> str:
    return "numba" if _core_compiled is not _core else "python"


def set_backend(name: str) -> str:
    """Fuerza el backend (tests y benchmark). Devuelve el anterior."""

    global _core_compiled
    previous = backend()
    if name == "python":
        _core_compiled = _core
    elif name == "numba":
        if njit is None:
            raise FastBtError("numba no está instalado")
        _core_compiled = njit(cache=True)(_core)
    else:
        raise FastBtError(f"backend desconocido: {name!r}")
    return previous


# ---------------------------------------------------------------------------
# Preparación y ejecución
# ---------------------------------------------------------------------------


def _signal_arrays(signals: Any, n: int) -> tuple[np.ndarray, np.ndarray, int]:
    """Normaliza ``compiler.Signals`` (única clase) a arrays de barras."""

    try:
        return signals.arrays(n)
    except FastBtError:
        raise
    except (AttributeError, TypeError, ValueError) as exc:
        raise FastBtError(str(exc)) from exc


def _parse_hhmm(value: str | None, name: str) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    try:
        hour, minute = text.split(":")
        h = int(hour)
        m = int(minute)
    except Exception as exc:  # noqa: BLE001 - mensaje propio
        raise FastBtError(f"{name} inválido: {value!r}") from exc
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise FastBtError(f"{name} fuera de rango: {value!r}")
    return h * 3600 + m * 60


def _validate_bars(bars: pd.DataFrame) -> None:
    if not isinstance(bars, pd.DataFrame) or len(bars) == 0:
        raise FastBtError("Sin datos: no hay barras")
    if not isinstance(bars.index, pd.DatetimeIndex):
        raise FastBtError("el índice de barras debe ser DatetimeIndex")
    if bars.index.tz is None:
        raise FastBtError("Sin datos: las barras deben tener zona horaria")
    if not bars.index.is_monotonic_increasing:
        raise FastBtError("las barras deben estar ordenadas")
    if bars.index.has_duplicates:
        raise FastBtError("las barras tienen timestamps duplicados")
    for column in ("open", "high", "low", "close"):
        if column not in bars.columns:
            raise FastBtError(f"falta la columna {column}")
        values = pd.to_numeric(bars[column], errors="coerce").to_numpy(dtype=float)
        if np.isnan(values).any():
            raise FastBtError(f"Sin datos: NaN en {column}")
        if (values <= 0).any():
            raise FastBtError(f"precios no positivos en {column}")


@dataclass(frozen=True)
class SessionMask:
    """Máscaras de sesión y día local para un ``RunLimits`` concreto."""

    allowed: np.ndarray
    allowed_entry: np.ndarray
    flat_flag: np.ndarray
    day_id: np.ndarray


@dataclass
class PreparedBars:
    """Barras y derivados que un worker reutiliza en todos sus jobs."""

    bars: pd.DataFrame
    panel: CostPanel
    atr: dict[int, np.ndarray] = field(default_factory=dict)
    masks: dict[tuple, SessionMask] = field(default_factory=dict)


def _mask_key(limits: RunLimits) -> tuple:
    return (
        limits.session_tz,
        limits.session_start,
        limits.session_end,
        limits.flat_at,
        tuple(int(day) for day in limits.weekdays),
    )


def _session_mask(bars: pd.DataFrame, limits: RunLimits) -> SessionMask:
    n = len(bars)
    if not limits.session_tz:
        raise FastBtError("session_tz vacío")
    try:
        local = bars.index.tz_convert(limits.session_tz)
    except Exception as exc:  # noqa: BLE001
        raise FastBtError(f"session_tz inválido: {limits.session_tz}") from exc

    start_s = _parse_hhmm(limits.session_start, "session_start")
    end_s = _parse_hhmm(limits.session_end, "session_end")
    flat_s = _parse_hhmm(limits.flat_at, "flat_at")
    if flat_s is not None and start_s < end_s and flat_s < start_s:
        raise FastBtError("flat_at no puede ser anterior a session_start")
    seconds = (
        local.hour.to_numpy() * 3600
        + local.minute.to_numpy() * 60
        + local.second.to_numpy()
    )

    def _in_window(begin: int, finish: int) -> np.ndarray:
        if begin == finish:
            return np.ones(n, dtype=bool)
        if begin < finish:
            return (seconds >= begin) & (seconds <= finish)
        return (seconds >= begin) | (seconds <= finish)

    entry_window = _in_window(start_s, end_s)
    manage_end = end_s if flat_s is None else max(end_s, flat_s)
    manage_window = _in_window(start_s, manage_end)
    weekday = np.isin(
        local.day_of_week.to_numpy(), np.asarray(limits.weekdays, dtype=int)
    )
    if flat_s is None:
        flat_flag = np.zeros(n, dtype=bool)
    else:
        # Posición relativa al inicio de la sesión. Para 18:00→02:45, el
        # flat de 02:45 cae 8 h 45 min después del inicio y NO marca la tarde.
        day_seconds = 24 * 3600
        relative = (seconds - start_s) % day_seconds
        duration = (manage_end - start_s) % day_seconds
        if duration == 0:
            duration = day_seconds
        flat_relative = (flat_s - start_s) % day_seconds
        flat_flag = (relative >= flat_relative) & (relative <= duration)
    local_day = (
        local.normalize()
        .tz_localize(None)
        .to_numpy(dtype="datetime64[D]")
        .astype(np.int64)
    )
    day_id = local_day
    if start_s > end_s:
        # Sesión que cruza medianoche: las barras anteriores al fin (p. ej.
        # 02:00) pertenecen a la sesión que empezó el día anterior.
        before_end = seconds < end_s
        day_id = local_day - before_end.astype(np.int64)
    return SessionMask(
        allowed=manage_window & weekday,
        allowed_entry=entry_window & weekday & ~flat_flag,
        flat_flag=flat_flag,
        day_id=day_id,
    )


def session_mask(
    bars: pd.DataFrame,
    limits: RunLimits,
    *,
    prepared: PreparedBars | None = None,
) -> SessionMask:
    """Máscara de sesión reutilizando la caché de ``prepared`` si existe."""

    if prepared is not None:
        if prepared.bars is not bars:
            raise FastBtError("prepared no corresponde a estas barras")
        key = _mask_key(limits)
        mask = prepared.masks.get(key)
        if mask is None:
            mask = _session_mask(bars, limits)
            prepared.masks[key] = mask
        return mask
    return _session_mask(bars, limits)


def atr_window(
    bars: pd.DataFrame,
    window: int,
    *,
    prepared: PreparedBars | None = None,
) -> np.ndarray:
    """ATR en array, reutilizando la caché de ``prepared`` si existe."""

    value = int(window)
    if value < 1:
        raise FastBtError("la ventana ATR debe ser >= 1")
    if prepared is not None:
        if prepared.bars is not bars:
            raise FastBtError("prepared no corresponde a estas barras")
        cached = prepared.atr.get(value)
        if cached is None:
            cached = atr_series(bars, value).to_numpy(dtype=float)
            prepared.atr[value] = cached
        return cached
    return atr_series(bars, value).to_numpy(dtype=float)


def prepare(
    bars: pd.DataFrame,
    cost: Any,
    *,
    atr_windows: tuple[int, ...] | list[int] = (),
    sessions: tuple[RunLimits, ...] | list[RunLimits] = (),
) -> PreparedBars:
    """Calcula una vez barras derivadas para reutilizarlas entre backtests."""

    _validate_bars(bars)
    panel = cost.panel(bars)
    prepared = PreparedBars(bars=bars, panel=panel)
    for window in atr_windows:
        value = int(window)
        if value > 0 and value not in prepared.atr:
            prepared.atr[value] = atr_series(bars, value).to_numpy(dtype=float)
    for limits in sessions:
        key = _mask_key(limits)
        if key not in prepared.masks:
            prepared.masks[key] = _session_mask(bars, limits)
    return prepared


def _prepare(
    signals: Signals,
    bars: pd.DataFrame,
    exit_spec: ExitSpec,
    limits: RunLimits,
    panel: CostPanel,
    market: str,
    prepared: PreparedBars | None = None,
    cost_model_version: int = 1,
) -> tuple[dict[str, Any], int, int]:
    _validate_bars(bars)
    if prepared is not None and prepared.bars is not bars:
        raise FastBtError("prepared no corresponde a estas barras")
    n = len(bars)
    if limits.end_index is None:
        end_idx = n - 1
    else:
        end_idx = int(limits.end_index)
        if end_idx < 0:
            raise FastBtError("end_index no puede ser negativo")
        end_idx = min(end_idx, n - 1)
    long_arr, short_arr, start = _signal_arrays(signals, n)
    if limits.execution not in {"open_next", "close_signal"}:
        raise FastBtError(f"execution inválido: {limits.execution!r}")
    if limits.cooldown_bars < 0:
        raise FastBtError("cooldown_bars no puede ser negativo")
    if limits.max_trades_per_day is not None and limits.max_trades_per_day < 0:
        raise FastBtError("max_trades_per_day no puede ser negativo")
    if limits.execution == "open_next" and exit_spec.stop is None:
        raise FastBtError("el motor de eventos necesita un stop (sin stop no hay R)")

    key = _mask_key(limits)
    if prepared is not None:
        mask = prepared.masks.get(key)
        if mask is None:
            mask = _session_mask(bars, limits)
            prepared.masks[key] = mask
    else:
        mask = _session_mask(bars, limits)
    allowed = mask.allowed
    allowed_entry = mask.allowed_entry
    flat_flag = mask.flat_flag
    day_id = mask.day_id

    def _atr_values(window: int) -> np.ndarray:
        if prepared is not None:
            cached = prepared.atr.get(int(window))
            if cached is None:
                cached = atr_series(bars, int(window)).to_numpy(dtype=float)
                prepared.atr[int(window)] = cached
            return cached
        return atr_series(bars, int(window)).to_numpy(dtype=float)

    if exit_spec.stop == "atr":
        atr_values = _atr_values(exit_spec.stop_n)
    else:
        atr_values = np.zeros(n, dtype=float)
    if exit_spec.trail_atr_mult is not None:
        trail_dist = _atr_values(exit_spec.trail_n) * exit_spec.trail_atr_mult
    else:
        trail_dist = np.zeros(n, dtype=float)

    stop_kind = {"atr": 0, "pct": 1, "fixed": 2}.get(exit_spec.stop, -1)
    target_kind = {"rr": 0, "pct": 1, "fixed": 2, None: 3}[exit_spec.target]

    payload = {
        "open_": bars["open"].to_numpy(dtype=float),
        "high": bars["high"].to_numpy(dtype=float),
        "low": bars["low"].to_numpy(dtype=float),
        "close": bars["close"].to_numpy(dtype=float),
        "long_sig": long_arr,
        "short_sig": short_arr,
        "allowed": allowed,
        "allowed_entry": allowed_entry,
        "flat_flag": flat_flag,
        "day_id": day_id,
        "atr": atr_values,
        "trail_dist": trail_dist,
        "entry_bps": panel.entry_bps,
        "stop_bps": panel.stop_bps,
        "target_bps": panel.target_bps,
        "spread_bps": panel.spread_bps,
        "slip_bps": panel.slip_bps,
        "comm_bps": panel.comm_bps,
        "cost_model_version": int(cost_model_version),
        "fut_price": float(panel.fut_price),
        "stop_kind": int(stop_kind),
        "stop_mult": float(exit_spec.stop_mult),
        "stop_pct": float(exit_spec.stop_mult),
        "stop_fixed": float(exit_spec.stop_price or 0.0),
        "target_kind": int(target_kind),
        "target_rr": float(exit_spec.target_rr),
        "target_pct": float(exit_spec.target_pct or 0.0),
        "target_fixed": float(exit_spec.target_price or 0.0),
        "be_at_r": float(exit_spec.breakeven_at_r or 0.0),
        "trail_on": 1 if exit_spec.trail_atr_mult is not None else 0,
        "time_exit_bars": int(exit_spec.time_exit_bars or 0),
        "opposite": 1 if exit_spec.opposite_signal else 0,
        "on_signal_end": 1 if exit_spec.on_signal_end else 0,
        "max_per_day": (
            -1 if limits.max_trades_per_day is None else int(limits.max_trades_per_day)
        ),
        "cooldown": int(limits.cooldown_bars),
        "allow_next_day": 1 if limits.allow_next_day_entry else 0,
        "close_mode": 1 if limits.execution == "close_signal" else 0,
        "close_at_end": 1 if limits.close_at_end else 0,
        "market_cfd": 1 if market == "cfd" else 0,
        "start_idx": start,
        "end_idx": int(end_idx),
    }
    return payload, n, 1 if limits.execution == "close_signal" else 0


def run(
    signals: Signals,
    bars: pd.DataFrame,
    exit_spec: ExitSpec,
    cost: CfdBpsCosts | CfdProfileCosts | FuturesCosts,
    limits: RunLimits | None = None,
    *,
    prepared: PreparedBars | None = None,
    collect_metrics: bool = True,
    cost_model_version: int | None = None,
) -> FastResult:
    """Ejecuta las señales sobre barras ya cargadas (sin datos reales aquí).

    ``collect_metrics=False`` evita calcular expectativa/PF/Sharpe: lo usa el
    escaneo de viabilidad, que solo necesita operaciones y coste. No cambia la
    ejecución ni las operaciones.

    ``cost_model_version``: 1 (histórico) o 2 (BID/ASK, un spread por
    operación). Si no se pasa, manda ``limits.cost_model_version`` (1).
    """

    limits = limits or RunLimits()
    version = int(
        cost_model_version
        if cost_model_version is not None
        else getattr(limits, "cost_model_version", 1)
    )
    if version not in {1, 2}:
        raise FastBtError(f"cost_model_version inválida: {version}")
    exit_spec = exit_spec.validated()
    market = getattr(cost, "market", None)
    if market not in {"cfd", "futures"}:
        raise MissingCostData("Sin datos: modelo de coste sin mercado declarado")
    if not hasattr(cost, "panel"):
        raise MissingCostData("Sin datos: modelo de coste sin panel")
    panel = prepared.panel if prepared is not None else cost.panel(bars)
    payload, _n, _close_mode = _prepare(
        signals, bars, exit_spec, limits, panel, market, prepared, version
    )

    if signals.exit_index is not None:
        if limits.execution == "close_signal":
            raise FastBtError("calendar_exit no admite execution=close_signal")
        exit_index = np.asarray(signals.exit_index, dtype=np.int64).reshape(-1)
        if len(exit_index) != len(bars):
            raise FastBtError(
                "signals.exit_index debe tener una entrada por barra"
            )
        result = _calendar_core_compiled(
            payload["open_"],
            payload["high"],
            payload["low"],
            payload["close"],
            payload["long_sig"],
            payload["short_sig"],
            payload["allowed"],
            payload["allowed_entry"],
            payload["atr"],
            payload["entry_bps"],
            payload["stop_bps"],
            payload["target_bps"],
            payload["spread_bps"],
            payload["slip_bps"],
            payload["comm_bps"],
            payload["cost_model_version"],
            payload["fut_price"],
            payload["stop_kind"],
            payload["stop_mult"],
            payload["stop_pct"],
            payload["stop_fixed"],
            payload["target_kind"],
            payload["target_rr"],
            payload["target_pct"],
            payload["target_fixed"],
            payload["close_at_end"],
            payload["start_idx"],
            payload["end_idx"],
            exit_index,
        )
    else:
        result = _core_compiled(
            payload["open_"],
            payload["high"],
            payload["low"],
            payload["close"],
            payload["long_sig"],
            payload["short_sig"],
            payload["allowed"],
            payload["allowed_entry"],
            payload["flat_flag"],
            payload["day_id"],
            payload["atr"],
            payload["trail_dist"],
            payload["entry_bps"],
            payload["stop_bps"],
            payload["target_bps"],
            payload["spread_bps"],
            payload["slip_bps"],
            payload["comm_bps"],
            payload["cost_model_version"],
            payload["fut_price"],
            payload["stop_kind"],
            payload["stop_mult"],
            payload["stop_pct"],
            payload["stop_fixed"],
            payload["target_kind"],
            payload["target_rr"],
            payload["target_pct"],
            payload["target_fixed"],
            payload["be_at_r"],
            payload["trail_on"],
            payload["time_exit_bars"],
            payload["opposite"],
            payload["on_signal_end"],
            payload["max_per_day"],
            payload["cooldown"],
            payload["allow_next_day"],
            payload["close_mode"],
            payload["close_at_end"],
            payload["market_cfd"],
            payload["start_idx"],
            payload["end_idx"],
        )
    (
        count,
        rejected,
        ent_i,
        ex_i,
        side_arr,
        ent_px,
        ex_px,
        stop0,
        tgt0,
        reason_arr,
        ent_cost,
        ex_cost,
        risk_arr,
        r_gross,
        r_cost,
        r_net,
        held,
    ) = result

    index = bars.index
    trades: list[Trade] = []
    for k in range(int(count)):
        risk = float(risk_arr[k])
        net = float(r_net[k])
        side_name = "long" if int(side_arr[k]) == 1 else "short"
        reason_name = REASONS.get(int(reason_arr[k]), "unknown")
        entry_i = int(ent_i[k])
        exit_i = int(ex_i[k])
        spread_r = slip_r = comm_r = None
        if version >= 2 and np.isfinite(risk) and risk > 0.0:
            factor = float(ent_px[k]) / risk / 10_000.0
            comm_r = (
                float(panel.comm_bps[entry_i] + panel.comm_bps[exit_i]) * factor
                + 2.0 * float(panel.fut_price) / risk
            )
            slip_r = float(
                panel.slip_bps[entry_i] + panel.slip_bps[exit_i]
            ) * factor
            if side_name == "long":
                spread_bps_trade = float(panel.spread_bps[entry_i])
            elif reason_name in {"stop", "target"}:
                # El ASK ya está en el precio de salida / del objetivo.
                spread_bps_trade = 0.0
            else:
                spread_bps_trade = float(panel.spread_bps[exit_i])
            spread_r = spread_bps_trade * factor
        trades.append(
            Trade(
                side=side_name,
                entry_index=entry_i,
                exit_index=exit_i,
                entry_time=index[entry_i],
                exit_time=index[exit_i],
                entry_price=float(ent_px[k]),
                exit_price=float(ex_px[k]),
                stop=float(stop0[k]),
                target=None if np.isnan(tgt0[k]) else float(tgt0[k]),
                reason=reason_name,
                bars_held=int(held[k]),
                risk_price=None if np.isnan(risk) else risk,
                entry_cost_bps=float(ent_cost[k]),
                exit_cost_bps=float(ex_cost[k]),
                r_gross=None if np.isnan(r_gross[k]) else float(r_gross[k]),
                r_cost=None if np.isnan(r_cost[k]) else float(r_cost[k]),
                r_net=None if np.isnan(net) else net,
                spread_r=spread_r,
                slip_r=slip_r,
                comm_r=comm_r,
            )
        )

    daily: dict[date, float] = {}
    swap_model = getattr(cost, "swap", None)
    if swap_model is not None and not getattr(cost, "swap_managed", False):
        adjusted: list[Trade] = []
        for trade in trades:
            if (
                trade.r_net is None
                or trade.risk_price is None
                or not np.isfinite(float(trade.risk_price))
                or float(trade.risk_price) <= 0
            ):
                adjusted.append(trade)
                continue
            swap_r = swap_model.r(
                side=trade.side,
                entry_price=trade.entry_price,
                risk_price=float(trade.risk_price),
                entry_time=trade.entry_time,
                exit_time=trade.exit_time,
                allow_credit=bool(
                    getattr(cost, "swap_allow_credit", False)
                ),
            )
            if swap_r:
                adjusted.append(
                    replace(
                        trade,
                        r_cost=float(trade.r_cost or 0.0) - swap_r,
                        r_net=float(trade.r_net) + swap_r,
                        swap_r=swap_r,
                    )
                )
            else:
                adjusted.append(replace(trade, swap_r=0.0))
        trades = adjusted
    for trade in trades:
        if trade.r_net is None:
            continue
        day = trade.exit_time.tz_convert(limits.session_tz).date()
        daily[day] = daily.get(day, 0.0) + trade.r_net
    daily_r = pd.Series(daily, dtype=float).sort_index()
    if len(daily_r):
        daily_r.index = pd.to_datetime(daily_r.index)
    daily_r.name = "r"

    ledger = None
    if limits.series_ledger:
        if limits.execution != "close_signal":
            raise FastBtError("series_ledger solo existe en close_signal")
        ledger = _series_ledger(trades, bars, cost)

    return FastResult(
        trades=trades,
        daily_r=daily_r,
        metrics=summarize(trades, daily_r) if collect_metrics else {},
        bar_returns=ledger,
        rejected=int(rejected),
        backend=backend(),
        cost_label=getattr(cost, "label", lambda: "")(),
    )


def _series_ledger(
    trades: list[Trade],
    bars: pd.DataFrame,
    cost: Any,
) -> pd.Series:
    """Serie de retornos idéntica a ``backtest_intraday`` (solo paridad)."""

    pos = pd.Series(0.0, index=bars.index, dtype=float)
    for trade in trades:
        start = trade.entry_index + 1
        end = trade.exit_index + 1
        if end > start:
            pos.iloc[start:end] = float(trade.side_sign)
    turnover = pos.diff().abs().fillna(pos.abs())
    cost_bps = cost.ledger_bps(bars).reindex(bars.index).astype(float)
    gross = bars["close"].pct_change().fillna(0.0) * pos
    net = gross - turnover * cost_bps / 10_000.0
    net.name = "returns"
    return net


__all__ = [
    "CfdBpsCosts",
    "CfdProfileCosts",
    "CostPanel",
    "ExitSpec",
    "FastBtError",
    "FastResult",
    "FuturesCosts",
    "HAVE_NUMBA",
    "MissingCostData",
    "PreparedBars",
    "RunLimits",
    "SessionMask",
    "Signals",
    "Trade",
    "atr_window",
    "backend",
    "cfd_costs_from_bps",
    "cost_from_profile",
    "prepare",
    "run",
    "session_mask",
    "set_backend",
]
