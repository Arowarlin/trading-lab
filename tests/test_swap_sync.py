from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from tradinglab.carry import CostModel
from tradinglab.intraday_costs import asset_costs
from tradinglab.swap_sync import (
    build_swap_payload,
    convert_symbol,
    render_swap_block,
    sync_swaps,
    update_costs_yaml,
)

READ_AT = "2026-11-15T12:00:00+00:00"


def _info(mode: int, long: float, short: float, triple: int = 3) -> dict:
    return {
        "swap_mode": mode,
        "swap_long": long,
        "swap_short": short,
        "swap_rollover3days": triple,
    }


def test_convert_symbol_respeta_swap_mode():
    points = convert_symbol("AAA", _info(1, -12.5, 8.0), READ_AT)
    assert points["status"] == "ok"
    assert points["unit"] == "points"
    assert points["long"] == -12.5
    assert points["triple_swap_weekday"] == 2

    interest = convert_symbol("BBB", _info(5, -2.5, -1.25), READ_AT)
    assert interest["status"] == "ok"
    assert interest["unit"] == "percent_annual"

    unsupported = convert_symbol("CCC", _info(2, -1.0, 1.0), READ_AT)
    assert unsupported["status"] == "no_soportado"
    assert unsupported["swap_mode"] == 2


def test_referencia_us100_triple_viernes_y_puntos():
    converted = convert_symbol(
        "US100.CASH", _info(1, -676.55, 1.75, triple=5), READ_AT
    )
    assert converted["status"] == "ok"
    assert converted["unit"] == "points"
    assert converted["long"] == -676.55
    assert converted["short"] == 1.75
    assert converted["triple_swap_weekday"] == 4  # viernes
    model = CostModel(
        swap_long=converted["long"],
        swap_short=converted["short"],
        swap_unit=converted["unit"],
        triple_weekday=converted["triple_swap_weekday"],
        point=0.01,
        contract_size=1.0,
    )
    assert model.daily_cash(
        "long", notional=0.0, shares=1.0, day=date(2026, 11, 12)
    ) == pytest.approx(-6.7655)


def test_comisiones_del_catalogo_coinciden_con_la_especificacion():
    eur = asset_costs("EURUSD")
    assert eur.commission_per_lot_usd == pytest.approx(2.50)
    assert eur.commission_side == "per_side"
    xau = asset_costs("XAUUSD")
    assert xau.commission_percent_per_side == pytest.approx(0.0007)
    assert xau.commission_side == "per_side"
    us100 = asset_costs("US100.CASH")
    assert us100.commission_type == "zero"


def test_swap_sync_guarda_tasa_anual_y_precio_de_lectura():
    info = _info(1, -676.55, 1.75, triple=5)
    info.update(
        {"point": 0.01, "trade_contract_size": 1.0, "bid": 27_945.73}
    )
    converted = convert_symbol("US100.CASH", info, READ_AT)
    assert converted["price_at_read"] == pytest.approx(27_945.73)
    assert converted["swap_annual_pct_long"] == pytest.approx(-8.8364, abs=0.001)
    assert converted["swap_annual_pct_short"] == pytest.approx(0.0229, abs=0.001)


def test_resuelve_us100_cash_case_insensitive_y_guarda_canonico():
    names = [
        SimpleNamespace(name="EURUSD"),
        SimpleNamespace(name="US100.cash"),
    ]
    infos = {
        "US100.cash": _info(1, -676.55, 1.75, triple=5),
    }
    payload = build_swap_payload(
        ["US100.CASH"],
        infos.get,
        symbols_getter=lambda: names,
        read_at=READ_AT,
    )
    assert payload["n_read"] == 1
    item = payload["symbols"]["US100.CASH"]
    assert item["broker_symbol"] == "US100.cash"
    assert item["long"] == -676.55
    assert item["triple_swap_weekday"] == 4
    assert item["triple_name"] == "viernes"
    block = yaml.safe_load(render_swap_block(payload))
    assert block["swap"]["assets"]["US100.CASH"]["triple_swap_weekday"] == 4
    assert "US100.cash" not in block["swap"]["assets"]


