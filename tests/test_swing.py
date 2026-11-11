from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import tradinglab.swing as swing
from tradinglab.config import Settings
from tradinglab.db import connect, init_db
from tradinglab.intraday import cache_file
from tradinglab.prop.rules import ftmo
from tradinglab.strategies.swing import (
    atr_close_stop,
    daily_bars,
    daily_target_to_intraday,
    trading_day,
    trend_daily_atr,
)
from tradinglab.swing import GRID, daily_returns, run_swing, spread_bps, symbol_point


def _h4_frame(days: int = 900, start: str = "2022-01-03") -> pd.DataFrame:
    """Barras H4 sintéticas con tendencia suave y sin fines de semana."""
    index = pd.date_range(start, periods=days, freq="D", tz="UTC")
    index = index[index.day_of_week < 5]
    stamps = []
    for day in index:
        for hour in (1, 5, 9, 13, 17, 21):
            stamps.append(day + pd.Timedelta(hours=hour))
    stamps = pd.DatetimeIndex(stamps)
    rng = np.random.default_rng(7)
    steps = rng.normal(0.0006, 0.003, len(stamps))
    close = 1800.0 * np.exp(np.cumsum(steps))
    frame = pd.DataFrame(
        {
            "open": close * (1 + rng.normal(0, 0.0002, len(stamps))),
            "high": close * 1.002,
            "low": close * 0.998,
            "close": close,
            "volume": 1000.0,
            "spread": 30.0,
        },
        index=stamps,
    )
    return frame


def _write_cache(cache_dir: Path, symbol: str, frame: pd.DataFrame) -> Path:
    path = cache_file(cache_dir, symbol, "H4")
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path)
    return path


def test_daily_bars_junta_el_domingo_con_el_lunes():
    index = pd.DatetimeIndex(
        [
            "2026-11-08 22:00",  # domingo
            "2026-11-09 02:00",  # lunes
            "2026-11-09 06:00",
            "2026-11-14 10:00",  # sábado (se descarta)
        ],
        tz="UTC",
    )
    frame = pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0, 103.0],
            "high": [101.0, 102.0, 103.0, 104.0],
            "low": [99.0, 100.0, 101.0, 102.0],
            "close": [100.5, 101.5, 102.5, 103.5],
            "volume": [1.0, 2.0, 3.0, 4.0],
        },
        index=index,
    )
    daily = daily_bars(frame)
    assert len(daily) == 1
    assert daily.index[0].date().isoformat() == "2026-11-09"
    assert daily["open"].iloc[0] == 100.0
    assert daily["close"].iloc[0] == 102.5
    assert daily["high"].iloc[0] == 103.0


def test_trading_day_domingo_a_lunes():
    days = pd.DatetimeIndex(["2026-11-08", "2026-11-09", "2026-11-14"], tz="UTC")
    mapped = trading_day(days)
    assert [item.date().isoformat() for item in mapped] == [
        "2026-11-09",
        "2026-11-09",
        "2026-11-14",
    ]


def test_la_senal_diaria_llega_un_dia_despues():
    daily = pd.Series(
        [0.0, 1.0, 1.0],
        index=pd.DatetimeIndex(["2026-11-09", "2026-11-10", "2026-11-11"], tz="UTC"),
    )
    index = pd.DatetimeIndex(
        [
            "2026-11-09 02:00",
            "2026-11-09 18:00",
            "2026-11-10 02:00",
            "2026-11-10 18:00",
            "2026-11-11 02:00",
        ],
        tz="UTC",
    )
    mapped = daily_target_to_intraday(daily, index)
    # la señal del día D se aplica a partir del día D+1 (nunca el mismo día)
    assert mapped.tolist() == [0.0, 0.0, 0.0, 0.0, 1.0]


def test_el_stop_cierra_y_no_reentra_hasta_que_la_senal_vuelve_a_cero():
    index = pd.date_range("2026-01-05", periods=6, freq="D", tz="UTC")
    frame = pd.DataFrame(
        {
            "open": [100, 100, 100, 100, 100, 100],
            "high": [101, 101, 101, 101, 101, 101],
            "low": [99, 99, 90, 99, 99, 99],
            "close": [100, 100, 95, 100, 100, 100],
            "volume": 1.0,
        },
        index=index,
    )
    target = pd.Series([1.0, 1.0, 1.0, 1.0, 1.0, 1.0], index=index)
    stopped = atr_close_stop(target, frame, stop_atr=2.0, atr_window=2)
    # la caída del día 3 rompe el stop y no se reentra aunque la señal siga en 1
    assert stopped.tolist()[3:] == [0.0, 0.0, 0.0]
    assert float(stopped.iloc[0]) == 1.0


def test_trend_daily_atr_reutiliza_la_familia_trend():
    frame = _h4_frame(days=400)
    with_stop = trend_daily_atr(frame, fast=20, slow=100, stop_atr=50.0)
    daily = daily_bars(frame)
    from tradinglab.strategies.trend import trend_signal

    base = trend_signal(daily, fast=20, slow=100, regime=200)
    mapped = daily_target_to_intraday(base.target, pd.DatetimeIndex(frame.index))
    # con un stop enormérrimo no se dispara: el objetivo es la señal mapeada
    assert np.allclose(with_stop.target.to_numpy(), mapped.to_numpy())
    assert with_stop.name == "trend-daily-atr"


def test_spread_bps_usa_el_punto_del_simbolo():
    frame = pd.DataFrame(
        {"close": [1000.0, 2000.0], "spread": [10.0, 10.0]},
        index=pd.date_range("2026-01-05", periods=2, freq="D", tz="UTC"),
    )
    assert spread_bps(frame, point=0.01).iloc[0] == pytest.approx(1.0)
    assert spread_bps(frame, point=0.01).iloc[1] == pytest.approx(0.5)
    assert symbol_point("XAUUSD") == 0.01
    assert symbol_point("NO-EXISTE") == 0.01


