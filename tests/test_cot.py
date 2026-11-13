from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from tradinglab.data.cot import (
    fetch_cot,
    latest_as_of,
    publication_date,
)


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _Client:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None):
        self.calls.append((url, params))
        contract = (params or {}).get("$where", "")
        if "NASDAQ" in contract:
            return _Response([{
                "market_and_exchange_names": "NASDAQ MINI - CME",
                "report_date_as_yyyy_mm_dd": "2026-11-03T00:00:00.000",
                "open_interest_all": "1000",
                "asset_mgr_positions_long": "100",
                "asset_mgr_positions_short": "50",
                "lev_money_positions_long": "200",
                "lev_money_positions_short": "150",
            }])
        return _Response([{
            "market_and_exchange_names": "GOLD - COMEX",
            "report_date_as_yyyy_mm_dd": "2026-11-03T00:00:00.000",
            "open_interest_all": "2000",
            "noncomm_positions_long_all": "300",
            "noncomm_positions_short_all": "100",
            "comm_positions_long_all": "400",
            "comm_positions_short_all": "500",
        }])


def test_cot_usa_fecha_de_publicacion_y_es_causal():
    client = _Client()
    frame = fetch_cot(contracts=("nasdaq", "gold"), limit=1, client=client)
    assert len(frame) == 2
    assert len(client.calls) == 2
    nasdaq = frame[frame["contract"] == "nasdaq"].iloc[0]
    assert nasdaq["report_date"] == "2026-11-03"
    assert str(nasdaq["published_at"]).startswith("2026-11-06T20:30:00+00:00")
    before = datetime(2026, 11, 6, 20, 0, tzinfo=timezone.utc)
    after = datetime(2026, 11, 6, 21, 0, tzinfo=timezone.utc)
    assert latest_as_of(frame, before).empty
    assert len(latest_as_of(frame, after)) == 2


def test_publication_date_es_viernes():
    stamp = publication_date("2026-11-03")
    assert stamp.weekday() == 4
    assert stamp.hour == 20  # 15:30 ET en UTC (EST)
    assert pd.Timestamp(stamp) > pd.Timestamp("2026-11-03", tz="UTC")
