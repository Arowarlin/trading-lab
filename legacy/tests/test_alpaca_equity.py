from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from tradinglab.execution.alpaca import AlpacaBroker


class FakeClient:
    def __init__(
        self,
        responses: dict[str, object],
        *,
        errors: set[str] | None = None,
    ) -> None:
        self.responses = responses
        self.errors = errors or set()
        self.calls: list[str] = []

    def get_portfolio_history(self, history_filter=None):
        period = history_filter.period
        self.calls.append(period)
        if period in self.errors:
            raise RuntimeError(f"fallo simulado en {period}")
        return self.responses.get(
            period, SimpleNamespace(timestamp=[], equity=[])
        )


def _broker(client: FakeClient, *, snapshot_equity: float | None = None):
    broker = AlpacaBroker.__new__(AlpacaBroker)
    broker.client = client
    broker.paper = True
    broker.db_path = None

    if snapshot_equity is None:

        def forbidden_snapshot(prices=None):
            raise AssertionError("snapshot no debe usarse cuando hay historial")

        broker.snapshot = forbidden_snapshot
    else:
        broker.snapshot = lambda prices=None: {"equity": snapshot_equity}
    return broker


def test_1m_vacio_3m_con_datos_devuelve_3m() -> None:
    client = FakeClient(
        {
            "1M": SimpleNamespace(timestamp=[], equity=[]),
            "3M": SimpleNamespace(
                timestamp=[1767225600, 1767312000],
                equity=[100.0, 101.0],
            ),
        }
    )
    series = _broker(client).equity_series()

    assert client.calls == ["1M", "3M"]
    assert list(series.values) == [100.0, 101.0]
    assert series.index.tz is not None


def test_todo_vacio_usa_equity_actual(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = FakeClient(
        {
            "1M": SimpleNamespace(timestamp=[], equity=[]),
            "3M": SimpleNamespace(timestamp=[], equity=[]),
        }
    )
    broker = _broker(client, snapshot_equity=12345.67)

    with caplog.at_level(logging.WARNING):
        series = broker.equity_series()

    assert client.calls == ["1M", "3M"]
    assert len(series) == 1
    assert series.iloc[0] == pytest.approx(12345.67)
    assert series.index.tz is not None
    assert any(
        "sin historial" in record.getMessage() for record in caplog.records
    )


def test_historial_con_datos_no_usa_fallback() -> None:
    client = FakeClient(
        {
            "1M": SimpleNamespace(
                timestamp=[1767225600, 1767312000, 1767398400],
                equity=[99.0, 100.0, 101.0],
            )
        }
    )
    series = _broker(client).equity_series()

    assert client.calls == ["1M"]
    assert list(series.values) == [99.0, 100.0, 101.0]


def test_error_en_1m_y_3m_vacio_usa_fallback() -> None:
    client = FakeClient(
        {"3M": SimpleNamespace(timestamp=[], equity=[])},
        errors={"1M"},
    )
    broker = _broker(client, snapshot_equity=500.0)

    series = broker.equity_series()

    assert client.calls == ["1M", "3M"]
    assert len(series) == 1
    assert series.iloc[0] == pytest.approx(500.0)
