"""T21 · Primaria y meseta: decisión, rejilla y contador."""

from __future__ import annotations

from pathlib import Path

from tradinglab.discovery import campaigns, databank, engine, plateau


def _individual(name: str, expectancy: float) -> engine.Individual:
    return engine.Individual(
        strategy={"exit": {"stop": {"mult": 1.0}}},
        strategy_hash=name,
        rank=0,
        feasible=True,
        metrics={"is": {"expectancy_r": expectancy}, "drift": {"percentile": 95.0}},
        folds=[{"expectancy_r": 0.1}] * 4,
        complexity=0,
    )


def _approved_campaign(
    db: Path,
    name: str,
    config: dict,
    *,
    n_total: int = 9,
) -> None:
    databank.add_campaign(
        name,
        config,
        instrument="US100",
        timeframe="M5",
        template="ny_open_vol_filter",
        status="draft",
        n_total=n_total,
        db_path=db,
    )
    databank.approve_campaign(name, approved_by="test", db_path=db)


def test_meseta_3x3():
    values = [0.1, 0.2, -0.1, 0.3, 0.1, 0.2, -0.2, 0.05, 0.01]
    payload = plateau.summary(values)
    assert payload["plateau_n"] == 9
    assert payload["plateau_pct"] == 7 / 9
    assert payload["plateau_ok"] is True
    assert plateau.summary([-0.1] * 9)["plateau_ok"] is False


def test_primaria_no_cambia_al_permutar_la_rejilla():
    population = [_individual("h1", 0.2), _individual("h2", 0.3)]
    first, _ = engine._rank1_candidates(population, 4, primary_hash="h1")
    second, _ = engine._rank1_candidates(list(reversed(population)), 4, primary_hash="h1")
    assert [item.strategy_hash for item in first] == ["h1"]
    assert [item.strategy_hash for item in second] == ["h1"]


def test_contador_v1_suma_n_total(tmp_path: Path):
    db = tmp_path / "discovery.db"
    databank.init_databank(db)
    _approved_campaign(
        db,
        "v1",
        {"protocol_version": 1, "plateau_n": 0, "decision_n_total": None},
    )
    tests = campaigns.discovery_tests(db)
    assert tests["campaigns"] == 9
    assert tests["total"] == 9


def test_contador_v2_con_primaria_suma_n_total(tmp_path: Path):
    db = tmp_path / "discovery.db"
    databank.init_databank(db)
    _approved_campaign(
        db,
        "v2",
        {
            "protocol_version": 2,
            "primary": {"stop": 2.0},
            "plateau_n": 8,
            "decision_n_total": 1,
        },
    )
    tests = campaigns.discovery_tests(db)
    assert tests["campaigns"] == 9
    assert tests["total"] == 9


def test_contador_v2_antigua_plateau_cero_suma_n_total(tmp_path: Path):
    db = tmp_path / "discovery.db"
    databank.init_databank(db)
    _approved_campaign(
        db,
        "v2-old",
        {
            "protocol_version": 2,
            "primary": {"stop": 2.0},
            "plateau_n": 0,
            "decision_n_total": 1,
        },
    )
    tests = campaigns.discovery_tests(db)
    assert tests["campaigns"] == 9
    assert tests["total"] == 9
