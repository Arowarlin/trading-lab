from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from tradinglab import broker_costs


def _ticks() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts": pd.to_datetime(
                [
                    "2026-11-09 08:00:00",
                    "2026-11-09 08:01:00",
                    "2026-11-09 09:00:00",
                    "2026-11-09 09:01:00",
                    "2026-11-09 09:02:00",
                ],
                utc=True,
            ),
            "bid": [1.1000, 1.1000, 1.2000, 1.2000, 1.2000],
            "ask": [1.1001, 1.1002, 1.2003, 1.2001, 1.2004],
        }
    )


def test_hourly_spreads_mediana_p75_y_cobertura():
    rows = broker_costs.hourly_spreads(_ticks(), "eurusd")
    assert list(rows.columns) == broker_costs.SPREAD_COLUMNS
    assert rows["symbol"].tolist() == ["EURUSD", "EURUSD"]
    assert rows["hour_utc"].tolist() == [8, 9]
    assert rows["n_ticks"].tolist() == [2, 3]
    assert rows["source"].tolist() == ["broker", "broker"]
    assert rows.iloc[0]["median_bps"] == pytest.approx((0.909 + 1.818) / 2, rel=1e-3)
    assert rows.iloc[0]["p75_bps"] > rows.iloc[0]["median_bps"]
    assert rows.iloc[1]["p75_bps"] == pytest.approx(2.916, rel=1e-2)


def test_persist_y_load_spreads(tmp_path):
    db = tmp_path / "lab.db"
    rows = broker_costs.hourly_spreads(_ticks(), "EURUSD")
    assert broker_costs.persist_spreads(rows, db) == 2
    loaded = broker_costs.load_spreads(db, symbol="eurusd", source="broker")
    assert len(loaded) == 2
    assert set(loaded["hour_utc"]) == {8, 9}
    # Upsert no duplica
    broker_costs.persist_spreads(rows, db)
    assert len(broker_costs.load_spreads(db, symbol="EURUSD")) == 2


def test_collect_broker_mockea_copy_ticks(tmp_path):
    calls = []

    def fake_copy(symbol, start, end):
        calls.append((symbol, start, end))
        return _ticks()

    result = broker_costs.collect_broker(
        "EURUSD",
        2,
        fake_copy,
        db_path=tmp_path / "lab.db",
    )
    assert calls and calls[0][0] == "EURUSD"
    assert result["status"] == "ok"
    assert result["summary"]["p75_bps"] is not None
    assert len(result["rows"]) == 2
    assert result["hours"]["8"]["source"] == "broker"
    assert result["hours"]["0"] is None


def test_merge_report_marca_sin_datos_y_source(tmp_path):
    result = broker_costs.collect_broker(
        "EURUSD",
        2,
        lambda symbol, start, end: _ticks(),
        db_path=tmp_path / "lab.db",
    )
    report = broker_costs.merge_broker_report(result, tmp_path)
    assert "EURUSD" in report["symbols"]
    md = (tmp_path / "broker_costs.md").read_text(encoding="utf-8")
    assert "sin datos" in md
    assert "| 00 | sin datos | sin datos | 0 | — | — | sin datos |" in md
    assert "broker" in md


def test_dukascopy_sin_datos_y_con_parquet(tmp_path):
    empty = broker_costs.dukascopy_summary("EURUSD", tmp_path)
    assert empty["status"] == "sin datos"
    assert empty["p75_bps"] is None

    frame = _ticks()
    frame.to_parquet(tmp_path / "EURUSD_20261109.parquet", index=False)
    summary = broker_costs.dukascopy_summary("EURUSD", tmp_path)
    assert summary["status"] == "ok"
    assert summary["source"] == "dukascopy"
    assert summary["p75_bps"] is not None


def test_source_spread_sin_datos_no_rellena(tmp_path):
    item = broker_costs.source_spread(
        "EURUSD",
        "broker",
        out_dir=tmp_path,
        db_path=tmp_path / "lab.db",
    )
    assert item["status"] == "sin datos"
    assert item["p75_bps"] is None
    with pytest.raises(ValueError):
        broker_costs.source_spread("EURUSD", "otra", out_dir=tmp_path)


