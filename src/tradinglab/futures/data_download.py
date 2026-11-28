"""FUT-B2: descarga gobernada de Databento y normalización de ``trades``.

Reglas de ``docs/futures/03_ARQUITECTURA_FUTURES.md`` §3.2:

* **Crudo inmutable:** ``<out_root>/raw/databento/GLBX.MDP3/<schema>/<raíz>/<start>_<end>.csv.zst``.
  Si el fichero ya existe solo se acepta con la misma huella que su ficha del manifiesto; con otra
  huella, o sin ficha, **no se sobrescribe** y se lanza error.
* **Manifiesto:** una línea JSON por fichero en ``<out_root>/catalog/manifest.jsonl`` con sha256,
  proveedor, dataset, esquema, raíz, rango, filas, generador y versión.
* **Gasto:** ``download`` exige ``approved_by_operator=True`` (acuerdo OP-4). Sin esa aprobación no
  se hace ninguna llamada de red. Los tests usan un cliente falso; este módulo nunca descarga por
  su cuenta.

``out_root`` es la raíz ``data/futures`` (por defecto la del repositorio). El nombre del fichero usa
los timestamps con ``:`` sustituido por ``-`` para que sea válido en Windows; el rango original queda
literal en el manifiesto.

**Trozos mensuales:** los esquemas de tick (``trades``, ``tbbo``, ``mbp-*``, ``mbo``, ``bbo-1s``) se piden por
meses (``monthly``); ``download`` rechaza un trozo de tick de más de 32 días, porque la respuesta entera
vive en memoria (años de ``tbbo`` son decenas de GB).

**Compresión:** Databento devuelve el CSV comprimido con zstd y se guarda tal cual. Las filas del
manifiesto se cuentan descomprimiendo en memoria si está ``zstandard`` (extra ``futdata``); si no, quedan
``null`` y se rellenan al normalizar. Nunca se escribe el fichero y luego se falla al contarlo.

``normalize_trades`` devuelve el DataFrame normalizado con las columnas literales de Databento
(``ts_event`` en UTC ns, ``price``, ``size``, ``side`` con la letra B/A/N e ``instrument_id``);
``write_norm_trades`` lo guarda en parquet. El mapeo B=+1, A=−1, N=excluido pertenece a la capa de
investigación (``research/RA_spec.md`` §2), no a la normalización.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import pandas as pd

from ..config import ROOT
from ..discovery.fetch_databento import DATABENTO_BASE

DATASET = "GLBX.MDP3"
PROVIDER = "databento"
ROLL = "v"
GENERATOR = "tradinglab.futures.data_download"
GENERATOR_VERSION = "1"

# Esquemas nombrados en docs/futures/03_ARQUITECTURA_FUTURES.md §3.1.
ALLOWED_SCHEMAS = (
    "trades",
    "tbbo",
    "mbp-1",
    "bbo-1s",
    "mbp-10",
    "mbo",
    "ohlcv-1m",
    "ohlcv-1h",
    "definition",
    "statistics",
    "status",
)

TRADES_COLUMNS = ("ts_event", "price", "size", "side", "instrument_id")
SIDES = ("A", "B", "N")

TICK_SCHEMAS = ("trades", "tbbo", "mbp-1", "bbo-1s", "mbp-10", "mbo")
MAX_TICK_CHUNK_DAYS = 32
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"

DEFAULT_OUT_ROOT = ROOT / "data" / "futures"
_ROOT_PATTERN = re.compile(r"^[A-Z0-9]{2,6}$")


class DownloadError(RuntimeError):
    pass


@dataclass(frozen=True)
class Job:
    """Un trozo de un esquema de una raíz continua (``<raíz>.v.0``)."""

    schema: str
    root: str
    start: str
    end: str
    dataset: str = DATASET

    @property
    def symbol(self) -> str:
        return f"{self.root}.{ROLL}.0"

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "schema": self.schema,
            "root": self.root,
            "start": self.start,
            "end": self.end,
            "symbol": self.symbol,
        }


def _check_schema(value: Any) -> str:
    key = str(value or "").strip().lower()
    if key not in ALLOWED_SCHEMAS:
        raise DownloadError(
            f"esquema no soportado: {value!r}; usa uno de: {', '.join(ALLOWED_SCHEMAS)}"
        )
    return key


def _check_root(value: Any) -> str:
    key = str(value or "").strip().upper()
    if not _ROOT_PATTERN.match(key):
        raise DownloadError(f"raíz no válida: {value!r} (p. ej. NQ, MNQ, ES, GC)")
    return key


def _check_stamp(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise DownloadError(f"falta {name} en el trabajo")
    if pd.isna(pd.to_datetime(text, utc=True, errors="coerce")):
        raise DownloadError(f"{name} no es un timestamp válido: {text!r}")
    return text


def stamp_token(value: str) -> str:
    """Timestamps en el nombre del fichero: sin ``:`` ni separadores de ruta."""
    return re.sub(r"[:/\\]", "-", str(value))


def plan(rows: Iterable[dict[str, Any]]) -> list[Job]:
    """Trabajos de descarga a partir de las filas de la tabla de coste.

    Cada fila debe traer ``root``, ``schema``, ``start`` y ``end`` (``dataset`` opcional). No hace
    red. Repite el orden de entrada y descarta duplicados exactos.
    """
    jobs: list[Job] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise DownloadError(f"fila {index}: se esperaba un dict")
        job = Job(
            schema=_check_schema(row.get("schema")),
            root=_check_root(row.get("root")),
            start=_check_stamp(row.get("start"), "start"),
            end=_check_stamp(row.get("end"), "end"),
            dataset=str(row.get("dataset") or DATASET),
        )
        pd.Timestamp(job.start, tz="UTC")
        if pd.Timestamp(job.end, tz="UTC") <= pd.Timestamp(job.start, tz="UTC"):
            raise DownloadError(f"fila {index}: end debe ser posterior a start")
        key = (job.dataset, job.schema, job.root, job.start, job.end)
        if key in seen:
            continue
        seen.add(key)
        jobs.append(job)
    return jobs


def monthly(jobs: Iterable[Job]) -> list[Job]:
    """Parte cada trabajo en trozos por mes natural (UTC); los extremos del rango se respetan."""
    out: list[Job] = []
    for job in jobs:
        start = pd.Timestamp(job.start, tz="UTC") if pd.Timestamp(job.start).tzinfo is None else \
            pd.Timestamp(job.start).tz_convert("UTC")
        end = pd.Timestamp(job.end, tz="UTC") if pd.Timestamp(job.end).tzinfo is None else \
            pd.Timestamp(job.end).tz_convert("UTC")
        cut = start
        while cut < end:
            nxt = min((cut + pd.offsets.MonthBegin(1)).normalize(), end)
            out.append(Job(schema=job.schema, root=job.root, start=cut.strftime("%Y-%m-%dT%H:%M:%SZ"),
                           end=nxt.strftime("%Y-%m-%dT%H:%M:%SZ"), dataset=job.dataset))
            cut = nxt
    return out


def _span_days(job: Job) -> float:
    start, end = pd.Timestamp(job.start), pd.Timestamp(job.end)
    start = start.tz_localize("UTC") if start.tzinfo is None else start
    end = end.tz_localize("UTC") if end.tzinfo is None else end
    return (end - start).total_seconds() / 86400.0


def raw_path(job: Job, out_root: str | Path = DEFAULT_OUT_ROOT) -> Path:
    """``<out_root>/raw/databento/GLBX.MDP3/<schema>/<raíz>/<start>_<end>.csv.zst``."""
    return (
        Path(out_root)
        / "raw"
        / PROVIDER
        / job.dataset
        / job.schema
        / job.root
        / f"{stamp_token(job.start)}_{stamp_token(job.end)}.csv.zst"
    )


def manifest_path(out_root: str | Path = DEFAULT_OUT_ROOT) -> Path:
    return Path(out_root) / "catalog" / "manifest.jsonl"


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _entry_key(path: Path, out_root: str | Path) -> str:
    try:
        return path.resolve().relative_to(Path(out_root).resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def read_manifest(out_root: str | Path = DEFAULT_OUT_ROOT) -> list[dict[str, Any]]:
    """Fichas del manifiesto; fichero ausente es lista vacía."""
    path = manifest_path(out_root)
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DownloadError(f"{path}: línea {number} no es JSON") from exc
        if not isinstance(entry, dict):
            raise DownloadError(f"{path}: línea {number} no es un objeto")
        entries.append(entry)
    return entries


def manifest_entry(
    path: str | Path, out_root: str | Path = DEFAULT_OUT_ROOT
) -> dict[str, Any] | None:
    target = _entry_key(Path(path), out_root)
    for entry in read_manifest(out_root):
        if str(entry.get("path")) == target:
            return entry
    return None


def append_manifest(entry: dict[str, Any], out_root: str | Path = DEFAULT_OUT_ROOT) -> Path:
    target = manifest_path(out_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=True, sort_keys=True)
    with target.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line + "\n")
    return target


def _response_text(response: Any) -> str:
    return str(getattr(response, "text", "") or "")[:300]


def _decompress(payload: bytes) -> bytes:
    """CSV en claro: descomprime zstd si hace falta (extra ``futdata``)."""
    if not payload.startswith(ZSTD_MAGIC):
        return payload
    try:
        import zstandard
    except ImportError as exc:
        raise DownloadError("Sin datos: falta zstandard para leer .csv.zst (uv sync --extra futdata)") from exc
    return zstandard.ZstdDecompressor().stream_reader(io.BytesIO(payload)).read()


def _count_rows(payload: bytes) -> int | None:
    """Filas de datos del CSV (sin cabecera). ``None`` si no se pueden contar: nunca lanza."""
    try:
        text = _decompress(payload).decode("utf-8")
    except (DownloadError, UnicodeDecodeError, Exception):  # noqa: BLE001
        return None
    lines = [line for line in text.splitlines() if line.strip()]
    return max(0, len(lines) - 1)


def _write_new(path: Path, payload: bytes) -> None:
    """Escribe sin pisar un fichero existente (carrera incluida)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    if path.exists():
        temporary.unlink()
        raise DownloadError(f"el fichero apareció mientras se descargaba: {path}")
    temporary.replace(path)


