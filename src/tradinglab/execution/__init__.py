from __future__ import annotations

from ..config import Settings
from .alpaca import AlpacaBroker, AlpacaError
from .paper import PaperBroker


def get_broker(settings: Settings, db_path=None):
    """Devuelve el broker configurado: paper interno o Alpaca."""
    if settings.execution.broker == "alpaca":
        return AlpacaBroker(paper=(settings.mode != "live"), db_path=db_path)
    if db_path is None:
        from ..config import DEFAULT_DB

        db_path = DEFAULT_DB
    return PaperBroker(
        db_path,
        settings.starting_cash,
        settings.execution.commission_bps,
        settings.execution.slippage_bps,
    )


__all__ = ["PaperBroker", "AlpacaBroker", "AlpacaError", "get_broker"]
