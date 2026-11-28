"""FUT-B2: plan, descarga gobernada y normalización de `trades` con un cliente FALSO (sin red)."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from tradinglab.futures import data_download as dd

HEADER = (
    "ts_event,rtype,publisher_id,instrument_id,action,side,depth,price,size,flags,"
    "ts_recv,ts_in_delta,sequence\n"
)
TRADES_CSV = HEADER + (
    "2024-01-02T14:30:00.123456789Z,35,1,42075848,A,B,0,20125.25,2,0,"
    "2024-01-02T14:30:00.123456999Z,0,101\n"
    "2024-01-02T14:30:00.500000000Z,35,1,42075848,A,A,0,20125.00,3,0,"
    "2024-01-02T14:30:00.500000100Z,0,102\n"
    "2024-01-02T14:30:00.750000000Z,35,1,42075848,A,N,0,20125.00,1,0,"
    "2024-01-02T14:30:00.750000100Z,0,103\n"
)

JOB = dd.Job(
    schema="trades",
    root="NQ",
    start="2024-01-02T00:00:00Z",
    end="2024-01-03T00:00:00Z",
)


class Response:
    def __init__(self, content: bytes = b"", *, status: int = 200, text: str = "") -> None:
        self.content = content
        self.status_code = status
        self.text = text


class FakeClient:
    """Simula ``timeseries.get_range``: nunca toca la red."""

    def __init__(self, content: bytes = TRADES_CSV.encode("utf-8"), *, status: int = 200) -> None:
        self.content = content
        self.status = status
        self.posts: list[dict] = []

    def post(self, url: str, data=None):
        self.posts.append(dict(data or {}))
        return Response(self.content, status=self.status, text="error simulado")


def test_plan_construye_trabajos_continuos_y_valida():
    jobs = dd.plan(
        [
            {"root": "nq", "schema": "trades", "start": "2019-05-06", "end": "2026-11-01"},
            {"root": "MNQ", "schema": "tbbo", "start": "2019-05-06T00:00:00Z", "end": "2019-06-01T00:00:00Z"},
            {"root": "NQ", "schema": "trades", "start": "2019-05-06", "end": "2026-11-01"},
        ]
    )
    assert [job.as_dict() for job in jobs] == [
        {
            "dataset": "GLBX.MDP3",
            "schema": "trades",
            "root": "NQ",
            "start": "2019-05-06",
            "end": "2026-11-01",
            "symbol": "NQ.v.0",
        },
        {
            "dataset": "GLBX.MDP3",
            "schema": "tbbo",
            "root": "MNQ",
            "start": "2019-05-06T00:00:00Z",
            "end": "2019-06-01T00:00:00Z",
            "symbol": "MNQ.v.0",
        },
    ]
    with pytest.raises(dd.DownloadError, match="esquema no soportado"):
        dd.plan([{"root": "NQ", "schema": "bars", "start": "2024-01-01", "end": "2024-02-01"}])
    with pytest.raises(dd.DownloadError, match="raíz no válida"):
        dd.plan([{"root": "NQ!", "schema": "trades", "start": "2024-01-01", "end": "2024-02-01"}])
    with pytest.raises(dd.DownloadError, match="posterior"):
        dd.plan([{"root": "NQ", "schema": "trades", "start": "2024-02-01", "end": "2024-01-01"}])


def test_raw_path_crudo_inmutable(tmp_path):
    path = dd.raw_path(JOB, tmp_path)
    assert path == (
        tmp_path
        / "raw"
        / "databento"
        / "GLBX.MDP3"
        / "trades"
        / "NQ"
        / "2024-01-02T00-00-00Z_2024-01-03T00-00-00Z.csv.zst"
    )


def test_sin_aprobacion_no_hay_red(tmp_path):
    client = FakeClient()
    with pytest.raises(RuntimeError, match="OP-4 sin aprobar"):
        dd.download(JOB, client, tmp_path, approved_by_operator=False)
    assert client.posts == []
    assert not (tmp_path / "raw").exists()


def test_descarga_manifiesto_e_idempotencia(tmp_path):
    client = FakeClient()
    path = dd.download(JOB, client, tmp_path, approved_by_operator=True)

    assert path.read_bytes() == client.content
    (post,) = client.posts
    assert post["dataset"] == "GLBX.MDP3"
    assert post["symbols"] == "NQ.v.0"
    assert post["schema"] == "trades"
    assert post["encoding"] == "csv"
    assert post["compression"] == "zstd"
    assert post["stype_in"] == "continuous"
    assert (post["start"], post["end"]) == (JOB.start, JOB.end)

    entries = dd.read_manifest(tmp_path)
    assert len(entries) == 1
    assert entries[0]["sha256"] == dd.sha256_file(path)
    assert entries[0]["path"] == "raw/databento/GLBX.MDP3/trades/NQ/" + path.name
    assert entries[0]["rows"] == 3
    assert entries[0]["provider"] == "databento"
    assert entries[0]["root"] == "NQ"
    assert entries[0]["schema"] == "trades"
    assert entries[0]["start"] == JOB.start and entries[0]["end"] == JOB.end
    assert entries[0]["generator"] == dd.GENERATOR
    assert entries[0]["generator_version"] == dd.GENERATOR_VERSION
    assert set(entries[0]) >= {"sha256", "provider", "schema", "root", "start", "end", "rows", "generator"}

    again = FakeClient()
    assert dd.download(JOB, again, tmp_path, approved_by_operator=True) == path
    assert again.posts == []
    assert len(dd.read_manifest(tmp_path)) == 1


def test_conflicto_de_hash_no_sobrescribe(tmp_path):
    path = dd.download(JOB, FakeClient(), tmp_path, approved_by_operator=True)
    path.write_bytes(b"otra cosa")

    client = FakeClient()
    with pytest.raises(dd.DownloadError, match="hash distinto"):
        dd.download(JOB, client, tmp_path, approved_by_operator=True)
    assert client.posts == []
    assert path.read_bytes() == b"otra cosa"
    assert len(dd.read_manifest(tmp_path)) == 1


def test_fichero_sin_ficha_no_se_sobrescribe(tmp_path):
    path = dd.raw_path(JOB, tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"huerfano")

    with pytest.raises(dd.DownloadError, match="sin ficha"):
        dd.download(JOB, FakeClient(), tmp_path, approved_by_operator=True)
    assert path.read_bytes() == b"huerfano"


def test_error_http(tmp_path):
    client = FakeClient(status=401)
    with pytest.raises(dd.DownloadError, match="HTTP 401"):
        dd.download(JOB, client, tmp_path, approved_by_operator=True)
    assert not dd.raw_path(JOB, tmp_path).exists()


def test_normalizacion_valores_exactos(tmp_path):
    frame = dd.normalize_trades(TRADES_CSV)
    assert list(frame.columns) == ["ts_event", "price", "size", "side", "instrument_id"]
    assert str(frame["ts_event"].dt.tz) == "UTC"
    assert frame["ts_event"].dt.unit == "ns"
    assert frame["ts_event"].iloc[0] == pd.Timestamp("2024-01-02T14:30:00.123456789Z")
    assert frame["price"].tolist() == [20125.25, 20125.0, 20125.0]
    assert frame["size"].tolist() == [2, 3, 1]
    assert frame["side"].tolist() == ["B", "A", "N"]
    assert frame["instrument_id"].tolist() == [42075848, 42075848, 42075848]

    target = dd.write_norm_trades(TRADES_CSV, tmp_path / "norm" / "trades" / "NQ" / "2024.parquet")
    back = pd.read_parquet(target)
    assert list(back.columns) == list(dd.TRADES_COLUMNS)
    assert back["price"].tolist() == [20125.25, 20125.0, 20125.0]
    assert str(back["ts_event"].dt.tz) == "UTC"


def test_normalizacion_columna_ausente():
    csv = HEADER.replace("size,", "") + (
        "2024-01-02T14:30:00.123456789Z,35,1,42075848,A,B,0,20125.25,0,"
        "2024-01-02T14:30:00.123456999Z,0,101\n"
    )
    with pytest.raises(dd.DownloadError, match="Sin datos: size"):
        dd.normalize_trades(csv)
    with pytest.raises(dd.DownloadError, match="Sin datos: price"):
        dd.normalize_trades("ts_event,size,side,instrument_id\n2024-01-02T14:30:00Z,1,B,1\n")


def test_manifiesto_una_linea_por_fichero(tmp_path):
    other = dd.Job(
        schema="trades",
        root="MNQ",
        start="2024-01-02T00:00:00Z",
        end="2024-01-03T00:00:00Z",
    )
    dd.download(JOB, FakeClient(), tmp_path, approved_by_operator=True)
    dd.download(other, FakeClient(), tmp_path, approved_by_operator=True)

    raw = (tmp_path / "catalog" / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(raw) == 2
    assert [json.loads(line)["root"] for line in raw] == ["NQ", "MNQ"]
    assert len({json.loads(line)["path"] for line in raw}) == 2


def test_monthly_parte_por_mes_natural():
    jobs = dd.monthly([dd.Job(schema="tbbo", root="NQ", start="2019-06-03", end="2019-08-15")])
    assert [(j.start, j.end) for j in jobs] == [
        ("2019-06-03T00:00:00Z", "2019-07-01T00:00:00Z"),
        ("2019-07-01T00:00:00Z", "2019-08-01T00:00:00Z"),
        ("2019-08-01T00:00:00Z", "2019-08-15T00:00:00Z"),
    ]
    assert {j.symbol for j in jobs} == {"NQ.v.0"}


def test_trozo_de_tick_largo_se_rechaza_sin_red(tmp_path):
    client = FakeClient()
    big = dd.Job(schema="tbbo", root="MNQ", start="2019-06-03", end="2023-12-29")
    with pytest.raises(dd.DownloadError, match="monthly"):
        dd.download(big, client, tmp_path, approved_by_operator=True)
    assert client.posts == []
    ohlcv = dd.Job(schema="ohlcv-1m", root="ES", start="2010-06-06", end="2018-12-31")
    assert dd.download(ohlcv, client, tmp_path, approved_by_operator=True).exists()


def test_zstd_cuenta_filas_y_normaliza(tmp_path):
    zstandard = pytest.importorskip("zstandard")
    packed = zstandard.ZstdCompressor().compress(TRADES_CSV.encode("utf-8"))
    path = dd.download(JOB, FakeClient(packed), tmp_path, approved_by_operator=True)
    assert path.read_bytes() == packed                       # el crudo se guarda tal cual, comprimido
    assert dd.read_manifest(tmp_path)[0]["rows"] == 3
    assert dd.normalize_trades(path)["price"].tolist() == [20125.25, 20125.0, 20125.0]


def test_sin_zstandard_la_ficha_queda_sin_filas_pero_existe(tmp_path, monkeypatch):
    import builtins
    real_import = builtins.__import__

    def no_zstd(name, *args, **kwargs):
        if name == "zstandard":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_zstd)
    packed = dd.ZSTD_MAGIC + b"cuerpo comprimido simulado"
    path = dd.download(JOB, FakeClient(packed), tmp_path, approved_by_operator=True)
    entry = dd.read_manifest(tmp_path)[0]
    assert entry["rows"] is None and entry["sha256"] == dd.sha256_file(path)
    with pytest.raises(dd.DownloadError, match="zstandard"):
        dd.normalize_trades(path)
