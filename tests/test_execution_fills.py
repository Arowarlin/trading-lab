"""Contrato del modo de ejecución por eventos de intraday.py (aún no implementado).

API esperada::

    run_event_backtest(
        bars: pd.DataFrame,          # índice ts UTC; open, high, low, close
        orders: list[dict],          # side, level, stop, target, created_at, expires_at
        *,
        point: float = 0.01,
        commission_bps: float = 1.0,
        spread_bps: float = 10.0,
        slippage_bps: float = 5.0,
        fill_pessimism_points: int = 0,
        max_trades_per_day: int = 1,
        force_exit_time: datetime.time | None = None,
        session_offset_hours: float = 0.0,
    ) -> dict

Resultado esperado::

    {
        "trades": [
            {
                "side": "buy" | "sell",
                "entry_time": pd.Timestamp,
                "entry_price": float,
                "exit_time": pd.Timestamp,
                "exit_price": float,
                "exit_reason": "target" | "stop" | "force_exit",
                "entry_costs": {
                    "commission_bps": float,
                    "spread_bps": float,
                    "slippage_bps": float,
                },
                "exit_costs": {...},
            }
        ],
        "expired": int,
        "ignored": int,
    }

`created_at` es exclusivo: la orden puede ejecutarse en barras con ts > created_at.
`expires_at` marca el final de la ventana: una orden no ejecutada expira ahí y no
se arrastra al día siguiente. `force_exit_time` está en hora de sesión; el motor
debe convertirla a UTC con `session_offset_hours` (el offset semanal inferido por
`mt5_offsets.py`).

Estos tests deben fallar mientras `run_event_backtest` no exista. No son una
implementación ni una guía de datos reales: todas las barras son sintéticas.
"""
from __future__ import annotations

from datetime import time

import pandas as pd
import pytest

from tradinglab.prop.rules import PropRules


def _bars(*rows: tuple[str, float, float, float, float]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ts": pd.Timestamp(ts, tz="UTC"),
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
            }
            for ts, open_, high, low, close in rows
        ]
    ).set_index("ts")


def _order(
    side: str,
    level: float,
    stop: float,
    target: float,
    *,
    created: str = "2026-11-09 09:00",
    expires: str = "2026-11-09 09:15",
) -> dict:
    return {
        "side": side,
        "level": level,
        "stop": stop,
        "target": target,
        "created_at": pd.Timestamp(created, tz="UTC"),
        "expires_at": pd.Timestamp(expires, tz="UTC"),
    }


def _run(bars: pd.DataFrame, orders: list[dict], **kwargs):
    from tradinglab.intraday import run_event_backtest

    defaults = {
        "point": 0.01,
        "commission_bps": 1.0,
        "spread_bps": 10.0,
        "slippage_bps": 5.0,
        "fill_pessimism_points": 0,
        "max_trades_per_day": 1,
        "force_exit_time": None,
        "session_offset_hours": 0.0,
        "session_window": (time(0, 0), time(0, 0)),
        "session_tz": "UTC",
        "session_weekdays": (0, 1, 2, 3, 4),
        "session_rules": None,
        # Los tests históricos describen acciones; T07 solo cambia cfd/fx.
        "asset_class": "equity",
        "symbol": None,
    }
    defaults.update(kwargs)
    return run_event_backtest(bars, orders, **defaults)


# ---------------------------------------------------------------- límites 1 y 2


def test_buy_limit_solo_si_low_estrictamente_menor():
    bars = _bars(("2026-11-09 09:15", 100.0, 102.5, 99.99, 101.0))
    order = _order("buy", 100.0, 98.0, 102.0)
    result = _run(bars, [order])
    assert len(result["trades"]) == 1
    trade = result["trades"][0]
    assert trade["side"] == "buy"
    assert trade["entry_price"] == pytest.approx(100.0)


def test_buy_limit_no_fill_si_low_igual_que_level():
    bars = _bars(("2026-11-09 09:15", 100.0, 102.5, 100.0, 101.0))
    order = _order("buy", 100.0, 98.0, 102.0)
    result = _run(bars, [order])
    assert result["trades"] == []
    assert result["expired"] == 1


