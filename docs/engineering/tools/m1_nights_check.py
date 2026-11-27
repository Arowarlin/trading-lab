"""Comprueba por qué H-2026-013 (legacy) pasó de 21 a 13 noches con el motor 0.3.0.

Solo lectura: ejecuta la misma prueba que ``test_h2026_013_cero_noches_con_no_overnight``
con el motor actual y con el de ``motor-eng1-pre`` (leído con ``git show``, cargado en
memoria; no escribe nada en ``src``) y lista las operaciones que cruzan el día en cada uno.

    .venv\\Scripts\\python.exe docs\\engineering\\tools\\m1_nights_check.py
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[3]
NY = "America/New_York"


def _old_fastbt():
    source = subprocess.run(
        ["git", "show", "motor-eng1-pre:src/tradinglab/discovery/fastbt.py"],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout
    folder = Path(tempfile.mkdtemp(prefix="m1_nights_"))
    path = folder / "fastbt_pre.py"
    path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("tradinglab.discovery._fastbt_pre", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run(engine, mode: str):
    from tradinglab.discovery import campaigns, compiler, dsl, genetic, jobs, snapshots, specs

    template = genetic.configured_template("h1_sma50_session_long", instrument="US100", timeframe="H1")
    template["session"]["flat_mode"] = mode
    model = dsl.Strategy.model_validate(template)
    frame = snapshots.closed_bars(campaigns._source_frame("US100", "H1", "dukascopy"), "H1")
    frame = frame[(frame.index >= pd.Timestamp("2019-01-02", tz="UTC")) & (frame.index <= pd.Timestamp("2023-12-31", tz="UTC"))]
    setup = jobs.QueueSetup(
        instrument="US100", timeframe="H1", account="CFD-001", firm="ftmo",
        cost_accounts=("CFD-001",), cost_mode="target", legacy_cost=True, session_tz=NY,
        session_start="09:00", session_end="10:00", flat_at="15:00", flat_mode=mode,
        weekdays=(0, 1, 2, 3, 4),
    )
    limits = specs.run_limits_from_strategy(model, setup, close_at_end=True)
    limits = engine.RunLimits(**{k: getattr(limits, k) for k in engine.RunLimits.__dataclass_fields__ if hasattr(limits, k)})
    zero = engine.cfd_costs_from_bps(commission_bps=0.0, slippage_bps=0.0, spread_bps=0.0)
    prepared = engine.prepare(frame, zero, atr_windows=(14,), sessions=(limits,))
    result = engine.run(
        compiler.compile(model, frame), frame, specs.exit_spec_from_strategy(model), zero,
        limits, prepared=prepared, collect_metrics=False,
    )
    nights = {
        trade.entry_time.tz_convert(NY).isoformat(): trade
        for trade in result.trades
        if trade.entry_time.tz_convert(NY).date() != trade.exit_time.tz_convert(NY).date()
    }
    return result.trades, nights


def main() -> int:
    sys.path.insert(0, str(REPO / "src"))
    from tradinglab.discovery import fastbt

    old = _old_fastbt()
    for mode in ("legacy", "no_overnight"):
        old_trades, old_nights = _run(old, mode)
        new_trades, new_nights = _run(fastbt, mode)
        print(f"\n== {mode}: antes {len(old_trades)} ops / {len(old_nights)} noches; "
              f"ahora {len(new_trades)} ops / {len(new_nights)} noches")
        new_by_entry = {t.entry_time.isoformat(): t for t in new_trades}
        for key, trade in sorted(old_nights.items()):
            if key in new_nights:
                continue
            now = new_by_entry.get(trade.entry_time.isoformat())
            before = f"{trade.exit_time.tz_convert(NY):%Y-%m-%d %H:%M} {trade.reason}"
            after = "Sin datos" if now is None else f"{now.exit_time.tz_convert(NY):%Y-%m-%d %H:%M} {now.reason}"
            print(f"  deja de dormir · entrada {key[:16]} · antes {before} · ahora {after}")
        for key in sorted(set(new_nights) - set(old_nights)):
            print(f"  NUEVA noche · entrada {key[:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
