from __future__ import annotations

from datetime import date, datetime, timezone

from tradinglab.time_utils import market_today, utc_now


def test_market_today_invierno_23_30_local_es_dia_anterior_en_ny():
    # 23:30 en Santo Domingo (UTC-4) = 03:30 UTC del día siguiente.
    moment = datetime(2026, 1, 16, 3, 30, tzinfo=timezone.utc)
    assert market_today(moment) == date(2026, 1, 15)


def test_market_today_verano_03_30_utc_es_dia_anterior_en_ny():
    moment = datetime(2026, 7, 16, 3, 30, tzinfo=timezone.utc)
    assert market_today(moment) == date(2026, 7, 15)


def test_utc_now_tiene_zona():
    moment = utc_now()
    assert moment.tzinfo is timezone.utc
    assert moment.utcoffset().total_seconds() == 0
