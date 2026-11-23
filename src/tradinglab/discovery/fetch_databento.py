"""Futuros CME (Databento GLBX.MDP3): coste y tubería.

La clave vive en Windows Credential Manager (``tradinglab`` /
``DATABENTO_API_KEY``). Nunca se imprime ni se escribe en un fichero.

Regla de esta fase
------------------
Estimar es gratis; descargar cuesta. ``estimate`` usa solo
``metadata.get_cost``, ``metadata.get_record_count`` y
``metadata.get_billable_size``. La descarga (``timeseries.get_range``) exige
que el operador apruebe un importe que coincida con la estimación
(``approved_cost``); el CLI lo pide con ``--i-approve-cost``.

Contrato continuo
-----------------
Se usan los símbolos continuos de Databento con ``stype_in=continuous``:

* ``<RAIZ>.c.0``: roll por calendario (fecha fija antes del vencimiento).
* ``<RAIZ>.v.0``: roll por volumen.

Databento entrega el contrato continuo **sin ajuste de precio**. La opción por
defecto es ``adjust="none"``: se guardan los precios tal cual, que son los
válidos para ejecución y costes. ``adjust="back"`` suma la diferencia
acumulada de cada roll a las barras anteriores (back-adjust por diferencia)
para señales; necesita una tabla de rolls explícita porque las diferencias no
se inventan. Para que no se mezclen series, ``--adjust back`` exige que la
caché del símbolo esté vacía.

Símbolos internos y 6J
----------------------
``NQ→US100``, ``ES→US500``, ``YM→US30``, ``GC→XAUUSD``, ``6E→EURUSD``,
``6B→GBPUSD`` y ``6J→USDJPY``. El futuro 6J cotiza USD por JPY (p. ej.
0,0068). USDJPY es JPY por USD, así que se invierte **barra a barra**:

    open  = 1 / open_6J
    high  = 1 / low_6J       (la inversión intercambia máximo y mínimo)
    low   = 1 / high_6J
    close = 1 / close_6J
    volume = volume_6J

Formato de salida
-----------------
``data/cache/databento/<SÍMBOLO>_<TF>.parquet`` con índice UTC llamado
``time`` y columnas ``open, high, low, close, volume`` (el mismo formato base
que la caché M1 de Dukascopy, sin ASK porque Databento OHLCV no lo trae).
"""

from __future__ import annotations

import io
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import httpx
import pandas as pd

from ..config import KEYRING_SERVICE, ROOT

DATABENTO_BASE = "https://hist.databento.com/v0"
DATASET = "GLBX.MDP3"
DATASET_NAME = "CME Globex (GLBX.MDP3)"

# raíz Databento -> símbolo interno del Discovery Lab
ROOT_TO_INTERNAL = {
    "NQ": "US100",
    "ES": "US500",
    "YM": "US30",
    "GC": "XAUUSD",
    "6E": "EURUSD",
    "6B": "GBPUSD",
    "6J": "USDJPY",
}
INTERNAL_TO_ROOT = {value: key for key, value in ROOT_TO_INTERNAL.items()}
ROOTS = tuple(ROOT_TO_INTERNAL)
SYMBOLS = tuple(ROOT_TO_INTERNAL.values())
SCHEMAS = ("ohlcv-1m", "ohlcv-1h")
SCHEMA_TIMEFRAME = {"ohlcv-1m": "M1", "ohlcv-1h": "H1"}
ROLLS = ("c", "v")
ROLL_NAMES = {"c": "calendario", "v": "volumen"}
OHLC = ("open", "high", "low", "close")
COLUMNS = OHLC + ("volume",)
DATABENTO_DIR = ROOT / "data" / "cache" / "databento"
SECRET_KEY = "DATABENTO_API_KEY"


class DatabentoError(RuntimeError):
    pass


@dataclass(frozen=True)
class CostRow:
    symbol: str
    root: str
    continuous: str
    schema: str
    roll: str
    records: int
    billable_bytes: int
    cost_usd: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "root": self.root,
            "continuous": self.continuous,
            "schema": self.schema,
            "roll": self.roll,
            "records": self.records,
            "billable_bytes": self.billable_bytes,
            "cost_usd": self.cost_usd,
        }


