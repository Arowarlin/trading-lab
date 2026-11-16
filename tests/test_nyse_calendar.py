from __future__ import annotations

import re
from pathlib import Path

from tradinglab.nyse_calendar import (
    EARLY_CLOSES,
    FULL_HOLIDAYS,
    early_close_input,
    effective_flat_min,
    holiday_input,
    is_full_holiday,
)

ROOT = Path(__file__).resolve().parents[1]
EA = ROOT / "integrations" / "mt5" / "us100_ftmo1" / "US100_EA.mq5"
SETFILE = ROOT / "integrations" / "mt5" / "us100_ftmo1" / "US100_FTMO_v3_challenge.set"


def test_calendario_sin_solapamiento():
    assert not (set(FULL_HOLIDAYS) & set(EARLY_CLOSES))


def test_2026_07_03_es_festivo_completo_no_cierre_temprano():
    assert 20260703 in FULL_HOLIDAYS
    assert 20260703 not in EARLY_CLOSES
    assert is_full_holiday(20260703)
    assert effective_flat_min(20260703, 1545) == 945


def test_2027_festivos_y_cierres_tempranos():
    assert 20270101 in FULL_HOLIDAYS
    assert 20270705 in FULL_HOLIDAYS
    assert 20271224 in FULL_HOLIDAYS
    assert 20271231 not in FULL_HOLIDAYS
    assert 20271126 in EARLY_CLOSES
    assert 20271126 not in FULL_HOLIDAYS
    assert 20270702 not in EARLY_CLOSES
    assert holiday_input(2027, 2027).split(",") == [
        "20270101",
        "20270118",
        "20270215",
        "20270326",
        "20270531",
        "20270618",
        "20270705",
        "20270906",
        "20271125",
        "20271224",
    ]


def test_inputs_del_ea_coinciden_con_el_calendario():
    source = EA.read_text(encoding="utf-8")
    early = re.search(r'InpEarlyClose\s*=\s*"([^"]*)"', source)
    holidays = re.search(r'InpHolidays\s*=\s*"([^"]*)"', source)
    assert early is not None and early.group(1) == early_close_input()
    assert holidays is not None
    assert holidays.group(1) == holiday_input(2026, 2027)

    setfile = SETFILE.read_text(encoding="utf-8")
    assert f"InpEarlyClose={early_close_input()}" in setfile
    assert f"InpHolidays={holiday_input(2026, 2027)}" in setfile
