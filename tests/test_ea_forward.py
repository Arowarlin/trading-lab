from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from tradinglab import ea_forward
from tradinglab.db import connect, init_db
from tradinglab.ea_forward import (
    EA_CRITERIA,
    criteria_preview,
    ensure_forward,
    forward_metrics,
    refresh_forward_preregistration,
)
from tradinglab.ea_registry import get_ea
from tradinglab.journal import ClosedTrade
from tradinglab.lifecycle import (
    LifecycleError,
    criteria_hash,
    evaluate_criteria,
    pre_register_external,
    start_external_forward,
)

FROZEN_HASH = "f490642ba7a1f71b"


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
    assert EA_CRITERIA["engine_version"] == "3.2"
    for key in (
        "setfile_sha256",
        "code_sha256",
        "replica_sha256",
        "calendar_sha256",
    ):
        assert len(EA_CRITERIA[key]) == 64


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
            "INSERT INTO fills(ts, qty, price, bot, account, magic) "
            "VALUES(?,?,?,?,?,?)",
            (
                fill_ts,
                1.0,
                20_000.0,
                "ea:us100-ftmo1",
                "ftmo_demo",
                93010001,
            ),
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



def _forward_trade(
    *,
    entry_ts: str,
    entry_price: float,
    pnl: float,
    r_multiple: float,
    side: str = "long",
) -> ClosedTrade:
    return ClosedTrade(
        bot="ea:us100-ftmo1",
        account="ftmo_demo",
        profile="intraday_fx",
        ticker="US100.cash",
        qty=1.0,
        entry_price=entry_price,
        exit_price=entry_price + pnl,
        entry_ts=entry_ts,
        exit_ts=entry_ts[:11] + "16:00:00+00:00",
        pnl=pnl,
        fees=0.0,
        return_pct=0.0,
        holding_hours=1.0,
        day=entry_ts[:10],
        hour=10,
        entry_order_id=1,
        exit_order_id=2,
        exit_fill_id=3,
        risk_usd=100.0,
        r_multiple=r_multiple,
        side=side,
    )


def test_coincidencia_de_entradas_50_y_criterio(tmp_path, monkeypatch):
    db = tmp_path / "lab.db"
    init_db(db)
    trades = [
        _forward_trade(
            entry_ts="2025-07-03T14:02:00+00:00",
            entry_price=100.01,
            pnl=100.0,
            r_multiple=1.0,
        ),
        _forward_trade(
            entry_ts="2025-07-04T15:00:00+00:00",
            entry_price=200.00,
            pnl=-50.0,
            r_multiple=-0.5,
        ),
    ]
    monkeypatch.setattr(ea_forward, "_closed", lambda db_path, ea: trades)
    monkeypatch.setattr(ea_forward, "load_bars", lambda cfg: pd.DataFrame())
    monkeypatch.setattr(ea_forward, "load_setfile", lambda path: {})
    monkeypatch.setattr(ea_forward, "params_from_set", lambda values: {})
    predicted = pd.DataFrame(
        [
            {"t": pd.Timestamp("2025-07-03 10:00:00"), "d": 1, "ent": 100.0},
            {"t": pd.Timestamp("2025-07-04 10:00:00"), "d": 1, "ent": 200.0},
        ]
    )
    monkeypatch.setattr(ea_forward, "run_engine", lambda df, params: predicted)

    metrics = forward_metrics(db)

    assert metrics["n_trades"] == 2
    assert metrics["entry_match_pct"] == pytest.approx(0.50)
    assert metrics["slippage_mean_points"] == pytest.approx(1.0)
    failures = evaluate_criteria({**metrics, "drift_status": "ok"}, EA_CRITERIA)
    assert any("coincidencia de entradas" in item for item in failures)

    passed = evaluate_criteria(
        {**metrics, "entry_match_pct": 1.0, "drift_status": "ok"},
        EA_CRITERIA,
    )
    assert not any("coincidencia de entradas" in item for item in passed)


