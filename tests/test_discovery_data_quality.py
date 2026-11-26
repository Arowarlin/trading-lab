from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tradinglab.discovery.config import SessionSegment, load_engine_config
from tradinglab.discovery.data_quality import (
    _calendar_gap,
    _calendar_gap_session,
    _gap_analysis,
    check_dataset,
    dataset_hash,
    load_and_check,
)
from tradinglab.discovery.source_quality import quality_config


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
    assert report.scheduled_pauses[0]["start_hhmm"] == "07:00"
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
    frame = _frame(days=6, start="2024-01-08", sessions=((8, 0, 16, 20),))
    for hour in (9, 10, 13, 14):
        start = pd.Timestamp("2024-01-08 00:00", tz="UTC") + pd.Timedelta(hours=hour)
        drop = (frame.index >= start) & (frame.index < start + pd.Timedelta(minutes=20))
        frame = frame.loc[~drop]
    report = check_dataset(
        frame,
        "US100.cash",
        "M5",
        segments={
            "is": ("2024-01-08", "2024-01-10"),
            "oos1": ("2024-01-11", "2024-01-12"),
            "oos2": ("2024-01-13", None),
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


def _mixed_granularity() -> pd.DataFrame:
    stamps = []
    stamps.extend(pd.date_range("2024-01-01 16:00", periods=10, freq="1D", tz="UTC"))
    stamps.extend(pd.date_range("2024-02-01 09:00", periods=10, freq="1h", tz="UTC"))
    for day in range(1, 11):
        begin = pd.Timestamp(f"2024-03-{day:02d} 08:00", tz="UTC")
        stamps.extend(pd.date_range(begin, periods=24, freq="5min"))
    close = np.arange(len(stamps), dtype=float) + 100.0
    return pd.DataFrame(
        {"open": close, "high": close + 0.5, "low": close - 0.5, "close": close},
        index=pd.DatetimeIndex(stamps),
    )


def test_mes_de_una_barra_en_el_borde_no_invalida() -> None:
    frame = _frame(days=5, start="2024-01-01")
    edge = frame.iloc[[0]].copy()
    edge.index = [pd.Timestamp("2023-12-31 22:00", tz="UTC")]
    frame = pd.concat([edge, frame]).sort_index()
    report = check_dataset(
        frame,
        "US100.cash",
        "M5",
        segments={
            "is": ("2023-12-31", "2024-01-02"),
            "oos1": ("2024-01-03", "2024-01-04"),
            "oos2": ("2024-01-05", None),
        },
    )
    assert report.granularity["bad_months"] == []
    assert report.granularity["useful_start"].startswith("2023-12-31")


def test_mes_disperso_marca_inicio_util() -> None:
    first = _frame(days=5, start="2024-01-01")
    sparse = _frame(days=1, start="2024-02-01")
    dense = _frame(days=5, start="2024-03-01")
    frame = pd.concat([first, sparse, dense]).sort_index()
    report = check_dataset(
        frame,
        "US100.cash",
        "M5",
        segments={
            "is": ("2024-03-01", "2024-03-03"),
            "oos1": ("2024-03-04", "2024-03-05"),
            "oos2": ("2024-03-06", None),
        },
    )
    assert report.granularity["useful_start"].startswith("2024-03-01")
    assert "2024-02" in {
        item["month"] for item in report.granularity["bad_months"]
    }


def test_granularidad_mixta_marca_inicio_util() -> None:
    frame = _mixed_granularity()
    report = check_dataset(
        frame,
        "US100.cash",
        "M5",
        segments={
            "is": ("2024-03-01", "2024-03-05"),
            "oos1": ("2024-03-06", "2024-03-08"),
            "oos2": ("2024-03-09", None),
        },
    )
    assert report.granularity["useful_start"].startswith("2024-03-01")
    assert {item["month"] for item in report.granularity["bad_months"]} == {
        "2024-01",
        "2024-02",
    }
    assert report.status == "ok"


def test_tramo_antes_del_inicio_util_falla() -> None:
    frame = _mixed_granularity()
    report = check_dataset(
        frame,
        "US100.cash",
        "M5",
        segments={
            "is": ("2024-02-01", "2024-02-28"),
            "oos1": ("2024-03-01", "2024-03-05"),
            "oos2": ("2024-03-06", None),
        },
    )
    assert report.status == "fail"
    assert any("inicio útil" in issue for issue in report.issues)


def _frame_with_pause(days: list[str], pause_utc: str) -> pd.DataFrame:
    frames = []
    for day in days:
        begin = pd.Timestamp(f"{day} 00:00", tz="UTC")
        index = pd.date_range(begin, begin + pd.Timedelta(days=1), freq="5min", inclusive="left")
        start = pd.Timestamp(f"{day} {pause_utc}", tz="UTC")
        drop = (index >= start) & (index < start + pd.Timedelta(minutes=80))
        index = index[~drop]
        close = np.arange(len(index), dtype=float) + 100.0
        frames.append(
            pd.DataFrame(
                {"open": close, "high": close + 0.5, "low": close - 0.5, "close": close},
                index=index,
            )
        )
    return pd.concat(frames).sort_index()


def test_pausa_16_50_ny_con_dst_es_la_misma() -> None:
    summer = [f"2024-07-{day:02d}" for day in range(1, 11)]
    winter = [f"2024-01-{day:02d}" for day in range(8, 18)]
    frame = pd.concat(
        [
            _frame_with_pause(summer, "20:50"),
            _frame_with_pause(winter, "21:50"),
        ]
    ).sort_index()
    report = check_dataset(
        frame,
        "US100.cash",
        "M5",
        segments={
            "is": ("2024-01-08", "2024-01-17"),
            "oos1": ("2024-07-01", "2024-07-10"),
            "oos2": ("2024-07-01", None),
        },
    )
    # Las dos piezas (enero y julio) dejan un hueco de ~6 meses entre ellas.
    # Desde ENG-1 C-01 los huecos largos de M1-M30 ya no se descartan: ese es el
    # único no programado. Lo que este test protege es la pausa con DST.
    assert report.non_scheduled_gaps == 1
    hole = report.gap_thresholds["non_scheduled_samples"][0]
    assert hole["minutes"] > 100 * 24 * 60
    assert report.scheduled_pauses
    assert report.scheduled_pauses[0]["start_hhmm"] == "16:50"
    assert report.scheduled_pauses[0]["count"] == 20


def test_hueco_en_cierre_temprano_es_informativo() -> None:
    days = [f"2024-11-{day:02d}" for day in range(18, 30)]
    frames = []
    for day in days:
        begin = pd.Timestamp(f"{day} 08:00", tz="UTC")
        hours = 14 if day == "2024-11-29" else 12
        index = pd.date_range(
            begin, begin + pd.Timedelta(hours=hours), freq="5min", inclusive="left"
        )
        if day == "2024-11-29":
            drop = (index >= pd.Timestamp(f"{day} 18:00", tz="UTC")) & (
                index < pd.Timestamp(f"{day} 20:00", tz="UTC")
            )
            index = index[~drop]
        close = np.arange(len(index), dtype=float) + 100.0
        frames.append(
            pd.DataFrame(
                {"open": close, "high": close + 0.5, "low": close - 0.5, "close": close},
                index=index,
            )
        )
    frame = pd.concat(frames).sort_index()
    report = check_dataset(
        frame,
        "US100.cash",
        "M5",
        segments={
            "is": ("2024-11-18", "2024-11-25"),
            "oos1": ("2024-11-26", "2024-11-28"),
            "oos2": ("2024-11-29", None),
        },
    )
    assert report.status == "ok"
    assert report.non_scheduled_gaps == 0
    assert report.calendar_gaps
    assert "cierre temprano" in report.calendar_gaps[0]["reason"]


def _pause_frame_17ny() -> pd.DataFrame:
    days = list(pd.bdate_range("2024-03-11", "2024-03-28")) + [
        pd.Timestamp("2024-04-01")
    ]
    frames = []
    for day in days:
        begin = pd.Timestamp(day).tz_localize("UTC")
        index = pd.date_range(begin, begin + pd.Timedelta(days=1), freq="5min", inclusive="left")
        drop = (index >= pd.Timestamp(f"{day.date()} 21:00", tz="UTC")) & (
            index < pd.Timestamp(f"{day.date()} 22:00", tz="UTC")
        )
        index = index[~drop]
        close = np.arange(len(index), dtype=float) + 100.0
        frames.append(
            pd.DataFrame(
                {"open": close, "high": close + 0.5, "low": close - 0.5, "close": close},
                index=index,
            )
        )
    return pd.concat(frames).sort_index()


def test_pausa_17_ny_en_eurusd_sin_huecos_falsos_por_dst() -> None:
    frame = _pause_frame_17ny()
    report = check_dataset(
        frame,
        "EURUSD",
        "M5",
        segments={
            "is": ("2024-03-11", "2024-03-28"),
            "oos1": ("2024-03-29", "2024-03-31"),
            "oos2": ("2024-04-01", None),
        },
    )
    assert report.non_scheduled_gaps == 0
    assert report.scheduled_pauses
    assert report.scheduled_pauses[0]["start_hhmm"] == "17:00"
    assert report.scheduled_pauses[0]["count"] == 15
    assert report.gap_thresholds["pause_tz"] == "America/New_York"
    assert report.gap_thresholds["session_tz"] == "Europe/London"
    assert any("sin calendario" in issue for issue in report.issues)

    config = load_engine_config().data_quality
    scheduled, non_scheduled, _samples, _calendar, _outside = _gap_analysis(
        frame,
        5,
        config,
        pause_tz="Europe/London",
        calendar=None,
    )
    assert scheduled
    assert non_scheduled == 1


def _session_frame(labels: list[str]) -> pd.DataFrame:
    index = pd.DatetimeIndex(
        [pd.Timestamp(label, tz="America/New_York") for label in labels]
    )
    close = np.arange(len(index), dtype=float) + 100.0
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
        },
        index=index,
    )


