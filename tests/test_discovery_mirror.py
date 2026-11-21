"""Espejo por tipo de bloque: signed, bounded, price y none."""

from __future__ import annotations

import pytest

from tradinglab.discovery import blocks, dsl, genetic, grid, mirror

SESSION = {
    "start": "09:30",
    "end": "15:55",
    "flat_at": "15:55",
    "or_minutes": 15,
}


def _strategy(long_entry: dict, short_entry: dict | None) -> dict:
    return {
        "dsl_version": "1",
        "instrument": "US100",
        "market": "cfd",
        "timeframe": "M5",
        "session": SESSION,
        "long_entry": long_entry,
        "short_entry": short_entry,
        "exit": {
            "stop": {"type": "atr", "mult": 2.0, "n": 14},
            "target": {"type": "rr", "rr": 2.0},
        },
        "limits": {"max_trades_per_day": 1, "cooldown_bars": 0},
    }


def _ind(name: str, **extra) -> dict:
    node = {"kind": "indicator", "ind": name, "n": 14, "params": {}}
    node.update(extra)
    return node


def _sr() -> dict:
    return {
        "kind": "indicator",
        "ind": "session_return",
        "params": {"start": 570, "end": 600},
    }


def test_todos_los_bloques_tienen_mirror_valido() -> None:
    assert len(blocks.BLOCKS) == 31
    for name, spec in blocks.BLOCKS.items():
        assert spec.mirror in {"signed", "bounded", "price", "none"}, name
        if spec.mirror == "bounded":
            assert spec.center is not None, name
        else:
            assert spec.center is None, name


@pytest.mark.parametrize(
    "name,center,value,expected",
    [
        ("rsi", 50.0, 70.0, 30.0),
        ("stochastic", 50.0, 80.0, 20.0),
        ("bollinger_pct", 0.5, 0.8, 0.2),
        ("donchian_pos", 0.5, 0.8, 0.2),
        ("keltner_pos", 0.5, 0.8, 0.2),
    ],
)
def test_bounded_refleja_el_centro(
    name: str, center: float, value: float, expected: float
) -> None:
    node = {
        "kind": "gt",
        "left": _ind(name),
        "right": {"kind": "const", "value": value},
    }
    reflected = mirror.mirror_expr(node)
    assert reflected["kind"] == "lt"
    assert reflected["right"]["value"] == pytest.approx(expected)
    assert blocks.BLOCKS[name].center == center


def test_signed_niega_la_constante() -> None:
    node = {
        "kind": "gt",
        "left": _sr(),
        "right": {"kind": "const", "value": 0.002},
    }
    reflected = mirror.mirror_expr(node)
    assert reflected["kind"] == "lt"
    assert reflected["right"]["value"] == pytest.approx(-0.002)


def test_between_signed_y_bounded_refleja_y_ordena() -> None:
    signed = {
        "kind": "between",
        "left": _sr(),
        "low": 0.001,
        "high": 0.003,
    }
    reflected = mirror.mirror_expr(signed)
    assert (reflected["low"], reflected["high"]) == pytest.approx((-0.003, -0.001))

    bounded = {
        "kind": "between",
        "left": _ind("rsi"),
        "low": 60.0,
        "high": 80.0,
    }
    reflected = mirror.mirror_expr(bounded)
    assert (reflected["low"], reflected["high"]) == pytest.approx((20.0, 40.0))


def test_cross_signed_y_bounded() -> None:
    signed = {
        "kind": "cross_up",
        "left": _sr(),
        "right": {"kind": "const", "value": 0.002},
    }
    reflected = mirror.mirror_expr(signed)
    assert reflected["kind"] == "cross_down"
    assert reflected["right"]["value"] == pytest.approx(-0.002)

    bounded = {
        "kind": "cross_up",
        "left": _ind("rsi"),
        "right": {"kind": "const", "value": 70.0},
    }
    reflected = mirror.mirror_expr(bounded)
    assert reflected["kind"] == "cross_down"
    assert reflected["right"]["value"] == pytest.approx(30.0)


