from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "src" / "tradinglab" / "webui" / "index.html"


def test_barra_lateral_con_secciones_y_todas_las_vistas() -> None:
    text = INDEX.read_text(encoding="utf-8")
    sections = ["Principal", "Laboratorio", "Portafolios", "Riesgo y fondeo", "Inteligencia", "Sistema"]
    positions = [text.index(f'<div class="nav-label">{name}</div>') for name in sections]
    assert positions == sorted(positions)

    views = set(re.findall(r'data-view="([^"]+)"', text))
    assert views == {
        "overview",
        "market",
        "bots",
        "research",
        "agents",
        "accounts",
        "fund",
        "journal",
        "risk",
        "operator",
        "sala",
        "decisions",
        "learning",
        "repos",
        "logs",
    }


def test_dashboard_tiene_kpis_balance_performers_y_calendario() -> None:
    text = INDEX.read_text(encoding="utf-8")
    for marker in (
        'id="kpis"',
        'id="dashboard-balance"',
        'id="dashboard-performers"',
        'id="pnl-calendar"',
        'id="pnl-prev"',
        'id="pnl-next"',
        'id="journal-multiverse"',
        'id="run-detail-multiverse"',
        "multiverseCard",
        'id="bots-drift"',
        'id="drift-meta"',
        'id="fund-health"',
        'id="fund-health-meta"',
        'id="fund-flows"',
        'id="fund-twr"',
        "resumeFundPause",
        'id="view-learning"',
        'id="learning-list"',
        'id="reports-list"',
        'id="report-preview"',
        'id="sidebar-toggle"',
        "sidebar-collapsed",
        "computeDailyPnl",
    ):
        assert marker in text


def test_consola_local_sin_cdns_ni_frameworks() -> None:
    text = INDEX.read_text(encoding="utf-8")
    assert not re.search(r"https?://", text)
    lowered = text.lower()
    for forbidden in (
        "cdn.",
        "unpkg",
        "jsdelivr",
        "bootstrap.min",
        "bootstrap@",
        "react.production",
        "react@",
        "vue.min",
        "vue@",
    ):
        assert forbidden not in lowered
