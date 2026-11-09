"""Alias canónico → símbolo del broker para el perfil intradía forex/CFD.

Los nombres exactos se descubren en MT5 (no se suponen) y se guardan en la
tabla `asset_aliases`. El guard del perfil `intraday_fx` rechaza aperturas de
cualquier símbolo fuera de este universo.
"""
from __future__ import annotations

from pathlib import Path

from .db import connect, init_db, utcnow

INTRADAY_FX_PROFILE = "intraday_fx"

# Canonical -> candidatos en el broker (el primero que exista gana).
UNIVERSE_CANDIDATES: dict[str, tuple[str, ...]] = {
    "NASDAQ": ("US100.cash", "NAS100.cash", "USTEC", "US100"),
    "XAUUSD": ("XAUUSD", "GOLD"),
    "EURUSD": ("EURUSD",),
    "USDJPY": ("USDJPY",),
}

ASSET_CLASSES: dict[str, str] = {
    "NASDAQ": "índice",
    "XAUUSD": "metales",
    "EURUSD": "forex",
    "USDJPY": "forex",
}


def canonical_symbols() -> tuple[str, ...]:
    return tuple(UNIVERSE_CANDIDATES)


def discover(
    db_path: str | Path,
    broker,
    *,
    profile: str = INTRADAY_FX_PROFILE,
    source: str = "mt5",
) -> dict[str, str]:
    """Consulta el broker y guarda el alias de cada activo del universo."""
    init_db(db_path)
    discovered: dict[str, str] = {}
    now = utcnow()
    with connect(db_path) as con:
        for canonical, candidates in UNIVERSE_CANDIDATES.items():
            symbol = None
            for candidate in candidates:
                try:
                    spec = broker.symbol_spec(candidate)
                    if spec and spec.get("symbol"):
                        symbol = str(spec["symbol"])
                        break
                except Exception:
                    continue
            if symbol is None:
                continue
            discovered[canonical] = symbol
            con.execute(
                "INSERT OR REPLACE INTO asset_aliases"
                "(canonical, broker_symbol, asset_class, profile, discovered_at, source) "
                "VALUES(?,?,?,?,?,?)",
                (
                    canonical,
                    symbol,
                    ASSET_CLASSES.get(canonical, "desconocido"),
                    profile,
                    now,
                    source,
                ),
            )
    return discovered


def aliases(
    db_path: str | Path,
    *,
    profile: str = INTRADAY_FX_PROFILE,
) -> list[dict]:
    init_db(db_path)
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT * FROM asset_aliases WHERE profile = ? ORDER BY canonical",
            (profile,),
        ).fetchall()
    return [dict(row) for row in rows]


def allowed_symbols(
    db_path: str | Path,
    *,
    profile: str = INTRADAY_FX_PROFILE,
) -> set[str]:
    return {str(row["broker_symbol"]) for row in aliases(db_path, profile=profile)}


def symbol_allowed(
    db_path: str | Path,
    symbol: str,
    *,
    profile: str = INTRADAY_FX_PROFILE,
) -> tuple[bool, str | None]:
    """True si el símbolo puede abrirse dentro del perfil; nunca bloquea cierres."""
    if profile != INTRADAY_FX_PROFILE:
        return True, None
    allowed = {item.upper() for item in allowed_symbols(db_path, profile=profile)}
    symbol_upper = str(symbol or "").strip().upper()
    if symbol_upper in allowed:
        return True, None
    reason = (
        f"símbolo {symbol_upper or '?'} no permitido en {profile}: solo "
        f"{', '.join(sorted(allowed)) or 'sin aliases descubiertos'}"
    )
    return False, reason


__all__ = [
    "ASSET_CLASSES",
    "INTRADAY_FX_PROFILE",
    "UNIVERSE_CANDIDATES",
    "aliases",
    "allowed_symbols",
    "canonical_symbols",
    "discover",
    "symbol_allowed",
]