def test_symbols_get_sin_coincidencia_o_ambigua_es_sin_datos():
    info = _info(1, -1.0, 1.0)
    none = build_swap_payload(
        ["US100.CASH"],
        lambda symbol: info,
        symbols_getter=lambda: [SimpleNamespace(name="EURUSD")],
        read_at=READ_AT,
    )
    assert none["n_read"] == 0
    assert "sin coincidencia" in none["skipped"]["US100.CASH"]["reason"]

    ambiguous = build_swap_payload(
        ["US100.CASH"],
        lambda symbol: info,
        symbols_getter=lambda: [
            SimpleNamespace(name="US100.cash"),
            SimpleNamespace(name="us100.CASH"),
        ],
        read_at=READ_AT,
    )
    assert ambiguous["n_read"] == 0
    assert "ambigua" in ambiguous["skipped"]["US100.CASH"]["reason"]


def test_build_payload_y_bloque_yaml():
    infos = {
        "AAA": _info(1, -12.5, 8.0),
        "BBB": _info(5, -2.5, -1.25),
        "CCC": _info(2, -1.0, 1.0),
        "DDD": None,
    }
    payload = build_swap_payload(
        list(infos), lambda symbol: infos[symbol], read_at=READ_AT
    )
    assert payload["n_read"] == 2
    assert payload["n_skipped"] == 2
    assert set(payload["symbols"]) == {"AAA", "BBB"}
    block = yaml.safe_load(render_swap_block(payload))
    assert block["swap"]["synced_at"] == READ_AT
    assert block["swap"]["assets"]["AAA"]["unit"] == "points"
    assert block["swap"]["assets"]["BBB"]["unit"] == "percent_annual"
    assert "CCC" not in block["swap"]["assets"]


def test_update_costs_yaml_solo_cambia_el_bloque_swap(tmp_path: Path):
    path = tmp_path / "costs.yaml"
    path.write_text(
        "# comentario de cabecera\n"
        "assets:\n"
        "  AAA:\n"
        "    verified: true\n"
        "swap:\n"
        "  unit: percent_annual\n"
        "  defaults:\n"
        "    long: null\n"
        "    short: null\n"
        "slippage:\n"
        "  optimistic_bps: 0.5\n",
        encoding="utf-8",
    )
    payload = build_swap_payload(
        ["AAA"], lambda symbol: _info(1, -12.5, 8.0), read_at=READ_AT
    )
    update_costs_yaml(path, render_swap_block(payload))
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# comentario de cabecera")
    assert "slippage:\n  optimistic_bps: 0.5" in text
    data = yaml.safe_load(text)
    assert data["swap"]["assets"]["AAA"]["long"] == -12.5
    assert data["assets"]["AAA"]["verified"] is True


def test_sync_swaps_dry_run_no_escribe_y_write_es_selectivo(tmp_path: Path):
    path = tmp_path / "costs.yaml"
    original = (
        "assets:\n"
        "  AAA: {}\n"
        "  CCC: {}\n"
        "swap:\n"
        "  unit: percent_annual\n"
        "slippage:\n"
        "  optimistic_bps: 0.5\n"
    )
    path.write_text(original, encoding="utf-8")
    infos = {"AAA": _info(1, -12.5, 8.0), "CCC": _info(2, -1.0, 1.0)}

    def getter(symbol):
        return infos[symbol]

    dry = sync_swaps(costs_path=path, info_getter=getter)
    assert dry["written"] is False
    assert path.read_text(encoding="utf-8") == original

    written = sync_swaps(costs_path=path, info_getter=getter, write=True)
    assert written["written"] is True
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert "AAA" in data["swap"]["assets"]
    assert "CCC" not in data["swap"]["assets"]
    assert "CCC" in data["assets"]
