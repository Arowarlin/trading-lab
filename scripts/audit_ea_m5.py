"""Auditoría M5-only del EA us100-ftmo1 (solo lectura).

No registra trials, no llama a ``record_trial`` ni a ``register_campaign`` y no
escribe en ``data/lab.db``. Solo importa los componentes protegidos, lee la
caché del EA y escribe el informe en ``reports/audit``.

    .venv\\Scripts\\python.exe scripts\\audit_ea_m5.py

El escenario principal filtra la caché a velas M5 reales desde 2021-10-01 y
reconstruye la serie diaria solo con días M5. Se añaden dos referencias: la
caché completa con el motor actual (v3.2, con filtro de festivos NYSE) y un
arranque M5 desde 2021-09-14 para aislar el warmup.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from tradinglab import ea_us100  # noqa: E402
from tradinglab import ea_us100_engine as engine  # noqa: E402
from tradinglab.global_dsr import (  # noqa: E402
    DAILY,
    INTRADAY,
    frequency_for_timeframe,
    periods_for_timeframe,
    sr_from_annual,
)
from tradinglab.stats import dsr_from_returns, period_sharpe  # noqa: E402

AUDIT_DIR = ROOT / "reports" / "audit"
CACHE = ea_us100.CACHE
SETFILE = ROOT / "integrations" / "mt5" / "us100_ftmo1" / "US100_FTMO_v3_challenge.set"
DB = ROOT / "data" / "lab.db"
V3_JSON = ROOT / "reports" / "ea" / "us100-ftmo1_v3.json"
ROBUSTNESS_JSON = ROOT / "reports" / "research" / "ea_us100_ftmo1" / "robustness.json"

WINDOW_START = pd.Timestamp("2021-10-01")
M5_START = pd.Timestamp("2021-09-14")
V3_END = pd.Timestamp("2026-11-13 16:45:00")
RISK = ea_us100.RISK_PCT / 100.0
EA_REPORT_KEY = "ea:us100-ftmo1"


def _jsonable(value):
    """Convierte numpy/pandas a tipos JSON estándar y evita NaN/Infinity."""
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _db_state() -> dict:
    stat = DB.stat()
    return {
        "path": str(DB),
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "sha256": _sha256(DB),
    }


def _ro_connect(db_path: Path) -> sqlite3.Connection:
    """Conexión de solo lectura; ``total_changes`` debe quedar en 0."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.execute("PRAGMA query_only = ON")
    con.row_factory = sqlite3.Row
    return con