def test_sell_limit_solo_si_high_estrictamente_mayor():
    bars = _bars(("2026-11-09 09:15", 100.0, 100.01, 98.0, 99.0))
    order = _order("sell", 100.0, 102.0, 98.0)
    result = _run(bars, [order])
    assert len(result["trades"]) == 1
    assert result["trades"][0]["side"] == "sell"
    assert result["trades"][0]["entry_price"] == pytest.approx(100.0)


def test_sell_limit_no_fill_si_high_igual_que_level():
    bars = _bars(("2026-11-09 09:15", 100.0, 100.0, 98.0, 99.0))
    order = _order("sell", 100.0, 102.0, 98.0)
    result = _run(bars, [order])
    assert result["trades"] == []
    assert result["expired"] == 1


# --------------------------------------------------- T07: spread en CFD/FX


def test_buy_limit_cfd_no_fill_si_el_ask_no_toca_el_nivel():
    bars = _bars(("2026-11-09 09:15", 100.0, 100.5, 99.95, 100.2))
    order = _order("buy", 100.0, 98.0, 102.0)
    result = _run(
        bars, [order], asset_class="cfd", spread_bps=10.0
    )
    assert result["trades"] == []
    assert result["expired"] == 1


def test_buy_limit_cfd_fill_si_el_ask_toca_el_nivel():
    bars = _bars(("2026-11-09 09:15", 100.0, 100.5, 99.9, 100.2))
    order = _order("buy", 100.0, 98.0, 100.2)
    result = _run(
        bars, [order], asset_class="cfd", spread_bps=10.0
    )
    assert len(result["trades"]) == 1
    assert result["trades"][0]["entry_price"] == pytest.approx(100.0)


def test_buy_limit_cfd_usa_el_spread_de_la_hora():
    bars = _bars(("2026-11-09 09:15", 100.0, 100.5, 99.9, 100.2))
    order = _order("buy", 100.0, 98.0, 100.2)
    result = _run(
        bars,
        [order],
        asset_class="cfd",
        spread_bps=0.0,
        spread_by_hour={9: 50.0},
    )
    assert result["trades"] == []

    fallback = _run(
        bars,
        [order],
        asset_class="cfd",
        spread_bps=10.0,
        spread_by_hour={10: 50.0},
    )
    assert len(fallback["trades"]) == 1


def test_target_corto_cfd_exige_ask_en_el_objetivo():
    bars = _bars(
        ("2026-11-09 09:15", 100.0, 100.05, 99.95, 100.0),
        ("2026-11-09 09:30", 99.5, 99.5, 99.0, 99.4),
        ("2026-11-09 09:45", 99.2, 99.4, 98.9, 99.0),
    )
    order = _order(
        "sell", 100.0, 101.0, 99.0, expires="2026-11-09 09:50"
    )
    result = _run(
        bars, [order], asset_class="cfd", spread_bps=10.0
    )
    assert len(result["trades"]) == 1
    assert result["trades"][0]["exit_reason"] == "target"
    assert result["trades"][0]["exit_price"] == pytest.approx(99.0)


# ------------------------------------------------------------------- regla 3


def test_misma_barra_stop_y_target_prioriza_stop():
    bars = _bars(("2026-11-09 09:15", 100.0, 101.5, 98.5, 100.0))
    order = _order("buy", 100.0, 99.0, 101.0)
    result = _run(bars, [order])
    assert len(result["trades"]) == 1
    trade = result["trades"][0]
    assert trade["exit_reason"] == "stop"
    assert trade["exit_price"] == pytest.approx(99.0)


# -------------------------------------------------------------- huecos de precio


def test_stop_compra_con_hueco_abajo_fill_peor():
    bars = _bars(
        ("2026-11-09 09:15", 100.0, 101.0, 99.99, 100.5),
        ("2026-11-09 09:30", 90.0, 92.0, 89.0, 91.0),
    )
    order = _order("buy", 100.0, 95.0, 110.0, expires="2026-11-09 10:00")
    trade = _run(bars, [order])["trades"][0]
    assert trade["exit_reason"] == "stop"
    assert trade["exit_price"] == pytest.approx(90.0)


def test_stop_venta_con_hueco_arriba_fill_peor():
    bars = _bars(
        ("2026-11-09 09:15", 100.0, 100.01, 99.0, 99.5),
        ("2026-11-09 09:30", 110.0, 111.0, 108.0, 109.0),
    )
    order = _order("sell", 100.0, 105.0, 90.0, expires="2026-11-09 10:00")
    trade = _run(bars, [order])["trades"][0]
    assert trade["exit_reason"] == "stop"
    assert trade["exit_price"] == pytest.approx(110.0)


