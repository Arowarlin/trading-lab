"""R3 · Etiqueta de WF no informativo por baja frecuencia de operaciones."""

from __future__ import annotations

import pandas as pd

from tradinglab.discovery import robustness


def _frame(rows: int = 100) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=rows, freq="D")
    return pd.DataFrame({"a": range(rows)}, index=index)


def _folds() -> list[dict]:
    return [
        {"selected": 0, "test_start": 60, "test_end": 80},
        {"selected": 0, "test_start": 80, "test_end": 100},
    ]


def test_wf_baja_frecuencia_se_etiqueta_sin_cambiar_el_veredicto() -> None:
    frame = _frame()
    times = {7: [pd.Timestamp("2024-01-01", tz="UTC")]}  # fuera de las ventanas
    result = robustness._wf_trade_frequency(frame, _folds(), times, [7])
    assert result["test_trades_per_fold"] == [0, 0]
    assert result["test_trades_median"] == 0.0
    assert result["wf_informative"] is False
    assert result["wf_label"] == "WF no informativo (baja frecuencia)"


def test_wf_con_dos_operaciones_por_ventana_es_informativo() -> None:
    frame = _frame()
    times = {
        7: [
            pd.Timestamp("2024-03-02", tz="UTC"),
            pd.Timestamp("2024-03-10", tz="UTC"),
            pd.Timestamp("2024-03-22", tz="UTC"),
            pd.Timestamp("2024-04-05", tz="UTC"),
        ]
    }
    result = robustness._wf_trade_frequency(frame, _folds(), times, [7])
    assert result["test_trades_per_fold"] == [2, 2]
    assert result["test_trades_median"] == 2.0
    assert result["wf_informative"] is True
    assert result["wf_label"] is None


def test_matriz_del_frontier_es_diaria_y_ordenada(monkeypatch) -> None:
    """El PBO/WF exigen una serie regular; no una unión desordenada de días."""

    def fake_frontier(campaign_id, *, db_path=None, con=None):
        return [
            {
                "strategy_id": 1,
                "dates": ["2024-01-05", "2024-01-10"],
                "returns": [1.0, 3.0],
            },
            {
                "strategy_id": 2,
                "dates": ["2024-01-03", "2024-01-10"],
                "returns": [2.0, 4.0],
            },
        ]

    monkeypatch.setattr(robustness.databank, "frontier", fake_frontier)
    frame, ids = robustness._frontier_frame("x", None)
    assert ids == [1, 2]
    assert frame.index.is_monotonic_increasing
    assert list(frame.index) == list(pd.bdate_range("2024-01-03", "2024-01-10"))
    assert frame.loc["2024-01-03", 1] == 0.0
    assert frame.loc["2024-01-05", 1] == 1.0
    assert frame.loc["2024-01-10", 2] == 4.0
    assert (frame.columns == [1, 2]).all()

