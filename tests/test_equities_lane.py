from __future__ import annotations

import json
from pathlib import Path

import pytest

from tradinglab.daytrader import plan_orders
from tradinglab.equities_lane import Lane, LaneError, load_lane, status, symbol_in_lane

FIXTURES = Path(__file__).parent / "fixtures" / "daytrader"


def _config(tmp_path: Path, ticker: str = "AAPL") -> Path:
    path = tmp_path / "equities_lane.yaml"
    path.write_text(
        f"version: 1\nticker: {ticker}\nsetup: orb\nonly_ticker: true\n",
        encoding="utf-8",
    )
    return path


def test_la_configuracion_real_fija_un_ticker():
    lane = load_lane()
    assert lane.ticker == "AAPL"
    assert lane.only_ticker is True
    assert lane.account == "alpaca_paper"


def test_un_carril_sin_ticker_no_es_valido(tmp_path):
    path = tmp_path / "equities_lane.yaml"
    path.write_text("version: 1\nsetup: orb\n", encoding="utf-8")
    with pytest.raises(LaneError):
        load_lane(path)


def test_el_carril_solo_admite_su_ticker(tmp_path):
    lane = load_lane(_config(tmp_path))
    assert lane.allows("AAPL")
    assert lane.allows("aapl")
    assert not lane.allows("MSFT")
    assert symbol_in_lane("AAPL", lane)
    assert not symbol_in_lane("MSFT", lane)


def test_el_carril_sin_configuracion_no_admite_a_nadie():
    with pytest.raises(LaneError):
        load_lane(Path("no-existe-este-carril.yaml"))
    # sin configuración válida no se símbolo entra
    assert not symbol_in_lane("AAPL", Lane(ticker="", only_ticker=True))


def test_el_estado_lee_el_pipeline_externo(tmp_path):
    (tmp_path / "entry.json").write_text(
        json.dumps(
            {
                "symbol": "AAPL",
                "setup": "orb",
                "status": "waiting",
                "level": 353.87,
                "date": "2026-11-10",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "watchlist.json").write_text(
        json.dumps(
            {
                "as_of": "2026-11-10 close",
                "hits": [
                    {"symbol": "AAPL", "setup": "breakout_20d", "price": 350.69},
                    {"symbol": "MSFT", "setup": "reclaim_ma20", "price": 545.18},
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "targets.json").write_text(
        json.dumps(
            {
                "source": "13F",
                "weights": [{"ticker": "AAPL", "weight": 30.67}],
            }
        ),
        encoding="utf-8",
    )
    payload = status(directory=tmp_path)
    assert payload["ticker"] == "AAPL"
    assert payload["entry"]["status"] == "waiting"
    assert payload["entry"]["level"] == 353.87
    assert payload["watchlist_hits"] == 1
    assert payload["target_weight"] == 30.67
    assert payload["orders_in_lane"] == 0


def test_una_orden_fuera_del_carril_se_rechaza(tmp_path, monkeypatch):
    from tradinglab.config import Settings

    shutil_state = tmp_path / "state"
    shutil_state.mkdir(parents=True, exist_ok=True)
    (shutil_state / "risk.json").write_text(
        json.dumps(
            {
                "verdicts": [
                    {
                        "verdict": "PASS",
                        "fingerprint": "abc123",
                        "order": {"symbol": "MSFT"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "orders.json").write_text(
        json.dumps(
            {
                "orders": [
                    {
                        "symbol": "MSFT",
                        "side": "buy",
                        "qty": "4",
                        "type": "market",
                        "time_in_force": "day",
                        "order_class": "bracket",
                        "stop_loss_stop_price": "500.00",
                        "take_profit_limit_price": "560.00",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "tradinglab.daytrader.load_lane",
        lambda *args, **kwargs: Lane(ticker="AAPL", only_ticker=True),
    )
    settings = Settings(
        mode="paper",
        daytrader={"dir": str(tmp_path), "account": "alpaca_paper", "enabled": True},
    )
    plan = plan_orders(settings, tmp_path, execute=False)
    assert plan["lane_ticker"] == "AAPL"
    assert len(plan["orders"]) == 1
    order = plan["orders"][0]
    assert order["action"] == "rechazada"
    assert order["guard_verdict"] == "BLOCK"
    assert "fuera del carril" in order["reason"]
