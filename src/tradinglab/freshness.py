"""Frescura de datos: edad del último dato de cada símbolo y timeframe.

Cada fetch (yahoo, mt5, ticks) deja una fila en `data_freshness` con la
fecha del último dato, la hora de la descarga y la fuente. `check()` compara
esa edad con el umbral del timeframe y devuelve `ok`, `aviso` o `falla`.

Los umbrales viven en `config/ops.yaml -> freshness` cuando esa clave existe.
Si no existe se usan los valores por defecto de este módulo (documentados en
`docs/`), para no tocar el archivo congelado de F13.

Regla dura: **sin dato no hay apertura**. Un símbolo sin registro es `falla`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import CONFIG_DIR, DEFAULT_DB
from .db import connect, init_db

STATUS_OK = "ok"
STATUS_AVISO = "aviso"
STATUS_FALLA = "falla"

#: Umbrales por defecto: (aviso, falla) en segundos desde la última descarga.
DEFAULT_THRESHOLDS: dict[str, tuple[float, float]] = {
    "1d": (24 * 3600.0, 48 * 3600.0),
    "1h": (3 * 3600.0, 8 * 3600.0),
    "M15": (900.0, 3600.0),
    "M5": (300.0, 1200.0),
    "M1": (120.0, 600.0),
    "default": (6 * 3600.0, 24 * 3600.0),
}


class FreshnessError(RuntimeError):
    pass


def _now(now: datetime | None = None) -> datetime:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _parse(stamp: Any) -> datetime | None:
    if stamp is None or stamp == "":
        return None
    if isinstance(stamp, datetime):
        value = stamp
    else:
        try:
            value = datetime.fromisoformat(str(stamp))
        except ValueError:
            return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def thresholds(config_path: Path | None = None) -> dict[str, tuple[float, float]]:
    """Umbrales por timeframe: `ops.yaml -> freshness` o los valores por defecto."""
    out = dict(DEFAULT_THRESHOLDS)
    path = Path(config_path) if config_path else CONFIG_DIR / "ops.yaml"
    if not path.exists():
        path = CONFIG_DIR / "lab.yaml"
    if not path.exists():
        return out
    try:
        import yaml

        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return out
    section = raw.get("freshness")
    if not isinstance(section, dict):
        return out
    for key, value in section.items():
        if isinstance(value, dict):
            aviso = float(value.get("aviso_s", DEFAULT_THRESHOLDS["default"][0]))
            falla = float(value.get("falla_s", DEFAULT_THRESHOLDS["default"][1]))
        else:
            aviso, falla = DEFAULT_THRESHOLDS["default"]
        out[str(key)] = (aviso, falla)
    return out


def active_pairs(config_dir: Path | None = None) -> list[tuple[str, str]]:
    """Pares (s?mbolo, timeframe) del universo que opera el laboratorio.

    Incluye bots deterministas, forward intrad?a, los tres estilos de
    ai_trader y el EA externo. `D1` se comprueba contra `H4` porque el carril
    IA deriva el diario de las velas H4.
    """
    base = Path(config_dir) if config_dir else CONFIG_DIR
    pairs: set[tuple[str, str]] = set()

    def add(symbol, timeframe) -> None:
        if not symbol or not timeframe:
            return
        tf = str(timeframe)
        pairs.add((str(symbol).strip().upper(), "H4" if tf.upper() == "D1" else tf))

    def load(name: str) -> dict:
        path = base / name
        if not path.exists():
            return {}
        try:
            import yaml

            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    bots = load("bots.yaml")
    for bot in bots.get("bots") or []:
        if not isinstance(bot, dict) or not bot.get("enabled"):
            continue
        timeframe = bot.get("timeframe", "1d")
        for symbol in bot.get("universe") or []:
            add(symbol, timeframe)

    forward = load("intraday_forward.yaml")
    for bot in forward.get("bots") or []:
        if not isinstance(bot, dict) or not bot.get("enabled"):
            continue
        add(bot.get("canonical_symbol"), bot.get("timeframe", "M15"))

    ai = load("ai_trader.yaml")
    if ai.get("enabled"):
        for style in (ai.get("styles") or {}).values():
            if not isinstance(style, dict) or not style.get("enabled"):
                continue
            allowed = style.get("allowed") or {}
            if isinstance(allowed, dict) and allowed:
                for symbol, strategies in allowed.items():
                    if isinstance(strategies, dict):
                        for timeframe in strategies.values():
                            add(symbol, timeframe)
                    elif isinstance(strategies, (list, tuple)):
                        for timeframe in strategies:
                            add(symbol, timeframe)
            else:
                timeframes = style.get("timeframes") or []
                for symbol in style.get("universe") or []:
                    for timeframe in timeframes:
                        add(symbol, timeframe)

    eas = load("mt5_eas.yaml")
    for ea in eas.get("eas") or []:
        if isinstance(ea, dict) and ea.get("enabled"):
            add(ea.get("symbol"), "M5")

    return sorted(pairs)


def doctor_status(
    now: datetime | None = None,
    *,
    db_path: str | Path | None = None,
    config_dir: Path | None = None,
) -> dict:
    """Resumen de frescura del universo activo para `lab doctor`."""
    pairs = active_pairs(config_dir)
    if not pairs:
        return {
            "status": "aviso",
            "fails": 0,
            "warns": 0,
            "total": 0,
            "detail": "sin universo activo",
        }
    states = [
        check(
            symbol,
            timeframe,
            now=now,
            db_path=db_path,
            config_path=(Path(config_dir) / "ops.yaml") if config_dir else None,
        )
        for symbol, timeframe in pairs
    ]
    fails = [item for item in states if item["status"] == STATUS_FALLA]
    warns = [item for item in states if item["status"] == STATUS_AVISO]
    status = STATUS_FALLA if fails else STATUS_AVISO if warns else STATUS_OK
    detail = f"{len(fails)}/{len(pairs)} fallan"
    visible = fails or warns
    if visible:
        sample = []
        for item in visible[:4]:
            last = (item.get("last_bar_utc") or "")[:10] or "sin datos"
            sample.append(f"{item['symbol']} {item['timeframe']} ({last})")
        detail += " ? " + ", ".join(sample)
    if warns and fails:
        detail += f" ? {len(warns)} avisos"
    return {
        "status": status,
        "fails": len(fails),
        "warns": len(warns),
        "total": len(pairs),
        "detail": detail[:220],
    }


def record(
    symbol: str,
    timeframe: str,
    *,
    last_bar_utc: datetime | str | None,
    fetched_at_utc: datetime | str | None = None,
    source: str = "desconocido",
    db_path: str | Path | None = None,
) -> None:
    """Deja constancia de una descarga. No rompe la descarga si falla el registro."""
    try:
        init_db(db_path or DEFAULT_DB)
        with connect(db_path or DEFAULT_DB) as con:
            con.execute(
                "INSERT INTO data_freshness"
                "(symbol, timeframe, last_bar_utc, fetched_at_utc, source, ts) "
                "VALUES(?,?,?,?,?,?)",
                (
                    str(symbol).upper(),
                    str(timeframe),
                    _iso(last_bar_utc),
                    _iso(fetched_at_utc) or _iso(datetime.now(timezone.utc)),
                    str(source),
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ),
            )
    except Exception:
        return


def _iso(value: datetime | str | None) -> str | None:
    parsed = _parse(value)
    return parsed.isoformat(timespec="seconds") if parsed else None


def latest(
    symbol: str, timeframe: str, *, db_path: str | Path | None = None
) -> dict | None:
    """Último registro de frescura de un símbolo y timeframe."""
    path = db_path or DEFAULT_DB
    if not Path(path).exists():
        return None
    try:
        with connect(path) as con:
            row = con.execute(
                "SELECT * FROM data_freshness WHERE symbol = ? AND timeframe = ? "
                "ORDER BY id DESC LIMIT 1",
                (str(symbol).upper(), str(timeframe)),
            ).fetchone()
    except Exception:
        return None
    return dict(row) if row else None


def check(
    symbol: str,
    timeframe: str,
    now: datetime | None = None,
    *,
    db_path: str | Path | None = None,
    config_path: Path | None = None,
) -> dict:
    """Estado de frescura: `ok`, `aviso` o `falla` (sin dato -> `falla`)."""
    moment = _now(now)
    limits = thresholds(config_path)
    aviso_s, falla_s = limits.get(
        str(timeframe), limits.get("default", DEFAULT_THRESHOLDS["default"])
    )
    row = latest(symbol, timeframe, db_path=db_path)
    base = {
        "symbol": str(symbol).upper(),
        "timeframe": str(timeframe),
        "checked_at": moment.isoformat(timespec="seconds"),
        "aviso_s": float(aviso_s),
        "falla_s": float(falla_s),
        "source": None,
        "last_bar_utc": None,
        "fetched_at_utc": None,
        "age_s": None,
    }
    if not row:
        base.update(
            {
                "status": STATUS_FALLA,
                "reason": "sin datos: nunca se registró una descarga de este símbolo",
            }
        )
        return base

    last_bar = _parse(row.get("last_bar_utc"))
    fetched = _parse(row.get("fetched_at_utc"))
    # La edad que manda es la de la DESCARGA: es la frecuencia esperada de
    # refresco. La edad de la barra se informa aparte (con datos diarios la
    # marca de la barra es a medianoche y daría falsos avisos).
    reference = fetched or last_bar
    age_s = (moment - reference).total_seconds() if reference else None
    bar_age_s = (moment - last_bar).total_seconds() if last_bar else None
    base.update(
        {
            "source": row.get("source"),
            "last_bar_utc": row.get("last_bar_utc"),
            "fetched_at_utc": row.get("fetched_at_utc"),
            "age_s": age_s,
            "bar_age_s": bar_age_s,
        }
    )
    if age_s is None:
        base.update(
            {"status": STATUS_FALLA, "reason": "sin datos: la descarga no tiene fecha"}
        )
        return base
    if age_s < 0:
        base.update(
            {
                "status": STATUS_AVISO,
                "reason": f"la descarga es futura ({age_s:.0f} s): revisa el reloj",
            }
        )
        return base
    if age_s > falla_s:
        base.update(
            {
                "status": STATUS_FALLA,
                "reason": f"datos viejos: {age_s / 60:.0f} min sin refrescar (falla a {falla_s / 60:.0f} min)",
            }
        )
        return base
    if age_s > aviso_s:
        base.update(
            {
                "status": STATUS_AVISO,
                "reason": f"datos retrasados: {age_s / 60:.0f} min sin refrescar (aviso a {aviso_s / 60:.0f} min)",
            }
        )
        return base
    base.update({"status": STATUS_OK, "reason": f"datos frescos: {age_s / 60:.1f} min"})
    return base


__all__ = [
    "DEFAULT_THRESHOLDS",
    "active_pairs",
    "doctor_status",
    "FreshnessError",
    "STATUS_AVISO",
    "STATUS_FALLA",
    "STATUS_OK",
    "check",
    "latest",
    "record",
    "thresholds",
]
