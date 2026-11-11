from __future__ import annotations

from datetime import date

import pytest

from tradinglab.agent_compare import (
    CompareError,
    _run_deep,
    comparisons,
    report,
    run_comparison,
)
from tradinglab.config import Settings
from tradinglab.db import connect, init_db
from tradinglab.decisions import deep_prompt_hash, report_by_source


def _lite() -> dict:
    return {
        "rating": "Buy",
        "confidence": 0.7,
        "model": "lite-test",
        "elapsed_s": 1.2,
        "context": {"price": 100.0},
    }


def _deep(rating: str = "Buy") -> dict:
    return {
        "rating": rating,
        "confidence": 0.6,
        "model": "deep-test",
        "elapsed_s": 20.0,
        "context": {"price": 100.0},
    }


def test_comparacion_guarda_ambas_fuentes_y_acuerdo(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    today = date.today().isoformat()
    row = run_comparison(
        db,
        "spy",
        day=today,
        lite_runner=lambda *args: _lite(),
        deep_runner=lambda *args: _deep(),
        settings=Settings(),
    )
    assert row["ticker"] == "SPY"
    assert row["lite_rating"] == row["deep_rating"] == "Buy"
    assert row["agreement"] == 1
    assert row["deep_analysts"] == "market,news,fundamentals,social"
    assert row["lite_prompt_hash"]
    assert row["deep_prompt_hash"] == deep_prompt_hash(
        "deep-test", ["market", "news", "fundamentals", "social"], today
    )
    with connect(db) as con:
        outcomes = con.execute(
            "SELECT mode, analysts, duration_s, prompt_hash "
            "FROM decision_outcomes ORDER BY mode"
        ).fetchall()
    assert [item["mode"] for item in outcomes] == ["deep", "lite"]
    assert outcomes[0]["analysts"] == "market,news,fundamentals,social"
    assert outcomes[0]["duration_s"] == pytest.approx(20.0)
    assert outcomes[0]["prompt_hash"] == row["deep_prompt_hash"]
    assert outcomes[1]["analysts"] == "lite"
    assert outcomes[1]["duration_s"] == pytest.approx(1.2)
    assert len(comparisons(db)) == 1
    summary = report(db)
    assert summary["n"] == 1
    assert summary["agreement_rate"] == pytest.approx(1.0)
    assert summary["insufficient"] is True
    assert summary["by_source"][0]["n"] == 1


def test_retrospectiva_se_excluye_del_reporte(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    row = run_comparison(
        db,
        "QQQ",
        day="2026-01-05",
        retrospective=True,
        lite_runner=lambda *args: _lite(),
        deep_runner=lambda *args: _deep("Hold"),
        settings=Settings(),
    )
    assert row["retrospective"] == 1
    assert row["agreement"] == 0
    assert report(db)["n"] == 0


def test_fecha_pasada_exige_retrospectiva(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    with pytest.raises(CompareError, match="retrospective"):
        run_comparison(db, "SPY", day="2026-01-05", settings=Settings())


def test_fallback_de_analistas(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    calls: list[str] = []

    def deep_runner(ticker, day, analysts):
        calls.append(analysts)
        if "," in analysts:
            raise RuntimeError("contexto demasiado grande")
        if analysts == "news":
            return _deep("Hold")
        raise RuntimeError("analista no disponible")

    row = run_comparison(
        db,
        "XAUUSD",
        day=date.today().isoformat(),
        analysts=["market", "news", "social"],
        lite_runner=lambda *args: _lite(),
        deep_runner=deep_runner,
        settings=Settings(),
    )
    assert calls == ["market,news,social", "market", "news"]
    assert row["deep_rating"] == "Hold"
    assert row["deep_analysts"] == "news"
    assert row["deep_error"] is None


def test_errores_se_sanean_y_no_inventan_deep(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    row = run_comparison(
        db,
        "EURUSD",
        day=date.today().isoformat(),
        analysts=["market"],
        lite_runner=lambda *args: _lite(),
        deep_runner=lambda *args: (_ for _ in ()).throw(
            RuntimeError("fallo con token-abc123")
        ),
        settings=Settings(),
    )
    assert row["deep_rating"] is None
    assert row["agreement"] == 0
    assert row["deep_error"] == "fallo con [redacted]"
    assert report_by_source(db)[0]["source"] == "lite"


def test_ticker_invalido(tmp_path):
    db = tmp_path / "lab.db"
    init_db(db)
    with pytest.raises(CompareError, match="ticker"):
        run_comparison(db, "  ", settings=Settings())

def test_el_deep_no_reintenta_sin_presupuesto():
    """Con el presupuesto agotado no se llama al runner ni una vez."""
    calls: list[str] = []

    def runner(ticker, day, names):
        calls.append(names)
        return _deep()

    result, failed, error = _run_deep(
        "SPY", "2026-11-11", ["market", "news"], runner, budget={"remaining": 60}
    )
    assert result is None
    assert calls == []
    assert failed == ["market", "news"]
    assert "presupuesto" in error


def test_el_deep_reintenta_uno_a_uno_si_falla_rapido():
    calls: list[str] = []

    def runner(ticker, day, names):
        calls.append(names)
        raise RuntimeError("400 del modelo")

    result, failed, error = _run_deep(
        "SPY", "2026-11-11", ["market", "news"], runner, budget={"remaining": 1800}
    )
    assert result is None
    assert calls == ["market,news", "market", "news"]
    assert failed == ["market", "news"]
    assert "400" in error

