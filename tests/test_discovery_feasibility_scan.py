"""feasibility-scan: TF × factibilidad sin PnL, OOS ni DSR."""

from __future__ import annotations

from typer.testing import CliRunner

from tradinglab.discovery import campaigns, databank, engine, feasibility


def _frame():
    return engine.synthetic_frame(years=0.4, seed=20261123)


def _frames(timeframes: list[str]):
    frame = _frame()
    return {tf: frame for tf in timeframes}


def test_scan_no_escribe_dsr_ni_calcula_pnl(monkeypatch) -> None:
    def _forbidden(*_args, **_kwargs):
        raise AssertionError("feasibility-scan no puede registrar campañas")

    monkeypatch.setattr(campaigns, "register", _forbidden)
    monkeypatch.setattr(databank, "add_campaign", _forbidden)
    report = feasibility.scan(
        "ny_open_vol_filter",
        "US100",
        source="dukascopy",
        frames=_frames(["M1", "M5", "M15"]),
    )
    assert [row["timeframe"] for row in report["timeframes"]] == ["M1", "M5", "M15"]
    for row in report["timeframes"]:
        assert "expectancy" not in row
        assert "pnl" not in row
        assert "rows" in row
    assert report["source"] == "dukascopy"


def test_scan_h4_d1_bloqueadas_con_broker() -> None:
    report = feasibility.scan(
        "asia_range_reversion",
        "US100",
        source="broker",
        frames=_frames(["H4", "D1"]),
    )
    rows = {row["timeframe"]: row for row in report["timeframes"]}
    assert rows["H4"]["status"] == "blocked"
    assert rows["D1"]["status"] == "blocked"
    assert "Dukascopy" in rows["H4"]["reasons"][0]
    assert not rows["H4"]["passes"]
    assert not rows["D1"]["passes"]


def test_scan_cli_muestra_tabla(monkeypatch) -> None:
    from tradinglab.cli import app

    monkeypatch.setenv("COLUMNS", "240")
    monkeypatch.setattr(
        feasibility,
        "scan",
        lambda *args, **kwargs: {
            "template": "ny_open_vol_filter",
            "symbol": "US100",
            "source": "dukascopy",
            "account": "CFD-001",
            "passes": True,
            "n_feasible_timeframes": 2,
            "timeframes": [
                {
                    "timeframe": "M5",
                    "status": "ok",
                    "n_strategies": 1,
                    "n_feasible": 1,
                    "feasible_pct": 100.0,
                    "trades_is": 120.0,
                    "fold_trades": [30.0, 30.0, 30.0, 30.0],
                    "cost_r": 0.05,
                    "mean_bars": 6.0,
                    "mean_minutes": 30.0,
                    "passes": True,
                    "reasons": [],
                    "rows": [],
                },
                {
                    "timeframe": "M15",
                    "status": "ok",
                    "n_strategies": 1,
                    "n_feasible": 0,
                    "feasible_pct": 0.0,
                    "trades_is": 12.0,
                    "fold_trades": [3.0, 3.0, 3.0, 3.0],
                    "cost_r": 0.12,
                    "mean_bars": 4.0,
                    "mean_minutes": 60.0,
                    "passes": False,
                    "reasons": ["coste_R 0,12 > 0,10"],
                    "rows": [],
                },
            ],
        },
    )
    result = CliRunner().invoke(
        app,
        [
            "discovery",
            "feasibility-scan",
            "ny_open_vol_filter",
            "US100",
            "--source",
            "dukascopy",
        ],
    )
    assert result.exit_code == 0
    assert "M5" in result.output
    assert "M15" in result.output
    assert "Cost_R" in result.output
    assert "Sin datos" not in result.output.split("M15")[0]
