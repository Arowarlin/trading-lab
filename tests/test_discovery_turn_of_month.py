"""Plantilla turn_of_month: calendario NYSE, cierre exacto y sin anticipación."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from tradinglab.discovery import calendars, compiler, dsl, fastbt, genetic
from tradinglab.discovery.engine import synthetic_frame
from tradinglab.discovery.resample import resample_session
from tradinglab.discovery.specs import exit_spec_from_strategy, run_limits_from_strategy
from tradinglab.propfund.costs import load_profile


def _d1_frame(years: float = 2.0, seed: int = 5) -> pd.DataFrame:
    return resample_session(synthetic_frame(years=years, seed=seed), "D1")


def _strategy(n: int = 1, m: int = 2) -> dict:
    strategy = genetic.configured_template(
        "turn_of_month", instrument="US100", timeframe="D1"
    )
    strategy["long_entry"]["n"] = n
    strategy["long_entry"]["m"] = m
    return strategy


def _session_date(stamp) -> date:
    """Sesión NYSE que cubre una etiqueta D1 (apertura 17:00 NY)."""

    local = stamp.tz_convert("America/New_York")
    day = local.date()
    if local.hour >= 17:
        day += timedelta(days=1)
    return day


def _trading_days_only_frame(start: str, end: str) -> pd.DataFrame:
    """D1 con una barra por sesión NYSE, etiquetada el día anterior a 17:00.

    Reproduce los datos reales: la sesión del viernes lleva etiqueta de jueves
    y la del lunes, de domingo. No hay etiqueta en la propia fecha de sesión.
    """

    days = [
        stamp.date()
        for stamp in pd.date_range(start, end, freq="D")
        if stamp.weekday() < 5
        and not calendars.is_holiday(calendars.NYSE, stamp.date())
    ]
    labels = [
        pd.Timestamp(day) - pd.Timedelta(days=1) + pd.Timedelta(hours=17)
        for day in days
    ]
    index = pd.DatetimeIndex(labels).tz_localize("America/New_York")
    close = np.arange(len(index), dtype=float) + 100.0
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
        },
        index=index,
    )


def test_pares_calendario_fin_de_semana_y_festivos() -> None:
    # Junio 2024 termina en domingo: último hábil 28-jun; julio empieza el 1.
    assert calendars.month_turn_pairs(
        date(2024, 6, 1), date(2024, 7, 31), 1, 2
    ) == [(date(2024, 6, 28), date(2024, 7, 2))]
    # Noviembre 2024: último hábil 29; diciembre empieza el 2.
    assert calendars.month_turn_pairs(
        date(2024, 11, 1), date(2024, 12, 31), 1, 2
    ) == [(date(2024, 11, 29), date(2024, 12, 3))]
    # Diciembre 2024: 31-dic; enero 2025 salta el 1 y sale el 3.
    assert calendars.month_turn_pairs(
        date(2024, 12, 1), date(2025, 1, 31), 1, 2
    ) == [(date(2024, 12, 31), date(2025, 1, 3))]
    # N=2 desde el penúltimo hábil.
    assert calendars.month_turn_pairs(
        date(2024, 6, 1), date(2024, 7, 31), 2, 3
    )[0] == (date(2024, 6, 27), date(2024, 7, 3))
    assert date(2024, 7, 4) not in calendars.nyse_trading_days(2024, 7)


def test_plantilla_long_only_y_nueve_combinaciones() -> None:
    assert genetic.template_symmetric("turn_of_month") is False
    assert genetic.template_timeframes("turn_of_month") == ("D1",)
    strategy = _strategy()
    assert dsl.validate(strategy) == []
    assert strategy["short_entry"] is None
    from tradinglab.discovery import grid

    strategies = grid.grid_strategies(
        "turn_of_month", instrument="US100", timeframe="D1"
    )
    assert len(strategies) == 9
    assert {item["long_entry"]["n"] for item in strategies} == {1, 2, 3}
    assert {item["long_entry"]["m"] for item in strategies} == {2, 3, 4}


def test_validacion_rechaza_month_turn_en_corto_o_anidado() -> None:
    nested = _strategy()
    nested["long_entry"] = {
        "kind": "and",
        "args": [
            nested["long_entry"],
            {
                "kind": "gt",
                "left": {"kind": "price", "price": "close"},
                "right": {"kind": "const", "value": 0.0},
            },
        ],
    }
    assert any("raíz" in error for error in dsl.validate(nested))
    short = _strategy()
    short["short_entry"] = {"kind": "month_turn", "n": 1, "m": 2}
    assert any("short_entry" in error for error in dsl.validate(short))


def test_senales_y_salida_coinciden_con_el_calendario() -> None:
    frame = _d1_frame()
    strategy = _strategy(1, 2)
    signals = compiler.compile(strategy, frame)
    positions = np.flatnonzero(signals.long_entry)
    assert len(positions) >= 20
    local = frame.index.tz_convert("America/New_York")
    pairs = calendars.month_turn_pairs(
        _session_date(local[0]), _session_date(local[-1]), 1, 2
    )
    expected_entries = {entry for entry, _exit in pairs}
    got_entries = {_session_date(local[position]) for position in positions}
    assert got_entries == expected_entries
    for position in positions:
        exit_pos = int(signals.exit_index[position])
        assert exit_pos > position
        entry_day = _session_date(local[position])
        exit_day = _session_date(local[exit_pos])
        assert (entry_day, exit_day) in pairs


def test_mapea_por_sesion_y_no_por_etiqueta() -> None:
    # Datos como los reales: sin barra etiquetada en la fecha de sesión.
    frame = _trading_days_only_frame("2024-06-01", "2024-12-31")
    strategy = _strategy(1, 2)
    signals = compiler.compile(strategy, frame)
    local = frame.index.tz_convert("America/New_York")
    positions = {
        _session_date(local[position]): int(position)
        for position in np.flatnonzero(signals.long_entry)
    }
    pairs = dict(
        calendars.month_turn_pairs(date(2024, 6, 1), date(2024, 12, 31), 1, 2)
    )
    # Junio 2024 termina en viernes 28: entrada al cierre de esa sesión.
    assert date(2024, 6, 28) in positions
    entry = positions[date(2024, 6, 28)]
    assert local[entry].date() == date(2024, 6, 27)
    assert local[entry].hour == 17
    exit_pos = int(signals.exit_index[entry])
    assert _session_date(local[exit_pos]) == pairs[date(2024, 6, 28)]
    # Noviembre 2024 termina el viernes 29 tras Acción de Gracias: la etiqueta
    # es el festivo 28, pero la sesión es la del 29.
    assert date(2024, 11, 29) in positions
    entry = positions[date(2024, 11, 29)]
    assert local[entry].date() == date(2024, 11, 28)
    exit_pos = int(signals.exit_index[entry])
    assert _session_date(local[exit_pos]) == pairs[date(2024, 11, 29)]


def test_n2_m4_mapea_por_sesion_en_datos_reales() -> None:
    frame = _trading_days_only_frame("2024-06-01", "2024-12-31")
    signals = compiler.compile(_strategy(2, 4), frame)
    local = frame.index.tz_convert("America/New_York")
    positions = {
        _session_date(local[position]): int(position)
        for position in np.flatnonzero(signals.long_entry)
    }
    pairs = dict(
        calendars.month_turn_pairs(date(2024, 6, 1), date(2024, 12, 31), 2, 4)
    )
    # N=2: 27-jun; M=4: 5-jul (el 4 es festivo) -> etiqueta 4-jul 17:00.
    assert date(2024, 6, 27) in positions
    entry = positions[date(2024, 6, 27)]
    exit_pos = int(signals.exit_index[entry])
    assert _session_date(local[exit_pos]) == date(2024, 7, 5)
    assert local[exit_pos].date() == date(2024, 7, 4)
    assert pairs[date(2024, 6, 27)] == date(2024, 7, 5)


def test_sin_anticipacion_cambiar_el_futuro_no_cambia_las_entradas() -> None:
    frame = _d1_frame()
    changed = frame.copy()
    changed.loc[changed.index >= changed.index[100], ["open", "high", "low", "close"]] *= 1.5
    first = compiler.compile(_strategy(), frame)
    second = compiler.compile(_strategy(), changed)
    assert np.array_equal(first.long_entry, second.long_entry)
    assert np.array_equal(first.exit_index, second.exit_index)


def test_ejecuta_al_cierre_y_sale_el_dia_m() -> None:
    frame = _d1_frame()
    strategy = _strategy(1, 2)
    model = dsl.Strategy.model_validate(strategy)
    signals = compiler.compile(model, frame)
    cost = fastbt.cost_from_profile(load_profile("CFD-001", "US100", firm="ftmo"))
    limits = fastbt.RunLimits(
        session_tz="America/New_York",
        session_start="00:00",
        session_end="23:59",
        flat_at="23:59",
        weekdays=(0, 1, 2, 3, 4),
    )
    prepared = fastbt.prepare(frame, cost, atr_windows=(14,), sessions=(limits,))
    run_limits = run_limits_from_strategy(
        model, type("S", (), {"weekdays": (0, 1, 2, 3, 4), "session_tz": "America/New_York"})(), close_at_end=True
    )
    result = fastbt.run(
        signals,
        frame,
        exit_spec_from_strategy(model),
        cost,
        run_limits,
        prepared=prepared,
    )
    assert len(result.trades) >= 20
    local = frame.index.tz_convert("America/New_York")
    calendar_exits = 0
    for trade in result.trades:
        assert trade.side == "long"
        assert trade.entry_price == float(frame["close"].iloc[trade.entry_index])
        calendar_pos = int(signals.exit_index[trade.entry_index])
        assert trade.exit_index <= calendar_pos
        entry_day = _session_date(local[trade.entry_index])
        exit_day = _session_date(local[calendar_pos])
        assert (entry_day, exit_day) in calendars.month_turn_pairs(
            _session_date(local[0]), _session_date(local[-1]), 1, 2
        )
        if trade.reason == "calendar_exit":
            calendar_exits += 1
            assert trade.exit_index == calendar_pos
            assert trade.exit_price == float(frame["close"].iloc[trade.exit_index])
    assert calendar_exits >= 20
