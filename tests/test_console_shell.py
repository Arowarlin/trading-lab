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
        "asset",
        "bots",
        "incubation",
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


def test_vista_activo_incubadora_y_comparacion_lite_deep() -> None:
    text = INDEX.read_text(encoding="utf-8")
    for marker in (
        'id="view-asset"',
        'id="asset-select"',
        'id="asset-stats"',
        'id="asset-chart"',
        'id="asset-bots"',
        'id="asset-agents"',
        'id="asset-lifecycle"',
        "function renderAsset()",
        "function renderIncubation()",
        "function assetGroup(",
        "function sameAsset(",
        'id="view-incubation"',
        'id="incubation-stats"',
        'id="incubation-table"',
        'id="incubation-events"',
        'id="agent-compare"',
        "function renderAgentComparison()",
        "agent_comparisons",
        'id="decisions-sources"',
        "d.by_source",
        "Incubadora",
        "Comparación lite vs deep",
        "No activa bots, no envía órdenes",
    ):
        assert marker in text, marker


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


def test_componentes_v3_presentes() -> None:
    text = INDEX.read_text(encoding="utf-8")
    for marker in (
        'id="risk-gauges"',
        'id="risk-gauges-meta"',
        'id="density-toggle"',
        'id="density-label"',
        'id="refresh-pulse"',
        "renderRiskGauges",
        "renderKpis",
        "kpi-row",
        "gauge-svg",
        "gauge-limit",
        "skeleton",
        "num-changed",
        "DENSITY_KEY",
        'try { localStorage.setItem(DENSITY_KEY',
        "tl.table.density",
        "prefers-reduced-motion",
    ):
        assert marker in text, marker
    for marker in (
        "body.density-compact",
        ".gauge-fill",
        ".skeleton",
        ".delta.pos",
        ".delta.neg",
        ".tag.green::before",
    ):
        assert marker in text, marker


def test_research_muestra_coste_de_equilibrio() -> None:
    text = INDEX.read_text(encoding="utf-8")
    for marker in (
        "Coste de equilibrio",
        "0.5 bps",
        "cost_curve_bps",
        "breakeven_cost_bps",
        "calibrated_cost_bps",
        "SIN VERIFICAR",
        "slippage opt",
    ):
        assert marker in text, marker


def test_formato_gauges_performers_y_regimen() -> None:
    text = INDEX.read_text(encoding="utf-8")
    for marker in (
        "const arc = item.arc === undefined",
        'stroke-dasharray="${(arc * 100).toFixed(1)} 100"',
        "arc: health / 100",
        "value: num(health, 0)",
        "PARCIAL · cobertura",
        "Evaluaciones de backtest (no reales)",
        'id="performers-note"',
        "Trades*",
        "rebalanceos diarios",
        'id="regime-panel"',
        "panel-compact",
        'useGrouping: "always"',
        "function clampZero(",
        "function toneFor(",
        ".gauge-value { fill: var(--text); font-family: var(--mono); font-size: 16px;",
    ):
        assert marker in text, marker
    assert "100 / 100" not in text


def test_graficas_svg_y_mapas_de_calor_presentes() -> None:
    text = INDEX.read_text(encoding="utf-8")
    assert re.search(r'<svg[^>]*id="equity-canvas"', text)
    assert "<canvas" not in text
    for marker in (
        'id="corr-heatmap"',
        'id="corr-meta"',
        'id="equity-regime-note"',
        "renderCorrelationHeatmap",
        "renderPnlCalendar",
        "equity-band",
        "equity-trade",
        "equity-cross",
        "equity-fill",
        "rgba(76,201,240",
        "rgba(246,196,83",
        "Sin datos de régimen histórico",
        "heat-scale",
        "left.x - right.x",
        "equity-regime-note",
    ):
        assert marker in text, marker
    assert "ctx.createLinearGradient" not in text
    assert "getContext(\"2d\")" not in text


def test_accesibilidad_y_refresco_estable() -> None:
    text = INDEX.read_text(encoding="utf-8")
    for marker in (
        'class="skip-link"',
        'id="main-content"',
        "aria-current",
        "ArrowDown",
        "ArrowUp",
        ":focus-visible",
        "fingerprint(",
        "overviewChanged",
        "S.fp",
        'id="office-floor"',
        "function renderSala()",
        'event.key.toLowerCase() === "k"',
        "prefers-reduced-motion",
    ):
        assert marker in text, marker
    assert "@media (max-width: 1180px)" in text
    assert "@media (max-width: 760px)" in text


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
