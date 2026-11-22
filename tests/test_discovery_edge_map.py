"""Edge Map y suggest: determinismo, estados y exclusión de lo probado."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from tradinglab.discovery import (
    data_quality,
    databank,
    edge_map,
    engine,
)
from tradinglab.learning import count_tests
from tradinglab.propfund.registry import Registry

SEGMENTS = {
    "is": ["2023-01-02", "2023-03-31"],
    "oos1": ["2023-04-03", "2023-04-28"],
    "oos2": ["2023-05-01", None],
}


def _frame() -> pd.DataFrame:
    return engine.synthetic_frame(years=0.5, seed=20261125)


def _strategy(net: float = 0.05) -> dict:
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
            "stop": {"type": "atr", "mult": 2.0, "n": 14},
            "target": {"type": "rr", "rr": 2.0},
        },
        "limits": {"max_trades_per_day": 2, "cooldown_minutes": 0},
    }


def _campaign(
    db: Path,
    *,
    campaign_id: str,
    mode: str,
    status: str = "done",
    template: str = "ny_open_vol_filter",
    net: float = 0.05,
    pbo: float | None = 0.74,
    wf_ok: bool | None = False,
    level: int = 3,
    finalist: bool = True,
    frame: pd.DataFrame | None = None,
) -> tuple[dict, int, int]:
    frame = frame or _frame()
    start = pd.Timestamp(SEGMENTS["is"][0], tz="UTC")
    end = frame.index[-1]
    expected = frame[(frame.index >= start) & (frame.index <= end)]
    digest = data_quality.dataset_hash(expected)
    config = {
        "instrument": "US100",
        "timeframe": "M5",
        "template": template,
        "mode": mode,
        "data_source": "broker",
        "is_start": SEGMENTS["is"][0],
        "is_end": SEGMENTS["is"][1],
        "oos1_start": SEGMENTS["oos1"][0],
        "oos1_end": SEGMENTS["oos1"][1],
        "oos2_start": SEGMENTS["oos2"][0],
        "oos2_end": end.isoformat(),
        "dataset_hash": digest,
        "n_total": 2,
        "session": {
            "tz": "America/New_York",
            "start": "09:30",
            "end": "16:00",
            "flat_at": "16:00",
            "or_minutes": 15,
        },
        "limits": {"weekdays": [0, 1, 2, 3, 4], "stop_n": 14, "trail_n": 14},
        "point": 0.01,
        "cost": {"account": "CFD-001", "firm": "ftmo", "use_p75": True},
    }
    databank.add_campaign(
        campaign_id,
        config,
        instrument="US100",
        timeframe="M5",
        template=template,
        status=status,
        dataset_hash=digest,
        db_path=db,
    )
    if status in {"done", "synthetic", "invalid", "rejected"}:
        databank.set_campaign_status(campaign_id, status, db_path=db)
    strategy = _strategy(net)
    sid = databank.add_strategy(
        campaign_id,
        strategy,
        family=template,
        level=level,
        status="finalist" if finalist else "evaluated",
        db_path=db,
    )
    databank.add_evaluation(
        sid,
        segment="fitness_is",
        cost_profile="CFD-001:US100",
        metrics={"is": {"expectancy_r": net}, "cost_r": 0.02},
        trades_count=100,
        returns=[],
        db_path=db,
    )
    if pbo is not None:
        databank.add_validation(
            sid, "pbo", {"pbo": pbo, "status": "ok"}, pbo <= 0.30, db_path=db
        )
    if wf_ok is not None:
        databank.add_validation(
            sid, "wf", {"ok": wf_ok, "status": "ok"}, wf_ok, db_path=db
        )
    if finalist:
        databank.add_lineage(
            sid,
            parent_a=None,
            parent_b=None,
            operator="seed",
            generation=0,
            fitness={"vector": [net]},
            rank=0,
            reason="final",
            db_path=db,
        )
        databank.set_lineage_rank(sid, 0, 1.0, final=True, db_path=db)
    databank.set_campaign_counts(
        campaign_id, n_evaluated=1, n_effective=1, n_finalists=1, db_path=db
    )
    return config, sid, sid


def test_build_determinista_y_sobreajustada_no_candidata(tmp_path: Path) -> None:
    db = tmp_path / "discovery.db"
    _campaign(db, campaign_id="edge-1", mode="ga")
    empty = Registry(firms={}, accounts={})
    first = edge_map.build(
        db,
        data_root=tmp_path,
        costs_db=tmp_path / "lab.db",
        registry=empty,
        bars_loader=lambda _symbol, _tf: _frame(),
    )
    second = edge_map.build(
        db,
        data_root=tmp_path,
        costs_db=tmp_path / "lab.db",
        registry=empty,
        bars_loader=lambda _symbol, _tf: _frame(),
    )
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    row = first["combos"][0]
    assert row["state"] == "sobreajustada"
    assert row["candidate_count"] == 0
    assert row["overfit_count"] == 1
    assert row["pbo"] == pytest.approx(0.74)
    assert row["wf_ok"] is False
    assert row["dataset_source"] == "fuente viva"
    assert row["dataset_verified"] is True


def test_estado_invalida_y_sin_edge(tmp_path: Path) -> None:
    db = tmp_path / "discovery.db"
    _campaign(
        db,
        campaign_id="edge-invalid",
        mode="grid",
        status="invalid",
        template="intraday_momentum_close",
        pbo=None,
        wf_ok=None,
        finalist=False,
    )
    _campaign(
        db,
        campaign_id="edge-empty",
        mode="ga",
        status="done",
        template="intraday_momentum_close_v2",
        net=-0.10,
        pbo=None,
        wf_ok=None,
        level=1,
        finalist=False,
    )
    report = edge_map.build(
        db,
        data_root=tmp_path,
        costs_db=tmp_path / "lab.db",
        registry=Registry(firms={}, accounts={}),
        bars_loader=lambda _symbol, _tf: _frame(),
    )
    states = {row["template"]: row["state"] for row in report["combos"]}
    assert states["intraday_momentum_close"] == "inválida"
    assert states["intraday_momentum_close_v2"] == "edge bruto que el coste elimina"


def test_suggest_excluye_lo_probado_y_etiqueta(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "discovery.db"
    databank.init_databank(db)
    frame = _frame()
    start = pd.Timestamp("2023-01-02", tz="UTC")
    end = frame.index[-1]
    digest = data_quality.dataset_hash(frame[(frame.index >= start) & (frame.index <= end)])
    databank.add_campaign(
        "tested",
        {
            "instrument": "US100",
            "timeframe": "M5",
            "template": "ny_open_vol_filter",
            "mode": "grid",
            "data_source": "broker",
            "is_start": "2023-01-02",
            "is_end": "2023-03-31",
            "oos1_start": "2023-04-03",
            "oos1_end": "2023-04-28",
            "oos2_start": "2023-05-01",
            "oos2_end": end.isoformat(),
            "dataset_hash": digest,
        },
        instrument="US100",
        timeframe="M5",
        template="ny_open_vol_filter",
        status="done",
        dataset_hash=digest,
        db_path=db,
    )
    databank.set_campaign_status("tested", "done", db_path=db)
    monkeypatch.setattr(
        edge_map,
        "_base_viability",
        lambda *args, **kwargs: {
            "status": "ok",
            "feasible": True,
            "constraint": "compatible",
            "trades_is": 120,
            "fold_trades": [30, 30, 30, 30],
            "cost_r": 0.05,
            "reasons": [],
        },
    )
    report = edge_map.suggest(
        "CFD-001",
        discovery_db=db,
        costs_db=tmp_path / "lab.db",
        data_root=tmp_path,
        allow_dukascopy=False,
        bars_loader=lambda _symbol, _tf: frame,
    )
    assert report["label"] == "por probar"
    assert all(row["label"] == "por probar" for row in report["rows"])
    assert not any(
        row["template"] == "ny_open_vol_filter"
        and row["instrument"] == "US100"
        and row["timeframe"] == "M5"
        and row["source"] == "broker"
        for row in report["rows"]
    )
    assert any(row["timeframe"] == "M15" for row in report["rows"])


def test_edge_map_no_escribe_ni_cuenta_trials(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "discovery.db"
    _campaign(db, campaign_id="edge-1", mode="ga")
    before = db.read_bytes()
    learning = tmp_path / "lab.db"
    before_count = count_tests(learning, discovery_db=db)
    report = edge_map.build(
        db,
        data_root=tmp_path,
        costs_db=tmp_path / "lab.db",
        registry=Registry(firms={}, accounts={}),
        bars_loader=lambda _symbol, _tf: _frame(),
    )
    assert db.read_bytes() == before
    assert count_tests(learning, discovery_db=db) == before_count
    assert report["n_combos"] == 1


def test_edge_map_y_suggest_sin_read_holdout() -> None:
    source = Path(edge_map.__file__).read_text(encoding="utf-8")
    assert "read_holdout" not in source
    assert "disc_holdout_reads" not in source


def test_cli_edge_map_y_suggest(monkeypatch) -> None:
    from typer.testing import CliRunner

    from tradinglab.cli import app

    monkeypatch.setenv("COLUMNS", "240")

    report = {
        "combos": [
            {
                "template": "ny_open_vol_filter",
                "instrument": "US100",
                "timeframe": "M5",
                "source": "broker",
                "state": "sobreajustada",
                "raw_median_r": 0.01,
                "raw_best_r": 0.02,
                "net_median_r": 0.0,
                "cost_r": 0.02,
                "positive_folds_count": 2,
                "strategy_total": 4,
                "candidate_count": 0,
                "confirmed_count": 0,
                "dataset_source": "fuente viva",
            }
        ],
        "firms": [],
        "blocked": [{"timeframe": "H4", "reason": edge_map.DUKASCOPY_BLOCKED}],
        "summary": {"sobreajustada": 1},
        "n_combos": 1,
        "n_firms": 0,
    }
    monkeypatch.setattr(edge_map, "build", lambda *args, **kwargs: report)
    monkeypatch.setattr(
        edge_map,
        "export",
        lambda *args, **kwargs: {"json": "edge_map.json", "markdown": "edge_map.md"},
    )
    result = CliRunner().invoke(app, ["discovery", "edge-map", "--by", "hipotesis"])
    assert result.exit_code == 0
    assert "sobreajustada" in result.output
    assert "Dukascopy en descarga" in result.output
    assert "Exportado" in result.output

    suggest = {
        "rows": [
            {
                "template": "ny_open_vol_filter",
                "instrument": "US100",
                "timeframe": "M15",
                "source": "broker",
                "session": "09:35-11:30",
                "accounts": ["CFD-001"],
                "trades_is": 100,
                "fold_trades": [25, 25, 25, 25],
                "cost_r": 0.05,
                "label": "por probar",
            }
        ],
        "blocked": [],
        "n_rows": 1,
    }
    monkeypatch.setattr(edge_map, "suggest", lambda *args, **kwargs: suggest)
    result = CliRunner().invoke(app, ["discovery", "suggest", "--account", "CFD-001"])
    assert result.exit_code == 0
    assert "por probar" in result.output
    assert "no son candidatas" in result.output
