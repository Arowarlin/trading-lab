"""Catálogo de firmas de futuros por automatización (`config/prop_economics/firms_futures.yaml`).

Cada clasificación debe llevar su evidencia: una firma marcada como que permite bots (o con
condiciones, o prohibida) necesita fuente oficial con URL, fecha y cita; las no verificadas no
pueden presentarse como si permitieran bots.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml

CATALOG = Path(__file__).resolve().parents[1] / "config" / "prop_economics" / "firms_futures.yaml"
CATEGORIES = {"allowed", "conditional", "prohibited", "unverified"}
EXPECTED = {
    "topstep", "myfundedfutures", "lucid", "tradeday", "tradeify",
    "apex", "takeprofittrader", "earn2trade", "bulenox", "alphafutures",
}


def _firms():
    return yaml.safe_load(CATALOG.read_text(encoding="utf-8"))["firms"]


def test_the_ten_firms_are_listed_once():
    ids = [firm["id"] for firm in _firms()]
    assert len(ids) == len(set(ids)) == 10
    assert set(ids) == EXPECTED


def test_every_category_is_known():
    for firm in _firms():
        assert firm["automation"]["category"] in CATEGORIES, firm["id"]


def test_classified_firms_have_official_evidence():
    for firm in _firms():
        auto = firm["automation"]
        if auto["category"] == "unverified":
            assert auto["status"] in {"unverified", "sin_datos"}, firm["id"]
            assert "source" not in auto, f"{firm['id']}: una firma sin verificar no cita fuente vigente"
            continue
        assert auto["status"] == "verified", firm["id"]
        source = auto["source"]
        assert source["url"].startswith("https://"), firm["id"]
        assert isinstance(source["consulted_at"], date), firm["id"]
        assert auto["quote"].strip(), firm["id"]
        assert auto["conditions"], firm["id"]


def test_expected_classification_on_2026_11_27():
    by_id = {firm["id"]: firm["automation"]["category"] for firm in _firms()}
    assert by_id["lucid"] == "allowed"
    assert by_id["alphafutures"] == "prohibited"
    assert by_id["takeprofittrader"] == "prohibited"
    for firm in ("topstep", "myfundedfutures", "tradeday", "tradeify", "bulenox"):
        assert by_id[firm] == "conditional", firm
    for firm in ("apex", "earn2trade"):
        assert by_id[firm] == "unverified", firm
