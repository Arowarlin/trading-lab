from __future__ import annotations

from pathlib import Path

import pytest

from tradinglab.agent_compare import model_ranking
from tradinglab.db import connect, init_db


def _outcome(
    con,
    *,
    model: str,
    day: str,
    rating: str,
    ret: float,
    duration: float = 1.0,
    ticker: str = "SPY",
) -> None:
    con.execute(
        "INSERT INTO decision_outcomes(ts, ticker, decision_date, mode, rating, model, "
        "return_20d, duration_s) VALUES(?,?,?,?,?,?,?,?)",
        ("2026-01-01", ticker, day, "lite", rating, model, ret, duration),
    )


def test_ranking_vacio_sin_datos(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    assert model_ranking(db) == []


def test_ranking_con_datos_sinteticos(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        # modelo A: 3 decisiones, 2 aciertos
        _outcome(con, model="modelo-a", day="2026-01-01", rating="Buy", ret=0.05)
        _outcome(con, model="modelo-a", day="2026-01-02", rating="Buy", ret=-0.02)
        _outcome(con, model="modelo-a", day="2026-01-03", rating="Buy", ret=0.03)
        # modelo B: 1 decisión y acierto
        _outcome(
            con,
            model="modelo-b",
            day="2026-01-01",
            rating="Sell",
            ret=-0.04,
            ticker="AAPL",
        )
        # comparación lite/deep con acuerdo
        con.execute(
            "INSERT INTO agent_comparisons(ts, ticker, decision_date, lite_model, deep_model, "
            "agreement, lite_duration_s, deep_duration_s) VALUES(?,?,?,?,?,?,?,?)",
            ("2026-01-01", "QQQ", "2026-01-01", "modelo-a", "modelo-b", 1, 2.0, 4.0),
        )
        # comparación lite entre modelos
        con.execute(
            "INSERT INTO lite_model_comparisons(ts, ticker, decision_date, model_a, model_b, "
            "agreement, elapsed_a, elapsed_b) VALUES(?,?,?,?,?,?,?,?)",
            ("2026-01-02", "QQQ", "2026-01-02", "modelo-a", "modelo-b", 0, 1.5, 3.5),
        )
        # llamadas con validación de esquema
        con.execute(
            "INSERT INTO llm_calls(ts, model, ok, schema_ok, latency_ms) VALUES(?,?,?,?,?)",
            ("2026-01-01", "modelo-a", 1, 1, 1200),
        )
        con.execute(
            "INSERT INTO llm_calls(ts, model, ok, schema_ok, latency_ms) VALUES(?,?,?,?,?)",
            ("2026-01-02", "modelo-a", 1, 0, 2400),
        )
        con.execute(
            "INSERT INTO llm_calls(ts, model, ok, schema_ok, latency_ms) VALUES(?,?,?,?,?)",
            ("2026-01-03", "modelo-b", 1, 1, 900),
        )

    rows = model_ranking(db, min_sample=2)
    by_model = {row["model"]: row for row in rows}

    assert set(by_model) == {"modelo-a", "modelo-b"}
    a = by_model["modelo-a"]
    assert a["n"] == 5  # 3 decisiones + comparación lite/deep + comparación lite
    assert a["n_with_outcome"] == 3
    assert a["hit_rate_20d"] == pytest.approx(2 / 3)
    assert a["mean_return_20d"] == pytest.approx((0.05 - 0.02 + 0.03) / 3)
    assert a["schema_ok_rate"] == pytest.approx(0.5)
    assert a["agreement_rate"] == pytest.approx(0.5)
    assert a["median_latency_s"] == pytest.approx(1.2)  # 1.0 x3, 1.2, 1.5, 2.0 y 2.4
    assert a["insufficient"] is False

    b = by_model["modelo-b"]
    assert b["n"] == 3
    assert b["hit_rate_20d"] == pytest.approx(1.0)
    assert b["insufficient"] is False  # n=3 con min_sample=2
    assert b["sample_warning"] == ""


def test_ranking_marca_muestra_insuficiente(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        _outcome(con, model="modelo-c", day="2026-01-01", rating="Buy", ret=0.01)
    rows = model_ranking(db, min_sample=30)
    assert len(rows) == 1
    assert rows[0]["insufficient"] is True
    assert "muestra insuficiente" in rows[0]["sample_warning"]


def test_ranking_ordena_por_acierto(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        _outcome(con, model="malo", day="2026-01-01", rating="Buy", ret=-0.05)
        _outcome(
            con, model="bueno", day="2026-01-01", rating="Buy", ret=0.05, ticker="AAPL"
        )
    rows = model_ranking(db, min_sample=1)
    assert [row["model"] for row in rows] == ["bueno", "malo"]


def test_ranking_sin_retornos_no_inventa_aciertos(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        con.execute(
            "INSERT INTO decision_outcomes(ts, ticker, decision_date, mode, rating, model) "
            "VALUES(?,?,?,?,?,?)",
            ("2026-01-01", "SPY", "2026-01-01", "lite", "Hold", "modelo-h"),
        )
    rows = model_ranking(db, min_sample=1)
    assert rows[0]["n"] == 1
    assert rows[0]["hit_rate_20d"] is None
    assert rows[0]["mean_return_20d"] is None
