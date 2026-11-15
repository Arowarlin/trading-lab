from __future__ import annotations

import pandas as pd
import pytest

from tradinglab.db import connect, init_db
from tradinglab.ea_forward import EA_CRITERIA, criteria_preview, ensure_forward
from tradinglab.lifecycle import (
    LifecycleError,
    criteria_hash,
    pre_register_external,
    start_external_forward,
)

FROZEN_HASH = "2bfad45ca4ba36fc"


def test_criterios_del_ea_congelados_con_hash():
    payload = criteria_preview()
    assert payload["hash"] == FROZEN_HASH
    assert criteria_hash(EA_CRITERIA) == FROZEN_HASH
    assert EA_CRITERIA["window_days"] == 60
    assert EA_CRITERIA["min_trades"] == 40
    assert EA_CRITERIA["min_forward_pf"] == pytest.approx(1.15)
    assert EA_CRITERIA["min_expectancy_r"] == pytest.approx(0.10)
    assert EA_CRITERIA["max_forward_dd_pct"] == pytest.approx(0.06)
    assert EA_CRITERIA["max_slippage_mean_points"] == pytest.approx(2.0)
    assert EA_CRITERIA["min_entry_match_pct"] == pytest.approx(0.90)
    assert EA_CRITERIA["max_guard_breaches"] == 0


def test_pre_registro_no_admite_otro_hash(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    row = pre_register_external(
        db,
        bot="ea:us100-ftmo1",
        asset="US100.cash",
        criteria=EA_CRITERIA,
    )
    assert row["state"] == "incubando"
    assert row["start_date"] is None
    assert row["criteria_hash"] == FROZEN_HASH

    with pytest.raises(LifecycleError, match="congelados"):
        pre_register_external(
            db,
            bot="ea:us100-ftmo1",
            asset="US100.cash",
            criteria={**EA_CRITERIA, "min_forward_pf": 1.0},
        )


def test_ensure_forward_detecta_criterios_cambiados(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    pre_register_external(
        db,
        bot="ea:us100-ftmo1",
        asset="US100.cash",
        criteria={**EA_CRITERIA, "min_forward_pf": 1.0},
    )
    with pytest.raises(LifecycleError, match="congelados"):
        ensure_forward(db)


def test_el_reloj_arranca_con_un_fill_abierto(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    row = ensure_forward(db)
    frozen = pd.Timestamp(row["frozen_at"])
    fill_ts = (frozen + pd.Timedelta(minutes=5)).isoformat()
    with connect(db) as con:
        con.execute(
            "INSERT INTO fills(ts, qty, price, bot, magic) VALUES(?,?,?,?,?)",
            (fill_ts, 1.0, 20_000.0, "ea:us100-ftmo1", 93010001),
        )
    started = ensure_forward(db)
    expected = (
        pd.Timestamp(fill_ts).tz_convert("America/New_York").date().isoformat()
    )
    assert started["start_date"] == expected


def test_el_reloj_arranca_en_el_primer_fill(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    row = ensure_forward(db)
    assert row["start_date"] is None
    assert row["criteria_hash"] == FROZEN_HASH

    started = start_external_forward(
        db, bot="ea:us100-ftmo1", first_date="2026-11-16"
    )
    assert started["start_date"] == "2026-11-16"
    assert started["end_date"] == "2027-01-15"
    assert started["criteria_hash"] == FROZEN_HASH

    with connect(db) as con:
        events = con.execute(
            "SELECT to_state, criteria_hash FROM lifecycle_events "
            "WHERE bot='ea:us100-ftmo1' ORDER BY id"
        ).fetchall()
    assert [row["to_state"] for row in events] == ["incubando", "incubando"]
    assert events[-1]["criteria_hash"] == FROZEN_HASH