def _d1_labels(start: str, weeks: int = 3) -> list[str]:
    first = pd.Timestamp(start)
    labels: list[str] = []
    for week in range(weeks):
        sunday = first + pd.Timedelta(days=7 * week)
        for offset in range(5):
            labels.append((sunday + pd.Timedelta(days=offset)).strftime("%Y-%m-%d 17:00"))
    return labels


def _h4_labels(start: str, weeks: int = 2) -> list[str]:
    first = pd.Timestamp(f"{start} 17:00", tz="America/New_York")
    labels: list[str] = []
    for week in range(weeks):
        begin = first + pd.Timedelta(days=7 * week)
        labels.extend(
            stamp.isoformat()
            for stamp in pd.date_range(begin, periods=30, freq="4h")
        )
    return labels


def test_d1_fin_de_semana_normal_no_cuenta() -> None:
    frame = _session_frame(_d1_labels("2024-01-07"))
    config = quality_config(
        load_engine_config().data_quality, "US100", "D1", "dukascopy"
    )
    _scheduled, non_scheduled, _samples, calendar_gaps, _outside = _gap_analysis(
        frame,
        1440,
        config,
        pause_tz="America/New_York",
        calendar="nyse",
    )
    assert non_scheduled == 0
    assert calendar_gaps
    assert all(item["reason"] == "fin de semana" for item in calendar_gaps)