@dataclass(frozen=True)
class CostEstimate:
    dataset: str
    schema: str
    roll: str
    start: str
    end: str
    rows: tuple[CostRow, ...]

    @property
    def total_records(self) -> int:
        return sum(row.records for row in self.rows)

    @property
    def total_billable_bytes(self) -> int:
        return sum(row.billable_bytes for row in self.rows)

    @property
    def total_cost_usd(self) -> float:
        return sum(row.cost_usd for row in self.rows)

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "schema": self.schema,
            "roll": self.roll,
            "start": self.start,
            "end": self.end,
            "rows": [row.as_dict() for row in self.rows],
            "total_records": self.total_records,
            "total_billable_bytes": self.total_billable_bytes,
            "total_cost_usd": self.total_cost_usd,
        }


def api_key() -> str:
    """Lee la clave de Credential Manager; nunca la devuelve en un log."""
    try:
        import keyring

        value = keyring.get_password(KEYRING_SERVICE, SECRET_KEY)
    except Exception as exc:  # noqa: BLE001
        raise DatabentoError(
            f"no se pudo leer {SECRET_KEY} de Credential Manager: {type(exc).__name__}"
        ) from exc
    if not value:
        raise DatabentoError(
            f"Sin clave: falta {SECRET_KEY} en Credential Manager "
            f"(servicio {KEYRING_SERVICE!r})"
        )
    return str(value)


def _client(api_key_value: str | None = None) -> httpx.Client:
    return httpx.Client(
        auth=(api_key_value or api_key(), ""),
        timeout=httpx.Timeout(60.0, read=900.0, write=120.0, pool=60.0),
        follow_redirects=True,
    )


def normalize_symbol(value: str) -> str:
    """Acepta una raíz Databento o un símbolo interno y devuelve la raíz."""
    key = str(value or "").strip().upper()
    if key in ROOT_TO_INTERNAL:
        return key
    if key in INTERNAL_TO_ROOT:
        return INTERNAL_TO_ROOT[key]
    valid = ", ".join(ROOTS)
    raise DatabentoError(
        f"símbolo no soportado: {value!r}; usa una raíz de: {valid} "
        f"(o su símbolo interno)"
    )


def internal_symbol(value: str) -> str:
    return ROOT_TO_INTERNAL[normalize_symbol(value)]


def continuous_symbol(value: str, roll: str = "c") -> str:
    roll_key = str(roll or "").strip().lower()
    if roll_key not in ROLLS:
        raise DatabentoError(f"roll no soportado: {roll!r}; usa c o v")
    return f"{normalize_symbol(value)}.{roll_key}.0"


def normalize_schema(value: str) -> str:
    key = str(value or "").strip().lower()
    if key not in SCHEMAS:
        raise DatabentoError(
            f"schema no soportado: {value!r}; usa {' o '.join(SCHEMAS)}"
        )
    return key


def normalize_roll(value: str) -> str:
    key = str(value or "").strip().lower()
    if key not in ROLLS:
        raise DatabentoError(f"roll no soportado: {value!r}; usa c o v")
    return key


def timeframe_for_schema(schema: str) -> str:
    return SCHEMA_TIMEFRAME[normalize_schema(schema)]


def cache_path(symbol: str, schema: str = "ohlcv-1m", *, root: Path = ROOT) -> Path:
    key = internal_symbol(symbol)
    return (
        Path(root)
        / "data"
        / "cache"
        / "databento"
        / f"{key}_{timeframe_for_schema(schema)}.parquet"
    )


def _response_text(response: Any) -> str:
    return str(getattr(response, "text", "") or "")[:300]


def _get_json(client: Any, endpoint: str, params: dict[str, Any]) -> Any:
    try:
        response = client.get(f"{DATABENTO_BASE}/{endpoint}", params=params)
    except Exception as exc:  # noqa: BLE001
        raise DatabentoError(f"{endpoint}: {type(exc).__name__}") from exc
    status = int(getattr(response, "status_code", 0))
    if status != 200:
        raise DatabentoError(
            f"{endpoint}: HTTP {status} {_response_text(response)}"
        )
    try:
        return response.json()
    except Exception as exc:  # noqa: BLE001
        raise DatabentoError(f"{endpoint}: respuesta no JSON") from exc


