"""T20 · Puerta de potencia: MDE y veredicto."""

from __future__ import annotations

import pytest

from tradinglab.discovery import engine, power


def test_mde_400_y_700():
    assert power.mde(400) == pytest.approx(0.1245, abs=1e-4)
    no_power = power.power_check(400, 0.10)
    assert no_power["mde_holdout"] == pytest.approx(0.1245, abs=1e-4)
    assert no_power["potencia_ok"] is False
    with_power = power.power_check(700, 0.10)
    assert with_power["mde_holdout"] == pytest.approx(0.09413, abs=1e-4)
    assert with_power["potencia_ok"] is True


def test_sin_delta_es_aviso_no_bloqueo():
    verdict = power.power_check(400, None)
    assert verdict["potencia_ok"] is None
    assert "sin δ" in verdict["potencia_status"]


def test_counts_from_is_respeta_duraciones():
    segments = {
        "is": ["2021-10-01", "2024-06-30"],
        "oos1": ["2024-07-01", "2025-06-30"],
        "oos2": ["2025-07-01", "2026-11-24"],
    }
    counts = power.counts_from_is(400, segments)
    assert counts["trades_is"] == 400
    assert counts["trades_holdout"] > 0


def test_power_payload_usa_counts():
    campaign = {
        "config": {
            "plausible_edge_r": 0.1,
            "sigma_r": 1.0,
            "segments": {
                "is": ["2021-10-01", "2024-06-30"],
                "oos1": ["2024-07-01", "2025-06-30"],
                "oos2": ["2025-07-01", "2026-11-24"],
            },
        }
    }
    payload = engine._power_payload(
        campaign, "x", counts={"trades_is": 800, "trades_holdout": 400}
    )
    assert payload["expected_trades_holdout"] == 400
    assert payload["potencia_ok"] is False
    assert payload["potencia_status"].startswith("sin potencia")
