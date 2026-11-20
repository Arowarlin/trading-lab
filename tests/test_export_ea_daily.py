"""El exportador del EA no toca bases de datos y agrega R por día."""

from __future__ import annotations

import ast
import importlib.util

import pandas as pd

from tradinglab.config import ROOT

SCRIPT = ROOT / "scripts" / "export_ea_daily.py"


def test_export_ea_no_escribe_bases_de_datos() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)

    assert "sqlite3" not in modules
    assert not any(name.startswith("tradinglab.db") for name in modules)
    assert not any(name.startswith("tradinglab.learning") for name in modules)
    for forbidden in ("record_trial", "lab.db", "sqlite3", "connect("):
        assert forbidden not in source


def test_export_ea_daily_agrega_por_fecha_de_salida() -> None:
    spec = importlib.util.spec_from_file_location("export_ea_daily", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    trades = pd.DataFrame(
        {
            "t_exit": pd.to_datetime(
                ["2024-01-02 10:00", "2024-01-02 15:00", "2024-01-03 11:00"]
            ),
            "r": [1.0, -0.5, 2.0],
        }
    )
    daily = module.daily_r_from_trades(trades)

    assert list(daily.index) == list(
        pd.to_datetime(["2024-01-02", "2024-01-03"])
    )
    assert daily.tolist() == [0.5, 2.0]
    assert daily.name == "r"

    empty = module.daily_r_from_trades(pd.DataFrame())
    assert empty.empty
