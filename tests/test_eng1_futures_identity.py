"""C-04 (ENG-1): futuros CME (Databento) y CFD nunca comparten modelo de coste.

Hasta ahora ``register`` aceptaba ``data_source="databento"`` en M5-H1 con
cuentas CFD: el coste CFD (spread BID/ASK, swap) se aplicaba a precios de
operación del futuro NQ guardados como "US100". Ver
docs/engineering/AUDIT_FINDINGS.md (C-04) y docs/tradinglab2/06 §4.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tradinglab.discovery import campaigns

SEGMENTS = {
    "is": ["2024-01-08", "2024-01-20"],
    "oos1": ["2024-01-21", "2024-02-05"],
    "oos2": ["2024-02-06", None],
}


def _frame(bars: int = 20_000, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2024-01-08 00:00", periods=bars, freq="5min", tz="UTC")
    close = 20_000.0 + np.cumsum(rng.normal(0.0, 4.0, bars))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + rng.uniform(1.0, 5.0, bars)
    low = np.minimum(open_, close) - rng.uniform(1.0, 5.0, bars)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close}, index=index)


def test_databento_con_cuenta_cfd_se_rechaza(tmp_path: Path) -> None:
    with pytest.raises(campaigns.CampaignError, match="futuros"):
        campaigns.register(
            "US100",
            "M5",
            "ny_open_vol_filter",
            "small",
            segments=SEGMENTS,
            frame=_frame(),
            data_source="databento",
            cost_accounts=["CFD-001"],
            db_path=tmp_path / "discovery.db",
            dry_run=True,
        )


def test_dukascopy_con_cuenta_cfd_sigue_valido(tmp_path: Path) -> None:
    campaign = campaigns.register(
        "US100",
        "M5",
        "ny_open_vol_filter",
        "small",
        segments=SEGMENTS,
        frame=_frame(),
        data_source="dukascopy",
        cost_accounts=["CFD-001"],
        db_path=tmp_path / "discovery.db",
        dry_run=True,
    )
    assert campaign["config"]["data_source"] == "dukascopy"
