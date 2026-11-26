"""R1 · `point` sale de la especificación del instrumento, nunca 0,01 por defecto."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from tradinglab.discovery import fastbt, jobs, retester
from tradinglab.discovery.spec import SpecError, load_spec
from tradinglab.propfund.instruments import InstrumentPointError, point_size
from tradinglab.tl3 import verify

TABLE = {
    "EURUSD": 0.00001,
    "GBPUSD": 0.00001,
    "USDJPY": 0.001,
    "XAUUSD": 0.01,
    "US100": 0.01,
    "US500": 0.01,
    "US30": 0.01,
}


@pytest.mark.parametrize("source", ["broker", "dukascopy"])
@pytest.mark.parametrize("instrument,expected", TABLE.items())
def test_queue_setup_point_por_instrumento_y_fuente(
    instrument: str, expected: float, source: str
) -> None:
    setup = jobs.QueueSetup(instrument=instrument, timeframe="M5", data_source=source)
    assert setup.point == pytest.approx(expected)


def test_campana_antigua_con_point_0_01_se_corrige() -> None:
    campaign = {
        "id": "vieja",
        "instrument": "EURUSD",
        "timeframe": "H1",
        "config": {"point": 0.01, "seed": 0},
    }
    setup = jobs.QueueSetup.from_campaign(campaign).validated()
    assert setup.point == pytest.approx(0.00001)


def test_instrumento_sin_especificacion_falla_sin_datos_point() -> None:
    with pytest.raises(InstrumentPointError, match="Sin datos: point"):
        jobs.QueueSetup(instrument="ZZZUSD", timeframe="M5")


def test_slippage_plus_2_suma_exactamente_dos_points_por_lado() -> None:
    point = 0.00001
    price = 1.10
    bars = pd.DataFrame({"close": np.array([price, price], dtype=float)})
    panel = fastbt.CostPanel(
        spread_bps=np.zeros(2),
        slip_bps=np.zeros(2),
        comm_bps=np.zeros(2),
    )
    cost = SimpleNamespace(market="cfd")
    slipped = retester._scenario_panel(
        panel, cost, bars, slippage_points=2.0 * point
    )
    expected_bps = 2.0 * point / price * 10_000.0
    assert np.allclose(slipped.entry_bps, expected_bps)
    assert np.allclose(slipped.stop_bps, expected_bps)
    assert np.allclose(slipped.target_bps, expected_bps)
    assert np.allclose(slipped.slip_bps, expected_bps)
    check = verify.magnitude("EURUSD slip+2 bps", expected_bps, 0.0, 1.0)
    assert check["ok"] is True, check
    wrong = verify.magnitude("200 pips como slippage", 0.02 / price * 10_000.0, 0.0, 1.0)
    assert wrong["defect"] is True, wrong


def test_spec_declara_point_distinto_falla(tmp_path) -> None:
    path = tmp_path / "spec.yaml"
    path.write_text(
        """
instrument: EURUSD
timeframe: H1
template: trend_pullback_mtf
mode: ga
data_source: dukascopy
account: CFD-001
point: 0.01
segments:
  is: ["2024-01-01", "2024-03-31"]
  oos1: ["2024-04-01", "2024-05-31"]
  oos2: ["2024-06-01", null]
""",
        encoding="utf-8",
    )
    with pytest.raises(SpecError, match="point .* != especificaci"):
        load_spec(path)


def test_point_size_usa_el_catalogo() -> None:
    assert point_size("EURUSD.a") == pytest.approx(0.00001)
    assert point_size("us100.cash") == pytest.approx(0.01)
    assert point_size("NQ") == pytest.approx(0.25)