def dataset_range(
    dataset: str = DATASET, *, client: Any | None = None
) -> dict[str, Any]:
    """Rango disponible del dataset (gratis, sin descargar datos)."""
    own = client is None
    http = client or _client()
    try:
        return _get_json(
            http, "metadata.get_dataset_range", {"dataset": str(dataset)}
        )
    finally:
        if own:
            http.close()


def _schema_range(
    ranges: dict[str, Any], schema: str, start: str | None, end: str | None
) -> tuple[str, str]:
    per_schema = (ranges.get("schema") or {}).get(schema) or {}
    first = str(start or per_schema.get("start") or ranges.get("start") or "")
    last = str(end or per_schema.get("end") or ranges.get("end") or "")
    if not first or not last:
        raise DatabentoError("Databento no devolvió un rango utilizable")
    return first, last


def _metadata_params(
    *, dataset: str, schema: str, row_symbol: str, start: str, end: str
) -> dict[str, str]:
    return {
        "dataset": str(dataset),
        "schema": str(schema),
        "symbols": str(row_symbol),
        "stype_in": "continuous",
        "start": str(start),
        "end": str(end),
    }


def _estimate_with_client(
    client: Any,
    symbols: Sequence[str],
    *,
    schema: str,
    roll: str,
    start: str | None,
    end: str | None,
    dataset: str,
) -> CostEstimate:
    schema_key = normalize_schema(schema)
    roll_key = normalize_roll(roll)
    roots = [normalize_symbol(symbol) for symbol in symbols]
    if not roots:
        raise DatabentoError("no hay símbolos que estimar")
    ranges = _get_json(
        client, "metadata.get_dataset_range", {"dataset": str(dataset)}
    )
    first, last = _schema_range(ranges, schema_key, start, end)
    rows: list[CostRow] = []
    for root in roots:
        row_symbol = continuous_symbol(root, roll_key)
        params = _metadata_params(
            dataset=dataset,
            schema=schema_key,
            row_symbol=row_symbol,
            start=first,
            end=last,
        )
        records = int(
            _get_json(client, "metadata.get_record_count", params)
        )
        size = int(
            _get_json(client, "metadata.get_billable_size", params)
        )
        cost = float(_get_json(client, "metadata.get_cost", params))
        rows.append(
            CostRow(
                symbol=ROOT_TO_INTERNAL[root],
                root=root,
                continuous=row_symbol,
                schema=schema_key,
                roll=roll_key,
                records=records,
                billable_bytes=size,
                cost_usd=cost,
            )
        )
    return CostEstimate(
        dataset=str(dataset),
        schema=schema_key,
        roll=roll_key,
        start=first,
        end=last,
        rows=tuple(rows),
    )


def estimate(
    symbols: Iterable[str] = ROOTS,
    *,
    schema: str = "ohlcv-1m",
    roll: str = "c",
    start: str | None = None,
    end: str | None = None,
    dataset: str = DATASET,
    client: Any | None = None,
    api_key_value: str | None = None,
) -> CostEstimate:
    """Coste y tamaño por símbolo/roll/schema. No descarga datos de pago."""
    own = client is None
    http = client or _client(api_key_value)
    try:
        return _estimate_with_client(
            http,
            list(symbols),
            schema=schema,
            roll=roll,
            start=start,
            end=end,
            dataset=dataset,
        )
    finally:
        if own:
            http.close()


