from __future__ import annotations

from pathlib import Path

import pytest

from tradinglab.library import (
    LibraryError,
    get_entry,
    list_library,
    load_library,
    render_markdown,
)


def test_biblioteca_carga_y_estructura() -> None:
    payload = load_library()
    assert payload["reviewed_at"]
    entries = payload["entries"]
    assert len(entries) == 18
    ids = [entry["id"] for entry in entries]
    assert len(ids) == len(set(ids))
    assert {
        "dsr",
        "pbo",
        "walk-forward",
        "monte-carlo",
        "fred",
        "sec-edgar",
        "yfinance",
        "lm-studio",
        "optuna",
        "quantstats",
        "qlib",
        "hmmlearn",
        "vectorbt",
        "backtrader",
        "lean",
        "researchgate",
        "google-scholar",
        "ssrn",
    } == set(ids)
    for entry in entries:
        assert entry["status"] in {"adoptada", "evaluada", "descartada"}
        for field in ("name", "category", "problem", "license", "version", "reason"):
            assert entry[field], (entry["id"], field)


def test_fuentes_cientificas_sin_scraping_ni_paywalls() -> None:
    for entry_id in ("researchgate", "google-scholar", "ssrn"):
        entry = get_entry(entry_id)
        assert entry["status"] == "adoptada"
        policy = f"{entry['risks']} {entry['reason']}".lower()
        assert "scraping" in policy or "scrapea" in policy
        assert entry["official_url"].startswith("https://")
        assert "consulta manual" in entry["dependencies"].lower()


def test_biblioteca_show_y_filtro() -> None:
    entry = get_entry("dsr")
    assert entry["name"].startswith("Deflated Sharpe")
    assert entry["status"] == "adoptada"
    with pytest.raises(LibraryError):
        get_entry("no-existe")
    adopted = list_library(status="adoptada")
    assert adopted and all(item["status"] == "adoptada" for item in adopted)
    discarded = list_library(status="descartada")
    assert {item["id"] for item in discarded} >= {"qlib", "hmmlearn", "backtrader", "lean"}


def test_biblioteca_markdown(tmp_path: Path) -> None:
    text = render_markdown()
    assert "# Biblioteca de conocimiento" in text
    assert "Deflated Sharpe Ratio" in text
    assert "Optuna" in text
    assert "descartada" in text
    assert "No se copia texto de terceros" in text