def test_forward_deriva_r_del_riesgo_del_setfile(tmp_path, monkeypatch):
    db = tmp_path / "lab.db"
    init_db(db)
    trade = replace(
        _forward_trade(
            entry_ts="2026-11-16T14:55:00+00:00",
            entry_price=27_495.13,
            pnl=2_974.01,
            r_multiple=1.0,
        ),
        risk_usd=None,
        r_multiple=None,
    )
    monkeypatch.setattr(ea_forward, "_closed", lambda db_path, ea: [trade])
    monkeypatch.setattr(ea_forward, "load_bars", lambda cfg: pd.DataFrame())
    monkeypatch.setattr(
        ea_forward,
        "load_setfile",
        lambda path: {"InpDynRisk": True, "InpDynBase": 1.0},
    )
    monkeypatch.setattr(ea_forward, "params_from_set", lambda values: {})
    monkeypatch.setattr(
        ea_forward,
        "run_engine",
        lambda df, params: pd.DataFrame({"t": [], "d": [], "ent": []}),
    )

    metrics = forward_metrics(db)

    assert metrics["n_trades"] == 1
    assert metrics["expectancy"] == pytest.approx(2.97401, rel=1e-4)



def test_refresh_preregistro_solo_antes_del_primer_fill(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    old = pre_register_external(
        db,
        bot="ea:us100-ftmo1",
        asset="US100.cash",
        criteria={**EA_CRITERIA, "engine_version": "3.1"},
    )
    assert old["criteria_hash"] != criteria_hash(EA_CRITERIA)

    row = refresh_forward_preregistration(db)

    assert row["criteria_hash"] == criteria_hash(EA_CRITERIA)
    assert row["start_date"] is None
    assert "v3.2" in row["note"]
    with connect(db) as con:
        events = con.execute(
            "SELECT reason, criteria_hash FROM lifecycle_events "
            "WHERE bot='ea:us100-ftmo1' ORDER BY id"
        ).fetchall()
    assert events[-1]["criteria_hash"] == criteria_hash(EA_CRITERIA)
    assert "v3.2" in events[-1]["reason"]

    start_external_forward(
        db, bot="ea:us100-ftmo1", first_date="2026-11-16"
    )
    with pytest.raises(LifecycleError, match="ya empez?"):
        refresh_forward_preregistration(db)



def _insert_fill(con, *, ts, account, side, price, deal_id, magic=93010001):
    cur = con.execute(
        "INSERT INTO fills(ts, qty, price, bot, account, symbol, side, volume, "
        "deal_id, magic, ts_utc, contract_size) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            ts,
            1.0,
            price,
            "ea:us100-ftmo1",
            account,
            "US100.CASH",
            side,
            1.0,
            deal_id,
            magic,
            ts,
            1.0,
        ),
    )
    return int(cur.lastrowid)


def test_forward_usa_la_cuenta_del_ea_e_ignora_la_trial(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    row = ensure_forward(db)
    frozen = pd.Timestamp(row["frozen_at"])
    trial_ts = (frozen + pd.Timedelta(minutes=5)).isoformat()
    demo_ts = (frozen + pd.Timedelta(minutes=10)).isoformat()
    with connect(db) as con:
        _insert_fill(
            con,
            ts=trial_ts,
            account="ftmo_trial_ea",
            side="buy",
            price=20_000,
            deal_id=1,
        )
    assert ensure_forward(db)["start_date"] is None
    with connect(db) as con:
        _insert_fill(
            con, ts=demo_ts, account="ftmo_demo", side="buy", price=20_000, deal_id=2
        )
    started = ensure_forward(db)
    expected = pd.Timestamp(demo_ts).tz_convert("America/New_York").date().isoformat()
    assert started["start_date"] == expected


def test_forward_solo_cuenta_del_ea(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        _insert_fill(
            con,
            ts="2026-11-10T15:00:00+00:00",
            account="ftmo_demo",
            side="buy",
            price=20_000,
            deal_id=10,
        )
        demo_exit = _insert_fill(
            con,
            ts="2026-11-10T16:00:00+00:00",
            account="ftmo_demo",
            side="sell",
            price=20_100,
            deal_id=11,
        )
        _insert_fill(
            con,
            ts="2026-11-11T15:00:00+00:00",
            account="ftmo_trial_ea",
            side="buy",
            price=21_000,
            deal_id=20,
        )
        _insert_fill(
            con,
            ts="2026-11-11T16:00:00+00:00",
            account="ftmo_trial_ea",
            side="sell",
            price=21_100,
            deal_id=21,
        )

    ea = get_ea("us100-ftmo1")
    assert ea is not None
    assert ea_forward.FORWARD_ACCOUNT == ea.account == "ftmo_demo"
    trades = ea_forward._closed(db, ea)
    assert len(trades) == 1
    assert trades[0].exit_fill_id == demo_exit