def load_cache(
    symbol: str, schema: str = "ohlcv-1m", *, root: Path = ROOT
) -> pd.DataFrame:
    path = cache_path(symbol, schema, root=root)
    if not path.exists():
        raise DatabentoError(f"Sin datos: no existe {path}")
    try:
        frame = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        raise DatabentoError(
            f"Sin datos: no se pudo leer {path} ({type(exc).__name__}: {exc})"
        ) from exc
    frame = frame.copy()
    frame.columns = [str(column).lower() for column in frame.columns]
    missing = [column for column in COLUMNS if column not in frame.columns]
    if missing:
        raise DatabentoError(
            f"{path}: faltan columnas {', '.join(missing)}"
        )
    index = pd.DatetimeIndex(pd.to_datetime(frame.index))
    index = (
        index.tz_localize("UTC")
        if index.tz is None
        else index.tz_convert("UTC")
    )
    frame.index = index
    frame.index.name = "time"
    frame = frame.loc[:, list(COLUMNS)].sort_index()
    return frame.loc[~frame.index.duplicated(keep="last")]


def _parse_timestamp(series: pd.Series) -> pd.DatetimeIndex:
    if pd.api.types.is_numeric_dtype(series):
        return pd.DatetimeIndex(
            pd.to_datetime(series, unit="ns", utc=True, errors="coerce")
        )
    try:
        return pd.DatetimeIndex(
            pd.to_datetime(
                series.astype(str), utc=True, format="ISO8601", errors="coerce"
            )
        )
    except (TypeError, ValueError):
        return pd.DatetimeIndex(
            pd.to_datetime(series.astype(str), utc=True, errors="coerce")
        )


def invert_6j(frame: pd.DataFrame) -> pd.DataFrame:
    """Convierte 6J (USD/JPY) a USDJPY (JPY/USD) invirtiendo y volteando H/L."""
    out = frame.copy()
    for column in OHLC:
        values = pd.to_numeric(out[column], errors="coerce")
        if values.isna().any() or (values <= 0).any():
            raise DatabentoError("6J: precios no positivos; no se puede invertir")
    out["open"] = 1.0 / frame["open"].astype(float)
    out["high"] = 1.0 / frame["low"].astype(float)
    out["low"] = 1.0 / frame["high"].astype(float)
    out["close"] = 1.0 / frame["close"].astype(float)
    return out


def parse_csv(payload: bytes, *, root: str) -> pd.DataFrame:
    """Convierte el CSV de ``timeseries.get_range`` (pretty_px/pretty_ts)."""
    root_key = normalize_symbol(root)
    if not payload:
        raise DatabentoError("Databento devolvió una respuesta vacía")
    try:
        frame = pd.read_csv(io.BytesIO(payload))
    except Exception as exc:  # noqa: BLE001
        raise DatabentoError(f"CSV de Databento inválido: {type(exc).__name__}") from exc
    if frame.empty:
        raise DatabentoError(f"Sin datos: Databento no devolvió velas para {root_key}")
    frame.columns = [str(column).strip().lower() for column in frame.columns]
    stamp_column = "ts_event" if "ts_event" in frame.columns else "ts_recv"
    if stamp_column not in frame.columns:
        raise DatabentoError("CSV de Databento sin ts_event/ts_recv")
    missing = [column for column in COLUMNS if column not in frame.columns]
    if missing:
        raise DatabentoError(
            f"CSV de Databento sin columnas: {', '.join(missing)}"
        )
    stamps = _parse_timestamp(frame[stamp_column])
    if stamps.isna().any():
        raise DatabentoError("CSV de Databento con timestamps inválidos")
    frame = frame.loc[:, list(COLUMNS)].copy()
    for column in COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if frame[list(COLUMNS)].isna().any().any():
        raise DatabentoError("CSV de Databento con OHLCV no numérico")
    frame.index = stamps
    frame.index.name = "time"
    frame = frame.sort_index()
    frame = frame.loc[~frame.index.duplicated(keep="last")]
    frame = frame.loc[frame["volume"] > 0]
    if frame.empty:
        raise DatabentoError(f"Sin datos: {root_key} solo trae volumen 0")
    invalid = (
        (frame["high"] < frame["low"])
        | (frame["high"] < frame[["open", "close"]].max(axis=1))
        | (frame["low"] > frame[["open", "close"]].min(axis=1))
        | (frame[list(OHLC)] <= 0).any(axis=1)
    )
    if bool(invalid.any()):
        raise DatabentoError(
            f"{root_key}: {int(invalid.sum())} velas OHLC inválidas"
        )
    if root_key == "6J":
        frame = invert_6j(frame)
    return frame


