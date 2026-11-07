from __future__ import annotations

import pandas as pd
import pytest

from tradinglab.data.futures import ProjectXFuturesProvider, daily_proxy


def test_projectx_no_descarga_sin_suscripcion(tmp_path):
    provider = ProjectXFuturesProvider()
    with pytest.raises(NotImplementedError, match="suscripción"):
        provider.fetch_bars("ES=F", "M15", "2026-01-01", "2026-02-01", tmp_path)


def test_proxy_diario_usa_fetch_existente(monkeypatch, tmp_path):
    idx = pd.bdate_range("2026-01-01", periods=5)
    frame = pd.DataFrame(
        {"open": [1] * 5, "high": [1] * 5, "low": [1] * 5, "close": [1] * 5, "volume": [1] * 5},
        index=idx,
    )
    monkeypatch.setattr("tradinglab.data.futures.fetch", lambda *a, **k: frame)
    out = daily_proxy("ES=F", "2026-01-01", "2026-02-01", tmp_path)
    assert len(out) == 5
