"""Fetch M5 con MT5 simulado: sin login/shutdown, login estable y bloques."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from tradinglab.discovery import fetch


@dataclass
class _Info:
    login: int
    server: str = "FTMO-Server"
    trade_mode: int = 0


class _FakeMT5:
    TIMEFRAME_M5 = 5

    def __init__(self, *, login: int = 111111, change_after_copy: bool = False):
        self.login = login
        self.change_after_copy = change_after_copy
        self.copied = False
        self.calls: list[object] = []

    def account_info(self):
        self.calls.append("account_info")
        login = 222222 if self.copied and self.change_after_copy else self.login
        return _Info(login=login)

    def symbol_select(self, symbol: str, enable: bool) -> bool:
        self.calls.append(("symbol_select", symbol, enable))
        return True

    def copy_rates_range(self, symbol, timeframe, start: datetime, end: datetime):
        self.calls.append(("copy_rates_range", symbol, start, end))
        self.copied = True
        index = pd.date_range(start, end, freq="5min", inclusive="left")
        return [
            {
                "time": int(stamp.timestamp()),
                "open": 100.0,
                "high": 100.5,
                "low": 99.5,
                "close": 100.2,
                "tick_volume": 10,
                "spread": 1.0,
            }
            for stamp in index
        ]

    def login(self, *args, **kwargs):
        self.calls.append("login")
        return True

    def shutdown(self):
        self.calls.append("shutdown")


class _FakeBroker:
    def __init__(self, mt5: _FakeMT5, *, expected_login: int = 111111):
        self.mt5 = mt5
        self.expected_login = expected_login
        self.expected_server = "FTMO-Server"

    def connect(self):
        return {"identity_ok": True}

    def _require(self):
        return self.mt5


def _factory(mt5: _FakeMT5):
    return lambda account: _FakeBroker(mt5)


def _download(tmp_path: Path, mt5: _FakeMT5, *, block_days: int = 3, **kwargs):
    return fetch.download(
        "EURUSD",
        account="CFD-001",
        timeframe="M5",
        start="2024-01-01",
        end="2024-01-10",
        block_days=block_days,
        pause_s=0,
        root=tmp_path,
        broker_factory=_factory(mt5),
        offset_hours=0.0,
        **kwargs,
    )


def test_fetch_sin_login_ni_shutdown_y_solo_discovery(tmp_path: Path) -> None:
    mt5 = _FakeMT5()
    result = _download(tmp_path, mt5)

    assert result["rows"] > 0
    assert not any(call == "login" for call in mt5.calls)
    assert not any(call == "shutdown" for call in mt5.calls)
    assert any(isinstance(call, tuple) and call[0] == "symbol_select" for call in mt5.calls)
    assert any(isinstance(call, tuple) and call[0] == "copy_rates_range" for call in mt5.calls)
    assert sum(1 for call in mt5.calls if call == "account_info") >= 2

    output = Path(result["path"])
    assert output.exists()
    assert "data/cache/discovery" in output.as_posix()
    assert not list((tmp_path / "data" / "cache" / "mt5").glob("*.parquet"))
    assert not list((tmp_path / "data" / "cache" / "ea").glob("*.parquet"))


def test_fetch_aborta_si_el_login_cambia(tmp_path: Path) -> None:
    mt5 = _FakeMT5(change_after_copy=True)
    with pytest.raises(fetch.FetchError, match="login esperado"):
        _download(tmp_path, mt5)

    assert not list((tmp_path / "data" / "cache" / "discovery").glob("*.parquet"))
    assert not any(call == "login" for call in mt5.calls)
    assert not any(call == "shutdown" for call in mt5.calls)


def test_fetch_bloques_contiguos_sin_duplicados(tmp_path: Path) -> None:
    mt5 = _FakeMT5()
    result = _download(tmp_path, mt5, block_days=2)
    frame = pd.read_parquet(result["path"])

    assert frame.index.is_unique
    assert frame.index.is_monotonic_increasing
    diffs = frame.index.to_series().diff().dropna()
    assert (diffs == pd.Timedelta(minutes=5)).all()
    assert str(frame.index.tz) == "UTC"


def test_fetch_usa_el_simbolo_del_contrato(tmp_path: Path) -> None:
    mt5 = _FakeMT5()
    result = fetch.download(
        "US30",
        account="CFD-001",
        timeframe="M5",
        start="2024-01-01",
        end="2024-01-03",
        block_days=2,
        pause_s=0,
        root=tmp_path,
        broker_factory=_factory(mt5),
        offset_hours=0.0,
    )
    assert result["broker_symbol"] == "US30.cash"
    assert "US30_M5.parquet" in result["path"]
