"""Aísla la suite de la `discovery.db` real.

``count_tests`` lee por defecto ``data/discovery.db``. Sin este fixture, una
campaña real aprobada (small = 440 pruebas) contamina cualquier test que use
un ``lab.db`` temporal y afirme valores absolutos del contador.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_discovery_db(tmp_path, monkeypatch):
    from tradinglab.discovery import databank

    monkeypatch.setattr(
        databank, "DEFAULT_DISCOVERY_DB", tmp_path / "discovery-ausente.db"
    )
