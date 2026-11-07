from __future__ import annotations

import json
from pathlib import Path

from tradinglab.portfolio import build_clusters, load_clusters, render_markdown, write
from tradinglab.prop.guard import AccountSnapshot, evaluate_account
from tradinglab.prop.rules import ftmo


def test_build_clusters_une_correlacion_alta():
    payload = {
        "correlations": {
            "labels": ["#1 SPY trend x1", "#2 SPY trend x0.5", "#3 QQQ meanrev x1"],
            "matrix": [[1.0, 0.92, 0.1], [0.92, 1.0, 0.2], [0.1, 0.2, 1.0]],
        }
    }
    clusters = build_clusters(payload)
    assert len(clusters) == 2
    assert clusters[0]["size"] == 2
    assert any("#3 QQQ" in member for member in clusters[1]["members"])


def test_load_y_escribir_clusters(tmp_path):
    payload = {
        "generated_at": "2026-11-07T00:00:00+00:00",
        "correlations": {
            "labels": ["#1 A trend x1", "#2 B trend x1"],
            "matrix": [[1.0, 0.8], [0.8, 1.0]],
        },
    }
    (tmp_path / "horizons.json").write_text(json.dumps(payload), encoding="utf-8")
    report = load_clusters(tmp_path)
    assert report["clusters"][0]["size"] == 2
    files = write(report, tmp_path)
    assert Path(files["json"]).exists()
    assert "Clúster" in render_markdown(report)


def test_guard_limita_riesgo_de_cluster_y_permite_cerrar():
    rules = ftmo(100_000, max_open_risk_pct=0.05)
    state = AccountSnapshot(
        equity=100_000,
        day_start_equity=100_000,
        initial_balance=100_000,
        peak_equity=100_000,
    )
    blocked = evaluate_account(
        rules,
        state,
        proposed_risk_usd=600,
        cluster_open_risk_usd=500,
        max_cluster_risk_pct=0.01,
    )
    assert blocked.allowed is False
    assert "clúster" in blocked.reason
    assert evaluate_account(
        rules,
        state,
        proposed_risk_usd=600,
        cluster_open_risk_usd=500,
        max_cluster_risk_pct=0.01,
        closing=True,
    ).allowed
