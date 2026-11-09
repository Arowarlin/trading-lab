from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from tradinglab.config import RiskSettings, get_settings
from tradinglab.cushion import (
    DEFAULT_THRESHOLDS,
    evaluate,
    evaluate_from_db,
    load_thresholds,
    summary_line,
)
from tradinglab.db import connect, init_db


def _series(values: list[float], start: str = "2026-11-09 14:00") -> pd.Series:
    index = pd.date_range(start, periods=len(values), freq="h", tz="UTC")
    return pd.Series(values, index=index, dtype=float)


def _cfg() -> RiskSettings:
    return RiskSettings(daily_loss_limit_pct=0.03, max_drawdown_pct=0.15)


def _now() -> datetime:
    return datetime(2026, 11, 9, 17, 0, tzinfo=timezone.utc)


def test_umbrales_por_defecto_y_archivo(tmp_path: Path) -> None:
    assert load_thresholds(tmp_path / "no-existe.yaml") == DEFAULT_THRESHOLDS
    path = tmp_path / "cushion.yaml"
    path.write_text(
        "daily:\n"
        "  amber_at_used: 0.25\n"
        "  red_at_used: 0.60\n"
        "drawdown:\n"
        "  amber_at_used: 0.40\n"
        "  red_at_used: 0.90\n",
        encoding="utf-8",
    )
    loaded = load_thresholds(path)
    assert loaded["daily"] == {"amber_at_used": 0.25, "red_at_used": 0.60}
    assert loaded["drawdown"] == {"amber_at_used": 0.40, "red_at_used": 0.90}


def test_umbrales_invalidos_fallan(tmp_path: Path) -> None:
    path = tmp_path / "cushion.yaml"
    path.write_text(
        "daily:\n  amber_at_used: 0.9\n  red_at_used: 0.5\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="amber"):
        load_thresholds(path)


def test_semaforo_verde() -> None:
    report = evaluate(
        _series([100_000.0, 100_000.0, 100_500.0]),
        _cfg(),
        current=100_500.0,
        now=_now(),
    )
    assert report.state == "green"
    assert report.daily.state == "green"
    assert report.drawdown.state == "green"
    assert report.daily.used_fraction == 0.0
    assert report.daily.remaining_pct == pytest.approx(0.03)
    assert report.daily.remaining_usd == pytest.approx(3_000.0)


def test_semaforo_ambar_por_perdida_diaria() -> None:
    report = evaluate(
        _series([100_000.0, 100_000.0, 98_500.0]),
        _cfg(),
        current=98_500.0,
        now=_now(),
    )
    assert report.daily.used_fraction == pytest.approx(0.5)
    assert report.daily.state == "amber"
    assert report.state == "amber"


def test_semaforo_rojo_por_perdida_diaria() -> None:
    report = evaluate(
        _series([100_000.0, 100_000.0, 97_600.0]),
        _cfg(),
        current=97_600.0,
        now=_now(),
    )
    assert report.daily.used_fraction == pytest.approx(0.8)
    assert report.daily.state == "red"
    assert report.state == "red"


def test_semaforo_drawdown_y_colchon_restante() -> None:
    report = evaluate(
        _series([100_000.0, 110_000.0, 94_000.0]),
        _cfg(),
        current=94_000.0,
        now=_now(),
    )
    assert report.drawdown.used_fraction == pytest.approx((110_000 - 94_000) / 110_000 / 0.15)
    assert report.drawdown.state == "red"
    assert report.drawdown.remaining_pct == pytest.approx(0.15 - (110_000 - 94_000) / 110_000)
    assert report.state == "red"


def test_limites_explicitos_no_cambian_el_guard() -> None:
    report = evaluate(
        _series([100_000.0, 100_000.0, 98_500.0]),
        _cfg(),
        current=98_500.0,
        now=_now(),
        daily_loss_limit_pct=0.02,
        max_drawdown_pct=0.10,
    )
    assert report.daily.limit_pct == pytest.approx(0.02)
    assert report.drawdown.limit_pct == pytest.approx(0.10)
    assert report.daily.used_fraction == pytest.approx(0.75)
    assert report.informative is True


def test_sin_datos_no_inventa_verde(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    report = evaluate_from_db(db)
    assert report.state == "no_data"
    assert report.daily.state == "no_data"
    assert report.drawdown.state == "no_data"
    assert "sin datos" in summary_line(report)


def test_evaluate_from_db_lee_equity(tmp_path: Path) -> None:
    db = tmp_path / "lab.db"
    init_db(db)
    with connect(db) as con:
        con.execute(
            "INSERT INTO equity(ts, cash, positions_value, equity) VALUES(?,?,?,?)",
            ("2026-11-09T14:00:00+00:00", 100_000.0, 0.0, 100_000.0),
        )
        con.execute(
            "INSERT INTO equity(ts, cash, positions_value, equity) VALUES(?,?,?,?)",
            ("2026-11-09T15:00:00+00:00", 98_500.0, 0.0, 98_500.0),
        )
    report = evaluate_from_db(db, now=_now())
    assert report.daily.state == "amber"
    assert report.daily.remaining_usd == pytest.approx(1_500.0)
    assert "ámbar" in summary_line(report)


def test_archivo_roto_cae_en_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "cushion.yaml"
    path.write_text("daily: [no-es-un-mapa]\n", encoding="utf-8")
    import tradinglab.cushion as cushion

    monkeypatch.setattr(cushion, "CUSHION_FILE", path)
    report = evaluate(
        _series([100_000.0, 100_000.0, 98_500.0]),
        _cfg(),
        current=98_500.0,
        now=_now(),
    )
    assert report.daily.state == "amber"
    assert report.warning is not None
    assert report.thresholds == DEFAULT_THRESHOLDS


def test_usa_limites_del_killswitch_por_defecto() -> None:
    settings = get_settings()
    report = evaluate(
        _series([100_000.0, 100_000.0, 98_500.0]),
        settings.risk,
        current=98_500.0,
        now=_now(),
    )
    assert report.daily.limit_pct == pytest.approx(settings.risk.daily_loss_limit_pct)
    assert report.drawdown.limit_pct == pytest.approx(settings.risk.max_drawdown_pct)


def test_estado_de_telegram_incluye_el_colchon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tradinglab import telegram as tg

    report = evaluate(
        _series([100_000.0, 100_000.0, 98_500.0]),
        _cfg(),
        current=98_500.0,
        now=_now(),
    )
    monkeypatch.setattr(
        "tradinglab.cushion.evaluate_from_db",
        lambda *args, **kwargs: report,
    )
    text = tg.status_text(tg.TelegramConfig())
    assert "Colchón riesgo: ámbar" in text
    assert "resta 1.50%" in text
