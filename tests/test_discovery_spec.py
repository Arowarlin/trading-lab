from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tradinglab.config import DEFAULT_DB
from tradinglab.discovery import databank, engine, feasibility
from tradinglab.discovery.spec import SpecError, load_spec
from tradinglab.learning import count_tests


def _spec_text(timeframe: str = "H1") -> str:
    return f"""
instrument: US100
timeframe: {timeframe}
template: asia_range_reversion
profile: small
mode: ga
seed: 11
data_source: dukascopy
account: CFD-001
segments:
  is: ["2024-01-01", "2024-03-31"]
  oos1: ["2024-04-01", "2024-05-31"]
  oos2: ["2024-06-01", null]
"""


def _campaign_rows() -> int:
    path = Path(databank.DEFAULT_DISCOVERY_DB)
    if not path.exists():
        return 0
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        return int(
            con.execute("SELECT COUNT(*) FROM disc_campaigns").fetchone()[0]
        )
    finally:
        con.close()


def test_spec_incompatible_rechaza_h4(tmp_path: Path) -> None:
    path = tmp_path / "spec.yaml"
    path.write_text(_spec_text("H4"), encoding="utf-8")
    with pytest.raises(SpecError, match="no declara H4"):
        load_spec(path)


def test_preflight_y_feasibility_spec_no_tocan_db(tmp_path: Path) -> None:
    path = tmp_path / "spec.yaml"
    path.write_text(_spec_text(), encoding="utf-8")
    frame = engine.synthetic_frame(years=0.5, seed=2)
    before_tests = count_tests(DEFAULT_DB)
    before_rows = _campaign_rows()

    preflight = engine.preflight_spec(path)
    report = feasibility.check_spec(path, bars=frame)

    assert preflight["campaign_id"] == "spec:spec"
    assert preflight["generated"] == preflight["population"] == 40
    assert report["campaign_id"] == "spec:spec"
    assert report["n_checked"] == 40
    assert count_tests(DEFAULT_DB) == before_tests
    assert _campaign_rows() == before_rows