def test_none_se_copia_igual() -> None:
    atr = {
        "kind": "gt",
        "left": _ind("atr"),
        "right": {"kind": "const", "value": 10.0},
    }
    assert mirror.mirror_expr(atr) == atr
    vol = {
        "kind": "regime",
        "regime": "vol_high",
        "n": 14,
        "lookback": 100,
        "params": {"pct": 0.8},
    }
    assert mirror.mirror_expr(vol) == vol


def test_vol_high_identico_en_largo_y_corto() -> None:
    long_entry = {
        "kind": "and",
        "args": [
            {
                "kind": "regime",
                "regime": "vol_high",
                "n": 14,
                "lookback": 100,
                "params": {"pct": 0.8},
            },
            {
                "kind": "gt",
                "left": {"kind": "price", "price": "close"},
                "right": {"kind": "level", "level": "opening_range_high"},
            },
        ],
    }
    short_entry = mirror.mirror_expr(long_entry)
    assert short_entry["args"][0] == long_entry["args"][0]
    assert short_entry["args"][1]["right"]["level"] == "opening_range_low"
    assert dsl.validate(_strategy(long_entry, short_entry)) == []


def test_precio_y_niveles_high_low() -> None:
    long_entry = {
        "kind": "gt",
        "left": {"kind": "price", "price": "close"},
        "right": {"kind": "level", "level": "opening_range_high"},
    }
    assert mirror.mirror_expr(long_entry) == {
        "kind": "lt",
        "left": {"kind": "price", "price": "close"},
        "right": {"kind": "level", "level": "opening_range_low"},
    }
    swing = {
        "kind": "gt",
        "left": {"kind": "price", "price": "close"},
        "right": _ind("swing_high"),
    }
    assert mirror.mirror_expr(swing)["right"]["ind"] == "swing_low"
    bos = {"kind": "pattern", "pattern": "bos_up", "left": 5, "right": 5}
    assert mirror.mirror_expr(bos)["pattern"] == "bos_down"


def test_validate_rechaza_signed_sin_negacion() -> None:
    long_entry = {
        "kind": "gt",
        "left": _sr(),
        "right": {"kind": "const", "value": 0.002},
    }
    bad_short = {
        "kind": "lt",
        "left": _sr(),
        "right": {"kind": "const", "value": 0.002},
    }
    errors = dsl.validate(_strategy(long_entry, bad_short))
    assert any("espejo" in error and "-0.002" in error for error in errors)

    good_short = mirror.mirror_expr(long_entry)
    assert dsl.validate(_strategy(long_entry, good_short)) == []


def test_validate_rechaza_vol_high_negado() -> None:
    vol = {
        "kind": "regime",
        "regime": "vol_high",
        "n": 14,
        "lookback": 100,
        "params": {"pct": 0.8},
    }
    bad_short = {"kind": "not", "args": [vol]}
    errors = dsl.validate(_strategy(vol, bad_short))
    assert any("espejo" in error for error in errors)
    assert dsl.validate(_strategy(vol, mirror.mirror_expr(vol))) == []


def test_validate_rechaza_nivel_de_precio_repetido() -> None:
    long_entry = {
        "kind": "gt",
        "left": {"kind": "price", "price": "close"},
        "right": {"kind": "level", "level": "opening_range_high"},
    }
    bad_short = {
        "kind": "lt",
        "left": {"kind": "price", "price": "close"},
        "right": {"kind": "level", "level": "opening_range_high"},
    }
    assert any("espejo" in error for error in dsl.validate(_strategy(long_entry, bad_short)))


def test_grid_v2_tiene_32_y_espejo_exacto() -> None:
    assert grid.grid_size("intraday_momentum_close_v2") == 32
    items = grid.grid_strategies(
        "intraday_momentum_close_v2",
        instrument="US100.CASH",
        timeframe="M5",
        session=SESSION,
    )
    assert len(items) == 32
    thresholds = set()
    short_thresholds = set()
    for item in items:
        assert dsl.validate(item) == []
        assert item["short_entry"] == genetic.mirror_expr(item["long_entry"])
        thresholds.add(item["long_entry"]["args"][0]["right"]["value"])
        short_thresholds.add(item["short_entry"]["args"][0]["right"]["value"])
    assert thresholds == {0.0, 0.001, 0.002, 0.003}
    assert short_thresholds == {0.0, -0.001, -0.002, -0.003}