def test_comparison_margen_si_no_y_sin_datos():
    original = {
        "symbol": "EURUSD",
        "run_id": "orig",
        "dsr_n_trials": 57,
        "cost_model": {
            "calibrated_cost_bps_median": 3.07,
            "spread": {"source": "MT5 bars: columna spread, mediana por hora"},
        },
        "outcomes": [{"metrics": {"sharpe": 1.0}}],
    }
    recalc = {
        "symbol": "EURUSD",
        "costs": {"commission_bps_median": 0.217},
        "outcomes": [{"metrics": {"sharpe": 1.0}, "breakeven_cost_bps": 0.23}],
    }
    broker = {"status": "ok", "p75_bps": 1.0}
    duk = {"status": "ok", "p75_bps": 0.4}
    row = broker_costs._comparison_row(original, recalc, broker, duk)
    assert row["broker_cost_bps"] == pytest.approx(0.217 + 1.0 + 2.0)
    assert row["dukascopy_cost_bps"] == pytest.approx(0.217 + 0.4 + 2.0)
    assert row["margin"] is False
    assert "no pasa" in row["sentence"]

    recalc_ok = {
        "symbol": "EURUSD",
        "costs": {"commission_bps_median": 0.0},
        "outcomes": [{"metrics": {"sharpe": 1.0}, "breakeven_cost_bps": 10.0}],
    }
    row_ok = broker_costs._comparison_row(original, recalc_ok, broker, duk)
    assert row_ok["margin"] is True
    assert "pasa a tener margen" in row_ok["sentence"]

    row_sin = broker_costs._comparison_row(
        original,
        recalc_ok,
        {"status": "sin datos", "p75_bps": None},
        {"status": "sin datos", "p75_bps": None},
    )
    assert row_sin["margin"] is None
    assert "sin datos" in row_sin["sentence"]


def test_render_comparison_incluye_tabla_y_frases(tmp_path):
    comparison = {
        "generated_at": "2026-11-09T00:00:00+00:00",
        "rows": [
            {
                "symbol": "EURUSD",
                "old_cost_bps": 3.07,
                "dukascopy_p75_bps": 0.4,
                "dukascopy_cost_bps": 2.62,
                "broker_p75_bps": 1.0,
                "broker_cost_bps": 3.22,
                "broker_cost_optimistic_bps": 1.72,
                "breakeven_bps": 0.23,
                "margin": False,
                "sentence": "EURUSD: no pasa a tener margen.",
            }
        ],
    }
    md = broker_costs.render_comparison(comparison)
    assert "Dukascopy" in md
    assert "Bróker p75" in md
    assert "no pasa a tener margen" in md
    files = broker_costs.write_comparison(comparison, tmp_path)
    assert Path(files["json"]).exists()
    assert Path(files["md"]).exists()
    payload = json.loads(Path(files["json"]).read_text(encoding="utf-8"))
    assert payload["rows"][0]["symbol"] == "EURUSD"


def _stage3_inputs(tmp_path: Path) -> Path:
    reports = tmp_path / "research"
    asset_dir = reports / "intraday_EURUSD"
    asset_dir.mkdir(parents=True)
    original = {
        "symbol": "EURUSD",
        "timeframe": "M15",
        "families": ["range_reversal"],
        "dsr_n_trials": 57,
        "n_trials": 1,
        "run_id": "orig",
        "outcomes": [
            {"metrics": {"sharpe": 1.0}, "breakeven_cost_bps": 0.23}
        ],
        "cost_model": {
            "calibrated_cost_bps_median": 3.07,
            "spread": {"source": "MT5 bars: columna spread, mediana por hora"},
        },
    }
    (asset_dir / "intraday.json").write_text(
        json.dumps(original), encoding="utf-8"
    )
    broker = {
        "symbols": {
            "EURUSD": {
                "summary": {"p75_bps": 1.0, "status": "ok", "source": "broker"},
                "window": {},
            }
        }
    }
    (reports / "broker_costs.json").write_text(
        json.dumps(broker), encoding="utf-8"
    )
    return reports


def _fake_recalc_report() -> dict:
    return {
        "symbol": "EURUSD",
        "timeframe": "M15",
        "costs": {"commission_bps_median": 0.2},
        "cost_model": {
            "spread": {"source": "broker: MT5 ticks p75", "stat": "p75"}
        },
        "outcomes": [
            {"metrics": {"sharpe": 1.0}, "breakeven_cost_bps": 0.23}
        ],
        "dsr_n_trials": 57,
        "recalculation": {"enabled": True},
    }


