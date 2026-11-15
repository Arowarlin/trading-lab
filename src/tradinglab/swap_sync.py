"""Sincroniza el swap de MT5 con el bloque `swap` de costs.yaml.

Solo lectura en MT5. `--write` reemplaza únicamente el bloque `swap:` y
conserva el resto del YAML. Un modo de swap no soportado no se escribe: queda
provisional y se informa.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from .config import DEFAULT_DB, Settings, get_settings
from .intraday_costs import COSTS_PATH

SWAP_MODES = {
    0: ("percent_annual", "deshabilitado"),
    1: ("points", "puntos"),
    5: ("percent_annual", "interes_current"),
    6: ("percent_annual", "interes_open"),
}
UNSUPPORTED_MODES = {2: "moneda_symbol", 3: "moneda_margin", 4: "moneda_deposit"}


def _get(info, key: str, default=None):
    if isinstance(info, dict):
        return info.get(key, default)
    return getattr(info, key, default)


def _triple_weekday(info) -> int:
    """MT5 0=domingo; Python 0=lunes. Devuelve el día Python."""
    raw = int(_get(info, "swap_rollover3days", 3) or 3)
    return (raw - 1) % 7


def convert_symbol(symbol: str, info, read_at: str) -> dict:
    mode = int(_get(info, "swap_mode", -1))
    if mode not in SWAP_MODES:
        return {
            "symbol": str(symbol).upper(),
            "status": "no_soportado",
            "swap_mode": mode,
            "reason": UNSUPPORTED_MODES.get(mode, f"swap_mode {mode}"),
        }
    unit, label = SWAP_MODES[mode]
    return {
        "symbol": str(symbol).upper(),
        "status": "ok",
        "swap_mode": mode,
        "mode_label": label,
        "long": float(_get(info, "swap_long", 0.0) or 0.0),
        "short": float(_get(info, "swap_short", 0.0) or 0.0),
        "unit": unit,
        "triple_swap_weekday": _triple_weekday(info),
        "source": f"mt5.symbol_info {read_at}",
    }


def build_swap_payload(
    symbols: list[str],
    info_getter,
    *,
    read_at: str | None = None,
) -> dict:
    """Convierte `symbol_info` en el bloque swap; no escribe nada."""
    moment = read_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    items: dict[str, dict] = {}
    skipped: dict[str, dict] = {}
    for symbol in symbols:
        info = info_getter(str(symbol))
        if info is None:
            skipped[str(symbol).upper()] = {
                "status": "Sin datos",
                "reason": "symbol_info vacío",
            }
            continue
        converted = convert_symbol(symbol, info, moment)
        if converted["status"] == "ok":
            items[converted["symbol"]] = converted
        else:
            skipped[converted["symbol"]] = converted
    return {
        "read_at": moment,
        "symbols": items,
        "skipped": skipped,
        "n_read": len(items),
        "n_skipped": len(skipped),
    }


def render_swap_block(payload: dict) -> str:
    assets = {
        symbol: {
            "long": item["long"],
            "short": item["short"],
            "unit": item["unit"],
            "swap_mode": item["swap_mode"],
            "triple_swap_weekday": item["triple_swap_weekday"],
            "source": item["source"],
        }
        for symbol, item in sorted(payload["symbols"].items())
    }
    block = {
        "swap": {
            "unit": "percent_annual",
            "triple_swap_weekday": 2,
            "source": f"mt5.symbol_info {payload['read_at']}",
            "synced_at": payload["read_at"],
            "defaults": {"long": None, "short": None},
            "assets": assets,
        }
    }
    return yaml.safe_dump(block, sort_keys=False, allow_unicode=True)


def update_costs_yaml(path: str | Path, block: str) -> Path:
    """Reemplaza solo el bloque `swap:`; conserva comentarios y el resto."""
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    start = text.find("\nswap:\n")
    if start < 0 and text.startswith("swap:\n"):
        start = 0
    if start < 0:
        raise ValueError("costs.yaml no tiene bloque swap")
    next_key = text.find("\nslippage:\n", start + 1)
    if next_key < 0:
        next_key = len(text)
    body = block if block.endswith("\n") else block + "\n"
    prefix = "" if start == 0 else text[: start + 1]
    updated = prefix + body + text[next_key + 1 :]
    target.write_text(updated, encoding="utf-8")
    return target


def _costs_symbols(path: str | Path = COSTS_PATH) -> list[str]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return sorted(str(key).upper() for key in (data.get("assets") or {}))


def sync_swaps(
    *,
    settings: Settings | None = None,
    db_path: str | Path = DEFAULT_DB,
    write: bool = False,
    info_getter=None,
    costs_path: str | Path = COSTS_PATH,
    symbols: list[str] | None = None,
) -> dict:
    """Lee swap de MT5 o de un getter inyectado; escribe solo si `write`."""
    symbols = (
        [str(item).upper() for item in symbols]
        if symbols
        else _costs_symbols(costs_path)
    )
    if info_getter is None:
        from .execution import get_mt5_broker

        cfg = settings or get_settings()
        broker = get_mt5_broker(cfg, db_path, dry_run=True)
        broker.connect()
        try:
            import MetaTrader5 as mt5

            info_getter = mt5.symbol_info
            payload = build_swap_payload(symbols, info_getter)
        finally:
            broker.shutdown()
    else:
        payload = build_swap_payload(symbols, info_getter)
    payload["costs_path"] = str(costs_path)
    payload["written"] = False
    if write and payload["symbols"]:
        block = render_swap_block(payload)
        update_costs_yaml(costs_path, block)
        payload["written"] = True
    return payload


__all__ = [
    "SWAP_MODES",
    "UNSUPPORTED_MODES",
    "build_swap_payload",
    "convert_symbol",
    "render_swap_block",
    "sync_swaps",
    "update_costs_yaml",
]