def test_d1_fin_de_semana_con_dst_no_cuenta() -> None:
    frame = _session_frame(_d1_labels("2024-03-03"))
    config = quality_config(
        load_engine_config().data_quality, "US100", "D1", "dukascopy"
    )
    _scheduled, non_scheduled, _samples, calendar_gaps, _outside = _gap_analysis(
        frame,
        1440,
        config,
        pause_tz="America/New_York",
        calendar="nyse",
    )
    assert non_scheduled == 0
    assert calendar_gaps


def test_d1_miercoles_que_falta_si_cuenta() -> None:
    labels = _d1_labels("2024-01-07")
    labels.remove("2024-01-09 17:00")  # sesión del miércoles 10
    frame = _session_frame(labels)
    config = quality_config(
        load_engine_config().data_quality, "US100", "D1", "dukascopy"
    )
    _scheduled, non_scheduled, samples, _calendar, _outside = _gap_analysis(
        frame,
        1440,
        config,
        pause_tz="America/New_York",
        calendar="nyse",
    )
    assert non_scheduled == 1
    assert samples
    assert "2024-01-10" in samples[0].get("reason", "sesión 2024-01-10")


def test_h4_fin_de_semana_no_cuenta_y_sesion_perdida_si() -> None:
    session = SessionSegment(friday_close="16:15", sunday_open="17:00")
    real, _reason = _calendar_gap_session(
        pd.Timestamp("2024-01-12 16:15", tz="America/New_York"),
        pd.Timestamp("2024-01-14 17:00", tz="America/New_York"),
        240,
        6 * 60,
        "nyse",
        session,
        "America/New_York",
    )
    assert real is False

    real, reason = _calendar_gap_session(
        pd.Timestamp("2024-01-10 09:00", tz="America/New_York"),
        pd.Timestamp("2024-01-10 17:00", tz="America/New_York"),
        240,
        6 * 60,
        "nyse",
        session,
        "America/New_York",
    )
    assert real is True
    assert "2024-01-10" in reason


