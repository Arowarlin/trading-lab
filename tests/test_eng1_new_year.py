"""ENG-1 C-07: con el 1-ene en sábado, el viernes 31-dic no es festivo (NYSE, CME, FX).

Solo afecta al código de investigación (``discovery/calendars.py``). El
calendario del EA (``nyse_calendar.py``) no se toca: su único caso es
2021-12-31 (histórico) y entra en el hash congelado del forward.
"""

from __future__ import annotations

from datetime import date

import pytest

from tradinglab.discovery import calendars


@pytest.mark.parametrize("fn", [calendars.nyse_holidays, calendars.cme_holidays, calendars.fx_metal_holidays])
@pytest.mark.parametrize("day", [date(2010, 12, 31), date(2021, 12, 31), date(2027, 12, 31)])
def test_31_dic_antes_de_un_sabado_no_es_festivo(fn, day):
    assert int(day.strftime("%Y%m%d")) not in fn(2005, 2030)


@pytest.mark.parametrize("fn", [calendars.nyse_holidays, calendars.cme_holidays])
def test_domingo_sigue_pasando_al_lunes(fn):
    # 2017-01-01 y 2023-01-01 fueron domingo: NYSE/CME cerraron el lunes 2.
    holidays = fn(2010, 2030)
    assert 20170102 in holidays and 20230102 in holidays


def test_el_calendario_del_ea_no_cambia():
    from tradinglab import nyse_calendar

    assert nyse_calendar.is_full_holiday(date(2021, 12, 31)) is True  # histórico, sin tocar
    assert "20271231" not in nyse_calendar.holiday_input(2026, 2027)