def _post_csv(
    client: Any,
    *,
    dataset: str,
    schema: str,
    row_symbol: str,
    start: str,
    end: str,
) -> bytes:
    data = _metadata_params(
        dataset=dataset,
        schema=schema,
        row_symbol=row_symbol,
        start=start,
        end=end,
    )
    data.update(
        {
            "encoding": "csv",
            "compression": "none",
            "pretty_px": "true",
            "pretty_ts": "true",
            "map_symbols": "false",
        }
    )
    try:
        response = client.post(f"{DATABENTO_BASE}/timeseries.get_range", data=data)
    except Exception as exc:  # noqa: BLE001
        raise DatabentoError(
            f"timeseries.get_range: {type(exc).__name__}"
        ) from exc
    status = int(getattr(response, "status_code", 0))
    if status != 200:
        raise DatabentoError(
            f"timeseries.get_range: HTTP {status} {_response_text(response)}"
        )
    content = getattr(response, "content", b"")
    if not content:
        raise DatabentoError("timeseries.get_range: respuesta vacía")
    return content


def load_roll_table(path: str | Path) -> dict[str, list[tuple[pd.Timestamp, float]]]:
    """Lee ``{"NQ": [["2024-06-17T00:00:00Z", 12.5], ...], ...}``.

    También acepta ``{"time": ..., "diff": ...}`` por entrada. La diferencia es
    ``precio_nuevo - precio_viejo`` en el primer timestamp del contrato nuevo;
    no se deduce de los datos.
    """
    target = Path(path)
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise DatabentoError(f"tabla de rolls ilegible: {target}") from exc
    if not isinstance(raw, dict):
        raise DatabentoError("la tabla de rolls debe ser un objeto JSON")
    table: dict[str, list[tuple[pd.Timestamp, float]]] = {}
    for name, items in raw.items():
        root = normalize_symbol(str(name))
        parsed: list[tuple[pd.Timestamp, float]] = []
        if not isinstance(items, list):
            raise DatabentoError(f"rolls de {name}: se esperaba una lista")
        for item in items:
            if isinstance(item, dict):
                stamp_text = item.get("time")
                diff = item.get("diff")
            else:
                try:
                    stamp_text, diff = item
                except (TypeError, ValueError) as exc:
                    raise DatabentoError(f"roll inválido en {name}: {item!r}") from exc
            try:
                stamp = pd.Timestamp(str(stamp_text))
                value = float(diff)
            except (TypeError, ValueError) as exc:
                raise DatabentoError(f"roll inválido en {name}: {item!r}") from exc
            if stamp.tzinfo is None:
                stamp = stamp.tz_localize("UTC")
            else:
                stamp = stamp.tz_convert("UTC")
            if not math.isfinite(value):
                raise DatabentoError(f"roll inválido en {name}: diferencia no finita")
            parsed.append((stamp, value))
        table[root] = sorted(parsed)
    return table


def back_adjust(
    frame: pd.DataFrame, rolls: Sequence[tuple[pd.Timestamp, float]]
) -> pd.DataFrame:
    """Back-adjust por diferencia: suma cada roll a las barras anteriores.

    ``diff = precio_nuevo - precio_viejo`` en el primer timestamp del contrato
    nuevo. Así el histórico anterior queda en la escala del contrato actual.
    """
    out = frame.copy()
    if out.index.tz is None:
        out.index = out.index.tz_localize("UTC")
    else:
        out.index = out.index.tz_convert("UTC")
    for stamp, diff in sorted(rolls, key=lambda item: item[0]):
        before = out.index < stamp
        for column in OHLC:
            out.loc[before, column] = out.loc[before, column] + float(diff)
    return out


def _write_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temporary)
    temporary.replace(path)