def test_objetivo_compra_no_regala_el_hueco():
    bars = _bars(
        ("2026-11-09 09:15", 100.0, 101.0, 99.9, 100.5),
        ("2026-11-09 09:30", 120.0, 125.0, 119.0, 121.0),
    )
    order = _order("buy", 100.0, 95.0, 110.0, expires="2026-11-09 10:00")
    trade = _run(bars, [order])["trades"][0]
    assert trade["exit_reason"] == "target"
    assert trade["exit_price"] == pytest.approx(110.0)


def test_objetivo_venta_no_regala_el_hueco():
    bars = _bars(
        ("2026-11-09 09:15", 100.0, 100.1, 99.0, 99.5),
        ("2026-11-09 09:30", 80.0, 81.0, 75.0, 79.0),
    )
    order = _order("sell", 100.0, 105.0, 90.0, expires="2026-11-09 10:00")
    trade = _run(bars, [order])["trades"][0]
    assert trade["exit_reason"] == "target"
    assert trade["exit_price"] == pytest.approx(90.0)


def test_entrada_limitada_compra_no_usa_hueco_favorable():
    bars = _bars(
        ("2026-11-09 09:15", 90.0, 95.0, 89.0, 94.0),
        ("2026-11-09 09:30", 120.0, 125.0, 119.0, 121.0),
    )
    order = _order("buy", 100.0, 80.0, 120.0, expires="2026-11-09 10:00")
    trade = _run(bars, [order])["trades"][0]
    assert trade["entry_price"] == pytest.approx(100.0)


def test_entrada_limitada_venta_no_usa_hueco_favorable():
    bars = _bars(
        ("2026-11-09 09:15", 110.0, 111.0, 105.0, 106.0),
        ("2026-11-09 09:30", 80.0, 81.0, 75.0, 79.0),
    )
    order = _order("sell", 100.0, 120.0, 80.0, expires="2026-11-09 10:00")
    trade = _run(bars, [order])["trades"][0]
    assert trade["entry_price"] == pytest.approx(100.0)


# ------------------------------------------------------------------- costes 4


def test_entrada_limitada_no_paga_spread():
    bars = _bars(("2026-11-09 09:15", 100.0, 102.5, 99.9, 101.5))
    order = _order("buy", 100.0, 98.0, 102.0)
    trade = _run(bars, [order])["trades"][0]
    assert trade["entry_costs"] == {
        "commission_bps": 1.0,
        "spread_bps": 0.0,
        "slippage_bps": 0.0,
    }


def test_salida_objetivo_limitada_no_paga_spread():
    bars = _bars(("2026-11-09 09:15", 100.0, 102.5, 99.9, 101.5))
    order = _order("buy", 100.0, 98.0, 102.0)
    trade = _run(bars, [order])["trades"][0]
    assert trade["exit_reason"] == "target"
    assert trade["exit_costs"] == {
        "commission_bps": 1.0,
        "spread_bps": 0.0,
        "slippage_bps": 0.0,
    }


def test_salida_stop_paga_spread_y_slippage_completos():
    bars = _bars(("2026-11-09 09:15", 100.0, 101.0, 98.5, 99.0))
    order = _order("buy", 100.0, 99.0, 102.0)
    trade = _run(bars, [order])["trades"][0]
    assert trade["exit_reason"] == "stop"
    assert trade["exit_costs"] == {
        "commission_bps": 1.0,
        "spread_bps": 10.0,
        "slippage_bps": 5.0,
    }


def test_salida_forzada_paga_spread_y_slippage_completos():
    bars = _bars(
        ("2026-11-09 09:15", 100.0, 100.2, 99.9, 100.1),
        ("2026-11-09 16:00", 100.1, 100.3, 100.0, 100.2),
    )
    order = _order(
        "buy",
        100.0,
        90.0,
        110.0,
        expires="2026-11-09 20:00",
    )
    trade = _run(
        bars,
        [order],
        force_exit_time=time(18, 0),
        session_offset_hours=2.0,
    )["trades"][0]
    assert trade["exit_reason"] == "force_exit"
    assert trade["exit_costs"] == {
        "commission_bps": 1.0,
        "spread_bps": 10.0,
        "slippage_bps": 5.0,
    }


