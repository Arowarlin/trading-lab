"""Confirmación OOS-2 por firma: N = finalistas × cuentas y PSR k=1."""

from __future__ import annotations

import pandas as pd

from tradinglab.discovery import databank, engine, levels
from tradinglab.propfund.costs import CostProfile
from tradinglab.propfund.models import Market
from tradinglab.propfund.registry import load_registry

SEGMENTS = {
    "is": ["2023-01-02", "2023-02-28"],
    "oos1": ["2023-03-01", "2023-03-31"],
    "oos2": ["2023-04-01", None],
}


def _strategy() -> dict:
    return {
        "dsl_version": "1",
        "instrument": "US100",
        "market": "cfd",
        "timeframe": "M5",
        "session": {"start": "09:30", "end": "16:00", "flat_at": "16:00"},
        "long_entry": {
            "kind": "gt",
            "left": {"kind": "price", "price": "close"},
            "right": {"kind": "const", "value": 0.0},
        },
        "short_entry": None,
        "exit": {
            "stop": {"type": "pct", "value": 2.0},
            "target": {"type": "rr", "rr": 1.5},
            "time_exit_bars": 1,
        },
        "limits": {"max_trades_per_day": 100, "cooldown_bars": 0},
    }


def _campaign(db, k: int = 2) -> str:
    campaign_id = f"firm-{k}"
    databank.add_campaign(
        campaign_id,
        {
            "instrument": "US100",
            "timeframe": "M5",
            "n_total": 10,
            "cost": {"account": "CFD-001", "firm": "ftmo", "use_p75": True},
            "session": {
                "tz": "America/New_York",
                "start": "09:30",
                "end": "16:00",
                "flat_at": "16:00",
                "or_minutes": 15,
            },
            "limits": {"weekdays": [0, 1, 2, 3, 4], "stop_n": 14, "trail_n": 14},
            "point": 0.01,
        },
        n_total=10,
        status="done",
        db_path=db,
    )
    databank.set_campaign_status(campaign_id, "done", db_path=db)
    databank.set_campaign_counts(
        campaign_id, n_evaluated=k, n_effective=k, n_finalists=k, db_path=db
    )
    for index in range(k):
        sid = databank.add_strategy(
            campaign_id, _strategy(), status="finalist", level=3, db_path=db
        )
        databank.add_evaluation(
            sid,
            segment="fitness_is",
            cost_profile="CFD-001:US100",
            metrics={
                "is": {"expectancy_r": 0.1},
                "return_dates": pd.date_range("2023-01-03", periods=20).strftime(
                    "%Y-%m-%d"
                ).tolist(),
            },
            trades_count=20,
            returns=[0.01] * 20,
            db_path=db,
        )
        databank.add_evaluation(
            sid,
            segment="oos1",
            cost_profile="CFD-001:US100",
            metrics={
                "expectancy_r": 0.1,
                "return_dates": pd.date_range("2023-03-01", periods=20).strftime(
                    "%Y-%m-%d"
                ).tolist(),
            },
            trades_count=20,
            returns=[0.01] * 20,
            db_path=db,
        )
    return campaign_id


def _setup(db, monkeypatch):
    campaign_id = _campaign(db, 2)
    strategy = databank.list_strategies(
        campaign_id=campaign_id, limit=None, db_path=db
    )[0]
    frame = engine.synthetic_frame(years=0.1, seed=5)
    monkeypatch.setattr(levels, "evaluate", lambda *args, **kwargs: {"level": 3})
    monkeypatch.setattr(levels, "_trial_srs", lambda *args, **kwargs: [0.1, 0.2])
    monkeypatch.setattr(
        levels.robustness,
        "random_baseline",
        lambda *args, **kwargs: {"percentile": 99.0, "status": "ok"},
    )
    monkeypatch.setattr(
        levels.campaigns,
        "read_holdout",
        lambda *args, **kwargs: frame,
    )
    monkeypatch.setattr(
        "tradinglab.propfund.costs.load_profile",
        lambda *args, **kwargs: CostProfile(
            account="CFD-001",
            symbol="US100",
            market=Market.CFD,
            commission_type="zero",
            commission_value=0.0,
            slippage_price=0.0,
            spread_price=0.0,
            spread_p75_price=0.0,
        ),
    )
    return strategy, frame


def test_confirmacion_n_es_finalistas_por_cuentas(tmp_path, monkeypatch) -> None:
    db = tmp_path / "discovery.db"
    strategy, _frame = _setup(db, monkeypatch)
    registry = load_registry()
    accounts = [registry.accounts["CFD-001"], registry.accounts["CFD-006"]]
    monkeypatch.setattr(levels, "_confirm_accounts", lambda _setup: accounts)
    monkeypatch.setattr(
        levels,
        "_account_confirmation",
        lambda account, *args, **kwargs: {
            "account": account.id,
            "status": "NO CONFIRMADA",
            "n_trials": kwargs["n_trials"],
            "dsr": {"dsr": 0.5, "n_trials": kwargs["n_trials"]},
        },
    )
    monkeypatch.setattr(
        levels,
        "dsr_from_returns",
        lambda *args, **kwargs: {
            "dsr": 0.95,
            "status": "ok",
            "n_trials": kwargs.get("n_trials", 1),
        },
    )
    result = levels.confirm(
        int(strategy["id"]),
        approved_by_operator=True,
        db_path=db,
        costs_db=tmp_path / "lab.db",
    )
    assert set(result["firm_confirm"]) == {"CFD-001", "CFD-006"}
    assert result["firm_confirm"]["CFD-001"]["dsr"]["n_trials"] == 4
    assert result["firm_confirm"]["CFD-006"]["n_trials"] == 4
    assert result["dsr_confirm"]["n_trials"] == 4


def test_una_cuenta_conserva_n_y_k(tmp_path, monkeypatch) -> None:
    db = tmp_path / "discovery.db"
    strategy, _frame = _setup(db, monkeypatch)
    registry = load_registry()
    monkeypatch.setattr(
        levels,
        "_confirm_accounts",
        lambda _setup: [registry.accounts["CFD-001"]],
    )
    monkeypatch.setattr(
        levels,
        "dsr_from_returns",
        lambda *args, **kwargs: {
            "dsr": 0.95,
            "status": "ok",
            "n_trials": kwargs.get("n_trials", 1),
        },
    )
    result = levels.confirm(
        int(strategy["id"]),
        approved_by_operator=True,
        db_path=db,
        costs_db=tmp_path / "lab.db",
    )
    assert result["firm_confirm"]["CFD-001"]["dsr"]["n_trials"] == 2
    assert result["dsr_confirm"]["n_trials"] == 2
    assert result["dsr_confirm"]["k_finalists"] == 2
    assert result["firm_confirm"]["CFD-001"]["dsr"] == result["dsr_confirm"]
    assert result["dsr_confirm"]["kind"] == "dsr_k_finalists"