def _table_counts(db_path: Path) -> dict[str, int]:
    con = _ro_connect(db_path)
    names = [
        row["name"]
        for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    counts = {}
    for name in names:
        counts[name] = int(
            con.execute(f'SELECT COUNT(*) AS n FROM "{name}"').fetchone()["n"]
        )
    if con.total_changes != 0:
        raise RuntimeError(f"la conexión de solo lectura escribió {con.total_changes} filas")
    con.close()
    return counts


def _rth_days(frame: pd.DataFrame) -> pd.DatetimeIndex:
    rth = frame.between_time("09:30", "15:59")
    return pd.DatetimeIndex(sorted(set(rth.index.normalize())))


def _naive_ts(value) -> pd.Timestamp | None:
    try:
        stamp = pd.Timestamp(str(value))
    except (TypeError, ValueError):
        return None
    if stamp.tzinfo is not None:
        stamp = stamp.tz_localize(None)
    return stamp


def _segment(frame: pd.DataFrame, label: str, start=None, end=None) -> dict:
    if start is not None and end is not None:
        sub = frame.loc[start:end]
    elif start is not None:
        sub = frame.loc[start:]
    elif end is not None:
        sub = frame.loc[:end]
    else:
        sub = frame
    diffs = pd.Series(sub.index).diff().dropna()
    counts = diffs.value_counts()
    total = int(len(diffs))
    five = int((diffs == pd.Timedelta(minutes=5)).sum())
    return {
        "label": label,
        "rows": int(len(sub)),
        "start": str(sub.index.min()) if len(sub) else None,
        "end": str(sub.index.max()) if len(sub) else None,
        "diffs_total": total,
        "share_5min": five / total if total else None,
        "min_diff": str(diffs.min()) if total else None,
        "max_diff": str(diffs.max()) if total else None,
        "top_diffs": [
            {"delta": str(delta), "n": int(n)} for delta, n in counts.head(5).items()
        ],
    }


def _granularity(frame: pd.DataFrame) -> dict:
    m5 = frame.loc[M5_START:V3_END]
    high = m5["high"].astype(float)
    low = m5["low"].astype(float)
    open_ = m5["open"].astype(float)
    close = m5["close"].astype(float)
    invalid = (
        (high < low)
        | (high < open_)
        | (high < close)
        | (low > open_)
        | (low > close)
    )
    diffs = pd.Series(m5.index).diff().dropna()
    return {
        "cache": str(CACHE),
        "cache_sha256": _sha256(CACHE),
        "rows": int(len(frame)),
        "start": str(frame.index.min()),
        "end": str(frame.index.max()),
        "duplicates": int(frame.index.duplicated().sum()),
        "missing_ohlc": int(m5[["open", "high", "low", "close"]].isna().any(axis=1).sum()),
        "invalid_ohlc_m5": int(invalid.sum()),
        "m5_share": float((diffs == pd.Timedelta(minutes=5)).mean()) if len(diffs) else None,
        "m5_min_diff": str(diffs.min()) if len(diffs) else None,
        "segments": [
            _segment(frame, "D1 2017-12-28..2020-12-30", end="2020-12-31 23:59:59"),
            _segment(frame, "H1 2021-01-03..2021-09-13", start="2021-01-01", end="2021-09-13 23:59:59"),
            _segment(frame, "M5 2021-09-14..2026-11-13", start=M5_START, end=V3_END),
        ],
    }


def _run_grid(
    frame: pd.DataFrame,
    values: dict,
    days: pd.DatetimeIndex,
    *,
    trade_start: pd.Timestamp | None = None,
) -> tuple[list[dict], pd.DataFrame, dict[int, pd.DataFrame]]:
    """Ejecuta las 8 variantes del GRID y devuelve filas, matriz diaria y trades."""
    baseline = ea_us100.params_from_set(values)
    keys = list(ea_us100.GRID)
    combos = [
        dict(zip(keys, combo))
        for combo in itertools.product(*(ea_us100.GRID[key] for key in keys))
    ]
    rows: list[dict] = []
    series: dict[int, pd.Series] = {}
    trades_map: dict[int, pd.DataFrame] = {}
    for index, patch in enumerate(combos):
        params = dict(baseline)
        params.update(patch)
        trades = engine.run(frame, params)
        if trade_start is not None and trades is not None and len(trades):
            trades = trades[pd.to_datetime(trades["t"]) >= trade_start].copy()
        trades_map[index] = trades
        series[index] = ea_us100._daily_r(trades, days) * RISK
        rows.append({"index": index, **patch, **ea_us100._stats(trades)})
    matrix = pd.DataFrame(series, index=days).fillna(0.0)
    return rows, matrix, trades_map


def _year_rows(trades: pd.DataFrame) -> list[dict]:
    if trades is None or len(trades) == 0:
        return []
    stamp = pd.to_datetime(trades["t"])
    rows = []
    for year in sorted(stamp.dt.year.unique()):
        subset = trades[stamp.dt.year == year]
        rows.append({"year": int(year), **ea_us100._stats(subset)})
    return rows


def _summarize(
    name: str,
    label: str,
    frame: pd.DataFrame,
    values: dict,
    days: pd.DatetimeIndex,
    *,
    trade_start: pd.Timestamp | None = None,
) -> dict:
    rows, matrix, trades_map = _run_grid(frame, values, days, trade_start=trade_start)
    baseline_index = ea_us100._baseline_index(rows)
    base_returns = matrix[baseline_index]
    local_srs = [period_sharpe(matrix[column]) for column in matrix.columns]
    dsr = dsr_from_returns(
        base_returns,
        local_srs,
        len(local_srs),
        periods_per_year=252.0,
    )
    variants = []
    for row in rows:
        index = int(row["index"])
        sr_period = period_sharpe(matrix[index])
        variants.append(
            {
                **row,
                "sr_period": sr_period,
                "sr_annual": sr_period * math.sqrt(252.0),
            }
        )
    baseline_trades = trades_map[baseline_index]
    first_trade = (
        str(pd.to_datetime(baseline_trades["t"]).min())
        if baseline_trades is not None and len(baseline_trades)
        else None
    )
    last_trade = (
        str(pd.to_datetime(baseline_trades["t"]).max())
        if baseline_trades is not None and len(baseline_trades)
        else None
    )
    nonzero = int((base_returns != 0).sum())
    return {
        "name": name,
        "label": label,
        "bars": {
            "rows": int(len(frame)),
            "start": str(frame.index.min()),
            "end": str(frame.index.max()),
        },
        "days": {
            "n": int(len(days)),
            "start": str(days.min()) if len(days) else None,
            "end": str(days.max()) if len(days) else None,
        },
        "baseline_index": baseline_index,
        "baseline": variants[baseline_index],
        "variants": variants,
        "dsr_local": dsr,
        "years": _year_rows(baseline_trades),
        "_returns": base_returns,
        "trades": {
            "first": first_trade,
            "last": last_trade,
            "nonzero_days": nonzero,
            "zero_days": int(len(base_returns) - nonzero),
        },
    }


def _count_tests_readonly(db_path: Path) -> dict:
    con = _ro_connect(db_path)
    components = {
        "lesson_tests": int(con.execute("SELECT COUNT(*) AS n FROM lesson_tests").fetchone()["n"]),
        "optimization_trials": int(
            con.execute("SELECT COUNT(*) AS n FROM optimization_trials").fetchone()["n"]
        ),
        "holdout_reads": int(
            con.execute("SELECT COUNT(*) AS n FROM holdout_reads").fetchone()["n"]
        ),
        "strategy_trials_counted": int(
            con.execute(
                "SELECT COUNT(*) AS n FROM strategy_trials WHERE counted = 1"
            ).fetchone()["n"]
        ),
        "campaign_registry_n_total": 0,
        "lifecycle_bots_frozen": 0,
    }
    if con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='campaign_registry'"
    ).fetchone():
        components["campaign_registry_n_total"] = int(
            con.execute(
                "SELECT COALESCE(SUM(n_total), 0) AS n FROM campaign_registry"
            ).fetchone()["n"]
        )
    if con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='lifecycle_bots'"
    ).fetchone():
        components["lifecycle_bots_frozen"] = int(
            con.execute(
                "SELECT COUNT(*) AS n FROM lifecycle_bots WHERE frozen_at IS NOT NULL"
            ).fetchone()["n"]
        )
    if con.total_changes != 0:
        raise RuntimeError(f"la conexión de solo lectura escribió {con.total_changes} filas")
    con.close()
    return {"total": int(sum(components.values())), "components": components}


