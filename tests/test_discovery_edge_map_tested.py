from __future__ import annotations

import sqlite3
from pathlib import Path

from tradinglab.discovery import databank, edge_map


def test_tested_keys_marca_hipotesis_probada_sin_fuente(tmp_path: Path) -> None:
    db = tmp_path / "discovery.db"
    config = {
        "instrument": "USDJPY",
        "timeframe": "H1",
        "template": "asia_range_reversion",
        "mode": "grid",
        "seed": 11,
        "data_source": "dukascopy",
    }
    databank.add_campaign(
        "c1-test",
        config,
        instrument="USDJPY",
        timeframe="H1",
        template="asia_range_reversion",
        status="done",
        n_total=27,
        db_path=db,
    )
    databank.set_campaign_counts("c1-test", n_evaluated=27, db_path=db)
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        keys = edge_map._tested_keys(con)
    finally:
        con.close()
    assert ("asia_range_reversion", "USDJPY", "H1", "dukascopy") in keys
    assert ("asia_range_reversion", "USDJPY", "H1", "*") in keys
