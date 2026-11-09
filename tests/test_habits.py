from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tradinglab.habits import (
    DEFAULT_CONFIG,
    detect,
    detect_overtrading,
    detect_revenge,
    load_config,
)


def _trade(
    *,
    day: str = "2026-01-05",
    bot: str = "trend-spy",
    account: str = "paper_main",
    pnl: float = 10.0,
    entry_ts: str = "2026-01-05T10:00:00+00:00",
    exit_ts: str = "2026-01-05T10:30:00+00:00",
    risk_usd: float | None = 20.0,
) -> SimpleNamespace:
    return SimpleNamespace(
        day=day,
        bot=bot,
        account=account,
        pnl=pnl,
        entry_ts=entry_ts,
        exit_ts=exit_ts,
        risk_usd=risk_usd,
    )


def test_revenge_detecta_entrada_rapida_con_mas_riesgo() -> None:
    previous = _trade(pnl=-50.0, exit_ts="2026-01-05T10:00:00+00:00", risk_usd=20.0)
    current = _trade(
        entry_ts="2026-01-05T10:15:00+00:00",
        exit_ts="2026-01-05T10:45:00+00:00",
        risk_usd=30.0,
    )
    result = detect_revenge([previous, current], window_minutes=30)
    assert result["count"] == 1
    assert result["events"][0]["minutes"] == pytest.approx(15.0)
    assert result["events"][0]["risk_usd"] > result["events"][0]["previous_risk_usd"]


def test_revenge_no_marca_riesgo_menor_ni_fuera_de_ventana() -> None:
    previous = _trade(pnl=-50.0, exit_ts="2026-01-05T10:00:00+00:00", risk_usd=20.0)
    lower_risk = _trade(
        entry_ts="2026-01-05T10:10:00+00:00",
        exit_ts="2026-01-05T10:40:00+00:00",
        risk_usd=10.0,
    )
    late = _trade(
        entry_ts="2026-01-05T11:00:00+00:00",
        exit_ts="2026-01-05T11:30:00+00:00",
        risk_usd=30.0,
    )
    assert detect_revenge([previous, lower_risk], window_minutes=30)["count"] == 0
    assert detect_revenge([previous, late], window_minutes=30)["count"] == 0


def test_revenge_no_marca_tras_ganancia() -> None:
    previous = _trade(pnl=50.0, exit_ts="2026-01-05T10:00:00+00:00", risk_usd=20.0)
    current = _trade(
        entry_ts="2026-01-05T10:05:00+00:00",
        exit_ts="2026-01-05T10:35:00+00:00",
        risk_usd=30.0,
    )
    assert detect_revenge([previous, current], window_minutes=30)["count"] == 0


def test_revenge_separa_por_cuenta() -> None:
    previous = _trade(
        account="paper_main",
        pnl=-50.0,
        exit_ts="2026-01-05T10:00:00+00:00",
        risk_usd=20.0,
    )
    other = _trade(
        account="ftmo_demo",
        entry_ts="2026-01-05T10:05:00+00:00",
        exit_ts="2026-01-05T10:35:00+00:00",
        risk_usd=30.0,
    )
    assert detect_revenge([previous, other], window_minutes=30)["count"] == 0


def test_overtrading_usa_mediana_y_minimo() -> None:
    trades = [_trade(day=f"2026-01-0{day}") for day in range(1, 5)]
    trades += [_trade(day="2026-01-05") for _ in range(5)]
    result = detect_overtrading(trades, min_trades=4, median_multiple=2.0)
    assert result["count"] == 1
    assert result["median"] == pytest.approx(1.0)
    assert result["threshold"] == 4
    assert result["days"][0]["day"] == "2026-01-05"
    assert result["days"][0]["trades"] == 5


def test_overtrading_no_marca_un_dia_normal() -> None:
    trades = [_trade(day=f"2026-01-0{day}") for day in range(1, 6)]
    result = detect_overtrading(trades, min_trades=4, median_multiple=2.0)
    assert result["count"] == 0
    assert result["threshold"] == 4


def test_config_override_y_archivo_invalido(tmp_path: Path) -> None:
    path = tmp_path / "detectors.yaml"
    path.write_text(
        "revenge:\n  window_minutes: 10\n"
        "overtrading:\n  min_trades: 2\n  median_multiple: 3\n",
        encoding="utf-8",
    )
    config = load_config(path)
    assert config["revenge"]["window_minutes"] == pytest.approx(10.0)
    assert config["overtrading"]["min_trades"] == 2
    assert config["overtrading"]["median_multiple"] == pytest.approx(3.0)

    bad = tmp_path / "bad.yaml"
    bad.write_text("revenge:\n  window_minutes: 0\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(bad)


def test_detect_es_informativo_y_no_bloquea() -> None:
    result = detect([], config=DEFAULT_CONFIG)
    assert result["informative"] is True
    assert result["blocking"] is False
    assert result["revenge"]["count"] == 0
    assert result["overtrading"]["count"] == 0
