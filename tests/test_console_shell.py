from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "src" / "tradinglab" / "webui" / "index.html"
INVENTORY = ROOT / "docs" / "ui_inventory.json"


def _inventory() -> dict:
    return json.loads(INVENTORY.read_text(encoding="utf-8"))


def _tabs(text: str) -> list[tuple[str, str]]:
    items = []
    for match in re.finditer(
        r'<button class="nav-btn[^"]*" data-view="([^"]+)"[^>]*>(.*?)</button>',
        text,
        re.S,
    ):
        label = re.sub(r"<[^>]+>", "", match.group(2))
        items.append((match.group(1), re.sub(r"\s+", " ", label).strip()))
    return items


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
        'id="model-registry"',
        "renderModels",
        'id="reports-list"',
        'id="report-preview"',
        'id="market-catalog"',
        "renderMarketCatalog",
        'id="market-agents"',
        "renderMarketAgents",
        'id="market-pilots"',
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
        "@import",
        "fonts.googleapis",
        "url(http",
    ):
        assert forbidden not in lowered


def test_inventario_ui_base_sigue_completo() -> None:
    text = INDEX.read_text(encoding="utf-8")
    inventory = _inventory()

    views = set(re.findall(r'data-view="([^"]+)"', text))
    assert views == set(inventory["views"])
    for view in inventory["views"]:
        assert f'id="view-{view}"' in text
        assert f'data-view="{view}"' in text

    for section in inventory["nav_sections"]:
        assert f'<div class="nav-label">{section}</div>' in text
    assert _tabs(text) == [(item["view"], item["label"]) for item in inventory["tabs"]]

    for element_id in inventory["ids"]:
        assert f'id="{element_id}"' in text, element_id

    api_calls = set(re.findall(r"/api/[A-Za-z0-9_./?&=${}:-]*", text))
    assert api_calls == set(inventory["api_calls"])


def test_hud_barra_operativa_presente() -> None:
    text = INDEX.read_text(encoding="utf-8")
    for marker in (
        'id="hud"',
        'id="hud-killswitch"',
        'id="hud-killswitch-led"',
        'id="hud-f13"',
        'id="hud-data"',
        'id="hud-operator"',
        'id="mode-badge"',
        'id="session-badge"',
        'id="clock"',
        "operator-armed",
        "updateHud()",
        "updateHudOperator()",
    ):
        assert marker in text, marker
    for marker in ("--accent: #4cc9f0", "--positive", "--negative", "font-variant-numeric: tabular-nums"):
        assert marker in text, marker