def download(
    symbols: Iterable[str] = ROOTS,
    *,
    schema: str = "ohlcv-1m",
    roll: str = "c",
    start: str | None = None,
    end: str | None = None,
    approved_cost: float,
    adjust: str = "none",
    roll_table: str | Path | None = None,
    dataset: str = DATASET,
    root: Path = ROOT,
    client: Any | None = None,
    api_key_value: str | None = None,
) -> dict[str, Any]:
    """Descarga SOLO si ``approved_cost`` coincide con la estimación.

    ``timeseries.get_range`` factura. Esta función no se llama desde el CLI sin
    ``--i-approve-cost``. Los tests usan un cliente simulado.
    """
    adjust_key = str(adjust or "none").strip().lower()
    if adjust_key not in {"none", "back"}:
        raise DatabentoError(f"ajuste no soportado: {adjust!r}; usa none o back")
    if adjust_key == "back" and roll_table is None:
        raise DatabentoError("--adjust back exige --roll-table")
    tables = load_roll_table(roll_table) if roll_table is not None else {}

    own = client is None
    http = client or _client(api_key_value)
    try:
        costs = _estimate_with_client(
            http,
            list(symbols),
            schema=schema,
            roll=roll,
            start=start,
            end=end,
            dataset=dataset,
        )
        total = costs.total_cost_usd
        approved = float(approved_cost)
        if not math.isfinite(approved) or abs(total - approved) > 0.005:
            raise DatabentoError(
                f"coste no aprobado: estimación {total:.6f} USD, "
                f"aprobado {approved:.6f} USD (deben coincidir al centavo)"
            )
        results: list[dict[str, Any]] = []
        for row in costs.rows:
            path = cache_path(row.symbol, row.schema, root=root)
            if adjust_key == "back" and path.exists():
                raise DatabentoError(
                    f"--adjust back exige caché vacía: ya existe {path}"
                )
            payload = _post_csv(
                http,
                dataset=costs.dataset,
                schema=costs.schema,
                row_symbol=row.continuous,
                start=costs.start,
                end=costs.end,
            )
            frame = parse_csv(payload, root=row.root)
            if adjust_key == "back":
                rolls = tables.get(row.root, [])
                if not rolls:
                    raise DatabentoError(
                        f"--adjust back sin rolls para {row.root} en {roll_table}"
                    )
                frame = back_adjust(frame, rolls)
            if path.exists():
                frame = pd.concat([load_cache(row.symbol, row.schema, root=root), frame])
                frame = frame.sort_index()
                frame = frame.loc[~frame.index.duplicated(keep="last")]
            _write_atomic(frame.loc[:, list(COLUMNS)], path)
            results.append(
                {
                    "symbol": row.symbol,
                    "root": row.root,
                    "schema": row.schema,
                    "roll": row.roll,
                    "rows": int(len(frame)),
                    "start": frame.index[0].isoformat(),
                    "end": frame.index[-1].isoformat(),
                    "path": path.as_posix(),
                    "cost_usd": row.cost_usd,
                    "adjust": adjust_key,
                }
            )
        return {
            "dataset": costs.dataset,
            "schema": costs.schema,
            "roll": costs.roll,
            "start": costs.start,
            "end": costs.end,
            "estimated_cost_usd": total,
            "approved_cost_usd": approved,
            "rows": results,
        }
    finally:
        if own:
            http.close()


__all__ = [
    "COLUMNS",
    "DATABENTO_BASE",
    "DATABENTO_DIR",
    "DATASET",
    "DATASET_NAME",
    "DatabentoError",
    "INTERNAL_TO_ROOT",
    "OHLC",
    "ROLLS",
    "ROOT_TO_INTERNAL",
    "ROOTS",
    "SCHEMAS",
    "SCHEMA_TIMEFRAME",
    "SYMBOLS",
    "CostEstimate",
    "CostRow",
    "api_key",
    "back_adjust",
    "cache_path",
    "continuous_symbol",
    "dataset_range",
    "download",
    "estimate",
    "internal_symbol",
    "invert_6j",
    "load_cache",
    "load_roll_table",
    "normalize_roll",
    "normalize_schema",
    "normalize_symbol",
    "parse_csv",
    "timeframe_for_schema",
]
