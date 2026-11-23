"""Databento: estimación de coste, CSV sintético y tubería sin red."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from tradinglab.discovery import campaigns
from tradinglab.discovery import fetch_databento as db
from tradinglab.discovery.config import load_engine_config
from tradinglab.discovery.data_sources import DataSourceError, load_source
from tradinglab.discovery.source_quality import quality_config, quality_for_source

DATASET_RANGE = {
    "start": "2010-06-06T00:00:00.000000000Z",
    "end": "2026-11-23T00:00:00.000000000Z",
    "schema": {
        "ohlcv-1m": {
            "start": "2010-06-06T00:00:00.000000000Z",
            "end": "2026-11-23T00:00:00.000000000Z",
        },
        "ohlcv-1h": {
            "start": "2010-06-06T00:00:00.000000000Z",
            "end": "2026-11-23T00:00:00.000000000Z",
        },
    },
}

CSV_HEADER = (
    "ts_event,rtype,publisher_id,instrument_id,"
    "open,high,low,close,volume\n"
)
NQ_CSV = CSV_HEADER + (
    "2024-01-02T00:00:00.000000000Z,35,1,1,"
    "100.0,101.0,99.0,100.5,10\n"
    "2024-01-02T00:01:00.000000000Z,35,1,1,"
    "100.5,101.5,100.0,101.0,11\n"
)
J6_CSV = CSV_HEADER + (
    "2024-01-02T00:00:00.000000000Z,35,1,1,"
    "0.006800000,0.006900000,0.006700000,0.006850000,20\n"
)


class Response:
    def __init__(self, payload=None, *, status: int = 200, content: bytes = b"") -> None:
        self._payload = payload
        self.status_code = status
        self.content = content
        self.text = str(payload)

    def json(self):
        return self._payload


class FakeClient:
    """Simula metadata (GET) y timeseries (POST) sin tocar la red."""

    def __init__(self, *, cost: float = 0.5, records: int = 100, size: int = 1000) -> None:
        self.cost = cost
        self.records = records
        self.size = size
        self.gets: list[tuple[str, dict]] = []
        self.posts: list[dict] = []

    def get(self, url: str, params=None):
        endpoint = url.rsplit("/", 1)[-1]
        self.gets.append((endpoint, dict(params or {})))
        if endpoint == "metadata.get_dataset_range":
            return Response(DATASET_RANGE)
        if endpoint == "metadata.get_record_count":
            return Response(self.records)
        if endpoint == "metadata.get_billable_size":
            return Response(self.size)
        if endpoint == "metadata.get_cost":
            return Response(self.cost)
        return Response({"detail": "no"}, status=404)

    def post(self, url: str, data=None):
        values = dict(data or {})
        self.posts.append(values)
        symbol = values.get("symbols", "")
        if symbol.startswith("6J"):
            return Response(content=J6_CSV.encode("utf-8"))
        return Response(content=NQ_CSV.encode("utf-8"))


def test_mapeo_y_6j_invertido() -> None:
    assert db.normalize_symbol("NQ") == "NQ"
    assert db.normalize_symbol("US100") == "NQ"
    assert db.internal_symbol("6J") == "USDJPY"
    assert db.continuous_symbol("EURUSD", "v") == "6E.v.0"
    with pytest.raises(db.DatabentoError, match="no soportado"):
        db.normalize_symbol("BTC")

    frame = pd.DataFrame(
        {
            "open": [0.0068],
            "high": [0.0069],
            "low": [0.0067],
            "close": [0.00685],
            "volume": [3.0],
        }
    )
    out = db.invert_6j(frame)
    assert out["open"].iloc[0] == pytest.approx(1 / 0.0068)
    assert out["high"].iloc[0] == pytest.approx(1 / 0.0067)
    assert out["low"].iloc[0] == pytest.approx(1 / 0.0069)
    assert out["close"].iloc[0] == pytest.approx(1 / 0.00685)
    assert out["volume"].iloc[0] == pytest.approx(3.0)


def test_parse_csv_utc_y_columnas() -> None:
    frame = db.parse_csv(NQ_CSV.encode("utf-8"), root="NQ")
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert str(frame.index.tz) == "UTC"
    assert frame.index.name == "time"
    assert len(frame) == 2
    assert frame["close"].iloc[-1] == pytest.approx(101.0)


def test_parse_csv_6j_invierte_high_low() -> None:
    frame = db.parse_csv(J6_CSV.encode("utf-8"), root="6J")
    assert frame["open"].iloc[0] == pytest.approx(1 / 0.0068)
    assert frame["high"].iloc[0] == pytest.approx(1 / 0.0067)
    assert frame["low"].iloc[0] == pytest.approx(1 / 0.0069)
    assert frame["close"].iloc[0] == pytest.approx(1 / 0.00685)


def test_parse_csv_invalido() -> None:
    with pytest.raises(db.DatabentoError, match="vacía"):
        db.parse_csv(b"", root="NQ")
    bad = CSV_HEADER + "2024-01-02T00:00:00Z,35,1,1,100,99,101,100,1\n"
    with pytest.raises(db.DatabentoError, match="OHLC inválidas"):
        db.parse_csv(bad.encode("utf-8"), root="NQ")


def test_estimate_solo_metadata() -> None:
    client = FakeClient(cost=0.5, records=100, size=1000)
    estimate = db.estimate(
        ["NQ", "6J"],
        schema="ohlcv-1m",
        roll="v",
        client=client,
    )
    assert len(estimate.rows) == 2
    assert estimate.total_records == 200
    assert estimate.total_billable_bytes == 2000
    assert estimate.total_cost_usd == pytest.approx(1.0)
    assert all(row.continuous.endswith(".v.0") for row in estimate.rows)
    assert {call[0] for call in client.gets} == {
        "metadata.get_dataset_range",
        "metadata.get_record_count",
        "metadata.get_billable_size",
        "metadata.get_cost",
    }
    assert client.posts == []


def test_estimate_rango_por_schema() -> None:
    client = FakeClient()
    estimate = db.estimate(["NQ"], schema="ohlcv-1h", start="2024-01-01", end="2024-02-01", client=client)
    assert estimate.start == "2024-01-01"
    assert estimate.end == "2024-02-01"
    params = [params for endpoint, params in client.gets if endpoint == "metadata.get_cost"]
    assert params[0]["schema"] == "ohlcv-1h"
    assert params[0]["stype_in"] == "continuous"
    assert params[0]["symbols"] == "NQ.c.0"


def test_download_exige_coste_aprobado() -> None:
    client = FakeClient(cost=1.0)
    with pytest.raises(db.DatabentoError, match="coste no aprobado"):
        db.download(["NQ"], approved_cost=0.99, client=client)
    assert client.posts == []


def test_download_escribe_parquet_y_mapea(tmp_path) -> None:
    client = FakeClient(cost=0.5)
    result = db.download(
        ["NQ", "6J"],
        schema="ohlcv-1m",
        roll="c",
        approved_cost=1.0,
        root=tmp_path,
        client=client,
    )
    assert len(result["rows"]) == 2
    nq_path = tmp_path / "data" / "cache" / "databento" / "US100_M1.parquet"
    jpy_path = tmp_path / "data" / "cache" / "databento" / "USDJPY_M1.parquet"
    assert nq_path.exists() and jpy_path.exists()
    nq = db.load_cache("NQ", "ohlcv-1m", root=tmp_path)
    jpy = db.load_cache("6J", "ohlcv-1m", root=tmp_path)
    assert nq["close"].iloc[0] == pytest.approx(100.5)
    assert jpy["high"].iloc[0] == pytest.approx(1 / 0.0067)
    assert [post["schema"] for post in client.posts] == ["ohlcv-1m", "ohlcv-1m"]
    assert all(post["encoding"] == "csv" for post in client.posts)


def test_back_adjust_por_diferencia() -> None:
    index = pd.date_range("2024-01-02", periods=3, freq="min", tz="UTC")
    frame = pd.DataFrame(
        {
            "open": [100.0, 101.0, 110.0],
            "high": [101.0, 102.0, 111.0],
            "low": [99.0, 100.0, 109.0],
            "close": [100.0, 101.0, 110.0],
            "volume": [1.0, 1.0, 1.0],
        },
        index=index,
    )
    adjusted = db.back_adjust(frame, [(index[2], 9.0)])
    assert adjusted["close"].tolist() == pytest.approx([109.0, 110.0, 110.0])
    assert adjusted["high"].iloc[0] == pytest.approx(110.0)


def test_back_adjust_exige_tabla(tmp_path) -> None:
    client = FakeClient(cost=0.5)
    with pytest.raises(db.DatabentoError, match="roll-table"):
        db.download(
            ["NQ"],
            approved_cost=0.5,
            adjust="back",
            root=tmp_path,
            client=client,
        )
    assert client.posts == []


def test_data_source_databento_remuestrea(tmp_path) -> None:
    path = db.cache_path("US100", "ohlcv-1m", root=tmp_path)
    path.parent.mkdir(parents=True)
    index = pd.date_range("2024-01-02", periods=30, freq="min", tz="UTC")
    values = pd.Series(range(30), dtype=float) + 100.0
    pd.DataFrame(
        {
            "open": values.values,
            "high": values.values + 1.0,
            "low": values.values - 1.0,
            "close": values.values,
            "volume": 1.0,
        },
        index=index,
    ).to_parquet(path)

    loaded = load_source("US100", "M5", source="databento", root=tmp_path)
    assert loaded.source == "databento"
    assert loaded.derived_from == "M1"
    assert loaded.calendar == "cme"
    assert str(loaded.frame.index.tz) == "UTC"
    assert loaded.rows == 6


def test_data_source_databento_sin_cache(tmp_path) -> None:
    with pytest.raises(DataSourceError, match="Sin datos"):
        load_source("US100", "M5", source="databento", root=tmp_path)


def test_cli_por_defecto_solo_estima(monkeypatch) -> None:
    from typer.testing import CliRunner

    from tradinglab import cli

    row = db.CostRow(
        symbol="US100",
        root="NQ",
        continuous="NQ.c.0",
        schema="ohlcv-1m",
        roll="c",
        records=100,
        billable_bytes=1000,
        cost_usd=0.5,
    )
    estimate = db.CostEstimate(
        dataset=db.DATASET,
        schema="ohlcv-1m",
        roll="c",
        start="2010-06-06T00:00:00Z",
        end="2026-11-23T00:00:00Z",
        rows=(row,),
    )
    calls: list[int] = []

    def _estimar(*args, **kwargs):
        calls.append(1)
        return estimate

    def _no_descargar(*args, **kwargs):
        raise AssertionError("el CLI no debe descargar en modo estimación")

    monkeypatch.setattr(db, "estimate", _estimar)
    monkeypatch.setattr(db, "download", _no_descargar)
    result = CliRunner().invoke(
        cli.app, ["discovery", "fetch-databento", "--symbols", "NQ"]
    )
    assert result.exit_code == 0, result.output
    assert calls == [1]
    assert "no se ha descargado nada" in result.output


def test_cli_download_exige_aprobacion(monkeypatch) -> None:
    from typer.testing import CliRunner

    from tradinglab import cli

    def _falla(*args, **kwargs):
        raise db.DatabentoError("coste no aprobado: prueba")

    monkeypatch.setattr(db, "download", _falla)
    result = CliRunner().invoke(
        cli.app,
        [
            "discovery",
            "fetch-databento",
            "--symbols",
            "NQ",
            "--download",
            "--i-approve-cost",
            "0.01",
        ],
    )
    assert result.exit_code == 1
    assert "coste no aprobado" in result.output


def test_sesion_cme_declarada() -> None:
    config = load_engine_config().data_quality
    session = config.session_for("databento", "US100", date(2024, 1, 2))
    assert session is not None
    assert session.friday_close == "17:00"
    assert session.sunday_open == "18:00"
    assert session.pause_start == "17:00"
    assert session.pause_end == "18:00"
    assert (
        quality_config(config, "US100", "M5", "databento")
        .source_for("US100")
        .calendar
        == "cme"
    )


def test_derive_sessions_acepta_databento(monkeypatch) -> None:
    from types import SimpleNamespace

    from tradinglab.discovery import sessions

    index = pd.date_range("2024-01-02", "2024-03-28", freq="h", tz="UTC")
    local = index.tz_convert("America/New_York")
    index = index[(local.day_of_week < 5) & (local.hour >= 18) & (local.hour <= 22)]
    values = pd.Series(range(len(index)), dtype=float) + 100.0
    frame = pd.DataFrame(
        {
            "open": values.values,
            "high": values.values + 0.5,
            "low": values.values - 0.5,
            "close": values.values,
            "volume": 1.0,
        },
        index=index,
    )
    monkeypatch.setattr(
        sessions,
        "load_source",
        lambda *args, **kwargs: SimpleNamespace(frame=frame),
    )
    result = sessions.derive_sessions("US100", "databento", start_year=2024, end_year=2024)
    assert result["source"] == "databento"
    assert result["timeframe"] == "H1"
    assert "databento:US100" in sessions.yaml_block(result)


def test_usable_from_acepta_databento() -> None:
    from tradinglab.discovery.usability import compute_usable_from

    index = pd.date_range("2024-01-02", "2024-03-28", freq="5min", tz="UTC")
    local = index.tz_convert("America/New_York")
    index = index[(local.day_of_week < 5) & (local.hour != 17)]
    values = pd.Series(range(len(index)), dtype=float) + 100.0
    frame = pd.DataFrame(
        {
            "open": values.values,
            "high": values.values + 0.5,
            "low": values.values - 0.5,
            "close": values.values,
            "volume": 1.0,
        },
        index=index,
    )
    result = compute_usable_from("US100", "databento", "M5", frame=frame)
    assert result["key"] == "databento:US100:M5"
    assert result["source"] == "databento"
    assert result["symbol"] == "US100"
    assert result["status"] in {"ok", "warn", "fail"}


def test_data_check_acepta_databento(tmp_path) -> None:
    path = db.cache_path("US100", "ohlcv-1m", root=tmp_path)
    path.parent.mkdir(parents=True)
    index = pd.date_range("2024-01-02", periods=120, freq="min", tz="UTC")
    values = pd.Series(range(120), dtype=float) + 100.0
    pd.DataFrame(
        {
            "open": values.values,
            "high": values.values + 0.5,
            "low": values.values - 0.5,
            "close": values.values,
            "volume": 1.0,
        },
        index=index,
    ).to_parquet(path)
    data = quality_for_source("US100", "M1", source="databento", root=tmp_path)
    assert data["source_name"] == "databento"
    assert data["calendar"]["name"] == "cme"
    assert data["status"] in {"ok", "warn", "fail"}

def _tom_spec(confirm: bool) -> str:
    flag = "confirmation_only: true\n" if confirm else ""
    return (
        f"{flag}"
        "campaign_id: test-tom-confirm\n"
        "instrument: US100\n"
        "timeframe: D1\n"
        "template: turn_of_month\n"
        "profile: small\n"
        "mode: grid\n"
        "seed: 1\n"
        "data_source: databento\n"
        "account: CFD-001\n"
        "firm: ftmo\n"
        "cost_mode: best\n"
        "cost_accounts: [CFD-001, CFD-006]\n"
        "segments:\n"
        '  is: ["2010-06-06", "2024-06-30"]\n'
        '  oos1: ["2024-07-01", "2025-06-30"]\n'
        '  oos2: ["2025-07-01", null]\n'
        "grid:\n"
        "  dimensions:\n"
        "    - {name: n, kind: path, path: long_entry.n, values: [1, 2]}\n"
        "    - {name: m, kind: path, path: long_entry.m, values: [2, 3]}\n"
    )


def test_spec_confirmacion_permite_databento_d1(tmp_path) -> None:
    from tradinglab.discovery.spec import load_spec

    path = tmp_path / "tom-confirm.yaml"
    path.write_text(_tom_spec(True), encoding="utf-8")
    campaign = load_spec(path)
    assert campaign["confirmation_only"] is True
    assert campaign["config"]["confirmation_only"] is True
    assert campaign["config"]["data_source"] == "databento"
    assert campaign["timeframe"] == "D1"


def test_spec_sin_confirmacion_rechaza_databento_d1(tmp_path) -> None:
    from tradinglab.discovery.spec import SpecError, load_spec

    path = tmp_path / "tom-normal.yaml"
    path.write_text(_tom_spec(False), encoding="utf-8")
    with pytest.raises(SpecError, match="D1 exige datos de Dukascopy"):
        load_spec(path)


def test_register_sigue_bloqueando_databento_d1(tmp_path) -> None:
    frame = pd.DataFrame(
        {
            "open": [100.0] * 30,
            "high": [101.0] * 30,
            "low": [99.0] * 30,
            "close": [100.0] * 30,
        },
        index=pd.date_range("2024-01-02", periods=30, freq="D", tz="UTC"),
    )
    with pytest.raises(campaigns.CampaignError, match="D1 exige datos de Dukascopy"):
        campaigns.register(
            "US100",
            "D1",
            "turn_of_month",
            data_source="databento",
            frame=frame,
            dry_run=True,
            db_path=tmp_path / "discovery.db",
        )
