"""Cesta multi-símbolo: agregación de R, percentil y spec (Q3)."""

from __future__ import annotations

import pandas as pd

from tradinglab.discovery import basket


def test_combine_daily_suma_por_fecha() -> None:
    first = pd.Series(
        [1.0, -0.5],
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )
    second = pd.Series(
        [0.25, 0.5],
        index=pd.to_datetime(["2024-01-03", "2024-01-04"]),
    )
    combined = basket.combine_daily({"a": first, "b": second})
    assert combined.loc[pd.Timestamp("2024-01-02")] == 1.0
    assert combined.loc[pd.Timestamp("2024-01-03")] == -0.25
    assert combined.loc[pd.Timestamp("2024-01-04")] == 0.5


def test_percentil_cesta_pondera_por_operaciones() -> None:
    per_symbol = [
        {
            "random_means": [0.0, 1.0, 2.0, 3.0],
            "trades": 1,
            "strategy_expectancy_r": 2.5,
        },
        {
            "random_means": [0.0, 1.0, 2.0, 3.0],
            "trades": 3,
            "strategy_expectancy_r": 2.5,
        },
    ]
    result = basket.basket_percentile(per_symbol, percentile_min=90.0)
    assert result["simulations"] == 4
    assert result["trades"] == 4
    assert result["basket_expectancy_r"] == 2.5
    assert result["percentile"] == 75.0
    assert result["passed"] is False


def test_load_valida_cesta_de_dos_simbolos(tmp_path) -> None:
    path = tmp_path / "basket.yaml"
    path.write_text(
        "\n".join(
            [
                "basket: [XAUUSD, US100]",
                "campaign_id: test-basket",
                "instrument: XAUUSD",
                "timeframe: D1",
                "template: ts_momentum_d1",
                "mode: grid",
                "data_source: dukascopy",
                "segments:",
                '  is: ["2018-01-01", "2024-06-30"]',
                "basket_costs:",
                "  XAUUSD: {account: CFD-001, firm: ftmo, cost_accounts: [CFD-001], cost_mode: target}",
                "  US100: {account: CFD-001, firm: ftmo, cost_accounts: [CFD-001], cost_mode: target}",
                "grid:",
                "  dimensions:",
                "    - {name: fast_n, kind: path, path: long_entry.left.n, values: [50]}",
                "    - {name: slow_n, kind: path, path: long_entry.right.n, values: [200]}",
                "    - {name: stop_mult, kind: path, path: exit.stop.mult, values: [3.0]}",
            ]
        ),
        encoding="utf-8",
    )
    spec = basket.load(path)
    assert spec["symbols"] == ["XAUUSD", "US100"]
    assert len(spec["strategies"]) == 1
    assert spec["strategies"][0]["instrument"] == "XAUUSD"
    assert spec["cost"]["US100"]["account"] == "CFD-001"


def test_load_rechaza_un_solo_simbolo(tmp_path) -> None:
    import pytest

    path = tmp_path / "bad.yaml"
    path.write_text("basket: [XAUUSD]\n", encoding="utf-8")
    with pytest.raises(basket.BasketError, match=">= 2"):
        basket.load(path)


def test_feasibility_cesta_no_calcula_expectativa(tmp_path, monkeypatch) -> None:
    from tradinglab.discovery import metrics

    def _boom(*args, **kwargs):
        raise AssertionError("feasibility no debe calcular expectativa/PF")

    monkeypatch.setattr(metrics, "summarize", _boom)
    path = tmp_path / "basket.yaml"
    path.write_text(
        "\n".join(
            [
                "basket: [XAUUSD, US100]",
                "campaign_id: test-basket-feas",
                "instrument: XAUUSD",
                "timeframe: D1",
                "template: ts_momentum_d1",
                "mode: grid",
                "data_source: dukascopy",
                "segments:",
                '  is: ["2024-01-01", "2024-06-30"]',
                "basket_costs:",
                "  XAUUSD: {account: CFD-001, firm: ftmo, cost_accounts: [CFD-001], cost_mode: target}",
                "  US100: {account: CFD-001, firm: ftmo, cost_accounts: [CFD-001], cost_mode: target}",
                "grid:",
                "  dimensions:",
                "    - {name: fast_n, kind: path, path: long_entry.left.n, values: [50]}",
                "    - {name: slow_n, kind: path, path: long_entry.right.n, values: [200]}",
                "    - {name: stop_mult, kind: path, path: exit.stop.mult, values: [3.0]}",
            ]
        ),
        encoding="utf-8",
    )
    report = basket.check_spec(path)
    assert report["n_checked"] == 1
    row = report["rows"][0]
    assert "expectancy_r" not in row
    assert "profit_factor" not in row
    assert "trades_is" in row and "cost_r" in row
