"""Ejecuci├│n de campa├▒as de cesta (N2) con datos sint├®ticos y DB temporal."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import yaml

from tradinglab.discovery import basket, campaigns, databank, engine, feasibility, guard


def _frame(
    edge: bool,
    *,
    price: float,
    seed: int = 2,
    start: str = "2018-01-01",
    end: str = "2022-12-31",
) -> pd.DataFrame:
    index = pd.date_range(start, end, freq="D", tz="UTC")
    rng = np.random.default_rng(seed)
    closes = []
    close = float(price)
    for stamp in index:
        if stamp.day_of_week >= 5:
            closes.append(close)
            continue
        noise = rng.normal(0.0, 0.004)
        if edge:
            in_window = stamp.day >= 27 or stamp.day <= 6
            change = (0.012 if in_window else -0.002) + noise
        else:
            change = noise
        close = close * (1.0 + change)
        closes.append(close)
    values = np.asarray(closes, dtype=float)
    open_ = np.r_[values[0], values[:-1]]
    high = np.maximum(open_, values) * 1.003
    low = np.minimum(open_, values) * 0.997
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": values}, index=index
    )


def _spec_path(
    tmp_path,
    *,
    edge: bool,
    campaign_id: str = "test-cesta",
    single: bool = False,
    cost_mode: str = "target",
) -> tuple:
    cost_accounts = ["CFD-001"] if cost_mode == "target" else ["CFD-001", "CFD-006"]
    path = tmp_path / "cesta.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "basket": ["XAUUSD", "US100"],
                "campaign_id": campaign_id,
                "instrument": "XAUUSD",
                "timeframe": "D1",
                "template": "turn_of_month",
                "profile": "small",
                "mode": "grid",
                "seed": 7,
                "data_source": "dukascopy",
                "account": "CFD-001",
                "firm": "ftmo",
                "segments": {
                    "is": ["2018-01-01", "2020-12-31"],
                    "oos1": ["2021-01-01", "2021-12-31"],
                    "oos2": ["2022-01-01", None],
                },
                "basket_costs": {
                    "XAUUSD": {
                        "account": "CFD-001",
                        "firm": "ftmo",
                        "cost_accounts": cost_accounts,
                        "cost_mode": cost_mode,
                    },
                    "US100": {
                        "account": "CFD-001",
                        "firm": "ftmo",
                        "cost_accounts": cost_accounts,
                        "cost_mode": cost_mode,
                    },
                },
                "grid": {
                    "dimensions": [
                        {
                            "name": "n",
                            "kind": "path",
                            "path": "long_entry.n",
                            "values": [1] if single else [1, 2],
                        },
                        {
                            "name": "m",
                            "kind": "path",
                            "path": "long_entry.m",
                            "values": [2] if single else [2, 3],
                        },
                    ]
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    frames = {
        "XAUUSD": _frame(edge, price=2000.0, seed=2),
        "US100": _frame(edge, price=20_000.0, seed=3),
    }
    return path, frames


def _register(tmp_path, *, edge: bool, campaign_id: str = "test-cesta"):
    db = tmp_path / "discovery.db"
    path, frames = _spec_path(tmp_path, edge=edge, campaign_id=campaign_id)
    campaign = basket.register(path, frames=frames, db_path=db)
    return campaign, frames, db


def _v2_spec_path(tmp_path, *, campaign_id: str = "cesta-v2-cnt"):
    path = tmp_path / "cesta-v2.yaml"
    cost = {
        symbol: {
            "account": "CFD-001",
            "firm": "ftmo",
            "cost_accounts": ["CFD-001"],
            "cost_mode": "target",
        }
        for symbol in ("XAUUSD", "US100")
    }
    grid = {
        "dimensions": [
            {
                "name": "n",
                "kind": "path",
                "path": "long_entry.n",
                "values": [1, 2],
            },
            {
                "name": "m",
                "kind": "path",
                "path": "long_entry.m",
                "values": [2, 3],
            },
        ]
    }
    path.write_text(
        yaml.safe_dump(
            {
                "family_symbols": ["XAUUSD", "US100"],
                "campaign_id": campaign_id,
                "instrument": "XAUUSD",
                "timeframe": "D1",
                "template": "turn_of_month",
                "profile": "small",
                "mode": "grid",
                "seed": 7,
                "data_source": "dukascopy",
                "account": "CFD-001",
                "firm": "ftmo",
                "segments": {
                    "is": ["2018-01-01", "2020-12-31"],
                    "oos1": ["2021-01-01", "2021-12-31"],
                    "oos2": ["2022-01-01", None],
                },
                "protocol_version": 2,
                "cost_model_version": 2,
                "spread_model": "historical_scaled",
                "holdout_start": "2025-07-01",
                "plausible_edge_r": 0.1,
                "family": "calendario",
                "primary": {"n": 1, "m": 3},
                "plateau_grid": grid,
                "grid": grid,
                "cost": cost,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    frames = {
        "XAUUSD": _frame(True, price=2000.0, seed=2),
        "US100": _frame(True, price=20_000.0, seed=3),
    }
    return path, frames


def test_register_cesta_n_total_no_se_multiplica_por_simbolos(tmp_path) -> None:
    campaign, frames, db = _register(tmp_path, edge=True)

    assert campaign["n_total"] == 4
    assert campaign["config"]["basket"]["symbols"] == ["XAUUSD", "US100"]
    assert campaign["config"]["grid_size"] == 4
    assert campaign["instrument"] == "XAUUSD"
    for symbol in ("XAUUSD", "US100"):
        info = campaign["config"]["basket"]["snapshots"][symbol]
        assert info["hash"]
        assert int(info["rows"]) > 100
    stored = databank.get_campaign("test-cesta", db_path=db)
    assert stored is not None and stored["status"] == "draft"

    report = engine.preflight("test-cesta", db_path=db)
    assert report["instrument"] == "BASKET"
    assert report["population"] == 4
    assert report["valid"] == 4

    check = feasibility.check("test-cesta", db_path=db)
    assert check["n_checked"] == 4
    assert check["n_feasible"] >= 1


def test_register_cesta_v2_guarda_campos_de_la_spec(tmp_path) -> None:
    db = tmp_path / "discovery.db"
    path, frames = _v2_spec_path(tmp_path)
    campaign = basket.register(path, frames=frames, db_path=db)
    config = campaign["config"]

    assert campaign["n_total"] == 4
    assert config["n_total"] == 4
    assert config["protocol_version"] == 2
    assert config["primary"] == {"n": 1, "m": 3}
    assert config["plateau_n"] == 3
    assert config["decision_n_total"] == 1
    assert config["cost_model_version"] == 2
    assert config["holdout_start"] == "2025-07-01"
    assert config["plausible_edge_r"] == 0.1
    assert config["family"] == "calendario"
    assert config["plateau_grid"]["dimensions"][0]["name"] == "n"


def test_run_cesta_con_ventaja_pasa(tmp_path) -> None:
    campaign, frames, db = _register(tmp_path, edge=True, campaign_id="cesta-edge")
    campaigns.approve("cesta-edge", db_path=db, verify=False)

    summary = engine.run_campaign("cesta-edge", db_path=db)

    assert summary["n_total"] == 4
    assert summary["n_evaluated"] == 4
    assert summary["feasible"] >= 1
    assert summary["n_finalists"] >= 1
    assert summary["oos1_mean"] is not None and summary["oos1_mean"] > 0
    rows = databank.list_strategies(
        campaign_id="cesta-edge", limit=None, db_path=db
    )
    assert len(rows) == 4
    for row in rows:
        evaluations = databank.list_evaluations(row["id"], db_path=db)
        assert evaluations
        assert "is" in evaluations[0]["metrics"]

    from typer.testing import CliRunner

    from tradinglab.cli import app

    result = CliRunner().invoke(
        app, ["discovery", "results", "cesta-edge", "--db", str(db)]
    )
    assert result.exit_code == 0, result.output
    assert "Cesta: XAUUSD, US100" in result.output


def test_approve_cesta_verifica_preflight_y_viabilidad(tmp_path) -> None:
    campaign, frames, db = _register(tmp_path, edge=True, campaign_id="cesta-approve")
    approved = campaigns.approve("cesta-approve", db_path=db, verify=True)
    assert approved["status"] == "registered"
    assert approved["approved_at"]
    assert approved["n_total"] == 4


def test_run_cesta_sin_ventaja_no_pasa(tmp_path) -> None:
    campaign, frames, db = _register(tmp_path, edge=False, campaign_id="cesta-noise")
    campaigns.approve("cesta-noise", db_path=db, verify=False)

    summary = engine.run_campaign("cesta-noise", db_path=db)

    assert summary["n_total"] == 4
    assert summary["n_evaluated"] == 4
    assert summary["n_finalists"] == 0
    rows = databank.list_strategies(
        campaign_id="cesta-noise", limit=None, db_path=db
    )
    for row in rows:
        evaluations = databank.list_evaluations(row["id"], db_path=db)
        assert evaluations
        payload = evaluations[0]["metrics"]
        assert float(payload["is"]["expectancy_r"]) <= 0


def test_feasibility_cesta_cubre_todas_las_cuentas(tmp_path) -> None:
    db = tmp_path / "discovery.db"
    path, frames = _spec_path(
        tmp_path,
        edge=True,
        campaign_id="cesta-best",
        single=True,
        cost_mode="best",
    )
    basket.register(path, frames=frames, db_path=db)

    report = feasibility.check("cesta-best", db_path=db)

    assert report["n_checked"] == 1
    row = report["rows"][0]
    assert set(row["cost_by_account"]) == {"CFD-001", "CFD-006"}
    assert all(value is not None for value in row["cost_by_account"].values())


def test_guard_impide_rendimiento_sin_aprobar(tmp_path, monkeypatch) -> None:
    campaign, frames, db = _register(tmp_path, edge=True, campaign_id="cesta-draft")
    monkeypatch.setattr(guard, "ALLOW_UNAPPROVED", False)
    with pytest.raises(guard.UnapprovedPerformanceError, match="sin register"):
        basket.run_campaign("cesta-draft", db_path=db)
    assert databank.count_strategies("cesta-draft", db_path=db) == 0
    assert databank.get_campaign("cesta-draft", db_path=db)["status"] == "draft"


def test_feasibility_cesta_no_calcula_rendimiento(tmp_path, monkeypatch) -> None:
    campaign, frames, db = _register(tmp_path, edge=True, campaign_id="cesta-feas")

    def _boom(*args, **kwargs):
        raise AssertionError("feasibility no debe calcular expectativa/PF")

    monkeypatch.setattr(basket.metrics, "summarize", _boom)
    report = feasibility.check("cesta-feas", db_path=db)
    assert report["n_checked"] == 4
    assert report["trades_is"] is not None and report["trades_is"] > 0
    assert all("trades_is" in row for row in report["rows"])


def test_family_mde_baja_raiz_n():
    one = basket.family_mde(400, 1)
    four = basket.family_mde(400, 4)
    assert one is not None and four is not None
    assert four == pytest.approx(one / 2.0, rel=1e-9)


def test_family_symbols_es_alias_de_basket(tmp_path):
    path = tmp_path / "familia.yaml"
    path.write_text(
        yaml.safe_dump(
            {"family_symbols": ["XAUUSD", "US100"], "campaign_id": "x"},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    assert basket.is_basket_spec(path)
    assert basket._symbols_from({"family_symbols": ["XAUUSD", "US100"]}) == [
        "XAUUSD",
        "US100",
    ]


def test_read_holdout_cesta_es_unica(tmp_path) -> None:
    campaign, frames, db = _register(tmp_path, edge=True, campaign_id="cesta-oos2")
    campaigns.approve("cesta-oos2", db_path=db, verify=False)
    engine.run_campaign("cesta-oos2", db_path=db)
    rows = databank.list_strategies(
        campaign_id="cesta-oos2", limit=None, db_path=db
    )
    strategy_id = rows[0]["id"]

    sealed = campaigns.read_holdout(strategy_id, db_path=db)
    assert set(sealed) == {"XAUUSD", "US100"}
    assert all(len(value) > 0 for value in sealed.values())
    with pytest.raises(campaigns.HoldoutError, match="segunda lectura"):
        campaigns.read_holdout(strategy_id, db_path=db)