def _get_range(job: Job, client: Any) -> bytes:
    params = {
        "dataset": job.dataset,
        "schema": job.schema,
        "symbols": job.symbol,
        "stype_in": "continuous",
        "start": job.start,
        "end": job.end,
        "encoding": "csv",
        "compression": "zstd",
        "pretty_px": "true",
        "pretty_ts": "true",
        "map_symbols": "false",
    }
    try:
        response = client.post(f"{DATABENTO_BASE}/timeseries.get_range", data=params)
    except Exception as exc:  # noqa: BLE001
        raise DownloadError(f"timeseries.get_range: {type(exc).__name__}") from exc
    status = int(getattr(response, "status_code", 0))
    if status != 200:
        raise DownloadError(
            f"timeseries.get_range: HTTP {status} {_response_text(response)}"
        )
    content = getattr(response, "content", b"")
    if not content:
        raise DownloadError("timeseries.get_range: respuesta vacía")
    return content


def download(
    job: Job,
    client: Any,
    out_root: str | Path = DEFAULT_OUT_ROOT,
    *,
    approved_by_operator: bool,
) -> Path:
    """Descarga un trabajo si el operador aprobó OP-4; destino inmutable por sha256.

    Devuelve la ruta del fichero crudo. Si ya existe con la misma huella que su ficha **no**
    descarga. Nunca sobrescribe: otra huella o falta de ficha es error.
    """
    if not approved_by_operator:
        raise RuntimeError("OP-4 sin aprobar")
    if job.schema in TICK_SCHEMAS and _span_days(job) > MAX_TICK_CHUNK_DAYS:
        raise DownloadError(f"trozo de {job.schema} de {_span_days(job):.0f} días: pártelo con monthly(...)")
    path = raw_path(job, out_root)
    if path.exists():
        current = sha256_file(path)
        entry = manifest_entry(path, out_root)
        if entry is None:
            raise DownloadError(
                f"{path} existe sin ficha en el manifiesto: no se sobrescribe"
            )
        recorded = str(entry.get("sha256") or "")
        if recorded != current:
            raise DownloadError(
                f"{path}: hash distinto (ficha {recorded[:12]}…, fichero {current[:12]}…); "
                "nunca se sobrescribe"
            )
        return path

    payload = _get_range(job, client)
    rows = _count_rows(payload)          # antes de escribir: contar nunca deja un fichero sin ficha
    _write_new(path, payload)
    entry = {
        "path": _entry_key(path, out_root),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "rows": rows,
        "provider": PROVIDER,
        "dataset": job.dataset,
        "schema": job.schema,
        "root": job.root,
        "symbol": job.symbol,
        "start": job.start,
        "end": job.end,
        "encoding": "csv",
        "compression": "zstd",
        "generator": GENERATOR,
        "generator_version": GENERATOR_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    append_manifest(entry, out_root)
    return path


def _read_payload(payload: bytes | str | Path) -> bytes:
    if isinstance(payload, Path):
        return payload.read_bytes()
    if isinstance(payload, str):
        return payload.encode("utf-8")
    return bytes(payload)


def _parse_ts(series: pd.Series, column: str) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        stamps = pd.to_datetime(series, unit="ns", utc=True, errors="coerce")
    else:
        stamps = pd.to_datetime(series.astype(str), utc=True, errors="coerce")
    if stamps.isna().any():
        raise DownloadError(f"Sin datos: {column} con timestamps inválidos")
    index = pd.DatetimeIndex(stamps).tz_convert("UTC")
    return pd.Series(index.astype("datetime64[ns, UTC]"), index=series.index)


def normalize_trades(payload: bytes | str | Path) -> pd.DataFrame:
    """CSV de ``trades`` → DataFrame con ``ts_event`` (UTC ns), price, size, side, instrument_id."""
    raw = _read_payload(payload)
    if not raw:
        raise DownloadError("Sin datos: respuesta vacía")
    raw = _decompress(raw)
    try:
        frame = pd.read_csv(io.BytesIO(raw))
    except Exception as exc:  # noqa: BLE001
        raise DownloadError(f"CSV de trades inválido: {type(exc).__name__}") from exc
    frame.columns = [str(column).strip().lower() for column in frame.columns]
    for column in TRADES_COLUMNS:
        if column not in frame.columns:
            raise DownloadError(f"Sin datos: {column}")
    if frame.empty:
        raise DownloadError("Sin datos: el CSV no trae filas")

    out = pd.DataFrame(index=frame.index)
    out["ts_event"] = _parse_ts(frame["ts_event"], "ts_event")
    for column in ("price", "size", "instrument_id"):
        values = pd.to_numeric(frame[column], errors="coerce")
        if values.isna().any():
            raise DownloadError(f"Sin datos: {column} no numérico")
        out[column] = values.astype("int64" if column != "price" else "float64")
    side = frame["side"].astype(str).str.strip().str.upper()
    unknown = sorted(set(side) - set(SIDES))
    if unknown:
        raise DownloadError(f"Sin datos: side no reconocido {unknown[0]!r}")
    out["side"] = side

    out = out.loc[:, list(TRADES_COLUMNS)]
    out = out.sort_values("ts_event", kind="stable").reset_index(drop=True)
    if not out["ts_event"].is_monotonic_increasing:
        raise DownloadError("Sin datos: ts_event no monótono")
    return out


def write_norm_trades(
    payload: bytes | str | Path, path: str | Path
) -> Path:
    """Normaliza y escribe el parquet indicado (la ruta la fija quien llama)."""
    target = Path(path)
    frame = normalize_trades(payload)
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(target, index=False)
    return target


def download_many(
    jobs: Sequence[Job],
    client: Any,
    out_root: str | Path = DEFAULT_OUT_ROOT,
    *,
    approved_by_operator: bool,
) -> list[Path]:
    """Encadena ``download`` en orden; sin aprobación falla en el primer trabajo."""
    return [
        download(job, client, out_root, approved_by_operator=approved_by_operator)
        for job in jobs
    ]


__all__ = [
    "ALLOWED_SCHEMAS",
    "DATASET",
    "DEFAULT_OUT_ROOT",
    "DownloadError",
    "GENERATOR",
    "GENERATOR_VERSION",
    "Job",
    "PROVIDER",
    "ROLL",
    "SIDES",
    "TRADES_COLUMNS",
    "append_manifest",
    "download",
    "download_many",
    "manifest_entry",
    "manifest_path",
    "monthly",
    "normalize_trades",
    "plan",
    "raw_path",
    "read_manifest",
    "sha256_file",
    "stamp_token",
    "write_norm_trades",
]