def test_comision_por_lado_se_paga_siempre():
    bars = _bars(("2026-11-09 09:15", 100.0, 102.5, 99.9, 101.5))
    order = _order("buy", 100.0, 98.0, 102.0)
    trade = _run(bars, [order])["trades"][0]
    assert trade["entry_costs"]["commission_bps"] == 1.0
    assert trade["exit_costs"]["commission_bps"] == 1.0


# --------------------------------------------------------------- regla 5


def test_fill_pessimism_cero_permite_touch_estricto():
    bars = _bars(("2026-11-09 09:15", 100.0, 102.5, 99.99, 101.5))
    order = _order("buy", 100.0, 98.0, 102.0)
    result = _run(bars, [order], fill_pessimism_points=0)
    assert len(result["trades"]) == 1


def test_fill_pessimism_positivo_exige_superar_el_nivel_en_puntos():
    # point=0.01, X=2: el low debe quedar estrictamente por debajo de 99.98.
    exact = _bars(("2026-11-09 09:15", 100.0, 102.5, 99.98, 101.5))
    order = _order("buy", 100.0, 98.0, 102.0)
    assert _run(exact, [order], fill_pessimism_points=2)["trades"] == []

    beyond = _bars(("2026-11-09 09:15", 100.0, 102.5, 99.97, 101.5))
    trade = _run(beyond, [order], fill_pessimism_points=2)["trades"][0]
    assert trade["entry_price"] == pytest.approx(100.0)


# --------------------------------------------------------------- regla 6


def test_max_trades_per_day_por_defecto_uno():
    bars = _bars(
        ("2026-11-09 09:15", 100.0, 102.5, 99.9, 101.5),
        ("2026-11-09 10:15", 100.0, 102.0, 100.0, 101.0),
    )
    orders = [
        _order("buy", 100.0, 98.0, 102.0, expires="2026-11-09 09:15"),
        _order(
            "buy",
            100.5,
            98.0,
            102.0,
            created="2026-11-09 10:00",
            expires="2026-11-09 10:15",
        ),
    ]
    result = _run(bars, orders)
    assert len(result["trades"]) == 1
    assert result["ignored"] >= 1


# --------------------------------------------------------------- regla 7


def test_force_exit_time_usa_offset_semanal_de_sesion():
    bars = _bars(
        ("2026-11-09 09:15", 100.0, 100.2, 99.9, 100.1),
        ("2026-11-09 15:00", 100.1, 100.3, 100.0, 100.2),
    )
    order = _order(
        "buy",
        100.0,
        90.0,
        110.0,
        expires="2026-11-09 20:00",
    )
    trade = _run(
        bars,
        [order],
        force_exit_time=time(18, 0),
        session_offset_hours=3.0,
    )["trades"][0]
    assert trade["exit_reason"] == "force_exit"
    assert trade["exit_time"] == pd.Timestamp("2026-11-09 15:00", tz="UTC")


# --------------------------------------------------------------- regla 8


def test_limitada_no_ejecutada_expira_y_no_pasa_al_dia_siguiente():
    bars = _bars(
        ("2026-11-09 09:15", 100.0, 100.2, 100.05, 100.1),
        ("2026-11-10 09:15", 99.0, 100.5, 99.0, 100.0),
    )
    order = _order(
        "buy",
        100.0,
        98.0,
        102.0,
        created="2026-11-09 09:00",
        expires="2026-11-09 16:00",
    )
    result = _run(bars, [order])
    assert result["trades"] == []
    assert result["expired"] == 1


def test_sesion_bloquea_barra_fuera_de_horario():
    bars = _bars(("2026-11-09 08:00", 100.0, 101.0, 99.0, 100.5))
    order = _order(
        "buy",
        100.0,
        95.0,
        110.0,
        created="2026-11-09 07:00",
        expires="2026-11-09 10:00",
    )
    result = _run(
        bars,
        [order],
        session_window=(time(9, 0), time(17, 0)),
        session_tz="UTC",
        asset_class="cfd",
    )
    assert result["trades"] == []
    assert result["session_skipped"] == 1