def test_recalculate_stage3_usa_record_false_y_dsr_original(monkeypatch, tmp_path):
    import tradinglab.intraday as intraday_mod
    import tradinglab.learning as learning_mod

    reports = _stage3_inputs(tmp_path)
    captured = {}

    def fake_run(bars, **kwargs):
        captured.update(kwargs)
        return _fake_recalc_report()

    monkeypatch.setattr(intraday_mod, "load_bars", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(intraday_mod, "run_intraday", fake_run)
    monkeypatch.setattr(learning_mod, "count_tests", lambda *a, **k: 10)
    monkeypatch.setattr(broker_costs, "_write_recalc_report", lambda *a, **k: {})
    monkeypatch.setattr(broker_costs, "write_comparison", lambda *a, **k: {})
    monkeypatch.setattr(
        broker_costs, "merge_comparison_into_broker_report", lambda *a, **k: {}
    )
    monkeypatch.setattr(
        broker_costs,
        "dukascopy_summary",
        lambda *a, **k: {"status": "sin datos", "p75_bps": None},
    )

    result = broker_costs.recalculate_stage3(
        reports_dir=reports,
        cache_dir=tmp_path / "cache",
        db_path=tmp_path / "lab.db",
        assets=("EURUSD",),
    )

    assert captured["record"] is False
    assert captured["dsr_n_trials"] == 57
    assert captured["spread_override_bps"] == pytest.approx(1.0)
    assert captured["spread_override_reliable"] is True
    report = result["assets"]["EURUSD"]["report"]
    assert report["dsr_n_trials"] == 57
    assert report["recalculation"]["dsr_counter_unchanged"] is True
    assert report["recalculation"]["strategy_trials_before"] == 10
    assert report["recalculation"]["strategy_trials_after"] == 10


def test_recalculate_stage3_falla_si_cambia_el_contador(monkeypatch, tmp_path):
    import tradinglab.intraday as intraday_mod
    import tradinglab.learning as learning_mod

    reports = _stage3_inputs(tmp_path)
    counts = iter([10, 11])

    monkeypatch.setattr(intraday_mod, "load_bars", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(
        intraday_mod, "run_intraday", lambda *a, **k: _fake_recalc_report()
    )
    monkeypatch.setattr(learning_mod, "count_tests", lambda *a, **k: next(counts))
    monkeypatch.setattr(broker_costs, "_write_recalc_report", lambda *a, **k: {})
    monkeypatch.setattr(broker_costs, "write_comparison", lambda *a, **k: {})
    monkeypatch.setattr(
        broker_costs, "merge_comparison_into_broker_report", lambda *a, **k: {}
    )
    monkeypatch.setattr(
        broker_costs,
        "dukascopy_summary",
        lambda *a, **k: {"status": "sin datos", "p75_bps": None},
    )

    with pytest.raises(RuntimeError, match="contador DSR"):
        broker_costs.recalculate_stage3(
            reports_dir=reports,
            cache_dir=tmp_path / "cache",
            db_path=tmp_path / "lab.db",
            assets=("EURUSD",),
        )


def test_broker_costs_report_incluye_comparativa(tmp_path):
    result = broker_costs.collect_broker(
        "EURUSD",
        2,
        lambda symbol, start, end: _ticks(),
        db_path=tmp_path / "lab.db",
    )
    broker_costs.merge_broker_report(result, tmp_path)
    comparison = {
        "generated_at": "2026-11-09T00:00:00+00:00",
        "rows": [
            {
                "symbol": "EURUSD",
                "old_cost_bps": 3.07,
                "dukascopy_p75_bps": 0.4,
                "dukascopy_cost_bps": 2.62,
                "broker_p75_bps": 1.0,
                "broker_cost_bps": 3.22,
                "broker_cost_optimistic_bps": 1.72,
                "breakeven_bps": 0.23,
                "margin": False,
                "sentence": "EURUSD: no pasa a tener margen.",
            }
        ],
    }
    broker_costs.merge_comparison_into_broker_report(comparison, tmp_path)
    md = (tmp_path / "broker_costs.md").read_text(encoding="utf-8")
    payload = json.loads(
        (tmp_path / "broker_costs.json").read_text(encoding="utf-8")
    )
    assert "## Comparativa de costes" in md
    assert "no pasa a tener margen" in md
    assert payload["comparison"]["rows"][0]["symbol"] == "EURUSD"