def test_calendario_viernes_a_lunes_y_jueves_a_domingo() -> None:
    # Falta el lunes: viernes 19-ene 17:00 -> lunes 22-ene 17:00.
    real, _reason = _calendar_gap(
        pd.Timestamp("2024-01-19 17:00", tz="America/New_York"),
        pd.Timestamp("2024-01-22 17:00", tz="America/New_York"),
        1440,
        36 * 60,
        "nyse",
        "America/New_York",
    )
    assert real is True
    # Falta el viernes: jueves 18-ene 17:00 -> domingo 21-ene 17:00.
    real, _reason = _calendar_gap(
        pd.Timestamp("2024-01-18 17:00", tz="America/New_York"),
        pd.Timestamp("2024-01-21 17:00", tz="America/New_York"),
        1440,
        36 * 60,
        "nyse",
        "America/New_York",
    )
    assert real is True
    # Año Nuevo en forex: el 1-ene es festivo.
    real, reason = _calendar_gap(
        pd.Timestamp("2023-12-31 17:00", tz="America/New_York"),
        pd.Timestamp("2024-01-01 18:00", tz="America/New_York"),
        60,
        90,
        None,
        "America/New_York",
    )
    assert real is False
    assert "festivo" in reason and "2024-01-01" in reason


def test_us30_usa_nyse_y_los_demas_sin_calendario() -> None:
    config = load_engine_config().data_quality
    assert config.source_for("US30").calendar == "nyse"
    assert config.source_for("US30.cash").calendar == "nyse"
    for symbol in ("GER40", "GER40.cash", "XAUUSD", "EURUSD", "GBPUSD", "USDJPY"):
        assert config.source_for(symbol).calendar is None

    days = [f"2024-07-{day:02d}" for day in range(1, 11)]
    frames = []
    for day in days:
        begin = pd.Timestamp(f"{day} 08:00", tz="UTC")
        index = pd.date_range(begin, begin + pd.Timedelta(hours=12), freq="5min", inclusive="left")
        if day == "2024-07-04":
            drop = (index >= pd.Timestamp(f"{day} 14:00", tz="UTC")) & (
                index < pd.Timestamp(f"{day} 16:00", tz="UTC")
            )
            index = index[~drop]
        close = np.arange(len(index), dtype=float) + 100.0
        frames.append(
            pd.DataFrame(
                {"open": close, "high": close + 0.5, "low": close - 0.5, "close": close},
                index=index,
            )
        )
    frame = pd.concat(frames).sort_index()
    report = check_dataset(
        frame,
        "US30",
        "M5",
        segments={
            "is": ("2024-07-01", "2024-07-05"),
            "oos1": ("2024-07-06", "2024-07-08"),
            "oos2": ("2024-07-09", None),
        },
    )
    assert report.calendar_gaps
    assert any("2024-07-04" in item["start"] for item in report.calendar_gaps)
    assert report.calendar["name"] == "nyse"


def test_sin_sesion_configurada_el_comportamiento_es_el_anterior() -> None:
    # Tres semanas H1 continuas; se borra la segunda semana completa.
    labels = []
    first = pd.Timestamp("2024-01-07 17:00", tz="America/New_York")
    for week in range(3):
        begin = first + pd.Timedelta(days=7 * week)
        end = begin + pd.Timedelta(days=5)
        labels.extend(
            stamp.isoformat() for stamp in pd.date_range(begin, end, freq="h", inclusive="left")
        )
    missing = pd.Timestamp("2024-01-15", tz="America/New_York")
    labels = [
        label
        for label in labels
        if not (
            pd.Timestamp(label).date() >= missing.date()
            and pd.Timestamp(label).date() < (missing + pd.Timedelta(days=5)).date()
        )
    ]
    frame = _session_frame(labels)
    config = quality_config(
        load_engine_config().data_quality, "TEST", "H1", "dukascopy"
    )
    assert config.session_for("dukascopy", "TEST", pd.Timestamp("2024-01-16").date()) is None

    legacy = _gap_analysis(
        frame, 60, config, pause_tz="America/New_York", calendar=None
    )
    con_contexto = _gap_analysis(
        frame,
        60,
        config,
        pause_tz="America/New_York",
        calendar=None,
        symbol="TEST",
        source="dukascopy",
    )
    assert legacy[1] == con_contexto[1] == 1
    assert len(legacy[3]) == len(con_contexto[3])
    assert legacy[2][0]["start"] == con_contexto[2][0]["start"]

