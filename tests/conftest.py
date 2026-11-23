"""Aísla la suite de la `discovery.db` real.

``count_tests`` lee por defecto ``data/discovery.db``. Sin este fixture, una
campaña real aprobada (small = 440 pruebas) contamina cualquier test que use
un ``lab.db`` temporal y afirme valores absolutos del contador.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_discovery_db(tmp_path, monkeypatch):
    from tradinglab import learning
    from tradinglab.discovery import databank

    empty = tmp_path / "discovery-empty.db"
    databank.init_databank(empty)
    monkeypatch.setattr(databank, "DEFAULT_DISCOVERY_DB", empty)
    monkeypatch.setattr(learning, "CANONICAL_DISCOVERY_DB", empty)


@pytest.fixture(autouse=True)
def _allow_unapproved_performance(monkeypatch):
    """Los tests calculan rendimiento con datos sintéticos por diseño."""

    from tradinglab.discovery import guard

    monkeypatch.setenv("TRADINGLAB_ALLOW_UNAPPROVED", "1")
    monkeypatch.setattr(guard, "ALLOW_UNAPPROVED", True)