def _json_value(value, default):
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or "null")
    except (TypeError, ValueError):
        return default


def _add_item(
    items: list[dict],
    *,
    sr_period,
    periods_per_year,
    source: str,
    key: str,
    frequency: str | None = None,
) -> None:
    if sr_period is None or periods_per_year is None:
        return
    freq = frequency or (DAILY if float(periods_per_year) <= 366.0 else INTRADAY)
    items.append(
        {
            "sr_period": float(sr_period),
            "periods_per_year": float(periods_per_year),
            "frequency": freq,
            "source": source,
            "key": key,
        }
    )


def _collect_daily_srs_readonly(db_path: Path) -> list[dict]:
    """Replica ``global_srs(db, 'daily')`` sin abrir la base en escritura."""
    items: list[dict] = []
    con = _ro_connect(db_path)
    for row in con.execute(
        "SELECT id, source, params, result, sr_period, periods_per_year "
        "FROM strategy_trials"
    ):
        params = _json_value(row["params"], {})
        result = _json_value(row["result"], {})
        timeframe = params.get("timeframe") if isinstance(params, dict) else None
        periods = periods_for_timeframe(timeframe)
        sr_period = row["sr_period"]
        if sr_period is not None:
            periods = float(row["periods_per_year"] or periods or 0.0) or None
        else:
            sr_annual = result.get("sharpe") if isinstance(result, dict) else None
            sr_period = sr_from_annual(sr_annual, periods)
        _add_item(
            items,
            sr_period=sr_period,
            periods_per_year=periods,
            source=f"strategy_trials:{row['source'] or 'sin fuente'}",
            key=f"strategy_trials:{row['id']}",
            frequency=frequency_for_timeframe(timeframe),
        )
    for row in con.execute(
        "SELECT id, sr_period, periods_per_year FROM optimization_trials"
    ):
        _add_item(
            items,
            sr_period=row["sr_period"],
            periods_per_year=row["periods_per_year"],
            source="optimization_trials",
            key=f"optimization_trials:{row['id']}",
        )
    if con.total_changes != 0:
        raise RuntimeError(f"la conexión de solo lectura escribió {con.total_changes} filas")
    con.close()

    latest = ROOT / "reports" / "research" / "latest.json"
    if latest.exists():
        payload = json.loads(latest.read_text(encoding="utf-8"))
        for index, row in enumerate(payload.get("results") or []):
            if not isinstance(row, dict):
                continue
            _add_item(
                items,
                sr_period=sr_from_annual(row.get("sharpe"), 252.0),
                periods_per_year=252.0,
                source="research_report",
                key=f"research:{index}",
                frequency=DAILY,
            )

    if V3_JSON.exists():
        payload = json.loads(V3_JSON.read_text(encoding="utf-8"))
        _add_item(
            items,
            sr_period=sr_from_annual(payload.get("sharpe"), 252.0),
            periods_per_year=252.0,
            source="ea_report",
            key=EA_REPORT_KEY,
            frequency=DAILY,
        )

    seen: set[str] = set()
    for path in (ROOT / "reports" / "research").glob("intraday*/*/*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        timeframe = payload.get("timeframe")
        periods = periods_for_timeframe(timeframe)
        if periods is None:
            continue
        run_id = str(payload.get("run_id") or path.stem)
        for row in payload.get("outcomes") or []:
            if not isinstance(row, dict):
                continue
            metrics = row.get("metrics") or {}
            key = (
                f"intraday:{run_id}:{row.get('strategy')}:"
                f"{json.dumps(row.get('params') or {}, sort_keys=True)}"
            )
            if key in seen:
                continue
            seen.add(key)
            _add_item(
                items,
                sr_period=sr_from_annual(metrics.get("sharpe"), periods),
                periods_per_year=periods,
                source="intraday_report",
                key=key,
                frequency=frequency_for_timeframe(timeframe),
            )
    return [item for item in items if item["frequency"] == DAILY]


def _global_dsr(returns: pd.Series, srs: list[float], n_trials: int) -> dict:
    return dsr_from_returns(returns, srs, n_trials, periods_per_year=252.0)


def _replace_ea_sr(items: list[dict], annual_sr: float) -> list[float]:
    values = []
    for item in items:
        if item["key"] == EA_REPORT_KEY:
            values.append(float(annual_sr) / math.sqrt(252.0))
        else:
            values.append(item["sr_period"])
    return values


def _us100_groups(db_path: Path, daily_keys: set[str]) -> list[dict]:
    con = _ro_connect(db_path)
    rows = con.execute(
        "SELECT id, family, source, params, result, window_start, window_end, counted "
        "FROM strategy_trials WHERE symbol LIKE '%US100%' ORDER BY id"
    ).fetchall()
    if con.total_changes != 0:
        raise RuntimeError(f"la conexión de solo lectura escribió {con.total_changes} filas")
    con.close()

    grouped: dict[tuple, dict] = {}
    for row in rows:
        start = _naive_ts(row["window_start"])
        if start is None or start >= WINDOW_START:
            continue
        params = _json_value(row["params"], {})
        result = _json_value(row["result"], {})
        timeframe = params.get("timeframe") if isinstance(params, dict) else None
        is_grid = (
            row["source"] == "sweep"
            and int(row["counted"] or 0) == 1
            and isinstance(params, dict)
            and isinstance(result, dict)
            and all(name in params for name in ("min_score", "rr", "gap_min", "max_consec"))
            and "n" in result
        )
        kind = "variante_grid" if is_grid else "resumen"
        key = (
            row["family"],
            row["source"],
            timeframe,
            str(row["window_start"]),
            str(row["window_end"]),
            int(row["counted"] or 0),
            kind,
        )
        item = grouped.setdefault(
            key,
            {
                "family": row["family"],
                "source": row["source"],
                "timeframe": timeframe,
                "tf_label": "M5" if row["family"] == "US100_FTMO_CONFLUENCE" else timeframe,
                "kind": kind,
                "window_start": str(row["window_start"]),
                "window_end": str(row["window_end"]),
                "counted": int(row["counted"] or 0),
                "rows": 0,
                "ids": [],
                "en_dsr_diario": 0,
                "cache_ea": False,
            },
        )
        item["rows"] += 1
        item["ids"].append(int(row["id"]))
        if f"strategy_trials:{row['id']}" in daily_keys:
            item["en_dsr_diario"] += 1
        if row["family"] == "US100_FTMO_CONFLUENCE":
            item["cache_ea"] = True

    out = []
    for item in grouped.values():
        family = item["family"]
        if family == "US100_FTMO_CONFLUENCE" and item["kind"] == "variante_grid":
            motivo = "8 variantes M5 del EA; SR recalculados en la auditoría"
            recalculado = True
        elif family == "US100_FTMO_CONFLUENCE":
            motivo = "resumen/informe de robustez; no añade una serie al DSR"
            recalculado = False
        elif item["en_dsr_diario"]:
            motivo = "D1 nativo construido desde H4 (campaign.py); no usa la caché M5 del EA"
            recalculado = False
        elif item["timeframe"] == "H4":
            motivo = "H4: frecuencia intraday; no entra en la dispersión diaria"
            recalculado = False
        elif family == "TREND_DAILY_ATR":
            motivo = "counted=0 y sin sharpe de primer nivel; excluido"
            recalculado = False
        else:
            motivo = "sin timeframe/sr_period: global_srs lo excluye de la dispersión diaria"
            recalculado = False
        out.append({**item, "motivo": motivo, "recalculado_m5": recalculado})
    out.sort(key=lambda item: (item["family"], item["source"], item["window_start"]))
    return out


def _md_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return lines


def _fmt(value, digits: int = 2) -> str:
    if value is None:
        return "Sin datos"
    if isinstance(value, bool):
        return "sí" if value else "no"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _dd(value, digits: int = 1) -> str:
    if value is None:
        return "Sin datos"
    return f"-{abs(float(value)):.{digits}f}"


def _render(payload: dict) -> str:
    scenarios = payload["scenarios"]
    registered = payload["v3_registered"]
    global_dsr = payload["global_dsr"]
    lines = [
        "# Auditoría M5-only · EA `us100-ftmo1`",
        "",
        f"Generado: {payload['generated_at']} · **solo lectura, sin trials nuevos**",
        "",
        f"- Caché: `{payload['granularity']['cache']}`",
        f"- Setfile: `{payload['setfile']['path']}`",
        "- Ventana auditada: **2021-10-01 → 2026-11-13 16:45**",
        f"- `count_tests`: **{payload['count_tests']['total']}** antes y después "
        f"(sin cambios; {payload['db']['writes']} escrituras propias en `data/lab.db`)",
        f"- Cambios externos en `data/lab.db` durante la ejecución: "
        f"**{payload['db']['external_changes'] or 'ninguno'}**",
        "- Motor: `ea_us100_engine.py` actual (v3.2, incluye filtro de festivos NYSE)",
        "",
        "## 1. Granularidad de la caché",
        "",
    ]
    gran = payload["granularity"]
    lines += _md_table(
        ["Segmento", "Fechas", "Filas", "Δ mínimo", "Δ máximo", "Δ dominante", "% 5 min"],
        [
            [
                segment["label"],
                f"{segment['start']} → {segment['end']}",
                str(segment["rows"]),
                str(segment["min_diff"]),
                str(segment["max_diff"]),
                ", ".join(f"{item['delta']} ({item['n']})" for item in segment["top_diffs"]),
                _fmt(segment["share_5min"], 1) if segment["share_5min"] is not None else "Sin datos",
            ]
            for segment in gran["segments"]
        ],
    )
    lines += [
        "",
        f"- Duplicados: **{gran['duplicates']}** · OHLC inválidas en M5: **{gran['invalid_ohlc_m5']}** "
        f"· OHLC ausentes en M5: **{gran['missing_ohlc']}**",
        f"- En el tramo M5, el **{_fmt((gran['m5_share'] or 0) * 100, 1)} %** de los saltos son de 5 min; "
        f"el mínimo es **{gran['m5_min_diff']}**. La caché mezcla D1 (2018-2020), H1 (ene-sep 2021) y M5 "
        "(desde 2021-09-14). `ea_us100_engine.run` no detecta granularidad.",
        "",
        "## 2. Comparación de escenarios",
        "",
    ]
    lines += _md_table(
        [
            "Escenario",
            "Barras",
            "Días RTH",
            "n_obs",
            "Ops",
            "Win %",
            "PF",
            "Exp R",
            "Total R",
            "DD R",
            "DSR local",
        ],
        [
            [
                "v3 registrado",
                str(registered["bars"]["rows"]),
                "1.500",
                "1.500",
                str(int(registered["baseline"]["n"])),
                _fmt(registered["baseline"]["win"], 1),
                _fmt(registered["baseline"]["pf"], 2),
                f"{registered['baseline']['expR']:+.3f}",
                f"{registered['baseline']['totR']:+.1f}",
                _dd(registered["baseline"]["maxDD_R"]),
                _fmt(registered["dsr"]["local"], 6),
            ],
            *[
                [
                    scenario["label"],
                    str(scenario["bars"]["rows"]),
                    str(scenario["days"]["n"]),
                    str(scenario["dsr_local"]["n_obs"]),
                    str(int(scenario["baseline"]["n"])),
                    _fmt(scenario["baseline"]["win"], 1),
                    _fmt(scenario["baseline"]["pf"], 2),
                    f"{scenario['baseline']['expR']:+.3f}",
                    f"{scenario['baseline']['totR']:+.1f}",
                    _dd(scenario["baseline"]["maxDD_R"]),
                    _fmt(scenario["dsr_local"]["dsr"], 6),
                ]
                for scenario in scenarios.values()
            ],
        ],
    )
    lines += [
        "",
        "> El v3 registrado usa el motor anterior al filtro de festivos v3.2; por eso no es "
        "directamente comparable con las otras filas. La fila `Caché mixta completa (motor actual)` "
        "es la referencia reproducible del motor que corre hoy.",
        "",
        "### Operaciones y R por año",
        "",
    ]
    years = sorted(
        {
            int(item["year"])
            for scenario in scenarios.values()
            for item in scenario["years"]
        }
        | {int(item["year"]) for item in registered["years"]}
    )
    year_rows = []
    for year in years:
        row = [str(year)]
        reg = next((item for item in registered["years"] if int(item["year"]) == year), None)
        row += [str(int(reg["trades"])) if reg else "Sin datos", f"{reg['total_r']:+.1f}" if reg else "Sin datos"]
        for scenario in scenarios.values():
            item = next(
                (entry for entry in scenario["years"] if int(entry["year"]) == year),
                None,
            )
            row += [
                str(int(item["n"])) if item else "Sin datos",
                f"{item['totR']:+.1f}" if item else "Sin datos",
            ]
        year_rows.append(row)
    lines += _md_table(
        ["Año", "v3 ops", "v3 R", "full ops", "full R", "strict ops", "strict R", "warm ops", "warm R"],
        year_rows,
    )
    lines += ["", "### DD máximo por año (R)", ""]
    dd_rows = []
    for year in years:
        row = [str(year)]
        reg = next((item for item in registered["years"] if int(item["year"]) == year), None)
        row.append(_dd(reg["dd_r"]) if reg else "Sin datos")
        for scenario in scenarios.values():
            item = next(
                (entry for entry in scenario["years"] if int(entry["year"]) == year),
                None,
            )
            row.append(_dd(item["maxDD_R"]) if item else "Sin datos")
        dd_rows.append(row)
    lines += _md_table(["Año", "v3 DD", "full DD", "strict DD", "warm DD"], dd_rows)

    lines += [
        "",
        "## 3. Sharpes de las 8 variantes del EA",
        "",
        "Las 8 variantes se recalcularon con la misma matriz diaria del DSR local. "
        "`strategy_trials` no guardó `sr_period` para estas filas, así que la referencia "
        "es el recálculo sobre la caché completa con el motor actual.",
        "",
    ]
    variant_rows = []
    full = scenarios["full"]
    strict = scenarios["strict"]
    warm = scenarios["warmup"]
    for position in range(len(full["variants"])):
        f_row = full["variants"][position]
        s_row = strict["variants"][position]
        w_row = warm["variants"][position]
        variant_rows.append(
            [
                str(position),
                _fmt(f_row["rr"], 2),
                _fmt(f_row["gap_min"], 1),
                str(int(f_row["max_consec"])),
                _fmt(f_row["sr_annual"], 3),
                _fmt(s_row["sr_annual"], 3),
                f"{s_row['sr_annual'] - f_row['sr_annual']:+.3f}",
                _fmt(w_row["sr_annual"], 3),
            ]
        )
    lines += _md_table(
        ["#", "RR", "gap", "consec", "SR full", "SR strict", "Δ strict", "SR warmup"],
        variant_rows,
    )
    ea_full = full["baseline"]
    ea_strict = strict["baseline"]
    ea_warm = warm["baseline"]
    lines += [
        "",
        f"- Serie base (`ea_report`, 1 serie): SR anual **{_fmt(ea_full['sr_annual'], 3)}** "
        f"(full) → **{_fmt(ea_strict['sr_annual'], 3)}** (strict) → "
        f"**{_fmt(ea_warm['sr_annual'], 3)}** (warmup). v3 registrado: "
        f"**{_fmt(payload['v3_registered']['sharpe'], 3)}**.",
        "",
        "## 4. DSR global antes y después",
        "",
    ]
    global_rows = [
        [
            item["label"],
            str(item["n_obs"]),
            _fmt(item["annualized_sr"], 3),
            str(item["n_series"]),
            str(item["n_trials"]),
            _fmt(item["dsr"], 6),
        ]
        for item in global_dsr["rows"]
    ]
    lines += _md_table(
        ["Escenario", "n_obs", "SR anual", "Series", "N trials", "DSR global"],
        global_rows,
    )
    lines += ["", "### Descomposición del cambio", ""]
    lines += _md_table(
        ["Paso", "DSR global", "Δ"],
        [
            [
                item["label"],
                _fmt(item["dsr"], 6),
                "—" if item["delta"] is None else f"{item['delta']:+.6f}",
            ]
            for item in global_dsr["decomposition"]
        ],
    )
    lines += [
        "",
        f"- El v3 registrado (**{_fmt(global_dsr['registered']['dsr'], 6)}**) se reproduce como "
        f"**{_fmt(global_dsr['reproduced']['dsr'], 6)}** si se fija la SR de la serie base al valor v3 "
        f"(Δ {global_dsr['reproduced']['delta']:+.6f}). La mayor parte de la diferencia con el DSR "
        f"actual ({_fmt(global_dsr['current']['dsr'], 6)}) es el filtro de festivos v3.2; la "
        "granularidad añade el resto (ver descomposición).",
        f"- Reemplazar solo la SR de `ea_report` en la dispersión mueve el global "
        f"**{_fmt(global_dsr['dispersion_only']['dsr'], 6)}** (Δ "
        f"{global_dsr['dispersion_only']['delta']:+.6f}): las otras 32 series US100 son D1 nativas.",
        f"- Limpiar la caché y acortar la serie base lleva el global a "
        f"**{_fmt(global_dsr['strict']['dsr'], 6)}** (strict) o "
        f"**{_fmt(global_dsr['warmup']['dsr'], 6)}** (warmup). Sigue por debajo de 0,90: el gate global falla.",
        "",
        "## 5. Trials US100 con ventana anterior a 2021-10-01",
        "",
    ]
    trial_rows = [
        [
            f"`{item['family']}`",
            str(item["rows"]),
            f"{item['window_start']} → {item['window_end']}",
            item.get("tf_label") or "—",
            str(item["counted"]),
            "sí" if item["en_dsr_diario"] else "no",
            "sí" if item["cache_ea"] else "no",
            item["motivo"],
        ]
        for item in payload["us100_trials"]
    ]
    trial_rows.append(
        [
            "`ea_report`",
            "1",
            "2017-12-28 → 2026-11-13",
            "M5 mixta",
            "—",
            "sí",
            "sí",
            "SR recalculado; única serie US100 de la dispersión que usa la caché mixta",
        ]
    )
    lines += _md_table(
        ["Grupo", "Filas", "Ventana", "TF", "counted", "¿Dispersión diaria?", "¿Caché EA?", "Acción"],
        trial_rows,
    )
    lines += [
        "",
        f"- Filas US100 con ventana anterior a 2021-10-01: **{payload['us100_summary']['rows']}**; "
        f"en la dispersión diaria: **{payload['us100_summary']['in_daily']}**; "
        f"recalculadas sobre M5: **{payload['us100_summary']['recalculated']}**.",
        "- Las 32 celdas `campaign` D1 se construyen desde H4 (`campaign.py`), no desde la caché M5 del EA. "
        "Las filas `ORB_NY`/`TREND_INTRADAY`/`TREND` H4 no entran en la dispersión diaria por falta de "
        "`timeframe`/`sr_period` o por ser H4.",
        "",
        "## 6. Conclusiones",
        "",
        "1. **La caché no es M5 homogénea.** 2018-2020 son D1, enero-septiembre 2021 son H1 y el M5 real "
        "empieza el 2021-09-14. El motor no detecta granularidad; las velas D1/H1 se procesan como si "
        "fueran M5.",
        "2. **El DSR local no cambia de conclusión.** 0,999362 (v3) → 0,999481 (strict) → 0,999577 "
        "(warmup). Sigue aprobando el criterio informativo local.",
        "3. **El total R cambia poco.** v3 +143,2 R; motor actual full +150,4 R; strict +145,9 R; "
        "warmup +146,9 R. Entre full, strict y warmup, 2022-2025 son idénticos; el año 2021 es el "
        "sensible al corte del 2021-10-01 (+4,6 R → +0,1 R) y 2026 coincide al mismo corte. La "
        "diferencia v3 vs full en 2025-2026 son las 4 operaciones de festivos que filtra v3.2.",
        "4. **El DSR global sigue fallando.** Actual 0,706211 → strict 0,740171 → warmup 0,749774, "
        "todos < 0,90. El 0,634293 registrado se reproduce exactamente (0,634287) fijando la SR v3; "
        "la diferencia es el filtro de festivos v3.2, no la granularidad.",
        "5. **Solo 1 de las 33 series US100 diarias usa la caché mixta.** Las 32 `campaign` D1 son "
        "nativas. Los trials `ORB_NY`/`TREND_INTRADAY`/`TREND` H4 no entran en la dispersión diaria. "
        "Por eso reemplazar los Sharpes US100 apenas mueve el global (−0,002): el cambio viene de la "
        "serie base, no de la dispersión.",
        "6. **Veredicto:** la auditoría no rescata el EA. El gate global sigue fallando y el local sigue "
        "aprobando; la conclusión `NO PASA` se mantiene.",
        "",
        "## Aviso",
        "",
        "- El motor actual ya no reproduce el v3 registrado (480 ops, +143,2 R, 0,634293): el filtro de "
        "festivos v3.2 elimina 4 operaciones y sube la SR. La comparación limpia es contra la fila "
        "`Caché mixta completa (motor actual)`.",
        "- No se ha ejecutado `lab campaign run`, `research`, `research-intraday` ni `research-swing`; "
        "no se ha insertado nada en `strategy_trials`, `optimization_trials`, `holdout_reads` ni "
        "`campaign_registry`.",
        "- Todas las conexiones a `data/lab.db` son `mode=ro` con `PRAGMA query_only=ON`; "
        "`total_changes=0` en cada una. `count_tests` sigue en "
        f"**{payload['count_tests']['total']}** y las tablas auditadas no cambiaron. "
        "Si el SHA-256 del archivo cambió, fue por un proceso externo (se registra arriba).",
        "",
    ]
    return "\n".join(lines)


def main() -> dict:
    started = datetime.now(timezone.utc)
    db_before = _db_state()
    count_before = _count_tests_readonly(DB)
    tables_before = _table_counts(DB)

    cache = pd.read_parquet(CACHE)
    cache.index = pd.DatetimeIndex(cache.index)
    cache = cache.loc[:V3_END]
    values = ea_us100.load_setfile(SETFILE)

    granularity = _granularity(cache)
    full_frame = cache
    strict_frame = cache.loc[WINDOW_START:]
    warm_frame = cache.loc[M5_START:]
    warm_days = _rth_days(warm_frame.loc[WINDOW_START:])

    scenarios = {
        "full": _summarize(
            "full",
            "Caché mixta completa (motor actual)",
            full_frame,
            values,
            _rth_days(full_frame),
        ),
        "strict": _summarize(
            "strict",
            "M5 real desde 2021-10-01",
            strict_frame,
            values,
            _rth_days(strict_frame),
        ),
        "warmup": _summarize(
            "warmup",
            "M5 real desde 2021-09-14, ops desde 2021-10-01",
            warm_frame,
            values,
            warm_days,
            trade_start=WINDOW_START,
        ),
    }

    v3 = json.loads(V3_JSON.read_text(encoding="utf-8"))
    robustness = json.loads(ROBUSTNESS_JSON.read_text(encoding="utf-8"))
    registered = {
        "bars": v3["bars"],
        "window": robustness["window"],
        "baseline": v3["baseline"],
        "years": robustness["years"],
        "dsr": {
            "local": v3["dsr_local"],
            "global": v3["dsr_global"],
            "n_trials": v3["n_trials"],
            "n_series_global": v3["dsr_global_meta"]["n_series"],
        },
        "sharpe": v3["sharpe"],
    }

    daily_items = _collect_daily_srs_readonly(DB)
    daily_keys = {item["key"] for item in daily_items}
    all_srs = [item["sr_period"] for item in daily_items]
    us500_keys = {f"strategy_trials:{index}" for index in range(1710, 1718)}
    srs_653 = [
        item["sr_period"]
        for item in daily_items
        if item["key"] not in us500_keys
    ]

    # La matriz diaria no se serializa; se guarda aparte para el DSR global.
    full_series = scenarios["full"].pop("_returns")
    strict_series = scenarios["strict"].pop("_returns")
    warm_series = scenarios["warmup"].pop("_returns")

    strict_annual = period_sharpe(strict_series) * math.sqrt(252.0)
    warm_annual = period_sharpe(warm_series) * math.sqrt(252.0)
    full_annual = period_sharpe(full_series) * math.sqrt(252.0)

    registered_sr = sr_from_annual(v3["sharpe"], 252.0)
    adjusted = full_series - full_series.mean() + registered_sr * full_series.std(ddof=1)
    reproduced = _global_dsr(adjusted, srs_653, 1042)
    current = _global_dsr(full_series, all_srs, count_before["total"])
    strict = _global_dsr(strict_series, _replace_ea_sr(daily_items, strict_annual), count_before["total"])
    warmup = _global_dsr(warm_series, _replace_ea_sr(daily_items, warm_annual), count_before["total"])
    dispersion_only = _global_dsr(
        full_series, _replace_ea_sr(daily_items, strict_annual), count_before["total"]
    )
    returns_only = _global_dsr(strict_series, all_srs, count_before["total"])
    strict_653 = _global_dsr(
        strict_series,
        _replace_ea_sr(
            [item for item in daily_items if item["key"] not in us500_keys],
            strict_annual,
        ),
        1042,
    )
    current_653 = _global_dsr(full_series, srs_653, 1042)

    global_dsr = {
        "registered": {
            "label": "Registrado v3 (histórico)",
            "dsr": v3["dsr_global"],
            "n_trials": v3["n_trials"],
            "n_series": v3["dsr_global_meta"]["n_series"],
            "n_obs": v3["dsr_global_meta"]["n_obs"],
            "annualized_sr": v3["sharpe"],
        },
        "reproduced": {
            "label": "v3 reproducido (SR ajustada al v3)",
            "dsr": reproduced["dsr"],
            "n_trials": 1042,
            "n_series": len(srs_653),
            "n_obs": reproduced["n_obs"],
            "annualized_sr": reproduced["annualized_sr"],
            "delta": (reproduced["dsr"] or 0.0) - v3["dsr_global"],
        },
        "current": {
            "label": "Actual antes (motor v3.2, caché mixta)",
            "dsr": current["dsr"],
            "n_trials": count_before["total"],
            "n_series": len(all_srs),
            "n_obs": current["n_obs"],
            "annualized_sr": full_annual,
        },
        "strict": {
            "label": "Después strict (M5 desde 2021-10-01)",
            "dsr": strict["dsr"],
            "n_trials": count_before["total"],
            "n_series": len(all_srs),
            "n_obs": strict["n_obs"],
            "annualized_sr": strict_annual,
        },
        "warmup": {
            "label": "Después warmup (M5 desde 2021-09-14)",
            "dsr": warmup["dsr"],
            "n_trials": count_before["total"],
            "n_series": len(all_srs),
            "n_obs": warmup["n_obs"],
            "annualized_sr": warm_annual,
        },
        "dispersion_only": {
            "label": "Solo dispersión (misma serie, SR ea nueva)",
            "dsr": dispersion_only["dsr"],
            "n_trials": count_before["total"],
            "n_series": len(all_srs),
            "n_obs": dispersion_only["n_obs"],
            "annualized_sr": full_annual,
            "delta": (dispersion_only["dsr"] or 0.0) - (current["dsr"] or 0.0),
        },
        "returns_only": {
            "label": "Solo retornos (serie strict, SR ea vieja)",
            "dsr": returns_only["dsr"],
            "n_trials": count_before["total"],
            "n_series": len(all_srs),
            "n_obs": returns_only["n_obs"],
            "annualized_sr": strict_annual,
            "delta": (returns_only["dsr"] or 0.0) - (strict["dsr"] or 0.0),
        },
        "strict_653": {
            "label": "Sensibilidad strict + 653 series + N=1042",
            "dsr": strict_653["dsr"],
            "n_trials": 1042,
            "n_series": len(srs_653),
            "n_obs": strict_653["n_obs"],
            "annualized_sr": strict_annual,
        },
        "current_653": {
            "label": "Actual con 653 series + N=1042",
            "dsr": current_653["dsr"],
            "n_trials": 1042,
            "n_series": len(srs_653),
            "n_obs": current_653["n_obs"],
            "annualized_sr": full_annual,
        },
        "decomposition": [
            {
                "label": "v3 registrado",
                "dsr": v3["dsr_global"],
                "delta": None,
            },
            {
                "label": "+ filtro de festivos v3.2 (653 series, N=1042)",
                "dsr": current_653["dsr"],
                "delta": (current_653["dsr"] or 0.0) - v3["dsr_global"],
            },
            {
                "label": "+ 8 series US500 y N=1060",
                "dsr": current["dsr"],
                "delta": (current["dsr"] or 0.0) - (current_653["dsr"] or 0.0),
            },
            {
                "label": "+ M5-only strict (661 series, N=1060)",
                "dsr": strict["dsr"],
                "delta": (strict["dsr"] or 0.0) - (current["dsr"] or 0.0),
            },
        ],
        "rows": [],
    }
    global_dsr["rows"] = [
        global_dsr[key]
        for key in ("registered", "reproduced", "current", "strict", "warmup", "strict_653")
    ]

    us100_trials = _us100_groups(DB, daily_keys)
    us100_rows = sum(item["rows"] for item in us100_trials)
    us100_in_daily = sum(item["en_dsr_diario"] for item in us100_trials) + 1
    us100_recalc = sum(item["rows"] for item in us100_trials if item["recalculado_m5"]) + 1

    db_after = _db_state()
    count_after = _count_tests_readonly(DB)
    tables_after = _table_counts(DB)
    external_changes = {
        name: tables_after[name] - tables_before.get(name, 0)
        for name in tables_after
        if tables_after[name] != tables_before.get(name, 0)
    }
    audited_tables = {
        "lesson_tests",
        "optimization_trials",
        "holdout_reads",
        "strategy_trials",
        "campaign_registry",
        "lifecycle_bots",
    }
    audited_changes = {
        name: delta
        for name, delta in external_changes.items()
        if name in audited_tables
    }
    if count_before["total"] != count_after["total"]:
        raise RuntimeError("count_tests cambió durante la auditoría")
    if audited_changes:
        raise RuntimeError(f"tablas auditadas cambiaron: {audited_changes}")
    db_changed = db_before["sha256"] != db_after["sha256"]

    payload = {
        "audit": "ea_us100_m5_only",
        "generated_at": started.isoformat(timespec="seconds"),
        "read_only": True,
        "window": {
            "start": str(WINDOW_START),
            "end": str(V3_END),
            "m5_start": str(M5_START),
        },
        "setfile": {
            "path": str(SETFILE),
            "sha256": _sha256(SETFILE),
        },
        "db": {
            "before": db_before,
            "after": db_after,
            "changed": db_changed,
            "external_changes": external_changes,
            "audited_changes": audited_changes,
            "writes": 0,
            "our_connection_changes": 0,
        },
        "count_tests": {
            "before": count_before,
            "after": count_after,
            "total": count_after["total"],
        },
        "granularity": granularity,
        "v3_registered": registered,
        "scenarios": scenarios,
        "ea_variants": {
            "full": scenarios["full"]["variants"],
            "strict": scenarios["strict"]["variants"],
            "warmup": scenarios["warmup"]["variants"],
        },
        "global_dsr": global_dsr,
        "us100_trials": us100_trials,
        "us100_summary": {
            "rows": us100_rows,
            "in_daily": us100_in_daily,
            "recalculated": us100_recalc,
        },
    }

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = AUDIT_DIR / "ea_us100_m5_only.json"
    md_path = AUDIT_DIR / "ea_us100_m5_only.md"
    json_path.write_text(
        json.dumps(_jsonable(payload), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    md_path.write_text(_render(payload), encoding="utf-8")

    print(f"JSON: {json_path}")
    print(f"MD:   {md_path}")
    print(f"count_tests: {count_before['total']} → {count_after['total']}")
    print(f"db sha256: {db_before['sha256'][:16]}… → {db_after['sha256'][:16]}…")
    return payload


if __name__ == "__main__":
    main()
