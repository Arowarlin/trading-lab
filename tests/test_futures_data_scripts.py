"""FUT-B1/B3: los scripts de datos funcionan sin red y sin datos reales (dobles de prueba)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cost_rows_only_metadata_and_errors_are_kept():
    cost = _load("futures_data_cost")
    calls = []

    def fake_get_json(client, endpoint, params):
        calls.append(endpoint)
        assert endpoint.startswith("metadata.")            # nunca timeseries
        if params["symbols"] == "MGC.v.0":
            raise RuntimeError("HTTP 422 símbolo")
        return {"metadata.get_record_count": 10, "metadata.get_billable_size": 2048, "metadata.get_cost": 1.5}[endpoint]

    def params(**kw):
        return {"symbols": kw["row_symbol"], **kw}

    rows = cost.cost_rows(None, fake_get_json, params)
    assert len(rows) == sum(len(r[1]) for r in cost.ROWS)
    assert set(calls) == {"metadata.get_record_count", "metadata.get_billable_size", "metadata.get_cost"}
    mgc = [r for r in rows if r["root"] == "MGC"]
    assert mgc and all(r["error"].startswith("Sin datos: ") and r["cost_usd"] is None for r in mgc)
    md = cost.to_markdown(rows)
    assert "No es una recomendación" in md and "ohlcv-1m (Research B (RB_spec §2))" in md


def test_manifest_on_synthetic_parquet(tmp_path, monkeypatch):
    man = _load("futures_manifest")
    data = tmp_path / "data"
    data.mkdir()
    pd.DataFrame({"ts_event": pd.date_range("2020-01-01", periods=3, freq="h", tz="UTC"),
                  "close": [1.0, 2.0, 3.0]}).to_parquet(data / "US500_H1.parquet")
    monkeypatch.setattr(man, "ROOT", tmp_path)
    row = man.describe(data / "US500_H1.parquet")
    assert (row["databento_root"], row["timeframe"], row["rows"], row["has_instrument_id"]) == ("ES", "H1", 3, False)
    assert row["first_utc"].startswith("2020-01-01T00:00")
    assert len(row["sha256"]) == 64
    assert json.dumps(row)


def test_manifest_accepts_data_outside_repo(tmp_path, monkeypatch):
    """FUT-B3: los parquet viven en otro worktree (E:\\trading-lab) y el script corre en E:\\tl-fut-s."""
    man = _load("futures_manifest")
    repo, other = tmp_path / "repo", tmp_path / "otro" / "data"
    repo.mkdir()
    other.mkdir(parents=True)
    pd.DataFrame({"ts_event": pd.date_range("2020-01-01", periods=2, freq="h", tz="UTC")}).to_parquet(
        other / "XAUUSD_M1.parquet")
    monkeypatch.setattr(man, "ROOT", repo)
    row = man.describe(other / "XAUUSD_M1.parquet")
    assert row["path"] == (other / "XAUUSD_M1.parquet").resolve().as_posix()
    assert (row["databento_root"], row["timeframe"], row["rows"]) == ("GC", "M1", 2)
    inside = repo / "data"
    inside.mkdir()
    pd.DataFrame({"ts_event": pd.date_range("2020-01-01", periods=1, freq="h", tz="UTC")}).to_parquet(
        inside / "US100_H1.parquet")
    assert man.describe(inside / "US100_H1.parquet")["path"] == "data/US100_H1.parquet"


def test_minimal_cost_plan_has_no_duplicated_trades_and_seals_oos2():
    """Plan mínimo: sin trades (tbbo ya los trae), y el OOS-2 de Research A en filas propias."""
    cost = _load("futures_data_cost")
    assert all(schema != "trades" for schema, *_ in cost.ROWS_MIN)
    tbbo = [(roots, start, end) for schema, roots, start, end, _ in cost.ROWS_MIN if schema == "tbbo"]
    assert tbbo == [(("NQ", "MNQ"), "2019-05-06", "2024-01-01"), (("NQ", "MNQ"), "2024-01-01", "2026-11-27")]
    rows = cost.cost_rows(None, lambda c, e, p: 1, lambda **kw: {"symbols": kw["row_symbol"]}, rows=cost.ROWS_MIN)
    assert len(rows) == sum(len(r[1]) for r in cost.ROWS_MIN) == 12
    assert set(cost.PLANS) == {"amplio", "minimo"}


def test_download_script_normalizes_and_summarizes(tmp_path, monkeypatch):
    """OP-4: el script une los trozos M1 por raíz y resume filas y rangos (sin red: los trozos ya están)."""
    zstandard = __import__("pytest").importorskip("zstandard")
    from tradinglab.futures import data_download as dd
    script = _load("futures_data_download")
    monkeypatch.setitem(dd.PACKAGES, "rb", (("ohlcv-1m", ("ES",), "2019-03-01", "2020-06-01"),))
    csv = ("ts_event,rtype,publisher_id,instrument_id,open,high,low,close,volume\n"
           "{d}T14:30:00Z,33,1,{iid},10.0,11.0,9.0,10.5,5\n")
    folder = tmp_path / "raw" / "databento" / "GLBX.MDP3" / "ohlcv-1m" / "ES"
    folder.mkdir(parents=True)
    for name, d, iid in (("a", "2019-03-01", 1), ("b", "2020-01-02", 2)):
        (folder / f"{name}.csv.zst").write_bytes(zstandard.ZstdCompressor().compress(
            csv.format(d=d, iid=iid).encode("utf-8")))
    written = script.normalize_package("rb", tmp_path)
    md = script.summary_md("rb", {"quoted_usd": 0.5, "max_usd": 45.0, "jobs": 2}, written)
    assert "0.50 USD" in md and "| ES | 2 | 2019-03-01T14:30:00+00:00 | 2020-01-02T14:30:00+00:00 | 2 |" in md
    assert "ningún desenlace" in md
