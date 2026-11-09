from __future__ import annotations

import json
from pathlib import Path

import pytest

from tradinglab.execution_model import build_report, collect_variants
from tradinglab.learning import count_tests
from tradinglab.trials import record_trial


@pytest.fixture()
def variants() -> list[dict]:
    """Conjunto fijo y pequeño de variantes; el test no depende del informe real."""
    return [
        {
            "strategy": "orb",
            "params": {"range_bars": 4},
            "trades": 10,
            "commission_bps": 0.07,
            "spread_bps": 1.06,
            "series_bps": 1.00,
        },
        {
            "strategy": "pullback",
            "params": {"fast": 20, "slow": 100},
            "trades": 20,
            "commission_bps": 0.07,
            "spread_bps": 1.06,
            "series_bps": 1.20,
        },
        {
            "strategy": "breakout",
            "params": {"lookback": 8},
            "trades": 30,
            "commission_bps": 0.07,
            "spread_bps": 1.06,
            "series_bps": 1.35,
        },
    ]


@pytest.fixture()
def fixture_db(tmp_path: Path, variants: list[dict]) -> Path:
    db = tmp_path / "lab.db"
    for index, variant in enumerate(variants):
        record_trial(
            db,
            family="fixture_execution_model",
            hypothesis="Variante fija del fixture de execution_model.",
            symbol="EURUSD",
            params=variant["params"],
            result={"num_trades": variant["trades"]},
            outcome="failed",
            source="sweep",
            run_id=f"fixture-{index}",
        )
    return db


@pytest.fixture()
def fixture_reports(tmp_path: Path, variants: list[dict]) -> Path:
    reports = tmp_path / "reports"
    base = reports / "intraday_EURUSD"
    base.mkdir(parents=True)
    payload = {
        "symbol": "EURUSD",
        "cost_model": {"slippage": {"conservative_bps": 2.0}},
        "outcomes": [
            {
                "strategy": variant["strategy"],
                "params": variant["params"],
                "metrics": {"num_trades": variant["trades"]},
                "commission_bps_median": variant["commission_bps"],
                "spread_bps_median": variant["spread_bps"],
                "calibrated_cost_bps": variant["series_bps"],
            }
            for variant in variants
        ],
    }
    (base / "intraday.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    return reports


def test_execution_model_no_cambia_contador_dsr(
    tmp_path: Path,
    variants: list[dict],
    fixture_db: Path,
    fixture_reports: Path,
) -> None:
    """El informe es medición: no registra trials ni mueve el contador DSR."""
    expected = len(variants)
    before = count_tests(fixture_db)
    assert before == expected

    rows = collect_variants(fixture_reports, db_path=fixture_db)
    assert len(rows) == expected
    assert all(row["dsr_count"] == before for row in rows)

    path = build_report(
        tmp_path / "out",
        reports_dir=fixture_reports,
        db_path=fixture_db,
    )
    after = count_tests(fixture_db)

    assert after == before
    text = path.read_text(encoding="utf-8")
    assert f"Variantes registradas: **{expected}**" in text
    assert f"Contador DSR leído: **{before}**" in text
    assert f"## Detalle de las {expected} variantes" in text
    assert "no se registraron trials" in text.lower()
    assert "Eventos" in text
