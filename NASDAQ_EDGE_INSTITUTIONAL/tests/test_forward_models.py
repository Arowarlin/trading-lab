"""Tests sinteticos de los modelos congelados del forward NQEDGE."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location(
    "forward_models", Path(__file__).resolve().parents[1] / "tools" / "forward_models.py"
)
fm = importlib.util.module_from_spec(SPEC)
sys.modules["forward_models"] = fm
SPEC.loader.exec_module(fm)


def _bars(rows):
    """(o,h,l,c) por vela M5 -> dict preparado a mano."""
    a = np.asarray(rows, dtype=float)
    n = len(a)
    return {
        "b": {
            "slot": np.arange(n),
            "o": a[:, 0],
            "h": a[:, 1],
            "l": a[:, 2],
            "c": a[:, 3],
            "v": np.full(n, 100.0),
            "end_min": 570 + 5 * np.arange(n) + 5,
            "last_i": np.arange(n),
        }
    }


def _session(day="2026-01-05", **extra):
    r = {"day": day}
    r.update(extra)
    return r


# ------------------------------------------------------------------ NQF-A


def test_a_ruptura_cierre_or15():
    r = _session(
        **_bars(
            [
                (100.0, 100.5, 99.5, 100.0),
                (100.0, 100.5, 99.5, 100.0),
                (100.0, 100.5, 99.5, 100.0),
                (100.0, 102.5, 100.0, 102.0),
                (102.0, 102.5, 101.8, 102.2),
            ]
        )
    )
    r["atr5"] = np.array([np.nan, np.nan, np.nan, np.nan, 1.0])
    sig = fm.signal_a(r)
    assert len(sig) == 1
    s = sig[0]
    assert s.variant == "NQF-A" and s.side == 1
    assert s.entry_min == 590  # 9:50, tras el cierre de 9:45
    assert s.stop == pytest.approx(99.5)  # ATR aun NaN -> lado opuesto de la OR
    assert s.target is None  # 2R


def test_a_sin_ruptura_no_hay_senal():
    r = _session(
        **_bars(
            [
                (100.0, 100.5, 99.5, 100.0),
                (100.0, 100.5, 99.5, 100.0),
                (100.0, 100.5, 99.5, 100.0),
                (100.0, 100.7, 99.8, 100.6),  # no supera 100.5 + 1 tick
            ]
        )
    )
    r["atr5"] = np.full(4, 1.0)
    assert fm.signal_a(r) == []


# ------------------------------------------------------------------ NQF-B


def test_b_barrido_onh_y_cierre_dentro():
    r = _session(
        onh=100.0,
        onl=90.0,
        **_bars(
            [
                (99.5, 99.8, 99.3, 99.6),
                (99.6, 101.0, 99.6, 99.8),  # barre ONH >= 2 ticks y cierra dentro
                (99.8, 100.0, 99.5, 99.9),
            ]
        ),
    )
    r["vwap"] = np.array([99.7, 99.7, 99.8])
    r["sd"] = np.ones(3)
    sig = fm.signal_b(r, "ON")
    assert len(sig) == 1
    s = sig[0]
    assert s.side == -1 and s.k5 == 1
    assert s.stop == pytest.approx(101.25)  # extremo + 1 tick
    assert s.target == pytest.approx(99.7)
    assert s.entry_min == 580  # 9:40


def test_b_sin_cierre_dentro_no_hay_senal():
    r = _session(
        onh=100.0,
        onl=90.0,
        **_bars(
            [
                (99.5, 99.8, 99.3, 99.6),
                (99.6, 101.0, 99.6, 100.4),  # barre pero no vuelve dentro
                (100.4, 100.6, 100.1, 100.5),
            ]
        ),
    )
    r["vwap"] = np.full(3, 99.7)
    r["sd"] = np.ones(3)
    assert fm.signal_b(r, "ON") == []


# ------------------------------------------------------------------ NQF-C


def test_c_reversion_vwap_corto():
    bars = [
        (100.0, 100.3, 99.8, 100.1),
        (100.1, 100.4, 99.9, 100.2),
        (100.2, 100.5, 100.0, 100.3),
        (100.3, 102.5, 100.2, 102.0),  # cierra fuera de +2 sigma
        (102.0, 102.1, 100.1, 100.2),  # vuelve dentro
        (100.2, 100.4, 100.0, 100.3),
    ]
    r = _session(**_bars(bars))
    r["vwap"] = np.full(6, 100.0)
    r["sd"] = np.full(6, 0.5)
    sig = fm.signal_c(r)
    assert len(sig) == 1
    s = sig[0]
    assert s.side == -1 and s.k5 == 4
    assert s.stop == pytest.approx(102.75)  # max de las ultimas 6 velas + tick
    assert s.target == pytest.approx(100.0)


def test_c_sin_sigma_no_hay_senal():
    r = _session(
        **_bars(
            [
                (100.0, 100.3, 99.8, 100.1),
                (100.1, 100.4, 99.9, 100.2),
            ]
        )
    )
    r["vwap"] = np.full(2, 100.0)
    r["sd"] = np.zeros(2)
    assert fm.signal_c(r) == []


# ------------------------------------------------------------------ ejecucion


def test_sl_primero_en_la_misma_vela():
    assert fm.same_bar_outcome(100, 99, 102, 103, 98, 1) == "stop"
    assert fm.same_bar_outcome(100, 99, 102, 103, 99.5, 1) == "target"
    assert fm.same_bar_outcome(100, 99, 102, 101, 99.5, 1) is None
    # corto simetrico
    assert fm.same_bar_outcome(100, 101, 98, 101.5, 97, -1) == "stop"


def test_contratos_no_trade_y_comision_obligatoria():
    # 150 / (10*2 + 2*1 + 1) = 150/23 = 6 contratos
    assert fm.contracts_for_risk(10.0, 1.0) == 6
    # 150 / (75*2 + 2 + 1) = 0 -> NO TRADE
    assert fm.contracts_for_risk(75.0, 1.0) == 0
    with pytest.raises(fm.MissingInput, match="Sin datos"):
        fm.contracts_for_risk(10.0, None)


def test_fomc_bloquea_el_dia_completo():
    fomc = {"2026-01-28"}
    assert fm.news_reason("2026-01-28", 600, fomc, []) == "fomc"
    assert fm.news_reason("2026-01-29", 600, fomc, []) is None


def test_tier1_bloquea_mas_menos_5_min_y_cierra_antes():
    tier1 = [("2026-01-29", 600, "CPI"), ("2026-01-30", 510, "NFP")]
    assert fm.news_reason("2026-01-29", 595, set(), tier1).startswith("tier1_pre")
    assert fm.news_reason("2026-01-29", 594, set(), tier1) is None
    assert fm.news_reason("2026-01-29", 605, set(), tier1).startswith("tier1_pre")
    assert fm.news_reason("2026-01-29", 606, set(), tier1) is None
    # 08:30 esta fuera de la sesion: no bloquea
    assert fm.news_reason("2026-01-30", 600, set(), tier1) is None
    assert fm.news_exit_minute("2026-01-29", tier1) == 595
    assert fm.news_exit_minute("2026-01-30", tier1) is None


def _m1(o, h, low, c):
    n = len(o)
    return {
        "t": np.arange(570, 570 + n),
        "o": np.asarray(o, float),
        "h": np.asarray(h, float),
        "l": np.asarray(low, float),
        "c": np.asarray(c, float),
        "v": np.full(n, 100.0),
    }


def _signal(stop=99.0, target=None, side=1):
    return fm.Signal("NQF-T", "2026-01-05", 0, 570, side, stop, target, "test")


def test_ejecuta_stop_primero_y_no_calcula_r():
    r = _m1([100] * 40, [100.5] * 40, [99.5] * 40, [100] * 40)
    r["o"][10] = 100.0
    r["h"][10] = 103.0
    r["l"][10] = 98.0
    ex = fm.execute_signal(r, _signal(), contracts=2, slip_ticks=0.0)
    assert ex.reason == "stop" and ex.exit_price == 99.0
    assert not hasattr(ex, "r_net")


def test_ejecuta_target_y_flat():
    r = _m1([100] * 40, [100.5] * 40, [99.5] * 40, [100] * 40)
    r["h"][10] = 103.0
    ex = fm.execute_signal(r, _signal(), contracts=2, slip_ticks=0.0)
    assert ex.reason == "target" and ex.exit_price == 102.0

    flat = fm.execute_signal(
        _m1([100] * 40, [100.4] * 40, [99.6] * 40, [100] * 40),
        _signal(),
        contracts=2,
        slip_ticks=0.0,
    )
    assert flat.reason == "eod"  # la sesion sintetica no llega a 15:55


def test_ejecuta_cierre_por_noticia():
    r = _m1([100] * 40, [100.4] * 40, [99.6] * 40, [100] * 40)
    ex = fm.execute_signal(
        r, _signal(), contracts=2, slip_ticks=0.0, news_exit=595
    )
    assert ex.reason == "news" and ex.exit_min == 595


def test_target_menor_que_1r_se_descarta():
    r = _m1([100] * 40, [100.4] * 40, [99.6] * 40, [100] * 40)
    sig = _signal(target=100.5)
    assert fm.execute_signal(r, sig, contracts=2, slip_ticks=0.0) is None


def test_prepare_sessions_produce_m5_vwap_y_atr():
    n = 60
    r = {
        "day": "2026-01-05",
        "t": np.arange(570, 570 + n),
        "o": np.full(n, 100.0),
        "h": np.full(n, 100.5),
        "l": np.full(n, 99.5),
        "c": np.full(n, 100.0),
        "v": np.full(n, 10.0),
    }
    out = fm.prepare_sessions([r])
    b = out[0]["b"]
    assert len(b["c"]) == 12
    assert b["end_min"][0] == 575 and b["end_min"][-1] == 630
    assert np.allclose(out[0]["vwap"], 100.0)
    assert out[0]["atr5"].shape == (12,)