def test_sesion_bloquea_rollover():
    bars = _bars(("2026-11-09 21:00", 100.0, 101.0, 99.0, 100.5))
    order = _order(
        "buy",
        100.0,
        95.0,
        110.0,
        created="2026-11-09 20:00",
        expires="2026-11-09 22:00",
    )
    rules = PropRules(
        rollover_utc="21:00",
        rollover_blackout_min=15,
        weekend_holding=True,
    )
    result = _run(
        bars,
        [order],
        session_window=(time(0, 0), time(0, 0)),
        session_tz="UTC",
        asset_class="cfd",
        session_rules=rules,
    )
    assert result["trades"] == []
    assert result["session_skipped"] == 1


def test_sesion_bloquea_viernes_tras_corte():
    bars = _bars(("2026-11-13 20:00", 100.0, 101.0, 99.0, 100.5))
    order = _order(
        "buy",
        100.0,
        95.0,
        110.0,
        created="2026-11-13 19:00",
        expires="2026-11-13 21:00",
    )
    rules = PropRules(
        weekend_holding=False,
        friday_cutoff_hour=20,
        reset_tz="Europe/Prague",
    )
    result = _run(
        bars,
        [order],
        session_window=(time(0, 0), time(0, 0)),
        session_tz="UTC",
        asset_class="cfd",
        session_rules=rules,
    )
    assert result["trades"] == []
    assert result["session_skipped"] == 1


def test_sesion_sin_datos_reporta_error():
    bars = _bars(("2026-11-09 09:15", 100.0, 101.0, 99.0, 100.5))
    order = _order("buy", 100.0, 95.0, 110.0)
    result = _run(
        bars,
        [order],
        session_window=None,
        symbol="DESCONOCIDO",
    )
    assert result["trades"] == []
    assert "sin datos de sesión" in result["session_error"]


def test_sesion_infiere_24_5_del_simbolo():
    bars = _bars(
        ("2026-11-09 09:15", 100.0, 101.0, 99.0, 100.5),
        ("2026-11-09 09:30", 120.0, 125.0, 119.0, 121.0),
    )
    order = _order("buy", 100.0, 95.0, 110.0, expires="2026-11-09 10:00")
    result = _run(
        bars,
        [order],
        session_window=None,
        symbol="EURUSD",
    )
    assert len(result["trades"]) == 1
    assert result["session_error"] is None


def test_reconciliacion_eventos_no_supera_serie_con_entrada_mercado():
    """Control de calidad de la fase de ejecución.

    Se simula la MISMA señal en los dos modos: largo en 09:00 y salida/stop en
    09:15. En el modo de eventos la entrada se fuerza a MERCADO (``type``
    ``market``), que paga spread y slippage completos. El modo de eventos NUNCA
    debe dar un retorno neto mayor que la serie de posición; si lo hace, el
    motor tiene sesgo optimista y este test debe fallar.
    """
    from tradinglab.intraday import backtest_intraday

    bars = _bars(
        ("2026-11-09 09:00", 100.0, 100.5, 99.5, 100.0),
        ("2026-11-09 09:15", 100.0, 100.2, 98.5, 99.0),
        ("2026-11-09 09:30", 99.0, 99.5, 98.8, 99.0),
    )
    target = pd.Series([1.0, 0.0, 0.0], index=bars.index)
    order = {**_order("buy", 100.0, 99.0, 110.0), "type": "market"}
    result = _run(bars, [order])
    assert len(result["trades"]) == 1
    trade = result["trades"][0]
    assert trade["entry_price"] == pytest.approx(100.0)
    assert trade["exit_reason"] == "stop"
    assert trade["entry_costs"] == {
        "commission_bps": 1.0,
        "spread_bps": 10.0,
        "slippage_bps": 5.0,
    }
    assert trade["exit_costs"] == {
        "commission_bps": 1.0,
        "spread_bps": 10.0,
        "slippage_bps": 5.0,
    }

    gross = trade["exit_price"] / trade["entry_price"] - 1.0
    event_cost = (
        sum(trade["entry_costs"].values()) + sum(trade["exit_costs"].values())
    ) / 10_000.0
    event_net = gross - event_cost

    series = backtest_intraday(
        bars,
        target,
        timeframe="M15",
        commission_bps=1.0,
        slippage_bps=5.0,
        spread_override_bps=10.0,
        point=0.01,
    )
    series_net = float((1.0 + series["returns"]).prod() - 1.0)

    assert event_net <= series_net + 1e-12
