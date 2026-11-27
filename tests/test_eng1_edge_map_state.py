"""ENG-1 E-03: bruto y neto positivos sin candidatas no es "sin edge bruto"."""

from __future__ import annotations

from tradinglab.discovery import edge_map


def _state(raw, net):
    campaign = {"status": "done", "n_evaluated": 10}
    raw_rows = [{"strategy_id": 1, "raw_expectancy_r": raw}]
    net_rows = [{"strategy_id": 1, "net_expectancy_r": net}]
    state, _ = edge_map._state_from_campaign(
        campaign, selected=[], raw_rows=raw_rows, net_rows=net_rows, validations={}, verified=True
    )
    return state


def test_bruto_y_neto_positivos_sin_candidatas():
    assert _state(0.2, 0.1) == "edge neto sin robustez"
    assert "edge neto sin robustez" in edge_map.STATES


def test_el_resto_de_etiquetas_no_cambia():
    assert _state(-0.1, -0.2) == "sin edge bruto"
    assert _state(0.1, -0.05) == "edge bruto que el coste elimina"
