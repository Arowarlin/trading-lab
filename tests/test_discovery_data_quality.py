from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tradinglab.discovery.data_quality import (
    check_dataset,
    dataset_hash,
    load_and_check,
)


def _frame(
    days: int = 10,
    *,
    start: str = "2024-01-01",
    sessions: tuple[tuple[int, int, int, int], ...] = ((8, 0, 18, 0),),
) -> pd.DataFrame:
    stamps: list[pd.Timestamp] = []
    base = pd.Timestamp(start, tz="UTC")
    for offset in range(days):
        day = base + pd.Timedelta(days=offset)
        for start_h, start_m, end_h, end_m in sessions:
            begin = day + pd.Timedelta(hours=start_h, minutes=start_m)
            end = day + pd.Timedelta(hours=end_h, minutes=end_m)
            stamps.extend(pd.date_range(begin, end, freq="5min", inclusive="left"))
    index = pd.DatetimeIndex(stamps, tz="UTC").sort_values()
    close = np.arange(len(index), dtype=float) + 100.0
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": 1.0,
        },
        index=index,
    )


SEGMENTS_10D = {
    "is": ("2024-01-01", "2024-01-05"),
    "oos1": ("2024-01-06", "2024-01-08"),
    "oos2": ("2024-01-09", None),
}


def test_dataset_limpio_ok_y_hash_estable() -> None:
    frame = _frame()
    report = check_dataset(frame, "US100.cash", "M5", segments=SEGMENTS_10D)
    assert report.status == "ok"
    assert report.rows == len(frame)
    assert report.dataset_hash
    assert report.segments["is"].rows > 0
    assert report.segments["oos1"].rows > 0

    shuffled = frame.sample(frac=1.0, random_state=7)[["close", "low", "high", "open", "volume"]]
    assert dataset_hash(frame) == dataset_hash(shuffled)


def test_pausa_diaria_recurrente_no_avisa() -> None:
    # 08:00-12:00 y 13:00-18:00: el hueco empieza a las 12:00 todos los días.
    frame = _frame(sessions=((8, 0, 12, 0), (13, 0, 18, 0)))
    report = check_dataset(frame, "US100.cash", "M5", segments=SEGMENTS_10D)
    assert report.status == "ok"
    assert report.non_scheduled_gaps == 0
    assert report.scheduled_pauses
    assert report.scheduled_pauses[0]["start_hhmm"] == "12:00"
    assert report.scheduled_pauses[0]["count"] == 10


def test_hueco_no_recurrente_avisa() -> None:
    frame = _frame()
    day = pd.Timestamp("2024-01-04", tz="UTC")
    drop = (frame.index >= day + pd.Timedelta(hours=14)) & (
        frame.index < day + pd.Timedelta(hours=16)
    )
    frame = frame.loc[~drop]
    report = check_dataset(frame, "US100.cash", "M5", segments=SEGMENTS_10D)
    assert report.status == "warn"
    assert report.non_scheduled_gaps == 1


def test_demasiados_huecos_falla() -> None:
    frame = _frame(days=6, sessions=((8, 0, 16, 20),))
    for hour in (9, 10, 13, 14):
        start = pd.Timestamp("2024-01-01 00:00", tz="UTC") + pd.Timedelta(hours=hour)
        drop = (frame.index >= start) & (frame.index < start + pd.Timedelta(minutes=15))
        frame = frame.loc[~drop]
    report = check_dataset(
        frame,
        "US100.cash",
        "M5",
        segments={
            "is": ("2024-01-01", "2024-01-03"),
            "oos1": ("2024-01-04", "2024-01-05"),
            "oos2": ("2024-01-06", None),
        },
    )
    assert report.non_scheduled_gaps == 4
    assert report.status == "fail"
    assert report.gap_thresholds["fail_if_gap_pct_gt"] == pytest.approx(0.005)


def test_duplicados_y_ohlc_invalido_fallan() -> None:
    frame = _frame(days=2)
    duplicated = pd.concat([frame, frame.iloc[[0]]]).sort_index()
    assert check_dataset(duplicated, "US100.cash", "M5").status == "fail"

    broken = frame.copy()
    broken.iloc[3, broken.columns.get_loc("high")] = broken.iloc[3]["low"] - 1
    assert check_dataset(broken, "US100.cash", "M5").status == "fail"


def test_tramo_vacio_falla() -> None:
    frame = _frame(days=5)
    report = check_dataset(
        frame,
        "US100.cash",
        "M5",
        segments={
            "is": ("2024-01-01", "2024-01-03"),
            "oos1": ("2024-01-04", "2024-01-05"),
            "oos2": ("2025-01-01", None),
        },
    )
    assert report.status == "fail"
    assert report.segments["oos2"].rows == 0
    assert report.segments["oos2"].sealed is True


def test_sin_cache_es_sin_datos(tmp_path: Path) -> None:
    report = load_and_check("NOEXISTE", "M5", cache_dir=tmp_path)
    assert report.status == "fail"
    assert any("Sin datos" in issue for issue in report.issues)


def test_reutiliza_datacheck(monkeypatch) -> None:
    frame = _frame(days=2)
    monkeypatch.setattr(
        "tradinglab.datacheck.check_frame",
        lambda *args, **kwargs: {"status": "ok", "sentinel": True},
    )
    report = check_dataset(frame, "US100.cash", "M5")
    assert report.datacheck == {"status": "ok", "sentinel": True}
