"""FUT-H2: /api/futures/economics responde con los bloques real, nominal y simulado separados (loopback)."""

from __future__ import annotations

import json
import threading
import urllib.request
from pathlib import Path

import pytest

from tradinglab import web
from tradinglab.config import Settings


@pytest.mark.network
def test_api_futures_economics(tmp_path: Path) -> None:
    data = web.LabData(Settings(), root=tmp_path, db_path=tmp_path / "missing.db", external=False)
    server = web.DashboardServer(("127.0.0.1", 0), data)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(f"{base}/api/futures/economics", timeout=10) as response:
            payload = json.load(response)
        assert {"real", "nominal", "simulated", "registry", "ranking", "alerts"} <= set(payload)
        assert payload["simulated"]["label"].startswith("SIMULADO")
    finally:
        server.shutdown()
        server.server_close()
