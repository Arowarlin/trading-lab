"""COLA-MOTOR-FLAT · M1: comportamiento ``legacy`` documentado e identidad.

Estos tests reproducen el fallo y fijan la identidad del modo por defecto antes
de tocar el motor. Deben pasar antes y después de M2.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from tradinglab.discovery import dsl, fastbt, genetic
from tradinglab.discovery.export_samples import build_samples
from tradinglab.discovery.fastbt import RunLimits, _session_mask
from tradinglab.discovery.timeframes import timeframe_minutes

NY = "America/New_York"
FIXTURES = Path(__file__).parent / "fixtures" / "motor_flat"
TEMPLATES = Path(__file__).parents[1] / "config" / "discovery" / "templates"
TFS = ("M5", "M15", "M30", "H1", "H4")


def _session_bars(
    timeframe: str,
    start: str,
    end: str,
    *,
    days: int = 2,
    first_day: str = "2024-07-01",
    drop_last: bool = False,
) -> pd.DataFrame:
    """Barras sintéticas alineadas a la rejilla del TF, en zona NY."""

    step = timeframe_minutes(timeframe)
    begin_h, begin_m = (int(part) for part in start.split(":"))
    end_h, end_m = (int(part) for part in end.split(":"))
    rows: list[pd.Timestamp] = []
    base = pd.Timestamp(first_day, tz=NY).normalize()
    for offset in range(days):
        current = base + pd.Timedelta(days=offset)
        begin = current + pd.Timedelta(hours=begin_h, minutes=begin_m)
        finish = current + pd.Timedelta(hours=end_h, minutes=end_m)
        if finish <= begin:
            finish += pd.Timedelta(days=1)
        grid = pd.date_range(
            current, current + pd.Timedelta(days=2), freq=f"{step}min", inclusive="left"
        )
        stamps = [stamp for stamp in grid if begin <= stamp <= finish]
        if drop_last and stamps:
            stamps = stamps[:-1]
        rows.extend(stamps)
    index = pd.DatetimeIndex(rows).tz_convert("UTC")
    return pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
        index=index,
    )


def _continuous_bars(timeframe: str, *, days: int = 60) -> pd.DataFrame:
    minutes = timeframe_minutes(timeframe)
    index = pd.date_range(
        "2024-01-01",
        periods=(days * 24 * 60) // minutes,
        freq=f"{minutes}min",
        tz=NY,
    ).tz_convert("UTC")
    return pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
        index=index,
    )


def _limits(**kwargs) -> RunLimits:
    return RunLimits(
        session_tz=NY,
        weekdays=(0, 1, 2, 3, 4, 5, 6),
        **kwargs,
    )


def _flag_at(mask, bars: pd.DataFrame, stamp: str) -> bool:
    target = pd.Timestamp(stamp, tz=NY).tz_convert("UTC")
    position = bars.index.get_loc(target)
    return bool(mask.flat_flag[position])


@pytest.mark.parametrize("first_day", ["2024-07-01", "2024-01-08"])
def test_legacy_1555_no_dispara_en_m15_m30_h1(first_day: str) -> None:
    """Sesión 09:30-15:55 con flat 15:55: solo M5 marca la vela de las 15:55."""

    cases = {
        "M5": True,
        "M15": False,
        "M30": False,
        "H1": False,
    }
    for timeframe, expected in cases.items():
        bars = _session_bars(
            timeframe, "09:30", "15:55", days=3, first_day=first_day
        )
        mask = _session_mask(
            bars,
            _limits(session_start="09:30", session_end="15:55", flat_at="15:55"),
        )
        marked = np.flatnonzero(mask.flat_flag)
        if expected:
            assert marked.size > 0
            for position in marked:
                local = bars.index[position].tz_convert(NY)
                assert (local.hour, local.minute) == (15, 55)
        else:
            assert marked.size == 0, f"{timeframe} no debería marcar ninguna vela"


def test_legacy_overnight_h1_marca_las_0300() -> None:
    """Sesión 18:00-03:00 con flat 02:45: H1 marca la vela de las 03:00."""

    bars = _session_bars("H1", "18:00", "03:00", days=3, first_day="2024-07-01")
    mask = _session_mask(
        bars,
        _limits(session_start="18:00", session_end="03:00", flat_at="02:45"),
    )
    marked = [bars.index[i].tz_convert(NY) for i in np.flatnonzero(mask.flat_flag)]
    assert marked
    assert all((stamp.hour, stamp.minute) == (3, 0) for stamp in marked)


def test_legacy_24h_h1_no_marca_ninguna_vela() -> None:
    """Sesión 24 h con flat 23:55: H1 no marca ninguna vela."""

    bars = _session_bars("H1", "00:00", "23:00", days=3, first_day="2024-07-01")
    mask = _session_mask(
        bars,
        _limits(session_start="00:00", session_end="23:59", flat_at="23:55"),
    )
    assert not mask.flat_flag.any()


def _template_session(name: str) -> dict:
    payload = yaml.safe_load(
        (TEMPLATES / f"{name}.yaml").read_text(encoding="utf-8")
    ) or {}
    return (payload.get("strategy") or {}).get("session") or {}


def test_legacy_flat_flag_identico_a_motor_flat_pre() -> None:
    """Los arrays legacy de 60 días coinciden con la foto previa al cambio."""

    fixture = np.load(FIXTURES / "legacy_flags.npz")
    assert fixture.files
    for key in fixture.files:
        template, timeframe = key.split("|")
        session = _template_session(template)
        bars = _continuous_bars(timeframe)
        mask = _session_mask(
            bars,
            _limits(
                session_start=str(session.get("start")),
                session_end=str(session.get("end")),
                flat_at=str(session.get("flat_at")),
            ),
        )
        np.testing.assert_array_equal(
            mask.flat_flag,
            fixture[key],
            err_msg=f"legacy cambió en {key}",
        )


def _normalize_mq5(source: str) -> str:
    lines = source.replace("\r\n", "\n").split("\n")
    return "\n".join(
        line
        for line in lines
        if not line.startswith("//| Exportador:")
        and not line.startswith("const int FLAT_MODE")
    )


def test_export_legacy_identico_salvo_version_y_flat_mode(tmp_path: Path) -> None:
    """El .mq5 legacy solo puede cambiar en la versión y en ``FLAT_MODE``."""

    result = build_samples(tmp_path)["synthetic_trend"]
    current = result.mq5_path.read_text(encoding="utf-8")
    previous = (FIXTURES / "legacy_synthetic_trend.mq5").read_text(encoding="utf-8")
    assert _normalize_mq5(current) == _normalize_mq5(previous)


def test_flat_mode_legacy_es_el_defecto() -> None:
    """Sin declarar ``flat_mode``, el motor usa ``legacy``."""

    limits = _limits(session_start="09:30", session_end="15:55", flat_at="15:55")
    assert getattr(limits, "flat_mode", "legacy") == "legacy"
    assert fastbt is not None


# ---------------------------------------------------------------------------
# M2 · no_overnight
# ---------------------------------------------------------------------------


def _no_overnight(**kwargs) -> RunLimits:
    return _limits(flat_mode="no_overnight", **kwargs)


@pytest.mark.parametrize(
    ("timeframe", "expected"),
    [("M15", (15, 45)), ("M30", (15, 30)), ("H1", (15, 0))],
)
def test_no_overnight_marca_la_vela_que_contiene_el_flat(
    timeframe: str, expected: tuple[int, int]
) -> None:
    bars = _session_bars(timeframe, "09:30", "15:55", days=3)
    mask = _session_mask(
        bars,
        _no_overnight(
            session_start="09:30", session_end="15:55", flat_at="15:55"
        ),
    )
    marked = [bars.index[i].tz_convert(NY) for i in np.flatnonzero(mask.flat_flag)]
    assert marked
    assert all((stamp.hour, stamp.minute) == expected for stamp in marked)
    # Una sola vela marcada por día de sesión.
    assert len(marked) == 3


def test_no_overnight_m5_dias_normales_identico_a_legacy() -> None:
    bars = _session_bars("M5", "09:30", "15:55", days=3)
    legacy = _session_mask(
        bars,
        _limits(session_start="09:30", session_end="15:55", flat_at="15:55"),
    )
    nuevo = _session_mask(
        bars,
        _no_overnight(
            session_start="09:30", session_end="15:55", flat_at="15:55"
        ),
    )
    np.testing.assert_array_equal(nuevo.flat_flag, legacy.flat_flag)


def _flat_frame() -> pd.DataFrame:
    """H1: día normal, cierre temprano (12:00) y falta la vela de las 15:00."""

    rows: list[pd.Timestamp] = []
    for day, last_hour in (
        ("2024-07-01", 15),
        ("2024-07-02", 12),
        ("2024-07-03", 14),
    ):
        base = pd.Timestamp(day, tz=NY)
        rows.extend(base + pd.Timedelta(hours=hour) for hour in range(9, last_hour + 1))
    index = pd.DatetimeIndex(rows).tz_convert("UTC")
    return pd.DataFrame(
        {"open": 100.0, "high": 100.2, "low": 99.8, "close": 100.0},
        index=index,
    )


def test_no_overnight_no_duerme_en_cierre_temprano_ni_con_vela_faltante() -> None:
    bars = _flat_frame()
    long = np.zeros(len(bars), dtype=bool)
    for stamp in ("2024-07-01 10:00", "2024-07-02 10:00", "2024-07-03 10:00"):
        long[bars.index.get_loc(pd.Timestamp(stamp, tz=NY).tz_convert("UTC"))] = True
    result = fastbt.run(
        fastbt.Signals(long, np.zeros(len(bars), dtype=bool)),
        bars,
        fastbt.ExitSpec(stop="pct", stop_mult=50.0, target=None),
        fastbt.cfd_costs_from_bps(
            commission_bps=0.0, slippage_bps=0.0, spread_bps=0.0
        ),
        _no_overnight(
            session_start="09:00",
            session_end="15:00",
            flat_at="15:00",
            close_at_end=False,
        ),
        collect_metrics=False,
    )
    assert len(result.trades) == 3
    for trade in result.trades:
        entry = trade.entry_time.tz_convert(NY)
        exit_ = trade.exit_time.tz_convert(NY)
        assert entry.date() == exit_.date()
    exits = [trade.exit_time.tz_convert(NY).strftime("%H:%M") for trade in result.trades]
    assert exits == ["15:00", "12:00", "14:00"]


def _h2026_013_nights(mode: str) -> tuple[int, int]:
    from tradinglab.discovery import campaigns, compiler, dsl, jobs, snapshots, specs

    template = genetic.configured_template(
        "h1_sma50_session_long", instrument="US100", timeframe="H1"
    )
    template["session"]["flat_mode"] = mode
    model = dsl.Strategy.model_validate(template)
    try:
        frame = campaigns._source_frame("US100", "H1", "dukascopy")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Sin datos: {exc}")
    frame = snapshots.closed_bars(frame, "H1")
    start = pd.Timestamp("2019-01-02", tz="UTC")
    end = pd.Timestamp("2023-12-31", tz="UTC")
    frame = frame[(frame.index >= start) & (frame.index <= end)]
    setup = jobs.QueueSetup(
        instrument="US100",
        timeframe="H1",
        account="CFD-001",
        firm="ftmo",
        cost_accounts=("CFD-001",),
        cost_mode="target",
        legacy_cost=True,
        session_tz=NY,
        session_start="09:00",
        session_end="10:00",
        flat_at="15:00",
        flat_mode=mode,
        weekdays=(0, 1, 2, 3, 4),
    )
    limits = specs.run_limits_from_strategy(model, setup, close_at_end=True)
    zero = fastbt.cfd_costs_from_bps(
        commission_bps=0.0, slippage_bps=0.0, spread_bps=0.0
    )
    prepared = fastbt.prepare(frame, zero, atr_windows=(14,), sessions=(limits,))
    result = fastbt.run(
        compiler.compile(model, frame),
        frame,
        specs.exit_spec_from_strategy(model),
        zero,
        limits,
        prepared=prepared,
        collect_metrics=False,
    )
    nights = sum(
        1
        for trade in result.trades
        if trade.entry_time.tz_convert(NY).date()
        != trade.exit_time.tz_convert(NY).date()
    )
    return len(result.trades), nights


def test_h2026_013_cero_noches_con_no_overnight() -> None:
    legacy_trades, legacy_nights = _h2026_013_nights("legacy")
    new_trades, new_nights = _h2026_013_nights("no_overnight")
    assert legacy_nights == 21, f"legacy: {legacy_trades} ops, {legacy_nights} noches"
    assert new_nights == 0, f"no_overnight: {new_trades} ops, {new_nights} noches"


def _mq5_const(source: str, name: str) -> int:
    import re

    match = re.search(rf"const int {name} = (\d+);", source)
    assert match, f"falta {name}"
    return int(match.group(1))


def _mirror_base(local: pd.Timestamp, constants: dict) -> bool:
    minute = local.hour * 60 + local.minute
    start = constants["SESSION_START"]
    manage_end = constants["MANAGE_END"]
    flat = constants["FLAT_AT"]
    duration = (manage_end - start) % 1440 or 1440
    flat_relative = (flat - start) % 1440
    relative = (minute - start) % 1440
    tf_seconds = 60 * timeframe_minutes("H1")
    return flat_relative <= relative <= duration or (
        constants["FLAT_MODE"] == 1
        and relative * 60 < flat_relative * 60
        and relative * 60 + tf_seconds > duration * 60
    )


def _mirror_flat_at(bars: pd.DataFrame, index: int, constants: dict) -> bool:
    """Replica en Python la lógica de FlatFlag/FlatFlagAt del .mq5."""

    local = bars.index[index].tz_convert(NY)
    if _mirror_base(local, constants):
        return True
    if constants["FLAT_MODE"] != 1:
        return False
    start = constants["SESSION_START"]
    manage_end = constants["MANAGE_END"]

    def day_key(stamp: pd.Timestamp) -> object:
        value = stamp.date()
        if start > constants["SESSION_END"] and (
            stamp.hour * 60 + stamp.minute
        ) < constants["SESSION_END"]:
            value -= pd.Timedelta(days=1)
        return value

    def in_manage(stamp: pd.Timestamp) -> bool:
        value = stamp.hour * 60 + stamp.minute
        if start < manage_end:
            return start <= value <= manage_end
        return value >= start or value <= manage_end

    if not in_manage(local):
        return False
    day = day_key(local)
    for later in range(index + 1, len(bars)):
        stamp = bars.index[later].tz_convert(NY)
        if day_key(stamp) != day:
            break
        if in_manage(stamp):
            return False
    for prior in range(index - 1, -1, -1):
        stamp = bars.index[prior].tz_convert(NY)
        if day_key(stamp) != day:
            break
        if _mirror_base(stamp, constants):
            return False
    return True


@pytest.mark.parametrize(
    "name",
    [
        "intraday_momentum_close_v3",
        "session_breakout_htf_v3",
        "st_reversal_idx_v3",
        "h1_sma50_session_long_v2",
    ],
)
def test_plantillas_nuevas_usan_no_overnight(name: str) -> None:
    payload = yaml.safe_load(
        (TEMPLATES / f"{name}.yaml").read_text(encoding="utf-8")
    ) or {}
    assert payload["name"] == name
    assert payload["strategy"]["session"]["flat_mode"] == "no_overnight"
    assert dsl.validate(payload["strategy"]) == []
    # La versión anterior sigue en legacy y no se toca.
    previous = {
        "intraday_momentum_close_v3": "intraday_momentum_close_v2",
        "session_breakout_htf_v3": "session_breakout_htf",
        "st_reversal_idx_v3": "st_reversal_idx",
        "h1_sma50_session_long_v2": "h1_sma50_session_long",
    }[name]
    old = yaml.safe_load(
        (TEMPLATES / f"{previous}.yaml").read_text(encoding="utf-8")
    ) or {}
    assert old["strategy"]["session"].get("flat_mode", "legacy") == "legacy"


def test_aviso_estatico_de_flat_at() -> None:
    from tradinglab.discovery.timeframes import flat_at_warning

    assert flat_at_warning("M5", "09:30", "15:55", "15:55") is None
    assert (
        flat_at_warning("M15", "09:30", "15:55", "15:55")
        == "flat_at no dispara en M15: la posición puede dormir"
    )


def test_mq5_flatflag_no_overnight_reproduce_el_array_de_fastbt(
    tmp_path: Path,
) -> None:
    import copy

    from tradinglab.discovery.export_mql5 import export_strategy
    from tradinglab.discovery.export_samples import SYNTHETIC_STRATEGIES

    strategy = copy.deepcopy(SYNTHETIC_STRATEGIES["synthetic_trend"])
    strategy["timeframe"] = "H1"
    strategy["session"].update(
        {
            "start": "09:00",
            "end": "10:00",
            "flat_at": "15:00",
            "flat_mode": "no_overnight",
        }
    )
    source = export_strategy(
        strategy, account_id="CFD-001", out_dir=tmp_path
    ).mq5_path.read_text(encoding="utf-8")
    assert "const int FLAT_MODE = 1;" in source
    assert "bool FlatFlagAt(" in source
    constants = {
        name: _mq5_const(source, name)
        for name in ("SESSION_START", "SESSION_END", "MANAGE_END", "FLAT_AT", "FLAT_MODE")
    }
    bars = _flat_frame()
    mask = _session_mask(
        bars,
        _no_overnight(
            session_start="09:00",
            session_end="15:00",
            flat_at="15:00",
            close_at_end=False,
        ),
    )
    mirror = np.array(
        [_mirror_flat_at(bars, index, constants) for index in range(len(bars))],
        dtype=bool,
    )
    np.testing.assert_array_equal(mirror, mask.flat_flag)
