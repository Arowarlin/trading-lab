from __future__ import annotations

import lzma
import struct
from datetime import date

import httpx
import pandas as pd
import pytest

from tradinglab.data.ticks import (
    TickError,
    decode_bi5,
    fetch_day,
    fetch_hour,
    hour_url,
    hourly_spread_bps,
    parse_hours,
    point_size,
    save_ticks,
    summarize_ticks,
)


def _payload(records: list[tuple[int, int, int, float, float]]) -> bytes:
    raw = b"".join(struct.pack(">IIIff", *row) for row in records)
    return lzma.compress(raw, format=lzma.FORMAT_ALONE)


def test_url_dukascopy_mes_cero_based():
    url = hour_url("eurusd", date(2026, 11, 6), 14)
    assert url.endswith("/EURUSD/2026/10/06/14h_ticks.bi5")
    assert "datafeed.dukascopy.com" in url


def test_decode_bi5_escala_y_timestamp():
    day = date(2026, 11, 6)
    payload = _payload(
        [
            (0, 110_010, 110_000, 1.5, 2.0),
            (1500, 110_020, 110_010, 1.0, 1.0),
        ]
    )
    frame = decode_bi5(payload, symbol="EURUSD", day=day, hour=14)
    assert list(frame.columns[:5]) == [
        "ts",
        "bid",
        "ask",
        "bid_volume",
        "ask_volume",
    ]
    assert len(frame) == 2
    assert str(frame["ts"].iloc[0]) == "2026-11-06 14:00:00+00:00"
    assert frame["bid"].iloc[0] == pytest.approx(1.10000)
    assert frame["ask"].iloc[0] == pytest.approx(1.10010)
    assert frame["spread"].iloc[0] == pytest.approx(0.0001)
    assert frame["spread_bps"].iloc[0] == pytest.approx(0.909, rel=1e-3)
    assert frame["ask_volume"].iloc[0] == pytest.approx(1.5)


def test_decode_vacio_o_corrupto():
    empty = decode_bi5(b"", symbol="EURUSD", day=date(2026, 11, 6), hour=0)
    assert empty.empty
    with pytest.raises(TickError, match="LZMA"):
        decode_bi5(b"no-es-lzma", symbol="EURUSD", day=date(2026, 11, 6), hour=0)
    with pytest.raises(TickError, match="múltiplo"):
        decode_bi5(
            lzma.compress(b"123", format=lzma.FORMAT_ALONE),
            symbol="EURUSD",
            day=date(2026, 11, 6),
            hour=0,
        )


def test_point_por_simbolo_y_override():
    assert point_size("EURUSD") == pytest.approx(0.00001)
    assert point_size("USDJPY") == pytest.approx(0.001)
    assert point_size("BTCUSD", point=0.1) == pytest.approx(0.1)
    with pytest.raises(TickError, match="sin point"):
        point_size("BTCUSD")


def test_parse_hours():
    assert parse_hours("0-2,5") == [0, 1, 2, 5]
    assert parse_hours("23") == [23]
    with pytest.raises(TickError, match="invertido"):
        parse_hours("5-3")
    with pytest.raises(TickError, match="entre 0 y 23"):
        parse_hours("24")


def test_fetch_hour_404_es_sin_datos():
    class Response:
        status_code = 404
        content = b""

    class Client:
        def get(self, url):
            return Response()

    frame = fetch_hour(
        "EURUSD", date(2026, 11, 7), 3, client=Client(), retries=0
    )
    assert frame.empty


def test_hourly_spread_bps(tmp_path):
    frame = pd.DataFrame(
        {
            "ts": pd.to_datetime(
                [
                    "2025-01-10T14:00:00Z",
                    "2025-01-10T14:30:00Z",
                    "2025-01-10T15:00:00Z",
                ]
            ),
            "spread_bps": [0.2, 0.4, 0.6],
        }
    )
    path = tmp_path / "ticks.parquet"
    frame.to_parquet(path, index=False)
    hourly = hourly_spread_bps(path)
    assert hourly.loc[14] == pytest.approx(0.3)
    assert hourly.loc[15] == pytest.approx(0.6)
    with pytest.raises(TickError, match="spread_bps"):
        hourly_spread_bps(frame.drop(columns=["spread_bps"]))


def test_fetch_day_combina_horas_y_guarda(tmp_path):
    payload = _payload([(0, 110_010, 110_000, 1.0, 1.0)])

    class Response:
        def __init__(self, status=200, content=b""):
            self.status_code = status
            self.content = content

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError(
                    "fallo",
                    request=httpx.Request("GET", "https://dukascopy"),
                    response=httpx.Response(self.status_code),
                )

    class Client:
        def get(self, url):
            return Response(200, payload) if "/00h_" in url else Response(404)

    day = date(2026, 11, 6)
    frame = fetch_day(
        "EURUSD", day, hours=[0, 1], client=Client(), retries=0
    )
    assert len(frame) == 1
    path = save_ticks(frame, "EURUSD", day, out_dir=tmp_path)
    assert path.exists() and path.suffix == ".parquet"
    summary = summarize_ticks(frame)
    assert summary["ticks"] == 1
    assert summary["median_spread"] == pytest.approx(0.0001)
