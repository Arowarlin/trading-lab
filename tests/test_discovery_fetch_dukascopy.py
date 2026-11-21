"""Dukascopy M1: decodificación, caché única, reanudación y ASK."""

from __future__ import annotations

import lzma
import struct
from datetime import date

import pandas as pd
import pytest

from tradinglab.discovery import fetch_dukascopy as duka


def _payload(records: list[tuple[int, int, int, int, int, float]]) -> bytes:
    raw = b"".join(struct.pack(">IIIIIf", *row) for row in records)
    return lzma.compress(raw, format=lzma.FORMAT_ALONE)


def _day_frame(day: date, side: str = "BID", rows: int = 3) -> pd.DataFrame:
    index = pd.date_range(
        pd.Timestamp(day, tz="UTC"), periods=rows, freq="1min"
    )
    values = pd.Series(range(rows), dtype=float) + 100.0
    frame = pd.DataFrame(
        {
            "open": values.values,
            "high": values.values + 1.0,
            "low": values.values - 1.0,
            "close": values.values + 0.5,
            "volume": 1.0,
        },
        index=index,
    )
    if str(side).upper() == "ASK":
        frame.columns = list(duka.ASK_COLUMNS)
    return frame


def test_url_mes_cero_based() -> None:
    url = duka.candle_url("EURUSD", date(2024, 1, 2), "BID")
    assert url.endswith("/EURUSD/2024/00/02/BID_candles_min_1.bi5")
    assert "datafeed.dukascopy.com" in url


def test_decode_escala_y_descarta_volumen_cero() -> None:
    payload = _payload(
        [
            (0, 110_010, 110_020, 110_000, 110_030, 1.5),
            (60, 110_020, 110_020, 110_020, 110_020, 0.0),
            (120, 110_030, 110_040, 110_020, 110_050, 2.0),
        ]
    )
    frame = duka.decode_candles(
        payload, day=date(2024, 1, 2), point=1e-5, side="BID"
    )
    assert len(frame) == 2
    assert frame.index[0] == pd.Timestamp("2024-01-02 00:00", tz="UTC")
    assert frame.index[1] == pd.Timestamp("2024-01-02 00:02", tz="UTC")
    assert frame["open"].iloc[0] == pytest.approx(1.10010)
    assert frame["close"].iloc[0] == pytest.approx(1.10020)
    assert frame["low"].iloc[0] == pytest.approx(1.10000)
    assert frame["high"].iloc[0] == pytest.approx(1.10030)


def test_decode_payload_invalido() -> None:
    with pytest.raises(duka.DukascopyError, match="LZMA"):
        duka.decode_candles(b"no-es-lzma", day=date(2024, 1, 2), point=1e-5)
    with pytest.raises(duka.DukascopyError, match="múltiplo"):
        duka.decode_candles(
            lzma.compress(b"123", format=lzma.FORMAT_ALONE),
            day=date(2024, 1, 2),
            point=1e-5,
        )


def test_download_escribe_solo_m1_y_reanuda(tmp_path, monkeypatch) -> None:
    calls: list[tuple[date, str]] = []

    def fake_fetch(client, instrument, day, side, point, **kwargs):
        calls.append((day, side))
        return _day_frame(day, side)

    monkeypatch.setattr(duka, "_fetch_day", fake_fetch)
    result = duka.download(
        "EURUSD",
        start="2024-01-01",
        end="2024-01-31",
        workers=2,
        rate_per_s=0,
        root=tmp_path,
        backoff_s=0,
    )
    assert result["rows"] > 0
    assert result["ask_rows"] == result["rows"]
    files = sorted((tmp_path / "data" / "cache" / "dukascopy").glob("*"))
    assert [path.name for path in files] == ["EURUSD_M1.parquet"]
    first_calls = len(calls)

    # Segunda pasada: el mes ya está completo (llegó al día 20) y se salta.
    again = duka.download(
        "EURUSD",
        start="2024-01-01",
        end="2024-01-31",
        workers=2,
        rate_per_s=0,
        root=tmp_path,
        backoff_s=0,
    )
    assert len(calls) == first_calls
    assert again["months_skipped"] >= 1
    assert again["rows"] == result["rows"]


def test_resume_conserva_meses_anteriores(tmp_path, monkeypatch) -> None:
    def fake_fetch(client, instrument, day, side, point, **kwargs):
        return _day_frame(day, side)

    monkeypatch.setattr(duka, "_fetch_day", fake_fetch)
    duka.download(
        "EURUSD",
        start="2024-01-26",
        end="2024-01-31",
        workers=1,
        rate_per_s=0,
        root=tmp_path,
        backoff_s=0,
    )
    january = duka.load_cache("EURUSD", root=tmp_path)
    result = duka.download(
        "EURUSD",
        start="2024-02-01",
        end="2024-02-05",
        workers=1,
        rate_per_s=0,
        root=tmp_path,
        backoff_s=0,
    )
    assert result["start"] == january.index[0].isoformat()
    assert result["rows"] > len(january)
    assert result["rows"] == len(january) + 4 * 3  # 1, 2, 4 y 5 de febrero (sábado fuera)


def test_fetch_day_reintenta_429(monkeypatch) -> None:
    payload = _payload([(0, 110_010, 110_020, 110_000, 110_030, 1.0)])

    class Response:
        def __init__(self, status: int, content: bytes = b"") -> None:
            self.status_code = status
            self.content = content

    class Client:
        def __init__(self) -> None:
            self.calls = 0

        def get(self, url: str) -> Response:
            self.calls += 1
            return Response(429) if self.calls == 1 else Response(200, payload)

    monkeypatch.setattr(duka.time, "sleep", lambda _: None)
    client = Client()
    frame = duka._fetch_day(
        client,
        "EURUSD",
        date(2024, 1, 2),
        "BID",
        1e-5,
        retries=1,
        backoff_s=0,
    )
    assert client.calls == 2
    assert len(frame) == 1


def test_sin_ask_tambien_guarda_bid(tmp_path, monkeypatch) -> None:
    def fake_fetch(client, instrument, day, side, point, **kwargs):
        return _day_frame(day, side) if side == "BID" else duka._empty(side)

    monkeypatch.setattr(duka, "_fetch_day", fake_fetch)
    result = duka.download(
        "EURUSD",
        start="2024-01-02",
        end="2024-01-03",
        workers=1,
        rate_per_s=0,
        root=tmp_path,
        backoff_s=0,
    )
    assert result["rows"] == 6
    assert result["ask_rows"] == 0


def test_sin_datos_no_escribe(tmp_path, monkeypatch) -> None:
    def fake_fetch(client, instrument, day, side, point, **kwargs):
        return duka._empty(side)

    monkeypatch.setattr(duka, "_fetch_day", fake_fetch)
    with pytest.raises(duka.DukascopyError, match="Sin datos"):
        duka.download(
            "EURUSD",
            start="2024-01-01",
            end="2024-01-02",
            workers=1,
            rate_per_s=0,
            root=tmp_path,
            backoff_s=0,
        )
    assert not duka.cache_path("EURUSD", root=tmp_path).exists()


def test_simbolo_desconocido() -> None:
    with pytest.raises(duka.DukascopyError, match="no soportado"):
        duka.normalize_symbol("BTCUSD")
