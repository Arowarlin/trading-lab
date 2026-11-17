"""Lógica de trailing compartida por el script manual y el carril IA.

`next_stop` calcula el nuevo SL de una posición:
- breakeven al llegar a `be_r` R;
- trailing a `atr_mult` × ATR desde `trail_r` R, sin alejar nunca el stop y
  sin dejarlo peor que breakeven cuando la operación ya está a favor.
"""
from __future__ import annotations


def _is_short(side: str) -> bool:
    return str(side).lower() in {"sell", "short"}


def next_stop(
    *,
    side: str,
    entry: float,
    best: float,
    atr_value: float,
    current_sl: float,
    profit_r: float,
    be_r: float = 0.5,
    trail_r: float = 1.0,
    atr_mult: float = 1.0,
    digits: int = 2,
    min_distance: float = 0.0,
) -> float | None:
    """Nuevo SL o None. `best` es el extremo favorable (mínimo en corto)."""
    short = _is_short(side)
    candidate: float | None = None
    if profit_r >= trail_r:
        candidate = best + atr_mult * atr_value if short else best - atr_mult * atr_value
        # Nunca peor que breakeven: si el ATR es más ancho que el beneficio,
        # el trail quedaría en pérdida. En corto manda el SL más bajo.
        candidate = min(candidate, entry) if short else max(candidate, entry)
    elif profit_r >= be_r:
        candidate = entry
    if candidate is None:
        return None
    candidate = round(float(candidate), int(digits))
    if short:
        if current_sl and candidate >= current_sl - 1e-9:
            return None
        if candidate <= best + min_distance - 1e-9:
            return None
    else:
        if current_sl and candidate <= current_sl + 1e-9:
            return None
        if candidate >= best - min_distance + 1e-9:
            return None
    return candidate


def tp_protection_stop(
    *,
    side: str,
    entry: float,
    tp: float,
    best: float,
    price: float,
    current_sl: float,
    be_at: float = 0.50,
    lock_at: float = 0.80,
    lock_profit: float = 0.50,
    digits: int = 2,
    min_distance: float = 0.0,
) -> float | None:
    """SL por avance al TP: BE al 50 % y 50 % del trayecto al 80 %.

    `best` es el extremo favorable alcanzado (mínimo en corto, máximo en
    largo) y `price` el precio actual. Nunca aleja el stop ni lo deja del
    lado equivocado del mercado. Si el precio ya devolvió el tramo del 80 %,
    cae a breakeven cuando ese nivel sigue siendo válido.
    """
    short = _is_short(side)
    entry = float(entry)
    tp = float(tp)
    best = float(best)
    price = float(price)
    if entry <= 0 or tp <= 0:
        return None
    distance = entry - tp if short else tp - entry
    if distance <= 0:
        return None
    advance = entry - best if short else best - entry
    if advance <= 0:
        return None
    progress = advance / distance
    if progress >= lock_at:
        candidate = (
            entry - lock_profit * distance
            if short
            else entry + lock_profit * distance
        )
    elif progress >= be_at:
        candidate = entry
    else:
        return None
    candidate = round(float(candidate), int(digits))

    def valid(value: float) -> bool:
        if short:
            if current_sl and value >= current_sl - 1e-9:
                return False
            if price and value <= price + min_distance - 1e-9:
                return False
        else:
            if current_sl and value <= current_sl + 1e-9:
                return False
            if price and value >= price - min_distance + 1e-9:
                return False
        return True

    if valid(candidate):
        return candidate
    if progress >= lock_at:
        be = round(entry, int(digits))
        if valid(be):
            return be
    return None