def test_daily_returns_no_rellena_fines_de_semana():
    index = pd.DatetimeIndex(
        ["2026-11-06 10:00", "2026-11-06 14:00", "2026-11-09 10:00"], tz="UTC"
    )
    returns = pd.Series([0.01, 0.02, -0.01], index=index)
    daily = daily_returns(returns)
    assert len(daily) == 2
    assert daily.index[0].date().isoformat() == "2026-11-06"
    assert daily.iloc[0] == pytest.approx(1.01 * 1.02 - 1.0)


def test_el_informe_sin_pasar_no_activa_ni_registra_candidato(tmp_path):
    cache = tmp_path / "cache"
    _write_cache(cache, "XAUUSD", _h4_frame(days=700))
    db = tmp_path / "lab.db"
    init_db(db)
    report = run_swing(
        db,
        ftmo(100_000.0, "challenge"),
        cache,
        symbols=("XAUUSD",),
        grid=({"fast": 20, "slow": 100, "stop_atr": 2.0},),
        out_dir=tmp_path / "out",
        paths=20,
        record=True,
    )
    assert report["passed"] == 0
    assert report["results"]
    assert report["data"]["XAUUSD"]["d1"]["status"] == "Sin datos"
    assert report["candidates"] == []
    with connect(db) as con:
        trials = con.execute(
            "SELECT * FROM strategy_trials WHERE family = 'TREND'"
        ).fetchall()
        lifecycle = con.execute("SELECT * FROM lifecycle_bots").fetchall()
    assert trials and trials[0]["outcome"] == "failed"
    assert lifecycle == []
    markdown = (tmp_path / "out" / "swing.md").read_text(encoding="utf-8")
    assert "se documenta y se para" in markdown
    payload = json.loads((tmp_path / "out" / "swing.json").read_text(encoding="utf-8"))
    assert payload["enabled"] is False


def test_una_variante_que_pasa_entra_como_candidato_sin_activarse(
    tmp_path, monkeypatch
):
    cache = tmp_path / "cache"
    _write_cache(cache, "XAUUSD", _h4_frame(days=700))
    db = tmp_path / "lab.db"
    init_db(db)
    monkeypatch.setattr(swing, "_failure_reasons", lambda *a, **k: [])
    report = run_swing(
        db,
        ftmo(100_000.0, "challenge"),
        cache,
        symbols=("XAUUSD",),
        grid=({"fast": 20, "slow": 100, "stop_atr": 2.0},),
        out_dir=tmp_path / "out",
        paths=20,
        record=True,
    )
    assert report["passed"] == 1
    assert report["candidates"]
    assert report["candidates"][0]["state"] == "candidato"
    assert report["candidates"][0]["bot"] == "xauusd-trend-d1"
    with connect(db) as con:
        row = con.execute(
            "SELECT state FROM lifecycle_bots WHERE bot = 'xauusd-trend-d1'"
        ).fetchone()
    assert row["state"] == "candidato"


def test_el_presupuesto_bloquea_el_activo(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    _write_cache(cache, "XAUUSD", _h4_frame(days=400))
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        for index in range(5):
            con.execute(
                "INSERT INTO strategy_trials"
                "(ts, family, hypothesis, symbol, params, result, outcome, reason, "
                "source, run_id, fingerprint, counted) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "2026-11-09T00:00:00+00:00",
                    "TREND",
                    "seed",
                    "XAUUSD",
                    "{}",
                    "{}",
                    "failed",
                    "",
                    "sweep",
                    f"seed{index}",
                    f"fp{index}",
                    1,
                ),
            )
    report = run_swing(
        db,
        ftmo(100_000.0, "challenge"),
        cache,
        symbols=("XAUUSD",),
        grid=({"fast": 20, "slow": 100, "stop_atr": 2.0},),
        out_dir=tmp_path / "out",
        paths=20,
        record=True,
    )
    assert report["results"] == []
    assert any("presupuesto" in item["error"] for item in report["errors"])


def test_la_rejilla_es_pequena_y_usa_los_valores_pedidos():
    assert len(GRID) <= 5
    assert {item["fast"] for item in GRID} == {20, 50}
    assert {item["slow"] for item in GRID} == {100, 200}
    assert {item["stop_atr"] for item in GRID} == {2.0, 3.0}


def test_los_bots_del_carril_siguen_desactivados():
    import yaml

    from tradinglab.config import ROOT

    bots = yaml.safe_load(
        (ROOT / "config" / "intraday_bots.yaml").read_text(encoding="utf-8")
    )["bots"]
    by_id = {item["id"]: item for item in bots}
    for bot_id in ("us100-trend-d1", "xauusd-trend-d1"):
        assert by_id[bot_id]["enabled"] is False
        assert by_id[bot_id]["profile"] == "swing_cfd"
        assert by_id[bot_id]["family"] == "trend"
        assert by_id[bot_id]["strategy"] == "trend_daily_atr"
    profile = yaml.safe_load(
        (ROOT / "config" / "profiles.yaml").read_text(encoding="utf-8")
    )["profiles"]["swing_cfd"]
    assert profile["target_vol"] == 0.10
    assert profile["max_risk_pct"] == 0.005
    assert profile["vol_target"]["enabled"] is False


def test_el_settings_no_necesita_dependencias(tmp_path):
    # el módulo no importa paquetes nuevos; basta con el Settings de siempre
    settings = Settings(mode="paper", data={"cache_dir": str(tmp_path)})
    assert settings.mode == "paper"
