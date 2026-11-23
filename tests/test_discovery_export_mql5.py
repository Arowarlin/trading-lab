"""F12a: exportador MQL5 determinista, cobertura de bloques y trazas."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

import pytest
import yaml

from tradinglab.discovery import databank
from tradinglab.discovery.blocks import BLOCKS
from tradinglab.discovery.export_mql5 import (
    ExportError,
    block_coverage,
    export_spec,
    export_strategy,
    export_strategy_id,
    magic_number,
    trace_csv,
    trace_signals,
)
from tradinglab.discovery.export_samples import (
    SYNTHETIC_STRATEGIES,
    build_samples,
    synthetic_bars,
)

FIXTURES = Path(__file__).parent / "fixtures" / "f12_export"
GENERATED = FIXTURES / "generated"


def _strategy(name: str = "synthetic_trend") -> dict:
    return copy.deepcopy(SYNTHETIC_STRATEGIES[name])


def _assert_mql5_sane(source: str) -> None:
    assert source.count("{") == source.count("}")
    assert "WEEKDAY_TEST" not in source
    assert "None" not in source
    definitions = set(re.findall(r"\b(?:double|bool)\s+([VB]_[0-9a-f]{12})\s*\(", source))
    calls = set(re.findall(r"\b([VB]_[0-9a-f]{12})\s*\(", source))
    assert calls <= definitions, f"llamadas sin definicion: {sorted(calls - definitions)}"
    for name in BLOCKS:
        assert f"{name}(shift" not in source, f"llamada cruda al bloque {name}"
    for helper in ("PrevSessionLevelAt", "PrevDayLevelAt", "OpeningRangeAt", "DonchianLevelAt"):
        assert f"double {helper}(" in source
        assert f"bool {helper}(" not in source
    for struct_name in ("EmaState", "AdxState"):
        declaration = source.find(f"{struct_name} g_")
        if declaration >= 0:
            assert source.find(f"struct {struct_name}") < declaration



def test_export_is_deterministic(tmp_path: Path) -> None:
    first = export_strategy(_strategy(), account_id="CFD-001", out_dir=tmp_path / "a")
    second = export_strategy(_strategy(), account_id="CFD-001", out_dir=tmp_path / "b")
    assert first.mq5_path.name == second.mq5_path.name
    assert first.mq5_path.read_bytes() == second.mq5_path.read_bytes()
    assert first.sha256 == second.sha256
    assert first.magic == second.magic


def test_manifest_hash_and_no_absolute_paths(tmp_path: Path) -> None:
    result = export_strategy(
        _strategy(),
        account_id="CFD-001",
        out_dir=tmp_path,
        template="ny_open_vol_filter",
    )
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    digest = hashlib.sha256(result.mq5_path.read_bytes()).hexdigest()
    assert manifest["sha256"] == digest == result.sha256
    assert manifest["file"] == result.mq5_path.name
    assert manifest["magic"] == result.magic
    assert manifest["strategy_hash"] == result.strategy_hash
    assert manifest["template"]["name"] == "ny_open_vol_filter"
    assert manifest["template"]["version"]
    assert manifest["template"]["sha256"]
    source = result.mq5_path.read_text(encoding="utf-8")
    assert str(tmp_path) not in source
    assert "timestamp" not in manifest


def test_golden_samples_and_traces(tmp_path: Path) -> None:
    results = build_samples(tmp_path)
    assert set(results) == set(SYNTHETIC_STRATEGIES)
    for name, result in results.items():
        expected_mq5 = GENERATED / f"{name}.mq5"
        expected_trace = GENERATED / f"{name}.trace.csv"
        expected_manifest = GENERATED / f"{name}.manifest.json"
        assert expected_mq5.exists(), f"falta el golden {expected_mq5}"
        assert result.mq5_path.read_bytes() == expected_mq5.read_bytes()
        _assert_mql5_sane(result.mq5_path.read_text(encoding="utf-8"))
        assert result.trace_path is not None
        assert result.trace_path.read_bytes() == expected_trace.read_bytes()
        assert result.manifest_path.read_bytes() == expected_manifest.read_bytes()
        assert result.trace_path.read_text(encoding="utf-8").startswith("bar_time,side,entry,stop,target\n")


def test_unsupported_block_fails_loudly(tmp_path: Path) -> None:
    strategy = _strategy()
    strategy["long_entry"] = {
        "kind": "gt",
        "left": {"kind": "indicator", "ind": "vwap_distance", "n": 14},
        "right": {"kind": "const", "value": 0.0},
    }
    strategy["short_entry"] = None
    with pytest.raises(ExportError, match="bloque vwap_distance no exportable"):
        export_strategy(strategy, account_id="CFD-001", out_dir=tmp_path)


def test_htf_fails_loudly(tmp_path: Path) -> None:
    strategy = _strategy()
    strategy["long_entry"] = {
        "kind": "htf",
        "tf": "M15",
        "expr": {
            "kind": "gt",
            "left": {"kind": "price", "price": "close"},
            "right": {"kind": "const", "value": 1.0},
        },
    }
    strategy["short_entry"] = None
    with pytest.raises(ExportError, match="nodo htf no exportable"):
        export_strategy(strategy, account_id="CFD-001", out_dir=tmp_path)


def test_non_new_york_session_fails_loudly(tmp_path: Path) -> None:
    strategy = _strategy()
    strategy["instrument"] = "EURUSD"
    with pytest.raises(ExportError, match="huso Europe/London no exportable"):
        export_strategy(strategy, account_id="CFD-001", out_dir=tmp_path)


def test_market_mismatch_fails_loudly(tmp_path: Path) -> None:
    strategy = _strategy()
    strategy["market"] = "futures"
    with pytest.raises(ExportError, match="CFD-001 es cfd"):
        export_strategy(strategy, account_id="CFD-001", out_dir=tmp_path)


def test_firm_risk_governs_sizing(tmp_path: Path) -> None:
    strategy = _strategy()
    strategy["sizing"] = {"risk_per_trade_r": 2.0}
    result = export_strategy(strategy, account_id="CFD-001", out_dir=tmp_path)
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["risk"]["per_trade_risk_pct"] == 0.5


def test_missing_firm_limits_fail_loudly(tmp_path: Path) -> None:
    with pytest.raises(ExportError, match="Sin datos: CFD-003 no declara perdida diaria"):
        export_strategy(_strategy(), account_id="CFD-003", out_dir=tmp_path)


def test_magic_is_stable_and_bounded() -> None:
    digest = "a" * 64
    magic = magic_number(digest)
    assert magic == magic_number(digest)
    assert 100_000_000 <= magic <= 999_999_999
    assert magic == int(digest[:8], 16) % 900_000_000 + 100_000_000
    with pytest.raises(ExportError):
        magic_number("abc")


def test_block_coverage_covers_every_block() -> None:
    coverage = block_coverage()
    assert set(coverage) == set(BLOCKS)
    for name, (supported, reason) in coverage.items():
        if supported:
            assert reason == ""
        else:
            assert reason, f"{name} no exportable sin motivo"


def _default_params(name: str) -> dict[str, float | int]:
    spec = BLOCKS[name]
    values: dict[str, float | int] = {}
    for param_name, param in spec.params.items():
        values[param_name] = int(param.default) if param.integer else float(param.default)
    return values


@pytest.mark.parametrize(
    "name",
    [name for name, (supported, _reason) in block_coverage().items() if supported],
)
def test_every_supported_block_generates_mql5(name: str, tmp_path: Path) -> None:
    params = _default_params(name)
    spec = BLOCKS[name]
    node: dict = {"kind": "indicator" if spec.output == "float" else "pattern", "params": params}
    if spec.output == "float":
        node["ind"] = name
        condition = {
            "kind": "gt",
            "left": node,
            "right": {"kind": "const", "value": 0.0},
        }
    else:
        if name in {"trending", "ranging", "vol_high", "vol_low"}:
            node = {"kind": "regime", "regime": name, "params": params}
        else:
            node = {"kind": "pattern", "pattern": name, "params": params}
        condition = node
    strategy = _strategy()
    strategy["long_entry"] = condition
    strategy["short_entry"] = None
    result = export_strategy(strategy, account_id="CFD-001", out_dir=tmp_path)
    source = result.mq5_path.read_text(encoding="utf-8")
    assert "LongSignal" in source
    assert name in result.blocks or f"level:{name}" in result.blocks
    assert f"{name}(shift" not in source
    _assert_mql5_sane(source)


_NODE_CASES: list[dict] = [
    {"kind": "gt", "left": {"kind": "price", "price": "close"}, "right": {"kind": "const", "value": 1.0}},
    {"kind": "between", "left": {"kind": "price", "price": "close"}, "low": 1.0, "high": 1_000_000.0},
    {
        "kind": "cross_up",
        "left": {"kind": "price", "price": "close"},
        "right": {"kind": "const", "value": 1.0},
    },
    {
        "kind": "cross_down",
        "left": {"kind": "price", "price": "close"},
        "right": {"kind": "const", "value": 1.0},
    },
    {"kind": "time_between", "start": "10:00", "end": "11:00"},
    {"kind": "weekday_in", "days": ["mon", "wed"]},
    {
        "kind": "held_for",
        "n": 2,
        "args": [
            {
                "kind": "gt",
                "left": {"kind": "price", "price": "close"},
                "right": {"kind": "const", "value": 1.0},
            }
        ],
    },
    {
        "kind": "within_bars",
        "n": 2,
        "args": [
            {
                "kind": "lt",
                "left": {"kind": "price", "price": "close"},
                "right": {"kind": "const", "value": 1.0},
            }
        ],
    },
    {
        "kind": "not",
        "args": [
            {
                "kind": "gt",
                "left": {"kind": "price", "price": "close"},
                "right": {"kind": "const", "value": 1.0},
            }
        ],
    },
] + [
    {
        "kind": "gt",
        "left": {"kind": "price", "price": "close"},
        "right": {"kind": "level", "level": level, **({"n": 20} if level.startswith("donchian") else {})},
    }
    for level in (
        "prev_session_high",
        "prev_session_low",
        "opening_range_high",
        "opening_range_low",
        "prev_day_high",
        "prev_day_low",
        "donchian_high",
        "donchian_low",
    )
]


@pytest.mark.parametrize("entry", _NODE_CASES)
def test_every_node_kind_generates_mql5(entry: dict, tmp_path: Path) -> None:
    strategy = _strategy()
    strategy["long_entry"] = entry
    strategy["short_entry"] = None
    result = export_strategy(strategy, account_id="CFD-001", out_dir=tmp_path)
    assert result.mq5_path.exists()




def test_trace_is_deterministic_and_uses_fastbt() -> None:
    strategy = _strategy("synthetic_reversion")
    bars = synthetic_bars()
    rows = trace_signals(strategy, bars)
    assert rows
    assert {row.side for row in rows} <= {"long", "short"}
    first = trace_csv(strategy, bars)
    second = trace_csv(strategy, bars)
    assert first == second
    lines = first.strip().splitlines()
    assert lines[0] == "bar_time,side,entry,stop,target"
    assert len(lines) == len(rows) + 1


def test_export_from_spec(tmp_path: Path) -> None:
    path = tmp_path / "spec.yaml"
    path.write_text(
        yaml.safe_dump(
            {"strategy": _strategy(), "account": "CFD-001", "template": None},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    result = export_spec(path, out_dir=tmp_path / "out")
    assert result.mq5_path.exists()
    assert result.account == "CFD-001"


def test_cli_export_mql5(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from tradinglab.cli import app

    path = tmp_path / "spec.yaml"
    path.write_text(
        yaml.safe_dump({"strategy": _strategy(), "account": "CFD-001"}, sort_keys=False),
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        app,
        ["discovery", "export-mql5", "--spec", str(path), "--out", str(tmp_path / "out")],
    )
    assert result.exit_code == 0, result.stdout
    assert list((tmp_path / "out").glob("*.mq5"))


def test_export_from_strategy_id(tmp_path: Path) -> None:
    database = tmp_path / "discovery.db"
    strategy_id = databank.add_strategy(
        "test:f12a",
        _strategy(),
        db_path=database,
    )
    result = export_strategy_id(
        strategy_id,
        out_dir=tmp_path / "out",
        account_id="CFD-001",
        db_path=database,
    )
    assert result.mq5_path.exists()
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["strategy_hash"] == result.strategy_hash
    assert manifest["sha256"] == hashlib.sha256(result.mq5_path.read_bytes()).hexdigest()
    assert manifest["magic"] == result.magic
