"""NQ-A · Adaptador M1→M5, spread, rolls y validez."""

from __future__ import annotations

import numpy as np
import pandas as pd

from tradinglab.ea_lab.nq_adapter import (
    apply_spread,
    filter_crossing_rolls,
    match_validity,
    resample_m5,
    run_nq,
)
from tradinglab.ea_us100 import load_setfile, params_from_set


def _m1(start: str, values: list[float], *, tz: str | None = None) -> pd.DataFrame:
    index = pd.date_range(start, periods=len(values), freq="min", tz=tz)
    close = np.asarray(values, dtype=float)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close + 0.5,
            "volume": np.ones(len(values)),
        },
        index=index,
    )


def test_remuestreo_m1_a_m5_exacto():
    frame = _m1(
        "2026-01-15 09:30",
        [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    )
    m5 = resample_m5(frame)

    assert list(m5.index) == [
        pd.Timestamp("2026-01-15 09:30"),
        pd.Timestamp("2026-01-15 09:35"),
    ]
    assert m5.iloc[0]["open"] == 1.0
    assert m5.iloc[0]["high"] == 6.0
    assert m5.iloc[0]["low"] == 0.0
    assert m5.iloc[0]["close"] == 5.5
    assert m5.iloc[0]["tickvol"] == 5.0
    assert m5.iloc[1]["open"] == 6.0
    assert m5.iloc[1]["close"] == 10.5


def test_spread_por_franja_con_cambio_de_hora():
    profile = pd.DataFrame(
        {"slot": range(288), "spread": [100.0] * 288}
    )
    profile.loc[114, "spread"] = 80.0
    winter = _m1(
        "2026-01-15 14:30", [10, 11, 12, 13, 14], tz="UTC"
    )
    summer = _m1(
        "2026-07-15 13:30", [10, 11, 12, 13, 14], tz="UTC"
    )

    winter_m5 = apply_spread(resample_m5(winter), profile)
    summer_m5 = apply_spread(resample_m5(summer), profile)

    assert winter_m5.index[0] == pd.Timestamp("2026-01-15 09:30")
    assert summer_m5.index[0] == pd.Timestamp("2026-07-15 09:30")
    assert winter_m5.iloc[0]["spread"] == 80.0
    assert summer_m5.iloc[0]["spread"] == 80.0


def test_descarta_operacion_que_cruza_un_roll():
    trades = pd.DataFrame(
        {
            "t": [pd.Timestamp("2026-01-15 10:00"), pd.Timestamp("2026-01-15 10:00")],
            "t_exit": [
                pd.Timestamp("2026-01-15 11:00"),
                pd.Timestamp("2026-01-15 13:00"),
            ],
            "d": [1, 1],
            "r": [1.0, 1.0],
        }
    )
    filtered, crossed = filter_crossing_rolls(
        trades, [pd.Timestamp("2026-01-15 12:00")]
    )

    assert len(filtered) == 1
    assert crossed == 1
    assert filtered.iloc[0]["t_exit"] == pd.Timestamp("2026-01-15 11:00")


def test_motor_corre_con_barras_del_adaptador():
    frames = []
    for day in range(12):
        stamp = pd.Timestamp("2026-01-05") + pd.Timedelta(days=day)
        values = 100.0 + np.cumsum(
            np.random.default_rng(day).normal(0.0, 0.2, 390)
        )
        index = pd.date_range(
            stamp + pd.Timedelta(hours=9, minutes=30),
            periods=390,
            freq="min",
        )
        frames.append(
            pd.DataFrame(
                {
                    "open": values,
                    "high": values + 0.4,
                    "low": values - 0.4,
                    "close": values + 0.1,
                    "volume": 10.0,
                },
                index=index,
            )
        )
    m1 = pd.concat(frames)
    profile = pd.DataFrame(
        {"slot": range(288), "spread": [100.0] * 288}
    )
    values = load_setfile(
        "integrations/mt5/us100_ftmo1/US100_FTMO_v3_challenge.set"
    )
    result = run_nq(m1, params_from_set(values), profile=profile)

    assert set(result["bars"].columns) >= {
        "open",
        "high",
        "low",
        "close",
        "tickvol",
        "spread",
    }
    assert isinstance(result["trades"], pd.DataFrame)


def _trades(times, r_values, sides=None):
    return pd.DataFrame(
        {
            "t": [pd.Timestamp(item) for item in times],
            "t_exit": [pd.Timestamp(item) + pd.Timedelta(hours=1) for item in times],
            "d": sides or [1] * len(times),
            "r": r_values,
        }
    )


def test_validez_empareja_por_lado_y_barra():
    us100 = _trades(
        [
            "2026-01-15 10:00",
            "2026-01-15 11:00",
            "2026-01-15 12:00",
            "2026-01-15 13:00",
            "2026-01-15 14:00",
        ],
        [1.0, 2.0, 3.0, 4.0, 5.0],
    )
    nq = _trades(
        [
            "2026-01-15 10:05",
            "2026-01-15 11:00",
            "2026-01-15 12:00",
            "2026-01-15 13:00",
            "2026-01-15 16:00",
        ],
        [1.0, 2.0, 3.0, 4.0, 9.0],
    )

    validity = match_validity(nq, us100)

    assert validity.matched == 4
    assert validity.reference == 5
    assert validity.matched_pct == 80.0
    assert validity.correlation == 1.0
    assert validity.valid is True

    orphan = _trades(["2026-01-15 17:00"], [1.0], sides=[-1])
    mismatch = match_validity(orphan, us100)
    assert mismatch.valid is False
