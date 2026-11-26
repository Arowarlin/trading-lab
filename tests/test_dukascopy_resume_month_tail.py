"""C-02 (ENG-1): reanudar Dukascopy no debe perder el final del último mes en caché.

Feed simulado con ``httpx.MockTransport`` (sin red): cada día no domingo sirve
60 velas M1 sintéticas. Ver docs/engineering/AUDIT_FINDINGS.md (C-02).
"""

from __future__ import annotations

import lzma
import struct
from datetime import datetime, timezone

import httpx

from tradinglab.discovery import fetch_dukascopy as fd

_REC = struct.Struct(">IIIIIf")


def _payload() -> bytes:
    raw = b""
    for minute in range(60):
        price = 17_000_000
        raw += _REC.pack(minute * 60, price, price, price - 1_000, price + 1_000, 1.0)
    return lzma.compress(raw)


def _client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        parts = request.url.path.split("/")
        year, month0, day = int(parts[-4]), int(parts[-3]), int(parts[-2])
        if datetime(year, month0 + 1, day).weekday() == 6:
            return httpx.Response(200, content=b"")
        return httpx.Response(200, content=_payload())

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_reanudar_descarga_el_final_del_ultimo_mes_en_cache(tmp_path):
    client = _client()
    # 1.ª ejecución el 25-nov: la caché llega hasta el 24-nov (día >= 20).
    fd.download(
        "US100",
        start="2026-11-01",
        include_ask=False,
        root=tmp_path,
        client=client,
        now=datetime(2026, 11, 25, 10, tzinfo=timezone.utc),
        rate_per_s=0,
    )
    # 2.ª ejecución el 3-dic: noviembre ya no es el mes en curso.
    fd.download(
        "US100",
        start="2026-11-01",
        include_ask=False,
        root=tmp_path,
        client=client,
        now=datetime(2026, 12, 3, 10, tzinfo=timezone.utc),
        rate_per_s=0,
    )
    cache = fd.load_cache("US100", root=tmp_path)
    november = {ts.date().day for ts in cache.index if ts.month == 11}
    for day in (25, 26, 27, 30):
        assert day in november, f"falta el {day}-nov tras reanudar"


def test_meses_anteriores_completos_se_siguen_saltando(tmp_path):
    client = _client()
    fd.download(
        "US100",
        start="2026-09-01",
        include_ask=False,
        root=tmp_path,
        client=client,
        now=datetime(2026, 11, 25, 10, tzinfo=timezone.utc),
        rate_per_s=0,
    )
    second = fd.download(
        "US100",
        start="2026-09-01",
        include_ask=False,
        root=tmp_path,
        client=client,
        now=datetime(2026, 12, 3, 10, tzinfo=timezone.utc),
        rate_per_s=0,
    )
    # Septiembre y octubre están completos y tienen datos posteriores: se saltan.
    assert second["months_skipped"] == 2
